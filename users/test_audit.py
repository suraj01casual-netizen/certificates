"""Targeted unit tests for the AuditLog system and AuditLogService."""

import datetime
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from certificates.models import Certificate, CertificateTemplate, Enrollment, Program
from certificates.services import CertificateIssuanceService
from users.audit_service import AuditLogService
from users.models import AuditLog, AuthorizedSignatory, CompanySettings, Student


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AuditLogSystemTests(TestCase):
    """Test suite for system-wide audit logging and admin log inspection."""

    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            username="audit_admin",
            email="auditadmin@test.local",
            password="adminpassword123",
        )

        cls.company = CompanySettings.get_instance()
        cls.company.company_name = "Global Audit Academy"
        cls.company.save()

        cls.program = Program.objects.create(
            name="Cybersecurity & Incident Response",
            program_type="INTERNSHIP",
            duration=90,
            mode="ONLINE",
            department="Security",
            is_active=True,
        )

        cls.template = CertificateTemplate.objects.create(
            name="Security Certificate Modern",
            design_style="MODERN",
            organization="Global Audit Academy",
            is_active=True,
        )

        cls.signatory = AuthorizedSignatory.objects.create(
            name="Alan Turing",
            title="Director of Forensics",
            organization="Global Audit Academy",
            email="alan@gaa.edu",
            is_active=True,
        )

    def setUp(self):
        self.client.login(username="audit_admin", password="adminpassword123")
        AuditLog.objects.all().delete()

    def test_sensitive_data_sanitization(self):
        """Sensitive keys (passwords, secrets, keys) are redacted in audit changes."""
        dirty_data = {
            "user_email": "admin@gaa.edu",
            "password": "SuperSecretPassword123!",
            "api_key": "sec_live_998877",
            "student_name": "Rosalind Franklin",
            "nested": {
                "db_secret": "my_db_pass",
                "normal_field": "visible_value",
            },
        }
        clean_data = AuditLogService.sanitize_data(dirty_data)

        self.assertEqual(clean_data["user_email"], "admin@gaa.edu")
        self.assertEqual(clean_data["password"], "[REDACTED]")
        self.assertEqual(clean_data["api_key"], "[REDACTED]")
        self.assertEqual(clean_data["student_name"], "Rosalind Franklin")
        self.assertEqual(clean_data["nested"]["db_secret"], "[REDACTED]")
        self.assertEqual(clean_data["nested"]["normal_field"], "visible_value")

    def test_student_lifecycle_audit_logging(self):
        """Student creation, update, and deactivation are logged in AuditLog."""
        # 1. Create Student
        create_url = reverse("dashboard:student_add")
        resp = self.client.post(
            create_url,
            {
                "full_name": "Grace Hopper",
                "email": "grace.hopper@usnavy.mil",
                "phone": "+1-555-0199",
                "college": "Vassar College",
                "university": "Yale",
                "degree": "Ph.D.",
                "branch": "Mathematics",
                "graduation_year": 2026,
                "is_active": True,
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)

        student = Student.objects.get(email="grace.hopper@usnavy.mil")
        create_log = AuditLog.objects.filter(action="CREATE", object_type="Student").first()
        self.assertIsNotNone(create_log)
        self.assertEqual(create_log.object_id, student.student_id)
        self.assertEqual(create_log.user_email, "auditadmin@test.local")

        # 2. Update Student
        update_url = reverse("dashboard:student_edit", kwargs={"pk": student.pk})
        resp_update = self.client.post(
            update_url,
            {
                "full_name": "Rear Admiral Grace Hopper",
                "email": "grace.hopper@usnavy.mil",
                "phone": "+1-555-0199",
                "college": "Vassar College",
                "university": "Yale",
                "degree": "Ph.D.",
                "branch": "Mathematics",
                "graduation_year": 2026,
                "is_active": True,
            },
            follow=True,
        )
        self.assertEqual(resp_update.status_code, 200)

        update_log = AuditLog.objects.filter(action="UPDATE", object_type="Student").first()
        self.assertIsNotNone(update_log)
        self.assertEqual(update_log.changes["full_name"], "Rear Admiral Grace Hopper")

        # 3. Deactivate Student
        deact_url = reverse("dashboard:student_deactivate", kwargs={"pk": student.pk})
        resp_deact = self.client.post(deact_url, follow=True)
        self.assertEqual(resp_deact.status_code, 200)

        deact_log = AuditLog.objects.filter(
            action="UPDATE", object_type="Student", changes__status="DEACTIVATED"
        ).first()
        self.assertIsNotNone(deact_log)

    def test_program_lifecycle_audit_logging(self):
        """Program creation, update, and active state toggling are logged in AuditLog."""
        # 1. Create Program
        create_url = reverse("dashboard:program_add")
        resp = self.client.post(
            create_url,
            {
                "name": "Cloud Native Kubernetes Architecture",
                "program_type": "TRAINING",
                "description": "Production Kubernetes Administration",
                "duration": 45,
                "mode": "ONLINE",
                "department": "Infrastructure",
                "mentor": "Linus Torvalds",
                "is_active": True,
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)

        prog = Program.objects.get(name="Cloud Native Kubernetes Architecture")
        create_log = AuditLog.objects.filter(action="CREATE", object_type="Program").first()
        self.assertIsNotNone(create_log)
        self.assertEqual(create_log.object_id, prog.program_id)

        # 2. Toggle Active
        toggle_url = reverse("dashboard:program_toggle_active", kwargs={"pk": prog.pk})
        resp_toggle = self.client.post(toggle_url, follow=True)
        self.assertEqual(resp_toggle.status_code, 200)

        toggle_log = AuditLog.objects.filter(
            action="UPDATE", object_type="Program", changes__is_active=False
        ).first()
        self.assertIsNotNone(toggle_log)

    def test_certificate_lifecycle_audit_logging(self):
        """Certificate issuance, downloads, verifications, regenerations, and revocations are logged."""
        student = Student.objects.create(
            full_name="Claude Shannon",
            email="claude.shannon@bell-labs.com",
            phone="+1-555-0123",
            college="MIT",
            university="MIT",
            degree="M.S.",
            branch="EECS",
            graduation_year=2026,
            is_active=True,
        )

        # 1. Issue Certificate
        cert = CertificateIssuanceService.issue_certificate(
            student=student,
            program=self.program,
            certificate_type="INTERNSHIP",
            template=self.template,
            authorized_signatory=self.signatory,
            issue_date=datetime.date(2026, 5, 1),
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 3, 31),
            duration=90,
            user=self.admin_user,
            ip_address="10.0.0.1",
        )

        issue_log = AuditLog.objects.filter(action="ISSUE", object_id=cert.certificate_id).first()
        self.assertIsNotNone(issue_log)
        self.assertEqual(issue_log.changes["status"], "ISSUED")

        # 2. Download from Dashboard
        dl_url = reverse("dashboard:certificate_download", kwargs={"pk": cert.pk})
        dl_resp = self.client.get(dl_url)
        self.assertEqual(dl_resp.status_code, 200)

        dl_log = AuditLog.objects.filter(
            action="DOWNLOAD", object_id=cert.certificate_id, changes__source="DASHBOARD"
        ).first()
        self.assertIsNotNone(dl_log)

        # 3. Public Download
        pub_dl_url = reverse("verify:verify_download", kwargs={"token": cert.verification_token})
        pub_dl_resp = self.client.get(pub_dl_url)
        self.assertEqual(pub_dl_resp.status_code, 200)

        pub_dl_log = AuditLog.objects.filter(
            action="DOWNLOAD", object_id=cert.certificate_id, changes__source="PUBLIC_VERIFY_PAGE"
        ).first()
        self.assertIsNotNone(pub_dl_log)

        # 4. Public Verification
        verify_url = reverse("verify:verify_token", kwargs={"token": cert.verification_token})
        verify_resp = self.client.get(verify_url)
        self.assertEqual(verify_resp.status_code, 200)

        verify_log = AuditLog.objects.filter(action="VERIFY", object_id=cert.certificate_id).first()
        self.assertIsNotNone(verify_log)
        self.assertEqual(verify_log.changes["result"], "VERIFIED")

        # 5. Regenerate PDF
        regen_url = reverse("dashboard:certificate_regenerate_pdf", kwargs={"pk": cert.pk})
        regen_resp = self.client.post(regen_url, follow=True)
        self.assertEqual(regen_resp.status_code, 200)

        regen_log = AuditLog.objects.filter(action="REGENERATE", object_id=cert.certificate_id).first()
        self.assertIsNotNone(regen_log)

        # 6. Revoke Certificate
        revoke_url = reverse("dashboard:certificate_revoke", kwargs={"pk": cert.pk})
        revoke_resp = self.client.post(
            revoke_url,
            {"revocation_reason": "Academic Honor Code Policy Infraction"},
            follow=True,
        )
        self.assertEqual(revoke_resp.status_code, 200)

        revoke_log = AuditLog.objects.filter(action="REVOKE", object_id=cert.certificate_id).first()
        self.assertIsNotNone(revoke_log)
        self.assertEqual(revoke_log.changes["revocation_reason"], "Academic Honor Code Policy Infraction")

    def test_audit_log_admin_view_filtering_and_search(self):
        """Admin audit log page supports search query, action filter, object filter, and date filters."""
        # Create test logs
        AuditLogService.log_event(
            action="CREATE",
            object_type="Student",
            object_id="STU-2026-000101",
            user_email="auditor@gaa.edu",
            changes={"student_name": "Ada Lovelace"},
        )
        AuditLogService.log_event(
            action="ISSUE",
            object_type="Certificate",
            object_id="COMP-INT-2026-778899",
            user_email="auditor@gaa.edu",
            changes={"student_name": "Ada Lovelace"},
        )
        AuditLogService.log_event(
            action="REVOKE",
            object_type="Certificate",
            object_id="COMP-INT-2026-112233",
            user_email="auditor@gaa.edu",
            changes={"revocation_reason": "Clerical error"},
        )

        logs_url = reverse("dashboard:audit_log_list")

        # 1. Base view
        resp = self.client.get(logs_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "System Audit &amp; Event Logs")
        self.assertContains(resp, "COMP-INT-2026-778899")

        # 2. Filter by Action=ISSUE
        resp_act = self.client.get(logs_url, {"action": "ISSUE"})
        self.assertEqual(resp_act.status_code, 200)
        self.assertContains(resp_act, "COMP-INT-2026-778899")
        self.assertNotContains(resp_act, "STU-2026-000101")

        # 3. Filter by Object Type=Student
        resp_obj = self.client.get(logs_url, {"object_type": "Student"})
        self.assertEqual(resp_obj.status_code, 200)
        self.assertContains(resp_obj, "STU-2026-000101")
        self.assertNotContains(resp_obj, "COMP-INT-2026-778899")

        # 4. Search by Query
        resp_search = self.client.get(logs_url, {"q": "112233"})
        self.assertEqual(resp_search.status_code, 200)
        self.assertContains(resp_search, "COMP-INT-2026-112233")
        self.assertNotContains(resp_search, "STU-2026-000101")
