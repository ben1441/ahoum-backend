"""Custom DRF exception handler enforcing the API-wide error contract:

    {"detail": "<human message>", "code": "<stable_error_code>"}

Validation errors additionally carry an ``errors`` mapping with per-field messages.
"""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404, JsonResponse
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.views import exception_handler as drf_exception_handler

from .errors import ErrorCode

STATUS_FALLBACK_CODES = {
    401: ErrorCode.NOT_AUTHENTICATED,
    403: ErrorCode.PERMISSION_DENIED,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
    429: ErrorCode.THROTTLED,
}


def exception_handler(exc, context):
    if isinstance(exc, Http404):
        exc = NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = PermissionDenied()

    response = drf_exception_handler(exc, context)
    if response is None:  # non-API exception -> Django's 500 path (see server_error below)
        return None

    if isinstance(exc, ValidationError):
        errors = _normalize_errors(exc.detail)
        response.data = {
            "detail": _first_message(exc.detail),
            "code": ErrorCode.VALIDATION_ERROR,
            "errors": errors,
        }
    else:
        response.data = {
            "detail": _first_message(exc.detail),
            "code": _resolve_code(exc, response.status_code),
        }
    return response


def _resolve_code(exc: APIException, status_code: int) -> str:
    codes = exc.get_codes()
    if isinstance(codes, dict):
        # e.g. simplejwt's InvalidToken: {"detail": "token_not_valid", ...}
        codes = codes.get("detail") or codes.get("code") or next(iter(codes.values()), None)
    if isinstance(codes, list):
        codes = codes[0] if codes else None
    if not isinstance(codes, str) or codes in ("error", "invalid"):
        return STATUS_FALLBACK_CODES.get(status_code, ErrorCode.VALIDATION_ERROR)
    return codes


def _first_message(detail) -> str:
    """Pull one human-readable message out of DRF's detail structures."""
    if isinstance(detail, str):
        return str(detail)
    if isinstance(detail, list):
        return _first_message(detail[0]) if detail else "Invalid request."
    if isinstance(detail, dict):
        for field, value in detail.items():
            message = _first_message(value)
            if field in ("detail", "non_field_errors"):
                return message
            return f"{field}: {message}"
    return str(detail) if detail else "Invalid request."


def _normalize_errors(detail):
    if isinstance(detail, dict):
        return {key: _normalize_errors(value) for key, value in detail.items()}
    if isinstance(detail, list):
        return [str(item) for item in detail]
    return [str(detail)]


def server_error(request, *args, **kwargs):
    """JSON 500 handler so even unhandled crashes honor the error contract."""
    return JsonResponse(
        {"detail": "Internal server error.", "code": ErrorCode.SERVER_ERROR}, status=500
    )


def not_found(request, exception, *args, **kwargs):
    """JSON 404 for URLs that don't match any route."""
    return JsonResponse({"detail": "Not found.", "code": ErrorCode.NOT_FOUND}, status=404)
