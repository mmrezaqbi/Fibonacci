from django.urls import path
from.views import login_user , logout_user

app_name = 'accounts'

urlpatterns = [
    path("login/" , login_user , name="login"),
    path("logout/" , login_user , name="logout")
]
