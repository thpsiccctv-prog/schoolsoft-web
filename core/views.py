from decimal import Decimal

from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import FeeReceiptEntryForm, FeeReceiptLineEntryForm, SalaryPaymentForm, TransferCertificateForm
from .models import (
    AcademicSession,
    ExamMark,
    ExamTerm,
    FeeHead,
    FeeReceipt,
    FeeStructure,
    SalaryPayment,
    SchoolClass,
    SchoolProfile,
    Section,
    Staff,
    Student,
    StudentTransport,
    TransferCertificate,
    TransportBus,
    TransportRoute,
)
from .pdf import (
    build_admission_form_pdf,
    build_character_certificate_pdf,
    build_due_report_pdf,
    build_fee_receipt_pdf,
    build_marksheet_pdf,
    build_salary_payslip_pdf,
    build_transfer_certificate_pdf,
)


def get_active_school_profile():
    return SchoolProfile.objects.filter(is_active=True).first()


def dashboard(request):
    audit_dir = settings.BASE_DIR.parent / "migration_audit"
    school7_tables = audit_dir / "school7_mdb" / "tables_summary.csv"
    school7_columns = audit_dir / "school7_mdb" / "columns_summary.csv"
    today = timezone.localdate()
    today_receipts = FeeReceipt.objects.filter(receipt_date=today)
    today_totals = today_receipts.aggregate(received=Sum("received_amount"))
    total_dues = FeeReceipt.objects.aggregate(due=Sum("legacy_due_amount"))

    context = {
        "today": today,
        "active_session": AcademicSession.objects.filter(is_active=True).order_by("-starts_on", "name").first(),
        "dashboard_kpis": [
            ("Today's Collection", today_totals["received"] or Decimal("0.00"), "success"),
            ("Receipts Today", today_receipts.count(), "info"),
            ("Total Dues", total_dues["due"] or Decimal("0.00"), "danger"),
            ("Active Students", Student.objects.filter(is_active=True).count(), "neutral"),
        ],
        "stats": [
            ("Students", Student.objects.count()),
            ("Classes", SchoolClass.objects.count()),
            ("Fee heads", FeeHead.objects.count()),
            ("Receipts", FeeReceipt.objects.count()),
            ("Sessions", AcademicSession.objects.count()),
        ],
        "audit_files": [
            ("SCHOOL7 tables", school7_tables),
            ("SCHOOL7 columns", school7_columns),
            ("Phase 1 notes", audit_dir / "phase1_schoolsoft_audit.md"),
        ],
        "next_actions": [
            "Create active academic session",
            "Import class master from CLASS",
            "Import students from ADDMISSION",
            "Map legacy fee columns to FeeHead",
            "Generate first test fee receipt PDF",
        ],
    }
    return render(request, "core/dashboard.html", context)


def student_list(request):
    query = request.GET.get("q", "").strip()
    class_id = request.GET.get("class", "").strip()
    section_id = request.GET.get("section", "").strip()

    students = Student.objects.select_related("current_class", "current_section").order_by(
        "current_class__display_order",
        "current_section__name",
        "roll_no",
        "full_name",
    )

    if query:
        students = students.filter(
            Q(full_name__icontains=query)
            | Q(father_name__icontains=query)
            | Q(mother_name__icontains=query)
            | Q(admission_no__icontains=query)
            | Q(legacy_sid__icontains=query)
            | Q(mobile_primary__icontains=query)
        )

    if class_id:
        students = students.filter(current_class_id=class_id)

    if section_id:
        students = students.filter(current_section_id=section_id)

    paginator = Paginator(students, 50)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page": page,
        "query": query,
        "selected_class": class_id,
        "selected_section": section_id,
        "classes": SchoolClass.objects.order_by("display_order", "name"),
        "sections": Section.objects.select_related("school_class").order_by(
            "school_class__display_order",
            "name",
        ),
        "total_students": students.count(),
    }
    return render(request, "core/student_list.html", context)


def student_detail(request, pk):
    student = get_object_or_404(
        Student.objects.select_related("current_class", "current_section"),
        pk=pk,
    )
    return render(
        request,
        "core/student_detail.html",
        {
            "student": student,
        },
    )


def school_profile_detail(request):
    profile = get_active_school_profile()
    all_profiles = SchoolProfile.objects.order_by("-is_active", "name")
    return render(
        request,
        "core/school_profile_detail.html",
        {
            "profile": profile,
            "all_profiles": all_profiles,
        },
    )


