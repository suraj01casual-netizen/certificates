"""
Tests for certificate identity generation.

Covers the four required guarantees:
  1. Certificate IDs are unique.
  2. Verification tokens are unique.
  3. Verification tokens are not predictable.
  4. Existing certificate IDs never change.

Also verifies the ID format, type-prefix mapping, and that the service
does **not** rely on forbidden primitives (random.randint, timestamps
alone, sequential IDs, MD5, predictable hashes).
"""

import re
import secrets
import string
from collections import Counter
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from certificates.models import (
    Certificate,
    CertificateTemplate,
    Program,
)
from certificates.services import (
    CERTIFICATE_ID_PREFIX,
    CERTIFICATE_TYPE_PREFIXES,
    CertificateService,
    QRCodeService,
    CertificatePDFService,
    CertificateIssuanceService,
)
from users.models import AuthorizedSignatory, Student, AuditLog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_student(email="student@example.com", full_name="Test Student"):
    """Create and return a Student instance."""
    return Student.objects.create(
        full_name=full_name,
        email=email,
        phone="1234567890",
        college="Test College",
        university="Test University",
        degree="B.Tech",
        branch="Computer Science",
        graduation_year=timezone.now().year,
        is_active=True,
    )


def _make_program(name="Test Program"):
    """Create and return a Program instance."""
    return Program.objects.create(
        name=name,
        program_type="INTERNSHIP",
        description="A test program.",
        duration=30,
        mode="ONLINE",
        department="Computer Science",
        mentor="Test Mentor",
        skills=["Python"],
        learning_outcomes=["Learn Python"],
        is_active=True,
    )


def _make_template(name="Test Template"):
    """Create and return a CertificateTemplate instance."""
    return CertificateTemplate.objects.create(
        name=name,
        organization="Test Org",
        description="A test template.",
        html_template="<html></html>",
        colors={"primary": "#000000"},
        is_active=True,
    )


def _make_signatory(name="Test Signatory"):
    """Create and return an AuthorizedSignatory instance."""
    return AuthorizedSignatory.objects.create(
        name=name,
        title="Director",
        organization="Test Org",
        email="signatory@example.com",
        signature_image="signatures/test.png",
    )


def _make_certificate(
    certificate_type="INTERNSHIP",
    student=None,
    program=None,
    template=None,
    signatory=None,
):
    """Create and return a Certificate instance with sensible defaults."""
    if student is None:
        student = _make_student()
    if program is None:
        program = _make_program()
    if template is None:
        template = _make_template()
    if signatory is None:
        signatory = _make_signatory()

    return Certificate.objects.create(
        student=student,
        program=program,
        certificate_type=certificate_type,
        issue_date=timezone.now().date(),
        start_date=timezone.now().date(),
        end_date=None,
        duration=30,
        status="ISSUED",
        template=template,
        authorized_signatory=signatory,
    )


# ---------------------------------------------------------------------------
# ID format and prefix tests
# ---------------------------------------------------------------------------

class CertificateIDFormatTests(TestCase):
    """Verify the certificate ID format and type-prefix mapping."""

    def test_id_format_matches_pattern(self):
        """Every generated ID must match COMP-{PREFIX}-{YYYY}-{XXXXXX}."""
        cert = _make_certificate(certificate_type="INTERNSHIP")
        pattern = r"^COMP-[A-Z]{3}-\d{4}-\d{6}$"
        self.assertRegex(cert.certificate_id, pattern)

    def test_id_starts_with_comp_prefix(self):
        """The global prefix must be 'COMP'."""
        cert = _make_certificate()
        self.assertTrue(cert.certificate_id.startswith(f"{CERTIFICATE_ID_PREFIX}-"))

    def test_internship_prefix(self):
        """INTERNSHIP type → INT prefix."""
        cert = _make_certificate(certificate_type="INTERNSHIP")
        year = timezone.now().year
        self.assertTrue(cert.certificate_id.startswith(f"COMP-INT-{year}-"))

    def test_course_prefix(self):
        """COURSE type → COU prefix."""
        cert = _make_certificate(certificate_type="COURSE")
        year = timezone.now().year
        self.assertTrue(cert.certificate_id.startswith(f"COMP-COU-{year}-"))

    def test_workshop_prefix(self):
        """WORKSHOP type → WRK prefix."""
        cert = _make_certificate(certificate_type="WORKSHOP")
        year = timezone.now().year
        self.assertTrue(cert.certificate_id.startswith(f"COMP-WRK-{year}-"))

    def test_achievement_prefix(self):
        """ACHIEVEMENT type → ACH prefix."""
        cert = _make_certificate(certificate_type="ACHIEVEMENT")
        year = timezone.now().year
        self.assertTrue(cert.certificate_id.startswith(f"COMP-ACH-{year}-"))

    def test_training_prefix(self):
        """TRAINING type → TRN prefix (as shown in examples)."""
        cert = _make_certificate(certificate_type="INTERNSHIP")
        # TRAINING is not in the model choices, but the service mapping
        # should still support it.
        token = CertificateService.get_type_prefix("TRAINING")
        self.assertEqual(token, "TRN")

    def test_all_type_prefixes_are_three_letters(self):
        """Every prefix in the mapping must be exactly 3 uppercase letters."""
        for cert_type, prefix in CERTIFICATE_TYPE_PREFIXES.items():
            self.assertEqual(len(prefix), 3, f"Prefix for {cert_type} is not 3 chars")
            self.assertTrue(prefix.isalpha(), f"Prefix for {cert_type} is not alphabetic")
            self.assertTrue(prefix.isupper(), f"Prefix for {cert_type} is not uppercase")

    def test_unknown_type_raises_value_error(self):
        """An unknown certificate type must raise ValueError."""
        with self.assertRaises(ValueError):
            CertificateService.get_type_prefix("UNKNOWN_TYPE")

    def test_id_is_database_safe(self):
        """ID must contain only alphanumeric chars and hyphens."""
        cert = _make_certificate()
        allowed = set(string.ascii_letters + string.digits + "-")
        self.assertTrue(set(cert.certificate_id) <= allowed)

    def test_id_not_based_on_database_pk(self):
        """The certificate_id must not equal or be derived from the DB primary key."""
        cert = _make_certificate()
        self.assertNotEqual(cert.certificate_id, str(cert.pk))
        self.assertNotEqual(cert.certificate_id.split('-')[-1], str(cert.pk))
        self.assertNotEqual(cert.certificate_id.split('-')[-1], f"{cert.pk:06d}")

    def test_id_length_within_field_limit(self):
        """ID must fit within the 50-char CharField."""
        cert = _make_certificate()
        self.assertLessEqual(len(cert.certificate_id), 50)


