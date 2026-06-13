from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path("signup", views.SignupView.as_view(), name="signup"),
    path("verify-email", views.VerifyEmailView.as_view(), name="verify-email"),
    path("resend-otp", views.ResendOTPView.as_view(), name="resend-otp"),
    path("login", views.LoginView.as_view(), name="login"),
    path("refresh", TokenRefreshView.as_view(), name="refresh"),
    path("me", views.MeView.as_view(), name="me"),
]
