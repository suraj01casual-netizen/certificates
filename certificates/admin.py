from django.contrib import admin
from .models import Program, Enrollment, Certificate, CertificateTemplate


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ['name', 'program_id', 'program_type', 'mode', 'duration', 'is_active']
    list_filter = ['program_type', 'mode', 'is_active']
    search_fields = ['name', 'program_id', 'department']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('program_id', 'name', 'program_type', 'description')
        }),
        ('Program Details', {
            'fields': ('duration', 'mode', 'department', 'mentor')
        }),
        ('Content', {
            'fields': ('skills', 'learning_outcomes')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ['enrollment_id', 'student', 'program', 'start_date', 'status']
    list_filter = ['status', 'program', 'start_date']
    search_fields = ['enrollment_id', 'student__full_name', 'program__name']
    readonly_fields = ['enrollment_id', 'created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('enrollment_id', 'student', 'program', 'status')
        }),
        ('Duration', {
            'fields': ('start_date', 'end_date', 'duration')
        }),
        ('Details', {
            'fields': ('mentor', 'department', 'project_title', 'project_description')
        }),
        ('Performance', {
            'fields': ('skills', 'learning_outcomes', 'attendance_percentage', 'performance_rating')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CertificateTemplate)
class CertificateTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'is_active']
    list_filter = ['is_active', 'organization']
    search_fields = ['name', 'organization']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Certificate)
class CertificateAdmin(admin.ModelAdmin):
    list_display = ['certificate_id', 'student', 'program', 'status', 'issue_date']
    list_filter = ['status', 'certificate_type', 'issue_date']
    search_fields = ['certificate_id', 'verification_token', 'student__full_name']
    readonly_fields = ['created_at', 'updated_at', 'verification_token', 'qr_code_preview']
    fieldsets = (
        ('Certificate Information', {
            'fields': ('certificate_id', 'verification_token', 'certificate_type', 'status')
        }),
        ('Recipient', {
            'fields': ('student', 'program', 'enrollment')
        }),
        ('Dates', {
            'fields': ('issue_date', 'start_date', 'end_date', 'duration')
        }),
        ('Template & Signatory', {
            'fields': ('template', 'authorized_signatory')
        }),
        ('Files & QR Code', {
            'fields': ('certificate_pdf', 'qr_code', 'qr_code_preview')
        }),
        ('Revocation', {
            'fields': ('revoked_at', 'revocation_reason'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    date_hierarchy = 'issue_date'

    def qr_code_preview(self, obj):
        if obj.qr_code:
            from django.utils.html import format_html
            return format_html(
                '<img src="{}" width="150" height="150" style="object-fit: contain; border: 1px solid #ddd; padding: 4px; border-radius: 4px;" />',
                obj.qr_code.url
            )
        return "No QR Code generated yet"
    qr_code_preview.short_description = "QR Code Preview"

