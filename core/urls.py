from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("school-profile/", views.school_profile_detail, name="school_profile_detail"),
    path("fee-structure/", views.fee_structure_report, name="fee_structure_report"),
    path("marks/", views.marks_report, name="marks_report"),
    path("students/", views.student_list, name="student_list"),
    path("students/<int:pk>/", views.student_detail, name="student_detail"),
    path("receipts/", views.receipt_list, name="receipt_list"),
    path("receipts/new/", views.receipt_create, name="receipt_create"),
    path("dues/", views.due_report, name="due_report"),
    path("dues/pdf/", views.due_report_pdf, name="due_report_pdf"),
    path("receipts/<int:pk>/", views.receipt_detail, name="receipt_detail"),
    path("receipts/<int:pk>/pdf/", views.receipt_pdf, name="receipt_pdf"),
    path("api/students/<int:pk>/fee-defaults/", views.student_fee_defaults, name="student_fee_defaults"),
    path("collection/", views.collection_report, name="collection_report"),
    path("collection/pdf/", views.collection_report_pdf, name="collection_report_pdf"),
    path("students/<int:pk>/admission-form/pdf/", views.admission_form_pdf, name="admission_form_pdf"),
    path("students/<int:pk>/character-certificate/pdf/", views.character_certificate_pdf, name="character_certificate_pdf"),
    path("students/<int:pk>/tc/", views.tc_detail, name="tc_detail"),
    path("students/<int:pk>/tc/pdf/", views.tc_pdf, name="tc_pdf"),
    path("students/<int:pk>/marksheet/", views.marksheet_select, name="marksheet_select"),
    path("students/<int:pk>/marksheet/<int:term_id>/pdf/", views.marksheet_pdf, name="marksheet_pdf"),
    path("staff/", views.staff_list, name="staff_list"),
    path("staff/<int:pk>/", views.staff_detail, name="staff_detail"),
    path("staff/salary/new/", views.salary_payment_create, name="salary_payment_create"),
    path("staff/salary/<int:pk>/pdf/", views.salary_payslip_pdf, name="salary_payslip_pdf"),
    path("transport/", views.transport_list, name="transport_list"),
]
