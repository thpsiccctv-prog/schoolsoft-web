import csv
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, ProtectedError, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .access import user_can_access, user_is_readonly
from .forms import DisciplineRecordForm, FamilyForm, FeeReceiptEditForm, FeeReceiptEntryForm, FeeReceiptLineEntryForm, InventoryIssueForm, InventoryItemForm, SalaryPaymentForm, StudentForm, TransferCertificateForm
from .models import (
    AcademicSession,
    DisciplineRecord,
    ExamMark,
    ExamTerm,
    Family,
    FeeHead,
    FeeReceipt,
    FeeReceiptAuditLog,
    FeeStructure,
    House,
    InventoryIssue,
    InventoryItem,
    SalaryPayment,
    SalaryPaymentAuditLog,
    SchoolClass,
    SchoolProfile,
    Section,
    Staff,
    Student,
    StudentTransport,
    TransferCertificate,
    TransportBus,
    TransportRoute,
    Voucher,
)
from .whatsapp import build_wa_link, family_due_message
from .pdf import (
    build_admission_form_pdf,
    build_character_certificate_pdf,
    build_discipline_summary_pdf,
    build_due_report_pdf,
    build_fee_receipt_pdf,
    build_id_card_batch_pdf,
    build_id_card_pdf,
    build_marksheet_pdf,
    build_salary_payslip_pdf,
    build_scholar_register_book_pdf,
    build_scholar_register_index_pdf,
    build_scholar_register_pdf,
    build_transfer_certificate_pdf,
)


def get_active_school_profile():
    return SchoolProfile.objects.filter(is_active=True).first()


def apply_receipt_student_snapshot(receipt):
    student = receipt.student
    receipt.student_name_snapshot = student.full_name or ""
    receipt.father_name_snapshot = student.father_name or ""
    receipt.class_snapshot = student.current_class.name if student.current_class else ""
    receipt.section_snapshot = student.current_section.name if student.current_section else ""


def dashboard(request):
    user = request.user
    today = timezone.localdate()
    active_session = AcademicSession.objects.filter(is_active=True).order_by("-starts_on", "name").first()
    readonly = user_is_readonly(user)

    # Each KPI/tile's underlying query only runs if the user can actually see
    # it - this avoids both a misleading dashboard (cards linking to a 403)
    # and unnecessary work/exposure of numbers the user isn't permitted to view.
    kpis = []
    if user_can_access(user, "fee_collection"):
        today_received = FeeReceipt.objects.filter(receipt_date=today, is_cancelled=False).aggregate(
            total=Sum("received_amount")
        )["total"] or Decimal("0.00")

        # Previous-collection-day context (Stage 2): find the most recent earlier
        # date that actually had money collected (not just "yesterday" - Sundays/
        # holidays have zero receipts, so this naturally skips them without
        # needing a Holiday/working-day calendar model). Deliberately no
        # zyada/kam delta yet - comparing a partial "today so far" total against
        # a previous complete day would be misleading most mornings.
        prev_date = (
            FeeReceipt.objects.filter(receipt_date__lt=today, is_cancelled=False, received_amount__gt=0)
            .order_by("-receipt_date")
            .values_list("receipt_date", flat=True)
            .first()
        )
        prev_total = None
        prev_days_ago = None
        if prev_date:
            prev_days_ago = (today - prev_date).days
            if prev_days_ago <= 13:
                prev_total = FeeReceipt.objects.filter(
                    receipt_date=prev_date, is_cancelled=False
                ).aggregate(total=Sum("received_amount"))["total"] or Decimal("0.00")

        kpis.append({
            "label": "Today's Collection",
            "value": today_received,
            "tone": "success",
            "icon": "collection",
            "currency": True,
            "empty_caption": "Abhi tak koi collection nahi",
            "prev_date": prev_date,
            "prev_total": prev_total,
            "prev_days_ago": prev_days_ago,
        })

    if user_can_access(user, "accounts"):
        today_expenses = Voucher.objects.filter(
            voucher_date=today,
            is_cancelled=False,
            voucher_type=Voucher.VoucherType.CASH_PAYMENT,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        kpis.append({
            "label": "Today's Expense",
            "value": today_expenses,
            "tone": "outflow",
            "icon": "expense",
            "currency": True,
        })

    if user_can_access(user, "dues"):
        total_dues = Decimal("0.00")
        if active_session:
            total_dues = FeeReceipt.objects.filter(
                is_cancelled=False, carried_forward=False, session=active_session, student__is_active=True
            ).aggregate(total=Sum("legacy_due_amount"))["total"] or Decimal("0.00")
        kpis.append({
            "label": "Total Dues",
            "value": total_dues,
            "tone": "attention",
            "icon": "dues",
            "currency": True,
        })

    student_total = 0
    active_students = 0
    if user_can_access(user, "students"):
        student_counts = Student.objects.aggregate(
            total=Count("pk"),
            active=Count("pk", filter=Q(is_active=True)),
        )
        student_total = student_counts["total"]
        active_students = student_counts["active"]
        kpis.append({
            "label": "Active Students",
            "value": active_students,
            "tone": "neutral",
            "icon": "students",
            "currency": False,
        })

    tiles = []
    if user_can_access(user, "fee_collection") and not readonly:
        tiles.append({
            "url": reverse("core:receipt_create"), "color": "positive",
            "label": "Fee Collection", "sub": "Daily counter receipt desk",
            "icon": "receipt",
        })
    if user_can_access(user, "students"):
        tiles.append({
            "url": reverse("core:student_list"), "color": "neutral",
            "label": "Students", "sub": "total", "sub_value": student_total,
            "count": active_students, "icon": "students",
        })
    if user_can_access(user, "receipts"):
        receipt_count = FeeReceipt.objects.filter(session=active_session, is_cancelled=False).count() if active_session else 0
        tiles.append({
            "url": reverse("core:receipt_list"), "color": "neutral",
            "label": "Receipts", "sub": "Register and PDFs",
            "count": receipt_count, "icon": "book",
        })
    if user_can_access(user, "dues"):
        tiles.append({
            "url": reverse("core:due_report"), "color": "attention",
            "label": "Dues", "sub": "Pending fee report", "icon": "clock",
        })
    if user_can_access(user, "marks"):
        tiles.append({
            "url": reverse("core:marks_report"), "color": "neutral",
            "label": "Marks", "sub": "Results and marksheets", "icon": "cap",
        })
    if user_can_access(user, "collection"):
        tiles.append({
            "url": reverse("core:collection_report"), "color": "positive",
            "label": "Collection", "sub": "Daily collection report", "icon": "chart",
        })
    if user_can_access(user, "fee_setup"):
        tiles.append({
            "url": reverse("core:fee_structure_report"), "color": "neutral",
            "label": "Fee Setup", "sub": "Heads and structure",
            "count": FeeHead.objects.count(), "icon": "grid",
        })
    if user_can_access(user, "staff"):
        tiles.append({
            "url": reverse("core:staff_list"), "color": "neutral",
            "label": "Staff", "sub": "Teacher records", "icon": "people",
        })
    if user_can_access(user, "transport"):
        tiles.append({
            "url": reverse("core:transport_list"), "color": "neutral",
            "label": "Transport", "sub": "Routes and buses", "icon": "bus",
        })
    if user_can_access(user, "school_profile"):
        tiles.append({
            "url": reverse("core:school_profile_detail"), "color": "neutral",
            "label": "School Profile", "sub": "Identity and settings", "icon": "building",
        })

    for tile in tiles:
        tile.setdefault("count", None)
        tile.setdefault("sub_value", None)

    context = {
        "today": today,
        "active_session": active_session,
        "dashboard_kpis": kpis,
        "tiles": tiles,
        "can_new_receipt": user_can_access(user, "fee_collection") and not readonly,
        "can_due_report": user_can_access(user, "dues"),
    }
    return render(request, "core/dashboard.html", context)


def _get_filtered_students(request):
    query = request.GET.get("q", "").strip()
    class_id = request.GET.get("class", "").strip()
    section_id = request.GET.get("section", "").strip()
    status = request.GET.get("status", "active").strip() or "active"

    students = Student.objects.select_related("current_class", "current_section").order_by(
        "current_class__display_order",
        "current_section__name",
        "roll_no",
        "full_name",
    )

    if status == "active":
        students = students.filter(is_active=True)
    elif status == "inactive":
        students = students.filter(is_active=False)

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

    return students, query, class_id, section_id, status


def student_list(request):
    students, query, class_id, section_id, status = _get_filtered_students(request)

    all_students = Student.objects.all()
    total_all_students = all_students.count()
    total_active_students = all_students.filter(is_active=True).count()
    total_inactive_students = total_all_students - total_active_students

    try:
        per_page = int(request.GET.get("per_page", 50))
    except ValueError:
        per_page = 50
        
    paginator = Paginator(students, per_page)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page": page,
        "per_page": per_page,
        "total_students": students.count(),
        "query": query,
        "selected_class": class_id,
        "selected_section": section_id,
        "selected_status": status,
        "classes": SchoolClass.objects.order_by("display_order", "name"),
        "sections": Section.objects.select_related("school_class").order_by(
            "school_class__display_order",
            "name",
        ),
        "total_students": students.count(),
        "total_all_students": total_all_students,
        "total_active_students": total_active_students,
        "total_inactive_students": total_inactive_students,
    }
    return render(request, "core/student_list.html", context)