def fee_structure_report(request):
    selected_session_id = request.GET.get("session", "").strip()
    selected_class_id = request.GET.get("class", "").strip()
    row_mode = request.GET.get("rows", "nonzero").strip() or "nonzero"
    sessions = AcademicSession.objects.order_by("-is_active", "-starts_on", "name")
    selected_session = None

    if selected_session_id:
        selected_session = sessions.filter(pk=selected_session_id).first()

    if selected_session is None:
        selected_session = sessions.filter(is_active=True, fee_structures__isnull=False).distinct().first()

    if selected_session is None:
        selected_session = sessions.filter(fee_structures__isnull=False).distinct().first()

    structures = FeeStructure.objects.select_related("session", "school_class", "fee_head").order_by(
        "school_class__display_order",
        "school_class__name",
        "fee_head__name",
    )

    if selected_session:
        structures = structures.filter(session=selected_session)

    if selected_class_id:
        structures = structures.filter(school_class_id=selected_class_id)

    if row_mode != "all":
        structures = structures.filter(amount__gt=Decimal("0.00"))

    totals = structures.aggregate(
        total_amount=Sum("amount"),
        total_rows=Count("id"),
    )
    class_totals = (
        structures.values(
            "school_class_id",
            "school_class__name",
            "school_class__display_order",
        )
        .annotate(total_amount=Sum("amount"), fee_heads=Count("id"))
        .order_by("school_class__display_order", "school_class__name")
    )

    return render(
        request,
        "core/fee_structure_report.html",
        {
            "structures": structures,
            "class_totals": class_totals,
            "sessions": sessions,
            "classes": SchoolClass.objects.order_by("display_order", "name"),
            "selected_session": selected_session,
            "selected_session_id": str(selected_session.id) if selected_session else selected_session_id,
            "selected_class_id": selected_class_id,
            "row_mode": row_mode,
            "totals": totals,
        },
    )


def marks_report(request):
    selected_term_id = request.GET.get("term", "").strip()
    selected_class_id = request.GET.get("class", "").strip()
    query = request.GET.get("q", "").strip()

    terms = (
        ExamTerm.objects.select_related("session")
        .filter(tests__marks__isnull=False)
        .distinct()
        .order_by("-session__name", "display_order", "name")
    )
    selected_term = terms.filter(pk=selected_term_id).first() if selected_term_id else None
    if selected_term is None:
        selected_term = terms.first()

    marks = ExamMark.objects.select_related(
        "student",
        "student__current_class",
        "student__current_section",
        "exam_test",
        "exam_test__subject",
        "exam_test__term",
    )

    if selected_term:
        marks = marks.filter(exam_test__term=selected_term)
    else:
        marks = marks.none()

    if selected_class_id:
        marks = marks.filter(exam_test__school_class_id=selected_class_id)

    if query:
        marks = marks.filter(
            Q(student__full_name__icontains=query)
            | Q(student__father_name__icontains=query)
            | Q(student__legacy_sid__icontains=query)
            | Q(student__admission_no__icontains=query)
        )

    summary = marks.aggregate(
        mark_rows=Count("id"),
        subjects=Count("exam_test__subject", distinct=True),
        tests=Count("exam_test", distinct=True),
    )
    grouped_rows = marks.values(
        "student_id",
        "student__legacy_sid",
        "student__admission_no",
        "student__full_name",
        "student__father_name",
        "student__current_class__name",
        "student__current_class__display_order",
        "student__current_section__name",
    ).annotate(
        subjects=Count("id"),
        absent=Count("id", filter=Q(is_absent=True)),
        total_obtained=Sum("marks_obtained"),
        total_max=Sum("exam_test__max_marks"),
    ).order_by(
        "student__current_class__display_order",
        "student__current_section__name",
        "student__full_name",
    )

    rows = []
    for row in grouped_rows:
        total_obtained = row["total_obtained"] or Decimal("0.00")
        total_max = row["total_max"] or Decimal("0.00")
        percentage = None
        if total_max:
            percentage = (total_obtained / total_max * Decimal("100")).quantize(Decimal("0.01"))

        rows.append(
            {
                **row,
                "total_obtained": total_obtained,
                "total_max": total_max,
                "percentage": percentage,
            }
        )

    paginator = Paginator(rows, 50)
    page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "core/marks_report.html",
        {
            "page": page,
            "terms": terms,
            "classes": SchoolClass.objects.order_by("display_order", "name"),
            "selected_term": selected_term,
            "selected_term_id": str(selected_term.id) if selected_term else selected_term_id,
            "selected_class_id": selected_class_id,
            "query": query,
            "summary": summary,
            "total_students": len(rows),
        },
    )


