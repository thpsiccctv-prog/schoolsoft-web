import csv
import os
from decimal import Decimal
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import Student, FeeReceipt, FeeReceiptLine, FeeHead, AcademicSession
from core.fee_engine import calculate_student_due

class Command(BaseCommand):
    help = "Migrates fee receipts for newly admitted students from Folder 35 MDB export with strict duplicate protection and concession sync."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Apply changes to the live database")
        parser.add_argument("--confirm", type=str, help="Safety confirmation token (THPSIC)")
        parser.add_argument("--stufee-csv", type=str, default=r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35-new\StuFee_raw.csv", help="Path to StuFee_raw.csv")
        parser.add_argument("--preview-csv", type=str, default=r"E:\THPSIC-INTER-COLLEGE\05-reports\folder35-new-admissions\NEW_ADMISSIONS_FOLDER35_PREVIEW.csv", help="Path to 191 new admissions preview CSV")
        parser.add_argument("--out-dir", type=str, default=r"E:\THPSIC-INTER-COLLEGE\05-reports\folder35-new-receipts", help="Output directory for reports")

    def handle(self, *args, **options):
        apply_mode = options.get("apply", False)
        confirm_token = options.get("confirm", "")
        stufee_path = options.get("stufee_csv")
        preview_path = options.get("preview_csv")
        out_dir = Path(options.get("out_dir"))
        out_dir.mkdir(parents=True, exist_ok=True)

        if apply_mode and confirm_token != "THPSIC":
            self.stderr.write(self.style.ERROR("SAFETY ERROR: You must specify --confirm THPSIC to apply changes."))
            return

        self.stdout.write(self.style.MIGRATE_HEADING("=== FOLDER 35 NEW STUDENT RECEIPTS MIGRATION ==="))
        self.stdout.write(f"Mode: {'APPLY LIVE' if apply_mode else 'DRY-RUN PREVIEW'}")
        self.stdout.write(f"StuFee Source: {stufee_path}")

        # 1. Load active session
        session = AcademicSession.objects.filter(is_active=True).first() or AcademicSession.objects.first()
        if not session:
            self.stderr.write(self.style.ERROR("No active AcademicSession found in DB!"))
            return

        # 2. Load 191 new admissions SIDs
        csv.field_size_limit(2147483647)
        if not os.path.exists(preview_path):
            self.stderr.write(self.style.ERROR(f"Preview CSV not found at: {preview_path}"))
            return

        with open(preview_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            new_sids = {int(r["legacy_sid"]): r for r in reader if r.get("legacy_sid", "").strip().isdigit()}

        self.stdout.write(f"Loaded {len(new_sids)} target new student SIDs.")

        # 3. Index existing live students & receipts
        live_students = {s.legacy_sid: s for s in Student.objects.all() if s.legacy_sid}
        live_receipts = FeeReceipt.objects.all().select_related("student")

        existing_rcp_keys = set()
        existing_date_amt_keys = set()
        for fr in live_receipts:
            sid = fr.student.legacy_sid if fr.student else None
            if sid:
                existing_rcp_keys.add((sid, str(fr.receipt_no)))
                existing_rcp_keys.add((sid, f"SF-{fr.receipt_no}"))
                existing_rcp_keys.add((sid, f"MR-{fr.receipt_no}"))
                existing_date_amt_keys.add((sid, fr.receipt_date.strftime("%Y-%m-%d"), str(fr.received_amount)))

        # 4. Fee Head Mapping
        fee_heads_map = {}
        for fh in FeeHead.objects.all():
            fee_heads_map[fh.name.upper()] = fh
            if fh.legacy_column:
                fee_heads_map[fh.legacy_column.upper()] = fh

        adm_head = fee_heads_map.get("ADMISSION FEE") or fee_heads_map.get("ADMISSION_FEE")
        tut_head = fee_heads_map.get("TUITION FEE") or fee_heads_map.get("TUITION_FEE")
        gen_head = fee_heads_map.get("GENERATOR FEE") or fee_heads_map.get("GEN_FEE")
        exa_head = fee_heads_map.get("EXAM FEE") or fee_heads_map.get("EXAM_FEE")
        dev_head = fee_heads_map.get("DEVELOPMENT FEE") or fee_heads_map.get("DEV_FEE")
        sci_head = fee_heads_map.get("SCIENCE FEE") or fee_heads_map.get("SCI_FEE") or fee_heads_map.get("LAB_FEE")

        # 5. Read StuFee_raw.csv
        with open(stufee_path, "r", encoding="latin-1", errors="replace") as f:
            reader = csv.DictReader(f)
            all_stufee = list(reader)

        preview_records = []
        exceptions_records = []
        created_count = 0
        skipped_count = 0
        total_paid_imported = Decimal("0.00")
        total_concession_imported = Decimal("0.00")

        with transaction.atomic():
            for r in all_stufee:
                rcp_str = str(r.get("rcpno", "")).strip()
                sid_str = str(r.get("sid", "")).strip()
                v_date_str = str(r.get("v_date", "")).strip()
                paid_str = str(r.get("paid", "0")).strip() or "0"

                if not rcp_str.isdigit():
                    continue

                if not sid_str.isdigit():
                    exceptions_records.append({
                        "old_rcp_no": rcp_str, "legacy_sid": sid_str, "student_name": r.get("sname", ""),
                        "receipt_date": v_date_str, "paid_amount": paid_str, "reason": "Non-numeric SID"
                    })
                    continue

                sid = int(sid_str)

                # Only target the 191 newly migrated students (Rule 4 & Rule E)
                if sid not in new_sids:
                    continue

                student = live_students.get(sid)
                if not student:
                    exceptions_records.append({
                        "old_rcp_no": rcp_str, "legacy_sid": sid, "student_name": r.get("sname", ""),
                        "receipt_date": v_date_str, "paid_amount": paid_str, "reason": "Student not found in DB"
                    })
                    continue

                try:
                    dt = datetime.strptime(v_date_str.split(" ")[0], "%m/%d/%y").date()
                    date_iso = dt.strftime("%Y-%m-%d")
                    date_display = dt.strftime("%d/%m/%Y")
                except:
                    date_iso = v_date_str
                    date_display = v_date_str
                    dt = timezone.localdate()

                try:
                    paid = Decimal(paid_str)
                except:
                    paid = Decimal("0.00")

                less = Decimal(r.get("LES_FEE", "0") or "0")
                tot = Decimal(r.get("FEE_TOT", "0") or "0")
                due = Decimal(r.get("due", "0") or "0")
                net_tot = Decimal(r.get("NET_TOT", "0") or "0")

                # Double duplicate detection (Rule D)
                is_duplicate = False
                if (sid, rcp_str) in existing_rcp_keys or (sid, f"SF-{rcp_str}") in existing_rcp_keys:
                    is_duplicate = True
                elif (sid, date_iso, str(paid)) in existing_date_amt_keys:
                    is_duplicate = True

                if is_duplicate:
                    skipped_count += 1
                    preview_records.append({
                        "legacy_sid": sid, "admission_no": student.admission_no, "student_name": student.full_name,
                        "class_section": f"{student.current_class.name}-{student.current_section.name}",
                        "old_rcp_no": rcp_str, "receipt_date": date_display, "from_month": r.get("FRMONTH", ""),
                        "to_month": r.get("TOMONTH", ""), "gross_amount": str(tot), "concession_less": str(less),
                        "paid_amount": str(paid), "balance_due": str(due), "already_exists": "yes", "import_action": "SKIP"
                    })
                    continue

                # Specific concession adjustment for SHIV KUMAR (SID 10388)
                # In MDB, package charged was ₹4,000 (standard XI-D is ₹4,500).
                # Setting concession_amount = ₹500 ensures fee engine computes exact ₹3,000 due.
                if sid == 10388:
                    less = Decimal("500.00")

                # CREATE RECORD
                created_count += 1
                total_paid_imported += paid
                total_concession_imported += less

                preview_records.append({
                    "legacy_sid": sid, "admission_no": student.admission_no, "student_name": student.full_name,
                    "class_section": f"{student.current_class.name}-{student.current_section.name}",
                    "old_rcp_no": rcp_str, "receipt_date": date_display, "from_month": r.get("FRMONTH", ""),
                    "to_month": r.get("TOMONTH", ""), "gross_amount": str(tot), "concession_less": str(less),
                    "paid_amount": str(paid), "balance_due": str(due), "already_exists": "no", "import_action": "CREATE"
                })

                if apply_mode:
                    receipt_no = f"SF-{rcp_str}"
                    receipt = FeeReceipt.objects.create(
                        legacy_receipt_no=int(rcp_str),
                        receipt_no=receipt_no,
                        student=student,
                        session=session,
                        student_name_snapshot=student.full_name,
                        father_name_snapshot=student.father_name,
                        class_snapshot=student.current_class.name if student.current_class else "",
                        section_snapshot=student.current_section.name if student.current_section else "",
                        receipt_date=dt,
                        from_month=r.get("FRMONTH", "").strip(),
                        to_month=r.get("TOMONTH", "").strip(),
                        payment_mode=FeeReceipt.PaymentMode.CASH,
                        concession_amount=less,  # Rule A: Less directly to concession_amount
                        late_fee_amount=Decimal("0.00"),
                        received_amount=paid,
                        legacy_fee_total=tot,
                        legacy_net_total=net_tot,
                        legacy_due_amount=due,
                        carried_forward=False,  # Rule B: Current year receipt
                        remarks=f"Folder 35 MDB Receipt #{rcp_str} (Migrated)"
                    )

                    # Create FeeReceiptLine items
                    line_items = [
                        (adm_head, Decimal(r.get("ADM_FEE", "0") or "0")),
                        (tut_head, Decimal(r.get("TUT_FEE", "0") or "0")),
                        (gen_head, Decimal(r.get("GEN_FEE", "0") or "0")),
                        (exa_head, Decimal(r.get("EXA_FEE", "0") or "0")),
                        (dev_head, Decimal(r.get("DEV_FEE", "0") or "0")),
                        (sci_head, Decimal(r.get("SCI_FEE", "0") or "0") + Decimal(r.get("LAB_FEE", "0") or "0")),
                    ]

                    for head, amt in line_items:
                        if head and amt > Decimal("0.00"):
                            FeeReceiptLine.objects.create(
                                receipt=receipt,
                                fee_head=head,
                                amount=amt
                            )

            if not apply_mode:
                # Rollback everything in dry-run
                transaction.set_rollback(True)

        # 6. Save Reports
        csv_file = out_dir / "NEW_STUDENT_RECEIPTS_FOLDER35_PREVIEW.csv"
        with open(csv_file, "w", encoding="utf-8-sig", newline="") as f:
            fields = ["legacy_sid", "admission_no", "student_name", "class_section", "old_rcp_no", "receipt_date", "from_month", "to_month", "gross_amount", "concession_less", "paid_amount", "balance_due", "already_exists", "import_action"]
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(preview_records)

        exc_file = out_dir / "NEW_STUDENT_RECEIPTS_FOLDER35_EXCEPTIONS.csv"
        with open(exc_file, "w", encoding="utf-8-sig", newline="") as f:
            fields = ["old_rcp_no", "legacy_sid", "student_name", "receipt_date", "paid_amount", "reason"]
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(exceptions_records)

        self.stdout.write(self.style.SUCCESS(f"\nMigration Summary:"))
        self.stdout.write(f"- New Receipts to Create: {created_count}")
        self.stdout.write(f"- Already Existing / Skipped: {skipped_count}")
        self.stdout.write(f"- Total Paid Amount: ₹{total_paid_imported:,.2f}")
        self.stdout.write(f"- Total Concession Amount: ₹{total_concession_imported:,.2f}")
        self.stdout.write(f"- Preview CSV: {csv_file}")
        self.stdout.write(f"- Exceptions CSV: {exc_file}")
