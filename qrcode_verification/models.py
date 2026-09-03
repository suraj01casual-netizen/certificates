from django.db import models
from certificates.models import Certificate


class VerificationEvent(models.Model):
    """Model for tracking certificate verification events."""
    
    VERIFICATION_METHOD_CHOICES = [
        ('QR_SCAN', 'QR Code Scan'),
        ('SEARCH', 'Database Search'),
        ('API', 'API Call'),
        ('MANUAL', 'Manual Verification'),
    ]

    certificate = models.ForeignKey(
        Certificate,
        on_delete=models.CASCADE,
        related_name='verification_events'
    )
    verified_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, null=True, blank=True)
    verification_method = models.CharField(
        max_length=20,
        choices=VERIFICATION_METHOD_CHOICES,
        default='MANUAL'
    )

    class Meta:
        ordering = ['-verified_at']
        indexes = [
            models.Index(fields=['certificate', '-verified_at']),
            models.Index(fields=['verification_method', '-verified_at']),
            models.Index(fields=['-verified_at']),
        ]
        verbose_name_plural = "Verification Events"

    def __str__(self):
        return f"Verification of {self.certificate.certificate_id} - {self.verified_at}"
