"""
Certificate identity generation service.

This module provides a reusable service for generating:
  - Certificate IDs in the format ``COMP-{PREFIX}-{YYYY}-{XXXXXX}``
  - Cryptographically secure verification tokens

Design principles
-----------------
* **Unique** – IDs and tokens are checked for collisions before being returned.
* **Readable** – Human-friendly, hyphen-separated format.
* **Database-safe** – Only ASCII alphanumeric characters and hyphens;
  no special characters that could break SQL or URL contexts.
* **Never based on exposed database IDs** – The public ``certificate_id``
  is decoupled from the internal auto-increment primary key.
* **Not predictable** – The numeric suffix is generated with
  ``secrets.randbelow`` (CSPRNG), not ``random.randint`` or timestamps.
"""

from __future__ import annotations

import secrets
from typing import Dict, Optional


from django.utils import timezone

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Prefix for every certificate ID.
CERTIFICATE_ID_PREFIX = "COMP"

#: Number of digits in the random numeric suffix.
RANDOM_SUFFIX_LENGTH = 6

#: Maximum collision-resolution attempts before raising.
MAX_ATTEMPTS = 10

#: Length (in bytes) of the raw random data used for the verification token.
#: ``secrets.token_urlsafe`` encodes each byte into ~1.3 characters, so
#: 32 bytes yields ~43 characters – well within the 255-char field limit.
VERIFICATION_TOKEN_BYTES = 32

#: Mapping of certificate type → short prefix used in the certificate ID.
CERTIFICATE_TYPE_PREFIXES: Dict[str, str] = {
    "INTERNSHIP": "INT",
    "COURSE": "COU",
    "WORKSHOP": "WRK",
    "ACHIEVEMENT": "ACH",
    "TRAINING": "TRN",
}


