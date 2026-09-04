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
    FeeReceiptLine,
    FeeStructure,
    Student,
    StudentFeeWaiver,
    StudentOpeningBalance,
    StudentTransport,
)


ZERO = Decimal("0.00")
PENNY = Decimal("0.01")
DEFAULT_PACKAGE_TOTAL = Decimal("4500.00")
PACKAGE_FEE_HEAD_NAME = "Package Fee"
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
    policy_concession_amount: Decimal
    waiver_amount: Decimal
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


def _is_new_student_for_session(student: Student, session: AcademicSession):
    if not student.admission_date:
        return False
    return session.starts_on <= student.admission_date <= session.ends_on


def _fixed_month_installments(total, months):
    ordered_months = sorted(months, key=ACADEMIC_MONTHS.index)
    if not ordered_months:
        return {}

    total_cents = int(_money(total) * 100)
    base_cents, remainder_cents = divmod(total_cents, len(ordered_months))
    amounts = {month: Decimal(base_cents) / 100 for month in ordered_months}
    amounts[ordered_months[-1]] += Decimal(remainder_cents) / 100
    return {month: _money(amount) for month, amount in amounts.items()}


def _normalised_class_name(school_class):
    return "".join(ch for ch in (getattr(school_class, "name", "") or "").lower() if ch.isalnum())


def _is_ix_x_lab_fee(structure):
    head_name = (structure.fee_head.name or "").strip().lower()
    class_name = _normalised_class_name(structure.school_class)
    return head_name == "lab fee" and class_name in {"ix", "x", "9", "9th", "10", "10th"}


def student_is_zero_fee(student: Student):
    return bool(getattr(student, "is_zero_fee_section", False))


def student_uses_fee_package(student: Student):
    return bool(getattr(student, "uses_fee_package", False))


def student_fee_package_amount(student: Student):
    if not student_uses_fee_package(student):
        return ZERO
    amount = getattr(student, "fee_package_total", ZERO) or ZERO
    return _money(amount if amount > ZERO else DEFAULT_PACKAGE_TOTAL)


def _fee_structure_queryset_for_student(*, student: Student, session: AcademicSession):
    structures = FeeStructure.objects.select_related("fee_head").filter(
        session=session,
        school_class=student.current_class,
        is_active=True,
        fee_head__is_active=True,
        fee_head__is_transport=False,
    )
    if student_is_zero_fee(student) or student_uses_fee_package(student):
        return structures.none()
    return structures


def student_is_second_year_package(student: Student) -> bool:
    if not student_uses_fee_package(student):
        return False
    class_name = str(student.current_class.name if student.current_class else "").strip().upper()
    return class_name in {"X", "10", "10TH"} or class_name.startswith("XII") or class_name.startswith("12")


def _package_demand(student: Student):
    if student_is_zero_fee(student):
        return ZERO
    if student_is_second_year_package(student):
        # In Year 2 of 2-year package (Class X & XII), 2-year package fee (Rs. 4,500)
        # was already billed in Year 1 (Class IX & XI). The remaining unpaid balance
        # is carried forward via StudentOpeningBalance. Year 2 new demand is Rs. 0.
        return ZERO
    return student_fee_package_amount(student)


def package_receipt_default_amount(*, student: Student, session: AcademicSession):
    if student_is_second_year_package(student):
        due_res = calculate_student_due(student=student, session=session, through_month="MAR")
        return max(due_res.raw_balance, ZERO)

    package_total = student_fee_package_amount(student)
    if package_total <= ZERO:
        return ZERO

    package_head = FeeHead.objects.filter(name=PACKAGE_FEE_HEAD_NAME, is_active=True).first()
    if not package_head:
        return package_total

    paid = _money(
        FeeReceiptLine.objects.filter(
            receipt__student=student,
            receipt__session=session,
            receipt__is_cancelled=False,
            fee_head=package_head,
        ).aggregate(total=Sum("amount"))["total"]
    )
    return max(_money(package_total - paid), ZERO)


def _effective_charge_rule_and_months(structure, *, is_new_student):
    if _is_ix_x_lab_fee(structure):
        return FeeHead.ChargeRule.FIXED_MONTHS, ["DEC"]

    head = structure.fee_head
    cohort = "new" if is_new_student else "old"
    return (
        getattr(head, f"{cohort}_student_charge_rule"),
        getattr(head, f"{cohort}_student_charge_months") or [],
    )


def _scheduled_structure_demand(structure, *, is_new_student, student, session, cutoff, target_index):
    head = structure.fee_head
    if head.applies_to == FeeHead.AppliesTo.NEW and not is_new_student:
        return ZERO
    if head.applies_to == FeeHead.AppliesTo.OLD and is_new_student:
        return ZERO

    rule, months = _effective_charge_rule_and_months(structure, is_new_student=is_new_student)
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


def calculate_structure_receipt_amount(*, structure, student: Student, session: AcademicSession, from_month: str, to_month: str):
    from_month = str(from_month or "").strip().upper()
    to_month = str(to_month or "").strip().upper()
    if from_month not in ACADEMIC_MONTHS:
        raise ValidationError(f"Invalid academic month: {from_month or '(blank)' }.")
    if to_month not in ACADEMIC_MONTHS:
        raise ValidationError(f"Invalid academic month: {to_month or '(blank)' }.")
    if not session.starts_on or not session.ends_on:
        raise ValidationError("Academic session must have starts_on and ends_on dates.")

    start_index = ACADEMIC_MONTHS.index(from_month)
    end_index = ACADEMIC_MONTHS.index(to_month)
    if start_index > end_index:
        start_index, end_index = end_index, start_index

    is_new_student = _is_new_student_for_session(student, session)
    end_cutoff = _academic_month_cutoff(session, ACADEMIC_MONTHS[end_index])
    end_amount = _scheduled_structure_demand(
        structure,
        is_new_student=is_new_student,
        student=student,
        session=session,
        cutoff=end_cutoff,
        target_index=end_index,
    )
    if start_index == 0:
        return _money(end_amount)

    previous_month = ACADEMIC_MONTHS[start_index - 1]
    previous_cutoff = _academic_month_cutoff(session, previous_month)
    previous_amount = _scheduled_structure_demand(
        structure,
        is_new_student=is_new_student,
        student=student,
        session=session,
        cutoff=previous_cutoff,
        target_index=start_index - 1,
    )
    return _money(end_amount - previous_amount)


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


