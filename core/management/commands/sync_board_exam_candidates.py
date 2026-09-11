import csv
import os
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

csv.field_size_limit(2147483647)

import pymupdf
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import Student, SchoolClass, Section, AcademicSession
from core.krutidev import krutidev_to_unicode


def parse_date(date_str):
    if not date_str:
        return None
    date_str = str(date_str).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            pass
    return None


def norm(text):
    if not text:
        return ""
    return re.sub(r"[^A-Z]", "", str(text).upper())


TYPO_MAP = {
    "RARA KUMAR": "RAJA KUMAR",
    "LULMAN ALI": "LUKMAN ALI",
    "NITU KUMARI": "NETU KUMARI",
    "ADTIYA CHAUHAN": "ADITYA CHAUHAN",
    "SWHETA PRALHAD GUPTA": "SHWETA PRALHAD GUPTA",
    "AISRAJA ALI": "ASRAJA ALI",
}


class Command(BaseCommand):
    help = "Synchronizes official UP Board Regular Exam 2027 Candidates (Class 10 & 12) with live SchoolSoft database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pdf10",
            type=str,
            default=r"C:\Users\THPSIC THINKCLINTE2\.gemini\antigravity\brain\dd51995f-bbce-4efe-85cd-880aa13ac3ef\.user_uploaded\media_1789122882196.pdf",
            help="Path to Class 10 Board Regular Exam PDF",
        )
        parser.add_argument(
            "--pdf12",
            type=str,
            default=r"C:\Users\THPSIC THINKCLINTE2\.gemini\antigravity\brain\dd51995f-bbce-4efe-85cd-880aa13ac3ef\.user_uploaded\media_1789122882732.pdf",
            help="Path to Class 12 Board Regular Exam PDF",
        )
        parser.add_argument(
            "--adm-csv",
            type=str,
            default=r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35-new\ADDMISSION_raw.csv",
            help="Path to Folder 35 ADDMISSION_raw.csv",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply changes to the live database",
        )
        parser.add_argument(
            "--confirm",
            type=str,
            help="Safety confirmation token (must be 'THPSIC' when running with --apply)",
        )
        parser.add_argument(
            "--out-dir",
            type=str,
            default=r"E:\THPSIC-INTER-COLLEGE\05-reports\board-exam-candidates-2027",
            help="Output directory for audit report CSVs",
        )

    def extract_class10(self, pdf_path):
        if not os.path.exists(pdf_path):
            raise CommandError(f"PDF file not found: {pdf_path}")

        doc = pymupdf.open(pdf_path)
        students = []
        max_pages = min(len(doc), 72)

        for page_idx in range(max_pages):
            page = doc[page_idx]
            words = page.get_text("words")
            blocks = page.get_text("blocks")

            srl_words = [w for w in words if w[0] < 40.0 and re.match(r"^\d+\.$", w[4])]
            srl_words.sort(key=lambda w: w[1])

            for i, sw in enumerate(srl_words):
                srl = int(sw[4].rstrip("."))
                ay0 = sw[1] - 5.0
                ay1 = srl_words[i + 1][1] - 5.0 if i + 1 < len(srl_words) else ay0 + 85.0

                form_no = ""
                for w in words:
                    if 44.0 <= w[0] < 85.0 and ay0 <= (w[1] + w[3]) / 2.0 < ay0 + 35.0:
                        if re.match(r"^\d{4}$", w[4]):
                            form_no = w[4]
                            break

                name_en, mother_en, father_en = "", "", ""
                name_hi, mother_hi, father_hi = "", "", ""
                dob, dob_str, mobile = None, "", ""
                gender, caste_code, minority = "", "", False

                for b in blocks:
                    bx0, by0, bx1, by1, btext, bno, btype = b
                    b_ymid = (by0 + by1) / 2.0
                    if not (ay0 <= b_ymid < ay1 and bx0 >= 45.0):
                        continue
                    lines = [l.strip() for l in btext.split("\n") if l.strip()]
                    if 90.0 <= bx0 < 230.0:
                        if len(lines) >= 3:
                            name_en, mother_en, father_en = lines[0], lines[1], lines[2]
                        if len(lines) >= 6:
                            name_hi = krutidev_to_unicode(lines[3])
                            mother_hi = krutidev_to_unicode(lines[4])
                            father_hi = krutidev_to_unicode(lines[5])
                        elif len(lines) == 5:
                            name_hi = krutidev_to_unicode(lines[3])
                            mother_hi = krutidev_to_unicode(lines[4])
                    elif 230.0 <= bx0 < 305.0:
                        for l in lines:
                            if "/" in l and len(l) == 10:
                                dob_str = l
                                dob = parse_date(l)
                            elif re.match(r"^\d{10}$", l):
                                mobile = l
                    elif 305.0 <= bx0 < 380.0:
                        for l in lines:
                            if "FEMALE" in l:
                                gender = "F"
                            elif "MALE" in l:
                                gender = "M"
                            c_m = re.match(r"^([1-5])\s*-", l)
                            if c_m and not ("MALE" in l or "FEMALE" in l or "HINDI" in l or "FULL" in l):
                                caste_code = c_m.group(1)
                            if "MINORITY" in l:
                                minority = True

                # Word-based subject extraction
                subs = []
                for w in words:
                    if 380.0 <= w[0] < 430.0 and ay0 <= (w[1] + w[3]) / 2.0 < ay1:
                        if re.match(r"^\d{3}$", w[4]):
                            subs.append((w[1], w[4]))
                subs.sort(key=lambda x: x[0])
                subject_codes = [s[1] for s in subs]

                students.append({
                    "class_level": "X",
                    "srl": srl,
                    "form_no": form_no,
                    "name": name_en,
                    "mother": mother_en,
                    "father": father_en,
                    "name_hi": name_hi,
                    "mother_hi": mother_hi,
                    "father_hi": father_hi,
                    "dob": dob,
                    "dob_str": dob_str,
                    "mobile": mobile,
                    "gender": gender or "M",
                    "caste_code": caste_code or "4",
                    "minority": minority,
                    "subjects": subject_codes,
                })
        return students

    def extract_class12(self, pdf_path):
        if not os.path.exists(pdf_path):
            raise CommandError(f"PDF file not found: {pdf_path}")

        doc = pymupdf.open(pdf_path)
        students = []
        max_pages = min(len(doc), 91)

        for page_idx in range(max_pages):
            page = doc[page_idx]
            blocks = page.get_text("blocks")

            row_anchors = []
            for b in blocks:
                bx0, by0, bx1, by1, btext, bno, btype = b
                if bx0 < 45.0 and by0 > 80.0:
                    lines = [l.strip() for l in btext.split("\n") if l.strip()]
                    if lines and re.match(r"^\d+\.$", lines[0]):
                        srl = int(lines[0].rstrip("."))
                        form_no = lines[1] if len(lines) > 1 else ""
                        row_anchors.append((srl, form_no, by0 - 5.0))

            row_anchors.sort(key=lambda x: x[2])

            for i, anchor in enumerate(row_anchors):
                srl, form_no, ay0 = anchor
                ay1 = row_anchors[i + 1][2] if i + 1 < len(row_anchors) else ay0 + 85.0

                name_en, mother_en, father_en = "", "", ""
                name_hi, mother_hi, father_hi = "", "", ""
                mobile = ""
                gender, caste_code, minority = "", "", False
                grp = ""
                subjects = []
                hs_roll, hs_year, prev_board = "", "", ""

                for b in blocks:
                    bx0, by0, bx1, by1, btext, bno, btype = b
                    b_ymid = (by0 + by1) / 2.0
                    if not (ay0 <= b_ymid < ay1):
                        continue
                    lines = [l.strip() for l in btext.split("\n") if l.strip()]

                    # Names (80 <= bx0 < 220)
                    if 80.0 <= bx0 < 220.0:
                        if len(lines) >= 3:
                            name_en, mother_en, father_en = lines[0], lines[1], lines[2]
                        if len(lines) >= 6:
                            name_hi = krutidev_to_unicode(lines[3])
                            mother_hi = krutidev_to_unicode(lines[4])
                            father_hi = krutidev_to_unicode(lines[5])
                        elif len(lines) == 5:
                            name_hi = krutidev_to_unicode(lines[3])
                            mother_hi = krutidev_to_unicode(lines[4])

                    # Demographics (220 <= bx0 < 300)
                    elif 220.0 <= bx0 < 300.0:
                        for l in lines:
                            if "FEMALE" in l:
                                gender = "F"
                            elif "MALE" in l:
                                gender = "M"
                            c_m = re.match(r"^([1-5])\s*-", l)
                            if c_m and not ("MALE" in l or "FEMALE" in l or "HINDI" in l or "FULL" in l):
                                caste_code = c_m.group(1)
                            if "MINORITY" in l:
                                minority = True
                            if l in ("A", "B", "C"):
                                grp = l
                            if re.match(r"^\d{10}$", l):
                                mobile = l

                    # Subjects (300 <= bx0 < 420)
                    elif 300.0 <= bx0 < 420.0:
                        for l in lines:
                            s_m = re.match(r"^(\d{3})\s*-", l)
                            if s_m:
                                subjects.append(s_m.group(1))

                    # Transfer / HS Info (420 <= bx0 < 510)
                    elif 420.0 <= bx0 < 510.0:
                        text_all = " ".join(lines)
                        m_hs = re.search(r"HS\s*-\s*YEAR\s*:\s*(\d{4})\s*/\s*ROLL\s*:\s*(\d+)", text_all)
                        if m_hs:
                            hs_year = m_hs.group(1)
                            hs_roll = m_hs.group(2)
                        if "BIHAR" in text_all.upper():
                            prev_board = "BIHAR SCHOOL EXAMINATION BOARD"
                        elif "UP" in text_all.upper() or "PRAYAGRAJ" in text_all.upper():
                            prev_board = "U.P. BOARD"

                students.append({
                    "class_level": "XII",
                    "srl": srl,
                    "form_no": form_no,
                    "name": name_en,
                    "mother": mother_en,
                    "father": father_en,
                    "name_hi": name_hi,
                    "mother_hi": mother_hi,
                    "father_hi": father_hi,
                    "dob": None,
                    "dob_str": "",
                    "mobile": mobile,
                    "gender": gender or "M",
                    "caste_code": caste_code or "4",
                    "minority": minority,
                    "grp": grp or "B",
                    "subjects": subjects,
                    "hs_roll": hs_roll,
                    "hs_year": hs_year,
                    "prev_board": prev_board or "U.P. BOARD",
                })
        return students

    def handle(self, *args, **options):
        pdf10_path = options["pdf10"]
        pdf12_path = options["pdf12"]
        adm_csv_path = options["adm_csv"]
        apply_mode = options["apply"]
        confirm_str = options["confirm"]
        out_dir = Path(options["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        if apply_mode and confirm_str != "THPSIC":
            raise CommandError("You must provide '--confirm THPSIC' with --apply")

        self.stdout.write("==================================================================")
        self.stdout.write("UP BOARD REGULAR EXAM 2027 CANDIDATE SYNCHRONIZATION")
        self.stdout.write(f"Mode: {'LIVE APPLY' if apply_mode else 'DRY RUN'}")
        self.stdout.write(f"Class 10 PDF: {pdf10_path}")
        self.stdout.write(f"Class 12 PDF: {pdf12_path}")
        self.stdout.write(f"Folder 35 ADDMISSION: {adm_csv_path}")
        self.stdout.write("==================================================================")

        # Database safety backup in apply mode
        if apply_mode:
            db_path = os.environ.get(
                "SCHOOLSOFT_SQLITE_PATH",
                os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3"),
            )
            if os.path.exists(db_path):
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"{db_path}.backup_before_exam_sync_{ts}"
                shutil.copy2(db_path, backup_path)
                self.stdout.write(self.style.SUCCESS(f"[SAFETY BACKUP] Created: {backup_path}"))

        self.stdout.write("1. Extracting Candidates from Checklists...")
        st10 = self.extract_class10(pdf10_path)
        st12 = self.extract_class12(pdf12_path)
        self.stdout.write(f"   Extracted Class 10 candidates: {len(st10)}")
        self.stdout.write(f"   Extracted Class 12 candidates: {len(st12)}")

        # Load Folder 35 ADDMISSION
        adm_rows = []
        if os.path.exists(adm_csv_path):
            with open(adm_csv_path, "r", encoding="latin-1", errors="replace") as f:
                adm_rows = list(csv.DictReader(f))
            self.stdout.write(f"   Loaded Folder 35 ADDMISSION rows: {len(adm_rows)}")
        else:
            self.stdout.write(self.style.WARNING(f"   Folder 35 CSV not found: {adm_csv_path}"))

        students_x = list(Student.objects.filter(current_class__name__iexact="X").select_related("current_class", "current_section"))
        students_xii = list(Student.objects.filter(current_class__name__istartswith="XII").select_related("current_class", "current_section"))
        all_students = list(Student.objects.all().select_related("current_class", "current_section"))
        live_by_sid = {s.legacy_sid: s for s in all_students if s.legacy_sid}
        live_by_admno = {s.admission_no.strip(): s for s in all_students if s.admission_no}
        class_map = {c.name.upper(): c for c in SchoolClass.objects.all()}
        section_map = {}
        for sec in Section.objects.select_related("school_class").all():
            section_map[(sec.school_class.name.upper(), sec.name.upper())] = sec

        # Next admission number calculation
        max_admno = 10515
        for adm in Student.objects.exclude(admission_no="").values_list("admission_no", flat=True):
            if adm.isdigit() and int(adm) > max_admno:
                max_admno = int(adm)
        next_admno_seq = max_admno + 1

        stats = {
            "c10_total": len(st10),
            "c10_matched_db": 0,
            "c10_imported_f35": 0,
            "c10_created_direct": 0,
            "c12_total": len(st12),
            "c12_matched_db": 0,
            "c12_imported_f35": 0,
            "c12_created_direct": 0,
            "hindi_names_updated": 0,
            "board_srl_updated": 0,
            "dob_updated": 0,
            "subjects_updated": 0,
            "prev_exam_updated": 0,
        }

        audit_rows_10 = []
        audit_rows_12 = []

        with transaction.atomic():
            # =========================================================
            # PROCESS CLASS 10 CANDIDATES
            # =========================================================
            self.stdout.write("\n2. Processing Class 10 Exam Candidates...")
            
            x_by_name_father = {}
            x_by_name = {}
            x_by_mobile = {}
            for s in students_x:
                n = norm(s.full_name)
                fn = norm(s.father_name)
                if s.full_name in TYPO_MAP:
                    n = norm(TYPO_MAP[s.full_name])
                x_by_name_father.setdefault((n, fn), []).append(s)
                x_by_name.setdefault(n, []).append(s)
                if s.mobile_primary:
                    mob = re.sub(r"\D", "", s.mobile_primary)
                    if len(mob) == 10:
                        x_by_mobile.setdefault(mob, []).append(s)

            for c in st10:
                cn = norm(c["name"])
                cfn = norm(c["father"])
                cmn = norm(c["mother"])
                cmob = re.sub(r"\D", "", c.get("mobile", ""))

                target = None
                resolution_type = ""

                # Tier 1: Match DB
                if (cn, cfn) in x_by_name_father:
                    cands = x_by_name_father[(cn, cfn)]
                    target = cands[0]
                    resolution_type = "DB_EXACT_NAME_FATHER"
                elif len(cmob) == 10 and cmob in x_by_mobile:
                    for cand in x_by_mobile[cmob]:
                        if cn and norm(cand.full_name) and (cn[:4] == norm(cand.full_name)[:4] or norm(cand.full_name) in cn or cn in norm(cand.full_name)):
                            target = cand
                            resolution_type = "DB_MOBILE_PARTIAL_NAME"
                            break
                elif cn in x_by_name:
                    for cand in x_by_name[cn]:
                        cand_fn = norm(cand.father_name)
                        if cfn and cand_fn and (cfn[:3] == cand_fn[:3] or cfn in cand_fn or cand_fn in cfn):
                            target = cand
                            resolution_type = "DB_NAME_PARTIAL_FATHER"
                            break
                if not target:
                    for cand in students_x:
                        cand_n = norm(cand.full_name)
                        cand_fn = norm(cand.father_name)
                        if cand_n[:3] == cn[:3] and abs(len(cand_n) - len(cn)) <= 3:
                            if cand_fn and cfn and (cand_fn[:3] == cfn[:3] or cfn in cand_fn or cand_fn in cfn):
                                target = cand
                                resolution_type = "DB_FUZZY"
                                break

                # Tier 2: Check Folder 35
                f35_row = None
                if not target and adm_rows:
                    for r in adm_rows:
                        rn = norm(r.get("sname"))
                        rfn = norm(r.get("fname"))
                        if cn and rn and (cn == rn or (len(cn) >= 4 and cn in rn) or (len(rn) >= 4 and rn in cn)):
                            if cfn and rfn and (cfn[:3] == rfn[:3] or cfn in rfn or rfn in cfn):
                                f35_row = r
                                break

                # Tier 3: Create / Resolve
                changes = []
                if target:
                    stats["c10_matched_db"] += 1
                elif f35_row:
                    sid_val = int(f35_row["sid"]) if f35_row.get("sid", "").isdigit() else None
                    adm_no_val = str(f35_row.get("admno", "")).strip()
                    if sid_val and sid_val in live_by_sid:
                        target = live_by_sid[sid_val]
                        resolution_type = "DB_MATCH_VIA_F35_SID"
                        stats["c10_matched_db"] += 1
                    elif adm_no_val and adm_no_val in live_by_admno:
                        target = live_by_admno[adm_no_val]
                        resolution_type = "DB_MATCH_VIA_F35_ADMNO"
                        stats["c10_matched_db"] += 1
                    else:
                        stats["c10_imported_f35"] += 1
                        resolution_type = "FOLDER_35_IMPORT"
                        if not adm_no_val:
                            adm_no_val = str(sid_val or next_admno_seq)
                        while str(adm_no_val) in live_by_admno:
                            next_admno_seq += 1
                            adm_no_val = str(next_admno_seq)

                        cls_x = class_map.get("X")
                        sec_d = section_map.get(("X", "D")) or Section.objects.get_or_create(school_class=cls_x, name="D")[0]

                        target = Student(
                            legacy_sid=sid_val,
                            admission_no=adm_no_val,
                            full_name=c["name"],
                            father_name=c["father"],
                            mother_name=c["mother"],
                            current_class=cls_x,
                            current_section=sec_d,
                            mobile_primary=c["mobile"],
                            is_active=True,
                        )
                        if sid_val:
                            live_by_sid[sid_val] = target
                        live_by_admno[str(adm_no_val)] = target
                        changes.append(f"Imported from Folder 35 (SID {sid_val}, AdmNo {adm_no_val})")
                else:
                    stats["c10_created_direct"] += 1
                    resolution_type = "DIRECT_BOARD_CREATION"
                    while str(next_admno_seq) in live_by_admno:
                        next_admno_seq += 1
                    adm_no_val = str(next_admno_seq)
                    next_admno_seq += 1

                    cls_x = class_map.get("X")
                    sec_d = section_map.get(("X", "D")) or Section.objects.get_or_create(school_class=cls_x, name="D")[0]

                    target = Student(
                        admission_no=adm_no_val,
                        full_name=c["name"],
                        father_name=c["father"],
                        mother_name=c["mother"],
                        current_class=cls_x,
                        current_section=sec_d,
                        mobile_primary=c["mobile"],
                        is_active=True,
                    )
                    live_by_admno[str(adm_no_val)] = target
                    changes.append(f"Created direct board candidate (AdmNo {adm_no_val})")

                # Update Fields
                if c["name_hi"] and target.full_name_hindi != c["name_hi"]:
                    changes.append(f"Name_HI: '{target.full_name_hindi}' -> '{c['name_hi']}'")
                    target.full_name_hindi = c["name_hi"]
                    stats["hindi_names_updated"] += 1

                if c["father_hi"] and target.father_name_hindi != c["father_hi"]:
                    changes.append(f"Father_HI: '{target.father_name_hindi}' -> '{c['father_hi']}'")
                    target.father_name_hindi = c["father_hi"]

                if c["mother_hi"] and target.mother_name_hindi != c["mother_hi"]:
                    changes.append(f"Mother_HI: '{target.mother_name_hindi}' -> '{c['mother_hi']}'")
                    target.mother_name_hindi = c["mother_hi"]

                if c["form_no"] and target.board_sr_number != c["form_no"]:
                    changes.append(f"BoardSr: '{target.board_sr_number}' -> '{c['form_no']}'")
                    target.board_sr_number = c["form_no"]
                    stats["board_srl_updated"] += 1

                if c["dob"] and target.date_of_birth != c["dob"]:
                    changes.append(f"DOB: '{target.date_of_birth}' -> '{c['dob']}'")
                    target.date_of_birth = c["dob"]
                    stats["dob_updated"] += 1

                if c["gender"] and target.gender != c["gender"]:
                    target.gender = c["gender"]
                if c["caste_code"] and target.board_caste_code != c["caste_code"]:
                    target.board_caste_code = c["caste_code"]
                target.is_minority = c["minority"]
                target.exam_medium = "H"
                target.subject_group = "HS"

                # Subjects 1-7
                subs = c["subjects"]
                if subs:
                    sub_fields = [
                        ("subject_1_code", subs[0] if len(subs) > 0 else ""),
                        ("subject_2_code", subs[1] if len(subs) > 1 else ""),
                        ("subject_3_code", subs[2] if len(subs) > 2 else ""),
                        ("subject_4_code", subs[3] if len(subs) > 3 else ""),
                        ("subject_5_code", subs[4] if len(subs) > 4 else ""),
                        ("subject_6_code", subs[5] if len(subs) > 5 else ""),
                        ("subject_7_code", subs[6] if len(subs) > 6 else ""),
                    ]
                    sub_changed = False
                    for fld, val in sub_fields:
                        if getattr(target, fld) != val:
                            setattr(target, fld, val)
                            sub_changed = True
                    if sub_changed:
                        changes.append(f"Subjects: {subs}")
                        stats["subjects_updated"] += 1

                if apply_mode and changes:
                    target.save()

                audit_rows_10.append({
                    "Class": "X",
                    "SRL": c["srl"],
                    "FormNo": c["form_no"],
                    "Name": c["name"],
                    "Father": c["father"],
                    "Mother": c["mother"],
                    "Resolution": resolution_type,
                    "Status": "UPDATED" if changes else "NO_CHANGE",
                    "Matched_SID": target.legacy_sid or "",
                    "AdmNo": target.admission_no or "",
                    "DB_Name": target.full_name,
                    "Changes": "; ".join(changes) if changes else "Already up to date",
                })

            # =========================================================
            # PROCESS CLASS 12 CANDIDATES
            # =========================================================
            self.stdout.write("\n3. Processing Class 12 Exam Candidates...")

            xii_by_name_father = {}
            xii_by_name = {}
            xii_by_mobile = {}
            xii_by_roll = {}
            for s in students_xii:
                n = norm(s.full_name)
                fn = norm(s.father_name)
                if s.full_name in TYPO_MAP:
                    n = norm(TYPO_MAP[s.full_name])
                xii_by_name_father.setdefault((n, fn), []).append(s)
                xii_by_name.setdefault(n, []).append(s)
                if s.mobile_primary:
                    mob = re.sub(r"\D", "", s.mobile_primary)
                    if len(mob) == 10:
                        xii_by_mobile.setdefault(mob, []).append(s)
                if s.previous_roll_no:
                    xii_by_roll.setdefault(s.previous_roll_no.strip(), []).append(s)
                if s.roll_no:
                    xii_by_roll.setdefault(str(s.roll_no).strip(), []).append(s)

            def get_class12_stream(cand_c):
                grp = cand_c.get("grp", "B")
                subs = cand_c.get("subjects", [])
                if grp == "A":
                    return class_map.get("XII (ART)") or class_map.get("XII (BIO)")
                elif grp == "C":
                    return class_map.get("XII (COM)") or class_map.get("XII (BIO)")
                else:
                    if "153" in subs:
                        return class_map.get("XII (BIO)")
                    elif "149" in subs or "150" in subs:
                        return class_map.get("XII (MATHS)")
                    return class_map.get("XII (BIO)")

            for c in st12:
                cn = norm(c["name"])
                cfn = norm(c["father"])
                cmn = norm(c["mother"])
                cmob = re.sub(r"\D", "", c.get("mobile", ""))
                ch_roll = str(c.get("hs_roll", "")).strip()

                target = None
                resolution_type = ""

                # Tier 1: Match DB
                if (cn, cfn) in xii_by_name_father:
                    cands = xii_by_name_father[(cn, cfn)]
                    target = cands[0]
                    resolution_type = "DB_EXACT_NAME_FATHER"
                elif ch_roll and ch_roll in xii_by_roll:
                    target = xii_by_roll[ch_roll][0]
                    resolution_type = "DB_PREV_ROLL"
                elif len(cmob) == 10 and cmob in xii_by_mobile:
                    for cand in xii_by_mobile[cmob]:
                        if cn and norm(cand.full_name) and (cn[:4] == norm(cand.full_name)[:4] or norm(cand.full_name) in cn or cn in norm(cand.full_name)):
                            target = cand
                            resolution_type = "DB_MOBILE_PARTIAL_NAME"
                            break
                elif cn in xii_by_name:
                    for cand in xii_by_name[cn]:
                        cand_fn = norm(cand.father_name)
                        if cfn and cand_fn and (cfn[:3] == cand_fn[:3] or cfn in cand_fn or cand_fn in cfn):
                            target = cand
                            resolution_type = "DB_NAME_PARTIAL_FATHER"
                            break
                if not target:
                    for cand in students_xii:
                        cand_n = norm(cand.full_name)
                        cand_fn = norm(cand.father_name)
                        if cand_n[:3] == cn[:3] and abs(len(cand_n) - len(cn)) <= 3:
                            if cand_fn and cfn and (cand_fn[:3] == cfn[:3] or cfn in cand_fn or cand_fn in cfn):
                                target = cand
                                resolution_type = "DB_FUZZY"
                                break

                # Tier 2: Check Folder 35
                f35_row = None
                if not target and adm_rows:
                    for r in adm_rows:
                        rn = norm(r.get("sname"))
                        rfn = norm(r.get("fname"))
                        if cn and rn and (cn == rn or (len(cn) >= 4 and cn in rn) or (len(rn) >= 4 and rn in cn)):
                            if cfn and rfn and (cfn[:3] == rfn[:3] or cfn in rfn or rfn in cfn):
                                f35_row = r
                                break

                # Tier 3: Create / Resolve
                changes = []
                if target:
                    stats["c12_matched_db"] += 1
                    # Typo corrections
                    if target.full_name == "RARA KUMAR" and c["name"] == "RAJA KUMAR":
                        changes.append("Fix typo: 'RARA KUMAR' -> 'RAJA KUMAR'")
                        target.full_name = "RAJA KUMAR"
                    elif target.full_name == "LULMAN ALI" and c["name"] == "LUKMAN ALI":
                        changes.append("Fix typo: 'LULMAN ALI' -> 'LUKMAN ALI'")
                        target.full_name = "LUKMAN ALI"
                    elif target.full_name == "ADTIYA CHAUHAN" and c["name"] == "ADITYA CHAUHAN":
                        changes.append("Fix typo: 'ADTIYA CHAUHAN' -> 'ADITYA CHAUHAN'")
                        target.full_name = "ADITYA CHAUHAN"
                    elif target.full_name == "SWHETA PRALHAD GUPTA" and c["name"] == "SHWETA PRALHAD GUPTA":
                        changes.append("Fix typo: 'SWHETA PRALHAD GUPTA' -> 'SHWETA PRALHAD GUPTA'")
                        target.full_name = "SHWETA PRALHAD GUPTA"
                elif f35_row:
                    sid_val = int(f35_row["sid"]) if f35_row.get("sid", "").isdigit() else None
                    adm_no_val = str(f35_row.get("admno", "")).strip()
                    if sid_val and sid_val in live_by_sid:
                        target = live_by_sid[sid_val]
                        resolution_type = "DB_MATCH_VIA_F35_SID"
                        stats["c12_matched_db"] += 1
                    elif adm_no_val and adm_no_val in live_by_admno:
                        target = live_by_admno[adm_no_val]
                        resolution_type = "DB_MATCH_VIA_F35_ADMNO"
                        stats["c12_matched_db"] += 1
                    else:
                        stats["c12_imported_f35"] += 1
                        resolution_type = "FOLDER_35_IMPORT"
                        if not adm_no_val:
                            adm_no_val = str(sid_val or next_admno_seq)
                        while str(adm_no_val) in live_by_admno:
                            next_admno_seq += 1
                            adm_no_val = str(next_admno_seq)

                        target_cls = get_class12_stream(c)
                        sec_d = section_map.get((target_cls.name.upper(), "D")) or Section.objects.get_or_create(school_class=target_cls, name="D")[0]

                        target = Student(
                            legacy_sid=sid_val,
                            admission_no=adm_no_val,
                            full_name=c["name"],
                            father_name=c["father"],
                            mother_name=c["mother"],
                            current_class=target_cls,
                            current_section=sec_d,
                            mobile_primary=c["mobile"],
                            is_active=True,
                        )
                        if sid_val:
                            live_by_sid[sid_val] = target
                        live_by_admno[str(adm_no_val)] = target
                        changes.append(f"Imported from Folder 35 (SID {sid_val}, AdmNo {adm_no_val}) into {target_cls.name}")
                else:
                    stats["c12_created_direct"] += 1
                    resolution_type = "DIRECT_BOARD_CREATION"
                    while str(next_admno_seq) in live_by_admno:
                        next_admno_seq += 1
                    adm_no_val = str(next_admno_seq)
                    next_admno_seq += 1

                    target_cls = get_class12_stream(c)
                    sec_d = section_map.get((target_cls.name.upper(), "D")) or Section.objects.get_or_create(school_class=target_cls, name="D")[0]

                    target = Student(
                        admission_no=adm_no_val,
                        full_name=c["name"],
                        father_name=c["father"],
                        mother_name=c["mother"],
                        current_class=target_cls,
                        current_section=sec_d,
                        mobile_primary=c["mobile"],
                        is_active=True,
                    )
                    live_by_admno[str(adm_no_val)] = target
                    changes.append(f"Created direct board candidate (AdmNo {adm_no_val}) in {target_cls.name}")

                # Update Fields
                if c["name_hi"] and target.full_name_hindi != c["name_hi"]:
                    changes.append(f"Name_HI: '{target.full_name_hindi}' -> '{c['name_hi']}'")
                    target.full_name_hindi = c["name_hi"]
                    stats["hindi_names_updated"] += 1

                if c["father_hi"] and target.father_name_hindi != c["father_hi"]:
                    changes.append(f"Father_HI: '{target.father_name_hindi}' -> '{c['father_hi']}'")
                    target.father_name_hindi = c["father_hi"]

                if c["mother_hi"] and target.mother_name_hindi != c["mother_hi"]:
                    changes.append(f"Mother_HI: '{target.mother_name_hindi}' -> '{c['mother_hi']}'")
                    target.mother_name_hindi = c["mother_hi"]

                if c["form_no"] and target.board_sr_number != c["form_no"]:
                    changes.append(f"BoardSr: '{target.board_sr_number}' -> '{c['form_no']}'")
                    target.board_sr_number = c["form_no"]
                    stats["board_srl_updated"] += 1

                if c["gender"] and target.gender != c["gender"]:
                    target.gender = c["gender"]
                if c["caste_code"] and target.board_caste_code != c["caste_code"]:
                    target.board_caste_code = c["caste_code"]
                target.is_minority = c["minority"]
                target.exam_medium = "H"
                target.subject_group = c["grp"]

                # Previous Exam Details (HS Roll & Year)
                if c["hs_roll"] and target.previous_roll_no != c["hs_roll"]:
                    changes.append(f"PrevRoll: '{target.previous_roll_no}' -> '{c['hs_roll']}'")
                    target.previous_roll_no = c["hs_roll"]
                    stats["prev_exam_updated"] += 1
                if c["hs_year"] and str(target.previous_passing_year) != str(c["hs_year"]):
                    changes.append(f"PrevYear: '{target.previous_passing_year}' -> '{c['hs_year']}'")
                    target.previous_passing_year = c["hs_year"]
                    stats["prev_exam_updated"] += 1
                if c["prev_board"] and target.previous_board_name != c["prev_board"]:
                    changes.append(f"PrevBoard: '{target.previous_board_name}' -> '{c['prev_board']}'")
                    target.previous_board_name = c["prev_board"]

                # Subjects 1-7
                subs = c["subjects"]
                if subs:
                    sub_fields = [
                        ("subject_1_code", subs[0] if len(subs) > 0 else ""),
                        ("subject_2_code", subs[1] if len(subs) > 1 else ""),
                        ("subject_3_code", subs[2] if len(subs) > 2 else ""),
                        ("subject_4_code", subs[3] if len(subs) > 3 else ""),
                        ("subject_5_code", subs[4] if len(subs) > 4 else ""),
                        ("subject_6_code", subs[5] if len(subs) > 5 else ""),
                        ("subject_7_code", subs[6] if len(subs) > 6 else ""),
                    ]
                    sub_changed = False
                    for fld, val in sub_fields:
                        if getattr(target, fld) != val:
                            setattr(target, fld, val)
                            sub_changed = True
                    if sub_changed:
                        changes.append(f"Subjects: {subs}")
                        stats["subjects_updated"] += 1

                if apply_mode and changes:
                    target.save()

                audit_rows_12.append({
                    "Class": "XII",
                    "SRL": c["srl"],
                    "FormNo": c["form_no"],
                    "Name": c["name"],
                    "Father": c["father"],
                    "Mother": c["mother"],
                    "Stream": c["grp"],
                    "Resolution": resolution_type,
                    "Status": "UPDATED" if changes else "NO_CHANGE",
                    "Matched_SID": target.legacy_sid or "",
                    "AdmNo": target.admission_no or "",
                    "DB_Name": target.full_name,
                    "Changes": "; ".join(changes) if changes else "Already up to date",
                })

            # Output CSV Audits
            out_c10_csv = out_dir / "class_10_exam_candidates_sync_audit.csv"
            with open(out_c10_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "Class", "SRL", "FormNo", "Name", "Father", "Mother",
                    "Resolution", "Status", "Matched_SID", "AdmNo", "DB_Name", "Changes"
                ])
                writer.writeheader()
                writer.writerows(audit_rows_10)

            out_c12_csv = out_dir / "class_12_exam_candidates_sync_audit.csv"
            with open(out_c12_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    "Class", "SRL", "FormNo", "Name", "Father", "Mother", "Stream",
                    "Resolution", "Status", "Matched_SID", "AdmNo", "DB_Name", "Changes"
                ])
                writer.writeheader()
                writer.writerows(audit_rows_12)

            out_summary_txt = out_dir / "summary_report.txt"
            with open(out_summary_txt, "w", encoding="utf-8") as f:
                f.write("=== UP BOARD REGULAR EXAM 2027 SYNCHRONIZATION SUMMARY ===\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Mode: {'LIVE APPLY' if apply_mode else 'DRY RUN'}\n\n")
                f.write(f"Class 10 Total Candidates: {stats['c10_total']}\n")
                f.write(f"  - Matched Directly in DB: {stats['c10_matched_db']}\n")
                f.write(f"  - Imported from Folder 35: {stats['c10_imported_f35']}\n")
                f.write(f"  - Direct Board Candidates Created: {stats['c10_created_direct']}\n")
                f.write(f"  - Total Accounted: {stats['c10_matched_db'] + stats['c10_imported_f35'] + stats['c10_created_direct']} / {stats['c10_total']} (100.0%)\n\n")
                f.write(f"Class 12 Total Candidates: {stats['c12_total']}\n")
                f.write(f"  - Matched Directly in DB: {stats['c12_matched_db']}\n")
                f.write(f"  - Imported from Folder 35: {stats['c12_imported_f35']}\n")
                f.write(f"  - Direct Board Candidates Created: {stats['c12_created_direct']}\n")
                f.write(f"  - Total Accounted: {stats['c12_matched_db'] + stats['c12_imported_f35'] + stats['c12_created_direct']} / {stats['c12_total']} (100.0%)\n\n")
                f.write("Updates Applied:\n")
                f.write(f"  - Authentic Hindi Names Updated: {stats['hindi_names_updated']}\n")
                f.write(f"  - Board Form Numbers (board_sr_number) Updated: {stats['board_srl_updated']}\n")
                f.write(f"  - Date of Birth Updated: {stats['dob_updated']}\n")
                f.write(f"  - Subject Codes 1-7 Updated: {stats['subjects_updated']}\n")
                f.write(f"  - High School Roll/Year (Class 12) Updated: {stats['prev_exam_updated']}\n")

        self.stdout.write("\n==================================================================")
        self.stdout.write(self.style.SUCCESS("SYNCHRONIZATION RESULTS SUMMARY:"))
        self.stdout.write(f"Class 10 Accounted: {stats['c10_matched_db'] + stats['c10_imported_f35'] + stats['c10_created_direct']} / {stats['c10_total']} (100.0%)")
        self.stdout.write(f"  -> Matched in DB: {stats['c10_matched_db']} | Folder 35: {stats['c10_imported_f35']} | Direct: {stats['c10_created_direct']}")
        self.stdout.write(f"Class 12 Accounted: {stats['c12_matched_db'] + stats['c12_imported_f35'] + stats['c12_created_direct']} / {stats['c12_total']} (100.0%)")
        self.stdout.write(f"  -> Matched in DB: {stats['c12_matched_db']} | Folder 35: {stats['c12_imported_f35']} | Direct: {stats['c12_created_direct']}")
        self.stdout.write(f"Hindi Names Updated: {stats['hindi_names_updated']}")
        self.stdout.write(f"Board SR Numbers Updated: {stats['board_srl_updated']}")
        self.stdout.write(f"Subjects Updated: {stats['subjects_updated']}")
        self.stdout.write(f"HS Rolls/Years Updated: {stats['prev_exam_updated']}")
        self.stdout.write(f"Audit Reports written to: {out_dir}")
        self.stdout.write("==================================================================")
