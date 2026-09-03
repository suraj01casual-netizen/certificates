from django import forms
from django.utils import timezone
from django.core.validators import URLValidator
from django.core.files.uploadedfile import UploadedFile
import os
from PIL import Image
from users.models import Student, AuthorizedSignatory, CompanySettings
from certificates.models import Program, Enrollment, Certificate, CertificateTemplate

class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            'full_name',
            'email',
            'phone',
            'college',
            'university',
            'degree',
            'branch',
            'graduation_year',
            'profile_photo',
            'is_active',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter full name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter email address'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter phone number'}),
            'college': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter college name'}),
            'university': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter university name'}),
            'degree': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter degree (e.g., B.Tech)'}),
            'branch': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter branch (e.g., Computer Science)'}),
            'graduation_year': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter graduation year'}),
            'profile_photo': forms.ClearableFileInput(attrs={'class': 'form-control-file'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            email = email.lower()
            # Check unique email excluding current instance if editing
            qs = Student.objects.filter(email=email)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("A student with this email address already exists.")
        return email

    def clean_graduation_year(self):
        year = self.cleaned_data.get('graduation_year')
        if year is not None:
            if year < 1900 or year > 2100:
                raise forms.ValidationError("Please enter a valid graduation year between 1900 and 2100.")
        return year


class ProgramForm(forms.ModelForm):
    skills_text = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Enter skills covered, separated by commas'}),
        required=False,
        label="Skills Covered"
    )
    learning_outcomes_text = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Enter learning outcomes, separated by commas'}),
        required=False,
        label="Learning Outcomes"
    )

    class Meta:
        model = Program
        fields = [
            'name',
            'program_type',
            'description',
            'duration',
            'mode',
            'department',
            'mentor',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter program name'}),
            'program_type': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Enter description'}),
            'duration': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Duration in days'}),
            'mode': forms.Select(attrs={'class': 'form-control'}),
            'department': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter department'}),
            'mentor': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter mentor name'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if isinstance(self.instance.skills, list):
                self.fields['skills_text'].initial = ", ".join(self.instance.skills)
            if isinstance(self.instance.learning_outcomes, list):
                self.fields['learning_outcomes_text'].initial = ", ".join(self.instance.learning_outcomes)

    def clean_skills_text(self):
        data = self.cleaned_data.get('skills_text', '')
        if data:
            return [s.strip() for s in data.split(',') if s.strip()]
        return []

    def clean_learning_outcomes_text(self):
        data = self.cleaned_data.get('learning_outcomes_text', '')
        if data:
            return [l.strip() for l in data.split(',') if l.strip()]
        return []

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.skills = self.cleaned_data['skills_text']
        instance.learning_outcomes = self.cleaned_data['learning_outcomes_text']
        if commit:
            instance.save()
        return instance


class EnrollmentForm(forms.ModelForm):
    skills_text = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Enter skills acquired, separated by commas'}),
        required=False,
        label="Skills Acquired"
    )
    learning_outcomes_text = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Enter learning outcomes, separated by commas'}),
        required=False,
        label="Learning Outcomes"
    )

    class Meta:
        model = Enrollment
        fields = [
            'student',
            'program',
            'start_date',
            'end_date',
            'duration',
            'mentor',
            'department',
            'project_title',
            'project_description',
            'skills_text',
            'learning_outcomes_text',
            'attendance_percentage',
            'performance_rating',
            'status',
        ]
        widgets = {
            'student': forms.Select(attrs={'class': 'form-control'}),
            'program': forms.Select(attrs={'class': 'form-control'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'duration': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Auto-calculated from dates', 'readonly': 'readonly'}),
            'mentor': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter mentor name'}),
            'department': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter department'}),
            'project_title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter project title'}),
            'project_description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Enter project description'}),
            'attendance_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'e.g., 95.50'}),
            'performance_rating': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '1', 'max': '5', 'placeholder': 'Rating from 1-5'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if isinstance(self.instance.skills, list):
                self.fields['skills_text'].initial = ", ".join(self.instance.skills)
            if isinstance(self.instance.learning_outcomes, list):
                self.fields['learning_outcomes_text'].initial = ", ".join(self.instance.learning_outcomes)

    def clean(self):
        cleaned_data = super().clean()
        student = cleaned_data.get('student')
        program = cleaned_data.get('program')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date:
            if end_date < start_date:
                self.add_error('end_date', "End date cannot be before the start date.")

        if student and program and start_date:
            qs = Enrollment.objects.filter(student=student, program=program, start_date=start_date)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error('student', "Enrollment with this student, program, and start date already exists.")
        return cleaned_data

    def clean_skills_text(self):
        data = self.cleaned_data.get('skills_text', '')
        if data:
            return [s.strip() for s in data.split(',') if s.strip()]
        return []

    def clean_learning_outcomes_text(self):
        data = self.cleaned_data.get('learning_outcomes_text', '')
        if data:
            return [l.strip() for l in data.split(',') if l.strip()]
        return []

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.skills = self.cleaned_data['skills_text']
        instance.learning_outcomes = self.cleaned_data['learning_outcomes_text']
        # Calculate duration from start and end dates
        start_date = self.cleaned_data.get('start_date')
        end_date = self.cleaned_data.get('end_date')
        if start_date and end_date:
            instance.duration = (end_date - start_date).days
        if commit:
            instance.save()
        return instance


