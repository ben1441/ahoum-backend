"""Email rendering and sending. Templates live in templates/emails/."""

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string


def _send(template: str, context: dict, subject: str, recipient: str) -> None:
    body = render_to_string(f"emails/{template}.txt", context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient])


def send_otp_email(user, code: str) -> None:
    _send(
        "otp",
        {"code": code, "ttl_minutes": settings.OTP_TTL_SECONDS // 60},
        "Your Ahoum verification code",
        user.email,
    )


def send_follow_up_email(enrollment) -> None:
    _send(
        "follow_up",
        {"event": enrollment.event, "user": enrollment.seeker},
        f"How are you finding {enrollment.event.title}?",
        enrollment.seeker.email,
    )


def send_reminder_email(enrollment) -> None:
    _send(
        "reminder",
        {"event": enrollment.event, "user": enrollment.seeker},
        f"Starting soon: {enrollment.event.title}",
        enrollment.seeker.email,
    )