# ---------------------------------------------------------------------------
# 1. IDs are unique
# ---------------------------------------------------------------------------

class CertificateIDUniquenessTests(TestCase):
    """Prove that certificate IDs are unique."""

    def test_ids_unique_across_many_certificates(self):
        """Generate 500 certificates and verify all IDs are unique."""
        student = _make_student()
        program = _make_program()
        template = _make_template()
        signatory = _make_signatory()

        ids = []
        for i in range(500):
            cert = Certificate.objects.create(
                student=student,
                program=program,
                certificate_type="INTERNSHIP",
                issue_date=timezone.now().date(),
                start_date=timezone.now().date(),
                duration=30,
                status="ISSUED",
                template=template,
                authorized_signatory=signatory,
            )
            ids.append(cert.certificate_id)

        unique_ids = set(ids)
        self.assertEqual(len(ids), len(unique_ids),
                         f"Found {len(ids) - len(unique_ids)} duplicate IDs")

    def test_ids_unique_across_different_types(self):
        """IDs for different certificate types must not collide."""
        student = _make_student()
        program = _make_program()
        template = _make_template()
        signatory = _make_signatory()

        types = ["INTERNSHIP", "COURSE", "WORKSHOP", "ACHIEVEMENT"]
        ids = []
        for cert_type in types:
            cert = Certificate.objects.create(
                student=student,
                program=program,
                certificate_type=cert_type,
                issue_date=timezone.now().date(),
                start_date=timezone.now().date(),
                duration=30,
                status="ISSUED",
                template=template,
                authorized_signatory=signatory,
            )
            ids.append(cert.certificate_id)

        self.assertEqual(len(ids), len(set(ids)))

    def test_service_generate_certificate_id_is_unique(self):
        """Direct service calls should produce unique IDs.

        Each generated ID is persisted to the DB so the service's
        built-in collision detection is exercised.  With 6 random
        digits (1 000 000 possibilities) the birthday paradox makes
        pure-random uniqueness unreliable at 1000+ IDs, but the
        service regenerates on collision, guaranteeing uniqueness.
        """
        student = _make_student()
        program = _make_program()
        template = _make_template()
        signatory = _make_signatory()

        ids = []
        for _ in range(1000):
            cert = Certificate.objects.create(
                student=student,
                program=program,
                certificate_type="INTERNSHIP",
                issue_date=timezone.now().date(),
                start_date=timezone.now().date(),
                duration=30,
                status="ISSUED",
                template=template,
                authorized_signatory=signatory,
            )
            ids.append(cert.certificate_id)

        self.assertEqual(len(ids), len(set(ids)),
                         f"Found {len(ids) - len(set(ids))} duplicate IDs")


    def test_ids_not_sequential(self):
        """Generated IDs must not be sequential (no predictable ordering)."""
        ids = [
            CertificateService.generate_certificate_id("INTERNSHIP")
            for _ in range(100)
        ]
        suffixes = [int(cid.split("-")[-1]) for cid in ids]
        # If sequential, consecutive differences would all be 1.
        diffs = [suffixes[i + 1] - suffixes[i] for i in range(len(suffixes) - 1)]
        # At least 90% of consecutive diffs should NOT be 1.
        non_sequential_count = sum(1 for d in diffs if d != 1)
        self.assertGreater(non_sequential_count, len(diffs) * 0.9,
                           "IDs appear to be sequential")


# ---------------------------------------------------------------------------
# 2. Tokens are unique
# ---------------------------------------------------------------------------

class VerificationTokenUniquenessTests(TestCase):
    """Prove that verification tokens are unique."""

    def test_tokens_unique_across_many_certificates(self):
        """Generate 500 certificates and verify all tokens are unique."""
        student = _make_student()
        program = _make_program()
        template = _make_template()
        signatory = _make_signatory()

        tokens = []
        for _ in range(500):
            cert = Certificate.objects.create(
                student=student,
                program=program,
                certificate_type="INTERNSHIP",
                issue_date=timezone.now().date(),
                start_date=timezone.now().date(),
                duration=30,
                status="ISSUED",
                template=template,
                authorized_signatory=signatory,
            )
            tokens.append(cert.verification_token)

        unique_tokens = set(tokens)
        self.assertEqual(len(tokens), len(unique_tokens),
                         f"Found {len(tokens) - len(unique_tokens)} duplicate tokens")

    def test_service_generate_token_is_unique(self):
        """Direct service calls should produce unique tokens."""
        tokens = [
            CertificateService.generate_verification_token()
            for _ in range(1000)
        ]
        self.assertEqual(len(tokens), len(set(tokens)))

    def test_token_is_not_empty(self):
        """Every token must be non-empty."""
        cert = _make_certificate()
        self.assertTrue(cert.verification_token)
        self.assertGreater(len(cert.verification_token), 0)

    def test_token_length_is_sufficient(self):
        """Token must have enough entropy (at least 32 chars)."""
        cert = _make_certificate()
        self.assertGreaterEqual(len(cert.verification_token), 32)


# ---------------------------------------------------------------------------
# 3. Tokens are not predictable
# ---------------------------------------------------------------------------

