from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_sameorigin

from users.models import Student, AuthorizedSignatory, AuditLog, CompanySettings
from users.audit_service import AuditLogService
from certificates.models import Program, Enrollment, Certificate, CertificateTemplate
from certificates.services import (
    CertificateIssuanceService,
    CertificatePDFService,
    QRCodeService,
    BulkCertificateService,
)
from dashboard.forms import (
    StudentForm,
    ProgramForm,
    EnrollmentForm,
    CertificateCreateForm,
    CompanySettingsForm,
    AuthorizedSignatoryForm,
    BulkCertificateUploadForm,
)

class StudentListView(LoginRequiredMixin, ListView):
    model = Student
    template_name = 'dashboard/student_list.html'
    context_object_name = 'students'
    paginate_by = 5

    def get_queryset(self):
        queryset = Student.objects.all().order_by('-created_at')
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(student_id__icontains=q) |
                Q(full_name__icontains=q) |
                Q(email__icontains=q) |
                Q(phone__icontains=q) |
                Q(college__icontains=q)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '').strip()
        return context

class StudentDetailView(LoginRequiredMixin, DetailView):
    model = Student
    template_name = 'dashboard/student_detail.html'
    context_object_name = 'student'

class StudentCreateView(LoginRequiredMixin, CreateView):
    model = Student
    form_class = StudentForm
    template_name = 'dashboard/student_form.html'
    
    def get_success_url(self):
        return reverse_lazy('dashboard:student_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditLogService.log_student_created(
            self.object,
            user=self.request.user,
            request=self.request,
        )
        messages.success(self.request, f"Student {self.object.full_name} has been successfully added with ID {self.object.student_id}.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Add New Student"
        context['action'] = "Add Student"
        return context

class StudentUpdateView(LoginRequiredMixin, UpdateView):
    model = Student
    form_class = StudentForm
    template_name = 'dashboard/student_form.html'

    def get_success_url(self):
        return reverse_lazy('dashboard:student_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditLogService.log_student_updated(
            self.object,
            changes={"full_name": self.object.full_name, "email": self.object.email},
            user=self.request.user,
            request=self.request,
        )
        messages.success(self.request, f"Student {self.object.full_name}'s details have been successfully updated.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Edit Student: {self.object.full_name}"
        context['action'] = "Save Changes"
        return context

class StudentDeactivateView(LoginRequiredMixin, View):
    def get(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        return render(request, 'dashboard/student_deactivate_confirm.html', {'student': student})

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        student.is_active = False
        student.save()
        AuditLogService.log_student_deactivated(
            student,
            user=request.user,
            request=request,
        )
        messages.success(request, f"Student {student.full_name} has been successfully deactivated.")
        return redirect('dashboard:student_list')


class ProgramListView(LoginRequiredMixin, ListView):
    model = Program
    template_name = 'dashboard/program_list.html'
    context_object_name = 'programs'
    paginate_by = 5

    def get_queryset(self):
        queryset = Program.objects.all().order_by('-created_at')
        
        # Search
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(program_id__icontains=q) |
                Q(name__icontains=q) |
                Q(department__icontains=q) |
                Q(mentor__icontains=q) |
                Q(description__icontains=q)
            )
            
        # Filter by program type
        program_type = self.request.GET.get('program_type', '').strip()
        if program_type:
            queryset = queryset.filter(program_type=program_type)
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '').strip()
        context['program_type'] = self.request.GET.get('program_type', '').strip()
        context['program_types'] = Program.PROGRAM_TYPE_CHOICES
        return context

class ProgramDetailView(LoginRequiredMixin, DetailView):
    model = Program
    template_name = 'dashboard/program_detail.html'
    context_object_name = 'program'

class ProgramCreateView(LoginRequiredMixin, CreateView):
    model = Program
    form_class = ProgramForm
    template_name = 'dashboard/program_form.html'

    def get_success_url(self):
        return reverse_lazy('dashboard:program_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditLogService.log_program_created(
            self.object,
            user=self.request.user,
            request=self.request,
        )
        messages.success(self.request, f"Program '{self.object.name}' has been successfully created with ID {self.object.program_id}.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Add New Program"
        context['action'] = "Create Program"
        return context

class ProgramUpdateView(LoginRequiredMixin, UpdateView):
    model = Program
    form_class = ProgramForm
    template_name = 'dashboard/program_form.html'

    def get_success_url(self):
        return reverse_lazy('dashboard:program_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        AuditLogService.log_program_updated(
            self.object,
            changes={"name": self.object.name, "type": self.object.program_type},
            user=self.request.user,
            request=self.request,
        )
        messages.success(self.request, f"Program '{self.object.name}' has been successfully updated.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Edit Program: {self.object.name}"
        context['action'] = "Save Changes"
        return context

class ProgramToggleActiveView(LoginRequiredMixin, View):
    def get(self, request, pk):
        program = get_object_or_404(Program, pk=pk)
        return render(request, 'dashboard/program_toggle_confirm.html', {'program': program})

    def post(self, request, pk):
        program = get_object_or_404(Program, pk=pk)
        program.is_active = not program.is_active
        program.save()
        status_str = "activated" if program.is_active else "deactivated"
        AuditLogService.log_program_toggled(
            program,
            is_active=program.is_active,
            user=request.user,
            request=request,
        )
        messages.success(request, f"Program '{program.name}' has been successfully {status_str}.")
        return redirect('dashboard:program_detail', pk=program.pk)


class EnrollmentListView(LoginRequiredMixin, ListView):
    model = Enrollment
    template_name = 'dashboard/enrollment_list.html'
    context_object_name = 'enrollments'
    paginate_by = 5

    def get_queryset(self):
        queryset = Enrollment.objects.all().order_by('-created_at')
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(enrollment_id__icontains=q) |
                Q(student__full_name__icontains=q) |
                Q(student__email__icontains=q) |
                Q(program__name__icontains=q) |
                Q(project_title__icontains=q)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '').strip()
        return context

class EnrollmentDetailView(LoginRequiredMixin, DetailView):
    model = Enrollment
    template_name = 'dashboard/enrollment_detail.html'
    context_object_name = 'enrollment'

class EnrollmentCreateView(LoginRequiredMixin, CreateView):
    model = Enrollment
    form_class = EnrollmentForm
    template_name = 'dashboard/enrollment_form.html'

    def get_success_url(self):
        return reverse_lazy('dashboard:enrollment_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Enrollment {self.object.enrollment_id} has been successfully created for {self.object.student.full_name}.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = "Add New Enrollment"
        context['action'] = "Create Enrollment"
        return context

class EnrollmentUpdateView(LoginRequiredMixin, UpdateView):
    model = Enrollment
    form_class = EnrollmentForm
    template_name = 'dashboard/enrollment_form.html'

    def get_success_url(self):
        return reverse_lazy('dashboard:enrollment_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Enrollment {self.object.enrollment_id} has been successfully updated.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['title'] = f"Edit Enrollment: {self.object.enrollment_id}"
        context['action'] = "Save Changes"
        return context


# ===========================================================================
# Certificate Issuance Workflow Views
# ===========================================================================

class CertificateListView(LoginRequiredMixin, ListView):
    """Directory listing of all generated and issued certificates with rich multi-parameter filtering."""
    model = Certificate
    template_name = 'dashboard/certificate_list.html'
    context_object_name = 'certificates'
    paginate_by = 10

    def get_queryset(self):
        queryset = Certificate.objects.all().select_related('student', 'program', 'template', 'authorized_signatory').order_by('-created_at')

        # 1. Search Query (Certificate ID, Student Name, Email, Program)
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(certificate_id__icontains=q) |
                Q(student__full_name__icontains=q) |
                Q(student__email__icontains=q) |
                Q(program__name__icontains=q)
            )

        # 2. Filter by Status
        status = self.request.GET.get('status', '').strip()
        if status:
            queryset = queryset.filter(status=status)

        # 3. Filter by Program
        program_id = self.request.GET.get('program', '').strip()
        if program_id:
            queryset = queryset.filter(program_id=program_id)

        # 4. Filter by Certificate Type
        certificate_type = self.request.GET.get('certificate_type', '').strip()
        if certificate_type:
            queryset = queryset.filter(certificate_type=certificate_type)

        # 5. Filter by Issue Date
        issue_date = self.request.GET.get('issue_date', '').strip()
        if issue_date:
            try:
                queryset = queryset.filter(issue_date=issue_date)
            except Exception:
                pass

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '').strip()
        context['status_selected'] = self.request.GET.get('status', '').strip()
        context['program_selected'] = self.request.GET.get('program', '').strip()
        context['certificate_type_selected'] = self.request.GET.get('certificate_type', '').strip()
        context['issue_date_selected'] = self.request.GET.get('issue_date', '').strip()

        # Choices for filter dropdowns
        context['statuses'] = Certificate.STATUS_CHOICES
        context['certificate_types'] = Certificate.CERTIFICATE_TYPE_CHOICES
        context['programs'] = Program.objects.all().order_by('name')

        # Summary statistics
        context['total_count'] = Certificate.objects.count()
        context['issued_count'] = Certificate.objects.filter(status='ISSUED').count()
        context['draft_count'] = Certificate.objects.filter(status='DRAFT').count()
        context['revoked_count'] = Certificate.objects.filter(status='REVOKED').count()

        # Query string for pagination preservation
        params = self.request.GET.copy()
        if 'page' in params:
            params.pop('page')
        context['query_params'] = params.urlencode()
        return context


class CertificateDetailView(LoginRequiredMixin, DetailView):
    """Detailed view for a specific certificate record with preview, verification link, and actions."""
    model = Certificate
    template_name = 'dashboard/certificate_detail.html'
    context_object_name = 'certificate'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.urls import reverse
        context['verification_url'] = self.request.build_absolute_uri(
            reverse('verify:verify_token', kwargs={'token': self.object.verification_token})
        )
        return context


class CertificateCreateWorkflowView(LoginRequiredMixin, View):
    """Step 1: Form to select recipient, program, dates, and template."""
    def get(self, request):
        initial = {}
        enrollment_id = request.GET.get('enrollment')
        if enrollment_id:
            try:
                enrollment = Enrollment.objects.get(pk=enrollment_id)
                initial = {
                    'student': enrollment.student,
                    'program': enrollment.program,
                    'enrollment': enrollment,
                    'certificate_type': enrollment.program.program_type if enrollment.program.program_type in ['INTERNSHIP', 'COURSE', 'WORKSHOP', 'ACHIEVEMENT', 'TRAINING'] else 'INTERNSHIP',
                    'start_date': enrollment.start_date,
                    'end_date': enrollment.end_date,
                    'duration': enrollment.duration,
                }
            except Enrollment.DoesNotExist:
                pass

        form = CertificateCreateForm(initial=initial)
        return render(request, 'dashboard/certificate_form.html', {
            'form': form,
            'title': 'Create & Issue Certificate',
        })

    def post(self, request):
        form = CertificateCreateForm(request.POST)
        if not form.is_valid():
            return render(request, 'dashboard/certificate_form.html', {
                'form': form,
                'title': 'Create & Issue Certificate',
            })

        session_data = {
            'student_id': form.cleaned_data['student'].pk,
            'program_id': form.cleaned_data['program'].pk,
            'enrollment_id': form.cleaned_data['enrollment'].pk if form.cleaned_data.get('enrollment') else None,
            'certificate_type': form.cleaned_data['certificate_type'],
            'template_id': form.cleaned_data['template'].pk,
            'signatory_id': form.cleaned_data['authorized_signatory'].pk if form.cleaned_data.get('authorized_signatory') else None,
            'start_date': str(form.cleaned_data['start_date']),
            'end_date': str(form.cleaned_data['end_date']) if form.cleaned_data.get('end_date') else None,
            'issue_date': str(form.cleaned_data['issue_date']),
            'duration': form.cleaned_data.get('duration'),
        }
        request.session['certificate_creation_data'] = session_data
        return redirect('dashboard:certificate_preview')


class CertificatePreviewView(LoginRequiredMixin, View):
    """Step 2: Live HTML preview of certificate before confirmation."""
    def get(self, request):
        session_data = request.session.get('certificate_creation_data')
        if not session_data:
            messages.warning(request, "No active certificate creation in progress. Please start here.")
            return redirect('dashboard:certificate_create')

        import datetime
        student = get_object_or_404(Student, pk=session_data['student_id'])
        program = get_object_or_404(Program, pk=session_data['program_id'])
        template = get_object_or_404(CertificateTemplate, pk=session_data['template_id'])
        signatory = AuthorizedSignatory.objects.filter(pk=session_data['signatory_id']).first() if session_data.get('signatory_id') else None
        enrollment = Enrollment.objects.filter(pk=session_data['enrollment_id']).first() if session_data.get('enrollment_id') else None

        start_date = datetime.date.fromisoformat(session_data['start_date'])
        end_date = datetime.date.fromisoformat(session_data['end_date']) if session_data.get('end_date') else None
        issue_date = datetime.date.fromisoformat(session_data['issue_date'])

        # Render preview HTML
        preview_html, context = CertificateIssuanceService.render_preview(
            student=student,
            program=program,
            certificate_type=session_data['certificate_type'],
            template=template,
            authorized_signatory=signatory,
            issue_date=issue_date,
            start_date=start_date,
            end_date=end_date,
            duration=session_data.get('duration'),
            enrollment=enrollment,
        )

        return render(request, 'dashboard/certificate_preview.html', {
            'student': student,
            'program': program,
            'certificate_type': session_data['certificate_type'],
            'template': template,
            'signatory': signatory,
            'issue_date': issue_date,
            'start_date': start_date,
            'end_date': end_date,
            'duration': session_data.get('duration'),
            'preview_html': preview_html,
        })


class CertificateConfirmIssueView(LoginRequiredMixin, View):
    """Step 3: Execute atomic issuance (ID -> Token -> QR -> PDF -> ISSUED -> AuditLog)."""
    def post(self, request):
        session_data = request.session.get('certificate_creation_data')
        if not session_data:
            messages.error(request, "Session expired or invalid creation request.")
            return redirect('dashboard:certificate_create')

        import datetime
        student = get_object_or_404(Student, pk=session_data['student_id'])
        program = get_object_or_404(Program, pk=session_data['program_id'])
        template = get_object_or_404(CertificateTemplate, pk=session_data['template_id'])
        signatory = AuthorizedSignatory.objects.filter(pk=session_data['signatory_id']).first() if session_data.get('signatory_id') else None
        enrollment = Enrollment.objects.filter(pk=session_data['enrollment_id']).first() if session_data.get('enrollment_id') else None

        start_date = datetime.date.fromisoformat(session_data['start_date'])
        end_date = datetime.date.fromisoformat(session_data['end_date']) if session_data.get('end_date') else None
        issue_date = datetime.date.fromisoformat(session_data['issue_date'])

        ip_address = request.META.get('REMOTE_ADDR')

        try:
            certificate = CertificateIssuanceService.issue_certificate(
                student=student,
                program=program,
                certificate_type=session_data['certificate_type'],
                template=template,
                authorized_signatory=signatory,
                issue_date=issue_date,
                start_date=start_date,
                end_date=end_date,
                duration=session_data.get('duration'),
                enrollment=enrollment,
                user=request.user,
                ip_address=ip_address,
            )
            request.session.pop('certificate_creation_data', None)
            messages.success(
                request,
                f"Certificate {certificate.certificate_id} has been successfully issued to {student.full_name} with QR code and PDF."
            )
            return redirect('dashboard:certificate_detail', pk=certificate.pk)
        except Exception as e:
            messages.error(request, f"Certificate issuance failed: {str(e)}")
            return redirect('dashboard:certificate_preview')


class CertificateDownloadView(LoginRequiredMixin, View):
    """Download the compiled certificate PDF."""
    def get(self, request, pk):
        certificate = get_object_or_404(Certificate, pk=pk)
        if not certificate.certificate_pdf:
            CertificatePDFService.generate_pdf_for_certificate(certificate, save=True)
            certificate.refresh_from_db()

        certificate.certificate_pdf.open('rb')
        filename = CertificatePDFService.get_safe_filename(certificate.certificate_id)

        # Log dashboard download
        AuditLogService.log_certificate_downloaded(
            certificate,
            user=request.user,
            request=request,
            source="DASHBOARD",
        )

        response = FileResponse(certificate.certificate_pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response


@method_decorator(xframe_options_sameorigin, name='dispatch')
class CertificateHtmlPreviewView(LoginRequiredMixin, View):
    """Render an existing certificate as a full-screen HTML page for live in-browser preview."""
    def get(self, request, pk):
        from certificates.template_service import TemplateRenderingService
        certificate = get_object_or_404(Certificate, pk=pk)
        base_url = request.build_absolute_uri('/')
        html_content = TemplateRenderingService.render_template(certificate, base_url=base_url)
        return HttpResponse(html_content, content_type='text/html; charset=utf-8')


class CertificateTemplateGalleryView(LoginRequiredMixin, View):
    """Display the certificate template gallery for admin preview."""
    def get(self, request):
        features = [
            {'icon': '📜', 'title': 'Unique Certificate ID', 'desc': 'Auto-generated traceable identifier'},
            {'icon': '🔐', 'title': 'Verification Token', 'desc': 'Cryptographic public verification anchor'},
            {'icon': '▣', 'title': 'QR Code', 'desc': 'Embedded scannable verification QR'},
            {'icon': '✍️', 'title': 'Authorized Signatory', 'desc': 'Signature image and title embedded'},
            {'icon': '🏢', 'title': 'Company Logo', 'desc': 'Your organization branding auto-embedded'},
            {'icon': '📄', 'title': 'PDF Generation', 'desc': 'WeasyPrint A4 Landscape PDF output'},
            {'icon': '✉️', 'title': 'Email Delivery', 'desc': 'Sent directly to student with PDF attached'},
            {'icon': '🌐', 'title': 'Public Verification', 'desc': 'Scannable URL for anyone to verify'},
        ]
        return render(request, 'dashboard/certificate_templates.html', {
            'features': features,
        })


class CertificateIssueDraftView(LoginRequiredMixin, View):
    """Issue an existing draft certificate."""
    def post(self, request, pk):
        certificate = get_object_or_404(Certificate, pk=pk)
        ip_address = request.META.get('REMOTE_ADDR')
        try:
            CertificateIssuanceService.issue_existing_certificate(
                certificate, user=request.user, ip_address=ip_address
            )
            messages.success(request, f"Certificate {certificate.certificate_id} has been officially issued.")
        except Exception as e:
            messages.error(request, f"Failed to issue certificate: {str(e)}")
        return redirect('dashboard:certificate_detail', pk=certificate.pk)


class CertificateRevokeView(LoginRequiredMixin, View):
    """Revoke an issued certificate with a mandatory reason."""
    def post(self, request, pk):
        certificate = get_object_or_404(Certificate, pk=pk)
        reason = request.POST.get('revocation_reason', '').strip()

        if not reason:
            messages.error(request, "A revocation reason is required to revoke a certificate.")
            return redirect('dashboard:certificate_detail', pk=certificate.pk)

        if certificate.status == 'REVOKED':
            messages.warning(request, f"Certificate {certificate.certificate_id} has already been revoked.")
            return redirect('dashboard:certificate_detail', pk=certificate.pk)

        if certificate.status != 'ISSUED':
            messages.error(request, f"Cannot revoke certificate with status '{certificate.get_status_display()}'. Only ISSUED certificates can be revoked.")
            return redirect('dashboard:certificate_detail', pk=certificate.pk)

        ip_address = request.META.get('REMOTE_ADDR')
        try:
            certificate.revoke(reason=reason, user=request.user, ip_address=ip_address)
            messages.success(
                request,
                f"Certificate {certificate.certificate_id} has been revoked successfully."
            )
        except Exception as e:
            messages.error(request, f"Revocation failed: {str(e)}")

        return redirect('dashboard:certificate_detail', pk=certificate.pk)


class CertificateResendEmailView(LoginRequiredMixin, View):
    """Resend delivery email for an issued certificate."""
    def post(self, request, pk):
        certificate = get_object_or_404(Certificate, pk=pk)
        if certificate.status != 'ISSUED':
            messages.error(request, "Delivery emails can only be sent for ISSUED certificates.")
            return redirect('dashboard:certificate_detail', pk=certificate.pk)

        ip_address = request.META.get('REMOTE_ADDR')
        from certificates.services import CertificateEmailService
        success, error = CertificateEmailService.send_certificate_email(
            certificate,
            user=request.user,
            ip_address=ip_address,
            fail_silently=True,
        )
        if success:
            messages.success(
                request,
                f"Certificate delivery email successfully sent to {certificate.student.email}."
            )
        else:
            messages.error(
                request,
                f"Failed to send delivery email: {error or 'Unknown error'}"
            )

        return redirect('dashboard:certificate_detail', pk=certificate.pk)


class CompanySettingsView(LoginRequiredMixin, View):
    """View to inspect, live-preview, and update company settings."""
    template_name = 'dashboard/company_settings.html'

    def get(self, request):
        company = CompanySettings.get_instance()
        form = CompanySettingsForm(instance=company)
        return render(request, self.template_name, {
            'form': form,
            'company': company,
        })

    def post(self, request):
        company = CompanySettings.get_instance()
        form = CompanySettingsForm(request.POST, request.FILES, instance=company)
        if form.is_valid():
            old_data = {
                'company_name': company.company_name,
                'email': company.email,
                'phone': company.phone,
                'website': company.website,
                'address': company.address,
                'description': company.description,
                'certificate_footer': company.certificate_footer,
                'theme_color': company.theme_color,
            }
            updated_instance = form.save()
            new_data = {
                'company_name': updated_instance.company_name,
                'email': updated_instance.email,
                'phone': updated_instance.phone,
                'website': updated_instance.website,
                'address': updated_instance.address,
                'description': updated_instance.description,
                'certificate_footer': updated_instance.certificate_footer,
                'theme_color': updated_instance.theme_color,
            }
            # Record change history in AuditLog
            changes = {}
            for k in new_data:
                if old_data.get(k) != new_data.get(k):
                    changes[k] = {'old': old_data.get(k), 'new': new_data.get(k)}
            if 'logo' in request.FILES:
                changes['logo'] = {'updated': True, 'filename': request.FILES['logo'].name}

            AuditLog.objects.create(
                action='UPDATE',
                object_type='CompanySettings',
                object_id=str(company.pk),
                user_email=request.user.email or request.user.username,
                changes=changes,
                ip_address=request.META.get('REMOTE_ADDR'),
            )

            messages.success(request, "Company settings have been updated successfully.")
            return redirect('dashboard:company_settings')

        messages.error(request, "Please correct the errors below before saving.")
        return render(request, self.template_name, {
            'form': form,
            'company': company,
        })


# ===========================================================================
# Authorized Signatory Management Views
# ===========================================================================

class SignatoryListView(LoginRequiredMixin, ListView):
    """View to list, filter, and search authorized signatories."""
    model = AuthorizedSignatory
    template_name = 'dashboard/signatory_list.html'
    context_object_name = 'signatories'
    paginate_by = 10

    def get_queryset(self):
        queryset = AuthorizedSignatory.objects.all().prefetch_related('signed_certificates').order_by('-created_at')
        
        # Search filter
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(name__icontains=q) |
                Q(title__icontains=q) |
                Q(organization__icontains=q) |
                Q(email__icontains=q)
            )

        # Status filter
        status = self.request.GET.get('status', '').strip().lower()
        if status == 'active':
            queryset = queryset.filter(is_active=True)
        elif status == 'inactive':
            queryset = queryset.filter(is_active=False)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_signatories = AuthorizedSignatory.objects.all()
        context['total_count'] = all_signatories.count()
        context['active_count'] = all_signatories.filter(is_active=True).count()
        context['inactive_count'] = all_signatories.filter(is_active=False).count()
        context['search_query'] = self.request.GET.get('q', '').strip()
        context['status_filter'] = self.request.GET.get('status', '').strip().lower()
        return context


class SignatoryCreateView(LoginRequiredMixin, View):
    """View to add a new authorized signatory with signature preview."""
    template_name = 'dashboard/signatory_form.html'

    def get(self, request):
        form = AuthorizedSignatoryForm()
        return render(request, self.template_name, {
            'form': form,
            'is_edit': False,
            'signatory': None,
        })

    def post(self, request):
        form = AuthorizedSignatoryForm(request.POST, request.FILES)
        if form.is_valid():
            signatory = form.save()

            # Record AuditLog
            AuditLog.objects.create(
                action='CREATE',
                object_type='AuthorizedSignatory',
                object_id=str(signatory.pk),
                user_email=request.user.email or request.user.username,
                changes={
                    'name': signatory.name,
                    'title': signatory.title,
                    'organization': signatory.organization,
                    'is_active': signatory.is_active,
                },
                ip_address=request.META.get('REMOTE_ADDR'),
            )

            messages.success(request, f"Authorized signatory '{signatory.name}' was created successfully.")
            return redirect('dashboard:signatory_list')

        messages.error(request, "Please correct the errors indicated below.")
        return render(request, self.template_name, {
            'form': form,
            'is_edit': False,
            'signatory': None,
        })


class SignatoryUpdateView(LoginRequiredMixin, View):
    """View to update an existing authorized signatory and signature image."""
    template_name = 'dashboard/signatory_form.html'

    def get(self, request, pk):
        signatory = get_object_or_404(AuthorizedSignatory, pk=pk)
        form = AuthorizedSignatoryForm(instance=signatory)
        return render(request, self.template_name, {
            'form': form,
            'is_edit': True,
            'signatory': signatory,
        })

    def post(self, request, pk):
        signatory = get_object_or_404(AuthorizedSignatory, pk=pk)
        old_data = {
            'name': signatory.name,
            'title': signatory.title,
            'organization': signatory.organization,
            'email': signatory.email,
            'is_active': signatory.is_active,
        }
        form = AuthorizedSignatoryForm(request.POST, request.FILES, instance=signatory)
        if form.is_valid():
            updated = form.save()

            changes = {}
            for k in old_data:
                new_val = getattr(updated, k)
                if old_data[k] != new_val:
                    changes[k] = {'old': old_data[k], 'new': new_val}
            if 'signature_image' in request.FILES:
                changes['signature_image'] = {'updated': True, 'filename': request.FILES['signature_image'].name}

            if changes:
                AuditLog.objects.create(
                    action='UPDATE',
                    object_type='AuthorizedSignatory',
                    object_id=str(updated.pk),
                    user_email=request.user.email or request.user.username,
                    changes=changes,
                    ip_address=request.META.get('REMOTE_ADDR'),
                )

            messages.success(request, f"Authorized signatory '{updated.name}' was updated successfully.")
            return redirect('dashboard:signatory_list')

        messages.error(request, "Please correct the errors indicated below.")
        return render(request, self.template_name, {
            'form': form,
            'is_edit': True,
            'signatory': signatory,
        })


class SignatoryToggleActiveView(LoginRequiredMixin, View):
    """POST endpoint to toggle active/inactive status for a signatory."""

    def post(self, request, pk):
        signatory = get_object_or_404(AuthorizedSignatory, pk=pk)
        old_state = signatory.is_active
        signatory.is_active = not signatory.is_active
        signatory.save(update_fields=['is_active', 'updated_at'])

        status_text = "activated" if signatory.is_active else "deactivated"

        AuditLog.objects.create(
            action='UPDATE',
            object_type='AuthorizedSignatory',
            object_id=str(signatory.pk),
            user_email=request.user.email or request.user.username,
            changes={'is_active': {'old': old_state, 'new': signatory.is_active}},
            ip_address=request.META.get('REMOTE_ADDR'),
        )

        messages.success(request, f"Signatory '{signatory.name}' has been {status_text}.")
        return redirect('dashboard:signatory_list')


class SignatoryDeleteView(LoginRequiredMixin, View):
    """POST endpoint to safely delete an authorized signatory if no certificates are attached."""

    def post(self, request, pk):
        signatory = get_object_or_404(AuthorizedSignatory, pk=pk)
        
        # Safe deletion gate
        if not signatory.can_delete():
            count = signatory.certificates_count
            messages.error(
                request,
                f"Cannot delete '{signatory.name}' because {count} certificate(s) are signed by them. "
                "You can deactivate this signatory instead to prevent future assignments while preserving certificate authenticity."
            )
            return redirect('dashboard:signatory_list')

        name = signatory.name
        signatory.delete()

        AuditLog.objects.create(
            action='DELETE',
            object_type='AuthorizedSignatory',
            object_id=str(pk),
            user_email=request.user.email or request.user.username,
            changes={'name': name},
            ip_address=request.META.get('REMOTE_ADDR'),
        )

        messages.success(request, f"Authorized signatory '{name}' was safely deleted.")
        return redirect('dashboard:signatory_list')


class BulkCertificateUploadView(LoginRequiredMixin, View):
    """Step 1: Upload CSV file and select default template/signatory."""
    template_name = 'dashboard/certificate_bulk_upload.html'

    def get(self, request):
        form = BulkCertificateUploadForm()
        return render(request, self.template_name, {
            'form': form,
            'active_tab': 'certificates',
        })


class BulkCertificateValidateView(LoginRequiredMixin, View):
    """Step 2: Validate uploaded CSV file and store parsed results in session."""
    def post(self, request):
        form = BulkCertificateUploadForm(request.POST, request.FILES)
        if not form.is_valid():
            for field, errs in form.errors.items():
                for err in errs:
                    messages.error(request, f"{err}")
            return render(request, 'dashboard/certificate_bulk_upload.html', {
                'form': form,
                'active_tab': 'certificates',
            })

        csv_file = form.cleaned_data['csv_file']
        default_template = form.cleaned_data.get('default_template')
        default_signatory = form.cleaned_data.get('default_signatory')

        validation_result = BulkCertificateService.validate_csv(
            csv_file,
            default_template_id=default_template.pk if default_template else None,
            default_signatory_id=default_signatory.pk if default_signatory else None,
        )

        # Store in session
        request.session['bulk_validation_data'] = {
            'total_rows': validation_result.total_rows,
            'valid_rows_count': validation_result.valid_rows_count,
            'invalid_rows_count': validation_result.invalid_rows_count,
            'is_valid': validation_result.is_valid,
            'header_errors': validation_result.header_errors,
            'row_errors': [e.to_dict() for e in validation_result.row_errors],
            'preview_rows': validation_result.preview_rows,
            'serialized_data': validation_result.serialized_data,
            'default_template_name': default_template.name if default_template else 'System Default',
            'default_signatory_name': default_signatory.name if default_signatory else 'System Default',
        }

        return redirect('dashboard:certificate_bulk_preview')


class BulkCertificatePreviewView(LoginRequiredMixin, View):
    """Step 3: Preview validation status, show error details or confirmation button."""
    template_name = 'dashboard/certificate_bulk_preview.html'

    def get(self, request):
        data = request.session.get('bulk_validation_data')
        if not data:
            messages.warning(request, "No active CSV validation in progress. Please upload a CSV first.")
            return redirect('dashboard:certificate_bulk_upload')

        return render(request, self.template_name, {
            'data': data,
            'active_tab': 'certificates',
        })


class BulkCertificateConfirmView(LoginRequiredMixin, View):
    """Step 4: Execute transactional bulk certificate issuance."""
    def post(self, request):
        data = request.session.get('bulk_validation_data')
        if not data:
            messages.error(request, "Session expired or invalid bulk issuance request.")
            return redirect('dashboard:certificate_bulk_upload')

        if not data.get('is_valid') or data.get('invalid_rows_count', 0) > 0 or not data.get('serialized_data'):
            messages.error(request, "Cannot generate certificates: CSV contains validation errors.")
            return redirect('dashboard:certificate_bulk_preview')

        ip_address = request.META.get('REMOTE_ADDR')
        exec_result = BulkCertificateService.execute_bulk_issuance(
            validated_rows=data['serialized_data'],
            user=request.user,
            ip_address=ip_address,
        )

        if exec_result.success:
            # Clear session
            request.session.pop('bulk_validation_data', None)
            messages.success(
                request,
                f"Successfully issued {exec_result.issued_count} certificates in bulk!"
            )
            return redirect('dashboard:certificate_list')
        else:
            for err in exec_result.errors:
                messages.error(request, err)
            return redirect('dashboard:certificate_bulk_preview')


class BulkCertificateSampleCsvView(LoginRequiredMixin, View):
    """Download a ready-to-use sample CSV template."""
    def get(self, request):
        csv_content = BulkCertificateService.get_sample_csv_content()
        response = HttpResponse(csv_content, content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="sample_bulk_certificates.csv"'
        return response


class CertificateRegeneratePdfView(LoginRequiredMixin, View):
    """Regenerate WeasyPrint PDF and QR code for an existing certificate."""
    def post(self, request, pk):
        certificate = get_object_or_404(Certificate, pk=pk)
        if certificate.status == 'REVOKED':
            messages.error(request, "Cannot regenerate PDF for a revoked certificate.")
            return redirect('dashboard:certificate_detail', pk=certificate.pk)

        try:
            # Regenerate QR code
            QRCodeService.generate_qr_for_certificate(certificate, save=True)
            # Regenerate PDF
            CertificatePDFService.generate_pdf_for_certificate(certificate, save=True)
            certificate.refresh_from_db()

            # Log Audit
            AuditLogService.log_certificate_regenerated(
                certificate,
                user=request.user,
                request=request,
                reason="Admin re-compiled certificate PDF",
            )
            messages.success(request, f"Certificate PDF for {certificate.certificate_id} has been regenerated.")
        except Exception as e:
            messages.error(request, f"Failed to regenerate PDF: {str(e)}")

        return redirect('dashboard:certificate_detail', pk=certificate.pk)


class AuditLogListView(LoginRequiredMixin, ListView):
    """Admin view to inspect, search, filter, and page through system audit logs."""
    model = AuditLog
    template_name = 'dashboard/audit_log_list.html'
    context_object_name = 'logs'
    paginate_by = 20

    def get_queryset(self):
        import datetime
        from django.utils import timezone
        qs = AuditLog.objects.all().order_by('-timestamp')

        # Search query (certificate_id, user_email, object_id, action, changes text)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(object_id__icontains=q) |
                Q(user_email__icontains=q) |
                Q(object_type__icontains=q) |
                Q(action__icontains=q) |
                Q(ip_address__icontains=q)
            )

        # Action filter
        action = self.request.GET.get('action', '').strip()
        if action:
            qs = qs.filter(action=action)

        # Object type filter
        object_type = self.request.GET.get('object_type', '').strip()
        if object_type:
            qs = qs.filter(object_type=object_type)

        # Date preset filter
        date_filter = self.request.GET.get('date_range', '').strip()
        now = timezone.now()
        if date_filter == 'today':
            qs = qs.filter(timestamp__date=now.date())
        elif date_filter == '7days':
            qs = qs.filter(timestamp__gte=now - datetime.timedelta(days=7))
        elif date_filter == '30days':
            qs = qs.filter(timestamp__gte=now - datetime.timedelta(days=30))

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '').strip()
        context['action_selected'] = self.request.GET.get('action', '').strip()
        context['object_type_selected'] = self.request.GET.get('object_type', '').strip()
        context['date_range_selected'] = self.request.GET.get('date_range', '').strip()
        context['action_choices'] = AuditLog.ACTION_CHOICES
        context['object_types'] = sorted(list(
            set(AuditLog.objects.values_list('object_type', flat=True).distinct())
        ))
        context['total_count'] = AuditLog.objects.count()
        context['cert_count'] = AuditLog.objects.filter(object_type='Certificate').count()
        context['verify_count'] = AuditLog.objects.filter(action='VERIFY').count()
        context['active_tab'] = 'audit_logs'
        return context