def receipt_list(request):
    query = request.GET.get("q", "").strip()
    class_id = request.GET.get("class", "").strip()
    payment_mode = request.GET.get("payment_mode", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    receipts = FeeReceipt.objects.select_related(
        "student",
        "student__current_class",
        "student__current_section",
        "session",
    ).order_by("-receipt_date", "-legacy_receipt_no", "-id")

    if query:
        receipts = receipts.filter(
            Q(receipt_no__icontains=query)
            | Q(legacy_receipt_no__icontains=query)
            | Q(student__full_name__icontains=query)
            | Q(student__legacy_sid__icontains=query)
            | Q(student__admission_no__icontains=query)
        )

    if class_id:
        receipts = receipts.filter(student__current_class_id=class_id)

    if payment_mode:
        receipts = receipts.filter(payment_mode=payment_mode)

    if date_from:
        receipts = receipts.filter(receipt_date__gte=date_from)

    if date_to:
        receipts = receipts.filter(receipt_date__lte=date_to)

    totals = receipts.aggregate(
        received=Sum("received_amount"),
        net=Sum("legacy_net_total"),
        due=Sum("legacy_due_amount"),
    )
    paginator = Paginator(receipts, 50)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page": page,
        "query": query,
        "selected_class": class_id,
        "selected_payment_mode": payment_mode,
        "date_from": date_from,
        "date_to": date_to,
        "classes": SchoolClass.objects.order_by("display_order", "name"),
        "payment_modes": FeeReceipt.PaymentMode.choices,
        "totals": totals,
        "total_receipts": receipts.count(),
    }
    return render(request, "core/receipt_list.html", context)


def due_report(request):
    rows, totals = get_due_report_rows(request)
    paginator = Paginator(rows, 50)
    page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "core/due_report.html",
        {
            "page": page,
            "query": request.GET.get("q", "").strip(),
            "selected_class": request.GET.get("class", "").strip(),
            "classes": SchoolClass.objects.order_by("display_order", "name"),
            "total_students": rows.count(),
            "totals": totals,
        },
    )


