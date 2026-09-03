"""Targeted unit tests for CertificateEmailService and email delivery workflows."""

import datetime
from unittest import mock

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.base import ContentFile
from django.core.mail import EmailMultiAlternatives
from django.test import TestCase, override_settings
from django.urls import reverse

from certificates.models import Certificate, CertificateTemplate, Enrollment, Program
from certificates.services import (
    CertificateEmailService,
    CertificateIssuanceService,
    CertificatePDFService,
)
from users.models import AuditLog, AuthorizedSignatory, CompanySettings, Student


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CertificateEmailServiceTests(TestCase):
    """Test suite for CertificateEmailService delivery and resilience."""

    @classmethod
    def setUpTestData(cls):
        # Create superuser
        cls.admin_user = User.objects.create_superuser(
            username="admin_email",
            email="admin@test.local",
            password="adminpassword123",
        )

        # Company Settings
        cls.company = CompanySettings.get_instance()
        cls.company.company_name = "Nova Certification Authority"
        cls.company.email = "support@novacert.org"
        cls.company.website = "https://novacert.org"
        cls.company.address = "100 Tech Blvd, Silicon Valley"
        cls.company.save()

        # Student
        cls.student = Student.objects.create(
            full_name="Alexander Hamilton",
            email="alexander.hamilton@treasury.gov",
            phone="+1-555-177-6001",
            college="Columbia University",
            university="New York State",
            degree="Bachelor of Arts",
            branch="Economics",
            graduation_year=2026,
            is_active=True,
        )

        # Program
        cls.program = Program.objects.create(
            name="Advanced Fiscal Architecture & Monetary Policy",
            program_type="INTERNSHIP",
            duration=90,
            mode="ONLINE",
            department="Economics",
            is_active=True,
        )

        # Template & Signatory
        cls.template = CertificateTemplate.objects.create(
            name="Modern Classic Gold",
            design_style="MODERN",
            organization="Nova Certification Authority",
            is_active=True,
        )

        cls.signatory = AuthorizedSignatory.objects.create(
            name="George Washington",
            title="General Director",
            organization="Nova Certification Authority",
            email="george@novacert.org",
            is_active=True,
        )

    def setUp(self):
        # Fresh issued certificate for tests
        self.certificate = CertificateIssuanceService.issue_certificate(
            student=self.student,
            program=self.program,
            certificate_type="INTERNSHIP",
            template=self.template,
            authorized_signatory=self.signatory,
            issue_date=datetime.date(2026, 4, 1),
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 3, 31),
            duration=90,
            user=self.admin_user,
        )
        # Reset email state and audit log for individual test execution
        self.certificate.email_sent = False
        self.certificate.email_sent_at = None
        self.certificate.save(update_fields=["email_sent", "email_sent_at"])
        AuditLog.objects.filter(action="EMAIL").delete()
        mail.outbox.clear()

    def test_send_certificate_email_contains_required_fields(self):
        """Email delivery contains student name, program, certificate ID, verification link, and download link."""
        success, error = CertificateEmailService.send_certificate_email(
            self.certificate,
            base_url="https://verify.novacert.org",
            user=self.admin_user,
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertEqual(len(mail.outbox), 1)

        sent_msg = mail.outbox[0]
        self.assertIn(self.student.email, sent_msg.to)
        self.assertIn(self.certificate.certificate_id, sent_msg.subject)

        # Plaintext body checks
        self.assertIn(self.student.full_name, sent_msg.body)
        self.assertIn(self.program.name, sent_msg.body)
        self.assertIn(self.certificate.certificate_id, sent_msg.body)

        verification_url = f"https://verify.novacert.org/verify/{self.certificate.verification_token}/"
        download_url = f"https://verify.novacert.org/verify/{self.certificate.verification_token}/download/"

        self.assertIn(verification_url, sent_msg.body)
        self.assertIn(download_url, sent_msg.body)

        # HTML body checks (alternatives)
        self.assertEqual(len(sent_msg.alternatives), 1)
        html_content, mimetype = sent_msg.alternatives[0]
        self.assertEqual(mimetype, "text/html")
        self.assertIn(self.student.full_name, html_content)
        self.assertIn("Advanced Fiscal Architecture", html_content)
        self.assertIn(self.certificate.certificate_id, html_content)
        self.assertIn(verification_url, html_content)
        self.assertIn(download_url, html_content)

        # PDF attachment check
        self.assertEqual(len(sent_msg.attachments), 1)
        filename, content, content_type = sent_msg.attachments[0]
        self.assertEqual(filename, f"{self.certificate.certificate_id}.pdf")
        self.assertEqual(content_type, "application/pdf")
        self.assertTrue(len(content) > 0)

    def test_send_email_updates_certificate_model_and_audit_log(self):
        """Successful email delivery sets email_sent=True and records AuditLog."""
        self.assertFalse(self.certificate.email_sent)
        self.assertIsNone(self.certificate.email_sent_at)

        success, _ = CertificateEmailService.send_certificate_email(
            self.certificate,
            user=self.admin_user,
            ip_address="192.168.1.50",
        )

        self.assertTrue(success)
        self.certificate.refresh_from_db()
        self.assertTrue(self.certificate.email_sent)
        self.assertIsNotNone(self.certificate.email_sent_at)

        # AuditLog verification
        audit = AuditLog.objects.filter(
            action="EMAIL",
            object_id=self.certificate.certificate_id,
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.user_email, self.admin_user.email)
        self.assertEqual(audit.changes["status"], "SENT")
        self.assertEqual(audit.changes["recipient_email"], self.student.email)
        self.assertEqual(audit.ip_address, "192.168.1.50")

    def test_email_failure_does_not_affect_certificate_validity(self):
        """When SMTP / mail backend throws an error, certificate remains ISSUED and error is logged."""
        original_status = self.certificate.status
        self.assertEqual(original_status, "ISSUED")

        # Mock EmailMultiAlternatives.send to simulate SMTP failure
        with mock.patch.object(EmailMultiAlternatives, "send", side_effect=Exception("SMTP Connection Timeout")):
            success, error = CertificateEmailService.send_certificate_email(
                self.certificate,
                user=self.admin_user,
            )

        self.assertFalse(success)
        self.assertIn("SMTP Connection Timeout", error)

        # Invariant: Certificate remains 100% ISSUED and intact
        self.certificate.refresh_from_db()
        self.assertEqual(self.certificate.status, "ISSUED")
        self.assertFalse(self.certificate.email_sent)

        # AuditLog records failure
        audit = AuditLog.objects.filter(
            action="EMAIL",
            object_id=self.certificate.certificate_id,
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.changes["status"], "FAILED")
        self.assertIn("SMTP Connection Timeout", audit.changes["error"])

    def test_resend_email_dashboard_view(self):
        """Admin can resend certificate email via POST /dashboard/certificate/<pk>/resend-email/."""
        self.client.login(username="admin_email", password="adminpassword123")
        url = reverse("dashboard:certificate_resend_email", kwargs={"pk": self.certificate.pk})

        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "successfully sent")

        self.certificate.refresh_from_db()
        self.assertTrue(self.certificate.email_sent)
        self.assertEqual(len(mail.outbox), 1)
