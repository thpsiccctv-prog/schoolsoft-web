"""Read-only due reconciliation report for legacy receipt due vs new fee engine."""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ZERO = Decimal("0.00")
PENNY = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(value or ZERO).quantize(PENNY)


def fmt(value) -> str:
    return f"Rs. {money(value):,.2f}"


def setup_django(database: Path):
    os.environ["SCHOOLSOFT_SQLITE_PATH"] = str(database)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
    import django

    django.setup()


def normal_month(value: str | None) -> str:
    value = (value or "MAR").strip().upper()
    aliases = {"APRIL": "APR", "JUNE": "JUN", "JULY": "JUL", "SEPT": "SEP", "SEPTEMBER": "SEP", "MARCH": "MAR"}
    return aliases.get(value, value[:3])


def is_new_student(student, session) -> bool:
    return bool(student.admission_date and session.starts_on <= student.admission_date <= session.ends_on)


def receipt_lines_total(receipt, names: set[str]) -> Decimal:
    return money(sum((line.amount for line in receipt.lines.select_related("fee_head") if line.fee_head.name in names), ZERO))


def has_active_structure(session, school_class, fee_head) -> bool:
    from core.models import FeeStructure

    return FeeStructure.objects.filter(
        session=session,
        school_class=school_class,
        fee_head=fee_head,
        is_active=True,
        fee_head__is_active=True,
    ).exists()


def stale_head_total(receipt, session, school_class) -> tuple[Decimal, list[str]]:
    ignored = {"Admission Fee"}
    total = ZERO
    names = []
    for line in receipt.lines.select_related("fee_head"):
        head = line.fee_head
        if head.name in ignored:
            continue
        if not has_active_structure(session, school_class, head):
            total += line.amount
            names.append(head.name)
    return money(total), sorted(set(names))


def receipts_upto(receipt, session):
    from django.db.models import Q
    from core.models import FeeReceipt

    return FeeReceipt.objects.filter(
        student=receipt.student,
        session=session,
        is_cancelled=False,
    ).filter(Q(receipt_date__lt=receipt.receipt_date) | Q(receipt_date=receipt.receipt_date, id__lte=receipt.id))


def engine_due_as_of_receipt(receipt, session, target_month):
    from django.db.models import Sum
    from core.fee_engine import calculate_student_due

    result = calculate_student_due(student=receipt.student, session=session, through_month=target_month)
    totals = receipts_upto(receipt, session).aggregate(
        received=Sum("received_amount"),
        concession=Sum("concession_amount"),
        late_fee=Sum("late_fee_amount"),
    )
    paid = money(totals["received"])
    concession = money(totals["concession"])
    late_fee = money(totals["late_fee"])
    gross = money(result.scheduled_fee_demand + result.transport_demand + result.opening_balance_amount + late_fee)
    raw = money(gross - paid - concession)
    return {
        "gross": gross,
        "paid": paid,
        "concession": concession,
        "due": max(raw, ZERO),
        "credit": max(-raw, ZERO),
    }


def table(headers, lines):
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    out.extend(lines)
    return "\n".join(out)


