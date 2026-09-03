import datetime
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from certificates.models import Certificate, CertificateTemplate, Enrollment, Program
from qrcode_verification.models import VerificationEvent
from users.models import AuditLog, AuthorizedSignatory, Student


class PublicCertificateVerificationTests(TestCase):
    """Comprehensive test suite for the public verification portal and token endpoint."""

    def setUp(self):
        self.student = Student.objects.create(
            full_name="Samantha Ray",
            email="samantha.ray@university.edu",
            phone="+1-555-987-6543",
            college="Institute of Technology",
            university="Metro University",
            degree="Master of Science",
            branch="Cybersecurity",
            graduation_year=2026,
            is_active=True,
        )
        self.program = Program.objects.create(
            name="Advanced Cloud Security Engineering",
            program_type="INTERNSHIP",
            description="Enterprise cloud security and distributed access architecture.",
            duration=60,
            mode="ONLINE",
            department="Cybersecurity & Infrastructure",
            mentor="Dr. Alan Turing",
            skills=["Kubernetes Security", "Zero Trust Architecture", "OAuth 2.0 / OIDC"],
            learning_outcomes=["Deploy secure cloud enclaves", "Perform automated compliance audits"],
            is_active=True,
        )
        self.template = CertificateTemplate.objects.create(
            name="Enterprise Platinum Template",
            organization="Global Cybersecurity Institute",
            description="Accredited template",
            html_template="templates/certificates/certificate_pdf.html",
            is_active=True,
        )
        self.signatory = AuthorizedSignatory.objects.create(
            name="Dr. Alan Turing",
            title="Chief Information Security Officer",
            organization="Global Cybersecurity Institute",
            email="alan.turing@gci.org",
        )
        self.enrollment = Enrollment.objects.create(
            student=self.student,
            program=self.program,
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 3, 2),
            duration=60,
            skills=self.program.skills,
            learning_outcomes=self.program.learning_outcomes,
            attendance_percentage=98.0,
            performance_rating=4.8,
            status="COMPLETED",
        )
        self.cert = Certificate.objects.create(
            student=self.student,
            program=self.program,
            enrollment=self.enrollment,
            certificate_type="INTERNSHIP",
            issue_date=datetime.date(2026, 3, 2),
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 3, 2),
            duration=60,
            status="ISSUED",
            template=self.template,
            authorized_signatory=self.signatory,
        )

    def test_verify_search_page_get(self):
        """GET /verify/ returns 200 OK lookup search page without authentication."""
        url = reverse("verify:verify_search")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Public Certificate Verification")
        self.assertContains(response, "Certificate Identifier or Token")

    def test_verify_search_by_certificate_id_success(self):
        """POST /verify/ with valid certificate ID redirects to /verify/<token>/ and logs event."""
        url = reverse("verify:verify_search")
        response = self.client.post(url, data={"q": self.cert.certificate_id})

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("verify:verify_token", kwargs={"token": self.cert.verification_token}))

        # Assert VerificationEvent logged with method SEARCH
        event = VerificationEvent.objects.filter(certificate=self.cert, verification_method="SEARCH").first()
        self.assertIsNotNone(event)

    def test_verify_search_invalid_query_not_found(self):
        """POST /verify/ with unknown identifier displays not found and records AuditLog."""
        url = reverse("verify:verify_search")
        response = self.client.post(url, data={"q": "UNKNOWN-ID-99999"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CERTIFICATE NOT FOUND")

        # Assert AuditLog recorded
        log = AuditLog.objects.filter(action="VERIFY", object_id="UNKNOWN-ID-99999").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.changes["result"], "NOT_FOUND")

    def test_verify_valid_issued_certificate_displays_all_public_fields(self):
        """GET /verify/<token>/ displays all required public fields with verified status."""
        url = reverse("verify:verify_token", kwargs={"token": self.cert.verification_token})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # 1. Verified Status Banner
        self.assertContains(response, "VERIFIED CERTIFICATE")
        # 2. Certificate ID
        self.assertContains(response, self.cert.certificate_id)
        # 3. Student Name
        self.assertContains(response, self.student.full_name)
        # 4. Program Name
        self.assertContains(response, self.program.name)
        # 5. Certificate Type
        self.assertContains(response, "Internship")
        # 6. Company
        self.assertContains(response, "Global Cybersecurity Institute")
        # 7. Duration
        self.assertContains(response, "60 Days")
        # 8. Start & End Dates
        self.assertContains(response, "January 01, 2026")
        self.assertContains(response, "March 02, 2026")
        # 9. Issue Date
        self.assertContains(response, "March 02, 2026")
        # 10. Skills
        self.assertContains(response, "Kubernetes Security")
        self.assertContains(response, "Zero Trust Architecture")
        # 11. Learning Outcomes
        self.assertContains(response, "Deploy secure cloud enclaves")
        # 12. Authorized Signatory
        self.assertContains(response, "Dr. Alan Turing")
        self.assertContains(response, "Chief Information Security Officer")
        # 13. Actions
        self.assertContains(response, "Download Official PDF")
        self.assertContains(response, "Copy Verification Link")
        self.assertContains(response, "Share")

        # Verify event logged
        event = VerificationEvent.objects.filter(certificate=self.cert, verification_method="QR_SCAN").first()
        self.assertIsNotNone(event)

    def test_verify_strictly_excludes_private_pii(self):
        """Verification page MUST never display student email, phone, college address, or internal evaluations."""
        url = reverse("verify:verify_token", kwargs={"token": self.cert.verification_token})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.student.email)
        self.assertNotContains(response, self.student.phone)
        self.assertNotContains(response, self.student.college)
        self.assertNotContains(response, self.student.university)

    def test_verify_revoked_certificate(self):
        """Revoked certificate displays CERTIFICATE REVOKED status."""
        self.cert.revoke("Unauthorized tampering attempt")
        url = reverse("verify:verify_token", kwargs={"token": self.cert.verification_token})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CERTIFICATE REVOKED")
        self.assertNotContains(response, "Download Official PDF")

    def test_verify_expired_certificate(self):
        """Expired certificate displays CERTIFICATE EXPIRED status."""
        self.cert.status = "EXPIRED"
        self.cert.save()

        url = reverse("verify:verify_token", kwargs={"token": self.cert.verification_token})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CERTIFICATE EXPIRED")

    def test_verify_non_existent_token(self):
        """Invalid verification token displays CERTIFICATE NOT FOUND."""
        url = reverse("verify:verify_token", kwargs={"token": "invalid_non_existent_token"})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CERTIFICATE NOT FOUND")

        # AuditLog logged for failed token lookup
        log = AuditLog.objects.filter(action="VERIFY", object_id="invalid_non_existent_token").first()
        self.assertIsNotNone(log)

    def test_public_pdf_download_success(self):
        """Public endpoint allows downloading PDF for valid issued certificates without login."""
        url = reverse("verify:verify_download", kwargs={"token": self.cert.verification_token})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_public_pdf_download_revoked_fails_404(self):
        """Public PDF download returns 404 for revoked certificates."""
        self.cert.revoke("Suspended accreditation")
        url = reverse("verify:verify_download", kwargs={"token": self.cert.verification_token})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_json_api_verification(self):
        """JSON Accept header returns structured verification details without PII."""
        url = reverse("verify:verify_token", kwargs={"token": self.cert.verification_token})
        response = self.client.get(url, HTTP_ACCEPT="application/json")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["valid"])
        self.assertEqual(data["status"], "VERIFIED")
        self.assertEqual(data["certificate_id"], self.cert.certificate_id)
        self.assertEqual(data["student_name"], self.student.full_name)
        self.assertNotIn("email", data)
        self.assertNotIn("phone", data)
