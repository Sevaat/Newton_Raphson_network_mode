from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import include, path

from network.forms import StyledLoginForm
from network.views import SignupView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", LoginView.as_view(
        template_name="registration/auth_form.html",
        authentication_form=StyledLoginForm,
        extra_context={"title": "Вход", "is_login": True}), name="login"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("accounts/signup/", SignupView.as_view(), name="signup"),
    path("", include("network.urls")),
]
