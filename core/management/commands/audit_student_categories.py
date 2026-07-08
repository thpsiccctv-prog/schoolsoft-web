import csv
import os

from django.core.management.base import BaseCommand

from core.models import Student

VALID_CATEGORIES = {"general", "gen", "obc", "sc", "st"}


class Command(BaseCommand):
    help = (
        "Audit Student.category values. The official admission form (Section 5 - "
        "Social Category) treats Category as strictly one of General/OBC/SC/ST, "
        "separate from Caste (a free-text field). The legacy import command used "
        "`CATE or cast` as a fallback, so any student whose legacy CATE column was "
        "blank ended up with a caste name (e.g. KOIRI, YADAV, MUSLMAN) sitting in "
        "the category field instead of General/OBC/SC/ST. That caste name then "
        "prints on the Transfer Certificate under 'Whether belongs to SC/ST/OBC', "
        "which is factually wrong.\n\n"
        "This command does NOT change any data (a caste name cannot be safely "
        "auto-mapped to a reservation category). It only lists students whose "
        "current category value is blank or is not one of General/OBC/SC/ST, so "
        "office staff can look each one up and correct it via the student edit "
        "form before that student's TC/admission paperwork is finalised."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--out",
            default=r"D:\english medium\migration_audit\category_audit.csv",
            help="Path to write the CSV report to.",
        )

    def handle(self, *args, **options):
        out_path = options["out"]

        suspect = []
        blank = []
        for student in Student.objects.select_related("current_class", "current_section").order_by(
            "current_class__display_order", "current_section__name", "full_name"
        ):
            value = (student.category or "").strip()
            if not value:
                blank.append(student)
            elif value.lower() not in VALID_CATEGORIES:
                suspect.append(student)

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerow(["legacy_sid", "admission_no", "full_name", "class", "section", "current_category_value", "issue"])
            for student in suspect:
                writer.writerow([
                    student.legacy_sid or "",
                    student.admission_no,
                    student.full_name,
                    student.current_class.name if student.current_class else "",
                    student.current_section.name if student.current_section else "",
                    student.category,
                    "looks like a caste name, not General/OBC/SC/ST",
                ])
            for student in blank:
                writer.writerow([
                    student.legacy_sid or "",
                    student.admission_no,
                    student.full_name,
                    student.current_class.name if student.current_class else "",
                    student.current_section.name if student.current_section else "",
                    student.category,
                    "blank",
                ])

        self.stdout.write(self.style.SUCCESS(
            f"Total students: {Student.objects.count()}\n"
            f"Suspect (caste-name-like) category values: {len(suspect)}\n"
            f"Blank category values: {len(blank)}\n"
            f"Report written to: {out_path}"
        ))
