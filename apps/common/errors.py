"""Domain error types.

Every API error response has the shape ``{"detail": <message>, "code": <stable_code>}``.
Codes are defined here once so clients (and tests) never match on message strings.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class ErrorCode:
    VALIDATION_ERROR = "validation_error"
    NOT_AUTHENTICATED = "not_authenticated"
    AUTHENTICATION_FAILED = "authentication_failed"
    TOKEN_NOT_VALID = "token_not_valid"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    THROTTLED = "throttled"
    SERVER_ERROR = "server_error"

    EMAIL_NOT_VERIFIED = "email_not_verified"
    INVALID_CREDENTIALS = "invalid_credentials"
    OTP_INVALID = "otp_invalid"
    OTP_EXPIRED = "otp_expired"
    OTP_MAX_ATTEMPTS = "otp_max_attempts"
    OTP_COOLDOWN = "otp_cooldown"

    EVENT_FULL = "event_full"
    EVENT_ALREADY_STARTED = "event_already_started"
    ALREADY_ENROLLED = "already_enrolled"
    NOT_ENROLLED = "not_enrolled"


class DomainError(APIException):
    """Base for business-rule violations. Subclasses set status, code and message."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = ErrorCode.VALIDATION_ERROR


class EmailNotVerified(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = ErrorCode.EMAIL_NOT_VERIFIED
    default_detail = "Email address is not verified. Complete OTP verification first."


class InvalidCredentials(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = ErrorCode.INVALID_CREDENTIALS
    default_detail = "No active account found with the given credentials."


class OTPInvalid(DomainError):
    default_code = ErrorCode.OTP_INVALID
    default_detail = "The verification code is incorrect."


class OTPExpired(DomainError):
    default_code = ErrorCode.OTP_EXPIRED
    default_detail = "The verification code has expired. Request a new one."


class OTPMaxAttempts(DomainError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = ErrorCode.OTP_MAX_ATTEMPTS
    default_detail = "Too many incorrect attempts. Request a new verification code."


class OTPCooldown(DomainError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = ErrorCode.OTP_COOLDOWN
    default_detail = "A code was sent recently. Wait before requesting another."


class EventFull(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_code = ErrorCode.EVENT_FULL
    default_detail = "This event has reached its capacity."


class EventAlreadyStarted(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_code = ErrorCode.EVENT_ALREADY_STARTED
    default_detail = "This event has already started."


class AlreadyEnrolled(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_code = ErrorCode.ALREADY_ENROLLED
    default_detail = "You are already enrolled in this event."


class NotEnrolled(DomainError):
    status_code = status.HTTP_409_CONFLICT
    default_code = ErrorCode.NOT_ENROLLED
    default_detail = "You are not enrolled in this event."
