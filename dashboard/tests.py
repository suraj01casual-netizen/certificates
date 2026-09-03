from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from users.models import Student, AuthorizedSignatory, AuditLog
from certificates.models import Program, Enrollment, Certificate, CertificateTemplate

User = get_user_model()

class StudentManagementTests(TestCase):
    def setUp(self):
        # Create a user to authenticate views
        self.user = User.objects.create_user(
            username='admin',
            email='admin@example.com',
            password='adminpassword'
        )
        self.client.login(username='admin', password='adminpassword')

        # Create some students
        self.student1 = Student.objects.create(
            full_name="Alice Smith",
            email="alice@example.com",
            phone="1234567890",
            college="Engineering College",
            university="State University",
            degree="B.Tech",
            branch="Computer Science",
            graduation_year=2026,
            is_active=True
        )

        self.student2 = Student.objects.create(
            full_name="Bob Jones",
            email="bob@example.com",
            phone="0987654321",
            college="Science College",
            university="State University",
            degree="B.Sc",
            branch="Physics",
            graduation_year=2025,
            is_active=True
        )

    def test_student_id_auto_generation(self):
        """Test that student ID is generated automatically in correct format."""
        year = timezone.now().year
        self.assertTrue(self.student1.student_id.startswith(f"STU-{year}-"))
        self.assertTrue(self.student2.student_id.startswith(f"STU-{year}-"))
        
        id1_seq = int(self.student1.student_id.split('-')[-1])
        id2_seq = int(self.student2.student_id.split('-')[-1])
        self.assertEqual(id2_seq, id1_seq + 1)

    def test_student_list_view(self):
        """Test listing, search, and pagination on student list view."""
        response = self.client.get(reverse('dashboard:student_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice Smith")
        self.assertContains(response, "Bob Jones")

        # Test Search
        response_search = self.client.get(reverse('dashboard:student_list') + "?q=Alice")
        self.assertContains(response_search, "Alice Smith")
        self.assertNotContains(response_search, "Bob Jones")

    def test_student_detail_view(self):
        """Test viewing student details."""
        response = self.client.get(reverse('dashboard:student_detail', kwargs={'pk': self.student1.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student1.full_name)
        self.assertContains(response, self.student1.student_id)

    def test_add_student(self):
        """Test adding a student with valid and invalid data (server-side validation)."""
        # Test valid submission
        add_data = {
            'full_name': 'Charlie Brown',
            'email': 'charlie@example.com',
            'phone': '1112223333',
            'college': 'Arts College',
            'university': 'State University',
            'degree': 'B.A.',
            'branch': 'History',
            'graduation_year': 2027,
            'is_active': True,
        }
        response = self.client.post(reverse('dashboard:student_add'), data=add_data)
        self.assertEqual(response.status_code, 302)
        
        charlie = Student.objects.get(email='charlie@example.com')
        self.assertEqual(charlie.full_name, 'Charlie Brown')
        self.assertTrue(charlie.student_id.startswith(f"STU-{timezone.now().year}-"))

        # Test validation error - Duplicate email
        duplicate_data = add_data.copy()
        duplicate_data['full_name'] = 'Charlie Duplicate'
        response_dup = self.client.post(reverse('dashboard:student_add'), data=duplicate_data)
        self.assertEqual(response_dup.status_code, 200)
        self.assertFormError(response_dup.context['form'], 'email', "A student with this email address already exists.")

        # Test validation error - Invalid graduation year
        invalid_year_data = add_data.copy()
        invalid_year_data['email'] = 'new_email@example.com'
        invalid_year_data['graduation_year'] = 2200
        response_year = self.client.post(reverse('dashboard:student_add'), data=invalid_year_data)
        self.assertEqual(response_year.status_code, 200)
        self.assertFormError(response_year.context['form'], 'graduation_year', "Please enter a valid graduation year between 1900 and 2100.")

    def test_edit_student(self):
        """Test updating a student's profile."""
        edit_data = {
            'full_name': 'Alice Updated',
            'email': 'alice_updated@example.com',
            'phone': '1234567890',
            'college': 'Engineering College',
            'university': 'State University',
            'degree': 'B.Tech',
            'branch': 'Computer Science',
            'graduation_year': 2026,
            'is_active': True
        }
        response = self.client.post(
            reverse('dashboard:student_edit', kwargs={'pk': self.student1.pk}),
            data=edit_data
        )
        self.assertEqual(response.status_code, 302)
        
        self.student1.refresh_from_db()
        self.assertEqual(self.student1.full_name, 'Alice Updated')
        self.assertEqual(self.student1.email, 'alice_updated@example.com')

    def test_deactivate_student(self):
        """Test deactivating a student with confirmation before deactivation."""
        response_get = self.client.get(reverse('dashboard:student_deactivate', kwargs={'pk': self.student1.pk}))
        self.assertEqual(response_get.status_code, 200)
        self.assertContains(response_get, "Confirm Deactivation")

        response_post = self.client.post(reverse('dashboard:student_deactivate', kwargs={'pk': self.student1.pk}))
        self.assertEqual(response_post.status_code, 302)
        
        self.student1.refresh_from_db()
        self.assertFalse(self.student1.is_active)


class ProgramManagementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='admin2',
            email='admin2@example.com',
            password='adminpassword'
        )
        self.client.login(username='admin2', password='adminpassword')

        self.program1 = Program.objects.create(
            name="Web Development Bootcamp",
            program_type="TRAINING",
            description="Learn HTML, CSS, JavaScript, and Django.",
            duration=30,
            mode="ONLINE",
            department="Computer Science",
            mentor="John Doe",
            skills=["HTML", "CSS", "Django"],
            learning_outcomes=["Build web apps", "Understand relational databases"],
            is_active=True
        )

        self.program2 = Program.objects.create(
            name="AI & Machine Learning Internship",
            program_type="INTERNSHIP",
            description="Work on deep learning and NLP projects.",
            duration=90,
            mode="HYBRID",
            department="Data Science",
            mentor="Jane Smith",
            skills=["Python", "TensorFlow"],
            learning_outcomes=["Train neural networks"],
            is_active=True
        )

    def test_program_id_auto_generation(self):
        """Test that program ID is generated automatically in correct format."""
        year = timezone.now().year
        self.assertTrue(self.program1.program_id.startswith(f"PRG-{year}-"))
        self.assertTrue(self.program2.program_id.startswith(f"PRG-{year}-"))
        
        id1_seq = int(self.program1.program_id.split('-')[-1])
        id2_seq = int(self.program2.program_id.split('-')[-1])
        self.assertEqual(id2_seq, id1_seq + 1)

    def test_program_list_view(self):
        """Test listing, search, and filtration on program list view."""
        response = self.client.get(reverse('dashboard:program_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Web Development Bootcamp")
        self.assertContains(response, "AI &amp; Machine Learning Internship")

        # Test Search
        response_search = self.client.get(reverse('dashboard:program_list') + "?q=Bootcamp")
        self.assertContains(response_search, "Web Development Bootcamp")
        self.assertNotContains(response_search, "AI &amp; Machine Learning Internship")

        # Test Filter by program type
        response_filter = self.client.get(reverse('dashboard:program_list') + "?program_type=INTERNSHIP")
        self.assertNotContains(response_filter, "Web Development Bootcamp")
        self.assertContains(response_filter, "AI &amp; Machine Learning Internship")

    def test_program_detail_view(self):
        """Test viewing program details."""
        response = self.client.get(reverse('dashboard:program_detail', kwargs={'pk': self.program1.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.program1.name)
        self.assertContains(response, self.program1.program_id)
        self.assertContains(response, "HTML")

    def test_add_program(self):
        """Test adding a program."""
        add_data = {
            'name': 'Cloud Computing Course',
            'program_type': 'CERTIFICATION_PROGRAM',
            'description': 'Learn AWS and Kubernetes.',
            'duration': 45,
            'mode': 'OFFLINE',
            'department': 'Cloud Division',
            'mentor': 'Dave Miller',
            'skills_text': 'AWS, Docker, Kubernetes',
            'learning_outcomes_text': 'Deploy cloud architectures',
            'is_active': True,
        }
        response = self.client.post(reverse('dashboard:program_add'), data=add_data)
        self.assertEqual(response.status_code, 302)
        
        cloud_program = Program.objects.get(name='Cloud Computing Course')
        self.assertEqual(cloud_program.department, 'Cloud Division')
        self.assertEqual(cloud_program.skills, ['AWS', 'Docker', 'Kubernetes'])
        self.assertEqual(cloud_program.learning_outcomes, ['Deploy cloud architectures'])

    def test_edit_program(self):
        """Test editing a program."""
        edit_data = {
            'name': 'Web Development Bootcamp (Updated)',
            'program_type': 'TRAINING',
            'description': 'Updated description.',
            'duration': 35,
            'mode': 'ONLINE',
            'department': 'Computer Science',
            'mentor': 'John Doe',
            'skills_text': 'HTML, CSS, Django, React',
            'learning_outcomes_text': 'Build SPAs, Full stack applications',
            'is_active': True,
        }
        response = self.client.post(
            reverse('dashboard:program_edit', kwargs={'pk': self.program1.pk}),
            data=edit_data
        )
        self.assertEqual(response.status_code, 302)
        
        self.program1.refresh_from_db()
        self.assertEqual(self.program1.name, 'Web Development Bootcamp (Updated)')
        self.assertEqual(self.program1.skills, ['HTML', 'CSS', 'Django', 'React'])

    def test_toggle_program_active(self):
        """Test deactivating/activating a program with toggle active state view."""
        response_get = self.client.get(reverse('dashboard:program_toggle_active', kwargs={'pk': self.program1.pk}))
        self.assertEqual(response_get.status_code, 200)
        self.assertContains(response_get, "Confirm Deactivation")

        response_post = self.client.post(reverse('dashboard:program_toggle_active', kwargs={'pk': self.program1.pk}))
        self.assertEqual(response_post.status_code, 302)
        
        self.program1.refresh_from_db()
        self.assertFalse(self.program1.is_active)
        
        # Toggle back to active
        response_post2 = self.client.post(reverse('dashboard:program_toggle_active', kwargs={'pk': self.program1.pk}))
        self.assertEqual(response_post2.status_code, 302)
        
        self.program1.refresh_from_db()
        self.assertTrue(self.program1.is_active)


class EnrollmentManagementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='admin3',
            email='admin3@example.com',
            password='adminpassword'
        )
        self.client.login(username='admin3', password='adminpassword')

        # Create a student and program for enrollment
        self.student = Student.objects.create(
            full_name="Alice Smith",
            email="alice@example.com",
            phone="1234567890",
            college="Engineering College",
            university="State University",
            degree="B.Tech",
            branch="Computer Science",
            graduation_year=2026,
            is_active=True
        )

        self.program = Program.objects.create(
            name="Web Development Bootcamp",
            program_type="TRAINING",
            description="Learn HTML, CSS, JavaScript, and Django.",
            duration=30,
            mode="ONLINE",
            department="Computer Science",
            mentor="John Doe",
            skills=["HTML", "CSS", "Django"],
            learning_outcomes=["Build web apps"],
            is_active=True
        )

    def test_enrollment_id_auto_generation(self):
        """Test that enrollment ID is generated automatically in correct format."""
        year = timezone.now().year
        enrollment = Enrollment.objects.create(
            student=self.student,
            program=self.program,
            start_date="2026-01-01",
            end_date="2026-01-31",
            duration=30,
            mentor="John Doe",
            department="Computer Science",
            project_title="E-commerce Website",
            project_description="Build a full-stack e-commerce site.",
            skills=["HTML", "CSS"],
            learning_outcomes=["Build web apps"],
            attendance_percentage=95.50,
            performance_rating=4.5,
            status="ONGOING"
        )
        self.assertTrue(enrollment.enrollment_id.startswith(f"ENR-{year}-"))

    def test_valid_enrollment(self):
        """Test creating a valid enrollment."""
        add_data = {
            'student': self.student.pk,
            'program': self.program.pk,
            'start_date': '2026-01-01',
            'end_date': '2026-01-31',
            'duration': 30,
            'mentor': 'John Doe',
            'department': 'Computer Science',
            'project_title': 'E-commerce Website',
            'project_description': 'Build a full-stack e-commerce site.',
            'skills_text': 'HTML, CSS, Django',
            'learning_outcomes_text': 'Build web apps, Deploy to cloud',
            'attendance_percentage': 95.50,
            'performance_rating': 4.5,
            'status': 'ONGOING',
        }
        response = self.client.post(reverse('dashboard:enrollment_add'), data=add_data)
        self.assertEqual(response.status_code, 302)
        
        enrollment = Enrollment.objects.get(project_title='E-commerce Website')
        self.assertEqual(enrollment.student, self.student)
        self.assertEqual(enrollment.program, self.program)
        self.assertEqual(enrollment.duration, 30)
        self.assertEqual(enrollment.skills, ['HTML', 'CSS', 'Django'])
        self.assertEqual(enrollment.learning_outcomes, ['Build web apps', 'Deploy to cloud'])

    def test_invalid_date_enrollment(self):
        """Test that end_date before start_date is rejected."""
        add_data = {
            'student': self.student.pk,
            'program': self.program.pk,
            'start_date': '2026-02-01',
            'end_date': '2026-01-01',  # End date before start date
            'duration': 30,
            'mentor': 'John Doe',
            'department': 'Computer Science',
            'project_title': 'Invalid Date Project',
            'project_description': 'Project with invalid dates.',
            'skills_text': 'Python',
            'learning_outcomes_text': 'Learn Python',
            'attendance_percentage': 90.00,
            'performance_rating': 4.0,
            'status': 'ONGOING',
        }
        response = self.client.post(reverse('dashboard:enrollment_add'), data=add_data)
        self.assertEqual(response.status_code, 200)  # Form re-rendered with errors
        self.assertFormError(response.context['form'], 'end_date', "End date cannot be before the start date.")

    def test_duplicate_enrollment(self):
        """Test that duplicate enrollment (same student, program, start_date) is prevented."""
        # Create an initial enrollment
        Enrollment.objects.create(
            student=self.student,
            program=self.program,
            start_date="2026-01-01",
            end_date="2026-01-31",
            duration=30,
            mentor="John Doe",
            department="Computer Science",
            project_title="First Project",
            project_description="First project description.",
            skills=["HTML"],
            learning_outcomes=["Build web apps"],
            attendance_percentage=95.00,
            performance_rating=4.0,
            status="ONGOING"
        )

        # Attempt to create a duplicate with same student, program, start_date
        add_data = {
            'student': self.student.pk,
            'program': self.program.pk,
            'start_date': '2026-01-01',
            'end_date': '2026-02-15',
            'duration': 45,
            'mentor': 'John Doe',
            'department': 'Computer Science',
            'project_title': 'Duplicate Project',
            'project_description': 'Duplicate project description.',
            'skills_text': 'Python',
            'learning_outcomes_text': 'Learn Python',
            'attendance_percentage': 90.00,
            'performance_rating': 4.0,
            'status': 'ONGOING',
        }
        response = self.client.post(reverse('dashboard:enrollment_add'), data=add_data)
        self.assertEqual(response.status_code, 200)  # Form re-rendered with errors
        self.assertFormError(response.context['form'], 'student', "Enrollment with this student, program, and start date already exists.")

    def test_student_program_relationships(self):
        """Test that enrollment correctly links student and program."""
        enrollment = Enrollment.objects.create(
            student=self.student,
            program=self.program,
            start_date="2026-03-01",
            end_date="2026-03-31",
            duration=30,
            mentor="John Doe",
            department="Computer Science",
            project_title="Relationship Test Project",
            project_description="Testing relationships.",
            skills=["Python"],
            learning_outcomes=["Learn Python"],
            attendance_percentage=90.00,
            performance_rating=4.0,
            status="ONGOING"
        )
        
        # Verify the relationships
        self.assertEqual(enrollment.student, self.student)
        self.assertEqual(enrollment.program, self.program)
        self.assertIn(enrollment, self.student.enrollments.all())
        self.assertIn(enrollment, self.program.enrollments.all())

    def test_enrollment_detail_view(self):
        """Test viewing enrollment details."""
        enrollment = Enrollment.objects.create(
            student=self.student,
            program=self.program,
            start_date="2026-03-01",
            end_date="2026-03-31",
            duration=30,
            mentor="John Doe",
            department="Computer Science",
            project_title="Detail View Project",
            project_description="Testing detail view.",
            skills=["Python"],
            learning_outcomes=["Learn Python"],
            attendance_percentage=90.00,
            performance_rating=4.0,
            status="ONGOING"
        )
        response = self.client.get(reverse('dashboard:enrollment_detail', kwargs={'pk': enrollment.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, enrollment.enrollment_id)
        self.assertContains(response, "Detail View Project")
        self.assertContains(response, self.student.full_name)
        self.assertContains(response, self.program.name)

    def test_edit_enrollment(self):
        """Test editing an enrollment."""
        enrollment = Enrollment.objects.create(
            student=self.student,
            program=self.program,
            start_date="2026-03-01",
            end_date="2026-03-31",
            duration=30,
            mentor="John Doe",
            department="Computer Science",
            project_title="Original Project",
            project_description="Original description.",
            skills=["Python"],
            learning_outcomes=["Learn Python"],
            attendance_percentage=90.00,
            performance_rating=4.0,
            status="ONGOING"
        )
        
        edit_data = {
            'student': self.student.pk,
            'program': self.program.pk,
            'start_date': '2026-03-01',
            'end_date': '2026-04-15',
            'duration': 45,
            'mentor': 'Jane Smith',
            'department': 'Data Science',
            'project_title': 'Updated Project',
            'project_description': 'Updated description.',
            'skills_text': 'Python, Django',
            'learning_outcomes_text': 'Learn Python, Build APIs',
            'attendance_percentage': 92.00,
            'performance_rating': 4.5,
            'status': 'COMPLETED',
        }
        response = self.client.post(
            reverse('dashboard:enrollment_edit', kwargs={'pk': enrollment.pk}),
            data=edit_data
        )
        self.assertEqual(response.status_code, 302)
        
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.project_title, 'Updated Project')
        self.assertEqual(enrollment.mentor, 'Jane Smith')
        self.assertEqual(enrollment.status, 'COMPLETED')
        self.assertEqual(enrollment.skills, ['Python', 'Django'])

    def test_enrollment_model_clean_invalid_date(self):
        """Test that model-level clean raises ValidationError when end_date < start_date."""
        from django.core.exceptions import ValidationError
        import datetime
        enrollment = Enrollment(
            student=self.student,
            program=self.program,
            start_date=datetime.date(2026, 5, 10),
            end_date=datetime.date(2026, 5, 1),
            mentor="John Doe",
            department="Computer Science",
            project_title="Invalid Model Date",
            project_description="Testing model clean.",
            attendance_percentage=90.0,
            performance_rating=4.0,
            status="ONGOING"
        )
        with self.assertRaises(ValidationError):
            enrollment.clean()

    def test_enrollment_model_auto_duration_on_save(self):
        """Test that saving an enrollment auto-calculates duration if not provided."""
        import datetime
        enrollment = Enrollment.objects.create(
            student=self.student,
            program=self.program,
            start_date=datetime.date(2026, 6, 1),
            end_date=datetime.date(2026, 6, 21),
            mentor="Mentor Name",
            department="AI Labs",
            project_title="NLP Analyzer",
            project_description="Building an NLP pipeline.",
            skills=["NLP", "Python"],
            learning_outcomes=["Understand Transformers"],
            attendance_percentage=98.0,
            performance_rating=4.8,
            status="COMPLETED"
        )
        self.assertEqual(enrollment.duration, 20)


# ===========================================================================
# Certificate Management Tests
# ===========================================================================

class CertificateManagementTests(TestCase):
    """Verify admin dashboard certificate listing, searching, filtering, and actions."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="cert_admin",
            email="cert_admin@example.com",
            password="adminpassword123",
        )
        self.client.login(username="cert_admin", password="adminpassword123")

        # Students
        self.student_a = Student.objects.create(
            full_name="Diana Prince",
            email="diana.prince@themyscira.org",
            phone="1112223333",
            college="Amazon Academy",
            university="Olympus University",
            degree="B.S.",
            branch="Defense Engineering",
            graduation_year=2026,
            is_active=True,
        )
        self.student_b = Student.objects.create(
            full_name="Barry Allen",
            email="barry.allen@ccpd.org",
            phone="4445556666",
            college="Central City College",
            university="State University",
            degree="B.S.",
            branch="Forensic Science",
            graduation_year=2025,
            is_active=True,
        )

        # Programs
        self.program_internship = Program.objects.create(
            name="Quantum Computing Research Internship",
            program_type="INTERNSHIP",
            duration=90,
            mode="HYBRID",
            department="Physics & Quantum Architecture",
            is_active=True,
        )
        self.program_training = Program.objects.create(
            name="Applied Machine Learning Bootcamp",
            program_type="TRAINING",
            duration=30,
            mode="ONLINE",
            department="Artificial Intelligence",
            is_active=True,
        )

        # Template & Signatory
        self.template = CertificateTemplate.objects.create(
            name="Standard Gold Template",
            organization="Star Labs Institute",
            description="Gold certification layout",
            is_active=True,
        )
        self.signatory = AuthorizedSignatory.objects.create(
            name="Dr. Harrison Wells",
            title="Chief Scientist",
            organization="Star Labs Institute",
            email="harrison@starlabs.org",
        )

        # Certificates with distinct attributes
        import datetime
        self.cert_1 = Certificate.objects.create(
            student=self.student_a,
            program=self.program_internship,
            certificate_type="INTERNSHIP",
            issue_date=datetime.date(2026, 3, 1),
            start_date=datetime.date(2025, 12, 1),
            end_date=datetime.date(2026, 3, 1),
            duration=90,
            status="ISSUED",
            template=self.template,
            authorized_signatory=self.signatory,
        )

        self.cert_2 = Certificate.objects.create(
            student=self.student_b,
            program=self.program_training,
            certificate_type="TRAINING",
            issue_date=datetime.date(2026, 4, 15),
            start_date=datetime.date(2026, 3, 15),
            end_date=datetime.date(2026, 4, 15),
            duration=30,
            status="DRAFT",
            template=self.template,
            authorized_signatory=self.signatory,
        )

    def test_certificate_list_view_renders_all_certificates(self):
        """GET /dashboard/certificates/ displays metrics and certificate records."""
        url = reverse("dashboard:certificate_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Certificate Management")
        self.assertContains(response, self.cert_1.certificate_id)
        self.assertContains(response, self.cert_2.certificate_id)
        self.assertContains(response, "Diana Prince")
        self.assertContains(response, "Barry Allen")

    def test_search_certificates_by_name_and_id(self):
        """Search query filters by recipient name and certificate ID."""
        url = reverse("dashboard:certificate_list")

        # Search by student name
        res_name = self.client.get(f"{url}?q=Diana")
        self.assertContains(res_name, self.cert_1.certificate_id)
        self.assertNotContains(res_name, self.cert_2.certificate_id)

        # Search by Certificate ID
        res_id = self.client.get(f"{url}?q={self.cert_2.certificate_id}")
        self.assertContains(res_id, self.cert_2.certificate_id)
        self.assertNotContains(res_id, self.cert_1.certificate_id)

    def test_filter_by_status(self):
        """Filter by status=ISSUED vs status=DRAFT."""
        url = reverse("dashboard:certificate_list")

        res_issued = self.client.get(f"{url}?status=ISSUED")
        self.assertContains(res_issued, self.cert_1.certificate_id)
        self.assertNotContains(res_issued, self.cert_2.certificate_id)

        res_draft = self.client.get(f"{url}?status=DRAFT")
        self.assertContains(res_draft, self.cert_2.certificate_id)
        self.assertNotContains(res_draft, self.cert_1.certificate_id)

    def test_filter_by_program(self):
        """Filter by program ID."""
        url = reverse("dashboard:certificate_list")

        res_prog = self.client.get(f"{url}?program={self.program_internship.pk}")
        self.assertContains(res_prog, self.cert_1.certificate_id)
        self.assertNotContains(res_prog, self.cert_2.certificate_id)

    def test_filter_by_certificate_type(self):
        """Filter by certificate_type=INTERNSHIP vs TRAINING."""
        url = reverse("dashboard:certificate_list")

        res_type = self.client.get(f"{url}?certificate_type=INTERNSHIP")
        self.assertContains(res_type, self.cert_1.certificate_id)
        self.assertNotContains(res_type, self.cert_2.certificate_id)

    def test_filter_by_issue_date(self):
        """Filter by exact issue_date=YYYY-MM-DD."""
        url = reverse("dashboard:certificate_list")

        res_date = self.client.get(f"{url}?issue_date=2026-03-01")
        self.assertContains(res_date, self.cert_1.certificate_id)
        self.assertNotContains(res_date, self.cert_2.certificate_id)

    def test_certificate_detail_view_renders(self):
        """GET /dashboard/certificate/<pk>/ renders complete details, verification URL, and QR."""
        url = reverse("dashboard:certificate_detail", kwargs={"pk": self.cert_1.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.cert_1.certificate_id)
        self.assertContains(response, self.student_a.full_name)
        self.assertContains(response, self.program_internship.name)
        self.assertContains(response, "Open Public Verification")
        self.assertContains(response, "Copy Verification URL")
        self.assertContains(response, self.cert_1.verification_token)

    def test_certificate_download_endpoint(self):
        """GET /dashboard/certificate/<pk>/download/ returns application/pdf stream."""
        url = reverse("dashboard:certificate_download", kwargs={"pk": self.cert_1.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_revoke_issued_certificate_success(self):
        """Admin can revoke an ISSUED certificate with mandatory reason and AuditLog."""
        url = reverse("dashboard:certificate_revoke", kwargs={"pk": self.cert_1.pk})
        original_id = self.cert_1.certificate_id
        original_token = self.cert_1.verification_token

        response = self.client.post(url, data={"revocation_reason": "Academic policy violation"})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("dashboard:certificate_detail", kwargs={"pk": self.cert_1.pk}))

        self.cert_1.refresh_from_db()
        self.assertEqual(self.cert_1.status, "REVOKED")
        self.assertEqual(self.cert_1.revocation_reason, "Academic policy violation")
        self.assertIsNotNone(self.cert_1.revoked_at)

        # Invariants preserved
        self.assertEqual(self.cert_1.certificate_id, original_id)
        self.assertEqual(self.cert_1.verification_token, original_token)

        # AuditLog record
        audit = AuditLog.objects.filter(action="REVOKE", object_id=original_id).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.user_email, self.user.email)
        self.assertEqual(audit.changes["revocation_reason"], "Academic policy violation")

    def test_revoke_without_reason_fails(self):
        """Revoking without reason fails and preserves ISSUED status."""
        url = reverse("dashboard:certificate_revoke", kwargs={"pk": self.cert_1.pk})
        response = self.client.post(url, data={"revocation_reason": "   "})

        self.assertEqual(response.status_code, 302)
        self.cert_1.refresh_from_db()
        self.assertEqual(self.cert_1.status, "ISSUED")

    def test_cannot_revoke_already_revoked_certificate(self):
        """Cannot revoke an already revoked certificate."""
        self.cert_1.revoke("First revocation", user=self.user)
        self.assertEqual(self.cert_1.status, "REVOKED")

        url = reverse("dashboard:certificate_revoke", kwargs={"pk": self.cert_1.pk})
        response = self.client.post(url, data={"revocation_reason": "Attempting second revocation"})
        self.assertEqual(response.status_code, 302)

        self.cert_1.refresh_from_db()
        self.assertEqual(self.cert_1.revocation_reason, "First revocation")

    def test_cannot_revoke_draft_certificate(self):
        """Cannot revoke a DRAFT certificate."""
        url = reverse("dashboard:certificate_revoke", kwargs={"pk": self.cert_2.pk})
        response = self.client.post(url, data={"revocation_reason": "Draft revoke attempt"})

        self.assertEqual(response.status_code, 302)
        self.cert_2.refresh_from_db()
        self.assertEqual(self.cert_2.status, "DRAFT")

    def test_public_verification_immediately_reflects_revoked(self):
        """Public verification URL continues working (200 OK) and immediately displays CERTIFICATE REVOKED."""
        self.cert_1.revoke("Plagiarism confirmed", user=self.user)
        verify_url = reverse("verify:verify_token", kwargs={"token": self.cert_1.verification_token})

        response = self.client.get(verify_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CERTIFICATE REVOKED")
        self.assertNotContains(response, "Download Official PDF")

    def test_certificate_create_workflow_with_modern_template(self):
        """Admin selects Modern template in creation form, previews it, and issues certificate."""
        from certificates.models import CertificateTemplate
        modern_tmpl, _ = CertificateTemplate.objects.get_or_create(
            name="Modern Minimalist",
            defaults={
                'design_style': 'MODERN',
                'html_template': 'certificates/templates/modern.html',
                'is_active': True,
            }
        )

        create_url = reverse("dashboard:certificate_create")
        post_data = {
            "student": self.student_a.pk,
            "program": self.program_internship.pk,
            "certificate_type": "INTERNSHIP",
            "template": modern_tmpl.pk,
            "authorized_signatory": self.signatory.pk,
            "start_date": "2026-01-01",
            "end_date": "2026-03-31",
            "issue_date": "2026-04-01",
            "duration": 90,
        }

        # Step 1: Submit creation form -> redirects to Preview
        res_post = self.client.post(create_url, data=post_data)
        self.assertEqual(res_post.status_code, 302)
        self.assertRedirects(res_post, reverse("dashboard:certificate_preview"))

        # Step 2: GET Preview -> contains modern design snippet and student name
        res_prev = self.client.get(reverse("dashboard:certificate_preview"))
        self.assertEqual(res_prev.status_code, 200)
        self.assertContains(res_prev, "top-gradient-bar")
        self.assertContains(res_prev, self.student_a.full_name)

        # Step 3: POST Confirm -> issues certificate
        res_conf = self.client.post(reverse("dashboard:certificate_confirm"), follow=True)
        self.assertEqual(res_conf.status_code, 200)
        self.assertContains(res_conf, "successfully issued")

        # Verify created certificate in DB
        issued_cert = Certificate.objects.filter(
            student=self.student_a,
            program=self.program_internship,
            template=modern_tmpl,
        ).first()
        self.assertIsNotNone(issued_cert)
        self.assertEqual(issued_cert.status, "ISSUED")
        self.assertTrue(issued_cert.certificate_pdf)



class CompanySettingsFormAndViewTests(TestCase):
    """Test CompanySettings form validation and dashboard view."""

    @classmethod
    def setUpTestData(cls):
        from users.models import CompanySettings, AuditLog
        from django.contrib.auth.models import User
        cls.CompanySettings = CompanySettings
        cls.AuditLog = AuditLog
        cls.admin_user = User.objects.create_superuser(
            username='admin_settings',
            email='admin_settings@test.local',
            password='adminpassword123'
        )

    def setUp(self):
        self.client.login(username='admin_settings', password='adminpassword123')

    def test_settings_form_valid_data(self):
        """Test CompanySettingsForm with valid fields."""
        from dashboard.forms import CompanySettingsForm
        form = CompanySettingsForm(data={
            'company_name': 'Alpha Certification Institute',
            'email': 'support@alphacert.org',
            'phone': '+1 (555) 234-5678',
            'website': 'https://www.alphacert.org',
            'address': '456 Knowledge Way, Suite 100',
            'description': 'Global professional accreditation organization.',
            'certificate_footer': 'This is an authentic verified credential.',
            'theme_color': '#1d4ed8',
        })
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save()
        self.assertEqual(instance.company_name, 'Alpha Certification Institute')
        self.assertEqual(instance.organization_name, 'Alpha Certification Institute')

    def test_settings_form_invalid_company_name(self):
        """Test that company_name cannot be empty or under 2 chars."""
        from dashboard.forms import CompanySettingsForm
        form = CompanySettingsForm(data={'company_name': ' '})
        self.assertFalse(form.is_valid())
        self.assertIn('company_name', form.errors)

    def test_settings_form_website_auto_prefix(self):
        """Test that website without protocol automatically gets https:// prefix."""
        from dashboard.forms import CompanySettingsForm
        form = CompanySettingsForm(data={
            'company_name': 'Beta Institute',
            'website': 'www.betainstitute.edu',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['website'], 'https://www.betainstitute.edu')

    def test_settings_form_invalid_phone(self):
        """Test rejection of non-phone strings."""
        from dashboard.forms import CompanySettingsForm
        form = CompanySettingsForm(data={
            'company_name': 'Beta Institute',
            'phone': 'invalid_phone_abc',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('phone', form.errors)

    def test_settings_form_logo_invalid_extension(self):
        """Test rejection of unsupported file extensions."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from dashboard.forms import CompanySettingsForm
        fake_file = SimpleUploadedFile("malicious.exe", b"binary content", content_type="application/octet-stream")
        form = CompanySettingsForm(
            data={'company_name': 'Gamma Corp'},
            files={'logo': fake_file}
        )
        self.assertFalse(form.is_valid())
        self.assertIn('logo', form.errors)

    def test_settings_form_logo_oversized(self):
        """Test rejection of logo files exceeding 2 MB."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from dashboard.forms import CompanySettingsForm
        # 2.5 MB dummy file
        oversized = SimpleUploadedFile("big_logo.png", b"0" * (2500 * 1024), content_type="image/png")
        form = CompanySettingsForm(
            data={'company_name': 'Gamma Corp'},
            files={'logo': oversized}
        )
        self.assertFalse(form.is_valid())
        self.assertIn('logo', form.errors)

    def test_settings_form_valid_image_upload(self):
        """Test valid PNG logo upload."""
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from dashboard.forms import CompanySettingsForm

        img = Image.new('RGB', (100, 100), color='blue')
        img_bytes = io.BytesIO()
        img.save(img_bytes, format='PNG')
        img_bytes.seek(0)

        uploaded = SimpleUploadedFile("valid_logo.png", img_bytes.read(), content_type="image/png")
        form = CompanySettingsForm(
            data={'company_name': 'Delta Academy'},
            files={'logo': uploaded}
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_get_company_settings_view(self):
        """GET /dashboard/settings/ loads with 200 OK and pre-filled form."""
        url = reverse('dashboard:company_settings')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Company Settings")
        self.assertContains(response, "Live Organization Card")
        self.assertContains(response, "Certificate Footer Preview")

    def test_post_company_settings_view_updates_singleton_and_logs_audit(self):
        """POST /dashboard/settings/ updates CompanySettings and creates an AuditLog record."""
        url = reverse('dashboard:company_settings')
        data = {
            'company_name': 'Apex Certification Authority',
            'email': 'info@apexauthority.org',
            'phone': '+1 (800) 123-4567',
            'website': 'https://www.apexauthority.org',
            'address': '789 Summit Peak Dr, Denver, CO',
            'description': 'Accredited credential issuer.',
            'certificate_footer': 'Verified ISO-9001 certified credential authority.',
            'theme_color': '#059669',
        }
        response = self.client.post(url, data=data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Company settings have been updated successfully.")

        settings = self.CompanySettings.get_instance()
        self.assertEqual(settings.company_name, 'Apex Certification Authority')
        self.assertEqual(settings.email, 'info@apexauthority.org')
        self.assertEqual(settings.certificate_footer, 'Verified ISO-9001 certified credential authority.')

        # Verify AuditLog entry
        log = self.AuditLog.objects.filter(object_type='CompanySettings', action='UPDATE').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.user_email, 'admin_settings@test.local')


class SignatoryCRUDTests(TestCase):
    """Test Authorized Signatory management form validation, CRUD views, active toggling, and safe deletion."""

    @classmethod
    def setUpTestData(cls):
        from users.models import AuthorizedSignatory, AuditLog, Student
        from certificates.models import Program, CertificateTemplate, Certificate
        from django.contrib.auth.models import User
        from django.utils import timezone

        cls.AuthorizedSignatory = AuthorizedSignatory
        cls.AuditLog = AuditLog
        cls.Certificate = Certificate

        cls.admin_user = User.objects.create_superuser(
            username='admin_signatory',
            email='admin_sig@test.local',
            password='sigpassword123'
        )

        cls.student = Student.objects.create(
            full_name="Diana Prince",
            email="diana@themyscira.org",
            phone="1234567890",
            college="Amazon Academy",
            university="Themyscira Univ",
            degree="B.A.",
            branch="Diplomacy",
            graduation_year=2026,
        )

        cls.program = Program.objects.create(
            name="Leadership & Diplomacy",
            program_type="INTERNSHIP",
            description="Program",
            duration=60,
            mode="HYBRID",
            department="Gov",
            mentor="Hippolyta",
            skills=["Leadership"],
            learning_outcomes=["Conflict Resolution"],
        )

        cls.template = CertificateTemplate.objects.create(
            name="Executive Leadership",
            organization="Diplomatic Academy",
            description="Template",
            html_template="<html></html>",
            colors={"primary": "#000000"},
        )

    def setUp(self):
        self.client.login(username='admin_signatory', password='sigpassword123')

    def _create_sample_image(self):
        import io
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        img = Image.new('RGBA', (120, 40), color=(0, 0, 128, 255))
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return SimpleUploadedFile("signature.png", buf.read(), content_type="image/png")

    def test_signatory_form_valid_on_create(self):
        """Test AuthorizedSignatoryForm with valid inputs and signature upload."""
        from dashboard.forms import AuthorizedSignatoryForm
        sig_file = self._create_sample_image()
        form = AuthorizedSignatoryForm(
            data={
                'name': 'Dr. Robert Oppenheimer',
                'title': 'Director of Research',
                'organization': 'Institute for Advanced Study',
                'email': 'oppenheimer@ias.edu',
                'is_active': True,
            },
            files={'signature_image': sig_file}
        )
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save()
        self.assertEqual(instance.name, 'Dr. Robert Oppenheimer')
        self.assertEqual(instance.title, 'Director of Research')
        self.assertTrue(instance.is_active)

    def test_signatory_form_requires_signature_on_create(self):
        """Creating a new signatory requires a signature image."""
        from dashboard.forms import AuthorizedSignatoryForm
        form = AuthorizedSignatoryForm(data={
            'name': 'Dr. Richard Feynman',
            'title': 'Professor of Physics',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('signature_image', form.errors)

    def test_signatory_form_rejects_oversize_signature(self):
        """Reject signature uploads larger than 2 MB."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from dashboard.forms import AuthorizedSignatoryForm
        oversized = SimpleUploadedFile("big_sig.png", b"0" * (2500 * 1024), content_type="image/png")
        form = AuthorizedSignatoryForm(
            data={
                'name': 'Dr. Marie Curie',
                'title': 'Chief Radiologist',
            },
            files={'signature_image': oversized}
        )
        self.assertFalse(form.is_valid())
        self.assertIn('signature_image', form.errors)

    def test_signatory_list_view_renders_and_filters(self):
        """GET /dashboard/signatories/ displays summary metrics, search, and list."""
        sig1 = self.AuthorizedSignatory.objects.create(
            name="Professor Charles Xavier",
            title="Headmaster",
            organization="Xavier Institute",
            email="charles@xmen.org",
            signature_image="signatures/test1.png",
            is_active=True
        )
        sig2 = self.AuthorizedSignatory.objects.create(
            name="Erik Lehnsherr",
            title="Chancellor",
            organization="Brotherhood Institute",
            email="erik@brotherhood.org",
            signature_image="signatures/test2.png",
            is_active=False
        )

        url = reverse('dashboard:signatory_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Authorized Signatories")
        self.assertContains(response, "Professor Charles Xavier")
        self.assertContains(response, "Erik Lehnsherr")

        # Test Search filter
        search_res = self.client.get(f"{url}?q=Charles")
        self.assertContains(search_res, "Professor Charles Xavier")
        self.assertNotContains(search_res, "Erik Lehnsherr")

        # Test Status filter
        active_res = self.client.get(f"{url}?status=active")
        self.assertContains(active_res, "Professor Charles Xavier")
        self.assertNotContains(active_res, "Erik Lehnsherr")

    def test_signatory_create_view_post_success(self):
        """POST /dashboard/signatory/add/ creates record and logs AuditLog."""
        url = reverse('dashboard:signatory_add')
        sig_file = self._create_sample_image()
        data = {
            'name': 'Dr. Stephen Strange',
            'title': 'Sorcerer Supreme',
            'organization': 'Kamar-Taj Academy',
            'email': 'strange@kamartaj.org',
            'is_active': True,
            'signature_image': sig_file,
        }
        response = self.client.post(url, data=data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "was created successfully")

        sig = self.AuthorizedSignatory.objects.filter(name='Dr. Stephen Strange').first()
        self.assertIsNotNone(sig)
        self.assertEqual(sig.title, 'Sorcerer Supreme')

        # Check AuditLog
        log = self.AuditLog.objects.filter(object_type='AuthorizedSignatory', action='CREATE').first()
        self.assertIsNotNone(log)

    def test_signatory_update_view(self):
        """POST /dashboard/signatory/<id>/edit/ updates fields."""
        sig = self.AuthorizedSignatory.objects.create(
            name="Bruce Banner",
            title="Lead Researcher",
            organization="Stark Labs",
            signature_image="signatures/test.png",
            is_active=True
        )
        url = reverse('dashboard:signatory_edit', kwargs={'pk': sig.pk})
        data = {
            'name': 'Dr. Bruce Banner, Ph.D.',
            'title': 'Head of Biochemistry',
            'organization': 'Stark Industries',
            'email': 'banner@stark.org',
            'is_active': True,
        }
        response = self.client.post(url, data=data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "was updated successfully")

        sig.refresh_from_db()
        self.assertEqual(sig.name, 'Dr. Bruce Banner, Ph.D.')
        self.assertEqual(sig.title, 'Head of Biochemistry')

    def test_signatory_toggle_active_view(self):
        """POST /dashboard/signatory/<id>/toggle-active/ toggles active flag."""
        sig = self.AuthorizedSignatory.objects.create(
            name="Tony Stark",
            title="Chief Innovator",
            signature_image="signatures/test.png",
            is_active=True
        )
        url = reverse('dashboard:signatory_toggle_active', kwargs={'pk': sig.pk})
        
        # Deactivate
        res1 = self.client.post(url, follow=True)
        self.assertEqual(res1.status_code, 200)
        sig.refresh_from_db()
        self.assertFalse(sig.is_active)
        self.assertContains(res1, "has been deactivated")

        # Reactivate
        res2 = self.client.post(url, follow=True)
        self.assertEqual(res2.status_code, 200)
        sig.refresh_from_db()
        self.assertTrue(sig.is_active)
        self.assertContains(res2, "has been activated")

    def test_signatory_safe_delete_success(self):
        """POST /dashboard/signatory/<id>/delete/ deletes signatory when 0 certificates attached."""
        sig = self.AuthorizedSignatory.objects.create(
            name="Peter Parker",
            title="Lab Assistant",
            signature_image="signatures/test.png",
            is_active=True
        )
        url = reverse('dashboard:signatory_delete', kwargs={'pk': sig.pk})
        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "was safely deleted")
        self.assertFalse(self.AuthorizedSignatory.objects.filter(pk=sig.pk).exists())

    def test_signatory_delete_blocked_when_certificates_attached(self):
        """POST /dashboard/signatory/<id>/delete/ safely blocks deletion when certificates exist."""
        from django.utils import timezone
        sig = self.AuthorizedSignatory.objects.create(
            name="Nick Fury",
            title="Director",
            signature_image="signatures/test.png",
            is_active=True
        )
        # Attach a certificate
        self.Certificate.objects.create(
            student=self.student,
            program=self.program,
            template=self.template,
            authorized_signatory=sig,
            certificate_type="INTERNSHIP",
            issue_date=timezone.now().date(),
            start_date=timezone.now().date(),
            duration=60,
            status="ISSUED",
        )

        url = reverse('dashboard:signatory_delete', kwargs={'pk': sig.pk})
        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "because 1 certificate(s) are signed by them")
        self.assertContains(response, "Deactivate")
        
        # Verify record still exists in DB
        self.assertTrue(self.AuthorizedSignatory.objects.filter(pk=sig.pk).exists())




