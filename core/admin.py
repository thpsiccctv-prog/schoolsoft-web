from django.contrib import admin

from .models import (
    AcademicSession,
    DisciplineRecord,
    ExamMark,
    ExamTerm,
    ExamTest,
    Family,
    FeeHead,
    FeeReceipt,
    FeeReceiptAuditLog,
    FeeReceiptLine,
    FeeStructure,
    House,
    InventoryIssue,
    InventoryItem,
    LegacyImportBatch,
    SalaryPayment,
    SchoolClass,
    SchoolProfile,
    Section,
    Staff,
    Student,
    StudentTransport,
    Subject,
    TransferCertificate,
    TransportBus,
    TransportRoute,
)

admin.site.site_header = "THPSIC SchoolSoft Admin"
admin.site.site_title = "THPSIC SchoolSoft Admin"
admin.site.index_title = "THPSIC SchoolSoft Control Center"


@admin.register(AcademicSession)
class AcademicSessionAdmin(admin.ModelAdmin):
    list_display = ("name", "starts_on", "ends_on", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


class SectionInline(admin.TabularInline):
    model = Section
    extra = 1


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ("name", "legacy_code", "display_order")
    search_fields = ("name",)
    inlines = [SectionInline]


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("school_class", "name")
    list_filter = ("school_class",)
    search_fields = ("name", "school_class__name")


@admin.register(SchoolProfile)
class SchoolProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "legacy_comp_code", "phone", "email", "current_year", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "phone", "email")


@admin.register(House)
class HouseAdmin(admin.ModelAdmin):
    list_display = ("name", "color_code", "display_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "admission_no",
        "legacy_sid",
        "current_class",
        "current_section",
        "house",
        "roll_no",
        "mobile_primary",
        "is_active",
    )
    list_filter = ("is_active", "current_class", "current_section", "house", "gender", "category")
    search_fields = ("full_name", "father_name", "mother_name", "admission_no", "legacy_sid")
    autocomplete_fields = ("current_class", "current_section")


@admin.register(FeeHead)
class FeeHeadAdmin(admin.ModelAdmin):
    list_display = ("name", "frequency", "legacy_column", "is_transport", "is_active")
    list_filter = ("frequency", "is_transport", "is_active")
    search_fields = ("name", "legacy_column")


@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ("session", "school_class", "fee_head", "amount")
    list_filter = ("session", "school_class", "fee_head")
    search_fields = ("fee_head__name", "school_class__name", "session__name")


class FeeReceiptLineInline(admin.TabularInline):
    model = FeeReceiptLine
    extra = 1
    autocomplete_fields = ("fee_head",)


@admin.register(FeeReceipt)
class FeeReceiptAdmin(admin.ModelAdmin):
    list_display = (
        "receipt_no",
        "legacy_receipt_no",
        "student",
        "session",
        "receipt_date",
        "received_amount",
        "legacy_due_amount",
        "payment_mode",
    )
    list_filter = ("session", "receipt_date", "payment_mode")
    search_fields = ("receipt_no", "legacy_receipt_no", "student__full_name", "student__admission_no")
    autocomplete_fields = ("student", "session")
    inlines = [FeeReceiptLineInline]
    readonly_fields = (
        "is_edited",
        "edited_at",
        "edited_by",
        "edit_reason",
        "edit_count",
        "is_cancelled",
        "cancelled_at",
        "cancelled_by",
        "cancel_reason"
    )

@admin.register(FeeReceiptAuditLog)
class FeeReceiptAuditLogAdmin(admin.ModelAdmin):
    list_display = ("receipt", "action", "changed_by", "changed_at", "reason")
    list_filter = ("action", "changed_at")
    search_fields = ("receipt__receipt_no", "reason")
    readonly_fields = (
        "receipt",
        "action",
        "changed_by",
        "changed_at",
        "reason",
        "before_snapshot",
        "after_snapshot",
        "changes"
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TransferCertificate)
class TransferCertificateAdmin(admin.ModelAdmin):
    list_display = ("tc_number", "student", "issue_date", "last_class_studied", "conduct", "qualified_for_promotion")
    list_filter = ("conduct", "qualified_for_promotion", "last_class_studied")
    search_fields = ("tc_number", "student__full_name", "student__admission_no", "student__legacy_sid")
    autocomplete_fields = ("student", "last_class_studied")


@admin.register(DisciplineRecord)
class DisciplineRecordAdmin(admin.ModelAdmin):
    list_display = ("student", "incident_date", "category", "severity", "parent_notified", "reported_by")
    list_filter = ("category", "severity", "parent_notified", "incident_date")
    search_fields = ("student__full_name", "student__admission_no", "student__legacy_sid", "description")
    autocomplete_fields = ("student",)


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "unit_price", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name",)