class CertificateCreateForm(forms.Form):
    """Form to configure and preview certificate before issuance."""
    student = forms.ModelChoiceField(
        queryset=Student.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Student *"
    )
    program = forms.ModelChoiceField(
        queryset=Program.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Program *"
    )
    enrollment = forms.ModelChoiceField(
        queryset=Enrollment.objects.all(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Associated Enrollment (Optional)"
    )
    certificate_type = forms.ChoiceField(
        choices=Certificate.CERTIFICATE_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Certificate Type *"
    )
    template = forms.ModelChoiceField(
        queryset=CertificateTemplate.objects.filter(is_active=True),
        empty_label="-- Select Certificate Template --",
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Certificate Template *"
    )
    authorized_signatory = forms.ModelChoiceField(
        queryset=AuthorizedSignatory.objects.filter(is_active=True),
        required=False,
        empty_label="-- Select Active Signatory (Optional) --",
        widget=forms.Select(attrs={'class': 'form-control'}),
        label="Authorized Signatory"
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label="Start Date *"
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label="End Date"
    )
    issue_date = forms.DateField(
        initial=timezone.now().date,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        label="Issue Date *"
    )
    duration = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Auto-calculated or enter days'}),
        label="Duration (Days)"
    )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date:
            if end_date < start_date:
                self.add_error('end_date', "End date cannot be before the start date.")
            elif not cleaned_data.get('duration'):
                cleaned_data['duration'] = (end_date - start_date).days
        return cleaned_data


