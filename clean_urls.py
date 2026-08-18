tail_urls = '''    path("transport/", module_required("transport")(views.transport_list), name="transport_list"),

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
'''

urls_path = r'E:\THPSIC-INTER-COLLEGE\01-source-code\schoolsoft_web\core\urls.py'
with open(urls_path, 'r', encoding='utf-8') as f:
    content = f.read()

target = '    path("transport/", module_required("transport")(views.transport_list), name="transport_list"),'
idx = content.find(target)

new_content = content[:idx] + tail_urls
with open(urls_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("core/urls.py cleaned and updated successfully!")