def _normalise_receipt_month(value):
    value = str(value or "").strip().upper()
    if not value:
        return ""
    value = value[:3]
    return value if value in ACADEMIC_MONTHS else ""


def _receipt_counts_towards_month(receipt, *, target_index, cutoff):
    from_month = _normalise_receipt_month(receipt.from_month)
    to_month = _normalise_receipt_month(receipt.to_month)

    if from_month:
        return ACADEMIC_MONTHS.index(from_month) <= target_index
    if to_month:
        return ACADEMIC_MONTHS.index(to_month) <= target_index
    return receipt.receipt_date <= cutoff


def _receipt_totals_for_due(*, student, session, target_index, cutoff):
    receipts = FeeReceipt.objects.filter(
        student=student,
        session=session,
        is_cancelled=False,
    ).only(
        "from_month",
        "to_month",
        "receipt_date",
        "received_amount",
        "concession_amount",
        "late_fee_amount",
    )

    totals = {"received": ZERO, "concession": ZERO, "late_fee": ZERO}
    for receipt in receipts:
        if not _receipt_counts_towards_month(receipt, target_index=target_index, cutoff=cutoff):
            continue
        totals["received"] += receipt.received_amount
        totals["concession"] += receipt.concession_amount
        totals["late_fee"] += receipt.late_fee_amount
    return {key: _money(value) for key, value in totals.items()}


def calculate_student_due(*, student: Student, session: AcademicSession, through_month: str) -> DueResult:
    through_month = str(through_month or "").strip().upper()
    if through_month not in ACADEMIC_MONTHS:
        raise ValidationError(f"Invalid academic month: {through_month or '(blank)' }.")
    if not student.current_class_id:
        raise ValidationError("Student must have a current class for due calculation.")
    if not session.starts_on or not session.ends_on:
        raise ValidationError("Academic session must have starts_on and ends_on dates.")

    cutoff = _academic_month_cutoff(session, through_month)
    target_index = ACADEMIC_MONTHS.index(through_month)
    is_new_student = _is_new_student_for_session(student, session)

    structures = _fee_structure_queryset_for_student(student=student, session=session)
    if student_is_zero_fee(student):
        scheduled_fee_demand = ZERO
    elif student_uses_fee_package(student):
        scheduled_fee_demand = _package_demand(student)
    else:
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
    receipt_totals = _receipt_totals_for_due(
        student=student,
        session=session,
        target_index=target_index,
        cutoff=cutoff,
    )
    received_amount = _money(receipt_totals["received"])
    concession_amount = _money(receipt_totals["concession"])
    late_fee_amount = _money(receipt_totals["late_fee"])
    # ------------------------------------------------------------------
    # Policy concession (StudentConcession record)
    # ------------------------------------------------------------------
    policy_concession_amount = ZERO

    # Prefer prefetched queryset to avoid extra DB hit.
    _cache = getattr(student, '_prefetched_objects_cache', {})
    if 'concessions' in _cache:
        concession = next(
            (c for c in _cache['concessions'] if c.session_id == session.id and c.is_active),
            None,
        )
    else:
        concession = student.concessions.filter(session=session, is_active=True).first()

    if concession and concession.is_active:
        ctype = concession.concession_type

        if ctype in ('monthly_waiver', 'sibling_discount'):
            # Sum only MONTHLY fee heads.
            monthly_fee_amount = _money(
                sum(
                    (
                        s.amount
                        for s in structures
                        if _effective_charge_rule_and_months(
                            s,
                            is_new_student=is_new_student,
                        )[0] == FeeHead.ChargeRule.MONTHLY
                    ),
                    ZERO,
                )
            )
            # Waiver applies only to months within [from_month, to_month].
            applicable_months = concession.months_in_range(target_index)
            per_month_discount = concession.get_monthly_discount_amount(monthly_fee_amount)
            policy_concession_amount = _money(per_month_discount * applicable_months)

        elif ctype == 'full_free':
            # Waives the entire scheduled academic + transport demand for the session.
            policy_concession_amount = _money(scheduled_fee_demand + transport_demand)

        elif ctype == 'one_time':
            # Fixed one-time reduction — same regardless of through_month.
            # Percent amount_type is blocked by model.clean(), so only fixed/full reach here.
            if concession.months_in_range(target_index) > 0:
                if concession.amount_type == 'full':
                    policy_concession_amount = _money(scheduled_fee_demand + transport_demand)
                else:
                    policy_concession_amount = _money(concession.amount or ZERO)


    waiver_amount = _money(
        StudentFeeWaiver.objects.filter(student=student, session=session).aggregate(total=Sum("amount"))[
            "total"
        ]
    )

    gross_demand = _money(
        scheduled_fee_demand + transport_demand + opening_balance_amount + late_fee_amount
    )
    raw_balance = _money(
        gross_demand - received_amount - concession_amount - policy_concession_amount - waiver_amount
    )
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
        policy_concession_amount=policy_concession_amount,
        waiver_amount=waiver_amount,
        raw_balance=raw_balance,
        due_amount=_money(due_amount),
        credit_amount=_money(credit_amount),
    )
