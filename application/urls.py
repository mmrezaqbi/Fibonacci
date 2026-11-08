from django.contrib.auth import views as auth_views
from django.urls import path

from . import reports, settings_pages, views, warehouses, woo_pages

app_name = "application"

urlpatterns = [
    path("", views.home, name="home"),
    path("products/", views.product_list, name="product_list"),
    path("products/new/", views.product_create, name="product_create"),
    path("products/<int:pk>/", views.product_detail, name="product_detail"),
    path("stock/in/", views.stock_in, name="stock_in"),
    path("stock/out/", views.stock_out, name="stock_out"),
    path("warehouses/", warehouses.warehouse_list, name="warehouse_list"),
    path("warehouses/<int:pk>/", warehouses.warehouse_detail, name="warehouse_detail"),
    path("reports/", reports.reports_index, name="reports"),
    path("reports/transactions/", reports.report_transactions, name="report_transactions"),
    path("reports/stock/", reports.report_stock, name="report_stock"),
    path("settings/", settings_pages.settings_index, name="settings_index"),
    path("settings/colors/", settings_pages.simple_list, {"kind": "color"}, name="color_list"),
    path("settings/colors/<int:pk>/edit/", settings_pages.simple_edit, {"kind": "color"}, name="color_edit"),
    path("settings/colors/<int:pk>/delete/", settings_pages.simple_delete, {"kind": "color"}, name="color_delete"),
    path("settings/sizes/", settings_pages.simple_list, {"kind": "size"}, name="size_list"),
    path("settings/sizes/<int:pk>/edit/", settings_pages.simple_edit, {"kind": "size"}, name="size_edit"),
    path("settings/sizes/<int:pk>/delete/", settings_pages.simple_delete, {"kind": "size"}, name="size_delete"),
    path("settings/warehouses/", settings_pages.simple_list, {"kind": "warehouse"}, name="warehouse_settings"),
    path("settings/warehouses/<int:pk>/edit/", settings_pages.simple_edit, {"kind": "warehouse"}, name="warehouse_edit"),
    path("settings/warehouses/<int:pk>/delete/", settings_pages.simple_delete, {"kind": "warehouse"}, name="warehouse_delete"),
    path("settings/users/", settings_pages.user_list, name="user_list"),
    path("settings/users/new/", settings_pages.user_create, name="user_create"),
    path("settings/users/<int:pk>/edit/", settings_pages.user_edit, name="user_edit"),
    path("settings/users/<int:pk>/delete/", settings_pages.user_delete, name="user_delete"),
    path("settings/woocommerce/", woo_pages.woo_settings, name="woo_settings"),
    path("woocommerce/webhook/", woo_pages.woo_webhook, name="woo_webhook"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]