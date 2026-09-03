"""
Reusable QR Code generation service for certificates.

Encodes strictly the public verification URL:
    <absolute_site_url>/verify/<verification_token>/

Personal data (student email, phone, college, certificate dump) is NEVER encoded.
"""

from __future__ import annotations

import io
import re
from typing import TYPE_CHECKING, Optional

from django.conf import settings
from django.core.files.base import ContentFile
import qrcode
from qrcode.constants import ERROR_CORRECT_M

if TYPE_CHECKING:
    from PIL.Image import Image
    from certificates.models import Certificate


class QRCodeService:
    """Reusable QR code generation and verification service."""

    DEFAULT_BOX_SIZE = 10
    DEFAULT_BORDER = 4
    DEFAULT_ERROR_CORRECTION = ERROR_CORRECT_M

    @staticmethod
    def get_verification_url(
        verification_token: str,
        base_url: Optional[str] = None,
    ) -> str:
        """Construct the absolute public verification URL for a token.

        Format:
            <absolute_site_url>/verify/<verification_token>/

        Parameters
        ----------
        verification_token:
            The unique verification token of the certificate.
        base_url:
            Optional base URL (defaults to ``settings.SITE_URL`` or ``http://127.0.0.1:8000``).

        Returns
        -------
        str
            The absolute verification URL with trailing slash.
        """
        if not base_url:
            base_url = getattr(settings, "SITE_URL", "http://127.0.0.1:8000")

        base_clean = base_url.rstrip("/")
        token_clean = str(verification_token).strip("/")
        return f"{base_clean}/verify/{token_clean}/"

    @staticmethod
    def get_safe_filename(certificate_id: str) -> str:
        """Generate a safe, sanitized filename for the QR code image.

        Parameters
        ----------
        certificate_id:
            The human-readable certificate ID (e.g. ``"COMP-INT-2026-000001"``).

        Returns
        -------
        str
            A sanitized filename, e.g. ``"qr_COMP-INT-2026-000001.png"``.
        """
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", certificate_id)
        return f"qr_{sanitized}.png"

    @classmethod
    def create_qr_object(
        cls,
        data: str,
        box_size: int = DEFAULT_BOX_SIZE,
        border: int = DEFAULT_BORDER,
    ) -> qrcode.QRCode:
        """Create a configured QRCode object with the provided data payload."""
        qr = qrcode.QRCode(
            version=None,  # Automatically determine version based on content
            error_correction=cls.DEFAULT_ERROR_CORRECTION,
            box_size=box_size,
            border=border,
        )
        qr.add_data(data)
        qr.make(fit=True)
        return qr

    @classmethod
    def generate_qr_image(
        cls,
        data: str,
        box_size: int = DEFAULT_BOX_SIZE,
        border: int = DEFAULT_BORDER,
        fill_color: str = "black",
        back_color: str = "white",
    ) -> Image:
        """Generate a PIL Image for the given URL/data payload using ``qrcode``."""
        qr = cls.create_qr_object(data, box_size=box_size, border=border)
        return qr.make_image(fill_color=fill_color, back_color=back_color)

    @classmethod
    def generate_qr_code_file(
        cls,
        verification_token: str,
        filename: str,
        base_url: Optional[str] = None,
        box_size: int = DEFAULT_BOX_SIZE,
        border: int = DEFAULT_BORDER,
    ) -> ContentFile:
        """Generate the verification URL, render the QR code, and return a Django ``ContentFile``."""
        url = cls.get_verification_url(verification_token, base_url=base_url)
        img = cls.generate_qr_image(url, box_size=box_size, border=border)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return ContentFile(buffer.getvalue(), name=filename)

    @classmethod
    def generate_qr_for_certificate(
        cls,
        certificate: Certificate,
        base_url: Optional[str] = None,
        save: bool = True,
    ) -> Optional[ContentFile]:
        """Generate and attach a QR code image to a certificate.

        Requirements:
          - Encodes only ``<absolute_site_url>/verify/<verification_token>/``.
          - Uses safe filename based on ``certificate.certificate_id``.
          - Stores to ``certificate.qr_code`` ImageField.

        Parameters
        ----------
        certificate:
            The Certificate instance.
        base_url:
            Optional base URL override.
        save:
            Whether to commit the certificate instance to the database.
        """
        # Ensure certificate has ID and verification token
        if not certificate.certificate_id or not certificate.verification_token:
            certificate.save()

        filename = cls.get_safe_filename(certificate.certificate_id)
        content_file = cls.generate_qr_code_file(
            verification_token=certificate.verification_token,
            filename=filename,
            base_url=base_url,
        )

        # Save to ImageField
        certificate.qr_code.save(filename, content_file, save=save)
        return certificate.qr_code

    @classmethod
    def regenerate_qr_code(
        cls,
        certificate: Certificate,
        base_url: Optional[str] = None,
        save: bool = True,
    ) -> Optional[ContentFile]:
        """Regenerate the QR code for a certificate without altering its ID or token.

        Parameters
        ----------
        certificate:
            The existing Certificate instance.
        base_url:
            Optional base URL override.
        save:
            Whether to commit changes.
        """
        original_id = certificate.certificate_id
        original_token = certificate.verification_token

        # Delete existing file if stored
        if certificate.qr_code:
            try:
                certificate.qr_code.delete(save=False)
            except Exception:
                pass

        # Regenerate with same token and safe filename
        result = cls.generate_qr_for_certificate(
            certificate,
            base_url=base_url,
            save=save,
        )

        # Invariant check: certificate_id and verification_token must remain untouched
        assert certificate.certificate_id == original_id
        assert certificate.verification_token == original_token
        return result

    @staticmethod
    def validate_payload_has_no_pii(
        payload: str,
        student_email: Optional[str] = None,
        student_phone: Optional[str] = None,
        student_college: Optional[str] = None,
    ) -> bool:
        """Helper to verify that no student personal identifiable info is in QR payload."""
        if student_email and student_email.lower() in payload.lower():
            return False
        if student_phone and student_phone in payload:
            return False
        if student_college and student_college.lower() in payload.lower():
            return False
        return True
