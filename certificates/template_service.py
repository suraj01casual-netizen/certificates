"""
Certificate Template Rendering Service.

Provides a unified, modular template engine for certificate rendering across:
  - Classic Design (Traditional Ornate)
  - Modern Design (Minimalist Geometric / Gradient)
  - Professional Design (Corporate Executive)

Guarantees:
  - Strict separation of HTML and CSS across template designs.
  - Exactly one unified context data contract for all templates.
  - Zero duplication of certificate issuance or identity generation business logic.
  - Faithful rendering in both live browser preview iframe and WeasyPrint PDF compilation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Any
from django.template.loader import render_to_string

if TYPE_CHECKING:
    from certificates.models import Certificate, CertificateTemplate


class TemplateRenderingService:
    """Service to resolve, configure, and render certificate templates."""

    TEMPLATES_REGISTRY: Dict[str, Dict[str, Any]] = {
        'CLASSIC': {
            'key': 'CLASSIC',
            'name': 'Classic Certificate',
            'design_style': 'CLASSIC',
            'template_path': 'certificates/templates/classic.html',
            'description': 'Traditional ornate gold-leaf border with classical serif typography, corner filigrees, and official seal.',
            'primary_font': 'Cinzel, Playfair Display, Georgia, serif',
            'accent_color': '#c5a059',
        },
        'MODERN': {
            'key': 'MODERN',
            'name': 'Modern Minimalist',
            'design_style': 'MODERN',
            'template_path': 'certificates/templates/modern.html',
            'description': 'Contemporary geometric layout with sleek gradients, clean typography, and asymmetric badges.',
            'primary_font': 'Outfit, Inter, system-ui, sans-serif',
            'accent_color': '#4f46e5',
        },
        'PROFESSIONAL': {
            'key': 'PROFESSIONAL',
            'name': 'Professional Corporate',
            'design_style': 'PROFESSIONAL',
            'template_path': 'certificates/templates/professional.html',
            'description': 'Refined executive aesthetic with slate-navy dual borders, structured credential grid, and official watermark.',
            'primary_font': 'Montserrat, Merriweather, sans-serif',
            'accent_color': '#0f172a',
        },
    }

    DEFAULT_TEMPLATE_PATH = 'certificates/templates/classic.html'

    @classmethod
    def get_registered_templates(cls) -> List[Dict[str, Any]]:
        """Return list of all registered certificate templates."""
        return list(cls.TEMPLATES_REGISTRY.values())

    @classmethod
    def resolve_template_path(
        cls,
        template: Optional[CertificateTemplate] = None,
        design_style: Optional[str] = None,
    ) -> str:
        """Resolve the appropriate HTML template file path."""
        # 1. If explicit template instance provided
        if template:
            raw_path = getattr(template, 'html_template', '') or ''
            if raw_path.startswith('templates/'):
                raw_path = raw_path[len('templates/'):]
            if raw_path.strip().endswith('.html'):
                try:
                    from django.template.loader import get_template
                    get_template(raw_path.strip())
                    return raw_path.strip()
                except Exception:
                    pass

            # Check model property
            if hasattr(template, 'template_file') and template.template_file:
                return template.template_file
            style = getattr(template, 'design_style', None)
            if style and style.upper() in cls.TEMPLATES_REGISTRY:
                return cls.TEMPLATES_REGISTRY[style.upper()]['template_path']

        # 2. If design_style key provided directly
        if design_style and design_style.upper() in cls.TEMPLATES_REGISTRY:
            return cls.TEMPLATES_REGISTRY[design_style.upper()]['template_path']

        return cls.DEFAULT_TEMPLATE_PATH

    @classmethod
    def render_template(
        cls,
        certificate: Certificate,
        template: Optional[CertificateTemplate] = None,
        base_url: Optional[str] = None,
        extra_context: Optional[dict] = None,
    ) -> str:
        """Render the certificate HTML using the selected template and unified context."""
        from certificates.pdf_service import CertificatePDFService

        effective_template = template or getattr(certificate, 'template', None)
        template_path = cls.resolve_template_path(effective_template)

        # Build unified context
        context = CertificatePDFService.build_context(certificate, base_url=base_url)

        # Inject template metadata
        style_key = (
            getattr(effective_template, 'design_style', 'CLASSIC')
            if effective_template
            else 'CLASSIC'
        ).upper()
        template_meta = cls.TEMPLATES_REGISTRY.get(style_key, cls.TEMPLATES_REGISTRY['CLASSIC'])
        context['template_meta'] = template_meta
        context['design_style'] = style_key

        if extra_context:
            context.update(extra_context)

        return render_to_string(template_path, context)

    @classmethod
    def ensure_default_templates(cls) -> None:
        """Ensure default Classic, Modern, and Professional templates exist in DB."""
        from certificates.models import CertificateTemplate

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