def generate_report(database: Path, output: Path, session_name: str):
    setup_django(database)

    from core.fee_engine import ACADEMIC_MONTHS, calculate_student_due
    from core.models import AcademicSession, FeeReceipt, Student, FeeHead
    from django.db.migrations.recorder import MigrationRecorder

    session = AcademicSession.objects.get(name=session_name)
    active_students = Student.objects.filter(is_active=True).select_related("current_class", "current_section")

    historical = []
    latest_rows = []
    no_receipt_due = []

    receipt_qs = (
        FeeReceipt.objects.filter(session=session, is_cancelled=False, student__is_active=True)
        .select_related("student", "student__current_class", "student__current_section")
        .prefetch_related("lines", "lines__fee_head")
        .order_by("student__admission_no", "receipt_date", "id")
    )
    for receipt in receipt_qs:
        student = receipt.student
        if not student.current_class_id:
            continue
        target_month = normal_month(receipt.to_month or receipt.from_month)
        if target_month not in ACADEMIC_MONTHS:
            target_month = "MAR"
        asof = engine_due_as_of_receipt(receipt, session, target_month)
        receipt_due = money(receipt.legacy_due_amount)
        engine_due = money(asof["due"])
        if receipt_due == engine_due:
            continue

        admission = ZERO
        if not is_new_student(student, session):
            admission = receipt_lines_total(receipt, {"Admission Fee"})
        stale, stale_names = stale_head_total(receipt, session, student.current_class)
        receipt_over_engine = money(receipt_due - engine_due)
        residual = money(receipt_over_engine - admission - stale)
        notes = []
        if admission:
            notes.append("old-student admission fee")
        if stale:
            notes.append("stale heads: " + ", ".join(stale_names))
        if residual:
            notes.append("rate/residual")
        if not notes:
            notes.append("unexplained")
        historical.append(
            "| {sid} | {name} | {klass}-{section} | {receipt_no} | {month} | {receipt_due} | {engine_due} | {variance} | {admission} | {stale} | {residual} | {notes} |".format(
                sid=student.admission_no,
                name=(student.full_name or "").replace("|", "/"),
                klass=student.current_class,
                section=student.current_section or "",
                receipt_no=receipt.receipt_no,
                month=target_month,
                receipt_due=fmt(receipt_due),
                engine_due=fmt(engine_due),
                variance=fmt(engine_due - receipt_due),
                admission=fmt(admission),
                stale=fmt(stale),
                residual=fmt(residual),
                notes="; ".join(notes).replace("|", "/"),
            )
        )

    for student in active_students.order_by("current_class__display_order", "current_section__name", "full_name"):
        if not student.current_class_id:
            continue
        latest = FeeReceipt.objects.filter(student=student, session=session, is_cancelled=False).order_by("-receipt_date", "-id").first()
        if latest:
            target_month = normal_month(latest.to_month or latest.from_month)
            if target_month not in ACADEMIC_MONTHS:
                target_month = "MAR"
            result = calculate_student_due(student=student, session=session, through_month=target_month)
            if money(latest.legacy_due_amount) != money(result.due_amount):
                latest_rows.append(
                    f"| {student.admission_no} | {(student.full_name or '').replace('|','/')} | {student.current_class}-{student.current_section or ''} | {latest.receipt_no} | {target_month} | {fmt(latest.legacy_due_amount)} | {fmt(result.due_amount)} | {fmt(result.due_amount - latest.legacy_due_amount)} |"
                )
        else:
            result = calculate_student_due(student=student, session=session, through_month="MAR")
            if result.due_amount > ZERO:
                no_receipt_due.append(
                    f"| {student.admission_no} | {(student.full_name or '').replace('|','/')} | {student.current_class}-{student.current_section or ''} | MAR | {fmt(result.gross_demand)} | {fmt(result.received_amount)} | {fmt(result.concession_amount)} | {fmt(result.due_amount)} |"
                )

    report = []
    report.append("# Due Reconciliation Report")
    report.append("")
    report.append(f"Generated: {datetime.now().strftime('%d/%m/%Y %I:%M %p')}")
    report.append(f"Database copy: `{database}`")
    report.append(f"Session: `{session.name}`")
    report.append("")
    report.append("## Live-State Snapshot From Copy")
    report.append("")
    report.append(f"- Total students: **{Student.objects.count()}**")
    report.append(f"- Active students: **{active_students.count()}**")
    report.append(f"- Fee receipts: **{FeeReceipt.objects.count()}**")
    report.append(f"- Migration 0031: **{MigrationRecorder.Migration.objects.filter(app='core', name='0031_create_balance_fee_head').exists()}**")
    report.append(f"- Balance Fee head: **{FeeHead.objects.filter(name='Balance Fee', is_active=True).exists()}**")
    report.append("")
    report.append("## Historical Receipt Due vs New Engine Due (As-Of Receipt)")
    report.append("")
    report.append("This section compares each receipt's saved due with the new engine due as of that same receipt, ignoring later payments.")
    report.append("")
    if historical:
        report.append(table(["SID", "Student", "Class", "Receipt", "Month", "Receipt Due", "Engine Due", "Variance", "Admission", "Stale Heads", "Rate/Residual", "Notes"], historical))
    else:
        report.append("No historical discrepancies found.")
    report.append("")
    report.append("## Latest Receipt Snapshot")
    report.append("")
    report.append("This section shows students whose latest receipt due still differs from the current new-engine due.")
    report.append("")
    if latest_rows:
        report.append(table(["SID", "Student", "Class", "Latest Receipt", "Month", "Latest Receipt Due", "Current Engine Due", "Variance"], latest_rows))
    else:
        report.append("No latest-receipt discrepancies found.")
    report.append("")
    report.append("## Students With Engine Due But No Session Receipt")
    report.append("")
    if no_receipt_due:
        report.append(table(["SID", "Student", "Class", "Month", "Demand", "Paid", "Concession", "Engine Due"], no_receipt_due))
    else:
        report.append("No active no-receipt defaulters found.")
    report.append("")
    report.append("## Summary")
    report.append("")
    report.append(f"- Historical discrepancy rows: **{len(historical)}**")
    report.append(f"- Latest discrepancy rows: **{len(latest_rows)}**")
    report.append(f"- No-receipt due rows: **{len(no_receipt_due)}**")
    report.append("")
    report.append("## Safety Note")
    report.append("")
    report.append("This report is read-only. It does not rename, edit, cancel, or reclassify any receipt or fee head.")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--session", default="2026-27")
    args = parser.parse_args()
    generate_report(args.database, args.output, args.session)


if __name__ == "__main__":
    main()
