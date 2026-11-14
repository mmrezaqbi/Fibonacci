import io
import json
import zipfile

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .templatetags.money_tags import money
from .templatetags.nav_tags import section_for
from .xlsx import build_xlsx
from .widgets import MoneyInput
from .invoice_utils import clean_buyer_name, is_valid_mobile, normalize_phone
from .models import ActivityLog, Color, Invoice, Product, ProductVariant, Size, StockTransaction, StoreSettings, Warehouse

User = get_user_model()


class BuyerHelpersTests(SimpleTestCase):
    def test_normalize_phone_variants(self):
        for raw in ("09123456789", "۰۹۱۲۳۴۵۶۷۸۹", "+98 912 345 6789", "0098-912-345-6789", "9123456789"):
            self.assertEqual(normalize_phone(raw), "09123456789", raw)

    def test_is_valid_mobile(self):
        self.assertTrue(is_valid_mobile("09123456789"))
        self.assertFalse(is_valid_mobile("0912345678"))
        self.assertFalse(is_valid_mobile("02112345678"))
        self.assertFalse(is_valid_mobile(""))

    def test_clean_buyer_name_unifies_arabic_letters(self):
        self.assertEqual(clean_buyer_name("  علي   كريمي "), "علی کریمی")


class MoneyTests(SimpleTestCase):
    def test_money_filter_groups_by_three(self):
        self.assertEqual(money(1250000), "1,250,000")
        self.assertEqual(money("999"), "999")
        self.assertEqual(money(0), "0")
        self.assertEqual(money(None), "")

    def test_money_input_formats_and_strips_separators(self):
        w = MoneyInput()
        self.assertEqual(w.format_value(1250000), "1,250,000")
        self.assertEqual(w.value_from_datadict({"price": "۱,۲۵۰,۰۰۰"}, {}, "price"), "1250000")


class NavSectionTests(SimpleTestCase):
    def test_sub_pages_keep_their_menu_item_active(self):
        cases = {
            "home": "home", "product_detail": "products", "category_edit": "categories",
            "warehouse_detail": "warehouses", "report_sales": "reports", "invoice_detail": "reports",
            "user_edit": "settings", "color_list": "settings", "store_settings": "settings",
            "product_manage_edit": "settings", "woo_settings": "settings", "unknown": "",
        }
        for name, expected in cases.items():
            self.assertEqual(section_for(name), expected, name)


class InvoiceBuyerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("admin", password="pw", is_superuser=True, is_staff=True)
        cls.warehouse = Warehouse.objects.create(name="مرکزی")
        color = Color.objects.create(name="مشکی", code="BLK")
        size = Size.objects.create(name="M", sort_order=1)
        product = Product.objects.create(name="پیراهن", sku="SH1", price=100000)
        cls.variant = ProductVariant.objects.create(product=product, color=color, size=size)
        StockTransaction(variant=cls.variant, warehouse=cls.warehouse,
                         type=StockTransaction.Type.IN, quantity=50).save()

    def setUp(self):
        self.client.force_login(self.admin)

    def _submit(self, **extra):
        payload = {
            "type": "out", "warehouse": self.warehouse.pk, "note": "",
            "items": [{"variant": self.variant.pk, "quantity": 2, "price": 150000}],
        }
        payload.update(extra)
        return self.client.post(
            reverse("application:api_invoice_submit"), json.dumps(payload), content_type="application/json",
        )

    def test_out_invoice_requires_buyer_name_and_phone(self):
        self.assertEqual(self._submit().status_code, 400)
        self.assertEqual(self._submit(buyer_name="علی", buyer_phone="123").status_code, 400)
        self.assertEqual(self._submit(buyer_name="", buyer_phone="09123456789").status_code, 400)
        self.assertFalse(Invoice.objects.exists())
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 50)

    def test_out_invoice_saves_buyer_and_links_transactions(self):
        StoreSettings.objects.update_or_create(pk=1, defaults={"store_name": "فروشگاه فیبوناچی"})
        res = self._submit(buyer_name="علي رضایی", buyer_phone="۰۹۱۲ ۳۴۵ ۶۷۸۹")
        self.assertEqual(res.status_code, 200, res.content)
        data = res.json()
        self.assertEqual(data["buyer_name"], "علی رضایی")
        self.assertEqual(data["buyer_phone"], "09123456789")
        self.assertEqual(data["store_name"], "فروشگاه فیبوناچی")

        invoice = Invoice.objects.get(code=data["code"])
        self.assertEqual(invoice.buyer_phone, "09123456789")
        self.assertEqual(invoice.transactions.count(), 1)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 48)

    def test_in_invoice_does_not_need_buyer(self):
        res = self._submit(type="in", items=[{"variant": self.variant.pk, "quantity": 5}])
        self.assertEqual(res.status_code, 200, res.content)
        invoice = Invoice.objects.get(code=res.json()["code"])
        self.assertEqual((invoice.buyer_name, invoice.buyer_phone), ("", ""))

    def test_invoice_report_search_by_code_phone_and_name(self):
        first = self._submit(buyer_name="علی رضایی", buyer_phone="09121111111").json()
        second = self._submit(buyer_name="مریم احمدی", buyer_phone="09352222222").json()
        url = reverse("application:report_invoices")

        def codes(q):
            res = self.client.get(url, {"q": q})
            self.assertEqual(res.status_code, 200)
            return {inv.code for inv in res.context["page_obj"]}

        self.assertEqual(codes(first["code"]), {first["code"]})
        self.assertEqual(codes(first["code"].lower()), {first["code"]})
        self.assertEqual(codes("09352222222"), {second["code"]})
        self.assertEqual(codes("۰۹۳۵۲۲۲۲۲۲۲"), {second["code"]})
        self.assertEqual(codes("9121111111"), {first["code"]})
        self.assertEqual(codes("رضایی"), {first["code"]})
        self.assertEqual(codes("مریم احمدی"), {second["code"]})
        self.assertEqual(codes("ناموجود"), set())
        self.assertEqual(codes(""), {first["code"], second["code"]})

    def test_invoice_detail_shows_buyer_and_store_name(self):
        StoreSettings.objects.update_or_create(pk=1, defaults={"store_name": "فروشگاه فیبوناچی"})
        data = self._submit(buyer_name="علی رضایی", buyer_phone="09121111111").json()
        invoice = Invoice.objects.get(code=data["code"])
        res = self.client.get(reverse("application:invoice_detail", args=[invoice.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "فروشگاه فیبوناچی")
        self.assertContains(res, "علی رضایی")
        self.assertContains(res, "09121111111")

    def test_store_settings_can_be_added_and_edited_by_admin(self):
        url = reverse("application:store_settings")
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, {"store_name": "  فروشگاه   اول "})
        self.assertEqual(StoreSettings.load().store_name, "فروشگاه اول")
        self.client.post(url, {"store_name": "فروشگاه دوم"})
        self.assertEqual(StoreSettings.load().store_name, "فروشگاه دوم")

    def test_store_settings_blocked_for_non_admin(self):
        viewer = User.objects.create_user("viewer", password="pw")
        self.client.force_login(viewer)
        res = self.client.post(reverse("application:store_settings"), {"store_name": "هک"})
        self.assertEqual(res.status_code, 302)
        self.assertEqual(StoreSettings.load().store_name, "")


class ReportsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("admin", password="pw", is_superuser=True, is_staff=True)
        cls.warehouse = Warehouse.objects.create(name="مرکزی")
        color = Color.objects.create(name="مشکی", code="BLK")
        size = Size.objects.create(name="M", sort_order=1)
        cls.product = Product.objects.create(name="پیراهن", sku="SH1", price=100000)
        cls.variant = ProductVariant.objects.create(product=cls.product, color=color, size=size)
        StockTransaction(variant=cls.variant, warehouse=cls.warehouse,
                         type=StockTransaction.Type.IN, quantity=50).save()

    def setUp(self):
        self.client.force_login(self.admin)

    def _sell(self, qty, price):
        res = self.client.post(
            reverse("application:api_invoice_submit"),
            json.dumps({
                "type": "out", "warehouse": self.warehouse.pk, "note": "",
                "buyer_name": "علی رضایی", "buyer_phone": "09121111111",
                "items": [{"variant": self.variant.pk, "quantity": qty, "price": price}],
            }),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200, res.content)

    def test_sales_report_totals(self):
        self._sell(2, 150000)
        self._sell(3, 100000)
        for group in ("day", "month", "product"):
            res = self.client.get(reverse("application:report_sales"), {"group": group})
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.context["summary"]["qty"], 5)
            self.assertEqual(res.context["summary"]["amount"], 600000)
            self.assertEqual(res.context["summary"]["invoices"], 2)
            self.assertEqual(res.context["summary"]["average"], 300000)

    def test_asset_report_uses_base_price_times_stock(self):
        res = self.client.get(reverse("application:report_assets"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["summary"]["stock"], 50)
        self.assertEqual(res.context["summary"]["value"], 5000000)
        self._sell(10, 999999)  # قیمت فروش در دارایی اثری ندارد، فقط موجودی کم می‌شود
        res = self.client.get(reverse("application:report_assets"))
        self.assertEqual(res.context["summary"]["value"], 4000000)

    def test_activity_log_records_login_and_invoice(self):
        self.client.logout()
        self.client.login(username="admin", password="pw")
        self._sell(1, 100000)
        actions = set(ActivityLog.objects.filter(username="admin").values_list("action", flat=True))
        self.assertTrue({"login", "invoice_out"} <= actions)
        res = self.client.get(reverse("application:report_activity"), {"action": "invoice_out"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context["summary"]["count"], 1)

    def test_activity_report_is_admin_only(self):
        viewer = User.objects.create_user("viewer", password="pw")
        self.client.force_login(viewer)
        res = self.client.get(reverse("application:report_activity"))
        self.assertEqual(res.status_code, 302)


class ExportAndPrintTests(ReportsTests):
    REPORTS = ["report_transactions", "report_invoices", "report_stock",
               "report_sales", "report_assets", "report_activity"]

    def test_xlsx_writer_makes_valid_zip(self):
        data = build_xlsx([("شیت/۱", ["الف", "ب"], [["=1+1", 5], ["09121111111", None]])])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            self.assertIsNone(z.testzip())
            self.assertIn("xl/worksheets/sheet1.xml", z.namelist())

    def test_every_report_exports_xlsx(self):
        self._sell(2, 150000)
        for name in self.REPORTS:
            res = self.client.get(reverse(f"application:{name}"), {"export": "xlsx"})
            self.assertEqual(res.status_code, 200, name)
            self.assertIn("spreadsheetml", res["Content-Type"], name)
            self.assertIn(".xlsx", res["Content-Disposition"], name)
            with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                self.assertIsNone(z.testzip(), name)

    def test_export_respects_filters(self):
        self._sell(2, 150000)
        res = self.client.get(reverse("application:report_invoices"), {"export": "xlsx", "q": "ناموجود"})
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertNotIn("علی رضایی", xml)

    def test_warehouse_pages_do_not_show_export_buttons(self):
        res = self.client.get(reverse("application:warehouse_detail", args=[self.warehouse.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.context["can_export"])
        self.assertNotContains(res, "export=xlsx")
        res = self.client.get(reverse("application:report_sales"))
        self.assertTrue(res.context["can_export"])

    def test_print_mode_shows_store_name_and_all_rows(self):
        StoreSettings.objects.update_or_create(pk=1, defaults={"store_name": "فروشگاه فیبوناچی"})
        for _ in range(3):
            self._sell(1, 100000)
        for name in self.REPORTS:
            res = self.client.get(reverse(f"application:{name}"), {"print": "1"})
            self.assertEqual(res.status_code, 200, name)
            self.assertContains(res, "window.print()", msg_prefix=name)
            self.assertContains(res, "فروشگاه فیبوناچی", msg_prefix=name)
