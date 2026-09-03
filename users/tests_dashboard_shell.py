"""
Dashboard shell tests to verify UI components render correctly
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse


class DashboardShellTest(TestCase):
    """Test dashboard shell UI components"""

    def setUp(self):
        """Set up test client and test user"""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123',
            first_name='John',
            last_name='Doe'
        )

    def test_dashboard_shell_loads(self):
        """Test that dashboard shell template loads successfully"""
        self.client.login(email='test@example.com', username='testuser', password='testpass123')
        # Django login doesn't support email by default, so we use username
        self.client.force_login(self.user)

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'dashboard/dashboard_shell.html')

    def test_dashboard_contains_sidebar(self):
        """Test that dashboard contains sidebar component"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'id="sidebar"')
        self.assertContains(response, 'sidebar-logo')
        self.assertContains(response, 'nav-list')

    def test_dashboard_contains_navbar(self):
        """Test that dashboard contains navbar component"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'dashboard-navbar')
        self.assertContains(response, 'navbar-menu-toggle')
        self.assertContains(response, 'user-menu-toggle')

    def test_dashboard_contains_stats_cards(self):
        """Test that dashboard contains stats cards"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'stats-grid')
        self.assertContains(response, 'stat-card')
        self.assertContains(response, 'stat-empty-state')

    def test_dashboard_contains_activity_feed(self):
        """Test that dashboard contains activity feed"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'activity-section')
        self.assertContains(response, 'activity-feed')
        self.assertContains(response, 'activity-empty-state')

    def test_dashboard_contains_quick_actions(self):
        """Test that dashboard contains quick actions"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'quick-actions-section')
        self.assertContains(response, 'action-btn')

    def test_dashboard_contains_profile_card(self):
        """Test that dashboard contains profile card"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'profile-card')
        self.assertContains(response, 'profile-name')
        self.assertContains(response, 'profile-email')

    def test_dashboard_contains_footer(self):
        """Test that dashboard contains footer"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'dashboard-footer')

    def test_dashboard_displays_user_name(self):
        """Test that dashboard displays user's name"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'John')

    def test_dashboard_displays_user_email(self):
        """Test that dashboard displays user's email"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'test@example.com')

    def test_dashboard_includes_css(self):
        """Test that dashboard includes dashboard CSS"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'css/dashboard.css')

    def test_dashboard_includes_js(self):
        """Test that dashboard includes dashboard JavaScript"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'js/dashboard.js')

    def test_dashboard_responsive_navbar_elements(self):
        """Test that dashboard has responsive navbar elements"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'navbar-menu-toggle')
        self.assertContains(response, 'navbar-search')
        self.assertContains(response, 'navbar-notifications')

    def test_dashboard_contains_mobile_overlay(self):
        """Test that dashboard contains mobile menu overlay"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'id="sidebarOverlay"')
        self.assertContains(response, 'id="userMenu"')

    def test_dashboard_page_title(self):
        """Test that dashboard sets correct page title"""
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.context['page_title'], 'Dashboard')

    def test_unauthenticated_redirects_to_login(self):
        """Test that unauthenticated users are redirected to login"""
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login/', response.url)
