from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from . import user_admin
from .access import admin_only_required, module_required

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
    path("admin/online-sync/start/", admin_only_required("Online Sync")(views.online_sync_start), name="online_sync_start"),
    path("admin/backup/start/", admin_only_required("Backup Now")(views.backup_start), name="backup_start"),
    path("school-profile/", module_required("school_profile")(views.school_profile_detail), name="school_profile_detail"),
    path("fee-structure/", module_required("fee_setup")(views.fee_structure_report), name="fee_structure_report"),
    path("marks/", module_required("marks")(views.marks_report), name="marks_report"),
    path("students/", module_required("students")(views.student_list), name="student_list"),
    path("students/register/", module_required("students")(views.student_register), name="student_register"),
    path("students/export/", module_required("students")(views.student_export_csv), name="student_export_csv"),
    path("students/bulk-photo-upload/", module_required("students", write=True)(views.bulk_photo_upload_view), name="bulk_photo_upload"),
    path("students/bulk-photo-upload/export/", module_required("students")(views.bulk_photo_export_csv), name="bulk_photo_export_csv"),
    path("students/board-registration/<slug:kind>/export/", module_required("students")(views.board_registration_export_csv), name="board_registration_export_csv"),
    path("students/board-registration/<slug:kind>/export/excel/", module_required("students")(views.board_registration_export_excel), name="board_registration_export_excel"),
    path("students/id-cards/pdf/", module_required("students")(views.id_card_batch_pdf), name="id_card_batch_pdf"),
    path("students/new/", module_required("students", write=True)(views.student_create), name="student_create"),
    path("students/<int:pk>/", module_required("students")(views.student_detail), name="student_detail"),
    path("students/<int:pk>/edit/", module_required("students", write=True)(views.student_update), name="student_update"),
    path("students/<int:pk>/delete/", module_required("students", write=True)(views.student_delete), name="student_delete"),
    path("api/students/check-duplicate/", module_required("students")(views.check_student_duplicate), name="check_student_duplicate"),
    path("api/students/check-siblings/", module_required("students")(views.check_siblings), name="check_siblings"),
    path("receipts/", module_required("receipts")(views.receipt_list), name="receipt_list"),
    path("receipts/new/", module_required("fee_collection", write=True)(views.receipt_create), name="receipt_create"),
    path("dues-up-to-month/", module_required("dues")(views.due_up_to_month_report), name="due_up_to_month_report"),
    path("dues-up-to-month/pdf/", module_required("dues")(views.due_up_to_month_report_pdf), name="due_up_to_month_report_pdf"),
    path("dues-up-to-month/slips/", module_required("dues")(views.due_slip_pdf), name="due_slip_pdf"),
    path("dues/", module_required("dues")(views.due_report), name="due_report"),
    path("dues/pdf/", module_required("dues")(views.due_report_pdf), name="due_report_pdf"),
    path("reports/fee-register/", module_required("dues")(views.fee_register), name="fee_register"),
    path("reports/fee-register/pdf/", module_required("dues")(views.fee_register_pdf), name="fee_register_pdf"),
    path("reports/fee-register/excel/", module_required("dues")(views.fee_register_excel), name="fee_register_excel"),
    path("reports/defaulters/", module_required("dues")(views.defaulter_list), name="defaulter_list"),
    path("receipts/<int:pk>/", module_required("receipts")(views.receipt_detail), name="receipt_detail"),
    path("receipts/<int:pk>/edit/", module_required("receipts", write=True)(views.receipt_edit), name="receipt_edit"),
    path("receipts/<int:pk>/pdf/", module_required("receipts")(views.receipt_pdf), name="receipt_pdf"),
    path("receipts/<int:pk>/pdf/2up/", module_required("receipts")(views.receipt_pdf_2up), name="receipt_pdf_2up"),
    path("pdf-viewer/", views.pdf_viewer, name="pdf_viewer"),
    path("receipts/<int:pk>/print/", module_required("receipts")(views.receipt_print), name="receipt_print"),
    path("receipts/demand-slip/", module_required("fee_collection")(views.guardian_demand_slip), name="guardian_demand_slip"),
    path("receipts/<int:pk>/cancel/", module_required("receipts", write=True)(views.receipt_cancel), name="receipt_cancel"),
    path("api/students/<int:pk>/fee-defaults/", module_required("fee_collection")(views.student_fee_defaults), name="student_fee_defaults"),
    path("api/receipts/check-duplicate/", module_required("fee_collection")(views.check_duplicate_receipt), name="check_duplicate_receipt"),
    path("collection/", module_required("collection")(views.collection_report), name="collection_report"),
    path("collection/pdf/", module_required("collection")(views.collection_report_pdf), name="collection_report_pdf"),
    path("students/<int:pk>/admission-form/pdf/", module_required("students")(views.admission_form_pdf), name="admission_form_pdf"),
    path("students/<int:pk>/character-certificate/pdf/", module_required("students")(views.character_certificate_pdf), name="character_certificate_pdf"),
    path("students/<int:pk>/id-card/pdf/", module_required("students")(views.id_card_pdf), name="id_card_pdf"),
    path("students/<int:pk>/id-card/single/pdf/", module_required("students")(views.id_card_pdf), name="id_card_single_pdf"),
    path("academics/id-cards/", module_required("students")(views.id_cards_dashboard), name="id_cards_dashboard"),
    path("academics/id-cards/issue-list/", module_required("students")(views.id_card_issue_list_view), name="id_card_issue_list_view"),
    path("academics/id-cards/issue-list/pdf/", module_required("students")(views.id_card_issue_list_pdf), name="id_card_issue_list_pdf"),
    path("academics/id-cards/issue-list/excel/", module_required("students")(views.id_card_issue_list_excel), name="id_card_issue_list_excel"),
    path("students/<int:pk>/tc/", module_required("students", write=True)(views.tc_detail), name="tc_detail"),
    path("students/<int:pk>/tc/pdf/", module_required("students")(views.tc_pdf), name="tc_pdf"),
    path("students/<int:pk>/scholar-register/pdf/", module_required("students")(views.scholar_register_pdf), name="scholar_register_pdf"),
    path("students/register/scholar-book/pdf/", module_required("students")(views.scholar_register_book_pdf), name="scholar_register_book_pdf"),
    path("students/register/scholar-book/index/pdf/", module_required("students")(views.scholar_register_index_pdf), name="scholar_register_index_pdf"),
    path("academics/attendance/register/", module_required("students")(views.attendance_register_view), name="attendance_register"),
    path("academics/attendance/register/pdf/", module_required("students")(views.attendance_register_pdf), name="attendance_register_pdf"),
    path("academics/attendance/entry/", module_required("students", write=True)(views.attendance_summary_entry), name="attendance_summary_entry"),
    path("academics/attendance/report/", module_required("students")(views.attendance_summary_report), name="attendance_summary_report"),
    path("academics/attendance/report/excel/", module_required("students")(views.attendance_summary_report_excel), name="attendance_summary_report_excel"),
    path("academics/marks/entry/", module_required("marks", write=True)(views.marks_entry_view), name="marks_entry"),
    path("academics/marks/entry/export-excel/", module_required("marks")(views.marks_entry_export_excel), name="marks_entry_export_excel"),
    path("academics/marks/entry/import-excel/", module_required("marks", write=True)(views.marks_entry_import_excel), name="marks_entry_import_excel"),
    path("academics/marks/batch-marksheet/pdf/", module_required("marks")(views.marksheet_batch_pdf), name="marksheet_batch_pdf"),
    path("students/<int:pk>/marksheet/", module_required("marks")(views.marksheet_select), name="marksheet_select"),
    path("students/<int:pk>/marksheet/<int:term_id>/view/", module_required("marks")(views.marksheet_view), name="marksheet_view"),
    path("students/<int:pk>/marksheet/<int:term_id>/pdf/", module_required("marks")(views.marksheet_pdf), name="marksheet_pdf"),
    path("students/<int:pk>/discipline/", admin_only_required("Discipline Records")(views.discipline_list), name="discipline_list"),
    path("students/<int:pk>/discipline/new/", admin_only_required("Discipline Records")(views.discipline_create), name="discipline_create"),
    path("students/<int:pk>/discipline/pdf/", admin_only_required("Discipline Records")(views.discipline_pdf), name="discipline_pdf"),

    # Inventory (Uniform/Books)
    path("inventory/items/", module_required("inventory")(views.inventory_item_list), name="inventory_item_list"),
    path("inventory/items/new/", module_required("inventory", write=True)(views.inventory_item_create), name="inventory_item_create"),
    path("inventory/items/<int:pk>/toggle-active/", module_required("inventory", write=True)(views.inventory_item_toggle_active), name="inventory_item_toggle_active"),
    path("inventory/report/", module_required("inventory")(views.inventory_report), name="inventory_report"),
    path("students/<int:pk>/inventory/", module_required("inventory")(views.inventory_issue_list), name="inventory_issue_list"),
    path("students/<int:pk>/inventory/new/", module_required("inventory", write=True)(views.inventory_issue_create), name="inventory_issue_create"),

    # Family Ledger (siblings)
    path("families/", module_required("family")(views.family_list), name="family_list"),
    path("families/new/", module_required("family", write=True)(views.family_create), name="family_create"),
    path("families/suggestions/", module_required("family", write=True)(views.family_suggestions), name="family_suggestions"),
    path("families/suggestions/create/", module_required("family", write=True)(views.family_create_from_suggestion), name="family_create_from_suggestion"),
    path("families/<int:pk>/", module_required("family")(views.family_detail), name="family_detail"),
    path("families/<int:pk>/add-student/", module_required("family", write=True)(views.family_add_student), name="family_add_student"),
    path("families/<int:pk>/remove-student/<int:student_id>/", module_required("family", write=True)(views.family_remove_student), name="family_remove_student"),

    path("staff/", module_required("staff")(views.staff_list), name="staff_list"),
    path("staff/id-cards/pdf/", module_required("staff")(views.staff_id_card_batch_pdf), name="staff_id_card_batch_pdf"),
    path("staff/<int:pk>/", module_required("staff")(views.staff_detail), name="staff_detail"),
    path("staff/<int:pk>/id-card/pdf/", module_required("staff")(views.staff_id_card_pdf), name="staff_id_card_pdf"),
    path("staff/salary/", module_required("staff")(views.salary_payment_list), name="salary_payment_list"),
    path("staff/salary/new/", module_required("staff", write=True)(views.salary_payment_create), name="salary_payment_create"),
    path("staff/salary/status/", views.salary_status_api, name="salary_status_api"),
    path("staff/salary/<int:pk>/", module_required("staff")(views.salary_payment_detail), name="salary_payment_detail"),
    path("staff/salary/<int:pk>/edit/", module_required("staff", write=True)(views.salary_payment_edit), name="salary_payment_edit"),
    path("staff/salary/<int:pk>/cancel/", module_required("staff", write=True)(views.salary_payment_cancel), name="salary_payment_cancel"),
    path("staff/salary/<int:pk>/pdf/", module_required("staff")(views.salary_payslip_pdf), name="salary_payslip_pdf"),
    path("transport/", module_required("transport")(views.transport_list), name="transport_list"),

    # Accounts / Cash Book
    path("accounts/persons/", module_required("accounts")(views.person_list), name="person_list"),
    path("accounts/persons/<int:pk>/", module_required("accounts")(views.person_detail), name="person_detail"),
    path("accounts/expense/new/", module_required("accounts", write=True)(views.expense_create), name="expense_create"),
    path("accounts/receipt/new/", module_required("accounts", write=True)(views.receipt_other_create), name="receipt_other_create"),
    path("accounts/ledgers/", module_required("accounts")(views.ledger_list), name="ledger_list"),
    path("accounts/ledgers/new/", module_required("accounts", write=True)(views.ledger_create), name="ledger_create"),
    path("accounts/ledgers/<int:pk>/edit/", module_required("accounts", write=True)(views.ledger_edit), name="ledger_edit"),
    path("accounts/vouchers/", module_required("accounts")(views.voucher_list), name="voucher_list"),
    path("accounts/vouchers/<int:pk>/", module_required("accounts")(views.voucher_detail), name="voucher_detail"),
    path("accounts/vouchers/<int:pk>/edit/", module_required("accounts", write=True)(views.voucher_edit), name="voucher_edit"),
    path("accounts/vouchers/<int:pk>/cancel/", module_required("accounts", write=True)(views.voucher_cancel), name="voucher_cancel"),
    path("accounts/vouchers/<int:pk>/pdf/", module_required("accounts")(views.voucher_pdf), name="voucher_pdf"),
    path("accounts/cash-book/", module_required("accounts")(views.cash_book), name="cash_book"),

    # Attached / Feeder Schools (अटैच्ड विद्यालय)
    path("feeder-schools/", module_required("fee_setup")(views.feeder_school_list), name="feeder_school_list"),
    path("feeder-schools/new/", module_required("fee_setup", write=True)(views.feeder_school_create), name="feeder_school_create"),
    path("feeder-schools/<int:pk>/", module_required("fee_setup")(views.feeder_school_detail), name="feeder_school_detail"),
    path("feeder-schools/<int:pk>/edit/", module_required("fee_setup", write=True)(views.feeder_school_edit), name="feeder_school_edit"),
    path("feeder-schools/<int:pk>/payment/", module_required("fee_setup", write=True)(views.feeder_school_payment), name="feeder_school_payment"),
    path("feeder-schools/<int:pk>/statement/pdf/", module_required("fee_setup")(views.feeder_school_statement_pdf), name="feeder_school_statement_pdf"),
    path("feeder-schools/<int:pk>/statement/excel/", module_required("fee_setup")(views.feeder_school_statement_excel), name="feeder_school_statement_excel"),

    # Self-service password change (any logged-in user)
    path(
        "account/password/",
        auth_views.PasswordChangeView.as_view(
            template_name="core/password_change.html",
            success_url="/account/password/done/",
        ),
        name="password_change",
    ),
    path(
        "account/password/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="core/password_change_done.html",
        ),
        name="password_change_done",
    ),

    # Users & Permissions (administrators only)
    path("users/", user_admin.user_list, name="user_list"),
    path("users/new/", user_admin.user_create, name="user_create"),
    path("users/<int:pk>/edit/", user_admin.user_edit, name="user_edit"),
    path("users/<int:pk>/reset-password/", user_admin.user_reset_password, name="user_reset_password"),
    path("users/<int:pk>/toggle-active/", user_admin.user_toggle_active, name="user_toggle_active"),
]
