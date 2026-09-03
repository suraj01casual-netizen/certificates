from django.contrib import admin
from .models import Student, AuthorizedSignatory, AuditLog, CompanySettings


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'student_id', 'email', 'college', 'graduation_year', 'is_active']
    list_filter = ['is_active', 'graduation_year', 'college']
    search_fields = ['full_name', 'student_id', 'email']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('student_id', 'full_name', 'email', 'phone')
        }),
        ('Education Details', {
            'fields': ('college', 'university', 'degree', 'branch', 'graduation_year')
        }),
        ('Profile', {
            'fields': ('profile_photo', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AuthorizedSignatory)
class AuthorizedSignatoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'title', 'organization', 'email', 'is_active', 'created_at']
    list_filter = ['is_active', 'organization']
    search_fields = ['name', 'title', 'email', 'organization']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Signatory Details', {
            'fields': ('name', 'title', 'organization', 'email', 'is_active')
        }),
        ('Signature', {
            'fields': ('signature_image',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'object_type', 'object_id', 'user_email', 'timestamp']
    list_filter = ['action', 'object_type', 'timestamp']
    search_fields = ['object_type', 'object_id', 'user_email']
    readonly_fields = ['timestamp', 'action', 'object_type', 'object_id', 'user_email', 'changes', 'ip_address']
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CompanySettings)
class CompanySettingsAdmin(admin.ModelAdmin):
    readonly_fields = ['updated_at']
    fieldsets = (
        ('Company & Organization', {
            'fields': ('company_name', 'organization_name', 'logo', 'description', 'website')
        }),
        ('Contact Information', {
            'fields': ('email', 'phone', 'address')
        }),
        ('Certificate Settings & Appearance', {
            'fields': ('certificate_footer', 'theme_color')
        }),
        ('Timestamps', {
            'fields': ('updated_at',),
            'classes': ('collapse',)
        }),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
