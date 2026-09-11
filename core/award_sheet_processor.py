"""
core/award_sheet_processor.py
Processing and ingestion engine for scanned/photographed Teacher Award Sheets.
Performs:
1. Sheet-ID identification & page roster matching
2. Digit parsing with strict double-entry arithmetic cross-validation (Theory + Practical = Total)
3. Absent [AB] flag reconciliation
4. Dry-run audit preview CSV generation
5. Safe, idempotent atomic database commit to ExamMark
"""

import csv
from decimal import Decimal, InvalidOperation
import json
import math
import os
from pathlib import Path
import re

from django.db import transaction
from django.utils import timezone
from core.models import ExamMark, ExamTest, SchoolClass, Section, Student, grade_for_percentage
from core.award_sheet import STUDENTS_PER_PAGE


SHEET_TOKEN_PATTERN = re.compile(
    r"QEX2627-C(?P<class_id>\d+)-S(?P<sec_code>[^-]+)-T(?P<test_id>\d+)-P(?P<page_no>\d+)OF(?P<total_pages>\d+)",
    re.IGNORECASE
)


def parse_sheet_token(token_str):
    """
    Parses a machine-readable sheet token string, e.g.
    'QEX2627-C4-SA-T24-P1OF5' -> dict with class_id, sec_code, test_id, page_no, total_pages.
    """
    m = SHEET_TOKEN_PATTERN.search(token_str)
    if not m:
        return None
    data = m.groupdict()
    return {
        "class_id": int(data["class_id"]),
        "sec_code": data["sec_code"].upper(),
        "test_id": int(data["test_id"]),
        "page_no": int(data["page_no"]),
        "total_pages": int(data["total_pages"]),
    }


def get_expected_page_roster(exam_test, section=None, page_no=1):
    """
    Returns the exact list of students expected on this page index of the award sheet.
    """
    school_class = exam_test.school_class
    qs = Student.objects.filter(is_active=True, current_class=school_class)
    if section:
        qs = qs.filter(current_section=section)
    all_students = list(qs.order_by("roll_no", "legacy_sid", "full_name"))

    total_students = len(all_students)
    start_i = (page_no - 1) * STUDENTS_PER_PAGE
    end_i = min(start_i + STUDENTS_PER_PAGE, total_students)

    page_students = all_students[start_i:end_i]
    roster = []
    for idx, s in enumerate(page_students):
        roster.append({
            "s_no": start_i + idx + 1,
            "student_id": s.id,
            "student": s,
            "roll_no": s.roll_no,
            "admission_no": s.admission_no or "",
            "legacy_sid": s.legacy_sid,
            "full_name": s.full_name,
            "father_name": s.father_name,
        })
    return roster, total_students


def check_subject_pass(exam_test, th_obt, pr_obt, tot_obt, is_absent=False):
    """
    Determines if a student has passed a subject according to UP Board rules:
    - For subjects with Practical (e.g. 70/30): Theory and Practical must be passed separately.
      Theory >= 23/70, Practical >= 10/30.
    - For pure Theory subjects (e.g. 100/0): Theory >= 33/100.
    - Total marks must meet or exceed pass_marks (typically 33%).
    - Absent in subject is a direct fail.
    Returns: (is_pass: bool, fail_reasons: list[str])
    """
    if is_absent:
        return False, ["ABSENT"]
    if tot_obt is None:
        return False, ["NO_MARKS"]

    th_max = exam_test.theory_max_marks or Decimal("100.00")
    pr_max = exam_test.practical_max_marks or Decimal("0.00")
    tot_pass = exam_test.pass_marks or Decimal("33.00")

    # Component pass thresholds
    if th_max == Decimal("70.00"):
        th_pass = Decimal("23.00")
    elif th_max > Decimal("0.00"):
        th_pass = Decimal(str(math.ceil(float(th_max) * 0.33)))
    else:
        th_pass = Decimal("0.00")

    if pr_max == Decimal("30.00"):
        pr_pass = Decimal("10.00")
    elif pr_max > Decimal("0.00"):
        pr_pass = Decimal(str(math.ceil(float(pr_max) * 0.33)))
    else:
        pr_pass = Decimal("0.00")

    reasons = []
    if th_max > Decimal("0.00") and (th_obt is None or th_obt < th_pass):
        reasons.append(f"Theory {th_obt or 0} < min {th_pass}")

    if pr_max > Decimal("0.00") and (pr_obt is None or pr_obt < pr_pass):
        reasons.append(f"Practical {pr_obt or 0} < min {pr_pass}")

    if tot_obt < tot_pass:
        reasons.append(f"Total {tot_obt} < min {tot_pass}")

    is_pass = (len(reasons) == 0)
    return is_pass, reasons


