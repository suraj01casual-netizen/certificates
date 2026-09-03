"""Centralized AuditLog Service for tracking system-wide lifecycle events.

Provides clean abstractions for logging student, program, and certificate
events (creation, updates, issuance, downloads, public verifications,
revocations, and regenerations) with automatic sensitive data sanitization.
"""

from __future__ import annotations

import datetime
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from users.models import AuditLog

logger = logging.getLogger(__name__)

SENSITIVE_KEY_PATTERNS = [
    "password",
    "secret",
    "token",
    "key",
    "auth",
    "credential",
    "private",
]


class AuditLogService:
    """Service providing sanitized audit logging across the platform."""

    @classmethod
    def sanitize_data(cls, data: Any) -> Any:
        """Recursively sanitize data structures, redacting sensitive keys and serializing objects."""
        if isinstance(data, dict):
            clean_dict = {}
            for k, v in data.items():
                k_str = str(k).lower()
                if any(p in k_str for p in SENSITIVE_KEY_PATTERNS) and "token" not in k_str.replace("verification_token", ""):
                    # Redact password/secret keys unless it's a verification token name identifier
                    if "password" in k_str or "secret" in k_str or "key" in k_str:
                        clean_dict[k] = "[REDACTED]"
                        continue
                clean_dict[k] = cls.sanitize_data(v)
            return clean_dict
        elif isinstance(data, (list, tuple, set)):
            return [cls.sanitize_data(item) for item in data]
        elif isinstance(data, (datetime.date, datetime.datetime, datetime.time)):
            return data.isoformat()
        elif isinstance(data, Decimal):
            return float(data)
        elif hasattr(data, "pk"):
            return str(data)
        return data

    @classmethod
    def extract_ip_address(cls, request: Optional[Any] = None, ip_address: Optional[str] = None) -> Optional[str]:
        """Resolve client IP address from request META or explicit parameter."""
        if ip_address:
            return ip_address
        if request and hasattr(request, "META"):
            x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
            if x_forwarded_for:
                return x_forwarded_for.split(",")[0].strip()
            return request.META.get("REMOTE_ADDR")
        return None

    @classmethod
    def extract_user_email(cls, user: Optional[Any] = None, user_email: Optional[str] = None) -> Optional[str]:
        """Resolve actor email from User object or explicit parameter."""
        if user_email:
            return user_email
        if user and getattr(user, "is_authenticated", False):
            return getattr(user, "email", None) or getattr(user, "username", None)
        return None

    @classmethod
    def log_event(
        cls,
        action: str,
        object_type: str,
        object_id: str,
        user: Optional[Any] = None,
        user_email: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        request: Optional[Any] = None,
    ) -> Optional[AuditLog]:
        """Record an audit log entry safely."""
        try:
            resolved_ip = cls.extract_ip_address(request=request, ip_address=ip_address)
            resolved_user = cls.extract_user_email(user=user, user_email=user_email)
            sanitized_changes = cls.sanitize_data(changes or {})

            return AuditLog.objects.create(
                action=action,
                object_type=object_type,
                object_id=str(object_id)[:255],
                user_email=resolved_user,
                changes=sanitized_changes,
                ip_address=resolved_ip,
            )
        except Exception as exc:
            logger.error("Failed to write AuditLog entry (%s, %s): %s", action, object_type, exc, exc_info=True)
            return None

    # -------------------------------------------------------------------------
    # Student Lifecycle Events
    # -------------------------------------------------------------------------
    @classmethod
    def log_student_created(cls, student: Any, user: Optional[Any] = None, request: Optional[Any] = None, ip_address: Optional[str] = None):
        return cls.log_event(
            action="CREATE",
            object_type="Student",
            object_id=student.student_id or str(student.pk),
            user=user,
            request=request,
            ip_address=ip_address,
            changes={
                "student_id": student.student_id,
                "full_name": student.full_name,
                "email": student.email,
                "college": student.college,
                "degree": student.degree,
            },
        )

    @classmethod
    def log_student_updated(cls, student: Any, changes: Optional[Dict[str, Any]] = None, user: Optional[Any] = None, request: Optional[Any] = None, ip_address: Optional[str] = None):
        return cls.log_event(
            action="UPDATE",
            object_type="Student",
            object_id=student.student_id or str(student.pk),
            user=user,
            request=request,
            ip_address=ip_address,
            changes=changes or {"student_name": student.full_name, "email": student.email},
        )

    @classmethod
    def log_student_deactivated(cls, student: Any, user: Optional[Any] = None, request: Optional[Any] = None, ip_address: Optional[str] = None):
        return cls.log_event(
            action="UPDATE",
            object_type="Student",
            object_id=student.student_id or str(student.pk),
            user=user,
            request=request,
            ip_address=ip_address,
            changes={"status": "DEACTIVATED", "student_name": student.full_name},
        )

    # -------------------------------------------------------------------------
    # Program Lifecycle Events
    # -------------------------------------------------------------------------
    @classmethod
    def log_program_created(cls, program: Any, user: Optional[Any] = None, request: Optional[Any] = None, ip_address: Optional[str] = None):
        return cls.log_event(
            action="CREATE",
            object_type="Program",
            object_id=program.program_id or str(program.pk),
            user=user,
            request=request,
            ip_address=ip_address,
            changes={
                "program_id": program.program_id,
                "name": program.name,
                "type": program.program_type,
                "duration": program.duration,
            },
        )

    @classmethod
    def log_program_updated(cls, program: Any, changes: Optional[Dict[str, Any]] = None, user: Optional[Any] = None, request: Optional[Any] = None, ip_address: Optional[str] = None):
        return cls.log_event(
            action="UPDATE",
            object_type="Program",
            object_id=program.program_id or str(program.pk),
            user=user,
            request=request,
            ip_address=ip_address,
            changes=changes or {"name": program.name, "type": program.program_type},
        )

    @classmethod
    def log_program_toggled(cls, program: Any, is_active: bool, user: Optional[Any] = None, request: Optional[Any] = None, ip_address: Optional[str] = None):
        return cls.log_event(
            action="UPDATE",
            object_type="Program",
            object_id=program.program_id or str(program.pk),
            user=user,
            request=request,
            ip_address=ip_address,
            changes={"is_active": is_active, "name": program.name},
        )

    # -------------------------------------------------------------------------
    # Certificate Lifecycle Events
    # -------------------------------------------------------------------------
    @classmethod
    def log_certificate_created(cls, certificate: Any, user: Optional[Any] = None, request: Optional[Any] = None, ip_address: Optional[str] = None):
        return cls.log_event(
            action="CREATE",
            object_type="Certificate",
            object_id=certificate.certificate_id,
            user=user,
            request=request,
            ip_address=ip_address,
            changes={
                "status": certificate.status,
                "certificate_id": certificate.certificate_id,
                "student_name": certificate.student.full_name if certificate.student else None,
                "program_name": certificate.program.name if certificate.program else None,
                "certificate_type": certificate.certificate_type,
            },
        )

    @classmethod
    def log_certificate_issued(cls, certificate: Any, user: Optional[Any] = None, request: Optional[Any] = None, ip_address: Optional[str] = None):
        return cls.log_event(
            action="ISSUE",
            object_type="Certificate",
            object_id=certificate.certificate_id,
            user=user,
            request=request,
            ip_address=ip_address,
            changes={
                "status": "ISSUED",
                "certificate_id": certificate.certificate_id,
                "student_name": certificate.student.full_name if certificate.student else None,
                "program_name": certificate.program.name if certificate.program else None,
                "certificate_type": certificate.certificate_type,
                "issue_date": str(certificate.issue_date),
            },
        )

    @classmethod
    def log_certificate_downloaded(
        cls,
        certificate: Any,
        user: Optional[Any] = None,
        request: Optional[Any] = None,
        ip_address: Optional[str] = None,
        source: str = "DASHBOARD",
    ):
        return cls.log_event(
            action="DOWNLOAD",
            object_type="Certificate",
            object_id=certificate.certificate_id,
            user=user,
            request=request,
            ip_address=ip_address,
            changes={
                "source": source,
                "certificate_id": certificate.certificate_id,
                "student_name": certificate.student.full_name if certificate.student else None,
                "program_name": certificate.program.name if certificate.program else None,
            },
        )

    @classmethod
    def log_certificate_verified(
        cls,
        certificate: Optional[Any] = None,
        token_or_id: Optional[str] = None,
        result: str = "VERIFIED",
        method: str = "TOKEN_LOOKUP",
        request: Optional[Any] = None,
        ip_address: Optional[str] = None,
    ):
        obj_id = certificate.certificate_id if certificate else (token_or_id or "UNKNOWN")
        student_name = certificate.student.full_name if certificate and certificate.student else None
        program_name = certificate.program.name if certificate and certificate.program else None

        return cls.log_event(
            action="VERIFY",
            object_type="Certificate",
            object_id=obj_id,
            request=request,
            ip_address=ip_address,
            changes={
                "result": result,
                "method": method,
                "student_name": student_name,
                "program_name": program_name,
            },
        )

    @classmethod
    def log_certificate_revoked(
        cls,
        certificate: Any,
        reason: str,
        user: Optional[Any] = None,
        request: Optional[Any] = None,
        ip_address: Optional[str] = None,
    ):
        return cls.log_event(
            action="REVOKE",
            object_type="Certificate",
            object_id=certificate.certificate_id,
            user=user,
            request=request,
            ip_address=ip_address,
            changes={
                "status": "REVOKED",
                "revocation_reason": reason,
                "certificate_id": certificate.certificate_id,
                "student_name": certificate.student.full_name if certificate.student else None,
            },
        )

    @classmethod
    def log_certificate_regenerated(
        cls,
        certificate: Any,
        user: Optional[Any] = None,
        request: Optional[Any] = None,
        ip_address: Optional[str] = None,
        reason: str = "PDF Recompiled",
    ):
        return cls.log_event(
            action="REGENERATE",
            object_type="Certificate",
            object_id=certificate.certificate_id,
            user=user,
            request=request,
            ip_address=ip_address,
            changes={
                "reason": reason,
                "certificate_id": certificate.certificate_id,
                "student_name": certificate.student.full_name if certificate.student else None,
                "program_name": certificate.program.name if certificate.program else None,
                "template": certificate.template.name if certificate.template else None,
            },
        )
