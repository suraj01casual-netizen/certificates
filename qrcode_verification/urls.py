from django.urls import path
from qrcode_verification.views import (
    CertificateVerifySearchView,
    CertificateVerifyView,
    PublicCertificateDownloadView,
)

app_name = 'verify'

urlpatterns = [
    path('', CertificateVerifySearchView.as_view(), name='verify_search'),
    path('<str:token>/', CertificateVerifyView.as_view(), name='verify_token'),
    path('<str:token>/download/', PublicCertificateDownloadView.as_view(), name='verify_download'),
]