def validate_and_reconcile_row(student, exam_test, raw_th, raw_pr, raw_tot, is_absent=False, remarks=""):
    """
    Validates extracted marks for a single student row against exam_test rules.
    Performs the golden arithmetic self-check: Theory + Practical == Total.
    """
    theory_max = exam_test.theory_max_marks or Decimal("100.00")
    practical_max = exam_test.practical_max_marks or Decimal("0.00")
    total_max = exam_test.max_marks or (theory_max + practical_max)
    has_practical = practical_max > Decimal("0.00")

    result = {
        "student_id": student.id,
        "roll_no": student.roll_no,
        "legacy_sid": student.legacy_sid,
        "admission_no": student.admission_no,
        "student_name": student.full_name,
        "father_name": student.father_name,
        "raw_theory": raw_th,
        "raw_practical": raw_pr,
        "raw_total": raw_tot,
        "is_absent": bool(is_absent),
        "theory_marks": None,
        "practical_marks": None,
        "total_marks": None,
        "percentage": None,
        "grade": "",
        "status": "VALID",
        "flags": [],
        "remarks": remarks,
        "is_pass": False,
        "fail_reasons": [],
    }

    # 1. Check Absent
    if is_absent:
        result["is_absent"] = True
        result["grade"] = "AB"
        result["status"] = "ABSENT"
        result["is_pass"] = False
        result["fail_reasons"] = ["ABSENT"]
        return result

    # 2. Check Blank / Unentered
    th_str = str(raw_th or "").strip()
    pr_str = str(raw_pr or "").strip()
    tot_str = str(raw_tot or "").strip()

    if not th_str and not pr_str and not tot_str:
        result["status"] = "BLANK_ROW"
        result["flags"].append("No marks entered")
        result["is_pass"] = False
        return result

    # 3. Parse Numerical Values
    try:
        th_val = Decimal(th_str) if th_str else Decimal("0.00")
    except InvalidOperation:
        result["status"] = "INVALID_DIGIT"
        result["flags"].append(f"Invalid theory digits: '{th_str}'")
        return result

    try:
        pr_val = Decimal(pr_str) if pr_str else Decimal("0.00")
    except InvalidOperation:
        result["status"] = "INVALID_DIGIT"
        result["flags"].append(f"Invalid practical digits: '{pr_str}'")
        return result

    try:
        tot_val = Decimal(tot_str) if tot_str else None
    except InvalidOperation:
        result["status"] = "INVALID_DIGIT"
        result["flags"].append(f"Invalid total digits: '{tot_str}'")
        return result

    # 4. Check Maximum Bounds
    if th_val < Decimal("0.00") or th_val > theory_max:
        result["status"] = "EXCEEDS_MAX"
        result["flags"].append(f"Theory {th_val} exceeds max {theory_max}")

    if practical_max > Decimal("0.00"):
        if pr_val < Decimal("0.00") or pr_val > practical_max:
            result["status"] = "EXCEEDS_MAX"
            result["flags"].append(f"Practical {pr_val} exceeds max {practical_max}")

    calculated_tot = th_val + pr_val

    # 5. Golden Arithmetic Self-Check: Theory + Practical == Total
    if tot_val is not None:
        if tot_val != calculated_tot:
            result["status"] = "ARITHMETIC_MISMATCH"
            result["flags"].append(f"Mismatch: Th({th_val}) + Pr({pr_val}) = {calculated_tot} != Written Total({tot_val})")
            # Keep calculated_tot as the primary candidate but flag it for review
            final_tot = calculated_tot
        else:
            final_tot = tot_val
    else:
        final_tot = calculated_tot
        result["flags"].append("Written total was blank, used calculated sum")

    if final_tot > total_max:
        result["status"] = "EXCEEDS_MAX"
        result["flags"].append(f"Total {final_tot} exceeds max {total_max}")

    pct = (final_tot / total_max * Decimal("100")) if total_max else Decimal("0.00")
    grd = grade_for_percentage(pct)

    result["theory_marks"] = th_val
    result["practical_marks"] = pr_val if has_practical else Decimal("0.00")
    result["total_marks"] = final_tot
    result["percentage"] = round(pct, 2)
    result["grade"] = grd

    # Separate Theory/Practical Pass Check
    subj_pass, fail_reasons = check_subject_pass(
        exam_test, th_val, pr_val if has_practical else Decimal("0.00"), final_tot, is_absent=False
    )
    result["is_pass"] = subj_pass
    if not subj_pass:
        result["fail_reasons"] = fail_reasons

    if not result["flags"]:
        result["status"] = "VALID"

    return result


