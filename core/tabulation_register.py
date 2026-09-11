"""
core/tabulation_register.py
Generates the comprehensive Class-wise Result Tabulation Register (परीक्षा फल सारणी / Broad Sheet)
in both high-fidelity formatted Excel (.xlsx) and printable Landscape PDF formats.
Displays all students in a class/section with subject-wise marks breakdown, grand totals,
percentages, divisions, and rank.
"""

from decimal import Decimal
import io
import math
from pathlib import Path

from django.db.models import Q
from django.utils import timezone
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak

from core.models import ExamTerm, ExamTest, ExamMark, SchoolClass, Section, Student, grade_for_percentage, division_for_percentage


def build_tabulation_data(school_class, section=None, term=None):
    """
    Collects and calculates full result matrix for a given class, section, and term.
    Returns: {
        'term': term,
        'school_class': school_class,
        'section': section,
        'tests': list of ExamTest,
        'students_data': list of student result dicts sorted by rank/roll,
        'stats': summary statistics dict
    }
    """
    if term is None:
        term = ExamTerm.objects.filter(session__is_active=True).order_by("display_order", "id").first()

    tests = list(ExamTest.objects.select_related("subject").filter(
        school_class=school_class,
        term=term
    ).order_by("subject__display_order", "subject__name"))

    qs = Student.objects.filter(is_active=True, current_class=school_class)
    if section:
        qs = qs.filter(current_section=section)
    students = list(qs.order_by("roll_no", "legacy_sid", "full_name"))

    # Prefetch all marks for this class & term
    marks_qs = ExamMark.objects.select_related("exam_test").filter(
        exam_test__in=tests,
        student__in=students
    )
    marks_map = {}  # (student_id, test_id) -> mark
    for m in marks_qs:
        marks_map[(m.student_id, m.exam_test_id)] = m

    students_data = []
    for s in students:
        s_res = {
            "student": s,
            "roll_no": s.roll_no or "",
            "admission_no": s.admission_no or "",
            "legacy_sid": s.legacy_sid,
            "full_name": s.full_name,
            "father_name": s.father_name,
            "subject_marks": [],
            "grand_total_obtained": Decimal("0.00"),
            "grand_total_max": Decimal("0.00"),
            "has_failed": False,
            "all_absent": True,
            "percentage": Decimal("0.00"),
            "division": "",
            "overall_grade": "",
            "rank": 0,
        }

        any_appeared = False
        for t in tests:
            m = marks_map.get((s.id, t.id))
            tot_max = t.max_marks or Decimal("100.00")
            s_res["grand_total_max"] += tot_max

            if m:
                if m.is_absent:
                    s_res["subject_marks"].append({
                        "test_id": t.id,
                        "theory": None,
                        "practical": None,
                        "total": None,
                        "grade": "AB",
                        "is_absent": True,
                        "is_pass": False,
                    })
                    s_res["has_failed"] = True
                else:
                    any_appeared = True
                    s_res["all_absent"] = False
                    obt = m.marks_obtained or Decimal("0.00")
                    th = m.theory_marks_obtained
                    pr = m.practical_marks_obtained
                    grd = m.grade or grade_for_percentage((obt / tot_max * 100) if tot_max else 0)
                    is_pass = (obt >= (t.pass_marks or Decimal("33.00")))
                    if not is_pass:
                        s_res["has_failed"] = True

                    s_res["grand_total_obtained"] += obt
                    s_res["subject_marks"].append({
                        "test_id": t.id,
                        "theory": th,
                        "practical": pr,
                        "total": obt,
                        "grade": grd,
                        "is_absent": False,
                        "is_pass": is_pass,
                    })
            else:
                # No mark entry yet
                s_res["subject_marks"].append({
                    "test_id": t.id,
                    "theory": None,
                    "practical": None,
                    "total": None,
                    "grade": "—",
                    "is_absent": False,
                    "is_pass": False,
                })

        if any_appeared and s_res["grand_total_max"]:
            pct = (s_res["grand_total_obtained"] / s_res["grand_total_max"] * Decimal("100"))
            s_res["percentage"] = round(pct, 2)
            s_res["overall_grade"] = grade_for_percentage(pct)
            s_res["division"] = division_for_percentage(pct, is_failed=s_res["has_failed"])
        else:
            s_res["division"] = "Absent (अनुपस्थित)" if s_res["all_absent"] else "—"
            s_res["overall_grade"] = "AB" if s_res["all_absent"] else "—"

        students_data.append(s_res)

    # Assign ranks based on grand_total_obtained (descending) among non-failed students
    sorted_for_rank = sorted(
        [r for r in students_data if not r["has_failed"] and not r["all_absent"]],
        key=lambda x: x["grand_total_obtained"],
        reverse=True
    )
    for rank_idx, r in enumerate(sorted_for_rank):
        r["rank"] = rank_idx + 1

    # Overall stats
    total_enrolled = len(students)
    appeared = sum(1 for r in students_data if not r["all_absent"])
    absent = total_enrolled - appeared
    passed_first = sum(1 for r in students_data if "FIRST" in r["division"])
    passed_second = sum(1 for r in students_data if "SECOND" in r["division"])
    passed_third = sum(1 for r in students_data if "THIRD" in r["division"])
    passed_total = passed_first + passed_second + passed_third
    failed_count = appeared - passed_total

    stats = {
        "total_enrolled": total_enrolled,
        "appeared": appeared,
        "absent": absent,
        "passed_first": passed_first,
        "passed_second": passed_second,
        "passed_third": passed_third,
        "passed_total": passed_total,
        "failed_count": failed_count,
        "pass_percentage": round((passed_total / appeared * 100), 1) if appeared else 0.0,
    }

    return {
        "term": term,
        "school_class": school_class,
        "section": section,
        "tests": tests,
        "students_data": students_data,
        "stats": stats,
    }