def due_report_pdf(request):
    rows, totals = get_due_report_rows(request)
    pdf_bytes = build_due_report_pdf(list(rows), totals, get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="due-report.pdf"'
    return response


def get_due_report_rows(request):
    query = request.GET.get("q", "").strip()
    class_id = request.GET.get("class", "").strip()

    receipts = FeeReceipt.objects.select_related(
        "student",
        "student__current_class",
        "student__current_section",
    ).filter(legacy_due_amount__gt=0)

    if query:
        receipts = receipts.filter(
            Q(student__full_name__icontains=query)
            | Q(student__father_name__icontains=query)
            | Q(student__legacy_sid__icontains=query)
            | Q(student__admission_no__icontains=query)
        )

    if class_id:
        receipts = receipts.filter(student__current_class_id=class_id)

    rows = receipts.values(
        "student_id",
        "student__legacy_sid",
        "student__full_name",
        "student__father_name",
        "student__current_class__name",
        "student__current_class__display_order",
        "student__current_section__name",
        "student__mobile_primary",
    ).annotate(
        due_amount=Sum("legacy_due_amount"),
        paid_amount=Sum("received_amount"),
        net_amount=Sum("legacy_net_total"),
    ).order_by(
        "student__current_class__display_order",
        "student__current_section__name",
        "student__full_name",
    )

    totals = rows.aggregate(
        due=Sum("due_amount"),
        paid=Sum("paid_amount"),
        net=Sum("net_amount"),
    )
    return rows, totals


def receipt_create(request):
    recent_receipts = FeeReceipt.objects.select_related(
        "student",
        "student__current_class",
        "student__current_section",
    ).order_by("-receipt_date", "-id")[:8]
    today_totals = FeeReceipt.objects.filter(receipt_date=timezone.localdate()).aggregate(
        received=Sum("received_amount"),
        due=Sum("legacy_due_amount"),
        count=Count("id"),
    )

    if request.method == "POST":
        receipt_form = FeeReceiptEntryForm(request.POST)
        line_form = FeeReceiptLineEntryForm(request.POST)

        if receipt_form.is_valid() and line_form.is_valid():
            with transaction.atomic():
                receipt = receipt_form.save(commit=False)
                receipt.receipt_no = next_manual_receipt_no()
                line_total = line_form.cleaned_data["line_total"]
                receipt.legacy_fee_total = line_total
                receipt.legacy_net_total = line_total + receipt.late_fee_amount - receipt.concession_amount
                receipt.legacy_due_amount = max(
                    receipt.legacy_net_total - receipt.received_amount,
                    Decimal("0.00"),
                )
                receipt.save()

                for fee_head, amount in line_form.amounts():
                    receipt.lines.create(fee_head=fee_head, amount=amount)

            return redirect("core:receipt_detail", pk=receipt.pk)
    else:
        receipt_form = FeeReceiptEntryForm()
        line_form = FeeReceiptLineEntryForm()

    return render(
        request,
        "core/receipt_form.html",
        {
            "receipt_form": receipt_form,
            "line_form": line_form,
            "recent_receipts": recent_receipts,
            "today_totals": today_totals,
        },
    )


def receipt_detail(request, pk):
    receipt = get_object_or_404(
        FeeReceipt.objects.select_related(
            "student",
            "student__current_class",
            "student__current_section",
            "session",
        ).prefetch_related("lines", "lines__fee_head"),
        pk=pk,
    )
    return render(
        request,
        "core/receipt_detail.html",
        {
            "receipt": receipt,
            "school_profile": get_active_school_profile(),
        },
    )


def receipt_pdf(request, pk):
    receipt = get_object_or_404(
        FeeReceipt.objects.select_related(
            "student",
            "student__current_class",
            "student__current_section",
            "session",
        ).prefetch_related("lines", "lines__fee_head"),
        pk=pk,
    )
    pdf_bytes = build_fee_receipt_pdf(receipt, get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{receipt.receipt_no}.pdf"'
    return response


def student_fee_defaults(request, pk):
    student = get_object_or_404(Student.objects.select_related("current_class", "current_section"), pk=pk)
    session_id = request.GET.get("session")
    structures = FeeStructure.objects.select_related("fee_head").filter(school_class=student.current_class)

    if session_id:
        structures = structures.filter(session_id=session_id)

    if not structures.exists():
        structures = FeeStructure.objects.select_related("fee_head").filter(school_class=student.current_class)

    amounts = {
        f"fee_head_{structure.fee_head_id}": str(structure.amount)
        for structure in structures
        if structure.amount > Decimal("0.00")
    }

    return JsonResponse(
        {
            "student": student.full_name,
            "class": student.current_class.name if student.current_class else "",
            "section": student.current_section.name if student.current_section else "",
            "amounts": amounts,
        }
    )


def next_manual_receipt_no():
    timestamp = timezone.localtime().strftime("%Y%m%d%H%M%S")
    base = f"MR-{timestamp}"
    receipt_no = base
    suffix = 1

    while FeeReceipt.objects.filter(receipt_no=receipt_no).exists():
        suffix += 1
        receipt_no = f"{base}-{suffix}"

    return receipt_no

def get_collection_report_rows(request):
    from datetime import datetime
    date_from_str = request.GET.get('date_from', '')
    date_to_str = request.GET.get('date_to', '')
    
    receipts = FeeReceipt.objects.select_related(
        'student',
        'student__current_class',
        'student__current_section',
    ).order_by('receipt_date', 'receipt_no')
    
    date_from = None
    date_to = None
    
    if date_from_str:
        try:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
            receipts = receipts.filter(receipt_date__gte=date_from)
        except ValueError:
            pass
            
    if date_to_str:
        try:
            date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
            receipts = receipts.filter(receipt_date__lte=date_to)
        except ValueError:
            pass

    if not date_from_str and not date_to_str:
        # Default to today if no dates provided
        today = timezone.localdate()
        date_from_str = today.strftime('%Y-%m-%d')
        date_to_str = date_from_str
        receipts = receipts.filter(receipt_date=today)
        
    totals = receipts.aggregate(
        total_received=Sum('received_amount'),
        total_concession=Sum('concession_amount'),
        total_legacy_net=Sum('legacy_net_total')
    )
    
    return receipts, totals, date_from_str, date_to_str


def collection_report(request):
    receipts, totals, date_from_str, date_to_str = get_collection_report_rows(request)
    
    return render(request, 'core/collection_report.html', {
        'receipts': receipts,
        'totals': totals,
        'date_from_str': date_from_str,
        'date_to_str': date_to_str,
        'total_received': totals['total_received'] or Decimal('0.00'),
    })


def collection_report_pdf(request):
    from .pdf import build_collection_report_pdf
    receipts, totals, date_from_str, date_to_str = get_collection_report_rows(request)
    pdf_bytes = build_collection_report_pdf(list(receipts), totals, date_from_str, date_to_str, get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="collection-report.pdf"'
    return response


def admission_form_pdf(request, pk):
    student = get_object_or_404(Student.objects.select_related("current_class", "current_section"), pk=pk)
    pdf_bytes = build_admission_form_pdf(student, get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="admission-form-{student.admission_no or student.pk}.pdf"'
    return response


def character_certificate_pdf(request, pk):
    student = get_object_or_404(Student.objects.select_related("current_class", "current_section"), pk=pk)
    pdf_bytes = build_character_certificate_pdf(student, get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="character-certificate-{student.admission_no or student.pk}.pdf"'
    return response


def next_tc_number():
    timestamp = timezone.localtime().strftime("%Y%m%d%H%M%S")
    base = f"TC-{timestamp}"
    tc_number = base
    suffix = 1

    while TransferCertificate.objects.filter(tc_number=tc_number).exists():
        suffix += 1
        tc_number = f"{base}-{suffix}"

    return tc_number


def tc_detail(request, pk):
    student = get_object_or_404(Student.objects.select_related("current_class", "current_section"), pk=pk)
    tc = getattr(student, "transfer_certificate", None)

    if request.method == "POST":
        instance = tc if tc else TransferCertificate(student=student)
        form = TransferCertificateForm(request.POST, instance=instance)
        if form.is_valid():
            tc_obj = form.save(commit=False)
            tc_obj.student = student
            if not tc_obj.tc_number:
                tc_obj.tc_number = next_tc_number()
            if not tc_obj.last_class_studied_id and student.current_class_id:
                tc_obj.last_class_studied_id = student.current_class_id
            if not tc_obj.last_section and student.current_section:
                tc_obj.last_section = student.current_section.name
            tc_obj.save()
            return redirect("core:tc_detail", pk=student.pk)
    else:
        initial = {}
        if not tc:
            initial = {
                "last_class_studied": student.current_class_id,
                "last_section": student.current_section.name if student.current_section else "",
            }
        form = TransferCertificateForm(instance=tc, initial=initial)

    return render(
        request,
        "core/tc_form.html",
        {
            "student": student,
            "tc": tc,
            "form": form,
        },
    )


def tc_pdf(request, pk):
    student = get_object_or_404(Student, pk=pk)
    tc = get_object_or_404(TransferCertificate.objects.select_related("student", "last_class_studied"), student=student)
    pdf_bytes = build_transfer_certificate_pdf(tc, get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{tc.tc_number}.pdf"'
    return response


def marksheet_select(request, pk):
    student = get_object_or_404(Student.objects.select_related("current_class", "current_section"), pk=pk)
    terms = ExamTerm.objects.select_related("session").filter(
        tests__marks__student=student
    ).distinct().order_by("-session__name", "display_order")
    return render(request, "core/marksheet_select.html", {"student": student, "terms": terms})


def marksheet_pdf(request, pk, term_id):
    student = get_object_or_404(Student.objects.select_related("current_class", "current_section"), pk=pk)
    term = get_object_or_404(ExamTerm.objects.select_related("session"), pk=term_id)
    exam_marks = (
        ExamMark.objects.select_related("exam_test", "exam_test__subject")
        .filter(student=student, exam_test__term=term)
        .order_by("exam_test__subject__display_order", "exam_test__subject__name")
    )
    if not exam_marks.exists():
        return HttpResponse("No marks found for this student and term.", status=404)

    pdf_bytes = build_marksheet_pdf(student, term, list(exam_marks), get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="marksheet-{student.admission_no or student.pk}-{term.name}.pdf"'
    return response


def staff_list(request):
    query = request.GET.get("q", "").strip()
    staff_type = request.GET.get("staff_type", "").strip()
    status = request.GET.get("status", "active").strip()
    staff_qs = Staff.objects.order_by("full_name")

    if query:
        staff_qs = staff_qs.filter(
            Q(full_name__icontains=query)
            | Q(designation__icontains=query)
            | Q(phone__icontains=query)
            | Q(legacy_emp_code__icontains=query)
        )

    if staff_type:
        staff_qs = staff_qs.filter(staff_type=staff_type)

    if status == "active":
        staff_qs = staff_qs.filter(is_active=True)
    elif status == "left":
        staff_qs = staff_qs.filter(is_active=False)

    paginator = Paginator(staff_qs, 50)
    page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "core/staff_list.html",
        {
            "page": page,
            "query": query,
            "selected_staff_type": staff_type,
            "selected_status": status,
            "staff_types": Staff.StaffType.choices,
            "total_staff": staff_qs.count(),
            "active_staff": Staff.objects.filter(is_active=True).count(),
            "salary_payments_count": SalaryPayment.objects.count(),
        },
    )


def staff_detail(request, pk):
    staff = get_object_or_404(Staff, pk=pk)
    salary_payments = staff.salary_payments.order_by("-pay_month", "-id")[:12]
    return render(
        request,
        "core/staff_detail.html",
        {
            "staff": staff,
            "salary_payments": salary_payments,
        },
    )


def transport_list(request):
    query = request.GET.get("q", "").strip()
    route_id = request.GET.get("route", "").strip()
    status = request.GET.get("status", "active").strip()

    assignments = StudentTransport.objects.select_related(
        "student",
        "student__current_class",
        "student__current_section",
        "route",
        "bus",
    ).order_by(
        "student__current_class__display_order",
        "student__current_section__name",
        "student__full_name",
    )

    if query:
        assignments = assignments.filter(
            Q(student__full_name__icontains=query)
            | Q(student__father_name__icontains=query)
            | Q(student__legacy_sid__icontains=query)
            | Q(legacy_route_name__icontains=query)
            | Q(legacy_bus_label__icontains=query)
            | Q(stop_name__icontains=query)
        )

    if route_id:
        assignments = assignments.filter(route_id=route_id)

    if status == "active":
        assignments = assignments.filter(is_active=True)
    elif status == "inactive":
        assignments = assignments.filter(is_active=False)
    elif status == "enabled":
        assignments = assignments.filter(is_transport_enabled=True)
    elif status == "disabled":
        assignments = assignments.filter(is_transport_enabled=False)

    paginator = Paginator(assignments, 50)
    page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "core/transport_list.html",
        {
            "page": page,
            "query": query,
            "selected_route": route_id,
            "selected_status": status,
            "routes": TransportRoute.objects.order_by("name"),
            "route_summary": TransportRoute.objects.annotate(
                assignment_count=Count("student_assignments")
            ).order_by("name")[:12],
            "total_assignments": assignments.count(),
            "active_assignments": StudentTransport.objects.filter(is_active=True).count(),
            "enabled_assignments": StudentTransport.objects.filter(is_transport_enabled=True).count(),
            "total_routes": TransportRoute.objects.count(),
            "total_buses": TransportBus.objects.count(),
        },
    )


def next_slip_no():
    timestamp = timezone.localtime().strftime("%Y%m%d%H%M%S")
    base = f"SAL-{timestamp}"
    slip_no = base
    suffix = 1

    while SalaryPayment.objects.filter(slip_no=slip_no).exists():
        suffix += 1
        slip_no = f"{base}-{suffix}"

    return slip_no


def salary_payment_create(request):
    if request.method == "POST":
        form = SalaryPaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.slip_no = next_slip_no()
            payment.save()
            return redirect("core:salary_payslip_pdf", pk=payment.pk)
    else:
        form = SalaryPaymentForm()

    staff_defaults = {
        staff.id: {
            "basic_pay": str(staff.basic_pay),
            "da": str(staff.da),
            "other_allowances": str(staff.other_allowances),
        }
        for staff in Staff.objects.filter(is_active=True)
    }

    return render(
        request,
        "core/salary_payment_form.html",
        {
            "form": form,
            "staff_defaults": staff_defaults,
        },
    )


def salary_payslip_pdf(request, pk):
    payment = get_object_or_404(SalaryPayment.objects.select_related("staff"), pk=pk)
    pdf_bytes = build_salary_payslip_pdf(payment, get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{payment.slip_no}.pdf"'
    return response