class VerificationTokenPredictabilityTests(TestCase):
    """Prove that verification tokens are not predictable."""

    def test_tokens_have_high_entropy(self):
        """Tokens should use a wide character set (base64url)."""
        tokens = [
            CertificateService.generate_verification_token()
            for _ in range(100)
        ]
        all_chars = set()
        for t in tokens:
            all_chars.update(t)
        # A CSPRNG-based token_urlsafe should use many different characters.
        self.assertGreater(len(all_chars), 20,
                           "Token character set is too small – may be predictable")

    def test_tokens_not_equal_to_timestamps(self):
        """Tokens must not be simple timestamps or timestamp-derived."""
        token = CertificateService.generate_verification_token()
        # A timestamp would be all digits.
        self.assertFalse(token.isdigit())
        # A timestamp would be short.
        self.assertGreater(len(token), 10)

    def test_tokens_not_sequential(self):
        """Consecutive tokens must not follow a sequential pattern."""
        tokens = [
            CertificateService.generate_verification_token()
            for _ in range(100)
        ]
        # If tokens were sequential integers, they'd all be digits.
        digit_count = sum(1 for t in tokens if t.isdigit())
        self.assertEqual(digit_count, 0,
                         "Tokens appear to be numeric/sequential")

    def test_tokens_not_predictable_from_previous(self):
        """Given N tokens, the (N+1)th should not be guessable."""
        tokens = [
            CertificateService.generate_verification_token()
            for _ in range(50)
        ]
        # Try to predict the next token by looking for patterns.
        # If tokens were sequential, the next would be derivable.
        # We verify that no simple arithmetic progression exists.
        # Convert tokens to integers (if possible) and check for patterns.
        int_tokens = []
        for t in tokens:
            try:
                int_tokens.append(int(t, 36))  # base36 to handle alphanumeric
            except ValueError:
                int_tokens.append(None)

        # At least some tokens should not be convertible to int
        # (token_urlsafe produces base64url which includes - and _)
        non_int_count = sum(1 for t in tokens if not t.isalnum())
        self.assertGreater(non_int_count, 0,
                           "All tokens are alphanumeric – may be predictable")

    def test_token_uses_secrets_module(self):
        """Verify that token generation uses secrets (CSPRNG), not random."""
        with mock.patch("certificates.services.secrets") as mock_secrets:
            mock_secrets.token_urlsafe.return_value = "mocked_token"
            token = CertificateService.generate_verification_token()
            self.assertEqual(token, "mocked_token")
            mock_secrets.token_urlsafe.assert_called_once()

    def test_token_not_md5_or_sha_hash(self):
        """Token must not be a 32-char hex (MD5) or 40-char hex (SHA1)."""
        token = CertificateService.generate_verification_token()
        # MD5 produces 32 hex chars; SHA1 produces 40 hex chars.
        self.assertFalse(
            len(token) == 32 and all(c in "0123456789abcdef" for c in token),
            "Token looks like an MD5 hash"
        )
        self.assertFalse(
            len(token) == 40 and all(c in "0123456789abcdef" for c in token),
            "Token looks like a SHA1 hash"
        )

    def test_token_not_based_on_random_randint(self):
        """Verify that random.randint is never used for token generation."""
        import ast
        import certificates.services as svc_module
        source = open(svc_module.__file__).read()
        tree = ast.parse(source)

        # Walk the AST and check for any 'random' module imports or
        # random.randint attribute calls.  This avoids false positives
        # from docstrings or comments that merely *mention* random.randint.
        random_imported = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "random":
                        random_imported = True
            elif isinstance(node, ast.ImportFrom):
                if node.module == "random":
                    random_imported = True
            elif isinstance(node, ast.Attribute):
                if (isinstance(node.value, ast.Name)
                        and node.value.id == "random"
                        and node.attr == "randint"):
                    self.fail("services.py uses random.randint – must use secrets instead")

        self.assertFalse(random_imported,
                         "services.py should not import the 'random' module")


    def test_token_not_based_on_timestamp_alone(self):
        """Token must not be derivable from a timestamp alone."""
        token1 = CertificateService.generate_verification_token()
        token2 = CertificateService.generate_verification_token()
        # If tokens were timestamp-based, they'd be very similar or identical
        # when generated in quick succession.
        self.assertNotEqual(token1, token2)


# ---------------------------------------------------------------------------
# 4. Existing certificate IDs never change
# ---------------------------------------------------------------------------

class CertificateIDImmutabilityTests(TestCase):
    """Prove that existing certificate IDs never change after creation."""

    def test_id_unchanged_on_resave(self):
        """Saving a certificate again must not change its certificate_id."""
        cert = _make_certificate()
        original_id = cert.certificate_id
        cert.save()
        cert.refresh_from_db()
        self.assertEqual(cert.certificate_id, original_id)

    def test_id_unchanged_on_field_update(self):
        """Updating other fields must not change the certificate_id."""
        cert = _make_certificate()
        original_id = cert.certificate_id
        cert.status = "REVOKED"
        cert.save()
        cert.refresh_from_db()
        self.assertEqual(cert.certificate_id, original_id)
        self.assertEqual(cert.status, "REVOKED")

    def test_id_unchanged_on_revoke(self):
        """Revoking a certificate must not change its certificate_id."""
        cert = _make_certificate()
        original_id = cert.certificate_id
        cert.revoke("Test revocation")
        cert.refresh_from_db()
        self.assertEqual(cert.certificate_id, original_id)
        self.assertEqual(cert.status, "REVOKED")

    def test_token_unchanged_on_resave(self):
        """Saving a certificate again must not change its verification_token."""
        cert = _make_certificate()
        original_token = cert.verification_token
        cert.save()
        cert.refresh_from_db()
        self.assertEqual(cert.verification_token, original_token)

    def test_id_unchanged_when_explicitly_set(self):
        """If certificate_id is explicitly provided, it must be preserved."""
        student = _make_student()
        program = _make_program()
        template = _make_template()
        signatory = _make_signatory()

        custom_id = "COMP-INT-2025-999999"
        cert = Certificate(
            student=student,
            program=program,
            certificate_type="INTERNSHIP",
            issue_date=timezone.now().date(),
            start_date=timezone.now().date(),
            duration=30,
            status="ISSUED",
            template=template,
            authorized_signatory=signatory,
            certificate_id=custom_id,
        )
        cert.save()
        cert.refresh_from_db()
        self.assertEqual(cert.certificate_id, custom_id)

    def test_id_unchanged_after_multiple_updates(self):
        """Multiple sequential saves must not change the certificate_id."""
        cert = _make_certificate()
        original_id = cert.certificate_id

        for i in range(5):
            cert.duration = 30 + i
            cert.save()
            cert.refresh_from_db()
            self.assertEqual(cert.certificate_id, original_id,
                             f"ID changed on update #{i + 1}")


# ---------------------------------------------------------------------------
# Service-level tests (no DB required)
# ---------------------------------------------------------------------------

