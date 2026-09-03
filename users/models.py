from django.db import models
from django.core.validators import FileExtensionValidator
import secrets


class Student(models.Model):
    """Student profile model."""
    student_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        blank=True,
        help_text="Unique student identifier"
    )
    full_name = models.CharField(max_length=255)
    email = models.EmailField(unique=True, db_index=True)
    phone = models.CharField(max_length=20)
    college = models.CharField(max_length=255)
    university = models.CharField(max_length=255)
    degree = models.CharField(max_length=100)
    branch = models.CharField(max_length=100)
    graduation_year = models.IntegerField()
    profile_photo = models.ImageField(
        upload_to='students/profiles/',
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png'])]
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student_id']),
            models.Index(fields=['email']),
            models.Index(fields=['is_active', '-created_at']),
        ]
        verbose_name_plural = "Students"

    def __str__(self):
        return f"{self.full_name} ({self.student_id})"

    def save(self, *args, **kwargs):
        if not self.student_id:
            from django.utils import timezone
            year = timezone.now().year
            prefix = f"STU-{year}-"
            last_student = Student.objects.filter(student_id__startswith=prefix).order_by('-student_id').first()
            if last_student:
                try:
                    last_num = int(last_student.student_id.split('-')[-1])
                    new_num = last_num + 1
                except (ValueError, IndexError):
                    new_num = 1
            else:
                new_num = 1
            self.student_id = f"{prefix}{new_num:06d}"
        super().save(*args, **kwargs)


class AuthorizedSignatory(models.Model):
    """Model for authorized signatories who can sign certificates."""
    name = models.CharField(max_length=255, verbose_name="Signatory Name")
    title = models.CharField(max_length=255, verbose_name="Designation", help_text="Official designation/title (e.g. Director, Dean)")
    organization = models.CharField(max_length=255, blank=True, help_text="Organization name (optional)")
    email = models.EmailField(blank=True)
    signature_image = models.ImageField(
        upload_to='signatures/',
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp', 'svg'])],
        help_text="Official signature image"
    )
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['organization']),
        ]
        verbose_name = "Authorized Signatory"
        verbose_name_plural = "Authorized Signatories"

    @property
    def designation(self):
        """Alias for title/designation."""
        return self.title

    @property
    def signature(self):
        """Alias for signature_image."""
        return self.signature_image

    @property
    def certificates_count(self):
        """Count of certificates attached to this signatory."""
        return self.signed_certificates.count()

    def can_delete(self):
        """Determine if this signatory can be safely deleted without breaking historical certificates."""
        return not self.signed_certificates.exists()

    def __str__(self):
        if self.organization:
            return f"{self.name} - {self.title} ({self.organization})"
        return f"{self.name} - {self.title}"


class AuditLog(models.Model):
    """Model for audit logging of system actions."""
    
    ACTION_CHOICES = [
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('ISSUE', 'Issue Certificate'),
        ('DOWNLOAD', 'Download Certificate'),
        ('VERIFY', 'Verify Certificate'),
        ('REVOKE', 'Revoke Certificate'),
        ('REGENERATE', 'Regenerate Certificate'),
        ('EMAIL', 'Send Email'),
        ('EXPORT', 'Export'),
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
    ]

    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    object_type = models.CharField(max_length=100, db_index=True)
    object_id = models.CharField(max_length=255, db_index=True)
    user_email = models.EmailField(null=True, blank=True, db_index=True)
    changes = models.JSONField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['object_type', 'object_id']),
            models.Index(fields=['user_email', '-timestamp']),
            models.Index(fields=['-timestamp']),
        ]
        verbose_name_plural = "Audit Logs"

    def __str__(self):
        return f"{self.action} - {self.object_type} - {self.timestamp}"


class CompanySettings(models.Model):
    """Singleton model for company-wide settings."""
    
    company_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Company Name",
        help_text="Official name of the issuing company or organization"
    )
    organization_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Organization Name",
        help_text="Organization name (legacy/alias)"
    )
    logo = models.ImageField(
        upload_to='company/',
        null=True,
        blank=True,
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'webp', 'svg'])],
        help_text="Company logo displayed on certificates and public portal"
    )
    email = models.EmailField(blank=True, help_text="Official contact email")
    phone = models.CharField(max_length=20, blank=True, help_text="Official contact phone number")
    address = models.TextField(blank=True, help_text="Company physical or registered address")
    website = models.URLField(null=True, blank=True, help_text="Official website URL")
    description = models.TextField(blank=True, help_text="Company description or mission statement")
    certificate_footer = models.TextField(
        blank=True,
        help_text="Custom footer notice or legal text displayed at the bottom of certificates"
    )
    theme_color = models.CharField(
        max_length=7,
        default='#2c3e50',
        help_text="Hex color code for theme"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Company Settings"

    @property
    def name(self):
        """Return the effective company or organization name."""
        return self.company_name or self.organization_name or "Certificate Platform"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Ensure only one instance exists and keep names in sync."""
        self.pk = 1
        if self.company_name and not self.organization_name:
            self.organization_name = self.company_name
        elif self.organization_name and not self.company_name:
            self.company_name = self.organization_name
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Prevent deletion of company settings."""
        pass

    @classmethod
    def get_instance(cls):
        """Get or create the singleton instance."""
        obj, created = cls.objects.get_or_create(pk=1)
        return obj
