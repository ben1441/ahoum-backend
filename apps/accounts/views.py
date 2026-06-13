from rest_framework import status
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import (
    LoginSerializer,
    MeSerializer,
    ResendOTPSerializer,
    SignupSerializer,
    VerifyEmailSerializer,
)

GENERIC_OTP_SENT = (
    "If this email is not already registered, a 6-digit verification code has been sent."
)


class SignupView(APIView):
    permission_classes = [AllowAny]
    serializer_class = SignupSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.signup(**serializer.validated_data)
        # Identical response whether or not the email already existed (anti-enumeration).
        return Response({"detail": GENERIC_OTP_SENT}, status=status.HTTP_201_CREATED)


class VerifyEmailView(APIView):
    permission_classes = [AllowAny]
    serializer_class = VerifyEmailSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.verify_email(**serializer.validated_data)
        return Response({"detail": "Email verified. You can now log in."})


class ResendOTPView(APIView):
    permission_classes = [AllowAny]
    serializer_class = ResendOTPSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.resend_otp(**serializer.validated_data)
        return Response({"detail": GENERIC_OTP_SENT})


class LoginView(APIView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)


class MeView(RetrieveAPIView):
    serializer_class = MeSerializer

    def get_object(self):
        return self.request.user