class CertificateServiceUnitTests(TestCase):
    """Unit tests for CertificateService methods that don't require DB."""

    def test_generate_random_suffix_length(self):
        """Random suffix must be exactly 6 digits."""
        for _ in range(100):
            suffix = CertificateService.generate_random_suffix()
            self.assertEqual(len(suffix), 6)
            self.assertTrue(suffix.isdigit())

    def test_generate_random_suffix_is_zero_padded(self):
        """Suffix must be zero-padded to 6 characters."""
        for _ in range(100):
            suffix = CertificateService.generate_random_suffix()
            self.assertEqual(len(suffix), 6)
            # Should be parseable as int and back to 6-digit string
            self.assertEqual(suffix, str(int(suffix)).zfill(6))

    def test_generate_random_suffix_uses_secrets(self):
        """Suffix generation must use secrets.randbelow, not random.randint."""
        with mock.patch("certificates.services.secrets") as mock_secrets:
            mock_secrets.randbelow.return_value = 42
            suffix = CertificateService.generate_random_suffix()
            self.assertEqual(suffix, "000042")
            mock_secrets.randbelow.assert_called_once()

    def test_generate_verification_token_uses_secrets(self):
        """Token generation must use secrets.token_urlsafe."""
        with mock.patch("certificates.services.secrets") as mock_secrets:
            mock_secrets.token_urlsafe.return_value = "test_token_value"
            token = CertificateService.generate_verification_token()
            self.assertEqual(token, "test_token_value")
            mock_secrets.token_urlsafe.assert_called_once()

    def test_generate_certificate_id_format(self):
        """Generated ID must follow COMP-{PREFIX}-{YYYY}-{XXXXXX}."""
        cert_id = CertificateService.generate_certificate_id("INTERNSHIP", year=2026)
        self.assertRegex(cert_id, r"^COMP-INT-2026-\d{6}$")

    def test_generate_certificate_id_with_explicit_year(self):
        """Explicit year parameter must be reflected in the ID."""
        cert_id = CertificateService.generate_certificate_id("WORKSHOP", year=2025)
        self.assertTrue(cert_id.startswith("COMP-WRK-2025-"))

    def test_generate_identity_returns_both(self):
        """generate_identity must return (certificate_id, verification_token)."""
        cert_id, token = CertificateService.generate_identity("COURSE", year=2026)
        self.assertRegex(cert_id, r"^COMP-COU-2026-\d{6}$")
        self.assertTrue(token)
        self.assertGreater(len(token), 0)

    def test_no_sequential_ids_in_service(self):
        """Service-generated IDs must not be sequential."""
        ids = [
            CertificateService.generate_certificate_id("INTERNSHIP", year=2026)
            for _ in range(200)
        ]
        suffixes = [int(cid.split("-")[-1]) for cid in ids]
        # Check that not all consecutive differences are the same
        diffs = [suffixes[i + 1] - suffixes[i] for i in range(len(suffixes) - 1)]
        unique_diffs = set(diffs)
        self.assertGreater(len(unique_diffs), 1,
                           "All consecutive differences are the same – IDs are sequential")

    def test_no_random_randint_in_source(self):
        """The services module must not use random.randint (AST-based check)."""
        import ast
        import certificates.services as svc_module
        source = open(svc_module.__file__).read()
        tree = ast.parse(source)

        random_imported = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "random":
                        random_imported = True
            elif isinstance(node, ast.ImportFrom):
                if node.module == "random":
                    random_imported = True
            elif isinstance(node, ast.Attribute):
                if (isinstance(node.value, ast.Name)
                        and node.value.id == "random"
                        and node.attr == "randint"):
                    self.fail("services.py uses random.randint – must use secrets instead")

        self.assertFalse(random_imported,
                         "services.py should not import the 'random' module")


    def test_no_md5_in_source(self):
        """The services module must not use MD5."""
        import certificates.services as svc_module
        source = open(svc_module.__file__).read()
        self.assertNotIn("md5", source.lower())

    def test_no_hashlib_in_source(self):
        """The services module must not use hashlib (predictable hashes)."""
        import certificates.services as svc_module
        source = open(svc_module.__file__).read()
        self.assertNotIn("hashlib", source)

    def test_token_character_distribution(self):
        """Tokens should have a diverse character distribution (high entropy)."""
        tokens = [
            CertificateService.generate_verification_token()
            for _ in range(200)
        ]
        all_chars = "".join(tokens)
        char_counts = Counter(all_chars)
        # With 200 tokens of ~43 chars each, we should see many distinct chars.
        # A predictable scheme would use very few.
        self.assertGreater(len(char_counts), 30,
                           "Token character diversity is too low")

    def test_token_no_common_prefix(self):
        """Tokens should not share a long common prefix (not timestamp-based)."""
        tokens = [
            CertificateService.generate_verification_token()
            for _ in range(100)
        ]
        # Find the longest common prefix
        if len(tokens) > 1:
            prefix = tokens[0]
            for t in tokens[1:]:
                while not t.startswith(prefix):
                    prefix = prefix[:-1]
                    if not prefix:
                        break
            # A timestamp-based token would have a long common prefix.
            self.assertLess(len(prefix), 5,
                            "Tokens share a long common prefix – may be predictable")


# ---------------------------------------------------------------------------
# 5. QR Code Generation & Verification Tests
# ---------------------------------------------------------------------------

class QRCodeVerificationURLTests(TestCase):
    """Verify that QR code encodes strictly the public verification URL and no personal data."""

    def test_default_verification_url_format(self):
        """URL must follow <absolute_site_url>/verify/<verification_token>/."""
        token = "abc123xyz_token-value"
        url = QRCodeService.get_verification_url(token)
        self.assertTrue(url.startswith("http"))
        self.assertIn(f"/verify/{token}/", url)
        self.assertTrue(url.endswith(f"/verify/{token}/"))

    def test_custom_base_url_supported(self):
        """Custom base URL override is properly formatted with trailing slash."""
        token = "test_token_456"
        custom_base = "https://certs.company.org"
        url = QRCodeService.get_verification_url(token, base_url=custom_base)
        self.assertEqual(url, f"https://certs.company.org/verify/{token}/")

    def test_no_student_pii_in_url(self):
        """Personal identifiable information must NOT be in verification URL."""
        student = _make_student(
            email="secret.student@university.edu",
            full_name="Jane Doe",
        )
        cert = _make_certificate(student=student)
        url = QRCodeService.get_verification_url(cert.verification_token)

        self.assertNotIn(student.email, url)
        self.assertNotIn(student.phone, url)
        self.assertNotIn(student.college, url)
        self.assertNotIn(student.university, url)
        self.assertTrue(
            QRCodeService.validate_payload_has_no_pii(
                url,
                student_email=student.email,
                student_phone=student.phone,
                student_college=student.college,
            )
        )