def export_preview_csv(sheet_token, verified_rows, out_dir):
    """
    Saves the extracted marks preview to a clean CSV audit file.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_file = out_dir / f"MARKS_PREVIEW_{sheet_token}.csv"

    headers = [
        "S_NO", "ROLL_NO", "SID", "ADMISSION_NO", "STUDENT_NAME", "FATHER_NAME",
        "RAW_THEORY", "RAW_PRACTICAL", "RAW_TOTAL", "IS_ABSENT",
        "FINAL_THEORY", "FINAL_PRACTICAL", "FINAL_TOTAL", "PERCENTAGE", "GRADE",
        "PASS_STATUS", "STATUS", "FLAGS"
    ]

    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for idx, row in enumerate(verified_rows):
            pass_status_str = "PASS" if row.get("is_pass") else ("AB" if row.get("is_absent") else "FAIL")
            writer.writerow([
                idx + 1,
                row.get("roll_no") or "",
                row.get("legacy_sid") or "",
                row.get("admission_no") or "",
                row.get("student_name") or "",
                row.get("father_name") or "",
                row.get("raw_theory") or "",
                row.get("raw_practical") or "",
                row.get("raw_total") or "",
                "YES" if row.get("is_absent") else "NO",
                row.get("theory_marks") if row.get("theory_marks") is not None else "",
                row.get("practical_marks") if row.get("practical_marks") is not None else "",
                row.get("total_marks") if row.get("total_marks") is not None else "",
                f"{row['percentage']:.2f}" if row.get("percentage") is not None else "",
                row.get("grade") or "",
                pass_status_str,
                row.get("status") or "",
                "; ".join(row.get("flags") or []),
            ])

    return csv_file


def export_exceptions_csv(sheet_token, flagged_rows, out_dir):
    """
    Saves blocked/flagged rows (arithmetic mismatches, exceeds max, invalid digits, unmatched)
    to a dedicated exceptions CSV audit file: MARKS_EXCEPTIONS_<SHEET_TOKEN>.csv.
    Returns Path to the file, or None if no flagged rows.
    """
    if not flagged_rows:
        return None
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_file = out_dir / f"MARKS_EXCEPTIONS_{sheet_token}.csv"

    headers = [
        "S_NO", "ROLL_NO", "SID", "ADMISSION_NO", "STUDENT_NAME", "FATHER_NAME",
        "RAW_THEORY", "RAW_PRACTICAL", "RAW_TOTAL", "IS_ABSENT",
        "FINAL_THEORY", "FINAL_PRACTICAL", "FINAL_TOTAL", "STATUS", "FLAGS", "REMARKS"
    ]

    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for idx, row in enumerate(flagged_rows, 1):
            writer.writerow([
                idx,
                row.get("roll_no") or "",
                row.get("legacy_sid") or "",
                row.get("admission_no") or "",
                row.get("student_name") or "",
                row.get("father_name") or "",
                row.get("raw_theory") or "",
                row.get("raw_practical") or "",
                row.get("raw_total") or "",
                "YES" if row.get("is_absent") else "NO",
                row.get("theory_marks") if row.get("theory_marks") is not None else "",
                row.get("practical_marks") if row.get("practical_marks") is not None else "",
                row.get("total_marks") if row.get("total_marks") is not None else "",
                row.get("status") or "",
                "; ".join(row.get("flags") or []),
                row.get("remarks") or "",
            ])
    return csv_file


def commit_award_sheet_marks(exam_test, verified_rows, dry_run=False, force_commit_flagged=False):
    """
    Commits verified rows into the live database (ExamMark) inside an atomic transaction.
    HARD COMMIT GATE:
    - Only rows with status in ('VALID', 'ABSENT') are committed.
    - BLANK_ROW is skipped.
    - ARITHMETIC_MISMATCH, EXCEEDS_MAX, INVALID_DIGIT, UNMATCHED_STUDENT, etc. are STRICTLY BLOCKED
      and collected in summary['flagged_rows'] unless force_commit_flagged is True.
    Returns summary dict including flagged_blocked_count and flagged_rows.
    """
    summary = {
        "total_rows": len(verified_rows),
        "valid_rows": 0,
        "absent_rows": 0,
        "mismatch_rows": 0,
        "blank_rows": 0,
        "flagged_blocked_count": 0,
        "flagged_rows": [],
        "created_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "dry_run": dry_run,
    }

    with transaction.atomic():
        for row in verified_rows:
            status = row.get("status")
            if status == "ABSENT":
                summary["absent_rows"] += 1
            elif status == "VALID":
                summary["valid_rows"] += 1
            elif status == "BLANK_ROW":
                summary["blank_rows"] += 1
                summary["skipped_count"] += 1
                continue
            else:
                # Flagged status: ARITHMETIC_MISMATCH, EXCEEDS_MAX, INVALID_DIGIT, UNMATCHED_STUDENT, etc.
                if status == "ARITHMETIC_MISMATCH":
                    summary["mismatch_rows"] += 1
                summary["flagged_rows"].append(row)
                if not force_commit_flagged:
                    # HARD GATE: strictly block this row from touching the database!
                    summary["flagged_blocked_count"] += 1
                    summary["skipped_count"] += 1
                    continue

            # Student must exist
            student_id = row.get("student_id")
            if not student_id:
                summary["skipped_count"] += 1
                if row not in summary["flagged_rows"]:
                    summary["flagged_rows"].append(row)
                continue

            student = Student.objects.get(pk=student_id)

            if dry_run:
                # In dry run, check if record exists to count create vs update
                exists = ExamMark.objects.filter(exam_test=exam_test, student=student).exists()
                if exists:
                    summary["updated_count"] += 1
                else:
                    summary["created_count"] += 1
            else:
                is_ab = row.get("is_absent", False)
                obj, created = ExamMark.objects.update_or_create(
                    exam_test=exam_test,
                    student=student,
                    defaults={
                        "is_absent": is_ab,
                        "theory_marks_obtained": None if is_ab else row.get("theory_marks"),
                        "practical_marks_obtained": None if is_ab else row.get("practical_marks"),
                        "marks_obtained": None if is_ab else row.get("total_marks"),
                        "grade": row.get("grade", ""),
                        "remarks": "; ".join(row.get("flags", [])) if row.get("flags") else "",
                    }
                )
                if created:
                    summary["created_count"] += 1
                else:
                    summary["updated_count"] += 1

        if dry_run:
            transaction.set_rollback(True)

    return summary
