from django.contrib import admin
from .models import VerificationEvent


@admin.register(VerificationEvent)
class VerificationEventAdmin(admin.ModelAdmin):
    list_display = ['certificate', 'verified_at', 'verification_method', 'ip_address']
    list_filter = ['verification_method', 'verified_at']
    search_fields = ['certificate__certificate_id', 'ip_address']
    readonly_fields = ['certificate', 'verified_at', 'ip_address', 'user_agent', 'verification_method']
    date_hierarchy = 'verified_at'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
