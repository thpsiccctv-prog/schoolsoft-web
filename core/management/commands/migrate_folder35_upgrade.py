import csv
import os
import re
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

csv.field_size_limit(2147483647)

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import (
    Student, SchoolClass, Section, FeeReceipt, AcademicSession
)
from core.krutidev import krutidev_to_unicode, is_corrupt_string


class Command(BaseCommand):
    help = "Live Migration of Folder 35 Upgrade: New Admissions, Stream Mapping, and Authentic Hindi Names"

    def add_arguments(self, parser):
        parser.add_argument(
            "--adm-csv",
            type=str,
            default=r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35-new\ADDMISSION_raw.csv",
            help="Path to ADDMISSION_raw.csv",
        )
        parser.add_argument(
            "--fee-csv",
            type=str,
            default=r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35-new\StuFee_raw.csv",
            help="Path to StuFee_raw.csv",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply changes to the database",
        )
        parser.add_argument(
            "--confirm",
            type=str,
            help="Must be 'THPSIC' when running with --apply",
        )

    def parse_date(self, date_str):
        if not date_str:
            return None
        date_str = str(date_str).split(" ")[0].strip()
        for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                d = datetime.strptime(date_str, fmt).date()
                if d.year < 1900:
                    d = d.replace(year=d.year + 2000)
                elif d.year > 2050:
                    d = d.replace(year=d.year - 100)
                return d
            except ValueError:
                pass
        return None

    def get_authentic_hindi(self, raw_val):
        if not raw_val or is_corrupt_string(raw_val):
            return ""
        converted = krutidev_to_unicode(raw_val)
        if converted and not converted.isdigit() and len(converted) > 1:
            return converted
        return ""

    def get_board_serial(self, raw_val):
        value = str(raw_val or "").strip()
        if not value or not value.isdigit() or len(value) > 6:
            return ""
        return value.zfill(4) if len(value) < 4 else value

    def map_student_class_section_fee(self, raw_cls, raw_sec):
        raw_cls = str(raw_cls or "").strip().upper()
        raw_sec = str(raw_sec or "").strip().upper() or "A"
        
        is_package = False
        
        if raw_cls in ("6", "6TH", "VI"):
            target_class_name = "VI"
            target_sec_name = "A"
        elif raw_cls in ("7", "7TH", "VII"):
            target_class_name = "VII"
            target_sec_name = "A"
        elif raw_cls in ("8", "8TH", "VIII"):
            target_class_name = "VIII"
            target_sec_name = "A"
        elif raw_cls in ("9", "9TH", "IX"):
            target_class_name = "IX"
            target_sec_name = raw_sec
            if raw_sec == "D":
                is_package = True
        elif raw_cls in ("10", "10TH", "X"):
            target_class_name = "X"
            target_sec_name = raw_sec
            if raw_sec == "D":
                is_package = True
        elif raw_cls in ("11", "11TH", "XI"):
            # In Class XI: raw_sec in MDB represents stream code
            if raw_sec == "B":
                target_class_name = "XI (BIO)"
                target_sec_name = "A"
            elif raw_sec == "C":
                target_class_name = "XI (COM)"
                target_sec_name = "A"
            elif raw_sec == "M":
                target_class_name = "XI (MATHS)"
                target_sec_name = "A"
            elif raw_sec == "A":
                target_class_name = "XI (ART)"
                target_sec_name = "A"
            elif raw_sec == "D":
                target_class_name = "XI (BIO)"
                target_sec_name = "D"
                is_package = True
            elif raw_sec == "F":
                target_class_name = "XI (ART)"
                target_sec_name = "A"
            else:
                target_class_name = "XI (BIO)"
                target_sec_name = "A"
        elif raw_cls in ("12", "12TH", "XII"):
            if raw_sec == "B":
                target_class_name = "XII (BIO)"
                target_sec_name = "A"
            elif raw_sec == "C":
                target_class_name = "XII (COM)"
                target_sec_name = "A"
            elif raw_sec == "M":
                target_class_name = "XII (MATHS)"
                target_sec_name = "A"
            elif raw_sec == "A":
                target_class_name = "XII (ART)"
                target_sec_name = "A"
            elif raw_sec == "D":
                target_class_name = "XII (BIO)"
                target_sec_name = "D"
                is_package = True
            else:
                target_class_name = "XII (BIO)"
                target_sec_name = "A"
        else:
            target_class_name = "IX"
            target_sec_name = "A"
            
        return target_class_name, target_sec_name, is_package

    def handle(self, *args, **options):
        adm_csv = Path(options["adm_csv"])
        fee_csv = Path(options["fee_csv"])
        apply_mode = options["apply"]
        confirm_str = options["confirm"]

        if apply_mode and confirm_str != "THPSIC":
            raise CommandError("You must provide '--confirm THPSIC' with --apply")

        if not adm_csv.exists():
            raise CommandError(f"File not found: {adm_csv}")

        self.stdout.write(f"=== MIGRATION FROM FOLDER 35 (SCHOOL7.mdb Upgrade) ===")
        self.stdout.write(f"Mode: {'LIVE APPLY' if apply_mode else 'DRY RUN'}")
        self.stdout.write(f"Source ADDMISSION: {adm_csv}")

        session = AcademicSession.objects.filter(is_active=True).first()
        if not session:
            session = AcademicSession.objects.first()

        # Load ADDMISSION_raw.csv
        with open(adm_csv, "r", encoding="latin-1", errors="replace") as f:
            reader = csv.DictReader(f)
            adm_rows = list(reader)

        self.stdout.write(f"Total rows in ADDMISSION: {len(adm_rows)}")

        # Build lookup of live students by legacy_sid and admission_no
        live_students = {s.legacy_sid: s for s in Student.objects.all() if s.legacy_sid}
        live_admnos = {s.admission_no.strip(): s for s in Student.objects.all() if s.admission_no}
        self.stdout.write(f"Existing live students in SchoolSoft: {len(live_students)}")

        # Class lookup cache
        class_map = {c.name.upper(): c for c in SchoolClass.objects.all()}

        # Caste mapping
        caste_map = {
            "SC": "1", "ST": "2", "OBC": "3", "GENERAL": "4", "GEN": "4", "EWS": "5"
        }

        stats = {
            "existing_students_matched": 0,
            "hindi_name_updated": 0,
            "hindi_fname_updated": 0,
            "hindi_mname_updated": 0,
            "new_admissions_created": 0,
            "regular_new_students": 0,
            "feeder_new_students": 0,
            "package_new_students": 0,
        }

        new_students_list = []

        with transaction.atomic():
            # ==========================================
            # STEP 1: HINDI NAMES FOR EXISTING STUDENTS (Authentic Only)
            # ==========================================
            for row in adm_rows:
                sid_str = str(row.get("sid", "")).strip()
                if not sid_str.isdigit():
                    continue
                sid = int(sid_str)

                student = live_students.get(sid)
                if not student:
                    continue

                stats["existing_students_matched"] += 1

                raw_hname = str(row.get("H_NAME", "")).strip()
                raw_hfname = str(row.get("H_FNAME", "")).strip()
                raw_hmname = str(row.get("H_MNAME", "")).strip()

                hname = self.get_authentic_hindi(raw_hname)
                hfname = self.get_authentic_hindi(raw_hfname)
                hmname = self.get_authentic_hindi(raw_hmname)

                changed = False
                if hname and student.full_name_hindi != hname:
                    student.full_name_hindi = hname
                    stats["hindi_name_updated"] += 1
                    changed = True

                if hfname and student.father_name_hindi != hfname:
                    student.father_name_hindi = hfname
                    stats["hindi_fname_updated"] += 1
                    changed = True

                if hmname and student.mother_name_hindi != hmname:
                    student.mother_name_hindi = hmname
                    stats["hindi_mname_updated"] += 1
                    changed = True

                if changed and apply_mode:
                    student.save(update_fields=["full_name_hindi", "father_name_hindi", "mother_name_hindi"])

            # ==========================================
            # STEP 2: NEW ADMISSIONS (SESSION 2026-27)
            # ==========================================
            for row in adm_rows:
                sid_str = str(row.get("sid", "")).strip()
                if not sid_str.isdigit():
                    continue
                sid = int(sid_str)
                adm_no = str(row.get("admno", "")).strip()

                if sid in live_students or (adm_no and adm_no in live_admnos):
                    continue

                # Check if belongs to session 2026-27
                adm_year = str(row.get("adm_year", "")).strip()
                adm_date_for_filter = self.parse_date(row.get("v_date"))
                is_2026 = adm_year in ("26", "2026", "26-27") or (
                    adm_date_for_filter is not None and adm_date_for_filter.year == 2026
                )

                if not is_2026:
                    continue

                raw_class = str(row.get("class", "")).strip().upper()
                raw_sec = str(row.get("section", "")).strip().upper() or "A"

                target_cls_name, target_sec_name, is_package = self.map_student_class_section_fee(raw_class, raw_sec)

                school_class = class_map.get(target_cls_name) or class_map.get(target_cls_name.replace(" ", ""))
                if not school_class:
                    school_class = class_map.get("IX")

                # Section resolution / creation if needed
                section, _ = Section.objects.get_or_create(
                    school_class=school_class,
                    name=target_sec_name
                )

                # Student fields
                sname = str(row.get("sname", "")).strip().upper()
                fname = str(row.get("fname", "")).strip().upper()
                mname = str(row.get("mname", "")).strip().upper()
                dob = self.parse_date(row.get("dobfig"))
                adm_date = self.parse_date(row.get("v_date")) or timezone.now().date()
                mobile = str(row.get("pmobile", "")).strip() or str(row.get("pphone", "")).strip()
                address = str(row.get("padr1", "")).strip()
                village = str(row.get("padr1", "")).strip()
                block = str(row.get("padr2", "")).strip()
                district = str(row.get("padr3", "")).strip()
                gender = "F" if str(row.get("SEX", "")).strip().upper() in ("FEMALE", "GIRL", "F", "2") else "M"
                cast = str(row.get("cast", "")).strip().upper()
                caste_code = caste_map.get(cast, "4")
                caste_name = str(row.get("cast1", "")).strip() or cast

                # Authentic Hindi names
                hname = self.get_authentic_hindi(str(row.get("H_NAME", "")).strip())
                hfname = self.get_authentic_hindi(str(row.get("H_FNAME", "")).strip())
                hmname = self.get_authentic_hindi(str(row.get("H_MNAME", "")).strip())
                board_sr_number = self.get_board_serial(row.get("fedu"))

                stats["new_admissions_created"] += 1
                if target_cls_name == "IX" and target_sec_name in ("B", "C"):
                    stats["feeder_new_students"] += 1
                elif is_package or target_sec_name == "D":
                    stats["package_new_students"] += 1
                else:
                    stats["regular_new_students"] += 1

                new_students_list.append((sid, target_cls_name, target_sec_name, sname, hname, fname, mname))

                if apply_mode:
                    new_student = Student.objects.create(
                        legacy_sid=sid,
                        admission_no=adm_no or str(sid),
                        full_name=sname,
                        full_name_hindi=hname,
                        father_name=fname,
                        father_name_hindi=hfname,
                        mother_name=mname,
                        mother_name_hindi=hmname,
                        date_of_birth=dob,
                        admission_date=adm_date,
                        gender=gender,
                        mobile_primary=mobile,
                        address_permanent=address,
                        village_locality=village,
                        block=block,
                        district=district,
                        category=cast,
                        caste=caste_name,
                        board_caste_code=caste_code,
                        board_sr_number=board_sr_number,
                        current_class=school_class,
                        current_section=section,
                        fee_package_enabled=is_package,
                        fee_package_total=Decimal("4500.00") if is_package else Decimal("0.00"),
                        fee_package_note="Auto package by THPSIC Section D policy" if is_package else "",
                        is_active=True,
                    )
                    live_students[sid] = new_student

            if not apply_mode:
                transaction.set_rollback(True)

        self.stdout.write("\n=== MIGRATION AUDIT RESULTS ===")
        self.stdout.write(f"Existing Students Matched:     {stats['existing_students_matched']}")
        self.stdout.write(f"Candidate Hindi Names Updated: {stats['hindi_name_updated']}")
        self.stdout.write(f"Father Hindi Names Updated:    {stats['hindi_fname_updated']}")
        self.stdout.write(f"Mother Hindi Names Updated:    {stats['hindi_mname_updated']}")
        self.stdout.write(f"New 2026 Admissions Created:   {stats['new_admissions_created']}")
        self.stdout.write(f"  - Regular Fee Paying:        {stats['regular_new_students']}")
        self.stdout.write(f"  - Feeder (Zero Fee Sec B/C): {stats['feeder_new_students']}")
        self.stdout.write(f"  - Package (Section D):       {stats['package_new_students']}")

        self.stdout.write(self.style.SUCCESS(f"\nMigration {'APPLIED SUCCESSFULLY' if apply_mode else 'DRY RUN COMPLETED'}!"))