def generate_tabulation_register_excel(school_class, section=None, term=None):
    """
    Generates a professionally styled Excel workbook (.xlsx) of the Tabulation Register.
    """
    data = build_tabulation_data(school_class, section, term)
    tests = data["tests"]
    students_data = data["students_data"]
    stats = data["stats"]
    term = data["term"]
    sec_label = f" - Section {section.name}" if section else ""

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"BroadSheet_{school_class.name[:10]}"

    # Header fonts and styles
    title_font = Font(name="Calibri", size=14, bold=True, color="1E3A8A")
    sub_font = Font(name="Calibri", size=11, bold=True, color="0F172A")
    meta_font = Font(name="Calibri", size=9.5, italic=True, color="475569")
    th_font = Font(name="Calibri", size=9, bold=True, color="FFFFFF")
    th_sub_font = Font(name="Calibri", size=8, bold=True, color="CBD5E1")
    cell_font = Font(name="Calibri", size=9)
    bold_cell_font = Font(name="Calibri", size=9, bold=True)
    pass_font = Font(name="Calibri", size=9, bold=True, color="15803D")
    fail_font = Font(name="Calibri", size=9, bold=True, color="B91C1C")

    hdr_fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
    sub_hdr_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    alt_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    stat_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    # 1. School Title
    total_cols = 5 + len(tests) + 6
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    ws.cell(row=1, column=1, value="T H P S INTERMEDIATE COLLEGE").font = title_font
    ws.cell(row=1, column=1).alignment = Alignment(horizontal="center", vertical="center")

    # 2. Exam Subtitle
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=total_cols)
    ws.cell(row=2, column=1, value=f"{term.name.upper()} — TABULATION REGISTER (परीक्षा फल सारणी)").font = sub_font
    ws.cell(row=2, column=1).alignment = Alignment(horizontal="center", vertical="center")

    # 3. Class/Section Strip
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=total_cols)
    ws.cell(row=3, column=1, value=f"Class: {school_class.name}{sec_label} | Session: {term.session.name} | Date: {timezone.localdate().strftime('%d-%b-%Y')}").font = meta_font
    ws.cell(row=3, column=1).alignment = Alignment(horizontal="center", vertical="center")

    # 4. Table Headers (Row 4)
    headers = ["S.N.", "Roll", "SID", "Student Name", "Father Name"]
    for t in tests:
        sub_short = t.subject.name.split("(")[0].strip()
        headers.append(f"{sub_short}\n(Max {int(t.max_marks)})")
    headers.extend(["Grand Total", "Max Marks", "Percentage", "Grade", "Division", "Rank"])

    ws.append([])  # blank row 4
    for c_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=5, column=c_idx, value=h)
        cell.font = th_font
        cell.fill = hdr_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    ws.row_dimensions[5].height = 28

    # 5. Student Rows
    for r_idx, s in enumerate(students_data, 1):
        row_num = 5 + r_idx
        row_vals = [
            r_idx,
            s["roll_no"],
            s["legacy_sid"],
            s["full_name"],
            s["father_name"],
        ]
        for m in s["subject_marks"]:
            if m["is_absent"]:
                row_vals.append("AB")
            elif m["total"] is not None:
                row_vals.append(float(m["total"]))
            else:
                row_vals.append("—")

        row_vals.extend([
            float(s["grand_total_obtained"]),
            float(s["grand_total_max"]),
            f"{s['percentage']:.1f}%" if s["percentage"] else "—",
            s["overall_grade"],
            s["division"],
            s["rank"] if s["rank"] > 0 else "—",
        ])

        for c_idx, val in enumerate(row_vals, 1):
            cell = ws.cell(row=row_num, column=c_idx, value=val)
            cell.font = bold_cell_font if c_idx in (1, 2, 3, total_cols - 5, total_cols) else cell_font
            cell.border = thin_border
            if c_idx in (1, 2, 3, total_cols - 5, total_cols - 4, total_cols - 3, total_cols - 2, total_cols):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif c_idx in (4, 5):
                cell.alignment = Alignment(horizontal="left", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="center", vertical="center")

            # Division color
            if c_idx == total_cols - 1:
                if "FIRST" in str(val) or "SECOND" in str(val) or "THIRD" in str(val):
                    cell.font = pass_font
                elif "Fail" in str(val) or "अनुत्तीर्ण" in str(val):
                    cell.font = fail_font

            if r_idx % 2 == 0:
                cell.fill = alt_fill

    # 6. Summary Statistics Block
    stat_row = 5 + len(students_data) + 2
    ws.cell(row=stat_row, column=1, value="CLASS SUMMARY STATISTICS").font = Font(name="Calibri", size=10, bold=True, color="1E3A8A")
    summary_items = [
        f"Total Enrolled: {stats['total_enrolled']}",
        f"Appeared: {stats['appeared']}",
        f"Absent: {stats['absent']}",
        f"Passed: {stats['passed_total']} ({stats['pass_percentage']}%)",
        f"First Div: {stats['passed_first']}",
        f"Second Div: {stats['passed_second']}",
        f"Third Div: {stats['passed_third']}",
        f"Failed: {stats['failed_count']}",
    ]
    for idx, item in enumerate(summary_items, 1):
        c = ws.cell(row=stat_row + 1, column=idx * 2 - 1, value=item)
        c.font = bold_cell_font
        c.fill = stat_fill
        ws.merge_cells(start_row=stat_row + 1, start_column=idx * 2 - 1, end_row=stat_row + 1, end_column=idx * 2)

    # Auto column widths
    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 9)

    ws.column_dimensions["D"].width = 22  # Student Name
    ws.column_dimensions["E"].width = 20  # Father Name

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
