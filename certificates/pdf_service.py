"""
Reusable Certificate PDF generation service using WeasyPrint.

Renders A4 Landscape certificates with professional design, embedded QR codes,
signatures, company logos, and official verified seal.
Ensures zero private information leakage and strictly guarantees single-page layout.
"""

from __future__ import annotations

import base64
import mimetypes
import os
import re
from typing import TYPE_CHECKING, Optional

from django.conf import settings
from django.core.files.base import ContentFile
from django.template.loader import render_to_string
import weasyprint

if TYPE_CHECKING:
    from certificates.models import Certificate


class CertificatePDFService:
    """Reusable service for rendering and generating certificate PDFs via WeasyPrint."""

    TEMPLATE_NAME = "certificates/certificate_pdf.html"

    @staticmethod
    def file_to_data_uri(file_field) -> Optional[str]:
        """Convert a Django FileField/ImageField to a base64 data URI for reliable WeasyPrint embedding."""
        if not file_field:
            return None
        try:
            # Try to read file
            if hasattr(file_field, "open"):
                file_field.open("rb")
                content = file_field.read()
            elif hasattr(file_field, "path") and os.path.exists(file_field.path):
                with open(file_field.path, "rb") as f:
                    content = f.read()
            else:
                return None

            if not content:
                return None

            filename = getattr(file_field, "name", "image.png")
            mime_type, _ = mimetypes.guess_type(filename)
            if not mime_type:
                mime_type = "image/png"

            encoded = base64.b64encode(content).decode("ascii")
            return f"data:{mime_type};base64,{encoded}"
        except Exception:
            return None

    @staticmethod
    def get_safe_filename(certificate_id: str) -> str:
        """Generate a safe, sanitized filename for the certificate PDF."""
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", certificate_id)
        return f"cert_{sanitized}.pdf"

    @classmethod
    def get_certificate_title(cls, certificate: Certificate) -> str:
        """Derive an appropriate uppercase certificate title."""
        type_titles = {
            "INTERNSHIP": "CERTIFICATE OF INTERNSHIP",
            "TRAINING": "CERTIFICATE OF TRAINING",
            "WORKSHOP": "CERTIFICATE OF PARTICIPATION",
            "COURSE": "CERTIFICATE OF COMPLETION",
            "ACHIEVEMENT": "CERTIFICATE OF ACHIEVEMENT",
        }
        return type_titles.get(
            certificate.certificate_type,
            f"CERTIFICATE OF {certificate.get_certificate_type_display().upper()}",
        )

    @classmethod
    def build_context(
        cls,
        certificate: Certificate,
        base_url: Optional[str] = None,
    ) -> dict:
        """Build rendering context for WeasyPrint template."""
        from users.models import CompanySettings
        from certificates.services import QRCodeService

        # QR Code Handling (Saved vs Ephemeral/Preview)
        qr_data_uri = None
        if certificate.qr_code:
            qr_data_uri = cls.file_to_data_uri(certificate.qr_code)
        elif getattr(certificate, "pk", None):
            QRCodeService.generate_qr_for_certificate(
                certificate, base_url=base_url, save=True
            )
            certificate.refresh_from_db()
            qr_data_uri = cls.file_to_data_uri(certificate.qr_code)
        else:
            # Ephemeral certificate preview
            token = certificate.verification_token or "PREVIEW_TOKEN"
            preview_url = QRCodeService.get_verification_url(token, base_url=base_url)
            qr_img = QRCodeService.generate_qr_image(preview_url)
            import io
            buf = io.BytesIO()
            qr_img.save(buf, format="PNG")
            qr_data_uri = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"

        # Company / Template Logo
        company = None
        try:
            company = CompanySettings.get_instance()
        except Exception:
            pass

        logo_data_uri = None
        if certificate.template and certificate.template.logo:
            logo_data_uri = cls.file_to_data_uri(certificate.template.logo)
        if not logo_data_uri and company and company.logo:
            try:
                logo_data_uri = cls.file_to_data_uri(company.logo)
            except Exception:
                pass

        # Signature Image
        signature_data_uri = None
        if certificate.authorized_signatory and certificate.authorized_signatory.signature_image:
            signature_data_uri = cls.file_to_data_uri(certificate.authorized_signatory.signature_image)
        elif certificate.template and certificate.template.signature_image:
            signature_data_uri = cls.file_to_data_uri(certificate.template.signature_image)

        # Organization / Company name
        org_name = (
            (certificate.template.organization if certificate.template else None)
            or (company.name if company else None)
            or (certificate.authorized_signatory.organization if certificate.authorized_signatory else None)
            or "Certificate Authority"
        )

        # Signatory details
        signatory_name = (
            certificate.authorized_signatory.name
            if certificate.authorized_signatory
            else "Authorized Signatory"
        )
        signatory_title = (
            certificate.authorized_signatory.title
            if certificate.authorized_signatory
            else "Director"
        )

        # Certificate Footer Notice
        cert_footer = (company.certificate_footer if company else "")

        return {
            "certificate": certificate,
            "student": getattr(certificate, 'student', None),
            "recipient_name": certificate.student.full_name if getattr(certificate, 'student', None) else "",
            "program": getattr(certificate, 'program', None),
            "program_name": certificate.program.name if getattr(certificate, 'program', None) else "",
            "certificate_id": getattr(certificate, 'certificate_id', ""),
            "issue_date": getattr(certificate, 'issue_date', None),
            "start_date": getattr(certificate, 'start_date', None),
            "end_date": getattr(certificate, 'end_date', None),
            "duration": getattr(certificate, 'duration', None),
            "template": getattr(certificate, 'template', None),
            "authorized_signatory": getattr(certificate, 'authorized_signatory', None),
            "certificate_title": cls.get_certificate_title(certificate),
            "certificate_type_display": certificate.get_certificate_type_display(),
            "organization_name": org_name,
            "company": company,
            "company_name": org_name,
            "certificate_footer": cert_footer,
            "company_address": company.address if company else "",
            "company_website": company.website if company else "",
            "company_email": company.email if company else "",
            "company_phone": company.phone if company else "",
            "company_description": company.description if company else "",
            "signatory_name": signatory_name,
            "signatory_title": signatory_title,
            "logo_data_uri": logo_data_uri,
            "signature_data_uri": signature_data_uri,
            "qr_data_uri": qr_data_uri,
        }

    @classmethod
    def render_certificate_html(
        cls,
        certificate: Certificate,
        base_url: Optional[str] = None,
    ) -> str:
        """Render the certificate HTML string using the modular template engine."""
        from certificates.template_service import TemplateRenderingService
        return TemplateRenderingService.render_template(certificate, base_url=base_url)

    @classmethod
    def generate_pdf_bytes(
        cls,
        certificate: Certificate,
        base_url: Optional[str] = None,
    ) -> bytes:
        """Render HTML and compile it into PDF binary bytes using WeasyPrint."""
        html_content = cls.render_certificate_html(certificate, base_url=base_url)
        wp_html = weasyprint.HTML(string=html_content, base_url=str(settings.BASE_DIR))
        return wp_html.write_pdf()

    @classmethod
    def generate_pdf_for_certificate(
        cls,
        certificate: Certificate,
        save: bool = True,
        base_url: Optional[str] = None,
    ) -> ContentFile:
        """Generate the PDF and attach it to ``certificate.certificate_pdf``."""
        pdf_bytes = cls.generate_pdf_bytes(certificate, base_url=base_url)
        filename = cls.get_safe_filename(certificate.certificate_id)
        content_file = ContentFile(pdf_bytes, name=filename)

        certificate.certificate_pdf.save(filename, content_file, save=save)
        return certificate.certificate_pdf

    @classmethod
    def validate_single_page(cls, certificate: Certificate) -> bool:
        """Verify that the rendered certificate document occupies exactly 1 page."""
        html_content = cls.render_certificate_html(certificate)
        wp_html = weasyprint.HTML(string=html_content, base_url=str(settings.BASE_DIR))
        doc = wp_html.render()
        return len(doc.pages) == 1