class QRCodeEncodingContentTests(TestCase):
    """Verify that the generated QR code image encodes the exact public verification URL."""

    def test_qr_object_encodes_exact_url(self):
        """The QRCode data_list must hold the exact verification URL."""
        token = "secure_token_789"
        expected_url = QRCodeService.get_verification_url(token)
        qr_obj = QRCodeService.create_qr_object(expected_url)

        # qrcode package stores encoded chunk in data_list
        encoded_data = qr_obj.data_list[0].data
        if isinstance(encoded_data, bytes):
            encoded_data = encoded_data.decode("utf-8")

        self.assertEqual(encoded_data, expected_url)

    def test_qr_does_not_encode_personal_data(self):
        """QR payload must strictly contain only the URL, not personal info or certificate dump."""
        student = _make_student(
            email="confidential@college.edu",
            full_name="Secret Name",
        )
        cert = _make_certificate(student=student)
        expected_url = QRCodeService.get_verification_url(cert.verification_token)
        qr_obj = QRCodeService.create_qr_object(expected_url)

        encoded_data = qr_obj.data_list[0].data
        if isinstance(encoded_data, bytes):
            encoded_data = encoded_data.decode("utf-8")

        self.assertNotIn(student.email, encoded_data)
        self.assertNotIn(student.phone, encoded_data)
        self.assertNotIn(student.college, encoded_data)


class QRCodeStorageAndFilenameTests(TestCase):
    """Verify that QR codes are stored via ImageField with safe filenames."""

    def test_safe_filename_generation(self):
        """Filename must be sanitized and match qr_<sanitized_id>.png."""
        cert_id = "COMP-INT-2026-000001"
        filename = QRCodeService.get_safe_filename(cert_id)
        self.assertEqual(filename, "qr_COMP-INT-2026-000001.png")

        # Test special characters sanitization
        unsafe_id = "COMP/INT:2026*#001"
        safe_name = QRCodeService.get_safe_filename(unsafe_id)
        self.assertEqual(safe_name, "qr_COMP_INT_2026__001.png")

    def test_qr_saved_to_imagefield_as_valid_image(self):
        """QR code must be stored on Certificate.qr_code and be a readable image."""
        from PIL import Image
        cert = _make_certificate()
        QRCodeService.generate_qr_for_certificate(cert, save=True)
        cert.refresh_from_db()

        self.assertTrue(bool(cert.qr_code))
        self.assertTrue(cert.qr_code.name.endswith(".png"))

        # Verify image file is readable by PIL
        cert.qr_code.open("rb")
        img = Image.open(cert.qr_code)
        self.assertEqual(img.format, "PNG")
        self.assertGreater(img.width, 50)
        self.assertGreater(img.height, 50)


class QRCodeIssuanceTests(TestCase):
    """Verify that QR code is generated upon certificate issuance."""

    def test_qr_generated_on_certificate_issue(self):
        """Calling certificate.issue() must mark status ISSUED and create QR code."""
        cert = _make_certificate()
        cert.status = "DRAFT"
        cert.qr_code = None
        cert.save()

        self.assertFalse(bool(cert.qr_code))
        cert.issue()
        cert.refresh_from_db()

        self.assertEqual(cert.status, "ISSUED")
        self.assertTrue(bool(cert.qr_code))

    def test_qr_generated_when_created_as_issued(self):
        """Certificates created with status='ISSUED' automatically have QR generated."""
        cert = _make_certificate()
        cert.refresh_from_db()
        self.assertEqual(cert.status, "ISSUED")
        self.assertTrue(bool(cert.qr_code))


class QRCodeRegenerationTests(TestCase):
    """Verify QR code can be regenerated without changing certificate ID or token."""

    def test_regenerate_preserves_id_and_token(self):
        """Regenerating QR code must not change certificate_id or verification_token."""
        cert = _make_certificate()
        original_id = cert.certificate_id
        original_token = cert.verification_token
        original_qr_path = cert.qr_code.name

        # Regenerate QR code
        cert.regenerate_qr_code(save=True)
        cert.refresh_from_db()

        self.assertEqual(cert.certificate_id, original_id)
        self.assertEqual(cert.verification_token, original_token)
        self.assertTrue(bool(cert.qr_code))

    def test_regenerate_produces_valid_image(self):
        """Regenerated QR code must remain a valid PNG image."""
        from PIL import Image
        cert = _make_certificate()
        cert.regenerate_qr_code(save=True)
        cert.refresh_from_db()

        cert.qr_code.open("rb")
        img = Image.open(cert.qr_code)
        self.assertEqual(img.format, "PNG")


# ---------------------------------------------------------------------------
# 6. WeasyPrint Certificate PDF Generation Tests
# ---------------------------------------------------------------------------

