# Core Adapters Package
# Provides abstract adapter interfaces for swappable external service backends.
#
# Available adapters:
# - EmailSendingAdapter: Email sending (Instantly, Resend, SES, SMTP)

from core.adapters.email_sending import (  # noqa: F401
    EmailSendingAdapter,
    EmailBackend,
    DeliveryStatus,
    SendResult,
    EmailAccount,
    DomainHealth,
    MockEmailAdapter,
    get_email_adapter,
)
