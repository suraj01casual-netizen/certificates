"""Targeted unit tests for Bulk Student, Enrollment, and Certificate CSV processing."""

import datetime
import io
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from certificates.models import Certificate, CertificateTemplate, Enrollment, Program
from certificates.services import BulkCertificateService
from users.models import AuditLog, AuthorizedSignatory, CompanySettings, Student


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class BulkCertificateServiceTests(TestCase):
    """Unit tests for BulkCertificateService parsing, validation, and batch execution."""

    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username="bulk_admin",
            email="bulkadmin@test.local",
            password="adminpassword123",
        )

        cls.company = CompanySettings.get_instance()
        cls.company.company_name = "Apex Institute of Science"
        cls.company.save()

        cls.program_ai = Program.objects.create(
            name="Applied Artificial Intelligence & Deep Learning",
            program_type="INTERNSHIP",
            duration=90,
            mode="ONLINE",
            department="Computer Science",
            is_active=True,
        )

        cls.program_data = Program.objects.create(
            name="Data Engineering & Cloud Infrastructure",
            program_type="TRAINING",
            duration=60,
            mode="ONLINE",
            department="Data Science",
            is_active=True,
        )

        cls.template = CertificateTemplate.objects.create(
            name="Classic Prestige",
            design_style="CLASSIC",
            organization="Apex Institute of Science",
            is_active=True,
        )

        cls.signatory = AuthorizedSignatory.objects.create(
            name="Dr. Marie Curie",
            title="Dean of Research",
            organization="Apex Institute of Science",
            email="marie.curie@apex.edu",
            is_active=True,
        )

    def test_sample_csv_generation(self):
        """Sample CSV contains required headers and example data."""
        content = BulkCertificateService.get_sample_csv_content()
        self.assertIn("full_name", content)
        self.assertIn("email", content)
        self.assertIn("program", content)
        self.assertIn("start_date", content)

    def test_validate_valid_csv(self):
        """Valid CSV passes all checks and produces structured preview and execution data."""
        csv_text = (
            "full_name,email,program,certificate_type,start_date,end_date,duration,college\n"
            "Grace Hopper,grace.hopper@navy.mil,Applied Artificial Intelligence & Deep Learning,INTERNSHIP,2026-01-01,2026-03-31,90,Yale University\n"
            "Claude Shannon,claude.shannon@bell.com,Data Engineering & Cloud Infrastructure,TRAINING,2026-02-01,2026-04-01,60,MIT\n"
        )
        result = BulkCertificateService.validate_csv(
            csv_text,
            default_template_id=self.template.pk,
            default_signatory_id=self.signatory.pk,
        )

        self.assertTrue(result.is_valid)
        self.assertEqual(result.total_rows, 2)
        self.assertEqual(result.valid_rows_count, 2)
        self.assertEqual(result.invalid_rows_count, 0)
        self.assertEqual(len(result.row_errors), 0)
        self.assertEqual(len(result.serialized_data), 2)
        self.assertEqual(result.serialized_data[0]["full_name"], "Grace Hopper")
        self.assertEqual(result.serialized_data[1]["email"], "claude.shannon@bell.com")

    def test_validate_missing_required_columns(self):
        """CSV missing mandatory header columns fails header validation."""
        csv_text = "student_name,start_date\nJohn Doe,2026-01-01\n"
        result = BulkCertificateService.validate_csv(csv_text)

        self.assertFalse(result.is_valid)
        self.assertGreater(len(result.header_errors), 0)
        self.assertIn("email", result.header_errors[0])
        self.assertIn("program", result.header_errors[0])

    def test_validate_invalid_emails_dates_and_programs(self):
        """Row errors are gathered for bad email, bad dates, and nonexistent program."""
        csv_text = (
            "full_name,email,program,start_date,end_date\n"
            "Invalid Person,not-an-email,Nonexistent Program 999,invalid-date,2026-01-01\n"
            "Date Inverted,inverted@test.com,Applied Artificial Intelligence & Deep Learning,2026-05-01,2026-01-01\n"
        )
        result = BulkCertificateService.validate_csv(
            csv_text,
            default_template_id=self.template.pk,
            default_signatory_id=self.signatory.pk,
        )

        self.assertFalse(result.is_valid)
        self.assertEqual(result.total_rows, 2)
        self.assertEqual(result.invalid_rows_count, 2)
        self.assertEqual(len(result.row_errors), 2)

        # Check row 2 errors
        row2_errs = result.row_errors[0].errors
        self.assertTrue(any("Invalid email" in e for e in row2_errs))
        self.assertTrue(any("Program" in e and "not found" in e for e in row2_errs))
        self.assertTrue(any("Invalid start date" in e for e in row2_errs))

        # Check row 3 errors (inverted date)
        row3_errs = result.row_errors[1].errors
        self.assertTrue(any("earlier than start date" in e for e in row3_errs))

    def test_validate_duplicate_rows_in_csv(self):
        """Duplicate rows within the same CSV batch are detected and flagged."""
        csv_text = (
            "full_name,email,program,start_date\n"
            "Duplicate User,dup@test.com,Applied Artificial Intelligence & Deep Learning,2026-01-01\n"
            "Duplicate User,dup@test.com,Applied Artificial Intelligence & Deep Learning,2026-01-01\n"
        )
        result = BulkCertificateService.validate_csv(
            csv_text,
            default_template_id=self.template.pk,
            default_signatory_id=self.signatory.pk,
        )

        self.assertFalse(result.is_valid)
        self.assertEqual(result.invalid_rows_count, 1)
        self.assertEqual(result.valid_rows_count, 1)
        self.assertTrue(any("Duplicate entry in CSV" in e for e in result.row_errors[0].errors))

    def test_execute_bulk_issuance_creates_students_and_certificates(self):
        """Validated rows are issued in a transaction, creating students, enrollments, and certificates."""
        csv_text = (
            "full_name,email,program,certificate_type,start_date,end_date,duration,college,university,degree,branch,graduation_year,phone\n"
            "Katherine Johnson,katherine.johnson@nasa.gov,Applied Artificial Intelligence & Deep Learning,INTERNSHIP,2026-01-15,2026-04-15,90,WV State,State Univ,B.S.,Mathematics,2026,+1-555-001-9999\n"
            "Margaret Hamilton,margaret.hamilton@mit.edu,Data Engineering & Cloud Infrastructure,TRAINING,2026-02-01,2026-03-31,60,Earlham College,Earlham,B.A.,Math & Science,2025,+1-555-002-8888\n"
        )
        val_result = BulkCertificateService.validate_csv(
            csv_text,
            default_template_id=self.template.pk,
            default_signatory_id=self.signatory.pk,
        )
        self.assertTrue(val_result.is_valid)

        exec_result = BulkCertificateService.execute_bulk_issuance(
            validated_rows=val_result.serialized_data,
            user=self.admin_user,
            ip_address="127.0.0.1",
        )

        self.assertTrue(exec_result.success)
        self.assertEqual(exec_result.issued_count, 2)
        self.assertEqual(len(exec_result.certificate_ids), 2)

        # Check created students
        student_kj = Student.objects.filter(email="katherine.johnson@nasa.gov").first()
        self.assertIsNotNone(student_kj)
        self.assertEqual(student_kj.full_name, "Katherine Johnson")

        student_mh = Student.objects.filter(email="margaret.hamilton@mit.edu").first()
        self.assertIsNotNone(student_mh)

        # Check created certificates
        certs = Certificate.objects.filter(certificate_id__in=exec_result.certificate_ids)
        self.assertEqual(certs.count(), 2)
        for cert in certs:
            self.assertEqual(cert.status, "ISSUED")
            self.assertTrue(cert.certificate_pdf)
            self.assertTrue(cert.qr_code)
            self.assertTrue(cert.verification_token)

        # Check batch AuditLog
        batch_audit = AuditLog.objects.filter(
            action="ISSUE", object_type="BulkCertificateBatch"
        ).first()
        self.assertIsNotNone(batch_audit)
        self.assertEqual(batch_audit.changes["total_issued"], 2)

    def test_dashboard_bulk_workflow_views(self):
        """Full web workflow: upload CSV -> validate -> preview -> confirm -> redirect."""
        self.client.login(username="bulk_admin", password="adminpassword123")

        # 1. Sample CSV Download
        sample_url = reverse("dashboard:certificate_bulk_sample_csv")
        sample_resp = self.client.get(sample_url)
        self.assertEqual(sample_resp.status_code, 200)
        self.assertEqual(sample_resp["Content-Type"], "text/csv")

        # 2. Upload Page
        upload_url = reverse("dashboard:certificate_bulk_upload")
        upload_resp = self.client.get(upload_url)
        self.assertEqual(upload_resp.status_code, 200)
        self.assertContains(upload_resp, "Bulk Issue Certificates via CSV")

        # 3. Submit CSV for validation
        csv_content = (
            "full_name,email,program,start_date\n"
            "Emmy Noether,emmy.noether@erlangen.de,Applied Artificial Intelligence & Deep Learning,2026-03-01\n"
        ).encode("utf-8")
        csv_file = SimpleUploadedFile("batch_test.csv", csv_content, content_type="text/csv")

        val_url = reverse("dashboard:certificate_bulk_validate")
        post_resp = self.client.post(
            val_url,
            {
                "csv_file": csv_file,
                "default_template": self.template.pk,
                "default_signatory": self.signatory.pk,
            },
            follow=True,
        )
        self.assertEqual(post_resp.status_code, 200)
        self.assertContains(post_resp, "CSV Validated Successfully")
        self.assertContains(post_resp, "Emmy Noether")

        # 4. Confirm issuance
        confirm_url = reverse("dashboard:certificate_bulk_confirm")
        confirm_resp = self.client.post(confirm_url, follow=True)
        self.assertEqual(confirm_resp.status_code, 200)
        self.assertContains(confirm_resp, "Successfully issued 1 certificates in bulk")

        # Verify certificate in database
        en_cert = Certificate.objects.filter(student__email="emmy.noether@erlangen.de").first()
        self.assertIsNotNone(en_cert)
        self.assertEqual(en_cert.status, "ISSUED")
