"""Bulk Certificate, Student, and Enrollment Processing Service.

Provides robust CSV parsing, strict validation, zero-issuance on error,
pre-issuance preview data preparation, and transactional bulk issuance.
"""

from __future__ import annotations

import csv
import datetime
import io
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from certificates.models import Certificate, CertificateTemplate, Enrollment, Program
from users.models import AuditLog, AuthorizedSignatory, Student

logger = logging.getLogger(__name__)


@dataclass
class BulkRowError:
    """Represents a validation error for a specific row in the CSV."""
    row_number: int
    recipient: str
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "row_number": self.row_number,
            "recipient": self.recipient,
            "errors": self.errors,
        }


@dataclass
class BulkValidationResult:
    """Result of validating an entire CSV batch."""
    total_rows: int = 0
    valid_rows_count: int = 0
    invalid_rows_count: int = 0
    is_valid: bool = False
    header_errors: List[str] = field(default_factory=list)
    row_errors: List[BulkRowError] = field(default_factory=list)
    preview_rows: List[Dict[str, Any]] = field(default_factory=list)
    serialized_data: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.header_errors or self.row_errors or self.invalid_rows_count > 0)


@dataclass
class BulkExecutionResult:
    """Result of executing bulk certificate issuance."""
    success: bool
    total_requested: int
    issued_count: int
    failed_count: int = 0
    certificate_ids: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class BulkCertificateService:
    """Encapsulates CSV parsing, validation, and batch certificate generation."""

    REQUIRED_HEADER_GROUPS = {
        "full_name": ["full_name", "student_name", "name", "recipient_name", "student"],
        "email": ["email", "student_email", "mail", "email_address"],
        "program": ["program", "program_name", "program_id", "course", "course_name"],
        "start_date": ["start_date", "start", "from_date", "startdate"],
    }

    HEADER_ALIASES = {
        "full_name": ["full_name", "student_name", "name", "recipient_name", "student"],
        "email": ["email", "student_email", "mail", "email_address"],
        "program": ["program", "program_name", "program_id", "course", "course_name"],
        "certificate_type": ["certificate_type", "type", "cert_type"],
        "start_date": ["start_date", "start", "from_date", "startdate"],
        "end_date": ["end_date", "end", "to_date", "enddate", "completion_date"],
        "duration": ["duration", "days", "duration_days"],
        "issue_date": ["issue_date", "date_of_issue", "issued_on", "issuedate"],
        "template": ["template", "template_name", "template_id", "design_style"],
        "signatory": ["signatory", "signatory_name", "signatory_id", "authorized_signatory"],
        "phone": ["phone", "phone_number", "mobile", "contact"],
        "college": ["college", "college_name", "institution"],
        "university": ["university", "university_name"],
        "degree": ["degree", "degree_name"],
        "branch": ["branch", "department", "stream", "field_of_study"],
        "graduation_year": ["graduation_year", "grad_year", "batch", "passout_year"],
    }

    VALID_CERT_TYPES = {
        "INTERNSHIP": "INTERNSHIP",
        "COURSE": "COURSE",
        "WORKSHOP": "WORKSHOP",
        "ACHIEVEMENT": "ACHIEVEMENT",
        "TRAINING": "TRAINING",
    }

    @classmethod
    def get_sample_csv_content(cls) -> str:
        """Generate sample CSV data content."""
        sample_rows = [
            [
                "full_name",
                "email",
                "program",
                "certificate_type",
                "start_date",
                "end_date",
                "duration",
                "issue_date",
                "college",
                "university",
                "degree",
                "branch",
                "graduation_year",
                "phone",
            ],
            [
                "Ada Lovelace",
                "ada.lovelace@oxford.edu",
                "Quantum Computing Research Internship",
                "INTERNSHIP",
                "2026-01-01",
                "2026-03-31",
                "90",
                "2026-04-01",
                "Oxford University",
                "Oxford",
                "B.S.",
                "Computer Science",
                "2026",
                "+1-555-010-0001",
            ],
            [
                "Alan Turing",
                "alan.turing@cambridge.edu",
                "Applied Machine Learning Bootcamp",
                "TRAINING",
                "2026-02-01",
                "2026-03-02",
                "30",
                "2026-03-05",
                "King's College",
                "Cambridge",
                "M.S.",
                "Mathematics",
                "2025",
                "+1-555-010-0002",
            ],
        ]
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(sample_rows)
        return output.getvalue()

    @classmethod
    def parse_date(cls, val: Any) -> Optional[datetime.date]:
        """Attempt to parse date strings in various common formats."""
        if not val or not str(val).strip():
            return None
        val_str = str(val).strip()

        # Date format patterns
        formats = [
            "%Y-%m-%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%Y/%m/%d",
            "%d.%m.%Y",
            "%B %d, %Y",
            "%b %d, %Y",
        ]
        for fmt in formats:
            try:
                return datetime.datetime.strptime(val_str, fmt).date()
            except ValueError:
                continue
        return None

    @classmethod
    def map_headers(cls, raw_headers: List[str]) -> Tuple[Dict[str, int], List[str]]:
        """Map raw CSV header columns to standardized field keys."""
        col_mapping: Dict[str, int] = {}
        cleaned_headers = [str(h).strip().lower().replace(" ", "_") for h in raw_headers]

        for canonical_key, alias_list in cls.HEADER_ALIASES.items():
            for idx, raw_h in enumerate(cleaned_headers):
                if raw_h in alias_list and canonical_key not in col_mapping:
                    col_mapping[canonical_key] = idx
                    break

        # Check required headers
        missing_required = []
        for req_key, alias_list in cls.REQUIRED_HEADER_GROUPS.items():
            if req_key not in col_mapping:
                missing_required.append(f"'{req_key}' (accepted aliases: {', '.join(alias_list)})")

        return col_mapping, missing_required

    @classmethod
    def validate_csv(
        cls,
        csv_file_or_text: Any,
        default_template_id: Optional[int] = None,
        default_signatory_id: Optional[int] = None,
    ) -> BulkValidationResult:
        """Validate an uploaded CSV file or text payload before any issuance.

        Parameters
        ----------
        csv_file_or_text:
            UploadedFile, File, string, or bytes containing CSV text.
        default_template_id:
            Fallback default template ID if not specified per row.
        default_signatory_id:
            Fallback default signatory ID if not specified per row.

        Returns
        -------
        BulkValidationResult
            Validation metrics, row error lists, and preview rows.
        """
        result = BulkValidationResult()

        # 1. Read & Decode CSV content
        content = ""
        if hasattr(csv_file_or_text, "read"):
            raw_bytes = csv_file_or_text.read()
            if isinstance(raw_bytes, str):
                content = raw_bytes
            else:
                for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
                    try:
                        content = raw_bytes.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
        elif isinstance(csv_file_or_text, bytes):
            for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
                try:
                    content = csv_file_or_text.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
        else:
            content = str(csv_file_or_text)

        if not content.strip():
            result.header_errors.append("The uploaded CSV file is completely empty.")
            return result

        # 2. Parse CSV rows
        f = io.StringIO(content.strip())
        reader = csv.reader(f)
        try:
            raw_header = next(reader)
        except StopIteration:
            result.header_errors.append("The CSV file does not contain a header row.")
            return result

        col_mapping, missing_required = cls.map_headers(raw_header)
        if missing_required:
            result.header_errors.append(
                f"Missing required CSV column(s): {'; '.join(missing_required)}"
            )
            return result

        # Pre-fetch lookup caches for speed
        programs_by_name = {p.name.lower().strip(): p for p in Program.objects.filter(is_active=True)}
        programs_by_id = {p.program_id.lower().strip(): p for p in Program.objects.filter(is_active=True)}
        templates_by_name = {t.name.lower().strip(): t for t in CertificateTemplate.objects.filter(is_active=True)}
        templates_by_pk = {t.pk: t for t in CertificateTemplate.objects.filter(is_active=True)}
        signatories_by_name = {s.name.lower().strip(): s for s in AuthorizedSignatory.objects.filter(is_active=True)}
        signatories_by_pk = {s.pk: s for s in AuthorizedSignatory.objects.filter(is_active=True)}

        # Resolve fallback template and signatory
        fallback_template = (
            templates_by_pk.get(default_template_id)
            or CertificateTemplate.objects.filter(is_active=True).first()
        )
        fallback_signatory = (
            signatories_by_pk.get(default_signatory_id)
            or AuthorizedSignatory.objects.filter(is_active=True).first()
        )

        seen_csv_keys = set()
        row_number = 1  # Header was row 1

        for raw_row in reader:
            row_number += 1
            if not raw_row or not any(str(c).strip() for c in raw_row):
                # Skip empty lines
                continue

            result.total_rows += 1
            row_errors: List[str] = []

            # Extract fields from column mapping
            def get_val(key: str, default: str = "") -> str:
                idx = col_mapping.get(key)
                if idx is not None and idx < len(raw_row):
                    return str(raw_row[idx]).strip()
                return default

            full_name = get_val("full_name")
            email = get_val("email").lower()
            program_input = get_val("program")
            cert_type_input = get_val("certificate_type")
            start_date_input = get_val("start_date")
            end_date_input = get_val("end_date")
            duration_input = get_val("duration")
            issue_date_input = get_val("issue_date")
            template_input = get_val("template")
            signatory_input = get_val("signatory")
            phone = get_val("phone", "+1-555-000-0000")
            college = get_val("college", "University Department")
            university = get_val("university", "Accredited University")
            degree = get_val("degree", "Bachelor of Science")
            branch = get_val("branch", "Engineering & Applied Sciences")
            grad_year_input = get_val("graduation_year", str(timezone.now().year))

            # Validate Student Name
            if not full_name:
                row_errors.append("Student full name is required and cannot be empty.")

            # Validate Email
            if not email:
                row_errors.append("Email address is required.")
            else:
                try:
                    validate_email(email)
                except ValidationError:
                    row_errors.append(f"Invalid email address format: '{email}'.")

            # Validate Program
            matched_program = None
            if not program_input:
                row_errors.append("Program name or ID is required.")
            else:
                prog_clean = program_input.lower().strip()
                matched_program = (
                    programs_by_name.get(prog_clean)
                    or programs_by_id.get(prog_clean)
                )
                if not matched_program:
                    # Try partial case-insensitive search
                    matched_program = Program.objects.filter(
                        is_active=True, name__icontains=prog_clean
                    ).first()
                if not matched_program:
                    row_errors.append(f"Program '{program_input}' not found or is inactive.")

            # Validate Start Date
            start_date = cls.parse_date(start_date_input)
            if not start_date:
                row_errors.append(f"Invalid start date: '{start_date_input}'. Use format YYYY-MM-DD.")

            # Validate End Date & Duration
            end_date = cls.parse_date(end_date_input) if end_date_input else None
            duration = None
            if duration_input:
                try:
                    duration = int(float(duration_input))
                    if duration <= 0:
                        row_errors.append("Duration must be a positive integer.")
                except ValueError:
                    row_errors.append(f"Invalid duration: '{duration_input}'. Must be an integer number of days.")

            if start_date and end_date:
                if end_date < start_date:
                    row_errors.append(
                        f"End date ({end_date}) cannot be earlier than start date ({start_date})."
                    )
                if duration is None:
                    duration = max(1, (end_date - start_date).days)
            elif start_date and duration:
                end_date = start_date + datetime.timedelta(days=duration)
            elif start_date and matched_program:
                duration = matched_program.duration or 30
                end_date = start_date + datetime.timedelta(days=duration)
            elif start_date:
                duration = 30
                end_date = start_date + datetime.timedelta(days=30)

            # Validate Issue Date
            issue_date = cls.parse_date(issue_date_input) if issue_date_input else timezone.now().date()
            if issue_date_input and not issue_date:
                row_errors.append(f"Invalid issue date: '{issue_date_input}'. Use format YYYY-MM-DD.")

            # Validate Certificate Type
            cert_type = "INTERNSHIP"
            if cert_type_input:
                type_upper = cert_type_input.upper().strip()
                if type_upper in cls.VALID_CERT_TYPES:
                    cert_type = cls.VALID_CERT_TYPES[type_upper]
                else:
                    # Match by substring
                    for k in cls.VALID_CERT_TYPES:
                        if k in type_upper:
                            cert_type = k
                            break
                    else:
                        row_errors.append(
                            f"Invalid certificate type '{cert_type_input}'. Must be one of: {', '.join(cls.VALID_CERT_TYPES.keys())}."
                        )
            elif matched_program:
                cert_type = matched_program.program_type if matched_program.program_type in cls.VALID_CERT_TYPES else "INTERNSHIP"

            # Validate Template
            matched_template = fallback_template
            if template_input:
                tmpl_clean = template_input.lower().strip()
                matched_template = (
                    templates_by_name.get(tmpl_clean)
                    or CertificateTemplate.objects.filter(is_active=True, name__icontains=tmpl_clean).first()
                )
                if not matched_template:
                    row_errors.append(f"Certificate template '{template_input}' not found or is inactive.")
            if not matched_template:
                row_errors.append("No active certificate template available.")

            # Validate Signatory
            matched_signatory = fallback_signatory
            if signatory_input:
                sign_clean = signatory_input.lower().strip()
                matched_signatory = (
                    signatories_by_name.get(sign_clean)
                    or AuthorizedSignatory.objects.filter(is_active=True, name__icontains=sign_clean).first()
                )
                if not matched_signatory:
                    row_errors.append(f"Authorized signatory '{signatory_input}' not found or is inactive.")

            # Check graduation year
            grad_year = timezone.now().year
            if grad_year_input:
                try:
                    grad_year = int(float(grad_year_input))
                except ValueError:
                    grad_year = timezone.now().year

            # Check Duplicate within CSV batch
            if email and matched_program and start_date:
                csv_key = (email, matched_program.pk, str(start_date))
                if csv_key in seen_csv_keys:
                    row_errors.append(
                        f"Duplicate entry in CSV: recipient '{email}' already exists for program '{matched_program.name}' starting on {start_date}."
                    )
                else:
                    seen_csv_keys.add(csv_key)

            # Record row status
            if row_errors:
                result.invalid_rows_count += 1
                result.row_errors.append(
                    BulkRowError(
                        row_number=row_number,
                        recipient=full_name or email or f"Row {row_number}",
                        errors=row_errors,
                    )
                )
            else:
                result.valid_rows_count += 1

            # Prepare serialized row for preview and execution
            row_dict = {
                "row_number": row_number,
                "full_name": full_name,
                "email": email,
                "program_id": matched_program.pk if matched_program else None,
                "program_name": matched_program.name if matched_program else program_input,
                "certificate_type": cert_type,
                "start_date": str(start_date) if start_date else "",
                "end_date": str(end_date) if end_date else "",
                "duration": duration,
                "issue_date": str(issue_date) if issue_date else "",
                "template_id": matched_template.pk if matched_template else None,
                "template_name": matched_template.name if matched_template else "",
                "signatory_id": matched_signatory.pk if matched_signatory else None,
                "signatory_name": matched_signatory.name if matched_signatory else "",
                "phone": phone,
                "college": college,
                "university": university,
                "degree": degree,
                "branch": branch,
                "graduation_year": grad_year,
                "is_valid": len(row_errors) == 0,
                "errors": row_errors,
            }
            result.preview_rows.append(row_dict)
            if not row_errors:
                result.serialized_data.append(row_dict)

        result.is_valid = (
            result.total_rows > 0
            and result.invalid_rows_count == 0
            and len(result.header_errors) == 0
        )
        return result

    @classmethod
    def execute_bulk_issuance(
        cls,
        validated_rows: List[Dict[str, Any]],
        user: Optional[Any] = None,
        ip_address: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> BulkExecutionResult:
        """Execute transactional bulk certificate issuance for validated rows.

        Parameters
        ----------
        validated_rows:
            List of sanitized row dicts from validate_csv().
        user:
            Admin user performing the bulk action.
        ip_address:
            Client IP address.
        base_url:
            Base URL for verification link rendering.

        Returns
        -------
        BulkExecutionResult
            Summary of generated certificates.
        """
        from certificates.services import CertificateIssuanceService

        if not validated_rows:
            return BulkExecutionResult(
                success=False,
                total_requested=0,
                issued_count=0,
                errors=["No validated rows provided for certificate issuance."],
            )

        issued_certs: List[Certificate] = []
        errors: List[str] = []

        try:
            with transaction.atomic():
                for row in validated_rows:
                    email = row["email"].lower().strip()
                    full_name = row["full_name"].strip()

                    # 1. Get or create student
                    student, created = Student.objects.get_or_create(
                        email=email,
                        defaults={
                            "full_name": full_name,
                            "phone": row.get("phone") or "+1-555-000-0000",
                            "college": row.get("college") or "University Department",
                            "university": row.get("university") or "Accredited University",
                            "degree": row.get("degree") or "Bachelor of Science",
                            "branch": row.get("branch") or "Engineering & Applied Sciences",
                            "graduation_year": row.get("graduation_year") or timezone.now().year,
                            "is_active": True,
                        },
                    )
                    if not created and student.full_name != full_name:
                        # Update student full name if changed
                        student.full_name = full_name
                        student.save(update_fields=["full_name"])

                    # 2. Get Program
                    program = Program.objects.get(pk=row["program_id"])

                    # 3. Resolve Template & Signatory
                    template = CertificateTemplate.objects.get(pk=row["template_id"])
                    signatory = (
                        AuthorizedSignatory.objects.get(pk=row["signatory_id"])
                        if row.get("signatory_id")
                        else None
                    )

                    # 4. Parse dates
                    start_date = datetime.date.fromisoformat(row["start_date"])
                    end_date = (
                        datetime.date.fromisoformat(row["end_date"])
                        if row.get("end_date")
                        else None
                    )
                    issue_date = (
                        datetime.date.fromisoformat(row["issue_date"])
                        if row.get("issue_date")
                        else timezone.now().date()
                    )
                    duration = row.get("duration") or program.duration or 30

                    # 5. Get or create Enrollment
                    enrollment, _ = Enrollment.objects.get_or_create(
                        student=student,
                        program=program,
                        start_date=start_date,
                        defaults={
                            "end_date": end_date or (start_date + datetime.timedelta(days=duration)),
                            "duration": duration,
                            "mentor": program.mentor or "Academic Director",
                            "department": program.department or "Instruction",
                            "project_title": f"{program.name} Capstone Portfolio",
                            "project_description": f"Applied completion of {program.name} curriculum.",
                            "skills": program.skills,
                            "learning_outcomes": program.learning_outcomes,
                            "attendance_percentage": 95.0,
                            "performance_rating": 4.5,
                            "status": "COMPLETED",
                        },
                    )

                    # 6. Issue Certificate atomically via existing issuance service
                    cert = CertificateIssuanceService.issue_certificate(
                        student=student,
                        program=program,
                        certificate_type=row["certificate_type"],
                        template=template,
                        authorized_signatory=signatory,
                        issue_date=issue_date,
                        start_date=start_date,
                        end_date=end_date,
                        duration=duration,
                        enrollment=enrollment,
                        user=user,
                        ip_address=ip_address,
                        base_url=base_url,
                    )
                    issued_certs.append(cert)

                # Record bulk issuance in AuditLog
                user_email = (
                    getattr(user, "email", None)
                    if user and getattr(user, "is_authenticated", False)
                    else None
                )
                AuditLog.objects.create(
                    action="ISSUE",
                    object_type="BulkCertificateBatch",
                    object_id=f"BATCH-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                    user_email=user_email,
                    changes={
                        "total_issued": len(issued_certs),
                        "certificate_ids": [c.certificate_id for c in issued_certs],
                    },
                    ip_address=ip_address,
                )

            logger.info("Bulk certificate generation successful: %d certificates issued", len(issued_certs))
            return BulkExecutionResult(
                success=True,
                total_requested=len(validated_rows),
                issued_count=len(issued_certs),
                failed_count=0,
                certificate_ids=[c.certificate_id for c in issued_certs],
            )

        except Exception as exc:
            err_str = str(exc)
            logger.error("Bulk issuance failed in transaction: %s", err_str, exc_info=True)
            return BulkExecutionResult(
                success=False,
                total_requested=len(validated_rows),
                issued_count=0,
                failed_count=len(validated_rows),
                errors=[f"Transaction rolled back due to error: {err_str}"],
            )
