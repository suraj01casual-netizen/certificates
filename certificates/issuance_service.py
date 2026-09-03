"""
Certificate Issuance Workflow Service.

Coordinates:
  1. Certificate creation & data assembly
  2. Live preview rendering
  3. Confirmation
  4. Generation of unique Certificate ID
  5. Generation of unique Verification Token
  6. Generation of QR Code (pointing strictly to /verify/<token>/)
  7. Generation of WeasyPrint A4 Landscape PDF
  8. Atomic status update to ISSUED
  9. AuditLog recording

Ensures:
  - Atomic database transactions: No partially issued certificate on failure.
  - Certificate must not receive ISSUED status before successful generation.
  - Certificate ID and verification token remain immutable after issuance.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from django.db import transaction
from django.utils import timezone

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser
    from certificates.models import (
        AuthorizedSignatory,
        Certificate,
        CertificateTemplate,
        Enrollment,
        Program,
    )
    from users.models import Student


class CertificateIssuanceService:
    """Coordinates the end-to-end certificate issuance workflow."""

    @classmethod
    @transaction.atomic
    def issue_certificate(
        cls,
        student: Student,
        program: Program,
        certificate_type: str,
        template: CertificateTemplate,
        authorized_signatory: Optional[AuthorizedSignatory] = None,
        issue_date: Optional[datetime.date] = None,
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
        duration: Optional[int] = None,
        enrollment: Optional[Enrollment] = None,
        user: Optional[AbstractBaseUser] = None,
        ip_address: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Certificate:
        """Create and issue a certificate atomically.

        Guarantees:
        - If QR or PDF generation fails, the transaction rolls back cleanly.
        - The certificate NEVER receives ISSUED status before successful generation.
        - Certificate ID and verification token remain unchanged.
        - AuditLog record is created for the issuance.
        """
        from certificates.models import Certificate
        from certificates.services import (
            CertificatePDFService,
            CertificateService,
            QRCodeService,
        )
        from users.models import AuditLog

        if not issue_date:
            issue_date = timezone.now().date()
        if not start_date and enrollment:
            start_date = enrollment.start_date
        if not end_date and enrollment:
            end_date = enrollment.end_date
        if not duration and enrollment:
            duration = enrollment.duration
        elif not duration and start_date and end_date:
            duration = (end_date - start_date).days
        elif not duration:
            duration = program.duration

        # 1. Generate identity tokens
        cert_id = CertificateService.generate_certificate_id(certificate_type)
        token = CertificateService.generate_verification_token_unique()

        # 2. Create Certificate in DRAFT status initially
        certificate = Certificate.objects.create(
            certificate_id=cert_id,
            verification_token=token,
            student=student,
            program=program,
            enrollment=enrollment,
            certificate_type=certificate_type,
            template=template,
            authorized_signatory=authorized_signatory,
            issue_date=issue_date,
            start_date=start_date or issue_date,
            end_date=end_date,
            duration=duration,
            status="DRAFT",
        )

        # 3. Generate QR code
        QRCodeService.generate_qr_for_certificate(
            certificate, base_url=base_url, save=True
        )

        # 4. Generate WeasyPrint PDF
        CertificatePDFService.generate_pdf_for_certificate(
            certificate, save=True, base_url=base_url
        )

        # 5. Set status to ISSUED ONLY after successful generation of QR & PDF
        certificate.status = "ISSUED"
        certificate.save()

        # Invariant checks: Identity tokens must remain unchanged
        assert certificate.certificate_id == cert_id
        assert certificate.verification_token == token

        # 6. Record AuditLog
        user_email = (
            getattr(user, "email", None)
            if user and getattr(user, "is_authenticated", False)
            else None
        )
        AuditLog.objects.create(
            action="ISSUE",
            object_type="Certificate",
            object_id=certificate.certificate_id,
            user_email=user_email,
            changes={
                "status": "ISSUED",
                "certificate_id": certificate.certificate_id,
                "student_id": student.student_id,
                "student_name": student.full_name,
                "program_id": program.program_id,
                "program_name": program.name,
                "certificate_type": certificate.certificate_type,
                "issue_date": str(certificate.issue_date),
                "pdf_file": (
                    certificate.certificate_pdf.name
                    if certificate.certificate_pdf
                    else None
                ),
                "qr_code_file": (
                    certificate.qr_code.name if certificate.qr_code else None
                ),
            },
            ip_address=ip_address,
        )

        # 7. Deliver certificate notification via email (non-blocking)
        try:
            from certificates.services import CertificateEmailService
            CertificateEmailService.send_certificate_email(
                certificate,
                base_url=base_url,
                user=user,
                ip_address=ip_address,
                fail_silently=True,
            )
        except Exception:
            pass

        return certificate

    @classmethod
    @transaction.atomic
    def issue_existing_certificate(
        cls,
        certificate: Certificate,
        user: Optional[AbstractBaseUser] = None,
        ip_address: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> Certificate:
        """Issue an existing certificate draft, generating QR and PDF atomically."""
        from certificates.services import (
            CertificatePDFService,
            CertificateService,
            QRCodeService,
        )
        from users.models import AuditLog

        # Ensure ID and token exist
        if not certificate.certificate_id:
            certificate.certificate_id = CertificateService.generate_certificate_id(
                certificate.certificate_type, exclude_pk=certificate.pk
            )
        if not certificate.verification_token:
            certificate.verification_token = (
                CertificateService.generate_verification_token_unique(
                    exclude_pk=certificate.pk
                )
            )

        cert_id = certificate.certificate_id
        token = certificate.verification_token

        # Generate QR code
        QRCodeService.generate_qr_for_certificate(
            certificate, base_url=base_url, save=True
        )

        # Generate WeasyPrint PDF
        CertificatePDFService.generate_pdf_for_certificate(
            certificate, save=True, base_url=base_url
        )

        # Set status to ISSUED
        certificate.status = "ISSUED"
        if not certificate.issue_date:
            certificate.issue_date = timezone.now().date()
        certificate.save()

        # Invariant checks
        assert certificate.certificate_id == cert_id
        assert certificate.verification_token == token

        # Record AuditLog
        user_email = (
            getattr(user, "email", None)
            if user and getattr(user, "is_authenticated", False)
            else None
        )
        AuditLog.objects.create(
            action="ISSUE",
            object_type="Certificate",
            object_id=certificate.certificate_id,
            user_email=user_email,
            changes={
                "status": "ISSUED",
                "certificate_id": certificate.certificate_id,
                "student_name": certificate.student.full_name,
                "program_name": certificate.program.name,
                "issue_date": str(certificate.issue_date),
                "pdf_file": (
                    certificate.certificate_pdf.name
                    if certificate.certificate_pdf
                    else None
                ),
            },
            ip_address=ip_address,
        )

        # Deliver certificate notification via email (non-blocking)
        try:
            from certificates.services import CertificateEmailService
            CertificateEmailService.send_certificate_email(
                certificate,
                base_url=base_url,
                user=user,
                ip_address=ip_address,
                fail_silently=True,
            )
        except Exception:
            pass

        return certificate

    @classmethod
    def render_preview(
        cls,
        student: Student,
        program: Program,
        certificate_type: str,
        template: CertificateTemplate,
        authorized_signatory: Optional[AuthorizedSignatory] = None,
        issue_date: Optional[datetime.date] = None,
        start_date: Optional[datetime.date] = None,
        end_date: Optional[datetime.date] = None,
        duration: Optional[int] = None,
        enrollment: Optional[Enrollment] = None,
        base_url: Optional[str] = None,
    ) -> tuple[str, dict]:
        """Render a live HTML preview of the certificate before confirmation."""
        from certificates.models import Certificate
        from certificates.services import CertificatePDFService, CertificateService, QRCodeService

        if not issue_date:
            issue_date = timezone.now().date()
        if not start_date and enrollment:
            start_date = enrollment.start_date
        if not end_date and enrollment:
            end_date = enrollment.end_date
        if not duration and enrollment:
            duration = enrollment.duration
        elif not duration and start_date and end_date:
            duration = (end_date - start_date).days
        elif not duration:
            duration = program.duration

        # Ephemeral Certificate object for preview
        dummy_cert = Certificate(
            certificate_id="PREVIEW-000000",
            verification_token="PREVIEW_VERIFICATION_TOKEN",
            student=student,
            program=program,
            enrollment=enrollment,
            certificate_type=certificate_type,
            template=template,
            authorized_signatory=authorized_signatory,
            issue_date=issue_date,
            start_date=start_date or issue_date,
            end_date=end_date,
            duration=duration,
            status="DRAFT",
        )

        # Generate preview QR code data URI
        preview_url = QRCodeService.get_verification_url("PREVIEW_TOKEN", base_url=base_url)
        qr_img = QRCodeService.generate_qr_image(preview_url)
        import io, base64
        buf = io.BytesIO()
        qr_img.save(buf, format="PNG")
        qr_data_uri = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"

        from certificates.template_service import TemplateRenderingService
        html_content = TemplateRenderingService.render_template(
            dummy_cert,
            template=template,
            base_url=base_url,
            extra_context={
                "qr_data_uri": qr_data_uri,
                "is_preview": True,
            },
        )
        context = CertificatePDFService.build_context(dummy_cert, base_url=base_url)
        context["qr_data_uri"] = qr_data_uri
        context["is_preview"] = True
        return html_content, context
