from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .access import module_required

from django.views.generic import TemplateView

app_name = "core"

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="core/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),

    # PWA files
    path("manifest.webmanifest", TemplateView.as_view(template_name="core/manifest.webmanifest", content_type="application/manifest+json"), name="manifest"),
    path("service-worker.js", TemplateView.as_view(template_name="core/service-worker.js", content_type="application/javascript"), name="service_worker"),
    
    path("", module_required("dashboard")(views.dashboard), name="dashboard"),
    path("school-profile/", module_required("school_profile")(views.school_profile_detail), name="school_profile_detail"),
    path("fee-structure/", module_required("fee_setup")(views.fee_structure_report), name="fee_structure_report"),
    path("marks/", module_required("marks")(views.marks_report), name="marks_report"),
    path("students/", module_required("students")(views.student_list), name="student_list"),
    path("students/register/", module_required("students")(views.student_register), name="student_register"),
    path("students/export/", module_required("students")(views.student_export_csv), name="student_export_csv"),
    path("students/new/", module_required("students")(views.student_create), name="student_create"),
    path("students/<int:pk>/", module_required("students")(views.student_detail), name="student_detail"),
    path("students/<int:pk>/edit/", module_required("students")(views.student_update), name="student_update"),
    path("students/<int:pk>/delete/", module_required("students")(views.student_delete), name="student_delete"),
    path("api/students/check-duplicate/", module_required("students")(views.check_student_duplicate), name="check_student_duplicate"),
    path("receipts/", module_required("receipts")(views.receipt_list), name="receipt_list"),
    path("receipts/new/", module_required("fee_collection")(views.receipt_create), name="receipt_create"),
    path("dues/", module_required("dues")(views.due_report), name="due_report"),
    path("dues/pdf/", module_required("dues")(views.due_report_pdf), name="due_report_pdf"),
    path("receipts/<int:pk>/", module_required("receipts")(views.receipt_detail), name="receipt_detail"),
    path("receipts/<int:pk>/pdf/", module_required("receipts")(views.receipt_pdf), name="receipt_pdf"),
    path("api/students/<int:pk>/fee-defaults/", module_required("fee_collection")(views.student_fee_defaults), name="student_fee_defaults"),
    path("api/receipts/check-duplicate/", module_required("fee_collection")(views.check_duplicate_receipt), name="check_duplicate_receipt"),
    path("collection/", module_required("collection")(views.collection_report), name="collection_report"),
    path("collection/pdf/", module_required("collection")(views.collection_report_pdf), name="collection_report_pdf"),
    path("students/<int:pk>/admission-form/pdf/", module_required("students")(views.admission_form_pdf), name="admission_form_pdf"),
    path("students/<int:pk>/character-certificate/pdf/", module_required("students")(views.character_certificate_pdf), name="character_certificate_pdf"),
    path("students/<int:pk>/tc/", module_required("students")(views.tc_detail), name="tc_detail"),
    path("students/<int:pk>/tc/pdf/", module_required("students")(views.tc_pdf), name="tc_pdf"),
    path("students/<int:pk>/marksheet/", module_required("marks")(views.marksheet_select), name="marksheet_select"),
    path("students/<int:pk>/marksheet/<int:term_id>/pdf/", module_required("marks")(views.marksheet_pdf), name="marksheet_pdf"),
    path("staff/", module_required("staff")(views.staff_list), name="staff_list"),
    path("staff/<int:pk>/", module_required("staff")(views.staff_detail), name="staff_detail"),
    path("staff/salary/new/", module_required("staff")(views.salary_payment_create), name="salary_payment_create"),
    path("staff/salary/<int:pk>/pdf/", module_required("staff")(views.salary_payslip_pdf), name="salary_payslip_pdf"),
    path("transport/", module_required("transport")(views.transport_list), name="transport_list"),
]
