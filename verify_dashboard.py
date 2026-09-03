#!/usr/bin/env python
"""
Dashboard shell visual verification script
Run this to test the dashboard visually without a browser
"""

import os
import sys
from pathlib import Path

# Add project to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

# Add testserver to allowed hosts for testing
from django.conf import settings
if 'testserver' not in settings.ALLOWED_HOSTS:
    settings.ALLOWED_HOSTS.append('testserver')

from django.test import Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.template.loader import render_to_string

def verify_dashboard():
    """Verify dashboard shell renders correctly"""
    
    print("\n" + "="*70)
    print("DASHBOARD SHELL VISUAL VERIFICATION")
    print("="*70 + "\n")
    
    # Get or create test user with profile
    user, created = User.objects.get_or_create(
        username='dashboardtest',
        defaults={
            'email': 'dashboardtest@example.com',
            'first_name': 'Test',
            'last_name': 'User'
        }
    )
    if created:
        user.set_password('dashboardpass123')
        user.save()
    elif not user.first_name or not user.email:
        user.email = 'dashboardtest@example.com'
        user.first_name = 'Test'
        user.last_name = 'User'
        user.save()
    
    client = Client()
    client.force_login(user)
    
    # Get dashboard response
    response = client.get(reverse('dashboard'))
    
    print(f"✓ Status Code: {response.status_code}")
    print(f"✓ Content Type: {response.get('Content-Type')}")
    
    # Extract content
    content = response.content.decode('utf-8')
    
    # Verification checks
    checks = {
        'Sidebar Present': 'id="sidebar"' in content,
        'Navbar Present': 'dashboard-navbar' in content,
        'Stats Cards Present': 'stats-grid' in content,
        'Activity Feed Present': 'activity-section' in content,
        'Quick Actions Present': 'quick-actions-section' in content,
        'Profile Card Present': 'profile-card' in content,
        'Footer Present': 'dashboard-footer' in content,
        'CSS Loaded': 'css/dashboard.css' in content,
        'JS Loaded': 'js/dashboard.js' in content,
        'User Email Displayed': user.email in content,
        'Menu Toggle Present': 'navbar-menu-toggle' in content,
        'User Menu Present': 'user-menu-toggle' in content,
        'Navigation Links': 'Dashboard' in content and 'Certificates' in content,
        'Empty States': 'No data available' in content and 'No activity yet' in content,
    }
    
    print("\nVERIFICATION RESULTS:")
    print("-" * 70)
    
    passed = 0
    for check, result in checks.items():
        status = "✓" if result else "✗"
        print(f"{status} {check}")
        if result:
            passed += 1
    
    print("-" * 70)
    print(f"\nPassed: {passed}/{len(checks)}")
    
    if passed == len(checks):
        print("\n" + "="*70)
        print("✓ ALL CHECKS PASSED - Dashboard is ready!")
        print("="*70 + "\n")
        return True
    else:
        print(f"\n✗ {len(checks) - passed} checks failed")
        return False

def check_file_structure():
    """Verify all required files exist"""
    
    print("\n" + "="*70)
    print("FILE STRUCTURE VERIFICATION")
    print("="*70 + "\n")
    
    files = [
        ('templates/dashboard/dashboard_shell.html', 'Main template'),
        ('templates/dashboard/components/sidebar.html', 'Sidebar'),
        ('templates/dashboard/components/navbar.html', 'Navbar'),
        ('templates/dashboard/components/stats_cards.html', 'Stats Cards'),
        ('templates/dashboard/components/recent_activity.html', 'Activity Feed'),
        ('templates/dashboard/components/quick_actions.html', 'Quick Actions'),
        ('templates/dashboard/components/profile_card.html', 'Profile Card'),
        ('templates/dashboard/components/footer.html', 'Footer'),
        ('static/css/dashboard.css', 'Dashboard CSS'),
        ('static/js/dashboard.js', 'Dashboard JS'),
        ('users/tests_dashboard_shell.py', 'Tests'),
    ]
    
    all_exist = True
    for filepath, description in files:
        full_path = PROJECT_ROOT / filepath
        exists = full_path.exists()
        status = "✓" if exists else "✗"
        print(f"{status} {filepath:<50} ({description})")
        if not exists:
            all_exist = False
    
    print()
    if all_exist:
        print("✓ All files present!")
    else:
        print("✗ Some files missing!")
    
    return all_exist

def check_file_sizes():
    """Check file sizes and content"""
    
    print("\n" + "="*70)
    print("FILE SIZE VERIFICATION")
    print("="*70 + "\n")
    
    files = {
        'static/css/dashboard.css': 'CSS',
        'static/js/dashboard.js': 'JavaScript',
    }
    
    for filepath, desc in files.items():
        full_path = PROJECT_ROOT / filepath
        if full_path.exists():
            size = full_path.stat().st_size
            size_kb = size / 1024
            print(f"✓ {desc:<15} {size_kb:>6.1f}KB  ({size:>6} bytes)")

if __name__ == '__main__':
    print("\n")
    
    # Check files
    files_ok = check_file_structure()
    
    # Check sizes
    check_file_sizes()
    
    # Verify dashboard
    dashboard_ok = verify_dashboard()
    
    if files_ok and dashboard_ok:
        print("\n✓ Dashboard shell is fully functional!")
        print("\nTo access the dashboard:")
        print("1. Start Django: python manage.py runserver")
        print("2. Login at: http://localhost:8000/auth/login/")
        print("3. Visit dashboard: http://localhost:8000/auth/dashboard/")
    else:
        print("\n✗ Some checks failed - please review the output above")
        sys.exit(1)
