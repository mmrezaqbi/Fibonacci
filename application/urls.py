
from django.contrib.auth import views as auth_views
from django.urls import path
from . import views , reports

app_name = "application"

urlpatterns = [
    path("", views.home, name="home"),
    path("products/", views.product_list, name="product_list"),
    path("products/<int:pk>/", views.product_detail, name="product_detail"),
    path("products/new/", views.product_create, name="product_create"),
    path("stock/out/", views.stock_out, name="stock_out"),
    path("stock/in/", views.stock_in, name="stock_in"),
    path("reports/", reports.reports_index, name="reports"),
    path("reports/transactions/", reports.report_transactions, name="report_transactions"),
    path("reports/stock/", reports.report_stock, name="report_stock"),

    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]