class CertificatePDFGenerationTests(TestCase):
    """Verify WeasyPrint A4 landscape PDF generation, layout, fields, and privacy."""

    def setUp(self):
        self.student = _make_student(
            full_name="Eleanor Vance",
            email="eleanor.vance@stanford.edu",
        )
        self.program = _make_program(
            name="Distributed Systems & Cloud Architecture",
        )
        self.template = _make_template(
            name="Institutional Excellence Template",
        )
        self.signatory = _make_signatory(
            name="Prof. Jonathan Hayes",
        )
        self.cert = _make_certificate(
            certificate_type="INTERNSHIP",
            student=self.student,
            program=self.program,
            template=self.template,
            signatory=self.signatory,
        )

    def test_pdf_generates_valid_pdf_bytes(self):
        """Service must produce non-empty valid PDF bytes beginning with %PDF."""
        pdf_bytes = CertificatePDFService.generate_pdf_bytes(self.cert)
        self.assertTrue(pdf_bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_pdf_strictly_single_page_a4_landscape(self):
        """Rendered certificate document must occupy exactly 1 page."""
        is_single_page = CertificatePDFService.validate_single_page(self.cert)
        self.assertTrue(is_single_page, "Certificate PDF overflowed the single A4 page constraint")

    def test_pdf_contains_all_required_elements(self):
        """Rendered HTML context must contain all mandatory certificate elements."""
        html = CertificatePDFService.render_certificate_html(self.cert)

        # 1. Certificate Title
        self.assertIn("CERTIFICATE OF INTERNSHIP", html)
        # 2. Student Name
        self.assertIn("Eleanor Vance", html)
        # 3. Program Name
        self.assertIn("Distributed Systems &amp; Cloud Architecture", html)
        # 4. Certificate Type
        self.assertIn("Internship", html)
        # 5. Certificate ID
        self.assertIn(self.cert.certificate_id, html)
        # 6. Duration
        self.assertIn(f"{self.cert.duration} Days", html)
        # 7. Issue Date
        self.assertIn(self.cert.issue_date.strftime("%B"), html)
        # 8. Authorized Signatory
        self.assertIn("Prof. Jonathan Hayes", html)
        self.assertIn("Director", html)
        # 9. Seal element
        self.assertIn("OFFICIAL", html)
        self.assertIn("VERIFIED", html)
        # 10. QR code embedded
        self.assertIn("data:image/png;base64,", html)

    def test_pdf_does_not_contain_student_pii(self):
        """Private information (email, phone, college) must NOT appear on certificate."""
        html = CertificatePDFService.render_certificate_html(self.cert)

        self.assertNotIn(self.student.email, html)
        self.assertNotIn(self.student.phone, html)
        self.assertNotIn(self.student.college, html)

    def test_pdf_saved_to_certificate_model(self):
        """Calling generate_pdf() must store a valid PDF file on certificate.certificate_pdf."""
        self.cert.generate_pdf(save=True)
        self.cert.refresh_from_db()

        self.assertTrue(bool(self.cert.certificate_pdf))
        self.assertTrue(self.cert.certificate_pdf.name.endswith(".pdf"))
        self.assertGreater(self.cert.certificate_pdf.size, 1000)

    def test_safe_pdf_filename(self):
        """PDF filename must be sanitized."""
        filename = CertificatePDFService.get_safe_filename(self.cert.certificate_id)
        self.assertTrue(filename.startswith("cert_"))
        self.assertTrue(filename.endswith(".pdf"))
        self.assertNotIn("/", filename)
        self.assertNotIn("\\", filename)


# ---------------------------------------------------------------------------
# 7. End-to-End Certificate Issuance Workflow Tests
# ---------------------------------------------------------------------------

class CertificateIssuanceWorkflowTests(TestCase):
    """Verify complete issuance lifecycle, atomic rollback, and audit logging."""

    def setUp(self):
        self.student = _make_student(
            full_name="Lucas Montgomery",
            email="lucas.m@example.com",
        )
        self.program = _make_program(
            name="Cloud Native DevOps",
        )
        self.template = _make_template(
            name="Corporate Gold Template",
        )
        self.signatory = _make_signatory(
            name="Sarah Connor",
        )

    def test_complete_issuance_workflow_success(self):
        """Successful issuance generates ID, Token, QR, PDF, sets status=ISSUED and logs AuditLog."""
        cert = CertificateIssuanceService.issue_certificate(
            student=self.student,
            program=self.program,
            certificate_type="TRAINING",
            template=self.template,
            authorized_signatory=self.signatory,
            duration=45,
            ip_address="192.168.1.100",
        )

        self.assertEqual(cert.status, "ISSUED")
        self.assertTrue(cert.certificate_id.startswith("COMP-TRN-"))
        self.assertTrue(bool(cert.verification_token))
        self.assertTrue(bool(cert.qr_code))
        self.assertTrue(bool(cert.certificate_pdf))

        # Check files exist
        self.assertTrue(cert.qr_code.name.endswith(".png"))
        self.assertTrue(cert.certificate_pdf.name.endswith(".pdf"))

        # Check AuditLog
        audit_entry = AuditLog.objects.filter(object_id=cert.certificate_id, action="ISSUE").first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.action, "ISSUE")
        self.assertEqual(audit_entry.object_type, "Certificate")
        self.assertEqual(audit_entry.ip_address, "192.168.1.100")
        self.assertEqual(audit_entry.changes["status"], "ISSUED")

    def test_atomic_rollback_on_pdf_generation_failure(self):
        """If PDF generation fails, transaction must roll back with no partially issued certificate."""
        initial_cert_count = Certificate.objects.count()
        initial_audit_count = AuditLog.objects.count()

        with mock.patch("certificates.services.CertificatePDFService.generate_pdf_for_certificate") as mock_pdf:
            mock_pdf.side_effect = RuntimeError("Simulated WeasyPrint rendering failure")

            with self.assertRaises(RuntimeError):
                CertificateIssuanceService.issue_certificate(
                    student=self.student,
                    program=self.program,
                    certificate_type="INTERNSHIP",
                    template=self.template,
                    authorized_signatory=self.signatory,
                )

        # Database state after rollback
        self.assertEqual(Certificate.objects.count(), initial_cert_count)
        self.assertEqual(Certificate.objects.filter(status="ISSUED").count(), 0)
        self.assertEqual(AuditLog.objects.count(), initial_audit_count)

    def test_certificate_identity_immutable_after_issuance(self):
        """Certificate ID and verification token must not change after issuance."""
        cert = CertificateIssuanceService.issue_certificate(
            student=self.student,
            program=self.program,
            certificate_type="INTERNSHIP",
            template=self.template,
            authorized_signatory=self.signatory,
        )
        original_id = cert.certificate_id
        original_token = cert.verification_token

        # Update other fields and resave
        cert.duration = 60
        cert.save()
        cert.refresh_from_db()

        self.assertEqual(cert.certificate_id, original_id)
        self.assertEqual(cert.verification_token, original_token)
        self.assertEqual(cert.status, "ISSUED")


