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
    }

    # 1. Check Absent
    if is_absent:
        result["is_absent"] = True
        result["grade"] = "AB"
        result["status"] = "ABSENT"
        return result

    # 2. Check Blank / Unentered
    th_str = str(raw_th or "").strip()
    pr_str = str(raw_pr or "").strip()
    tot_str = str(raw_tot or "").strip()

    if not th_str and not pr_str and not tot_str:
        result["status"] = "BLANK_ROW"
        result["flags"].append("No marks entered")
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
        "STATUS", "FLAGS"
    ]

    with open(csv_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for idx, row in enumerate(verified_rows):
            writer.writerow([
                idx + 1,
                row["roll_no"] or "",
                row["legacy_sid"] or "",
                row["admission_no"] or "",
                row["student_name"],
                row["father_name"],
                row["raw_theory"],
                row["raw_practical"],
                row["raw_total"],
                "YES" if row["is_absent"] else "NO",
                row["theory_marks"] if row["theory_marks"] is not None else "",
                row["practical_marks"] if row["practical_marks"] is not None else "",
                row["total_marks"] if row["total_marks"] is not None else "",
                f"{row['percentage']:.2f}" if row["percentage"] is not None else "",
                row["grade"],
                row["status"],
                "; ".join(row["flags"]),
            ])

    return csv_file


def commit_award_sheet_marks(exam_test, verified_rows, dry_run=False):
    """
    Commits verified rows into the live database (ExamMark) inside an atomic transaction.
    Returns counts of created and updated records.
    """
    summary = {
        "total_rows": len(verified_rows),
        "valid_rows": 0,
        "absent_rows": 0,
        "mismatch_rows": 0,
        "blank_rows": 0,
        "created_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "dry_run": dry_run,
    }

    with transaction.atomic():
        for row in verified_rows:
            status = row["status"]
            if status == "ABSENT":
                summary["absent_rows"] += 1
            elif status == "VALID":
                summary["valid_rows"] += 1
            elif status == "ARITHMETIC_MISMATCH":
                summary["mismatch_rows"] += 1
            elif status == "BLANK_ROW":
                summary["blank_rows"] += 1
                summary["skipped_count"] += 1
                continue

            # Don't commit unentered blank rows
            student_id = row["student_id"]
            student = Student.objects.get(pk=student_id)

            if dry_run:
                # In dry run, check if record exists to count create vs update
                exists = ExamMark.objects.filter(exam_test=exam_test, student=student).exists()
                if exists:
                    summary["updated_count"] += 1
                else:
                    summary["created_count"] += 1
            else:
                is_ab = row["is_absent"]
                obj, created = ExamMark.objects.update_or_create(
                    exam_test=exam_test,
                    student=student,
                    defaults={
                        "is_absent": is_ab,
                        "theory_marks_obtained": None if is_ab else row["theory_marks"],
                        "practical_marks_obtained": None if is_ab else row["practical_marks"],
                        "marks_obtained": None if is_ab else row["total_marks"],
                        "grade": row["grade"],
                        "remarks": "; ".join(row["flags"]) if row["flags"] else "",
                    }
                )
                if created:
                    summary["created_count"] += 1
                else:
                    summary["updated_count"] += 1

        if dry_run:
            transaction.set_rollback(True)

    return summary
