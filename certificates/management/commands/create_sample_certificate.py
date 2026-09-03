import os
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageDraw
import io

from users.models import Student, AuthorizedSignatory, CompanySettings
from certificates.models import Program, CertificateTemplate, Certificate, Enrollment
from certificates.services import CertificatePDFService, QRCodeService


class Command(BaseCommand):
    help = "Create a sample certificate using demo data and generate its PDF."

    def handle(self, *args, **options):
        self.stdout.write("Creating demo data for sample certificate...")

        # 1. Company Settings
        company = CompanySettings.get_instance()
        company.organization_name = "Global Institute of Advanced Technologies"
        company.email = "admin@globaltech.edu"
        company.phone = "+1 (555) 019-2834"
        company.address = "100 Innovation Boulevard, Tech City, CA 94016"
        company.theme_color = "#1a365d"

        # Generate sample logo image
        logo_img = Image.new("RGBA", (200, 80), color=(26, 54, 93, 255))
        draw = ImageDraw.Draw(logo_img)
        draw.rectangle([10, 10, 190, 70], outline=(197, 160, 89), width=2)
        draw.text((30, 30), "GIAT ACADEMY", fill=(255, 255, 255))
        logo_buf = io.BytesIO()
        logo_img.save(logo_buf, format="PNG")
        company.logo.save("giat_logo.png", ContentFile(logo_buf.getvalue()), save=True)

        # 2. Student
        student, _ = Student.objects.get_or_create(
            email="alexandra.morgan@university.edu",
            defaults={
                "full_name": "Alexandra Morgan",
                "phone": "+1 555-432-1098",
                "college": "Stanford School of Engineering",
                "university": "Stanford University",
                "degree": "Bachelor of Science",
                "branch": "Computer Science & Artificial Intelligence",
                "graduation_year": 2026,
                "is_active": True,
            }
        )

        # 3. Program
        program, _ = Program.objects.get_or_create(
            name="Advanced Full-Stack Engineering & Cloud Architecture",
            defaults={
                "program_type": "INTERNSHIP",
                "description": "Comprehensive full-stack development, distributed systems, and cloud architecture program.",
                "duration": 90,
                "mode": "HYBRID",
                "department": "Department of Computer Science & Software Engineering",
                "mentor": "Dr. Marcus Vance, Principal Software Architect",
                "skills": ["Python", "Django", "React", "PostgreSQL", "Docker", "AWS"],
                "learning_outcomes": ["Architect resilient microservices", "Deploy containerized applications"],
                "is_active": True,
            }
        )

        # 4. Authorized Signatory
        signatory, _ = AuthorizedSignatory.objects.get_or_create(
            email="marcus.vance@giat.edu",
            defaults={
                "name": "Dr. Marcus Vance",
                "title": "Dean of Engineering & Executive Director",
                "organization": "Global Institute of Advanced Technologies",
            }
        )
        # Create a sample signature image
        sig_img = Image.new("RGBA", (250, 80), color=(255, 255, 255, 0))
        draw_sig = ImageDraw.Draw(sig_img)
        draw_sig.line([(20, 50), (60, 20), (100, 55), (140, 25), (180, 45), (220, 35)], fill=(26, 54, 93), width=3)
        draw_sig.line([(15, 60), (230, 60)], fill=(197, 160, 89), width=1)
        sig_buf = io.BytesIO()
        sig_img.save(sig_buf, format="PNG")
        signatory.signature_image.save("dean_signature.png", ContentFile(sig_buf.getvalue()), save=True)

        # 5. Certificate Template
        template, _ = CertificateTemplate.objects.get_or_create(
            name="Executive Platinum Certificate Template",
            defaults={
                "organization": "Global Institute of Advanced Technologies",
                "description": "Premium institutional certificate layout for degree and internship completion.",
                "html_template": "templates/certificates/certificate_pdf.html",
                "colors": {"primary": "#1a365d", "secondary": "#c5a059"},
                "is_active": True,
            }
        )

        # 6. Enrollment
        import datetime
        start_date = datetime.date(2026, 1, 5)
        end_date = datetime.date(2026, 4, 5)
        enrollment, _ = Enrollment.objects.get_or_create(
            student=student,
            program=program,
            start_date=start_date,
            defaults={
                "end_date": end_date,
                "duration": 90,
                "mentor": signatory.name,
                "department": program.department,
                "project_title": "Enterprise Microservices Distributed Event Pipeline",
                "project_description": "Architected and delivered an asynchronous high-throughput event processing platform.",
                "skills": program.skills,
                "learning_outcomes": program.learning_outcomes,
                "attendance_percentage": 98.50,
                "performance_rating": 4.9,
                "status": "COMPLETED",
            }
        )

        # 7. Issued Certificate
        certificate = Certificate.objects.create(
            student=student,
            program=program,
            enrollment=enrollment,
            certificate_type="INTERNSHIP",
            issue_date=end_date,
            start_date=start_date,
            end_date=end_date,
            duration=90,
            status="ISSUED",
            template=template,
            authorized_signatory=signatory,
        )

        # 8. Generate QR and PDF
        self.stdout.write("Generating QR Code...")
        QRCodeService.generate_qr_for_certificate(certificate, save=True)

        self.stdout.write("Generating WeasyPrint A4 Landscape PDF...")
        CertificatePDFService.generate_pdf_for_certificate(certificate, save=True)

        # Check single page
        is_single_page = CertificatePDFService.validate_single_page(certificate)

        self.stdout.write(self.style.SUCCESS(
            f"Successfully created sample certificate!\n"
            f"  - Certificate ID: {certificate.certificate_id}\n"
            f"  - Verification Token: {certificate.verification_token}\n"
            f"  - Student: {certificate.student.full_name}\n"
            f"  - Program: {certificate.program.name}\n"
            f"  - QR Code: {certificate.qr_code.name}\n"
            f"  - PDF Document: {certificate.certificate_pdf.name} (File Size: {certificate.certificate_pdf.size} bytes)\n"
            f"  - Single Page A4 Guarantee: {'PASSED' if is_single_page else 'FAILED'}"
        ))