@admin.register(InventoryIssue)
class InventoryIssueAdmin(admin.ModelAdmin):
    list_display = ("student", "item", "issue_date", "quantity", "unit_price", "amount_charged", "issued_by")
    list_filter = ("item", "issue_date")
    search_fields = ("student__full_name", "student__admission_no", "student__legacy_sid")
    autocomplete_fields = ("student",)


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ("name", "primary_mobile", "secondary_mobile")
    search_fields = ("name", "primary_mobile", "secondary_mobile")


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "legacy_code", "display_order", "is_active")
    search_fields = ("name", "legacy_code")


@admin.register(ExamTerm)
class ExamTermAdmin(admin.ModelAdmin):
    list_display = ("name", "session", "display_order")
    list_filter = ("session",)
    search_fields = ("name",)


@admin.register(ExamTest)
class ExamTestAdmin(admin.ModelAdmin):
    list_display = ("term", "school_class", "subject", "max_marks", "pass_marks")
    list_filter = ("term", "school_class", "subject")
    search_fields = ("subject__name", "school_class__name", "term__name")
    autocomplete_fields = ("subject",)


@admin.register(ExamMark)
class ExamMarkAdmin(admin.ModelAdmin):
    list_display = ("student", "exam_test", "marks_obtained", "is_absent", "grade")
    list_filter = ("exam_test__term", "exam_test__school_class", "exam_test__subject", "is_absent")
    search_fields = ("student__full_name", "student__legacy_sid", "student__admission_no")
    autocomplete_fields = ("student", "exam_test")


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "legacy_emp_code",
        "designation",
        "staff_type",
        "phone",
        "basic_pay",
        "is_active",
    )
    list_filter = ("staff_type", "is_active", "pf_applicable", "esi_applicable")
    search_fields = ("full_name", "legacy_emp_code", "phone", "email")


@admin.register(SalaryPayment)
class SalaryPaymentAdmin(admin.ModelAdmin):
    list_display = ("slip_no", "staff", "pay_month", "payment_date", "gross_pay_display", "net_pay_display", "payment_mode")
    list_filter = ("payment_mode", "pay_month")
    search_fields = ("slip_no", "staff__full_name", "staff__legacy_emp_code")
    autocomplete_fields = ("staff",)

    @admin.display(description="Gross")
    def gross_pay_display(self, obj):
        return obj.gross_pay

    @admin.display(description="Net")
    def net_pay_display(self, obj):
        return obj.net_pay


@admin.register(TransportBus)
class TransportBusAdmin(admin.ModelAdmin):
    list_display = ("name", "legacy_bus_code", "vehicle_no", "driver_name", "default_amount", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "vehicle_no", "driver_name", "legacy_bus_code")


@admin.register(TransportRoute)
class TransportRouteAdmin(admin.ModelAdmin):
    list_display = ("name", "legacy_route_code", "monthly_charge", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "legacy_route_code")


@admin.register(StudentTransport)
class StudentTransportAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "route",
        "bus",
        "legacy_student_name",
        "legacy_route_name",
        "legacy_bus_label",
        "is_active",
    )
    list_filter = ("is_active", "route", "bus")
    search_fields = (
        "student__full_name",
        "student__legacy_sid",
        "student__admission_no",
        "legacy_student_name",
        "legacy_father_name",
        "legacy_route_name",
        "legacy_bus_label",
    )
    autocomplete_fields = ("student", "route", "bus")


@admin.register(LegacyImportBatch)
class LegacyImportBatchAdmin(admin.ModelAdmin):
    list_display = ("source_table", "source_database", "records_seen", "records_imported", "created_at")
    list_filter = ("source_table",)
    search_fields = ("source_database", "source_table", "notes")

# Register your models here.

from .models import StudentConcession

@admin.register(StudentConcession)
class StudentConcessionAdmin(admin.ModelAdmin):
    list_display = [
        'student', 'session', 'concession_type', 
        'amount_type', 'amount', 'is_active', 
        'approved_by_name', 'created_at'
    ]
    list_filter = ['session', 'concession_type', 'amount_type', 'is_active', 'created_at']
    search_fields = ['student__full_name', 'student__admission_no', 'reason', 'approved_by_name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Student & Session', {
            'fields': ('student', 'session')
        }),
        ('Concession Details', {
            'fields': ('concession_type', 'amount_type', 'amount', 'reason', 'approved_by_name')
        }),
        ('Status', {
            'fields': ('is_active',)
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # New object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
