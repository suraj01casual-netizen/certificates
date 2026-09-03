from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse


class AuthenticationTest(TestCase):
    """Test authentication views and permissions."""
    
    @classmethod
    def setUpTestData(cls):
        """Create test users."""
        # Create a superuser
        User.objects.create_superuser(
            username='admin',
            email='admin@test.local',
            password='admin123'
        )
        
        # Create a regular user
        User.objects.create_user(
            username='testuser',
            email='testuser@test.local',
            password='testuser123',
            first_name='Test',
            last_name='User'
        )
    
    def setUp(self):
        """Set up test client."""
        self.client = Client()
    
    def test_unauthenticated_user_cannot_access_dashboard(self):
        """Test that unauthenticated users are redirected from dashboard."""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response.url)
    
    def test_login_page_loads(self):
        """Test that login page loads."""
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'auth/login.html')
    
    def test_login_with_valid_email_and_password(self):
        """Test login with valid credentials."""
        response = self.client.post(reverse('login'), {
            'email': 'admin@test.local',
            'password': 'admin123'
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.wsgi_request.user.is_authenticated)
    
    def test_login_with_invalid_password(self):
        """Test login with invalid password."""
        response = self.client.post(reverse('login'), {
            'email': 'admin@test.local',
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, 200)
    
    def test_authenticated_user_can_access_dashboard(self):
        """Test that authenticated users can access dashboard."""
        self.client.login(username='admin', password='admin123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/dashboard_shell.html')
    
    def test_logout_works(self):
        """Test that logout works."""
        self.client.login(username='admin', password='admin123')
        response = self.client.get(reverse('logout'), follow=True)
        self.assertEqual(response.status_code, 200)
        
        # Verify user is logged out
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
    
    def test_dashboard_shows_user_info(self):
        """Test that dashboard shows logged-in user info."""
        self.client.login(username='testuser', password='testuser123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test')
        self.assertContains(response, 'testuser@test.local')
    
    def test_authenticated_user_redirected_from_login_page(self):
        """Test that authenticated users are redirected from login page."""
        self.client.login(username='admin', password='admin123')
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/dashboard/', response.url)
    
    def test_csrf_protection(self):
        """Test CSRF protection on login form."""
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'csrfmiddlewaretoken')


class CompanySettingsModelTest(TestCase):
    """Test CompanySettings singleton model behavior, validation, and properties."""

    def setUp(self):
        from users.models import CompanySettings
        self.CompanySettings = CompanySettings

    def test_singleton_get_instance_creates_pk_1(self):
        """Test that get_instance always retrieves or creates pk=1."""
        settings = self.CompanySettings.get_instance()
        self.assertEqual(settings.pk, 1)

    def test_singleton_save_enforces_pk_1(self):
        """Test that saving any CompanySettings instance enforces pk=1."""
        s1 = self.CompanySettings(company_name="Acme Corp")
        s1.save()
        self.assertEqual(s1.pk, 1)

        s2 = self.CompanySettings(company_name="Beta Corp")
        s2.save()
        self.assertEqual(s2.pk, 1)
        self.assertEqual(self.CompanySettings.objects.count(), 1)
        self.assertEqual(self.CompanySettings.get_instance().company_name, "Beta Corp")

    def test_name_property_and_sync(self):
        """Test that company_name and organization_name synchronize on save."""
        settings = self.CompanySettings.get_instance()
        settings.company_name = "Global Tech Academy"
        settings.save()
        self.assertEqual(settings.name, "Global Tech Academy")
        self.assertEqual(settings.organization_name, "Global Tech Academy")

    def test_custom_fields_storage(self):
        """Test storing description, certificate_footer, contact info, and theme color."""
        settings = self.CompanySettings.get_instance()
        settings.company_name = "CertTech Corp"
        settings.email = "contact@certtech.io"
        settings.phone = "+1 800 555 1234"
        settings.address = "100 Silicon Way, Tech Park"
        settings.website = "https://www.certtech.io"
        settings.description = "Leading provider of digital credentialing."
        settings.certificate_footer = "Official verifiable certificate. Protected under ISO-27001."
        settings.theme_color = "#1e40af"
        settings.save()

        reloaded = self.CompanySettings.get_instance()
        self.assertEqual(reloaded.description, "Leading provider of digital credentialing.")
        self.assertEqual(reloaded.certificate_footer, "Official verifiable certificate. Protected under ISO-27001.")
        self.assertEqual(reloaded.website, "https://www.certtech.io")
        self.assertEqual(reloaded.theme_color, "#1e40af")


class AuthorizedSignatoryModelTests(TestCase):
    """Test AuthorizedSignatory model properties, helpers, and can_delete rules."""

    def setUp(self):
        from users.models import AuthorizedSignatory, Student
        from certificates.models import Program, CertificateTemplate, Certificate
        from django.utils import timezone
        self.AuthorizedSignatory = AuthorizedSignatory

        self.signatory = AuthorizedSignatory.objects.create(
            name="Dr. Eleanor Vance",
            title="Dean of Computer Science",
            organization="Apex University",
            email="eleanor.vance@apex.edu",
            signature_image="signatures/test.png",
            is_active=True
        )

        self.student = Student.objects.create(
            full_name="Bruce Wayne",
            email="bruce@wayne.org",
            phone="1234567890",
            college="Gotham College",
            university="Gotham University",
            degree="B.S.",
            branch="Engineering",
            graduation_year=2026,
        )

        self.program = Program.objects.create(
            name="Cybersecurity Fundamentals",
            program_type="TRAINING",
            description="Program",
            duration=30,
            mode="ONLINE",
            department="IT",
            mentor="Alfred",
            skills=["Security"],
            learning_outcomes=["Defense"],
        )

        self.template = CertificateTemplate.objects.create(
            name="Standard Tech Template",
            organization="Apex University",
            description="Template",
            html_template="<html></html>",
            colors={"primary": "#000000"},
        )

        self.Certificate = Certificate

    def test_signatory_properties_and_string_representation(self):
        """Test designation and signature property accessors and __str__."""
        self.assertEqual(self.signatory.designation, "Dean of Computer Science")
        self.assertEqual(self.signatory.signature, "signatures/test.png")
        self.assertIn("Dr. Eleanor Vance - Dean of Computer Science", str(self.signatory))
        self.assertEqual(self.signatory.certificates_count, 0)
        self.assertTrue(self.signatory.can_delete())

    def test_can_delete_blocks_when_certificates_attached(self):
        """Test that can_delete returns False when certificates are linked to the signatory."""
        from django.utils import timezone
        cert = self.Certificate.objects.create(
            student=self.student,
            program=self.program,
            template=self.template,
            authorized_signatory=self.signatory,
            certificate_type="TRAINING",
            issue_date=timezone.now().date(),
            start_date=timezone.now().date(),
            duration=30,
            status="ISSUED",
        )

        self.assertEqual(self.signatory.certificates_count, 1)
        self.assertFalse(self.signatory.can_delete())