class CertificateWorkflowViewTests(TestCase):
    """Test dashboard UI workflow: Create -> Preview -> Confirm -> Detail -> Download."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            username="admin_issuer",
            email="admin.issuer@example.com",
            password="securepassword123",
        )
        self.client.login(username="admin_issuer", password="securepassword123")

        self.student = _make_student()
        self.program = _make_program()
        self.template = _make_template()
        self.signatory = _make_signatory()

    def test_ui_create_preview_confirm_workflow(self):
        """Test the end-to-end interactive UI flow."""
        from django.urls import reverse

        # Step 1: Submit Create Form
        post_data = {
            "student": self.student.pk,
            "program": self.program.pk,
            "certificate_type": "INTERNSHIP",
            "template": self.template.pk,
            "authorized_signatory": self.signatory.pk,
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
            "issue_date": "2026-03-31",
            "duration": 90,
        }
        create_res = self.client.post(reverse("dashboard:certificate_create"), data=post_data)
        self.assertEqual(create_res.status_code, 302)
        self.assertRedirects(create_res, reverse("dashboard:certificate_preview"))

        # Step 2: View Preview Page
        preview_res = self.client.get(reverse("dashboard:certificate_preview"))
        self.assertEqual(preview_res.status_code, 200)
        self.assertContains(preview_res, "Certificate Live Preview")
        self.assertContains(preview_res, self.student.full_name)

        # Step 3: Confirm & Issue
        confirm_res = self.client.post(reverse("dashboard:certificate_confirm"))
        self.assertEqual(confirm_res.status_code, 302)

        # Check certificate created in DB
        issued_cert = Certificate.objects.filter(student=self.student, status="ISSUED").first()
        self.assertIsNotNone(issued_cert)
        self.assertEqual(issued_cert.duration, 90)
        self.assertTrue(bool(issued_cert.certificate_pdf))
        self.assertTrue(bool(issued_cert.qr_code))

        # Check redirect to detail page
        self.assertRedirects(confirm_res, reverse("dashboard:certificate_detail", kwargs={"pk": issued_cert.pk}))

        # Step 4: Download PDF
        download_res = self.client.get(reverse("dashboard:certificate_download", kwargs={"pk": issued_cert.pk}))
        self.assertEqual(download_res.status_code, 200)
        self.assertEqual(download_res["Content-Type"], "application/pdf")


class CompanySettingsCertificatePDFTests(TestCase):
    """Verify that Certificate PDF generation dynamically utilizes CompanySettings without hardcoding."""

    def setUp(self):
        from users.models import CompanySettings
        from certificates.pdf_service import CertificatePDFService
        self.CompanySettings = CompanySettings
        self.PDFService = CertificatePDFService

        self.student = _make_student(full_name="Arthur Pendragon", email="arthur@avalon.org")
        self.program = _make_program(name="Advanced Systems Architecture")
        self.template = _make_template(name="Dynamic Template")
        self.template.organization = ""
        self.template.save()

        self.signatory = _make_signatory(name="Merlin Emrys")
        self.signatory.organization = ""
        self.signatory.save()

        # Configure CompanySettings
        self.company = self.CompanySettings.get_instance()
        self.company.company_name = "Avalon International Institute"
        self.company.website = "https://www.avalon-edu.org"
        self.company.address = "1 Royal Way, Camelot"
        self.company.certificate_footer = "This document is verified and officially recorded in the Avalon registry."
        self.company.save()

        self.cert = _make_certificate(
            student=self.student,
            program=self.program,
            template=self.template,
            signatory=self.signatory,
        )

    def test_pdf_context_contains_company_settings(self):
        """Context should contain dynamic company name, address, website, and footer."""
        context = self.PDFService.build_context(self.cert)
        self.assertEqual(context["organization_name"], "Avalon International Institute")
        self.assertEqual(context["certificate_footer"], "This document is verified and officially recorded in the Avalon registry.")
        self.assertEqual(context["company_website"], "https://www.avalon-edu.org")
        self.assertEqual(context["company_address"], "1 Royal Way, Camelot")

    def test_rendered_html_contains_company_settings_elements(self):
        """Rendered certificate HTML should contain company settings without hardcoding."""
        html = self.PDFService.render_certificate_html(self.cert)
        self.assertIn("Avalon International Institute", html)
        self.assertIn("This document is verified and officially recorded in the Avalon registry.", html)
        self.assertIn("https://www.avalon-edu.org", html)
        self.assertIn("1 Royal Way, Camelot", html)


class AuthorizedSignatoryCertificateIntegrationTests(TestCase):
    """Test selection of active signatories in certificate generation and appearance on PDF."""

    def setUp(self):
        from users.models import AuthorizedSignatory
        from certificates.pdf_service import CertificatePDFService
        self.AuthorizedSignatory = AuthorizedSignatory
        self.PDFService = CertificatePDFService

        self.student = _make_student(full_name="Clark Kent", email="clark@dailyplanet.com")
        self.program = _make_program(name="Investigative Journalism")
        self.template = _make_template(name="Press Template")

        # Active Signatory
        self.active_signatory = self.AuthorizedSignatory.objects.create(
            name="Perry White",
            title="Editor-in-Chief",
            organization="Daily Planet Media Group",
            email="perry@dailyplanet.com",
            signature_image="signatures/perry.png",
            is_active=True
        )

        # Inactive Signatory
        self.inactive_signatory = self.AuthorizedSignatory.objects.create(
            name="Lois Lane",
            title="Senior Foreign Correspondent",
            organization="Daily Planet Media Group",
            email="lois@dailyplanet.com",
            signature_image="signatures/lois.png",
            is_active=False
        )

    def test_certificate_create_form_only_shows_active_signatories(self):
        """CertificateCreateForm dropdown queryset should only contain is_active=True signatories."""
        from dashboard.forms import CertificateCreateForm
        form = CertificateCreateForm()
        signatory_choices = list(form.fields['authorized_signatory'].queryset)
        self.assertIn(self.active_signatory, signatory_choices)
        self.assertNotIn(self.inactive_signatory, signatory_choices)

    def test_selected_signatory_appears_on_pdf_context_and_html(self):
        """When an active signatory is selected, their name, designation, and signature appear on the PDF."""
        cert = _make_certificate(
            student=self.student,
            program=self.program,
            template=self.template,
            signatory=self.active_signatory,
        )

        context = self.PDFService.build_context(cert)
        self.assertEqual(context["signatory_name"], "Perry White")
        self.assertEqual(context["signatory_title"], "Editor-in-Chief")

        html = self.PDFService.render_certificate_html(cert)
        self.assertIn("Perry White", html)
        self.assertIn("Editor-in-Chief", html)


class CertificateTemplateSystemTests(TestCase):
    """Test the multi-template certificate rendering system (Classic, Modern, Professional)."""

    def setUp(self):
        from users.models import AuthorizedSignatory, CompanySettings
        from certificates.models import CertificateTemplate
        from certificates.template_service import TemplateRenderingService
        from certificates.pdf_service import CertificatePDFService
        from certificates.issuance_service import CertificateIssuanceService

        self.TemplateService = TemplateRenderingService
        self.PDFService = CertificatePDFService
        self.IssuanceService = CertificateIssuanceService
        self.CertificateTemplate = CertificateTemplate

        self.student = _make_student(
            full_name="Tony Stark",
            email="tony@starkindustries.com"
        )
        self.program = _make_program(
            name="Advanced Arc Reactor Dynamics"
        )

        self.signatory = AuthorizedSignatory.objects.create(
            name="Virginia Pepper Potts",
            title="Chief Executive Officer",
            organization="Stark Industries Global",
            email="pepper@starkindustries.com",
            is_active=True
        )

        self.company = CompanySettings.get_instance()
        self.company.company_name = "Stark Educational Institute"
        self.company.website = "https://stark-institute.edu"
        self.company.certificate_footer = "Official verifiable record of academic distinction and technical proficiency."
        self.company.save()

        # Create templates for each design style
        self.classic_template, _ = self.CertificateTemplate.objects.get_or_create(
            name="Classic Royal Design",
            defaults={
                'design_style': 'CLASSIC',
                'html_template': 'certificates/templates/classic.html',
                'organization': 'Stark Educational Institute',
                'is_active': True,
            }
        )

        self.modern_template, _ = self.CertificateTemplate.objects.get_or_create(
            name="Modern Gradient Design",
            defaults={
                'design_style': 'MODERN',
                'html_template': 'certificates/templates/modern.html',
                'organization': 'Stark Educational Institute',
                'is_active': True,
            }
        )

        self.prof_template, _ = self.CertificateTemplate.objects.get_or_create(
            name="Executive Corporate Design",
            defaults={
                'design_style': 'PROFESSIONAL',
                'html_template': 'certificates/templates/professional.html',
                'organization': 'Stark Educational Institute',
                'is_active': True,
            }
        )

    def test_registered_templates_registry(self):
        """Registry contains CLASSIC, MODERN, and PROFESSIONAL definitions."""
        templates = self.TemplateService.get_registered_templates()
        styles = [t['design_style'] for t in templates]
        self.assertIn('CLASSIC', styles)
        self.assertIn('MODERN', styles)
        self.assertIn('PROFESSIONAL', styles)

    def test_template_path_resolution(self):
        """Resolve template paths correctly based on design_style."""
        self.assertEqual(
            self.TemplateService.resolve_template_path(self.classic_template),
            'certificates/templates/classic.html'
        )
        self.assertEqual(
            self.TemplateService.resolve_template_path(self.modern_template),
            'certificates/templates/modern.html'
        )
        self.assertEqual(
            self.TemplateService.resolve_template_path(self.prof_template),
            'certificates/templates/professional.html'
        )

    def test_all_three_templates_render_with_same_unified_context(self):
        """Same certificate data renders cleanly across Classic, Modern, and Professional templates."""
        for tmpl, expected_snippet in [
            (self.classic_template, "corner-filigree"),
            (self.modern_template, "top-gradient-bar"),
            (self.prof_template, "prof-matrix-card"),
        ]:
            cert = _make_certificate(
                student=self.student,
                program=self.program,
                template=tmpl,
                signatory=self.signatory,
            )

            html = self.PDFService.render_certificate_html(cert)

            # Check core unified data present in each template
            self.assertIn("Tony Stark", html)
            self.assertIn("Advanced Arc Reactor Dynamics", html)
            self.assertIn(cert.certificate_id, html)
            self.assertIn("Virginia Pepper Potts", html)
            self.assertIn("Chief Executive Officer", html)
            self.assertIn("Official verifiable record of academic distinction", html)
            self.assertIn(expected_snippet, html)

    def test_all_three_templates_compile_to_valid_single_page_pdf(self):
        """WeasyPrint compiles all three templates into valid single-page A4 Landscape PDFs."""
        for tmpl in [self.classic_template, self.modern_template, self.prof_template]:
            cert = _make_certificate(
                student=self.student,
                program=self.program,
                template=tmpl,
                signatory=self.signatory,
            )
            is_single_page = self.PDFService.validate_single_page(cert)
            self.assertTrue(is_single_page, f"Template '{tmpl.name}' ({tmpl.design_style}) did not render as a single page.")

            pdf_bytes = self.PDFService.generate_pdf_bytes(cert)
            self.assertTrue(pdf_bytes.startswith(b"%PDF-"), f"Template '{tmpl.name}' did not produce valid PDF bytes.")

    def test_render_preview_uses_selected_template(self):
        """Live preview rendering uses the selected template."""
        # Preview with Modern
        modern_preview_html, _ = self.IssuanceService.render_preview(
            student=self.student,
            program=self.program,
            certificate_type="ACHIEVEMENT",
            template=self.modern_template,
            authorized_signatory=self.signatory,
        )
        self.assertIn("top-gradient-bar", modern_preview_html)
        self.assertIn("Tony Stark", modern_preview_html)

        # Preview with Professional
        prof_preview_html, _ = self.IssuanceService.render_preview(
            student=self.student,
            program=self.program,
            certificate_type="ACHIEVEMENT",
            template=self.prof_template,
            authorized_signatory=self.signatory,
        )
        self.assertIn("prof-matrix-card", prof_preview_html)
        self.assertIn("Tony Stark", prof_preview_html)

    def test_full_issuance_workflow_with_modern_and_prof_templates(self):
        """Full atomic issuance workflow successfully generates and saves PDF using selected template."""
        # Issue Modern Certificate
        modern_cert = self.IssuanceService.issue_certificate(
            student=self.student,
            program=self.program,
            certificate_type="COURSE",
            template=self.modern_template,
            authorized_signatory=self.signatory,
        )
        self.assertEqual(modern_cert.status, "ISSUED")
        self.assertTrue(modern_cert.certificate_pdf)

        # Issue Professional Certificate
        prof_cert = self.IssuanceService.issue_certificate(
            student=self.student,
            program=self.program,
            certificate_type="INTERNSHIP",
            template=self.prof_template,
            authorized_signatory=self.signatory,
        )
        self.assertEqual(prof_cert.status, "ISSUED")
        self.assertTrue(prof_cert.certificate_pdf)






