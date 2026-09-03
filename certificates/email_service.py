"""Certificate email delivery service abstraction.

This module provides a reusable, robust email delivery service for sending
official certificates to students via Django's email backend.

Key Features:
-------------
- Dual-format delivery: Rich HTML email + Plaintext fallback.
- Context injection: Student name, program, certificate ID, verification URL,
  download URL, and signatory details.
- PDF attachment: Automatically attaches the official WeasyPrint PDF if available.
- Resilience: Failures in email transmission are caught and logged; the certificate
  remains valid.
- Audit & Logging: Records email delivery events in AuditLog and system logs.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Tuple

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser
    from certificates.models import Certificate

logger = logging.getLogger(__name__)


class CertificateEmailService:
    """Service abstraction for delivering certificate notifications to students."""

    HTML_TEMPLATE = "emails/certificate_delivery.html"
    TXT_TEMPLATE = "emails/certificate_delivery.txt"

    @classmethod
    def get_verification_url(
        cls,
        verification_token: str,
        base_url: Optional[str] = None,
    ) -> str:
        """Construct the absolute verification URL."""
        from certificates.services import QRCodeService
        return QRCodeService.get_verification_url(verification_token, base_url=base_url)

    @classmethod
    def get_download_url(
        cls,
        verification_token: str,
        base_url: Optional[str] = None,
    ) -> str:
        """Construct the absolute public PDF download URL."""
        if not base_url:
            base_url = getattr(settings, "SITE_URL", "http://127.0.0.1:8000")
        base_clean = base_url.rstrip("/")
        token_clean = str(verification_token).strip("/")
        return f"{base_clean}/verify/{token_clean}/download/"

    @classmethod
    def build_email_context(
        cls,
        certificate: Certificate,
        base_url: Optional[str] = None,
    ) -> dict:
        """Assemble rendering context for email templates."""
        from users.models import CompanySettings

        company = None
        try:
            company = CompanySettings.get_instance()
        except Exception:
            pass

        org_name = (
            (certificate.template.organization if certificate.template else None)
            or (company.name if company else None)
            or "Certificate Authority"
        )

        verification_url = cls.get_verification_url(
            certificate.verification_token, base_url=base_url
        )
        download_url = cls.get_download_url(
            certificate.verification_token, base_url=base_url
        )

        return {
            "certificate": certificate,
            "student": certificate.student,
            "certificate_type_display": certificate.get_certificate_type_display(),
            "organization_name": org_name,
            "company": company,
            "verification_url": verification_url,
            "download_url": download_url,
        }

    @classmethod
    def send_certificate_email(
        cls,
        certificate: Certificate,
        base_url: Optional[str] = None,
        attach_pdf: bool = True,
        user: Optional[AbstractBaseUser] = None,
        ip_address: Optional[str] = None,
        fail_silently: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """Send the official certificate issuance email to the recipient student.

        Parameters
        ----------
        certificate:
            The issued Certificate instance.
        base_url:
            Optional base URL for link construction.
        attach_pdf:
            Whether to attach the compiled PDF file to the email.
        user:
            User who triggered the email action (for AuditLog).
        ip_address:
            Client IP address (for AuditLog).
        fail_silently:
            If True, suppresses any exception and returns (False, error).

        Returns
        -------
        Tuple[bool, Optional[str]]
            (success, error_message)
        """
        from users.models import AuditLog

        student = getattr(certificate, "student", None)
        recipient_email = getattr(student, "email", None) if student else None

        if not recipient_email or not recipient_email.strip():
            err_msg = f"Cannot send certificate email: student has no valid email address."
            logger.warning(
                "Certificate email skipped for cert %s: no recipient email",
                certificate.certificate_id,
            )
            return False, err_msg

        try:
            context = cls.build_email_context(certificate, base_url=base_url)
            org_name = context["organization_name"]
            type_display = context["certificate_type_display"]

            subject = f"Your Official {type_display} - {certificate.certificate_id} ({org_name})"
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "webmaster@localhost")

            # Render HTML and Text versions
            html_body = render_to_string(cls.HTML_TEMPLATE, context)
            text_body = render_to_string(cls.TXT_TEMPLATE, context)

            # Construct EmailMultiAlternatives message
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=from_email,
                to=[recipient_email],
            )
            msg.attach_alternative(html_body, "text/html")

            # Attach PDF if requested and file is present
            if attach_pdf and certificate.certificate_pdf:
                try:
                    pdf_filename = f"{certificate.certificate_id}.pdf"
                    if hasattr(certificate.certificate_pdf, "read"):
                        certificate.certificate_pdf.open("rb")
                        pdf_content = certificate.certificate_pdf.read()
                        msg.attach(pdf_filename, pdf_content, "application/pdf")
                    elif hasattr(certificate.certificate_pdf, "path"):
                        with open(certificate.certificate_pdf.path, "rb") as pf:
                            msg.attach(pdf_filename, pf.read(), "application/pdf")
                except Exception as pdf_err:
                    logger.warning(
                        "Could not attach PDF file for cert %s: %s",
                        certificate.certificate_id,
                        pdf_err,
                    )

            # Send email
            msg.send(fail_silently=False)

            # Update certificate model delivery flags
            certificate.email_sent = True
            certificate.email_sent_at = timezone.now()
            certificate.save(update_fields=["email_sent", "email_sent_at"])

            # Record success in AuditLog
            user_email = (
                getattr(user, "email", None)
                if user and getattr(user, "is_authenticated", False)
                else None
            )
            AuditLog.objects.create(
                action="EMAIL",
                object_type="Certificate",
                object_id=certificate.certificate_id,
                user_email=user_email,
                changes={
                    "status": "SENT",
                    "recipient_email": recipient_email,
                    "student_name": student.full_name,
                    "certificate_id": certificate.certificate_id,
                    "timestamp": str(certificate.email_sent_at),
                },
                ip_address=ip_address,
            )

            logger.info(
                "Certificate email successfully sent to %s for cert %s",
                recipient_email,
                certificate.certificate_id,
            )
            return True, None

        except Exception as exc:
            err_msg = str(exc)
            logger.error(
                "Failed to send certificate email for %s to %s: %s",
                certificate.certificate_id,
                recipient_email,
                err_msg,
                exc_info=True,
            )

            # Record failure in AuditLog
            user_email = (
                getattr(user, "email", None)
                if user and getattr(user, "is_authenticated", False)
                else None
            )
            try:
                AuditLog.objects.create(
                    action="EMAIL",
                    object_type="Certificate",
                    object_id=certificate.certificate_id,
                    user_email=user_email,
                    changes={
                        "status": "FAILED",
                        "recipient_email": recipient_email,
                        "certificate_id": certificate.certificate_id,
                        "error": err_msg,
                    },
                    ip_address=ip_address,
                )
            except Exception:
                pass

            if not fail_silently:
                # Return failure tuple rather than crashing
                return False, err_msg

            return False, err_msg
