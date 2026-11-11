"""
مدیریت دسته‌بندی‌ها: لیست + افزودن، ویرایش و حذف (با انتقال کالاها به دسته‌ی دیگر).

فرض‌ها: مدل Category فیلد «name» دارد و Product با فیلد «category» به آن وصل است.
شمارش کالاها با Subquery انجام می‌شود تا به related_name وابسته نباشد.
"""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, Subquery
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Category, Product


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={
                "placeholder": "نام دسته‌بندی (مثلاً پیراهن مردانه)",
                "autocomplete": "off",
                "maxlength": 100,
            }),
        }
        labels = {"name": "نام دسته‌بندی"}

    def clean_name(self):
        # فاصله‌های اضافی حذف می‌شود و تکراری بودن بدون توجه به حروف بزرگ/کوچک چک می‌شود
        name = " ".join(self.cleaned_data["name"].split())
        if not name:
            raise forms.ValidationError("نام دسته‌بندی را وارد کنید.")
        duplicate = Category.objects.filter(name__iexact=name)
        if self.instance.pk:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise forms.ValidationError("دسته‌بندی دیگری با این نام وجود دارد.")
        return name


def _with_counts():
    per_category = (
        Product.objects.filter(category_id=OuterRef("pk"))
        .order_by()
        .values("category_id")
        .annotate(c=Count("pk"))
        .values("c")
    )
    return Category.objects.annotate(
        product_count=Coalesce(Subquery(per_category, output_field=IntegerField()), 0)
    ).order_by("name")


@login_required
def category_list(request):
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(request, f"دسته‌بندی «{category.name}» اضافه شد.")
            return redirect("application:category_list")
    else:
        form = CategoryForm()

    categories = list(_with_counts())
    return render(request, "category_list.html", {
        "form": form,
        "categories": categories,
        "total_products": sum(c.product_count for c in categories),
        "uncategorized": Product.objects.filter(category__isnull=True).count(),
    })


@login_required
def category_edit(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == "POST":
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, "تغییرات دسته‌بندی ذخیره شد.")
            return redirect("application:category_list")
    else:
        form = CategoryForm(instance=category)
    count = Product.objects.filter(category=category).count()
    return render(request, "category_edit.html", {"form": form, "category": category, "product_count": count})


@login_required
@require_POST
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    products = Product.objects.filter(category=category)
    count = products.count()
    name = category.name

    try:
        if count:
            move_to = request.POST.get("move_to", "")
            target = None
            if move_to.isdigit():
                target = Category.objects.exclude(pk=category.pk).filter(pk=int(move_to)).first()
            if target is None:
                messages.error(request, f"«{name}» {count} کالا دارد؛ دسته‌بندی مقصد را برای انتقال کالاها انتخاب کنید.")
                return redirect("application:category_list")
            with transaction.atomic():
                products.update(category=target)
                category.delete()
            messages.success(request, f"دسته‌بندی «{name}» حذف شد و {count} کالا به «{target.name}» منتقل شد.")
        else:
            category.delete()
            messages.success(request, f"دسته‌بندی «{name}» حذف شد.")
    except ProtectedError:
        messages.error(request, f"«{name}» به رکوردهای دیگری وصل است و حذف نشد.")
    return redirect("application:category_list")
