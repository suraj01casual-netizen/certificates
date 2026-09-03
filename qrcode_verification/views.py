"""
Public Certificate Verification Views.

Provides public endpoints:
  - /verify/ : Search / lookup portal by Certificate ID or Token
  - /verify/<verification_token>/ : Public verification credential page
  - /verify/<verification_token>/download/ : Public PDF download

Enforces strict privacy:
  - Excludes student email, phone, address, internal notes, evaluations.
  - Logs VerificationEvents for verified requests and AuditLogs for failed lookups.
"""

from __future__ import annotations

from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import View

from certificates.models import Certificate
from certificates.services import CertificatePDFService
from qrcode_verification.models import VerificationEvent
from users.audit_service import AuditLogService
from users.models import AuditLog, CompanySettings


class CertificateVerifySearchView(View):
    """Public lookup search page where anyone can search by token or Certificate ID."""

    def get(self, request):
        query = request.GET.get("q", "").strip()
        if query:
            return self._handle_search(request, query)
        return render(request, "verify/verify_search.html")

    def post(self, request):
        query = request.POST.get("q", "").strip()
        if not query:
            return render(
                request,
                "verify/verify_search.html",
                {"error": "Please enter a Certificate ID or Verification Token."},
            )
        return self._handle_search(request, query)

    def _handle_search(self, request, query: str):
        # 1. Search by verification_token or certificate_id
        cert = Certificate.objects.filter(
            Q(verification_token=query) | Q(certificate_id__iexact=query)
        ).first()

        ip_address = request.META.get("REMOTE_ADDR")

        if cert:
            # Record verification event
            user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]
            VerificationEvent.objects.create(
                certificate=cert,
                ip_address=ip_address,
                user_agent=user_agent,
                verification_method="SEARCH",
            )
            return redirect("verify:verify_token", token=cert.verification_token)

        # Log failed attempt in AuditLog
        AuditLogService.log_certificate_verified(
            token_or_id=query,
            result="NOT_FOUND",
            method="SEARCH_PORTAL",
            request=request,
        )

        return render(
            request,
            "verify/verify_detail.html",
            {
                "query": query,
                "is_found": False,
                "status_type": "NOT_FOUND",
                "status_title": "Certificate Not Found",
            },
        )


class CertificateVerifyView(View):
    """Public endpoint to verify a certificate by its unique verification token."""

    def get(self, request, token: str):
        token = token.strip()
        ip_address = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]

        cert = Certificate.objects.filter(verification_token=token).select_related(
            "student", "program", "template", "authorized_signatory", "enrollment"
        ).first()

        if not cert:
            # Record failed verification in AuditLog
            AuditLogService.log_certificate_verified(
                token_or_id=token,
                result="NOT_FOUND",
                method="TOKEN_LOOKUP",
                request=request,
            )

            if request.headers.get("Accept") == "application/json":
                return JsonResponse({"valid": False, "status": "NOT_FOUND", "error": "Certificate not found"}, status=404)

            return render(
                request,
                "verify/verify_detail.html",
                {
                    "token": token,
                    "is_found": False,
                    "status_type": "NOT_FOUND",
                    "status_title": "Certificate Not Found",
                },
            )

        # Record VerificationEvent
        VerificationEvent.objects.create(
            certificate=cert,
            ip_address=ip_address,
            user_agent=user_agent,
            verification_method="QR_SCAN",
        )

        # Determine Verification Status Type
        now = timezone.now().date()
        if cert.status == "REVOKED":
            status_type = "REVOKED"
            status_title = "Certificate Revoked"
            is_valid = False
        elif cert.status == "EXPIRED" or (getattr(cert, "expiry_date", None) and cert.expiry_date < now):
            status_type = "EXPIRED"
            status_title = "Certificate Expired"
            is_valid = False
        elif cert.status == "ISSUED":
            status_type = "VERIFIED"
            status_title = "VERIFIED CERTIFICATE"
            is_valid = True
        else:
            status_type = "DRAFT"
            status_title = f"Certificate {cert.get_status_display()}"
            is_valid = False

        # Record verified event in AuditLog
        AuditLogService.log_certificate_verified(
            certificate=cert,
            result=status_type,
            method="TOKEN_LOOKUP",
            request=request,
        )

        # Safe Public Data Extraction (Zero PII / Private details)
        company_name = (
            (cert.template.organization if cert.template else None)
            or (cert.authorized_signatory.organization if cert.authorized_signatory else None)
            or CompanySettings.get_instance().organization_name
        )

        # Skills & Learning outcomes (from enrollment or program)
        skills = []
        if cert.enrollment and cert.enrollment.skills:
            skills = cert.enrollment.skills
        elif cert.program and cert.program.skills:
            skills = cert.program.skills

        learning_outcomes = []
        if cert.enrollment and cert.enrollment.learning_outcomes:
            learning_outcomes = cert.enrollment.learning_outcomes
        elif cert.program and cert.program.learning_outcomes:
            learning_outcomes = cert.program.learning_outcomes

        context = {
            "token": token,
            "certificate": cert,
            "is_found": True,
            "is_valid": is_valid,
            "status_type": status_type,
            "status_title": status_title,
            "company_name": company_name,
            "company_settings": CompanySettings.get_instance(),
            "skills": skills,
            "learning_outcomes": learning_outcomes,
            "signatory": cert.authorized_signatory,
            "verification_url": request.build_absolute_uri(),
        }

        # JSON API response support
        if request.headers.get("Accept") == "application/json":
            return JsonResponse({
                "valid": is_valid,
                "status": status_type,
                "certificate_id": cert.certificate_id,
                "student_name": cert.student.full_name,
                "program_name": cert.program.name,
                "certificate_type": cert.get_certificate_type_display(),
                "company": company_name,
                "duration": cert.duration,
                "start_date": str(cert.start_date) if cert.start_date else None,
                "end_date": str(cert.end_date) if cert.end_date else None,
                "issue_date": str(cert.issue_date),
                "skills": skills,
                "learning_outcomes": learning_outcomes,
                "authorized_signatory": cert.authorized_signatory.name if cert.authorized_signatory else None,
            })

        return render(request, "verify/verify_detail.html", context)


class PublicCertificateDownloadView(View):
    """Public endpoint allowing holders/verifiers to download the verified PDF."""

    def get(self, request, token: str):
        cert = get_object_or_404(Certificate, verification_token=token)

        if cert.status != "ISSUED":
            raise Http404("Certificate is not issued or has been revoked.")

        # Verify physical file existence on disk (self-healing for ephemeral containers)
        pdf_ready = False
        if cert.certificate_pdf:
            try:
                pdf_ready = cert.certificate_pdf.storage.exists(cert.certificate_pdf.name)
            except Exception:
                pdf_ready = False

        if not pdf_ready:
            CertificatePDFService.generate_pdf_for_certificate(cert, save=True)
            cert.refresh_from_db()

        cert.certificate_pdf.open("rb")
        filename = CertificatePDFService.get_safe_filename(cert.certificate_id)

        # Log download event
        AuditLogService.log_certificate_downloaded(
            certificate=cert,
            request=request,
            source="PUBLIC_VERIFY_PAGE",
        )

        response = FileResponse(cert.certificate_pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response
