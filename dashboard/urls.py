from django.urls import path
from dashboard.views import (
    StudentListView,
    StudentDetailView,
    StudentCreateView,
    StudentUpdateView,
    StudentDeactivateView,
    ProgramListView,
    ProgramDetailView,
    ProgramCreateView,
    ProgramUpdateView,
    ProgramToggleActiveView,
    EnrollmentListView,
    EnrollmentDetailView,
    EnrollmentCreateView,
    EnrollmentUpdateView,
    CertificateListView,
    CertificateDetailView,
    CertificateCreateWorkflowView,
    CertificatePreviewView,
    CertificateConfirmIssueView,
    CertificateDownloadView,
    CertificateIssueDraftView,
    CertificateRevokeView,
    CertificateResendEmailView,
    CertificateRegeneratePdfView,
    CertificateHtmlPreviewView,
    CertificateTemplateGalleryView,
    BulkCertificateUploadView,
    BulkCertificateValidateView,
    BulkCertificatePreviewView,
    BulkCertificateConfirmView,
    BulkCertificateSampleCsvView,
    CompanySettingsView,
    SignatoryListView,
    SignatoryCreateView,
    SignatoryUpdateView,
    SignatoryToggleActiveView,
    SignatoryDeleteView,
    AuditLogListView,
)

app_name = 'dashboard'

urlpatterns = [
    path('', StudentListView.as_view(), name='student_list'),
    path('student/add/', StudentCreateView.as_view(), name='student_add'),
    path('student/<int:pk>/', StudentDetailView.as_view(), name='student_detail'),
    path('student/<int:pk>/edit/', StudentUpdateView.as_view(), name='student_edit'),
    path('student/<int:pk>/deactivate/', StudentDeactivateView.as_view(), name='student_deactivate'),
    
    path('programs/', ProgramListView.as_view(), name='program_list'),
    path('program/add/', ProgramCreateView.as_view(), name='program_add'),
    path('program/<int:pk>/', ProgramDetailView.as_view(), name='program_detail'),
    path('program/<int:pk>/edit/', ProgramUpdateView.as_view(), name='program_edit'),
    path('program/<int:pk>/toggle-active/', ProgramToggleActiveView.as_view(), name='program_toggle_active'),
    
    path('enrollments/', EnrollmentListView.as_view(), name='enrollment_list'),
    path('enrollment/add/', EnrollmentCreateView.as_view(), name='enrollment_add'),
    path('enrollment/<int:pk>/', EnrollmentDetailView.as_view(), name='enrollment_detail'),
    path('enrollment/<int:pk>/edit/', EnrollmentUpdateView.as_view(), name='enrollment_edit'),

    # Authorized Signatory Routes
    path('signatories/', SignatoryListView.as_view(), name='signatory_list'),
    path('signatory/add/', SignatoryCreateView.as_view(), name='signatory_add'),
    path('signatory/<int:pk>/edit/', SignatoryUpdateView.as_view(), name='signatory_edit'),
    path('signatory/<int:pk>/toggle-active/', SignatoryToggleActiveView.as_view(), name='signatory_toggle_active'),
    path('signatory/<int:pk>/delete/', SignatoryDeleteView.as_view(), name='signatory_delete'),

    # Certificate Issuance Workflow Routes
    path('certificates/', CertificateListView.as_view(), name='certificate_list'),
    path('certificates/bulk/', BulkCertificateUploadView.as_view(), name='certificate_bulk_upload'),
    path('certificates/bulk/validate/', BulkCertificateValidateView.as_view(), name='certificate_bulk_validate'),
    path('certificates/bulk/preview/', BulkCertificatePreviewView.as_view(), name='certificate_bulk_preview'),
    path('certificates/bulk/confirm/', BulkCertificateConfirmView.as_view(), name='certificate_bulk_confirm'),
    path('certificates/bulk/sample-csv/', BulkCertificateSampleCsvView.as_view(), name='certificate_bulk_sample_csv'),
    path('certificate/create/', CertificateCreateWorkflowView.as_view(), name='certificate_create'),
    path('certificate/preview/', CertificatePreviewView.as_view(), name='certificate_preview'),
    path('certificate/confirm/', CertificateConfirmIssueView.as_view(), name='certificate_confirm'),
    path('certificate/<int:pk>/', CertificateDetailView.as_view(), name='certificate_detail'),
    path('certificate/<int:pk>/download/', CertificateDownloadView.as_view(), name='certificate_download'),
    path('certificate/<int:pk>/issue/', CertificateIssueDraftView.as_view(), name='certificate_issue_draft'),
    path('certificate/<int:pk>/revoke/', CertificateRevokeView.as_view(), name='certificate_revoke'),
    path('certificate/<int:pk>/resend-email/', CertificateResendEmailView.as_view(), name='certificate_resend_email'),
    path('certificate/<int:pk>/regenerate/', CertificateRegeneratePdfView.as_view(), name='certificate_regenerate_pdf'),
    path('certificate/<int:pk>/html-preview/', CertificateHtmlPreviewView.as_view(), name='certificate_html_preview'),
    path('certificates/templates/', CertificateTemplateGalleryView.as_view(), name='certificate_templates'),

    # Company Settings Route
    path('settings/', CompanySettingsView.as_view(), name='company_settings'),

    # Audit Logs Route
    path('audit-logs/', AuditLogListView.as_view(), name='audit_log_list'),
]
