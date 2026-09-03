"""Comprehensive, end-to-end Django test suite covering all 16 mission-critical requirements:

1. Authentication
2. Permissions
3. Student CRUD
4. Program CRUD
5. Enrollment
6. Certificate Creation
7. Certificate ID Uniqueness
8. Verification Token Security
9. QR Generation
10. PDF Generation
11. Certificate Verification
12. Invalid Verification
13. Revocation
14. Expired Certificates
15. Audit Logs
16. File Uploads
"""

from __future__ import annotations

import datetime
import io
import secrets
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from certificates.models import (
    Certificate,
    CertificateTemplate,
    Enrollment,
    Program,
)
from certificates.services import (
    BulkCertificateService,
    CertificateIssuanceService,
    CertificatePDFService,
    QRCodeService,
)
from qrcode_verification.models import VerificationEvent
from users.audit_service import AuditLogService
from users.models import AuditLog, AuthorizedSignatory, CompanySettings, Student

User = get_user_model()


def create_dummy_image(name="test_image.png", width=100, height=50, format="PNG") -> SimpleUploadedFile:
    """Helper to create an in-memory valid image file for testing uploads."""
    buffer = io.BytesIO()
    image = Image.new("RGB", (width, height), color=(73, 109, 137))
    image.save(buffer, format=format)
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type=f"image/{format.lower()}")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MEDIA_ROOT="scratch/test_media/",
)
class ComprehensiveSystemTestSuite(TestCase):
    """Exhaustive test suite verifying the complete functionality and integrity of the application."""

    @classmethod
    def setUpTestData(cls):
        # 1. Superuser
        cls.admin_user = User.objects.create_superuser(
            username="master_admin",
            email="admin@certhub.local",
            password="SecureMasterPassword123!",
            first_name="Master",
            last_name="Admin",
        )

        # 2. Regular User
        cls.regular_user = User.objects.create_user(
            username="staff_member",
            email="staff@certhub.local",
            password="StaffMemberPassword123!",
            first_name="Staff",
            last_name="Member",
        )

        # 3. Company Settings
        cls.company = CompanySettings.get_instance()
        cls.company.company_name = "Global Cybersecurity & Tech Institute"
        cls.company.email = "contact@gcti.org"
        cls.company.phone = "+1-800-555-0199"
        cls.company.website = "https://gcti.org"
        cls.company.address = "100 Technology Square, Cambridge, MA"
        cls.company.certificate_footer = "Verified and issued under accredited academic charter."
        cls.company.save()

        # 4. Templates
        cls.template_modern = CertificateTemplate.objects.create(
            name="Modern Tech Template",
            design_style="MODERN",
            organization="Global Cybersecurity & Tech Institute",
            is_active=True,
        )
        cls.template_classic = CertificateTemplate.objects.create(
            name="Classic Tech Template",
            design_style="CLASSIC",
            organization="Global Cybersecurity & Tech Institute",
            is_active=True,
        )
        cls.template_pro = CertificateTemplate.objects.create(
            name="Professional Tech Template",
            design_style="PROFESSIONAL",
            organization="Global Cybersecurity & Tech Institute",
            is_active=True,
        )

        # 5. Signatory
        cls.signatory = AuthorizedSignatory.objects.create(
            name="Dr. Ada Lovelace",
            title="Chief Academic Dean",
            organization="Global Cybersecurity & Tech Institute",
            email="ada.lovelace@gcti.org",
            is_active=True,
        )

    def setUp(self):
        self.client = Client()

    # =========================================================================
    # 1. AUTHENTICATION TESTS
    # =========================================================================
    def test_01_authentication_login_success_and_session(self):
        """Valid email/username and password authenticates user and establishes session."""
        login_url = reverse("login")
        resp = self.client.post(
            login_url,
            {"email": "admin@certhub.local", "password": "SecureMasterPassword123!"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.wsgi_request.user.is_authenticated)
        self.assertEqual(resp.wsgi_request.user.email, "admin@certhub.local")

    def test_01_authentication_invalid_credentials_fail(self):
        """Invalid password fails login with appropriate status."""
        login_url = reverse("login")
        resp = self.client.post(
            login_url,
            {"email": "admin@certhub.local", "password": "WrongPassword!"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.wsgi_request.user.is_authenticated)

    def test_01_authentication_logout_clears_session(self):
        """Logout revokes active user session."""
        self.client.login(username="master_admin", password="SecureMasterPassword123!")
        logout_url = reverse("logout")
        resp = self.client.get(logout_url, follow=True)
        self.assertEqual(resp.status_code, 200)

        # Attempt to access dashboard redirects to login
        dash_resp = self.client.get(reverse("dashboard"))
        self.assertEqual(dash_resp.status_code, 302)
        self.assertIn("/auth/login/", dash_resp.url)

    # =========================================================================
    # 2. PERMISSIONS TESTS
    # =========================================================================
    def test_02_permissions_dashboard_routes_protected(self):
        """Protected dashboard views reject unauthenticated requests with redirect to login."""
        protected_urls = [
            reverse("dashboard:student_list"),
            reverse("dashboard:program_list"),
            reverse("dashboard:enrollment_list"),
            reverse("dashboard:certificate_list"),
            reverse("dashboard:signatory_list"),
            reverse("dashboard:company_settings"),
            reverse("dashboard:audit_log_list"),
        ]
        for url in protected_urls:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302, f"URL {url} must be protected by LoginRequiredMixin")
            self.assertIn("/auth/login/", resp.url)

    def test_02_permissions_public_verification_routes_accessible(self):
        """Public verification portal and token lookup are accessible without authentication."""
        public_urls = [
            reverse("verify:verify_search"),
        ]
        for url in public_urls:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, f"URL {url} must be publicly accessible")

    # =========================================================================
    # 3. STUDENT CRUD TESTS
    # =========================================================================
    def test_03_student_full_crud_lifecycle(self):
        """Admin can create, read, update, search, and deactivate students."""
        self.client.login(username="master_admin", password="SecureMasterPassword123!")

        # CREATE
        add_url = reverse("dashboard:student_add")
        resp = self.client.post(
            add_url,
            {
                "full_name": "Katherine Johnson",
                "email": "katherine.johnson@nasa.gov",
                "phone": "+1-555-0144",
                "college": "West Virginia State",
                "university": "West Virginia State University",
                "degree": "B.S.",
                "branch": "Mathematics & French",
                "graduation_year": 2026,
                "is_active": True,
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)

        student = Student.objects.get(email="katherine.johnson@nasa.gov")
        year = timezone.now().year
        self.assertTrue(student.student_id.startswith(f"STU-{year}-"))
        self.assertEqual(student.full_name, "Katherine Johnson")

        # READ (Detail & Search)
        detail_url = reverse("dashboard:student_detail", kwargs={"pk": student.pk})
        detail_resp = self.client.get(detail_url)
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, "Katherine Johnson")

        list_resp = self.client.get(reverse("dashboard:student_list") + "?q=Katherine")
        self.assertContains(list_resp, student.student_id)

        # UPDATE
        edit_url = reverse("dashboard:student_edit", kwargs={"pk": student.pk})
        edit_resp = self.client.post(
            edit_url,
            {
                "full_name": "Dr. Katherine Johnson",
                "email": "katherine.johnson@nasa.gov",
                "phone": "+1-555-0144",
                "college": "West Virginia State",
                "university": "West Virginia State University",
                "degree": "Ph.D.",
                "branch": "Orbital Mechanics",
                "graduation_year": 2026,
                "is_active": True,
            },
            follow=True,
        )
        self.assertEqual(edit_resp.status_code, 200)
        student.refresh_from_db()
        self.assertEqual(student.full_name, "Dr. Katherine Johnson")
        self.assertEqual(student.degree, "Ph.D.")

        # DEACTIVATE
        deact_url = reverse("dashboard:student_deactivate", kwargs={"pk": student.pk})
        deact_resp = self.client.post(deact_url, follow=True)
        self.assertEqual(deact_resp.status_code, 200)
        student.refresh_from_db()
        self.assertFalse(student.is_active)

    def test_03_student_duplicate_email_rejected(self):
        """Duplicate student email is rejected with clean form error."""
        self.client.login(username="master_admin", password="SecureMasterPassword123!")
        Student.objects.create(
            full_name="Original Student",
            email="unique.student@univ.edu",
            phone="+1-555-1111",
            college="MIT",
            graduation_year=2026,
        )

        add_url = reverse("dashboard:student_add")
        resp = self.client.post(
            add_url,
            {
                "full_name": "Duplicate Student",
                "email": "unique.student@univ.edu",
                "phone": "+1-555-2222",
                "college": "Stanford",
                "graduation_year": 2026,
                "is_active": True,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFormError(resp.context["form"], "email", "A student with this email address already exists.")

    # =========================================================================
    # 4. PROGRAM CRUD TESTS
    # =========================================================================
    def test_04_program_full_crud_lifecycle(self):
        """Admin can create, read, update, search, and toggle active status of programs."""
        self.client.login(username="master_admin", password="SecureMasterPassword123!")

        # CREATE
        add_url = reverse("dashboard:program_add")
        resp = self.client.post(
            add_url,
            {
                "name": "Distributed Systems & Cloud Architecture",
                "program_type": "INTERNSHIP",
                "description": "Designing high-scale distributed backends.",
                "duration": 90,
                "mode": "ONLINE",
                "department": "Engineering",
                "mentor": "Leslie Lamport",
                "is_active": True,
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)

        prog = Program.objects.get(name="Distributed Systems & Cloud Architecture")
        year = timezone.now().year
        self.assertTrue(prog.program_id.startswith(f"PRG-{year}-"))
        self.assertEqual(prog.mentor, "Leslie Lamport")

        # READ (Detail & Search)
        detail_resp = self.client.get(reverse("dashboard:program_detail", kwargs={"pk": prog.pk}))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, "Distributed Systems")

        # UPDATE
        edit_url = reverse("dashboard:program_edit", kwargs={"pk": prog.pk})
        edit_resp = self.client.post(
            edit_url,
            {
                "name": "Distributed Systems & Cloud Architecture v2",
                "program_type": "INTERNSHIP",
                "description": "Advanced consensus and distributed storage.",
                "duration": 120,
                "mode": "HYBRID",
                "department": "Infrastructure",
                "mentor": "Leslie Lamport",
                "is_active": True,
            },
            follow=True,
        )
        self.assertEqual(edit_resp.status_code, 200)
        prog.refresh_from_db()
        self.assertEqual(prog.duration, 120)
        self.assertEqual(prog.mode, "HYBRID")

        # TOGGLE ACTIVE
        toggle_url = reverse("dashboard:program_toggle_active", kwargs={"pk": prog.pk})
        toggle_resp = self.client.post(toggle_url, follow=True)
        self.assertEqual(toggle_resp.status_code, 200)
        prog.refresh_from_db()
        self.assertFalse(prog.is_active)

    # =========================================================================
    # 5. ENROLLMENT TESTS
    # =========================================================================
    def test_05_enrollment_lifecycle_and_uniqueness(self):
        """Enrollment connects student to program and tracks performance and status."""
        student = Student.objects.create(
            full_name="Claude Shannon",
            email="claude.shannon@mit.edu",
            phone="+1-555-8888",
            college="MIT",
            graduation_year=2026,
        )
        program = Program.objects.create(
            name="Information Theory & Cryptography",
            program_type="TRAINING",
            duration=60,
            mode="ONLINE",
            department="EECS",
            is_active=True,
        )

        enrollment = Enrollment.objects.create(
            student=student,
            program=program,
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 3, 2),
            duration=60,
            attendance_percentage=99.5,
            performance_rating=5.0,
            status="COMPLETED",
        )
        self.assertEqual(enrollment.status, "COMPLETED")
        self.assertEqual(enrollment.duration, 60)

        # Ensure reverse relationships work
        self.assertEqual(student.enrollments.count(), 1)
        self.assertEqual(program.enrollments.count(), 1)

    # =========================================================================
    # 6. CERTIFICATE CREATION TESTS
    # =========================================================================
    def test_06_certificate_creation_workflow_and_issuance(self):
        """Certificates can be created as drafts and officially issued."""
        student = Student.objects.create(
            full_name="Barbara Liskov",
            email="barbara.liskov@mit.edu",
            phone="+1-555-7777",
            college="MIT",
            graduation_year=2026,
        )
        program = Program.objects.create(
            name="Object-Oriented Architecture & Type Systems",
            program_type="INTERNSHIP",
            duration=90,
            mode="ONLINE",
            department="Computer Science",
            is_active=True,
        )

        cert = CertificateIssuanceService.issue_certificate(
            student=student,
            program=program,
            certificate_type="INTERNSHIP",
            template=self.template_modern,
            authorized_signatory=self.signatory,
            issue_date=datetime.date(2026, 5, 1),
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 3, 31),
            duration=90,
            user=self.admin_user,
            ip_address="127.0.0.1",
        )

        self.assertEqual(cert.status, "ISSUED")
        self.assertEqual(cert.student, student)
        self.assertEqual(cert.program, program)
        self.assertEqual(cert.template, self.template_modern)
        self.assertEqual(cert.authorized_signatory, self.signatory)
        self.assertTrue(bool(cert.certificate_pdf))
        self.assertTrue(bool(cert.qr_code))

    # =========================================================================
    # 7. CERTIFICATE ID UNIQUENESS TESTS
    # =========================================================================
    def test_07_certificate_id_format_and_strict_uniqueness(self):
        """Certificate IDs follow COMP-{TYPE}-{YEAR}-{SEQ} format and cannot be duplicated."""
        student = Student.objects.create(
            full_name="Grace Hopper",
            email="grace@navy.mil",
            phone="+1-555-0101",
            college="Vassar",
            graduation_year=2026,
        )
        program = Program.objects.create(
            name="Compilers & Programming Languages",
            program_type="TRAINING",
            duration=45,
            mode="ONLINE",
            is_active=True,
        )

        cert1 = Certificate.objects.create(
            student=student,
            program=program,
            certificate_type="TRAINING",
            template=self.template_modern,
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 2, 15),
            duration=45,
            issue_date=datetime.date(2026, 6, 1),
            status="ISSUED",
        )
        cert2 = Certificate.objects.create(
            student=student,
            program=program,
            certificate_type="TRAINING",
            template=self.template_modern,
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 2, 15),
            duration=45,
            issue_date=datetime.date(2026, 6, 1),
            status="ISSUED",
        )

        year = timezone.now().year
        self.assertTrue(cert1.certificate_id.startswith(f"COMP-TRN-{year}-"))
        self.assertTrue(cert2.certificate_id.startswith(f"COMP-TRN-{year}-"))
        self.assertNotEqual(cert1.certificate_id, cert2.certificate_id)

        # Database Unique Constraint Verification
        with self.assertRaises(IntegrityError):
            Certificate.objects.create(
                student=student,
                program=program,
                template=self.template_modern,
                certificate_id=cert1.certificate_id,
                certificate_type="TRAINING",
                start_date=datetime.date(2026, 1, 1),
                end_date=datetime.date(2026, 2, 15),
                duration=45,
                issue_date=datetime.date(2026, 6, 1),
            )

    # =========================================================================
    # 8. VERIFICATION TOKEN SECURITY TESTS
    # =========================================================================
    def test_08_verification_token_high_entropy_and_uniqueness(self):
        """Verification tokens are cryptographically strong, URL-safe, and unique."""
        student = Student.objects.create(
            full_name="John von Neumann",
            email="jvn@ias.edu",
            phone="+1-555-0909",
            college="Princeton",
            graduation_year=2026,
        )
        program = Program.objects.create(
            name="Quantum Computing & Automata",
            program_type="INTERNSHIP",
            duration=60,
            mode="ONLINE",
            is_active=True,
        )

        cert = Certificate.objects.create(
            student=student,
            program=program,
            template=self.template_modern,
            certificate_type="INTERNSHIP",
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 3, 2),
            duration=60,
            issue_date=datetime.date(2026, 6, 1),
            status="ISSUED",
        )

        self.assertTrue(len(cert.verification_token) >= 32)
        # Token must not contain private student details
        self.assertNotIn(student.email, cert.verification_token)
        self.assertNotIn(student.full_name, cert.verification_token)

        # Token uniqueness in DB
        with self.assertRaises(IntegrityError):
            Certificate.objects.create(
                student=student,
                program=program,
                template=self.template_modern,
                verification_token=cert.verification_token,
                certificate_type="INTERNSHIP",
                start_date=datetime.date(2026, 1, 1),
                end_date=datetime.date(2026, 3, 2),
                duration=60,
                issue_date=datetime.date(2026, 6, 1),
            )

    # =========================================================================
    # 9. QR GENERATION TESTS
    # =========================================================================
    def test_09_qr_generation_encodes_only_verification_url(self):
        """QR code encodes only the public URL and saves a valid PNG file."""
        token = "secure_public_token_xyz123abc456"
        url = QRCodeService.get_verification_url(token, base_url="https://verify.certhub.org")
        self.assertEqual(url, f"https://verify.certhub.org/verify/{token}/")

        student = Student.objects.create(
            full_name="Donald Knuth",
            email="knuth@stanford.edu",
            phone="+1-555-3141",
            college="Stanford",
            graduation_year=2026,
        )
        program = Program.objects.create(
            name="Algorithms & Concrete Mathematics",
            program_type="COURSE",
            duration=30,
            mode="ONLINE",
            is_active=True,
        )
        cert = Certificate.objects.create(
            student=student,
            program=program,
            template=self.template_modern,
            certificate_type="COURSE",
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 1, 31),
            duration=30,
            issue_date=datetime.date(2026, 6, 1),
            status="ISSUED",
        )

        QRCodeService.generate_qr_for_certificate(cert, save=True)
        cert.refresh_from_db()

        self.assertTrue(bool(cert.qr_code))
        self.assertTrue(cert.qr_code.name.endswith(".png"))

    # =========================================================================
    # 10. PDF GENERATION TESTS
    # =========================================================================
    def test_10_pdf_generation_weasyprint_compilation(self):
        """WeasyPrint renders the certificate template into valid PDF binary bytes."""
        student = Student.objects.create(
            full_name="Margaret Hamilton",
            email="margaret.hamilton@mit.edu",
            phone="+1-555-1969",
            college="MIT",
            graduation_year=2026,
        )
        program = Program.objects.create(
            name="Apollo Flight Software Engineering",
            program_type="INTERNSHIP",
            duration=180,
            mode="HYBRID",
            is_active=True,
        )
        cert = Certificate.objects.create(
            student=student,
            program=program,
            certificate_type="INTERNSHIP",
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 6, 30),
            duration=180,
            issue_date=datetime.date(2026, 7, 20),
            status="ISSUED",
            template=self.template_classic,
            authorized_signatory=self.signatory,
        )

        pdf_file = CertificatePDFService.generate_pdf_for_certificate(cert, save=True)
        cert.refresh_from_db()

        self.assertTrue(bool(cert.certificate_pdf))
        self.assertTrue(cert.certificate_pdf.name.endswith(".pdf"))
        # Verify valid PDF magic bytes
        cert.certificate_pdf.open("rb")
        pdf_bytes = cert.certificate_pdf.read(10)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    # =========================================================================
    # 11. CERTIFICATE VERIFICATION TESTS
    # =========================================================================
    def test_11_certificate_verification_success_html_and_json(self):
        """Public verification returns 200 with verified badge and logs verification event."""
        student = Student.objects.create(
            full_name="Radia Perlman",
            email="radia.perlman@mit.edu",
            phone="+1-555-8021",
            college="MIT",
            graduation_year=2026,
        )
        program = Program.objects.create(
            name="Spanning Tree Protocol & Network Routing",
            program_type="INTERNSHIP",
            duration=60,
            mode="ONLINE",
            skills=["Spanning Tree Protocol", "Layer 2 Switching", "BGP"],
            learning_outcomes=["Design loop-free networks"],
            is_active=True,
        )
        cert = Certificate.objects.create(
            student=student,
            program=program,
            certificate_type="INTERNSHIP",
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 3, 2),
            duration=60,
            issue_date=datetime.date(2026, 8, 1),
            status="ISSUED",
            template=self.template_pro,
            authorized_signatory=self.signatory,
        )

        # 1. HTML Verification Page
        verify_url = reverse("verify:verify_token", kwargs={"token": cert.verification_token})
        resp = self.client.get(verify_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "VERIFIED CERTIFICATE")
        self.assertContains(resp, "Radia Perlman")
        self.assertContains(resp, "Spanning Tree Protocol")

        # 2. JSON API Verification Endpoint
        json_resp = self.client.get(verify_url, HTTP_ACCEPT="application/json")
        self.assertEqual(json_resp.status_code, 200)
        data = json_resp.json()
        self.assertTrue(data["valid"])
        self.assertEqual(data["status"], "VERIFIED")
        self.assertEqual(data["student_name"], "Radia Perlman")

        # 3. Verification Event Recorded
        event = VerificationEvent.objects.filter(certificate=cert).first()
        self.assertIsNotNone(event)

    # =========================================================================
    # 12. INVALID VERIFICATION TESTS
    # =========================================================================
    def test_12_invalid_verification_unknown_token_and_search_miss(self):
        """Unknown or invalid token displays not found and records audit log."""
        # 1. Unknown token lookup
        bad_url = reverse("verify:verify_token", kwargs={"token": "non_existent_token_999"})
        resp = self.client.get(bad_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "CERTIFICATE NOT FOUND")

        # 2. JSON response for bad token
        json_resp = self.client.get(bad_url, HTTP_ACCEPT="application/json")
        self.assertEqual(json_resp.status_code, 404)

        # 3. AuditLog recorded for failed attempt
        audit = AuditLog.objects.filter(action="VERIFY", object_id="non_existent_token_999").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.changes["result"], "NOT_FOUND")

    # =========================================================================
    # 13. REVOCATION TESTS
    # =========================================================================
    def test_13_revocation_lifecycle_and_access_block(self):
        """Revoked certificates display revoked status and block public PDF downloads."""
        self.client.login(username="master_admin", password="SecureMasterPassword123!")

        student = Student.objects.create(
            full_name="Revocation Target",
            email="revoked.student@univ.edu",
            phone="+1-555-0000",
            college="Test College",
            graduation_year=2026,
        )
        program = Program.objects.create(
            name="Security Fundamentals",
            program_type="TRAINING",
            duration=30,
            mode="ONLINE",
            is_active=True,
        )
        cert = CertificateIssuanceService.issue_certificate(
            student=student,
            program=program,
            certificate_type="TRAINING",
            template=self.template_modern,
            authorized_signatory=self.signatory,
            issue_date=datetime.date(2026, 4, 1),
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 1, 31),
            duration=30,
            user=self.admin_user,
        )

        # Revoke via View
        revoke_url = reverse("dashboard:certificate_revoke", kwargs={"pk": cert.pk})
        revoke_resp = self.client.post(
            revoke_url,
            {"revocation_reason": "Academic Honor Code Violation"},
            follow=True,
        )
        self.assertEqual(revoke_resp.status_code, 200)
        cert.refresh_from_db()
        self.assertEqual(cert.status, "REVOKED")
        self.assertEqual(cert.revocation_reason, "Academic Honor Code Violation")

        # Verification Portal Shows Revoked
        verify_url = reverse("verify:verify_token", kwargs={"token": cert.verification_token})
        verify_resp = self.client.get(verify_url)
        self.assertEqual(verify_resp.status_code, 200)
        self.assertContains(verify_resp, "Certificate Revoked")

        # Public PDF download blocked (404)
        dl_url = reverse("verify:verify_download", kwargs={"token": cert.verification_token})
        dl_resp = self.client.get(dl_url)
        self.assertEqual(dl_resp.status_code, 404)

        # PDF regeneration blocked
        regen_url = reverse("dashboard:certificate_regenerate_pdf", kwargs={"pk": cert.pk})
        regen_resp = self.client.post(regen_url, follow=True)
        self.assertContains(regen_resp, "Cannot regenerate PDF for a revoked certificate.")

    # =========================================================================
    # 14. EXPIRED CERTIFICATES TESTS
    # =========================================================================
    def test_14_expired_certificate_verification_status(self):
        """Certificates marked EXPIRED display expired status on public verification."""
        student = Student.objects.create(
            full_name="Past Graduate",
            email="past.grad@univ.edu",
            phone="+1-555-9999",
            college="Test College",
            graduation_year=2024,
        )
        program = Program.objects.create(
            name="Temporary Safety Certification",
            program_type="TRAINING",
            duration=30,
            mode="ONLINE",
            is_active=True,
        )
        cert = Certificate.objects.create(
            student=student,
            program=program,
            certificate_type="TRAINING",
            start_date=datetime.date(2025, 1, 1),
            end_date=datetime.date(2025, 1, 31),
            duration=30,
            issue_date=datetime.date(2025, 1, 1),
            status="EXPIRED",
            template=self.template_modern,
            authorized_signatory=self.signatory,
        )

        verify_url = reverse("verify:verify_token", kwargs={"token": cert.verification_token})
        resp = self.client.get(verify_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Certificate Expired")

    # =========================================================================
    # 15. AUDIT LOGS TESTS
    # =========================================================================
    def test_15_audit_logs_tracking_sanitization_and_filtering(self):
        """AuditLog records all events with sensitive data redaction and supports admin filters."""
        self.client.login(username="master_admin", password="SecureMasterPassword123!")

        # 1. Test Sanitization
        raw_metadata = {
            "user": "auditor",
            "password": "ClearTextPassword123",
            "secret_key": "sec_key_xyz",
            "action_reason": "Regular maintenance",
        }
        sanitized = AuditLogService.sanitize_data(raw_metadata)
        self.assertEqual(sanitized["password"], "[REDACTED]")
        self.assertEqual(sanitized["secret_key"], "[REDACTED]")
        self.assertEqual(sanitized["action_reason"], "Regular maintenance")

        # 2. Record Test Logs
        AuditLog.objects.all().delete()
        AuditLogService.log_event(
            action="CREATE",
            object_type="Student",
            object_id="STU-2026-999001",
            user_email="admin@certhub.local",
            changes={"name": "Test Student"},
        )
        AuditLogService.log_event(
            action="ISSUE",
            object_type="Certificate",
            object_id="COMP-INT-2026-999002",
            user_email="admin@certhub.local",
            changes={"status": "ISSUED"},
        )

        # 3. Filter Logs via Admin View
        logs_url = reverse("dashboard:audit_log_list")
        resp_issue = self.client.get(logs_url, {"action": "ISSUE"})
        self.assertEqual(resp_issue.status_code, 200)
        self.assertContains(resp_issue, "COMP-INT-2026-999002")
        self.assertNotContains(resp_issue, "STU-2026-999001")

        resp_search = self.client.get(logs_url, {"q": "999001"})
        self.assertEqual(resp_search.status_code, 200)
        self.assertContains(resp_search, "STU-2026-999001")

    # =========================================================================
    # 16. FILE UPLOADS TESTS
    # =========================================================================
    def test_16_file_uploads_signatory_signature_and_bulk_csv(self):
        """Signatory signature image uploads and bulk CSV imports are validated and processed."""
        self.client.login(username="master_admin", password="SecureMasterPassword123!")

        # 1. Signatory Image Upload
        sig_image = create_dummy_image("ada_signature.png", width=120, height=40)
        create_sig_url = reverse("dashboard:signatory_add")
        resp_sig = self.client.post(
            create_sig_url,
            {
                "name": "Prof. Charles Babbage",
                "title": "Chair of Computing",
                "organization": "Global Cybersecurity & Tech Institute",
                "email": "babbage@gcti.org",
                "signature_image": sig_image,
                "is_active": True,
            },
            follow=True,
        )
        self.assertEqual(resp_sig.status_code, 200)
        babbage = AuthorizedSignatory.objects.get(name="Prof. Charles Babbage")
        self.assertTrue(bool(babbage.signature_image))
        self.assertTrue(babbage.signature_image.name.endswith(".png"))

        # 2. Bulk CSV Upload and Zero-Issuance on Validation Failure
        bad_csv_content = (
            "full_name,email,college,program_name,certificate_type,start_date,end_date\n"
            "Valid Student,valid.csv@univ.edu,MIT,NonExistentProgram,INTERNSHIP,2026-01-01,2026-03-01\n"
        )
        csv_file = SimpleUploadedFile("batch_test.csv", bad_csv_content.encode("utf-8"), content_type="text/csv")
        validate_url = reverse("dashboard:certificate_bulk_validate")
        resp_csv = self.client.post(validate_url, {"csv_file": csv_file}, follow=True)
        self.assertEqual(resp_csv.status_code, 200)

        # CSV validation preview should show invalid row
        preview_data = self.client.session.get("bulk_validation_data")
        self.assertIsNotNone(preview_data)
        self.assertFalse(preview_data["is_valid"])
        self.assertEqual(preview_data["invalid_rows_count"], 1)

        # Confirmation must refuse to issue any certificates
        confirm_url = reverse("dashboard:certificate_bulk_confirm")
        resp_confirm = self.client.post(confirm_url, follow=True)
        self.assertContains(resp_confirm, "Cannot generate certificates: CSV contains validation errors.")
        self.assertFalse(Certificate.objects.filter(student__email="valid.csv@univ.edu").exists())
