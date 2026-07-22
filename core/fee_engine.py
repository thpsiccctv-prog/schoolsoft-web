import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum

from .models import (
    ACADEMIC_MONTHS,
    AcademicSession,
    FeeHead,
    FeeReceipt,
    FeeStructure,
    Student,
    StudentOpeningBalance,
    StudentTransport,
)


ZERO = Decimal("0.00")
PENNY = Decimal("0.01")
MONTH_NUMBER = {
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
}


@dataclass(frozen=True)
class DueResult:
    through_month: str
    cutoff_date: date
    is_new_student: bool
    scheduled_fee_demand: Decimal
    transport_demand: Decimal
    opening_balance_amount: Decimal
    late_fee_amount: Decimal
    gross_demand: Decimal
    received_amount: Decimal
    concession_amount: Decimal
    raw_balance: Decimal
    due_amount: Decimal
    credit_amount: Decimal


def _money(value):
    return Decimal(value or ZERO).quantize(PENNY)


def _academic_month_cutoff(session, through_month):
    if not session.starts_on or not session.ends_on:
        raise ValidationError("Academic session must have starts_on and ends_on dates.")

    month_number = MONTH_NUMBER[through_month]
    candidates = []
    for year in range(session.starts_on.year, session.ends_on.year + 1):
        first = date(year, month_number, 1)
        last = date(year, month_number, calendar.monthrange(year, month_number)[1])
        if last >= session.starts_on and first <= session.ends_on:
            candidates.append(min(last, session.ends_on))

    if len(candidates) != 1:
        raise ValidationError(
            f"Month {through_month} does not resolve exactly once inside session {session.name}."
        )
    return candidates[0]


def _fixed_month_installments(total, months):
    ordered_months = sorted(months, key=ACADEMIC_MONTHS.index)
    if not ordered_months:
        return {}

    total_cents = int(_money(total) * 100)
    base_cents, remainder_cents = divmod(total_cents, len(ordered_months))
    amounts = {month: Decimal(base_cents) / 100 for month in ordered_months}
    amounts[ordered_months[-1]] += Decimal(remainder_cents) / 100
    return {month: _money(amount) for month, amount in amounts.items()}


def _scheduled_structure_demand(structure, *, is_new_student, student, session, cutoff, target_index):
    head = structure.fee_head
    if head.applies_to == FeeHead.AppliesTo.NEW and not is_new_student:
        return ZERO
    if head.applies_to == FeeHead.AppliesTo.OLD and is_new_student:
        return ZERO

    cohort = "new" if is_new_student else "old"
    rule = getattr(head, f"{cohort}_student_charge_rule")
    months = getattr(head, f"{cohort}_student_charge_months") or []
    amount = _money(structure.amount)

    if rule == FeeHead.ChargeRule.NOT_APPLICABLE:
        return ZERO
    if rule == FeeHead.ChargeRule.MONTHLY:
        return _money(amount * (target_index + 1))
    if rule == FeeHead.ChargeRule.ADMISSION_MONTH:
        admission_date = student.admission_date
        if admission_date and session.starts_on <= admission_date <= cutoff:
            return amount
        return ZERO
    if rule == FeeHead.ChargeRule.FIXED_MONTHS:
        invalid = [month for month in months if month not in ACADEMIC_MONTHS]
        if invalid or not months:
            raise ValidationError(f"Fee head {head.name} has an invalid fixed-month schedule.")
        installments = _fixed_month_installments(amount, months)
        return _money(
            sum(
                (
                    installment
                    for month, installment in installments.items()
                    if ACADEMIC_MONTHS.index(month) <= target_index
                ),
                ZERO,
            )
        )
    raise ValidationError(f"Fee head {head.name} has unsupported charge rule {rule}.")


