from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.views.decorators.csrf import csrf_protect


@require_http_methods(["GET", "POST"])
@csrf_protect
def login_view(request):
    """Handle user login."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '').strip()
        
        # Authenticate using email (since Django User model has username field)
        # We need to get the user by email first
        try:
            from django.contrib.auth.models import User
            user = User.objects.get(email=email)
            user = authenticate(request, username=user.username, password=password)
        except User.DoesNotExist:
            user = None
        
        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {user.first_name or user.username}!')
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid email or password.')
    
    context = {
        'page_title': 'Login',
    }
    return render(request, 'auth/login.html', context)


@login_required(login_url='login')
def logout_view(request):
    """Handle user logout."""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('home')


@login_required(login_url='login')
def dashboard_view(request):
    """Protected dashboard view with live statistics and recent activity."""
    from users.models import Student, AuthorizedSignatory, AuditLog
    from certificates.models import Certificate, Program, Enrollment

    total_certificates = Certificate.objects.count()
    issued_certificates = Certificate.objects.filter(status='ISSUED').count()
    draft_certificates = Certificate.objects.filter(status='DRAFT').count()
    revoked_certificates = Certificate.objects.filter(status='REVOKED').count()
    
    total_programs = Program.objects.filter(is_active=True).count()
    total_students = Student.objects.filter(is_active=True).count()
    total_enrollments = Enrollment.objects.count()
    total_signatories = AuthorizedSignatory.objects.filter(is_active=True).count()
    
    total_verifications = AuditLog.objects.filter(action='VERIFY').count()
    recent_activities = AuditLog.objects.all().order_by('-timestamp')[:8]
    recent_certificates = Certificate.objects.select_related('student', 'program').order_by('-created_at')[:6]

    context = {
        'page_title': 'Dashboard',
        'user': request.user,
        'total_certificates': total_certificates,
        'issued_certificates': issued_certificates,
        'draft_certificates': draft_certificates,
        'revoked_certificates': revoked_certificates,
        'total_programs': total_programs,
        'total_students': total_students,
        'total_enrollments': total_enrollments,
        'total_signatories': total_signatories,
        'total_verifications': total_verifications,
        'recent_activities': recent_activities,
        'recent_certificates': recent_certificates,
    }
    return render(request, 'dashboard/dashboard_shell.html', context)