class CertificateService:
    """Reusable service for certificate identity generation.

    All methods are ``@staticmethod`` so the class can be used without
    instantiation, but an instance can also be created for convenience::

        service = CertificateService()
        cert_id = service.generate_certificate_id("INTERNSHIP")
        token  = service.generate_verification_token()
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def get_type_prefix(certificate_type: str) -> str:
        """Return the short prefix for a given certificate type.

        Parameters
        ----------
        certificate_type:
            One of the keys in :data:`CERTIFICATE_TYPE_PREFIXES`
            (e.g. ``"INTERNSHIP"``).

        Returns
        -------
        str
            The 3-letter prefix (e.g. ``"INT"``).

        Raises
        ------
        ValueError
            If *certificate_type* is not a recognised type.
        """
        try:
            return CERTIFICATE_TYPE_PREFIXES[certificate_type]
        except KeyError:
            valid = ", ".join(sorted(CERTIFICATE_TYPE_PREFIXES))
            raise ValueError(
                f"Unknown certificate type '{certificate_type}'. "
                f"Valid types: {valid}"
            ) from None

    @staticmethod
    def generate_random_suffix(length: int = RANDOM_SUFFIX_LENGTH) -> str:
        """Generate a cryptographically secure random numeric suffix.

        Uses :func:`secrets.randbelow` (CSPRNG) – **never**
        ``random.randint``.

        Parameters
        ----------
        length:
            Number of digits in the suffix (default 6).

        Returns
        -------
        str
            Zero-padded numeric string, e.g. ``"047291"``.
        """
        if length < 1:
            raise ValueError("length must be >= 1")
        # randbelow(10**length) gives 0 .. 10**length - 1
        value = secrets.randbelow(10 ** length)
        return str(value).zfill(length)

    @staticmethod
    def generate_verification_token() -> str:
        """Generate a cryptographically secure verification token.

        Uses :func:`secrets.token_urlsafe` which is backed by the OS
        CSPRNG (``/dev/urandom`` on POSIX, ``CryptGenRandom`` on Windows).

        Returns
        -------
        str
            URL-safe base64 token (≈ 43 characters for 32 bytes).
        """
        return secrets.token_urlsafe(VERIFICATION_TOKEN_BYTES)

    # ------------------------------------------------------------------
    # Certificate ID generation
    # ------------------------------------------------------------------

    @staticmethod
    def _format_certificate_id(
        prefix: str, year: int, suffix: str
    ) -> str:
        """Assemble the final certificate ID string."""
        return f"{CERTIFICATE_ID_PREFIX}-{prefix}-{year}-{suffix}"

    @staticmethod
    def _is_certificate_id_taken(
        certificate_id: str,
        exclude_pk: Optional[int] = None,
    ) -> bool:
        """Check whether *certificate_id* already exists in the database.

        Parameters
        ----------
        certificate_id:
            The candidate ID to check.
        exclude_pk:
            Primary key of the certificate being updated (so an existing
            certificate is not flagged as a collision with itself).
        """
        # Imported lazily to avoid circular imports at module load time.
        from certificates.models import Certificate

        qs = Certificate.objects.filter(certificate_id=certificate_id)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        return qs.exists()

    @staticmethod
    def _is_token_taken(
        token: str,
        exclude_pk: Optional[int] = None,
    ) -> bool:
        """Check whether *token* already exists in the database."""
        from certificates.models import Certificate

        qs = Certificate.objects.filter(verification_token=token)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        return qs.exists()

    @classmethod
    def generate_certificate_id(
        cls,
        certificate_type: str,
        year: Optional[int] = None,
        exclude_pk: Optional[int] = None,
    ) -> str:
        """Generate a unique, non-sequential certificate ID.

        The ID follows the format::

            COMP-{PREFIX}-{YYYY}-{XXXXXX}

        where ``{PREFIX}`` is derived from *certificate_type* and
        ``{XXXXXX}`` is a **cryptographically secure random** 6-digit
        number (not sequential, not based on the database PK).

        If a collision is detected (extremely unlikely with 6 digits of
        CSPRNG entropy), a new suffix is generated, up to
        :data:`MAX_ATTEMPTS` times.

        Parameters
        ----------
        certificate_type:
            Certificate type key, e.g. ``"INTERNSHIP"``.
        year:
            Year to embed in the ID.  Defaults to the current year
            (using Django's timezone-aware ``now()``).
        exclude_pk:
            Primary key of the certificate being updated, so it is not
            considered a collision with itself.

        Returns
        -------
        str
            A unique certificate ID, e.g. ``"COMP-INT-2026-047291"``.

        Raises
        ------
        ValueError
            If *certificate_type* is unknown.
        RuntimeError
            If a unique ID could not be generated within
            :data:`MAX_ATTEMPTS` attempts.
        """
        prefix = cls.get_type_prefix(certificate_type)

        if year is None:
            year = timezone.now().year

        for _ in range(MAX_ATTEMPTS):
            suffix = cls.generate_random_suffix()
            candidate = cls._format_certificate_id(prefix, year, suffix)
            if not cls._is_certificate_id_taken(candidate, exclude_pk):
                return candidate

        raise RuntimeError(
            f"Unable to generate a unique certificate ID for type "
            f"'{certificate_type}' after {MAX_ATTEMPTS} attempts."
        )

    @classmethod
    def generate_verification_token_unique(
        cls,
        exclude_pk: Optional[int] = None,
    ) -> str:
        """Generate a verification token that is guaranteed unique in DB.

        Wraps :meth:`generate_verification_token` with a collision check
        against existing certificates.

        Parameters
        ----------
        exclude_pk:
            Primary key of the certificate being updated.

        Returns
        -------
        str
            A unique, cryptographically secure verification token.

        Raises
        ------
        RuntimeError
            If a unique token could not be generated within
            :data:`MAX_ATTEMPTS` attempts.
        """
        for _ in range(MAX_ATTEMPTS):
            token = cls.generate_verification_token()
            if not cls._is_token_taken(token, exclude_pk):
                return token

        raise RuntimeError(
            f"Unable to generate a unique verification token after "
            f"{MAX_ATTEMPTS} attempts."
        )

    # ------------------------------------------------------------------
    # Convenience: generate both at once
    # ------------------------------------------------------------------

    @classmethod
    def generate_identity(
        cls,
        certificate_type: str,
        year: Optional[int] = None,
        exclude_pk: Optional[int] = None,
    ) -> tuple[str, str]:
        """Generate both a certificate ID and a verification token.

        Parameters
        ----------
        certificate_type:
            Certificate type key, e.g. ``"INTERNSHIP"``.
        year:
            Year to embed in the ID (defaults to current year).
        exclude_pk:
            Primary key of the certificate being updated.

        Returns
        -------
        tuple[str, str]
            ``(certificate_id, verification_token)``
        """
        cert_id = cls.generate_certificate_id(
            certificate_type, year=year, exclude_pk=exclude_pk
        )
        token = cls.generate_verification_token_unique(exclude_pk=exclude_pk)
        return cert_id, token


# Re-export services for convenience
from certificates.qr_service import QRCodeService  # noqa: E402
from certificates.pdf_service import CertificatePDFService  # noqa: E402
from certificates.template_service import TemplateRenderingService  # noqa: E402
from certificates.issuance_service import CertificateIssuanceService  # noqa: E402
from certificates.email_service import CertificateEmailService  # noqa: E402
from certificates.bulk_service import BulkCertificateService  # noqa: E402