def _transport_demand(student, session, target_index):
    assignments = StudentTransport.objects.filter(
        student=student,
        session=session,
        billing_confirmed=True,
        is_active=True,
    ).order_by("id")

    assigned_months = {}
    total = ZERO
    for assignment in assignments:
        if assignment.monthly_amount is None or assignment.start_month not in ACADEMIC_MONTHS:
            raise ValidationError(f"Confirmed transport row {assignment.pk} is incomplete.")
        start_index = ACADEMIC_MONTHS.index(assignment.start_month)
        end_index = (
            ACADEMIC_MONTHS.index(assignment.end_month)
            if assignment.end_month in ACADEMIC_MONTHS
            else len(ACADEMIC_MONTHS) - 1
        )
        if end_index < start_index:
            raise ValidationError(f"Confirmed transport row {assignment.pk} has an invalid month window.")

        for month_index in range(start_index, min(end_index, target_index) + 1):
            month = ACADEMIC_MONTHS[month_index]
            if month in assigned_months:
                raise ValidationError(
                    f"Confirmed transport rows {assigned_months[month]} and {assignment.pk} overlap in {month}."
                )
            assigned_months[month] = assignment.pk
            total += assignment.monthly_amount
    return _money(total)


def calculate_student_due(*, student: Student, session: AcademicSession, through_month: str) -> DueResult:
    through_month = str(through_month or "").strip().upper()
    if through_month not in ACADEMIC_MONTHS:
        raise ValidationError(f"Invalid academic month: {through_month or '(blank)' }.")
    if not student.current_class_id:
        raise ValidationError("Student must have a current class for due calculation.")
    if not student.admission_date:
        raise ValidationError("Student admission date is required to derive New/Old status.")
    if not session.starts_on or not session.ends_on:
        raise ValidationError("Academic session must have starts_on and ends_on dates.")

    cutoff = _academic_month_cutoff(session, through_month)
    target_index = ACADEMIC_MONTHS.index(through_month)
    is_new_student = session.starts_on <= student.admission_date <= session.ends_on

    structures = FeeStructure.objects.select_related("fee_head").filter(
        session=session,
        school_class=student.current_class,
        is_active=True,
        fee_head__is_active=True,
        fee_head__is_transport=False,
    )
    scheduled_fee_demand = _money(
        sum(
            (
                _scheduled_structure_demand(
                    structure,
                    is_new_student=is_new_student,
                    student=student,
                    session=session,
                    cutoff=cutoff,
                    target_index=target_index,
                )
                for structure in structures
            ),
            ZERO,
        )
    )
    transport_demand = _transport_demand(student, session, target_index)

    opening_balance_amount = _money(
        StudentOpeningBalance.objects.filter(student=student, session=session).aggregate(total=Sum("amount"))[
            "total"
        ]
    )
    receipt_totals = FeeReceipt.objects.filter(
        student=student,
        session=session,
        is_cancelled=False,
        receipt_date__lte=cutoff,
    ).aggregate(
        received=Sum("received_amount"),
        concession=Sum("concession_amount"),
        late_fee=Sum("late_fee_amount"),
    )
    received_amount = _money(receipt_totals["received"])
    concession_amount = _money(receipt_totals["concession"])
    late_fee_amount = _money(receipt_totals["late_fee"])

    gross_demand = _money(
        scheduled_fee_demand + transport_demand + opening_balance_amount + late_fee_amount
    )
    raw_balance = _money(gross_demand - received_amount - concession_amount)
    due_amount = max(raw_balance, ZERO)
    credit_amount = max(-raw_balance, ZERO)

    return DueResult(
        through_month=through_month,
        cutoff_date=cutoff,
        is_new_student=is_new_student,
        scheduled_fee_demand=scheduled_fee_demand,
        transport_demand=transport_demand,
        opening_balance_amount=opening_balance_amount,
        late_fee_amount=late_fee_amount,
        gross_demand=gross_demand,
        received_amount=received_amount,
        concession_amount=concession_amount,
        raw_balance=raw_balance,
        due_amount=_money(due_amount),
        credit_amount=_money(credit_amount),
    )
