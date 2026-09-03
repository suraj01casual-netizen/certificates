from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator, MaxValueValidator
from django.utils import timezone
from users.models import Student, AuthorizedSignatory


class Program(models.Model):
    """Program/Course/Internship model."""
    
    PROGRAM_TYPE_CHOICES = [
        ('INTERNSHIP', 'Internship'),
        ('TRAINING', 'Training'),
        ('WORKSHOP', 'Workshop'),
        ('INDUSTRIAL_TRAINING', 'Industrial Training'),
        ('CERTIFICATION_PROGRAM', 'Certification Program'),
    ]
    
    MODE_CHOICES = [
        ('ONLINE', 'Online'),
        ('OFFLINE', 'Offline'),
        ('HYBRID', 'Hybrid'),
    ]

    program_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        blank=True,
        help_text="Unique program identifier"
    )
    name = models.CharField(max_length=255, db_index=True)
    program_type = models.CharField(max_length=50, choices=PROGRAM_TYPE_CHOICES)
    description = models.TextField()
    duration = models.IntegerField(help_text="Duration in days")
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    department = models.CharField(max_length=255)
    skills = models.JSONField(default=list, help_text="List of skills covered")
    learning_outcomes = models.JSONField(default=list, help_text="List of learning outcomes")
    mentor = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['program_id']),
            models.Index(fields=['program_type', 'is_active']),
            models.Index(fields=['is_active', '-created_at']),
        ]

    def __str__(self):
        return f"{self.name} ({self.program_id})"

    def save(self, *args, **kwargs):
        if not self.program_id:
            from django.utils import timezone
            year = timezone.now().year
            prefix = f"PRG-{year}-"
            last_program = Program.objects.filter(program_id__startswith=prefix).order_by('-program_id').first()
            if last_program:
                try:
                    last_num = int(last_program.program_id.split('-')[-1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = 1
            else:
                new_num = 1
            self.program_id = f"{prefix}{new_num:06d}"
        super().save(*args, **kwargs)


class Enrollment(models.Model):
    """Enrollment/Internship record model."""
    
    STATUS_CHOICES = [
        ('ONGOING', 'Ongoing'),
        ('COMPLETED', 'Completed'),
        ('DROPPED', 'Dropped'),
        ('SUSPENDED', 'Suspended'),
    ]

    enrollment_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        blank=True,
        help_text="Unique enrollment identifier"
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name='enrollments'
    )
    program = models.ForeignKey(
        Program,
        on_delete=models.PROTECT,
        related_name='enrollments'
    )
    start_date = models.DateField(db_index=True)
    end_date = models.DateField()
    duration = models.IntegerField(help_text="Duration in days")
    mentor = models.CharField(max_length=255)
    department = models.CharField(max_length=255)
    project_title = models.CharField(max_length=255)
    project_description = models.TextField()
    skills = models.JSONField(default=list, help_text="Skills acquired")
    learning_outcomes = models.JSONField(default=list, help_text="Outcomes achieved")
    attendance_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    performance_rating = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Rating from 1-5"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ONGOING', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['student', 'program', 'start_date']
        indexes = [
            models.Index(fields=['enrollment_id']),
            models.Index(fields=['student', 'status']),
            models.Index(fields=['program', 'status']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"{self.student.full_name} - {self.program.name} ({self.enrollment_id})"

    def clean(self):
        super().clean()
        if self.start_date and self.end_date:
            if self.end_date < self.start_date:
                raise ValidationError({'end_date': "End date cannot be before the start date."})
            if self.duration is None or self.duration == 0:
                self.duration = (self.end_date - self.start_date).days

    def save(self, *args, **kwargs):
        if not self.enrollment_id:
            from django.utils import timezone
            year = timezone.now().year
            prefix = f"ENR-{year}-"
            last_enrollment = Enrollment.objects.filter(enrollment_id__startswith=prefix).order_by('-enrollment_id').first()
            if last_enrollment:
                try:
                    last_num = int(last_enrollment.enrollment_id.split('-')[-1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = 1
            else:
                new_num = 1
            self.enrollment_id = f"{prefix}{new_num:06d}"
        if self.start_date and self.end_date and (self.duration is None or self.duration == 0):
            self.duration = (self.end_date - self.start_date).days
        super().save(*args, **kwargs)


class CertificateTemplate(models.Model):
    """Certificate template model for customizable certificate designs."""
    
    DESIGN_STYLE_CHOICES = [
        ('CLASSIC', 'Classic Design (Traditional Ornate)'),
        ('MODERN', 'Modern Design (Minimalist Gradient)'),
        ('PROFESSIONAL', 'Professional Design (Corporate Executive)'),
    ]

    name = models.CharField(max_length=255, unique=True, db_index=True)
    design_style = models.CharField(
        max_length=30,
        choices=DESIGN_STYLE_CHOICES,
        default='CLASSIC',
        db_index=True,
        help_text="Design style layout for certificate rendering"
    )
    organization = models.CharField(max_length=255, blank=True, help_text="Organization name (optional)")
    description = models.TextField(blank=True)
    html_template = models.TextField(blank=True, default='', help_text="Custom template path or override (optional)")
    logo = models.ImageField(
        upload_to='templates/logos/',
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp', 'svg'])]
    )
    signature_image = models.ImageField(
        upload_to='templates/signatures/',
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp', 'svg'])]
    )
    colors = models.JSONField(default=dict, blank=True, help_text="Color configuration as JSON")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['design_style']),
            models.Index(fields=['organization']),
        ]

    @property
    def template_file(self) -> str:
        """Resolve the template file path corresponding to this template's design style."""
        if self.html_template and self.html_template.strip().endswith('.html'):
            return self.html_template.strip()
        
        style = (self.design_style or 'CLASSIC').upper()
        if style == 'MODERN':
            return 'certificates/templates/modern.html'
        elif style == 'PROFESSIONAL':
            return 'certificates/templates/professional.html'
        return 'certificates/templates/classic.html'

    def __str__(self):
        return f"{self.name} ({self.get_design_style_display()})"


class Certificate(models.Model):
    """Issued certificate model."""
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ISSUED', 'Issued'),
        ('REVOKED', 'Revoked'),
        ('EXPIRED', 'Expired'),
    ]
    
    CERTIFICATE_TYPE_CHOICES = [
        ('INTERNSHIP', 'Internship Certificate'),
        ('COURSE', 'Course Certificate'),
        ('WORKSHOP', 'Workshop Certificate'),
        ('ACHIEVEMENT', 'Achievement Certificate'),
    ]

    certificate_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique certificate identifier"
    )
    verification_token = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Cryptographic token for verification",
        editable=False
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        related_name='certificates'
    )
    program = models.ForeignKey(
        Program,
        on_delete=models.PROTECT,
        related_name='certificates'
    )
    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='certificates'
    )
    certificate_type = models.CharField(max_length=20, choices=CERTIFICATE_TYPE_CHOICES)
    issue_date = models.DateField(db_index=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    duration = models.IntegerField(help_text="Duration in days")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='DRAFT',
        db_index=True
    )
    template = models.ForeignKey(
        CertificateTemplate,
        on_delete=models.PROTECT,
        related_name='issued_certificates'
    )
    authorized_signatory = models.ForeignKey(
        AuthorizedSignatory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='signed_certificates'
    )
    certificate_pdf = models.FileField(
        upload_to='certificates/',
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])]
    )
    qr_code = models.ImageField(
        upload_to='certificates/qr_codes/',
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['png', 'jpg', 'jpeg'])],
        help_text="QR code image for certificate verification"
    )
    email_sent = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether delivery email has been sent to recipient"
    )
    email_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when delivery email was successfully sent"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['certificate_id']),
            models.Index(fields=['verification_token']),
            models.Index(fields=['student', 'status']),
            models.Index(fields=['program', 'status']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['issue_date', 'status']),
            models.Index(fields=['email_sent']),
        ]
        verbose_name_plural = "Certificates"

    def __str__(self):
        return f"Certificate {self.certificate_id} - {self.student.full_name}"

    def save(self, *args, **kwargs):
        """Generate certificate ID and verification token if not already set.

        Both fields are generated via :class:`CertificateService` so that:
        * ``certificate_id`` is unique, readable, database-safe, and never
          based on the exposed database PK.
        * ``verification_token`` uses a cryptographically secure RNG.

        Existing values are preserved – the ID/token are only generated
        once, on initial save.
        """
        from certificates.services import CertificateService

        if not self.certificate_id:
            self.certificate_id = CertificateService.generate_certificate_id(
                self.certificate_type, exclude_pk=self.pk
            )
        if not self.verification_token:
            self.verification_token = (
                CertificateService.generate_verification_token_unique(
                    exclude_pk=self.pk
                )
            )
        super().save(*args, **kwargs)

        # Generate QR code automatically after issuance if not already present
        if self.status == 'ISSUED' and not self.qr_code:
            from certificates.services import QRCodeService
            QRCodeService.generate_qr_for_certificate(self, save=True)

    def generate_qr_code(self, base_url=None, save=True):
        """Generate and save the QR code image for this certificate."""
        from certificates.services import QRCodeService
        return QRCodeService.generate_qr_for_certificate(self, base_url=base_url, save=save)

    def regenerate_qr_code(self, base_url=None, save=True):
        """Regenerate QR code without changing certificate ID or verification token."""
        from certificates.services import QRCodeService
        return QRCodeService.regenerate_qr_code(self, base_url=base_url, save=save)

    def generate_pdf(self, save=True, base_url=None):
        """Generate and store the PDF document for this certificate."""
        from certificates.services import CertificatePDFService
        return CertificatePDFService.generate_pdf_for_certificate(self, save=save, base_url=base_url)

    def issue(self, base_url=None):
        """Mark certificate as ISSUED and generate QR code."""
        self.status = 'ISSUED'
        if not self.issue_date:
            self.issue_date = timezone.now().date()
        self.save()
        if not self.qr_code:
            self.generate_qr_code(base_url=base_url, save=True)
        return self

    def revoke(self, reason: str, user=None, ip_address=None):
        """Revoke an issued certificate with a mandatory reason and log to AuditLog."""
        if self.status == 'REVOKED':
            raise ValueError("Certificate is already revoked.")
        if self.status != 'ISSUED':
            raise ValueError(f"Cannot revoke certificate with status '{self.status}'. Only ISSUED certificates can be revoked.")
        if not reason or not reason.strip():
            raise ValueError("Revocation reason is required.")

        original_id = self.certificate_id
        original_token = self.verification_token
        original_qr = self.qr_code.name if self.qr_code else None

        self.status = 'REVOKED'
        self.revoked_at = timezone.now()
        self.revocation_reason = reason.strip()
        self.save()

        # Invariant checks: ID, token, and QR code must remain identical
        assert self.certificate_id == original_id
        assert self.verification_token == original_token
        if original_qr:
            assert self.qr_code.name == original_qr

        # Record in AuditLog
        from users.models import AuditLog
        user_email = (
            getattr(user, 'email', None)
            if user and getattr(user, 'is_authenticated', False)
            else None
        )
        AuditLog.objects.create(
            action='REVOKE',
            object_type='Certificate',
            object_id=self.certificate_id,
            user_email=user_email,
            changes={
                'status': 'REVOKED',
                'revocation_reason': self.revocation_reason,
                'revoked_at': str(self.revoked_at),
                'student_name': self.student.full_name,
                'program_name': self.program.name,
            },
            ip_address=ip_address,
        )
        return self