class CompanySettingsForm(forms.ModelForm):
    """Form to manage company branding, contact details, description, and certificate footer."""
    
    company_name = forms.CharField(
        max_length=255,
        required=True,
        label="Company / Organization Name *",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter official company or organization name',
            'id': 'id_company_name',
        })
    )
    email = forms.EmailField(
        required=False,
        label="Contact Email",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'contact@company.com',
            'id': 'id_email',
        })
    )
    phone = forms.CharField(
        max_length=20,
        required=False,
        label="Contact Phone",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+1 (555) 000-0000',
            'id': 'id_phone',
        })
    )
    address = forms.CharField(
        required=False,
        label="Address",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Enter street address, city, state, postal code, country',
            'id': 'id_address',
        })
    )
    website = forms.CharField(
        max_length=255,
        required=False,
        label="Website URL",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'https://www.company.com',
            'id': 'id_website',
        })
    )
    description = forms.CharField(
        required=False,
        label="Company Description",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Brief description of the organization or mission statement',
            'id': 'id_description',
        })
    )
    certificate_footer = forms.CharField(
        required=False,
        label="Certificate Footer Notice",
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Custom footer notice or legal disclaimer printed on generated certificates',
            'id': 'id_certificate_footer',
        })
    )
    theme_color = forms.CharField(
        max_length=7,
        required=False,
        label="Branding Theme Color",
        widget=forms.TextInput(attrs={
            'type': 'color',
            'class': 'form-control form-control-color',
            'id': 'id_theme_color',
            'style': 'height: 42px; padding: 4px; cursor: pointer; width: 100%;',
        })
    )

    class Meta:
        model = CompanySettings
        fields = [
            'company_name',
            'logo',
            'email',
            'phone',
            'address',
            'website',
            'description',
            'certificate_footer',
            'theme_color',
        ]
        widgets = {
            'logo': forms.ClearableFileInput(attrs={
                'class': 'form-control-file',
                'id': 'id_logo',
                'accept': '.jpg,.jpeg,.png,.webp,.svg',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if not self.initial.get('company_name'):
                self.initial['company_name'] = self.instance.company_name or self.instance.organization_name

    def clean_company_name(self):
        name = self.cleaned_data.get('company_name', '').strip()
        if not name:
            raise forms.ValidationError("Company / Organization name is required.")
        if len(name) < 2:
            raise forms.ValidationError("Company name must be at least 2 characters.")
        return name

    def clean_website(self):
        url = self.cleaned_data.get('website', '').strip()
        if url:
            if not url.startswith(('http://', 'https://')):
                url = f"https://{url}"
            validator = URLValidator()
            try:
                validator(url)
            except forms.ValidationError:
                raise forms.ValidationError("Please enter a valid website URL (e.g., https://example.com).")
        return url

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        if phone:
            import re
            # Allow digits, +, -, (, ), spaces, min length 7
            if not re.match(r'^[0-9+\-()\s]{7,20}$', phone):
                raise forms.ValidationError("Please enter a valid phone number (7-20 digits and standard punctuation).")
        return phone

    def clean_logo(self):
        logo = self.cleaned_data.get('logo')
        if logo and isinstance(logo, UploadedFile):
            # 1. File Size Validation (Max 2 MB)
            max_size_bytes = 2 * 1024 * 1024
            if logo.size > max_size_bytes:
                raise forms.ValidationError(
                    f"Logo file size ({logo.size / (1024*1024):.1f} MB) exceeds the maximum allowed size of 2 MB."
                )

            # 2. Extension & MIME Validation
            ext = os.path.splitext(logo.name)[1].lower()
            allowed_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.svg']
            if ext not in allowed_extensions:
                raise forms.ValidationError(
                    f"Unsupported image format '{ext}'. Allowed formats: JPG, PNG, WebP, SVG."
                )

            # 3. Pillow Image Integrity Validation (for raster images)
            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                try:
                    img = Image.open(logo)
                    img.verify()
                    # Reset pointer after verify
                    logo.seek(0)
                except Exception:
                    raise forms.ValidationError("Uploaded file is not a valid or readable image file.")
        return logo

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.company_name = self.cleaned_data.get('company_name')
        instance.organization_name = self.cleaned_data.get('company_name')
        if commit:
            instance.save()
        return instance


class AuthorizedSignatoryForm(forms.ModelForm):
    """Form for managing authorized signatories with image validation and formatting."""

    name = forms.CharField(
        max_length=255,
        required=True,
        label="Signatory Name *",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. Dr. Jane Smith',
            'autocomplete': 'name',
        })
    )

    title = forms.CharField(
        max_length=255,
        required=True,
        label="Designation / Title *",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. Director of Academic Affairs / CEO',
        })
    )

    organization = forms.CharField(
        max_length=255,
        required=False,
        label="Organization (Optional)",
        help_text="Leave blank to use the organization from Company Settings.",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. Global Institute of Technology',
        })
    )

    email = forms.EmailField(
        required=False,
        label="Email Address (Optional)",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'signatory@organization.org',
            'autocomplete': 'email',
        })
    )

    signature_image = forms.ImageField(
        required=False,
        label="Signature Image",
        help_text="PNG with transparent background is strongly recommended (max 2 MB).",
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/png,image/jpeg,image/webp,image/svg+xml',
            'id': 'id_signature_image',
        })
    )

    is_active = forms.BooleanField(
        required=False,
        initial=True,
        label="Active Signatory",
        help_text="Only active signatories can be selected during certificate generation.",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    class Meta:
        model = AuthorizedSignatory
        fields = [
            'name',
            'title',
            'organization',
            'email',
            'signature_image',
            'is_active',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Signature is required when creating a new signatory
        if not self.instance.pk:
            self.fields['signature_image'].required = True

    def clean_name(self):
        name = self.cleaned_data.get('name', '').strip()
        if not name or len(name) < 2:
            raise forms.ValidationError("Signatory name must be at least 2 characters.")
        return name

    def clean_title(self):
        title = self.cleaned_data.get('title', '').strip()
        if not title or len(title) < 2:
            raise forms.ValidationError("Designation must be at least 2 characters.")
        return title

    def clean_signature_image(self):
        signature = self.cleaned_data.get('signature_image')
        if signature and isinstance(signature, UploadedFile):
            # 1. File Size Validation (Max 2 MB)
            max_size_bytes = 2 * 1024 * 1024
            if signature.size > max_size_bytes:
                raise forms.ValidationError(
                    f"Signature file size ({signature.size / (1024*1024):.1f} MB) exceeds the 2 MB limit."
                )

            # 2. Extension Check
            ext = os.path.splitext(signature.name)[1].lower()
            allowed_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.svg']
            if ext not in allowed_extensions:
                raise forms.ValidationError(
                    f"Unsupported signature format '{ext}'. Allowed formats: PNG, JPG, WebP, SVG."
                )

            # 3. Pillow Integrity Verification
            if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                try:
                    img = Image.open(signature)
                    img.verify()
                    signature.seek(0)
                except Exception:
                    raise forms.ValidationError("Uploaded file is not a valid or readable image file.")
        return signature


class BulkCertificateUploadForm(forms.Form):
    """Form for uploading CSV files for bulk certificate generation."""

    csv_file = forms.FileField(
        label="Select CSV File",
        widget=forms.FileInput(attrs={"class": "form-control-file", "accept": ".csv"}),
        help_text="Upload a .csv file formatted with student, program, and date columns.",
    )
    default_template = forms.ModelChoiceField(
        queryset=CertificateTemplate.objects.filter(is_active=True),
        required=False,
        empty_label="-- Use Default Active Template --",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Optional fallback design template if not specified in CSV rows.",
    )
    default_signatory = forms.ModelChoiceField(
        queryset=AuthorizedSignatory.objects.filter(is_active=True),
        required=False,
        empty_label="-- Use Default Active Signatory --",
        widget=forms.Select(attrs={"class": "form-control"}),
        help_text="Optional fallback authorized signatory if not specified in CSV rows.",
    )

    def clean_csv_file(self):
        csv_file = self.cleaned_data.get("csv_file")
        if csv_file:
            ext = os.path.splitext(csv_file.name)[1].lower()
            if ext != ".csv":
                raise forms.ValidationError("Invalid file extension. Please upload a standard .csv file.")
            if csv_file.size > 10 * 1024 * 1024:
                raise forms.ValidationError("CSV file exceeds maximum allowed size of 10 MB.")
        return csv_file