def student_detail(request, pk):
    student = get_object_or_404(
        Student.objects.select_related("current_class", "current_section"),
        pk=pk,
    )
    due_total = FeeReceipt.objects.filter(
        student=student, is_cancelled=False, carried_forward=False, legacy_due_amount__gt=0
    ).aggregate(total=Sum("legacy_due_amount"))["total"] or 0
    school_profile = get_active_school_profile()
    return render(
        request,
        "core/student_detail.html",
        {
            "student": student,
            "due_total": due_total,
            "school_name": school_profile.name if school_profile else "",
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
    session_id = request.GET.get("session", "").strip()
    
    active_session = AcademicSession.objects.filter(is_active=True).first()
    if not session_id and not query:
        session_id = str(active_session.id) if active_session else ""
        
    receipts = FeeReceipt.objects.select_related(
        "student",
        "student__current_class",
        "student__current_section",
        "session",
    ).order_by("-receipt_date", "-legacy_receipt_no", "-id")

    if session_id and session_id != "all":
        receipts = receipts.filter(session_id=session_id)

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

    totals = receipts.filter(is_cancelled=False).aggregate(
        received=Sum("received_amount"),
        net=Sum("legacy_net_total"),
        # carried_forward receipts stay visible in the register (so staff can
        # see the history) but their due is now represented on whatever newer
        # receipt absorbed it via Previous Due - excluded here to avoid the
        # same balance being counted twice in this total.
        due=Sum("legacy_due_amount", filter=Q(carried_forward=False)),
    )
    cancelled_count = receipts.filter(is_cancelled=True).count()
    paginator = Paginator(receipts, 50)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page": page,
        "query": query,
        "selected_class": class_id,
        "selected_payment_mode": payment_mode,
        "selected_session": session_id,
        "date_from": date_from,
        "date_to": date_to,
        "classes": SchoolClass.objects.order_by("display_order", "name"),
        "sessions": AcademicSession.objects.order_by("-starts_on", "name"),
        "payment_modes": FeeReceipt.PaymentMode.choices,
        "totals": totals,
        "total_receipts": receipts.count(),
        "cancelled_count": cancelled_count,
    }
    return render(request, "core/receipt_list.html", context)


def due_report(request):
    rows, totals = get_due_report_rows(request)
    paginator = Paginator(rows, 50)
    page = paginator.get_page(request.GET.get("page"))
    school_profile = get_active_school_profile()

    return render(
        request,
        "core/due_report.html",
        {
            "page": page,
            "query": request.GET.get("q", "").strip(),
            "selected_class": request.GET.get("class", "").strip(),
            "selected_session": getattr(request, "_due_selected_session", ""),
            "selected_status": getattr(request, "_due_selected_status", "active"),
            "classes": SchoolClass.objects.order_by("display_order", "name"),
            "sessions": AcademicSession.objects.order_by("-starts_on", "name"),
            "total_students": rows.count(),
            "totals": totals,
            "school_name": school_profile.name if school_profile else "",
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
    session_id = request.GET.get("session", "").strip()
    status = request.GET.get("status", "active").strip()
    
    active_session = AcademicSession.objects.filter(is_active=True).first()
    if not session_id and not query:
        session_id = str(active_session.id) if active_session else ""
        
    request._due_selected_session = session_id
    request._due_selected_status = status

    receipts = FeeReceipt.objects.select_related(
        "student",
        "student__current_class",
        "student__current_section",
    ).filter(legacy_due_amount__gt=0, is_cancelled=False, carried_forward=False)

    if session_id and session_id != "all":
        receipts = receipts.filter(session_id=session_id)
        
    if status == "active":
        receipts = receipts.filter(student__is_active=True)
    elif status == "inactive":
        receipts = receipts.filter(student__is_active=False)

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
        "student__admission_no",
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
        # False: a receipt that only collects an old Previous Due (all fee-head
        # boxes at 0.00) is valid now - checked together with previous_due_amount
        # below instead of requiring a positive fee-head total on its own.
        line_form = FeeReceiptLineEntryForm(request.POST, require_positive_total=False)

        if receipt_form.is_valid() and line_form.is_valid():
            line_total = line_form.cleaned_data["line_total"]
            previous_due = receipt_form.cleaned_data.get("previous_due_amount") or Decimal("0.00")
            if line_total <= Decimal("0.00") and previous_due <= Decimal("0.00"):
                line_form.add_error(
                    None, "Enter at least one fee head amount, or a Previous Due amount, before saving."
                )
            else:
                with transaction.atomic():
                    receipt = receipt_form.save(commit=False)
                    receipt.receipt_no = next_manual_receipt_no()
                    receipt.legacy_fee_total = line_total
                    receipt.legacy_net_total = (
                        line_total + receipt.previous_due_amount + receipt.late_fee_amount - receipt.concession_amount
                    )
                    receipt.legacy_due_amount = max(
                        receipt.legacy_net_total - receipt.received_amount,
                        Decimal("0.00"),
                    )
                    apply_receipt_student_snapshot(receipt)
                    receipt.save()

                    for fee_head, amount in line_form.amounts():
                        receipt.lines.create(fee_head=fee_head, amount=amount)

                    if receipt.previous_due_amount > Decimal("0.00"):
                        _mark_prior_receipts_carried_forward(receipt)

                if request.POST.get("action") == "save_print":
                    return redirect(f"{reverse('core:receipt_detail', kwargs={'pk': receipt.pk})}?autoprint=1")
                return redirect("core:receipt_detail", pk=receipt.pk)
    else:
        student_id = request.GET.get("student")
        initial_data = {}
        if student_id:
            initial_data["student"] = student_id
        receipt_form = FeeReceiptEntryForm(initial=initial_data)
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


def receipt_cancel(request, pk):
    receipt = get_object_or_404(
        FeeReceipt.objects.select_related("student", "session"),
        pk=pk,
    )

    if receipt.is_cancelled:
        messages.info(request, f"Receipt {receipt.receipt_no} is already cancelled.")
        return redirect("core:receipt_detail", pk=receipt.pk)

    if request.method == "POST":
        reason = request.POST.get("cancel_reason", "").strip()
        if not reason:
            messages.error(request, "A cancellation reason is required.")
            return render(request, "core/receipt_cancel_confirm.html", {"receipt": receipt})

        receipt.is_cancelled = True
        receipt.cancelled_at = timezone.now()
        receipt.cancelled_by = request.user if request.user.is_authenticated else None
        receipt.cancel_reason = reason
        receipt.save(update_fields=["is_cancelled", "cancelled_at", "cancelled_by", "cancel_reason"])
        messages.success(request, f"Receipt {receipt.receipt_no} has been cancelled/voided.")
        return redirect("core:receipt_detail", pk=receipt.pk)

    return render(request, "core/receipt_cancel_confirm.html", {"receipt": receipt})


def receipt_edit(request, pk):
    receipt = get_object_or_404(
        FeeReceipt.objects.select_related("student", "session").prefetch_related("lines", "lines__fee_head"),
        pk=pk,
    )

    if receipt.is_cancelled:
        messages.error(request, f"Receipt {receipt.receipt_no} is cancelled and cannot be edited.")
        return redirect("core:receipt_detail", pk=receipt.pk)

    if request.method == "POST":
        receipt_form = FeeReceiptEditForm(request.POST, instance=receipt)
        line_form = FeeReceiptLineEntryForm(request.POST, require_positive_total=False)

        if receipt_form.is_valid() and line_form.is_valid():
            line_total = line_form.cleaned_data["line_total"]
            previous_due = receipt_form.cleaned_data.get("previous_due_amount") or Decimal("0.00")
            if line_total <= Decimal("0.00") and previous_due <= Decimal("0.00"):
                line_form.add_error(
                    None, "Enter at least one fee head amount, or a Previous Due amount, before saving."
                )
                return render(
                    request,
                    "core/receipt_edit.html",
                    {"receipt_form": receipt_form, "line_form": line_form, "receipt": receipt},
                )
            with transaction.atomic():
                original_receipt = FeeReceipt.objects.get(pk=receipt.pk)
                # Capture before snapshot
                before_snapshot = {
                    "receipt_no": original_receipt.receipt_no,
                    "student": original_receipt.display_student_name,
                    "father_name": original_receipt.display_father_name,
                    "class": original_receipt.display_class_section,
                    "session": original_receipt.session.name,
                    "receipt_date": str(original_receipt.receipt_date),
                    "from_month": original_receipt.from_month,
                    "to_month": original_receipt.to_month,
                    "payment_mode": original_receipt.payment_mode,
                    "previous_due_amount": str(original_receipt.previous_due_amount),
                    "concession_amount": str(original_receipt.concession_amount),
                    "late_fee_amount": str(original_receipt.late_fee_amount),
                    "received_amount": str(original_receipt.received_amount),
                    "legacy_fee_total": str(original_receipt.legacy_fee_total),
                    "legacy_net_total": str(original_receipt.legacy_net_total),
                    "legacy_due_amount": str(original_receipt.legacy_due_amount),
                    "remarks": original_receipt.remarks,
                    "lines": {line.fee_head.name: str(line.amount) for line in original_receipt.lines.all()}
                }

                updated_receipt = receipt_form.save(commit=False)
                
                # Delete old lines and create new ones
                updated_receipt.lines.all().delete()
                
                new_lines = []
                for fee_head, amount in line_form.amounts():
                    new_lines.append(updated_receipt.lines.create(fee_head=fee_head, amount=amount))
                
                # Recalculate totals
                line_total = line_form.cleaned_data["line_total"]
                updated_receipt.legacy_fee_total = line_total
                updated_receipt.legacy_net_total = (
                    line_total + updated_receipt.previous_due_amount
                    + updated_receipt.late_fee_amount - updated_receipt.concession_amount
                )
                updated_receipt.legacy_due_amount = max(
                    updated_receipt.legacy_net_total - updated_receipt.received_amount,
                    Decimal("0.00"),
                )
                apply_receipt_student_snapshot(updated_receipt)
                
                # Update audit fields
                updated_receipt.is_edited = True
                updated_receipt.edited_at = timezone.now()
                updated_receipt.edited_by = request.user if request.user.is_authenticated else None
                updated_receipt.edit_count += 1
                updated_receipt.save()

                # Capture after snapshot
                after_snapshot = {
                    "receipt_no": updated_receipt.receipt_no,
                    "student": updated_receipt.display_student_name,
                    "father_name": updated_receipt.display_father_name,
                    "class": updated_receipt.display_class_section,
                    "session": updated_receipt.session.name,
                    "receipt_date": str(updated_receipt.receipt_date),
                    "from_month": updated_receipt.from_month,
                    "to_month": updated_receipt.to_month,
                    "payment_mode": updated_receipt.payment_mode,
                    "previous_due_amount": str(updated_receipt.previous_due_amount),
                    "concession_amount": str(updated_receipt.concession_amount),
                    "late_fee_amount": str(updated_receipt.late_fee_amount),
                    "received_amount": str(updated_receipt.received_amount),
                    "legacy_fee_total": str(updated_receipt.legacy_fee_total),
                    "legacy_net_total": str(updated_receipt.legacy_net_total),
                    "legacy_due_amount": str(updated_receipt.legacy_due_amount),
                    "remarks": updated_receipt.remarks,
                    "lines": {line.fee_head.name: str(line.amount) for line in new_lines}
                }
                
                # Generate compact changes JSON
                changes = {}
                for key in before_snapshot:
                    if key != "lines":
                        if before_snapshot[key] != after_snapshot[key]:
                            changes[key] = {"before": before_snapshot[key], "after": after_snapshot[key]}
                
                lines_changes = {}
                all_heads = set(before_snapshot["lines"].keys()) | set(after_snapshot["lines"].keys())
                for head in all_heads:
                    b_amt = before_snapshot["lines"].get(head, "0.00")
                    a_amt = after_snapshot["lines"].get(head, "0.00")
                    if b_amt != a_amt:
                        lines_changes[head] = {"before": b_amt, "after": a_amt}
                
                if lines_changes:
                    changes["lines"] = lines_changes

                FeeReceiptAuditLog.objects.create(
                    receipt=updated_receipt,
                    action=FeeReceiptAuditLog.ActionChoices.EDITED,
                    changed_by=request.user if request.user.is_authenticated else None,
                    reason=updated_receipt.edit_reason,
                    before_snapshot=before_snapshot,
                    after_snapshot=after_snapshot,
                    changes=changes
                )

            messages.success(request, f"Receipt {receipt.receipt_no} has been corrected.")
            return redirect("core:receipt_detail", pk=receipt.pk)
    else:
        receipt_form = FeeReceiptEditForm(instance=receipt)
        
        # Populate lines
        initial_lines = {}
        for line in receipt.lines.all():
            initial_lines[f"fee_head_{line.fee_head_id}"] = line.amount
            
        line_form = FeeReceiptLineEntryForm(initial=initial_lines)

    return render(
        request,
        "core/receipt_edit.html",
        {
            "receipt": receipt,
            "receipt_form": receipt_form,
            "line_form": line_form,
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

    previous_due = _suggest_previous_due(student)

    return JsonResponse(
        {
            "student": student.full_name,
            "class": student.current_class.name if student.current_class else "",
            "section": student.current_section.name if student.current_section else "",
            "amounts": amounts,
            "previous_due": f"{previous_due:.2f}",
        }
    )


def _eligible_prior_due_receipts(student, exclude_pk=None):
    """Receipts that can legitimately feed a 'Previous Due' carry-forward for
    this student: unpaid, not cancelled, not already carried forward into an
    even earlier rollup, and entered live in this system (not part of the old
    legacy CSV bulk-import). Shared by the suggestion calculation and the
    marking step so both agree on what counts as 'previous'.

    Deliberately SESSION-AGNOSTIC (as of the July 2026 fix below) - due can
    carry forward from an earlier receipt within the SAME session (e.g. an
    April receipt's leftover balance should show up when collecting May's
    fee) just as much as from an earlier academic session. `exclude_pk` is
    used by the marking step to leave the just-saved receipt itself out of
    its own "prior" set.

    IMPORTANT: legacy bulk-imported receipts (from import_legacy_fees /
    import_yearly_fees - identifiable by legacy_receipt_no being set) are
    deliberately EXCLUDED here. Their stored legacy_due_amount is a stale
    snapshot from the old pre-automation records and is frequently already
    resolved through payments that were never entered into this system, so
    summing it automatically produces inflated, unreliable figures (real
    incident: a student's auto-suggested previous due came out to ~Rs
    56,950 - far more than a full year's fees - because it silently summed
    years of legacy receipts). Per the owner's original request, old/legacy
    due must be entered MANUALLY by office staff who know the correct
    figure; only receipts created going forward inside this app (which have
    no legacy_receipt_no) are trustworthy enough to auto carry-forward."""
    prior_receipts = FeeReceipt.objects.filter(
        student=student,
        is_cancelled=False,
        carried_forward=False,
        legacy_receipt_no__isnull=True,
    ).exclude(legacy_due_amount__lte=Decimal("0.00"))

    if exclude_pk:
        prior_receipts = prior_receipts.exclude(pk=exclude_pk)

    return prior_receipts


def _suggest_previous_due(student):
    """Auto-suggested 'Previous Due' figure for the Fee Collection form - sum
    of the student's unpaid, not-yet-carried-forward, live-system receipts
    (any earlier receipt, same session or an earlier one). Office staff can
    still override this in the form (needed while historical/legacy fee data
    is incomplete); once receipts are consistently recorded this keeps
    working automatically without any manual step."""
    total = _eligible_prior_due_receipts(student).aggregate(total=Sum("legacy_due_amount"))["total"]
    return total or Decimal("0.00")


def _mark_prior_receipts_carried_forward(receipt):
    """Called after saving a new receipt whose previous_due_amount > 0: marks
    the student's earlier eligible unpaid receipts as carried_forward=True so
    the Due Report (and any future previous-due suggestion) stops counting
    them separately - their balance now lives on this new receipt instead.
    Excludes the receipt itself (exclude_pk) so a receipt that still has its
    own leftover due after this save doesn't get marked as carrying its own
    balance forward into itself.
    Note: this marks ALL eligible prior receipts regardless of whether the
    office-entered previous_due_amount exactly matches their sum (the office
    figure is treated as authoritative - see CODEX-HANDOFF.md for the
    reasoning) - if it doesn't match, is_edited/remarks on this receipt is
    the audit trail for why."""
    _eligible_prior_due_receipts(receipt.student, exclude_pk=receipt.pk).update(carried_forward=True)


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
    ).filter(is_cancelled=False).order_by('receipt_date', 'receipt_no')

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
        'selected_session': getattr(request, "_col_selected_session", ""),
        'sessions': AcademicSession.objects.order_by("-starts_on", "name"),
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


def id_card_pdf(request, pk):
    student = get_object_or_404(Student.objects.select_related("current_class", "current_section", "house"), pk=pk)
    pdf_bytes = build_id_card_pdf(student, get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="id-card-{student.admission_no or student.pk}.pdf"'
    return response


def id_card_batch_pdf(request):
    students, query, class_id, section_id, status = _get_filtered_students(request)
    students = students.select_related("current_class", "current_section", "house")
    pdf_bytes = build_id_card_batch_pdf(list(students), get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="id-cards.pdf"'
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
            tc_obj.book_no = student.scholar_register_no
            tc_obj.sr_no = student.admission_no or str(student.legacy_sid or "")
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


def scholar_register_pdf(request, pk):
    # Unlike the TC (which only exists once a student has left), the Scholar
    # Register is the office's permanent record from admission onward - so
    # this is available for any student, active or left.
    student = get_object_or_404(
        Student.objects.select_related("current_class", "current_section", "transfer_certificate", "transfer_certificate__last_class_studied"),
        pk=pk,
    )
    pdf_bytes = build_scholar_register_pdf(student, get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="scholar-register-{student.admission_no or student.pk}.pdf"'
    return response


def _resolve_book_range(request):
    """Reads book/from_no/to_no GET params (same names/semantics as the
    Print Register page's range controls) and resolves them into a concrete
    (book_no, from_no, to_no) integer range. Returns (None, None, None) if
    no usable range was supplied - the full register book only makes sense
    for a fixed, contiguous number range."""
    book_no_raw = request.GET.get("book", "").strip()
    from_raw = request.GET.get("from_no", "").strip()
    to_raw = request.GET.get("to_no", "").strip()

    book_no = int(book_no_raw) if book_no_raw.isdigit() and int(book_no_raw) > 0 else None
    if book_no and not from_raw:
        from_raw = str((book_no - 1) * 100 + 1)
    if book_no and not to_raw:
        to_raw = str(book_no * 100)

    from_no = int(from_raw) if from_raw.isdigit() else None
    to_no = int(to_raw) if to_raw.isdigit() else None
    if from_no is None or to_no is None or from_no > to_no:
        return None, None, None
    return book_no, from_no, to_no


def _scholar_register_book_entries(from_no, to_no):
    """One entry per SID/Admission number in [from_no, to_no], in order.
    Entry is (sid, student_or_None) - None means no student record exists
    for that number (a 'Not Allotted' slot). Includes students of every
    status (active, inactive, TC-issued) by the owner's explicit decision -
    a register is a permanent ledger, students aren't removed from it when
    they leave."""
    students_by_sid = {
        s.legacy_sid: s
        for s in Student.objects.filter(legacy_sid__gte=from_no, legacy_sid__lte=to_no).select_related(
            "current_class", "current_section", "transfer_certificate", "transfer_certificate__last_class_studied"
        )
    }
    return [(n, students_by_sid.get(n)) for n in range(from_no, to_no + 1)]


def scholar_register_book_pdf(request):
    book_no, from_no, to_no = _resolve_book_range(request)
    if from_no is None:
        messages.error(request, "Full Register Book print karne ke liye Book No. ya From/To SID range dein.")
        return redirect("core:student_register")
    entries = _scholar_register_book_entries(from_no, to_no)
    pdf_bytes = build_scholar_register_book_pdf(entries, book_no, from_no, to_no, get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    label = f"book-{book_no}" if book_no else f"{from_no}-{to_no}"
    response["Content-Disposition"] = f'inline; filename="scholar-register-{label}.pdf"'
    return response


def scholar_register_index_pdf(request):
    book_no, from_no, to_no = _resolve_book_range(request)
    if from_no is None:
        messages.error(request, "Scholar Register Index print karne ke liye Book No. ya From/To SID range dein.")
        return redirect("core:student_register")
    entries = _scholar_register_book_entries(from_no, to_no)
    pdf_bytes = build_scholar_register_index_pdf(entries, book_no, from_no, to_no, get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    label = f"book-{book_no}" if book_no else f"{from_no}-{to_no}"
    response["Content-Disposition"] = f'inline; filename="scholar-register-index-{label}.pdf"'
    return response


def marksheet_select(request, pk):
    student = get_object_or_404(Student.objects.select_related("current_class", "current_section"), pk=pk)
    terms = ExamTerm.objects.select_related("session").filter(
        tests__marks__student=student
    ).distinct().order_by("-session__name", "display_order")
    return render(request, "core/marksheet_select.html", {"student": student, "terms": terms})


def check_duplicate_receipt(request):
    student_id = request.GET.get("student")
    session_id = request.GET.get("session")
    from_m = request.GET.get("from_month", "").upper()
    to_m = request.GET.get("to_month", "").upper()

    if not all([student_id, session_id, from_m, to_m]):
        return JsonResponse({"error": "Missing parameters"}, status=400)

    academic_months = ["APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC", "JAN", "FEB", "MAR"]
    try:
        start_idx = academic_months.index(from_m)
        end_idx = academic_months.index(to_m)
        if start_idx > end_idx:
            # Handle reverse range or wrap around if needed, but normally it shouldn't happen.
            start_idx, end_idx = end_idx, start_idx
    except ValueError:
        return JsonResponse({"warning": False})

    requested_range = set(range(start_idx, end_idx + 1))
    
    existing = FeeReceipt.objects.filter(
        student_id=student_id,
        session_id=session_id
    ).values("receipt_no", "from_month", "to_month")

    for receipt in existing:
        r_from = receipt["from_month"].upper()
        r_to = receipt["to_month"].upper()
        try:
            r_start = academic_months.index(r_from)
            r_end = academic_months.index(r_to)
            if r_start > r_end:
                r_start, r_end = r_end, r_start
            existing_range = set(range(r_start, r_end + 1))
            
            if requested_range.intersection(existing_range):
                return JsonResponse({
                    "warning": True, 
                    "message": f"A receipt ({receipt['receipt_no']}) already covers {r_from} to {r_to} in this session."
                })
        except ValueError:
            continue

    return JsonResponse({"warning": False})


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


def discipline_list(request, pk):
    student = get_object_or_404(Student, pk=pk)
    records = student.discipline_records.select_related("reported_by").all()
    school_profile = get_active_school_profile()
    return render(
        request,
        "core/discipline_list.html",
        {
            "student": student,
            "records": records,
            "school_name": school_profile.name if school_profile else "",
        },
    )


def discipline_create(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == "POST":
        form = DisciplineRecordForm(request.POST)
        if form.is_valid():
            record = form.save(commit=False)
            record.student = student
            record.reported_by = request.user
            record.save()
            messages.success(request, "Discipline record added.")
            return redirect("core:discipline_list", pk=student.pk)
    else:
        form = DisciplineRecordForm()
    return render(request, "core/discipline_form.html", {"student": student, "form": form})


def discipline_pdf(request, pk):
    student = get_object_or_404(Student, pk=pk)
    records = list(student.discipline_records.select_related("reported_by").all())
    pdf_bytes = build_discipline_summary_pdf(student, records, get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="discipline-{student.admission_no or student.pk}.pdf"'
    return response


def inventory_item_list(request):
    items = InventoryItem.objects.all()
    return render(request, "core/inventory_item_list.html", {"items": items})


def inventory_item_create(request):
    if request.method == "POST":
        form = InventoryItemForm(request.POST)
        if form.is_valid():
            item = form.save()
            messages.success(request, f"Item '{item.name}' added.")
            return redirect("core:inventory_item_list")
    else:
        form = InventoryItemForm()
    return render(request, "core/inventory_item_form.html", {"form": form})


def inventory_item_toggle_active(request, pk):
    item = get_object_or_404(InventoryItem, pk=pk)
    if request.method == "POST":
        item.is_active = not item.is_active
        item.save(update_fields=["is_active"])
        messages.success(request, f"'{item.name}' is now {'active' if item.is_active else 'inactive'}.")
    return redirect("core:inventory_item_list")


def inventory_report(request):
    issues = InventoryIssue.objects.select_related(
        "student", "student__current_class", "student__current_section", "item"
    ).all()

    query = request.GET.get("q", "").strip()
    class_id = request.GET.get("class", "").strip()
    item_id = request.GET.get("item", "").strip()
    date_from = request.GET.get("from_date", "").strip()
    date_to = request.GET.get("to_date", "").strip()

    if query:
        issues = issues.filter(
            Q(student__full_name__icontains=query)
            | Q(student__admission_no__icontains=query)
            | Q(student__legacy_sid__icontains=query)
        )
    if class_id:
        issues = issues.filter(student__current_class_id=class_id)
    if item_id:
        issues = issues.filter(item_id=item_id)
    if date_from:
        issues = issues.filter(issue_date__gte=date_from)
    if date_to:
        issues = issues.filter(issue_date__lte=date_to)

    issues = issues.order_by("-issue_date", "-id")
    totals = issues.aggregate(total_quantity=Sum("quantity"), total_charged=Sum("amount_charged"))

    paginator = Paginator(issues, 50)
    page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "core/inventory_report.html",
        {
            "page": page,
            "query": query,
            "selected_class": class_id,
            "selected_item": item_id,
            "date_from": date_from,
            "date_to": date_to,
            "classes": SchoolClass.objects.order_by("display_order", "name"),
            "items": InventoryItem.objects.filter(is_active=True),
            "totals": totals,
            "total_records": issues.count(),
        },
    )


def inventory_issue_list(request, pk):
    student = get_object_or_404(Student, pk=pk)
    issues = student.inventory_issues.select_related("item", "issued_by").all()
    total_charged = issues.aggregate(total=Sum("amount_charged"))["total"] or 0
    return render(
        request,
        "core/inventory_issue_list.html",
        {"student": student, "issues": issues, "total_charged": total_charged},
    )


def inventory_issue_create(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == "POST":
        form = InventoryIssueForm(request.POST)
        if form.is_valid():
            issue = form.save(commit=False)
            issue.student = student
            issue.unit_price = issue.item.unit_price
            issue.issued_by = request.user
            issue.save()
            messages.success(request, f"Issued {issue.item.name} to {student.full_name}.")
            return redirect("core:inventory_issue_list", pk=student.pk)
    else:
        form = InventoryIssueForm()
    return render(request, "core/inventory_issue_form.html", {"student": student, "form": form})


def _class_label(student):
    if student.current_class and student.current_section:
        return f"{student.current_class}-{student.current_section.name}"
    return str(student.current_class) if student.current_class else ""


def _student_due_total(student):
    return FeeReceipt.objects.filter(
        student=student, is_cancelled=False, carried_forward=False, legacy_due_amount__gt=0
    ).aggregate(total=Sum("legacy_due_amount"))["total"] or Decimal("0")


def family_list(request):
    query = request.GET.get("q", "").strip()
    families = Family.objects.annotate(member_count=Count("members", distinct=True))
    if query:
        families = families.filter(Q(name__icontains=query) | Q(primary_mobile__icontains=query))
    families = families.order_by("name")
    return render(request, "core/family_list.html", {"families": families, "query": query})


def family_create(request):
    if request.method == "POST":
        form = FamilyForm(request.POST)
        if form.is_valid():
            family = form.save()
            messages.success(request, f"Family '{family.name}' created.")
            return redirect("core:family_detail", pk=family.pk)
    else:
        form = FamilyForm()
    return render(request, "core/family_form.html", {"form": form})


def family_detail(request, pk):
    family = get_object_or_404(Family, pk=pk)
    members = family.members.select_related("current_class", "current_section").order_by("full_name")

    member_dues = []
    total_due = Decimal("0")
    for member in members:
        due = _student_due_total(member)
        member_dues.append({"student": member, "due": due, "class_label": _class_label(member)})
        total_due += due

    query = request.GET.get("q", "").strip()
    search_results = []
    if query:
        search_results = (
            Student.objects.filter(
                Q(full_name__icontains=query)
                | Q(admission_no__icontains=query)
                | Q(legacy_sid__icontains=query)
            )
            .exclude(family=family)
            .select_related("current_class", "current_section")[:20]
        )

    school_profile = get_active_school_profile()
    school_name = school_profile.name if school_profile else ""

    members_tuples = [(md["student"].full_name, md["class_label"], md["due"]) for md in member_dues]
    family_message = family_due_message(family.name, members_tuples, total_due, school_name)
    family_wa_url = build_wa_link(family.primary_mobile, family_message)

    return render(
        request,
        "core/family_detail.html",
        {
            "family": family,
            "member_dues": member_dues,
            "total_due": total_due,
            "query": query,
            "search_results": search_results,
            "school_name": school_name,
            "family_wa_url": family_wa_url,
        },
    )


def family_add_student(request, pk):
    family = get_object_or_404(Family, pk=pk)
    if request.method == "POST":
        student = get_object_or_404(Student, pk=request.POST.get("student_id"))
        student.family = family
        student.save(update_fields=["family"])
        messages.success(request, f"{student.full_name} added to '{family.name}'.")
    return redirect("core:family_detail", pk=family.pk)


def family_remove_student(request, pk, student_id):
    family = get_object_or_404(Family, pk=pk)
    if request.method == "POST":
        student = get_object_or_404(Student, pk=student_id, family=family)
        student.family = None
        student.save(update_fields=["family"])
        messages.success(request, f"{student.full_name} removed from '{family.name}'.")
    return redirect("core:family_detail", pk=family.pk)


def family_suggestions(request):
    unlinked = (
        Student.objects.filter(family__isnull=True, is_active=True)
        .exclude(father_name="")
        .exclude(mobile_primary="")
        .select_related("current_class", "current_section")
    )

    groups = {}
    for student in unlinked:
        key = (student.father_name.strip().lower(), student.mobile_primary.strip())
        groups.setdefault(key, []).append(student)

    suggestions = [
        {
            "father_name": students[0].father_name.strip(),
            "mobile": key[1],
            "students": students,
        }
        for key, students in groups.items()
        if len(students) >= 2
    ]
    suggestions.sort(key=lambda g: g["father_name"])

    return render(request, "core/family_suggestions.html", {"suggestions": suggestions})


def family_create_from_suggestion(request):
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        mobile = request.POST.get("mobile", "").strip()
        student_ids = request.POST.getlist("student_ids")
        if name and student_ids:
            family = Family.objects.create(name=name, primary_mobile=mobile)
            Student.objects.filter(id__in=student_ids, family__isnull=True).update(family=family)
            messages.success(request, f"Family '{family.name}' created with {len(student_ids)} student(s) linked.")
            return redirect("core:family_detail", pk=family.pk)
        messages.error(request, "Select at least one student and provide a family name.")
    return redirect("core:family_suggestions")


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
            if SalaryPayment.objects.filter(staff=payment.staff, pay_month=payment.pay_month, is_cancelled=False).exists():
                form.add_error(None, f"A valid salary payment for {payment.staff.full_name} for this month already exists.")
            else:
                payment.slip_no = next_slip_no()
                payment.save()
                SalaryPaymentAuditLog.objects.create(
                    payment=payment,
                    action=SalaryPaymentAuditLog.ActionChoices.CREATED,
                    changed_by=request.user if request.user.is_authenticated else None,
                    reason="Initial generation"
                )
                return redirect("core:salary_payment_detail", pk=payment.pk)
    else:
        form = SalaryPaymentForm()

    active_staff = Staff.objects.filter(is_active=True)
    staff_defaults = {}
    pending_advances = {}
    
    for staff in active_staff:
        staff_defaults[staff.id] = {
            "basic_pay": str(staff.basic_pay),
            "da": str(staff.da),
            "other_allowances": str(staff.other_allowances),
        }
        
        adv_given = Voucher.objects.filter(
            staff=staff,
            debit_account__group__name__iexact="Advance Given",
            is_cancelled=False
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        
        adv_recovered = SalaryPayment.objects.filter(
            staff=staff,
            is_cancelled=False
        ).aggregate(total=Sum("advance_recovery"))["total"] or Decimal("0.00")
        
        pending_advances[staff.id] = float(adv_given - adv_recovered)

    return render(
        request,
        "core/salary_payment_form.html",
        {
            "form": form,
            "staff_defaults": staff_defaults,
            "pending_advances": pending_advances,
        },
    )


def salary_payslip_pdf(request, pk):
    payment = get_object_or_404(SalaryPayment.objects.select_related("staff"), pk=pk)
    pdf_bytes = build_salary_payslip_pdf(payment, get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{payment.slip_no}.pdf"'
    return response

def student_create(request):
    if request.method == "POST":
        form = StudentForm(request.POST, request.FILES)
        if form.is_valid():
            student = form.save()
            action = request.POST.get("action")
            if action == "save_new":
                return redirect("core:student_create")
            return redirect("core:student_detail", pk=student.pk)
    else:
        form = StudentForm()
        
    recent_students = Student.objects.order_by("-id")[:5]
    context = {
        "form": form,
        "recent_students": recent_students,
        "is_edit": False,
    }
    return render(request, "core/student_form.html", context)


def student_update(request, pk):
    student = get_object_or_404(Student, pk=pk)
    if request.method == "POST":
        form = StudentForm(request.POST, request.FILES, instance=student)
        if form.is_valid():
            form.save()
            return redirect("core:student_detail", pk=student.pk)
    else:
        form = StudentForm(instance=student)
        
    recent_students = Student.objects.order_by("-id")[:5]
    context = {
        "form": form,
        "student": student,
        "recent_students": recent_students,
        "is_edit": True,
    }
    return render(request, "core/student_form.html", context)


def check_student_duplicate(request):
    """Async endpoint to check for duplicate students."""
    field = request.GET.get("field")
    value = request.GET.get("value", "").strip()
    exclude_id = request.GET.get("exclude_id")
    
    if not value or not field:
        return JsonResponse({"duplicate": False})
        
    query = Q()
    if field == "legacy_sid":
        query = Q(legacy_sid=value)
    elif field == "admission_no":
        query = Q(admission_no=value)
    elif field == "mobile":
        query = Q(mobile_primary=value) | Q(mobile_secondary=value)
    else:
        return JsonResponse({"duplicate": False})
        
    qs = Student.objects.filter(query)
    if exclude_id and exclude_id.isdigit():
        qs = qs.exclude(pk=exclude_id)
        
    matches = qs.values_list("full_name", "current_class__name")[:3]
    
    if matches:
        names = [f"{m[0]} ({m[1] or 'No class'})" for m in matches]
        return JsonResponse({
            "duplicate": True, 
            "message": f"Found existing student(s) with this {field}: " + ", ".join(names)
        })
        
    return JsonResponse({"duplicate": False})

def student_register(request):
    """
    Renders a printable student register with the exact same filtering as student_list.
    """
    students, query, class_id, section_id, status = _get_filtered_students(request)

    book_no = request.GET.get("book", "").strip()
    from_no = request.GET.get("from_no", "").strip()
    to_no = request.GET.get("to_no", "").strip()
    if book_no.isdigit() and int(book_no) > 0:
        book_number = int(book_no)
        from_no = from_no or str(((book_number - 1) * 100) + 1)
        to_no = to_no or str(book_number * 100)

    if from_no.isdigit():
        students = students.filter(legacy_sid__gte=int(from_no))
    if to_no.isdigit():
        students = students.filter(legacy_sid__lte=int(to_no))

    # Determine filter description for header
    filter_description = []
    if class_id:
        cls = SchoolClass.objects.filter(pk=class_id).first()
        if cls:
            filter_description.append(f"Class: {cls.name}")
    if section_id:
        sec = Section.objects.filter(pk=section_id).first()
        if sec:
            filter_description.append(f"Section: {sec.name}")
    filter_description.append(f"Status: {status.title()}")
    if query:
        filter_description.append(f"Search: '{query}'")
    if from_no or to_no:
        filter_description.append(f"SID Range: {from_no or 'start'} to {to_no or 'end'}")

    context = {
        "students": students,
        "filter_description": " | ".join(filter_description),
        "total_students": students.count(),
        "print_date": timezone.now(),
        "query": query,
        "selected_class": class_id,
        "selected_section": section_id,
        "selected_status": status,
        "book_no": book_no,
        "from_no": from_no,
        "to_no": to_no,
    }
    return render(request, "core/student_register_report.html", context)

def student_export_csv(request):
    """
    Exports the currently filtered students to a CSV file.
    """
    students, query, class_id, section_id, status = _get_filtered_students(request)
    
    # Generate filename
    date_str = timezone.now().strftime("%Y%m%d")
    status_str = status.title()
    filename = f"Students_{status_str}_{date_str}.csv"
    
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    
    # Write UTF-8 BOM for Excel compatibility with Hindi/Unicode characters
    response.write('\ufeff')
    
    writer = csv.writer(response)
    # Header row
    writer.writerow([
        "Registration No",
        "Admission No",
        "SID",
        "Admission Date",
        "Student Name",
        "Class",
        "Section",
        "DOB",
        "Gender",
        "Father's Name",
        "Mother's Name",
        "Category",
        "Religion",
        "Aadhaar Number",
        "Mobile Primary",
        "Mobile Secondary",
        "Address",
        "Status"
    ])
    
    for st in students:
        class_name = st.current_class.name if st.current_class else ""
        section_name = st.current_section.name if st.current_section else ""
        adm_date = st.admission_date.strftime("%d/%m/%Y") if st.admission_date else ""
        dob = st.date_of_birth.strftime("%d/%m/%Y") if st.date_of_birth else ""
        status_text = "Active" if st.is_active else "Inactive"
        
        address = st.address_local or st.address_permanent or ""
        
        writer.writerow([
            st.registration_no,
            st.admission_no,
            st.legacy_sid,
            adm_date,
            st.full_name,
            class_name,
            section_name,
            dob,
            st.get_gender_display(),
            st.father_name,
            st.mother_name,
            st.category,
            st.religion,
            st.aadhaar_no,
            st.mobile_primary,
            st.mobile_secondary,
            address.replace("\n", " ").replace("\r", ""),
            status_text
        ])
        
    return response

def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    
    if request.method == "POST":
        try:
            student.delete()
            messages.success(request, f"Student {student.full_name} deleted successfully.")
        except ProtectedError:
            messages.error(request, f"Cannot delete {student.full_name} because they have fee receipts or marks. Please mark them as Inactive instead.")
        return redirect("core:student_list")
        
    return render(request, "core/student_confirm_delete.html", {"student": student})

# ---------------------------------------------------------------------------
# Accounts / Cash Book (Phase 1)
# ---------------------------------------------------------------------------

def _generate_voucher_no(session, voucher_type):
    from django.db import transaction
    from .models import VoucherCounter
    year_str = session.name
    if not year_str and session.starts_on and session.ends_on:
        year_str = f"{session.starts_on.year}-{str(session.ends_on.year)[-2:]}"
    year_str = year_str or "SESSION"

    with transaction.atomic():
        counter, _ = VoucherCounter.objects.select_for_update().get_or_create(
            session=session, voucher_type=voucher_type
        )
        counter.last_number += 1
        counter.save()
        return f"{voucher_type}-{year_str}-{counter.last_number:04d}"


def _get_cash_account():
    from .models import LedgerAccount
    return LedgerAccount.objects.filter(is_cash_or_bank=True, name__icontains="cash").first()


@login_required
@permission_required('core.access_accounts', raise_exception=True)
def expense_create(request):
    from .forms import VoucherForm
    from .models import AcademicSession, Voucher, VoucherAuditLog, AccountGroup, Staff
    from django.utils import timezone
    from django.db import transaction
    
    session = AcademicSession.objects.filter(is_active=True).first()
    if not session:
        messages.error(request, "No active academic session found.")
        return redirect("core:dashboard")

    if request.method == "POST":
        form = VoucherForm(request.POST, voucher_kind="expense")
        if form.is_valid():
            voucher = form.save(commit=False)
            voucher.session = session
            voucher.voucher_type = Voucher.VoucherType.CASH_PAYMENT
            voucher.created_by = request.user
            
            # For expense/advance payment, credit should be Cash/Bank and debit should be Expense,
            # Advance Given, or a Liability being paid down (e.g. repaying a personal loan someone
            # advanced to the school - a real case: "Pragati ka paisa wapas kar diya gya" in the
            # legacy ledger. Repaying a loan reduces what the school owes, which is a Liability
            # debit, not an Expense - the old check rejected this with no way to record it).
            if not voucher.credit_account.is_cash_or_bank:
                messages.error(request, "For expenses/advances, the credit account must be a Cash or Bank account.")
            elif not (
                voucher.debit_account.group.group_type == AccountGroup.GroupType.EXPENSE
                or voucher.debit_account.group.group_type == AccountGroup.GroupType.LIABILITY
                or voucher.debit_account.group.name.lower() == "advance given"
            ):
                messages.error(request, "For expenses/advances, the debit account must be an Expense, Liability, or Advance Given account.")
            else:
                with transaction.atomic():
                    voucher.voucher_no = _generate_voucher_no(session, Voucher.VoucherType.CASH_PAYMENT)
                    voucher.save()
                    
                    VoucherAuditLog.objects.create(
                        voucher=voucher,
                        action=VoucherAuditLog.Action.CREATED,
                        changed_by=request.user,
                    )
                
                messages.success(request, f"Expense voucher {voucher.voucher_no} created successfully.")
                if "save_and_add_another" in request.POST:
                    return redirect("core:expense_create")
                return redirect("core:voucher_detail", pk=voucher.pk)
    else:
        initial = {"credit_account": _get_cash_account()}
        form = VoucherForm(initial=initial, voucher_kind="expense")

    return render(request, "core/expense_form.html", {"form": form})

@login_required
@permission_required('core.access_accounts', raise_exception=True)
def receipt_other_create(request):
    from .forms import VoucherForm
    from .models import AcademicSession, Voucher, VoucherAuditLog, AccountGroup
    from django.utils import timezone
    from django.db import transaction
    
    session = AcademicSession.objects.filter(is_active=True).first()
    if not session:
        messages.error(request, "No active academic session found.")
        return redirect("core:dashboard")

    if request.method == "POST":
        form = VoucherForm(request.POST, voucher_kind="receipt")
        if form.is_valid():
            voucher = form.save(commit=False)
            voucher.session = session
            voucher.voucher_type = Voucher.VoucherType.CASH_RECEIPT
            voucher.created_by = request.user
            
            # For receipts, debit should be Cash/Bank, credit should be Income OR a Liability
            # increasing (e.g. someone personally advancing cash to the school - a real case:
            # "PRAGATI PERSONAL/ADVANCE A/C ... SCHOOL KE KHARCH KE LIYE LOAN LIYA GAYA" in the
            # legacy ledger). Receiving a loan is real cash in, but it's not Income - it's a
            # Liability the school now owes back. The old check rejected this with no way to
            # record it, which would have blocked the owner's own decision to move this kind of
            # entry into the new app going forward.
            if not voucher.debit_account.is_cash_or_bank:
                messages.error(request, "For receipts, the debit account must be a Cash or Bank account.")
            elif voucher.credit_account.group.group_type not in (
                AccountGroup.GroupType.INCOME,
                AccountGroup.GroupType.LIABILITY,
            ):
                messages.error(request, "For receipts, the credit account must be an Income or Liability account.")
            else:
                with transaction.atomic():
                    voucher.voucher_no = _generate_voucher_no(session, Voucher.VoucherType.CASH_RECEIPT)
                    voucher.save()
                    
                    VoucherAuditLog.objects.create(
                        voucher=voucher,
                        action=VoucherAuditLog.Action.CREATED,
                        changed_by=request.user,
                    )
                
                messages.success(request, f"Receipt voucher {voucher.voucher_no} created successfully.")
                if "save_and_add_another" in request.POST:
                    return redirect("core:receipt_other_create")
                return redirect("core:voucher_detail", pk=voucher.pk)
    else:
        initial = {"debit_account": _get_cash_account()}
        form = VoucherForm(initial=initial, voucher_kind="receipt")
        
    return render(request, "core/receipt_other_form.html", {"form": form})


@login_required
@permission_required('core.access_accounts', raise_exception=True)
def ledger_list(request):
    from .models import LedgerAccount, AccountGroup
    ledgers = LedgerAccount.objects.select_related("group").all()
    return render(request, "core/ledger_list.html", {"ledgers": ledgers})


@login_required
@permission_required('core.access_accounts', raise_exception=True)
def ledger_create(request):
    from .forms import LedgerAccountForm
    if request.method == "POST":
        form = LedgerAccountForm(request.POST)
        if form.is_valid():
            ledger = form.save()
            messages.success(request, f"Ledger '{ledger.name}' created.")
            return redirect("core:ledger_list")
    else:
        form = LedgerAccountForm()
    return render(request, "core/ledger_form.html", {"form": form, "is_edit": False})


@login_required
@permission_required('core.access_accounts', raise_exception=True)
def ledger_edit(request, pk):
    from .models import LedgerAccount
    from .forms import LedgerAccountForm
    ledger = get_object_or_404(LedgerAccount, pk=pk)
    if request.method == "POST":
        form = LedgerAccountForm(request.POST, instance=ledger)
        if form.is_valid():
            form.save()
            messages.success(request, f"Ledger '{ledger.name}' updated.")
            return redirect("core:ledger_list")
    else:
        form = LedgerAccountForm(instance=ledger)
    return render(request, "core/ledger_form.html", {"form": form, "is_edit": True})


@login_required
@permission_required('core.access_accounts', raise_exception=True)
def voucher_list(request):
    from .models import Voucher
    vouchers = Voucher.objects.select_related("debit_account", "credit_account").all()
    
    q = request.GET.get("q", "").strip()
    if q:
        vouchers = vouchers.filter(voucher_no__icontains=q)
        
    v_type = request.GET.get("type", "")
    if v_type:
        vouchers = vouchers.filter(voucher_type=v_type)
        
    paginator = Paginator(vouchers, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    
    return render(request, "core/voucher_list.html", {
        "page_obj": page_obj,
        "q": q,
        "v_type": v_type,
        "voucher_types": Voucher.VoucherType.choices,
    })


@login_required
@permission_required('core.access_accounts', raise_exception=True)
def voucher_detail(request, pk):
    from .models import Voucher
    voucher = get_object_or_404(Voucher.objects.select_related("debit_account", "credit_account", "created_by", "cancelled_by", "edited_by"), pk=pk)
    logs = voucher.audit_logs.select_related("changed_by").all()
    return render(request, "core/voucher_detail.html", {"voucher": voucher, "logs": logs})


@login_required
@permission_required('core.access_accounts', raise_exception=True)
def voucher_edit(request, pk):
    from .models import Voucher, VoucherAuditLog
    from .forms import VoucherEditForm
    from django.db import transaction
    from django.forms.models import model_to_dict
    
    voucher = get_object_or_404(Voucher, pk=pk)
    if voucher.is_cancelled:
        messages.error(request, "Cannot edit a cancelled voucher.")
        return redirect("core:voucher_detail", pk=voucher.pk)
        
    if request.method == "POST":
        form = VoucherEditForm(request.POST, instance=voucher)
        if form.is_valid():
            before_snapshot = model_to_dict(voucher)
            
            updated = form.save(commit=False)
            updated.is_edited = True
            updated.edited_at = timezone.now()
            updated.edited_by = request.user
            updated.edit_count += 1
            updated.edit_reason = form.cleaned_data["edit_reason"]
            
            with transaction.atomic():
                updated.save()
                after_snapshot = model_to_dict(updated)
                
                # compute changes
                changes = {}
                for field in before_snapshot:
                    if field in ["edited_at", "edited_by", "edit_count", "is_edited", "edit_reason"]:
                        continue
                    if str(before_snapshot[field]) != str(after_snapshot[field]):
                        changes[field] = {"old": str(before_snapshot[field]), "new": str(after_snapshot[field])}
                
                VoucherAuditLog.objects.create(
                    voucher=updated,
                    action=VoucherAuditLog.Action.EDITED,
                    changed_by=request.user,
                    reason=updated.edit_reason,
                    before_snapshot=before_snapshot,
                    after_snapshot=after_snapshot,
                    changes=changes,
                )
            
            messages.success(request, f"Voucher {voucher.voucher_no} edited.")
            return redirect("core:voucher_detail", pk=voucher.pk)
    else:
        form = VoucherEditForm(instance=voucher)
        
    return render(request, "core/voucher_form.html", {"form": form, "voucher": voucher, "is_edit": True})


@login_required
@permission_required('core.access_accounts', raise_exception=True)
def voucher_cancel(request, pk):
    from .models import Voucher, VoucherAuditLog
    from django.db import transaction
    
    voucher = get_object_or_404(Voucher, pk=pk)
    if voucher.is_cancelled:
        messages.warning(request, "Voucher is already cancelled.")
        return redirect("core:voucher_detail", pk=voucher.pk)
        
    if request.method == "POST":
        reason = request.POST.get("cancel_reason", "").strip()
        if not reason:
            messages.error(request, "Cancellation reason is required.")
        else:
            with transaction.atomic():
                voucher.is_cancelled = True
                voucher.cancelled_at = timezone.now()
                voucher.cancelled_by = request.user
                voucher.cancel_reason = reason
                voucher.save()
                
                VoucherAuditLog.objects.create(
                    voucher=voucher,
                    action=VoucherAuditLog.Action.CANCELLED,
                    changed_by=request.user,
                    reason=reason,
                )
                
            messages.success(request, f"Voucher {voucher.voucher_no} has been cancelled.")
            return redirect("core:voucher_detail", pk=voucher.pk)
            
    return render(request, "core/voucher_cancel_confirm.html", {"voucher": voucher})


@login_required
@permission_required('core.access_accounts', raise_exception=True)
def voucher_pdf(request, pk):
    from .models import Voucher
    from .pdf import build_voucher_pdf
    
    voucher = get_object_or_404(Voucher.objects.select_related("debit_account", "credit_account"), pk=pk)
    pdf_bytes = build_voucher_pdf(voucher, get_active_school_profile())
    
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="voucher_{voucher.voucher_no}.pdf"'
    return response


@login_required
@permission_required('core.access_accounts', raise_exception=True)
def cash_book(request):
    from .models import Voucher, FeeReceipt, SalaryPayment, LedgerAccount
    from django.db.models import Sum
    import datetime
    
    from_date_str = request.GET.get("from_date")
    to_date_str = request.GET.get("to_date")
    
    try:
        if from_date_str:
            from_date = datetime.datetime.strptime(from_date_str, "%Y-%m-%d").date()
        else:
            from_date = timezone.localdate()
    except ValueError:
        from_date = timezone.localdate()
        
    try:
        if to_date_str:
            to_date = datetime.datetime.strptime(to_date_str, "%Y-%m-%d").date()
        else:
            to_date = timezone.localdate()
    except ValueError:
        to_date = timezone.localdate()
        
    if from_date > to_date:
        from_date, to_date = to_date, from_date
        
    include_salary = request.GET.get("include_salary") == "1"
    
    cash_ledger = _get_cash_account()
    if not cash_ledger:
        messages.error(request, "Cash ledger not found. Please run seed_accounts.")
        return redirect("core:dashboard")
        
    # Get all transactions for the date range
    
    # 1. Fee Receipts (Cash Receipt)
    fee_receipts = FeeReceipt.objects.filter(
        receipt_date__gte=from_date,
        receipt_date__lte=to_date,
        is_cancelled=False,
        payment_mode=FeeReceipt.PaymentMode.CASH
    ).select_related("student")
    
    # 2. Vouchers (Cash Payments and Cash Receipts, Contra)
    vouchers = Voucher.objects.filter(
        voucher_date__gte=from_date,
        voucher_date__lte=to_date,
        is_cancelled=False,
    ).filter(Q(debit_account=cash_ledger) | Q(credit_account=cash_ledger)).select_related("debit_account", "credit_account")
    
    # 3. Salary Payments (Cash Payment)
    salary_payments = []
    if include_salary:
        salary_payments = SalaryPayment.objects.filter(
            payment_date__gte=from_date,
            payment_date__lte=to_date,
            payment_mode=SalaryPayment.PaymentMode.CASH,
            is_cancelled=False
        ).select_related("staff")
        
    # Calculate opening balance up to from_date - 1 day
    # Base OB
    ob = cash_ledger.opening_balance
    ob_date = cash_ledger.opening_balance_date
    
    if ob_date and ob_date <= from_date:
        # Calculate net change from ob_date to from_date - 1
        
        # 1. Fee Receipts sum
        fr_sum = FeeReceipt.objects.filter(
            receipt_date__gte=ob_date,
            receipt_date__lt=from_date,
            is_cancelled=False,
            payment_mode=FeeReceipt.PaymentMode.CASH
        ).aggregate(total=Sum("received_amount"))["total"] or Decimal("0.00")
        
        from django.db.models import F
        sal_sum = SalaryPayment.objects.filter(
            payment_date__gte=ob_date,
            payment_date__lt=from_date,
            payment_mode=SalaryPayment.PaymentMode.CASH,
            is_cancelled=False
        ).aggregate(total=Sum(F('basic_pay') + F('da') + F('other_allowances') - F('pf_deduction') - F('esi_deduction') - F('other_deduction') - F('advance_recovery')))["total"] or Decimal("0.00")
        
        # 3. Voucher in/out
        v_in_sum = Voucher.objects.filter(
            voucher_date__gte=ob_date,
            voucher_date__lt=from_date,
            is_cancelled=False,
            debit_account=cash_ledger
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        
        v_out_sum = Voucher.objects.filter(
            voucher_date__gte=ob_date,
            voucher_date__lt=from_date,
            is_cancelled=False,
            credit_account=cash_ledger
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        
        ob = ob + fr_sum + v_in_sum - sal_sum - v_out_sum
        
    
    transactions = []
    
    for r in fee_receipts:
        transactions.append({
            "type": "FR",
            "ref": r,
            "ref_no": r.receipt_no,
            "date": r.receipt_date,
            "desc": f"Fee Receipt: {r.student.full_name}",
            "in_amt": r.received_amount,
            "out_amt": Decimal("0.00"),
            "sort_key": (r.receipt_date, r.created_at)
        })
        
    for v in vouchers:
        is_in = v.debit_account == cash_ledger
        party_name = v.staff.full_name if v.staff else v.paid_to_or_received_from
        head_name = v.credit_account.name if is_in else v.debit_account.name
        desc_bits = [part for part in [head_name, party_name, v.narration] if part]
        transactions.append({
            "type": "VOUCHER",
            "ref": v,
            "ref_no": v.voucher_no,
            "date": v.voucher_date,
            "desc": " - ".join(desc_bits),
            "in_amt": v.amount if is_in else Decimal("0.00"),
            "out_amt": Decimal("0.00") if is_in else v.amount,
            "sort_key": (v.voucher_date, v.created_at)
        })
        
    if include_salary:
        for s in salary_payments:
            desc_parts = [f"Salary: {s.staff.full_name}"]
            if s.remarks:
                desc_parts.append(f"({s.remarks})")
            
            transactions.append({
                "type": "SAL",
                "ref": s,
                "ref_no": f"SAL-{s.pk}",
                "date": s.payment_date,
                "desc": " ".join(desc_parts),
                "in_amt": Decimal("0.00"),
                "out_amt": s.net_pay,
                "sort_key": (s.payment_date, s.created_at)
            })
            
    transactions.sort(key=lambda x: x["sort_key"])
    
    tx_by_date = {}
    for tx in transactions:
        tx_by_date.setdefault(tx["date"], []).append(tx)
        
    dates_to_process = sorted(list(tx_by_date.keys()))
    if from_date not in dates_to_process:
        dates_to_process.insert(0, from_date)
    if to_date not in dates_to_process:
        dates_to_process.append(to_date)
        
    # Remove duplicates but keep sorted order
    dates_to_process = sorted(list(set(dates_to_process)))
    
    daily_data = []
    current_balance = ob
    
    from itertools import zip_longest
    
    for d in dates_to_process:
        day_tx = tx_by_date.get(d, [])
        receipts = []
        payments = []
        
        # Add OB
        if current_balance > 0:
            receipts.append({"ref_no": "-", "desc": "To Balance b/d", "amount": current_balance})
        elif current_balance < 0:
            payments.append({"ref_no": "-", "desc": "By Balance b/d", "amount": abs(current_balance)})
            
        for tx in day_tx:
            if tx["in_amt"] > 0:
                receipts.append({"ref_no": tx["ref_no"], "desc": tx["desc"], "amount": tx["in_amt"]})
            elif tx["out_amt"] > 0:
                payments.append({"ref_no": tx["ref_no"], "desc": tx["desc"], "amount": tx["out_amt"]})
                
        day_total_in = sum(r["amount"] for r in receipts)
        day_total_out = sum(p["amount"] for p in payments)
        
        cb = day_total_in - day_total_out
        
        if not day_tx and cb == 0:
            continue
            
        if cb > 0:
            payments.append({"ref_no": "-", "desc": "By Balance c/d", "amount": cb})
            day_total = day_total_in
        elif cb < 0:
            receipts.append({"ref_no": "-", "desc": "To Balance c/d", "amount": abs(cb)})
            day_total = day_total_out
        else:
            day_total = day_total_in
            
        current_balance = cb
        
        zipped_rows = list(zip_longest(receipts, payments, fillvalue=None))
        
        daily_data.append({
            "date": d,
            "rows": zipped_rows,
            "total": day_total
        })
    
    return render(request, "core/cash_book.html", {
        "from_date": from_date,
        "to_date": to_date,
        "daily_data": daily_data,
        "include_salary": include_salary
    })


def salary_payment_list(request):
    from_date = request.GET.get("from_date")
    to_date = request.GET.get("to_date")
    staff_id = request.GET.get("staff")
    payment_mode = request.GET.get("payment_mode")
    status = request.GET.get("status", "valid")

    qs = SalaryPayment.objects.select_related("staff").all()

    if from_date:
        qs = qs.filter(payment_date__gte=from_date)
    if to_date:
        qs = qs.filter(payment_date__lte=to_date)
    if staff_id:
        qs = qs.filter(staff_id=staff_id)
    if payment_mode:
        qs = qs.filter(payment_mode=payment_mode)

    if status == "valid":
        qs = qs.filter(is_cancelled=False)
    elif status == "cancelled":
        qs = qs.filter(is_cancelled=True)

    # Calculate totals
    if status == "cancelled":
        qs_for_totals = qs
    else:
        qs_for_totals = qs.filter(is_cancelled=False)

    total_gross = qs_for_totals.aggregate(t=Sum("basic_pay") + Sum("da") + Sum("other_allowances"))["t"] or Decimal("0.00")
    total_deductions = qs_for_totals.aggregate(t=Sum("pf_deduction") + Sum("esi_deduction") + Sum("other_deduction"))["t"] or Decimal("0.00")
    total_recovery = qs_for_totals.aggregate(t=Sum("advance_recovery"))["t"] or Decimal("0.00")

    total_net = total_gross - total_deductions - total_recovery

    paginator = Paginator(qs, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(request, "core/salary_list.html", {
        "page_obj": page_obj,
        "total_gross": total_gross,
        "total_deductions": total_deductions,
        "total_recovery": total_recovery,
        "total_net": total_net,
        "active_staff": Staff.objects.filter(is_active=True).order_by("full_name"),
    })


def salary_payment_detail(request, pk):
    payment = get_object_or_404(SalaryPayment.objects.select_related("staff", "cancelled_by", "edited_by"), pk=pk)
    logs = payment.audit_logs.select_related("changed_by").all()
    return render(request, "core/salary_detail.html", {
        "payment": payment,
        "audit_logs": logs
    })


def salary_payment_edit(request, pk):
    payment = get_object_or_404(SalaryPayment, pk=pk)
    if payment.is_cancelled:
        messages.error(request, "Cannot edit a cancelled salary payment.")
        return redirect("core:salary_payment_detail", pk=pk)

    if request.method == "POST":
        form = SalaryPaymentForm(request.POST, instance=payment)
        edit_reason = request.POST.get("edit_reason", "").strip()
        if not edit_reason:
            form.add_error(None, "An edit reason is required.")
            
        if form.is_valid():
            if SalaryPayment.objects.filter(staff=form.cleaned_data["staff"], pay_month=form.cleaned_data["pay_month"], is_cancelled=False).exclude(pk=pk).exists():
                form.add_error(None, "A valid salary payment for this staff for this month already exists.")
            else:
                updated_payment = form.save(commit=False)
                
                original_payment = SalaryPayment.objects.get(pk=pk)
                # Snapshot before
                before_snapshot = {
                    "basic_pay": str(original_payment.basic_pay),
                    "da": str(original_payment.da),
                    "other_allowances": str(original_payment.other_allowances),
                    "pf_deduction": str(original_payment.pf_deduction),
                    "esi_deduction": str(original_payment.esi_deduction),
                    "other_deduction": str(original_payment.other_deduction),
                    "advance_recovery": str(original_payment.advance_recovery),
                    "net_pay": str(original_payment.net_pay),
                }
                
                updated_payment.is_edited = True
                updated_payment.edited_at = timezone.now()
                updated_payment.edited_by = request.user if request.user.is_authenticated else None
                updated_payment.edit_reason = edit_reason
                updated_payment.edit_count += 1
                updated_payment.save()
                
                after_snapshot = {
                    "basic_pay": str(updated_payment.basic_pay),
                    "da": str(updated_payment.da),
                    "other_allowances": str(updated_payment.other_allowances),
                    "pf_deduction": str(updated_payment.pf_deduction),
                    "esi_deduction": str(updated_payment.esi_deduction),
                    "other_deduction": str(updated_payment.other_deduction),
                    "advance_recovery": str(updated_payment.advance_recovery),
                    "net_pay": str(updated_payment.net_pay),
                }
                
                SalaryPaymentAuditLog.objects.create(
                    payment=updated_payment,
                    action=SalaryPaymentAuditLog.ActionChoices.EDITED,
                    changed_by=request.user if request.user.is_authenticated else None,
                    reason=edit_reason,
                    before_snapshot=before_snapshot,
                    after_snapshot=after_snapshot
                )
                messages.success(request, "Salary payment updated successfully.")
                return redirect("core:salary_payment_detail", pk=updated_payment.pk)
    else:
        form = SalaryPaymentForm(instance=payment)

    active_staff = Staff.objects.filter(is_active=True)
    staff_defaults = {}
    pending_advances = {}
    
    for staff in active_staff:
        staff_defaults[staff.id] = {
            "basic_pay": str(staff.basic_pay),
            "da": str(staff.da),
            "other_allowances": str(staff.other_allowances),
        }
        adv_given = Voucher.objects.filter(staff=staff, debit_account__group__name__iexact="Advance Given", is_cancelled=False).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        adv_recovered = SalaryPayment.objects.filter(staff=staff, is_cancelled=False).exclude(pk=pk).aggregate(total=Sum("advance_recovery"))["total"] or Decimal("0.00")
        pending_advances[staff.id] = float(adv_given - adv_recovered)

    return render(
        request,
        "core/salary_edit.html",
        {
            "form": form,
            "payment": payment,
            "staff_defaults": staff_defaults,
            "pending_advances": pending_advances,
        },
    )


def salary_payment_cancel(request, pk):
    payment = get_object_or_404(SalaryPayment, pk=pk)
    if payment.is_cancelled:
        messages.error(request, "This salary payment is already cancelled.")
        return redirect("core:salary_payment_detail", pk=pk)

    if request.method == "POST":
        reason = request.POST.get("cancel_reason", "").strip()
        if not reason:
            messages.error(request, "A cancellation reason is required.")
        else:
            payment.is_cancelled = True
            payment.cancelled_at = timezone.now()
            payment.cancelled_by = request.user if request.user.is_authenticated else None
            payment.cancel_reason = reason
            payment.save(update_fields=["is_cancelled", "cancelled_at", "cancelled_by", "cancel_reason"])

            SalaryPaymentAuditLog.objects.create(
                payment=payment,
                action=SalaryPaymentAuditLog.ActionChoices.CANCELLED,
                changed_by=request.user if request.user.is_authenticated else None,
                reason=reason
            )
            messages.success(request, "Salary payment cancelled successfully.")
            return redirect("core:salary_payment_detail", pk=pk)

    return render(request, "core/salary_cancel_confirm.html", {"payment": payment})
