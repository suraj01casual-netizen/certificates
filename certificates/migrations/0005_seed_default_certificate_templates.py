from django.db import migrations


def seed_templates(apps, schema_editor):
    CertificateTemplate = apps.get_model('certificates', 'CertificateTemplate')
    defaults = [
        {
            'name': 'Classic Certificate',
            'design_style': 'CLASSIC',
            'description': 'Traditional ornate gold-leaf border with classical serif typography and official seal.',
            'html_template': 'certificates/templates/classic.html',
            'colors': {'primary': '#1e3a8a', 'accent': '#c5a059'},
            'is_active': True,
        },
        {
            'name': 'Modern Minimalist',
            'design_style': 'MODERN',
            'description': 'Contemporary geometric layout with sleek gradients, clean typography, and asymmetric badges.',
            'html_template': 'certificates/templates/modern.html',
            'colors': {'primary': '#4f46e5', 'accent': '#06b6d4'},
            'is_active': True,
        },
        {
            'name': 'Professional Corporate',
            'design_style': 'PROFESSIONAL',
            'description': 'Refined executive aesthetic with slate-navy borders, structured credential grid, and official watermark.',
            'html_template': 'certificates/templates/professional.html',
            'colors': {'primary': '#0f172a', 'accent': '#3b82f6'},
            'is_active': True,
        },
    ]
    for item in defaults:
        CertificateTemplate.objects.get_or_create(
            name=item['name'],
            defaults=item
        )


def unseed_templates(apps, schema_editor):
    CertificateTemplate = apps.get_model('certificates', 'CertificateTemplate')
    CertificateTemplate.objects.filter(
        name__in=['Classic Certificate', 'Modern Minimalist', 'Professional Corporate']
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('certificates', '0004_certificatetemplate_design_style_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_templates, unseed_templates),
    ]
