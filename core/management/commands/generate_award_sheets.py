"""
Django Management Command to batch-generate Teacher Award Sheets (अंक प्रविष्टि पत्रक)
for Quarterly Examination 2026-27 (or any active exam term).
Supports single class/section/test export as well as full-school batch generation.
"""

from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from core.models import ExamTerm, ExamTest, SchoolClass, Section, AcademicSession
from core.award_sheet import build_award_sheet_pdf, build_class_award_sheets_bundle_pdf


class Command(BaseCommand):
    help = "Generates printable PDF Award Sheets (अंक प्रविष्टि पत्रक) for teachers."

    def add_arguments(self, parser):
        parser.add_argument(
            "--term",
            type=int,
            default=None,
            help="ExamTerm ID (defaults to first term in active session).",
        )
        parser.add_argument(
            "--class",
            dest="class_name",
            type=str,
            default=None,
            help="Filter by SchoolClass name (e.g. 'IX', 'X', 'VI').",
        )
        parser.add_argument(
            "--section",
            type=str,
            default=None,
            help="Filter by Section name (e.g. 'A', 'B').",
        )
        parser.add_argument(
            "--subject",
            type=str,
            default=None,
            help="Filter by Subject name (e.g. 'Math', 'Hindi').",
        )
        parser.add_argument(
            "--bundle",
            action="store_true",
            help="Generate single combined multi-subject booklet PDF for each class/section.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Generate award sheets for all classes and sections in the active term.",
        )
        parser.add_argument(
            "--out-dir",
            default=r"E:\THPSIC-INTER-COLLEGE\05-reports\quarterly-exam-2026\blank-award-sheets",
            help="Destination output directory for PDF files.",
        )

    def handle(self, *args, **options):
        import sys
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

        term_id = options.get("term")
        class_name = options.get("class_name")
        section_name = options.get("section")
        subject_filter = options.get("subject")
        bundle_mode = options.get("bundle")
        all_mode = options.get("all")
        out_dir = Path(options.get("out_dir"))
        out_dir.mkdir(parents=True, exist_ok=True)

        # 1. Resolve Term
        if term_id:
            term = ExamTerm.objects.filter(pk=term_id).first()
            if not term:
                raise CommandError(f"ExamTerm with ID {term_id} does not exist.")
        else:
            term = ExamTerm.objects.filter(session__is_active=True).order_by("display_order", "id").first()
            if not term:
                term = ExamTerm.objects.first()
            if not term:
                raise CommandError("No ExamTerm found in the database.")

        self.stdout.write(self.style.SUCCESS(f"Selected Exam Term: {term.name} ({term.session})"))

        # 2. Resolve Classes
        if class_name:
            classes = list(SchoolClass.objects.filter(name__iexact=class_name))
            if not classes:
                classes = list(SchoolClass.objects.filter(name__icontains=class_name))
            if not classes:
                raise CommandError(f"No SchoolClass found matching '{class_name}'.")
        elif all_mode:
            classes = list(SchoolClass.objects.all().order_by("display_order", "id"))
        else:
            # Default: list available and require argument
            self.stdout.write("Please specify --class='<name>' or --all. Available classes:")
            for c in SchoolClass.objects.all().order_by("display_order"):
                self.stdout.write(f"  - {c.name}")
            return

        generated_count = 0

        for sc in classes:
            sections = list(sc.sections.all().order_by("name"))
            if section_name:
                sections = [s for s in sections if s.name.lower() == section_name.lower()]
                if not sections:
                    self.stdout.write(self.style.WARNING(f"Section '{section_name}' not found for {sc.name}, using all students."))
                    sections = [None]
            elif not sections:
                sections = [None]

            for sec in sections:
                sec_label = f"Sec_{sec.name}" if sec else "All_Sections"
                class_dir = out_dir / f"Class_{sc.name.replace(' ', '_')}" / sec_label
                class_dir.mkdir(parents=True, exist_ok=True)

                if bundle_mode:
                    try:
                        bundle_pdf = build_class_award_sheets_bundle_pdf(sc, section=sec, term=term)
                        out_path = class_dir / f"Award_Sheets_{sc.name.replace(' ', '_')}_{sec_label}_ALL_SUBJECTS.pdf"
                        out_path.write_bytes(bundle_pdf)
                        generated_count += 1
                        self.stdout.write(self.style.SUCCESS(f"  [BUNDLE] {out_path.name} ({len(bundle_pdf)} bytes)"))
                    except Exception as exc:
                        self.stdout.write(self.style.ERROR(f"  Failed bundle for {sc.name} {sec_label}: {exc}"))
                    continue

                tests_qs = ExamTest.objects.select_related("subject", "school_class").filter(
                    school_class=sc,
                    term=term
                ).order_by("subject__display_order", "subject__name")

                if subject_filter:
                    tests_qs = tests_qs.filter(subject__name__icontains=subject_filter)

                for test in tests_qs:
                    sub_clean = test.subject.name.split("(")[0].strip().replace(" ", "_").replace("/", "-")
                    try:
                        sheet_pdf = build_award_sheet_pdf(test, section=sec)
                        file_name = f"Award_Sheet_{sc.name.replace(' ', '_')}_{sec_label}_{sub_clean}.pdf"
                        out_path = class_dir / file_name
                        out_path.write_bytes(sheet_pdf)
                        generated_count += 1
                        self.stdout.write(f"  Generated: {file_name} ({len(sheet_pdf)} bytes)")
                    except Exception as exc:
                        self.stdout.write(self.style.ERROR(f"  Failed {test.subject.name}: {exc}"))

        self.stdout.write(self.style.SUCCESS(f"\nCompleted! Generated {generated_count} Award Sheet PDF(s) in:\n  {out_dir}"))
