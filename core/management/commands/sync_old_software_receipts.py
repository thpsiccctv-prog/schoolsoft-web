import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Max
from django.utils import timezone

from core.fee_engine import calculate_student_due
from core.models import AcademicSession, FeeHead, FeeReceipt, FeeReceiptLine, Student


DEFAULT_STUFEE_CSV = r"E:\THPSIC-INTER-COLLEGE\05-reports\access-audit-raw\school7-comp35-new\StuFee_raw.csv"
DEFAULT_OUT_DIR = r"E:\THPSIC-INTER-COLLEGE\05-reports\incremental-receipt-sync"
MONTH_ALIASES = {
    "APRIL": "APR",
    "MAY": "MAY",
    "JUNE": "JUN",
    "JULY": "JUL",
    "AUGUST": "AUG",
    "SEPTEMBER": "SEP",
    "OCTOBER": "OCT",
    "NOVEMBER": "NOV",
    "DECEMBER": "DEC",
    "JANUARY": "JAN",
    "FEBRUARY": "FEB",
    "MARCH": "MAR",
}

FEE_COLUMNS = [
    "ADM_FEE",
    "DEV_FEE",
    "TUT_FEE",
    "COM_FEE",
    "LIB_FEE",
    "CON_FEE",
    "SCI_FEE",
    "ELE_FEE",
    "SPO_FEE",
    "GEN_FEE",
    "MED_FEE",
    "EXA_FEE",
    "HOS_FEE",
    "ANU_FEE",
    "OTH_FEE",
    "FIN_FEE",
    "DUE_FEE",
    "BULD_FEE",
    "HAND_FEE",
    "LAB_FEE",
    "NCONS_FEE",
    "ANUA_FEE",
    "MAGI_FEE",
]

FEE_COLUMN_HEAD_HINTS = {
    "ADM_FEE": ("ADM_FEE", "ADMISSION FEE", "ADMISSION / REG FEE"),
    "DEV_FEE": ("DEV_FEE", "DEVELOPMENT FEE"),
    "TUT_FEE": ("TUT_FEE", "TUITION FEE", "PACKAGE FEE"),
    "COM_FEE": ("COM_FEE", "COMPUTER FEE"),
    "LIB_FEE": ("LIB_FEE", "LIBRARY FEE"),
    "CON_FEE": ("CON_FEE", "CONVEYANCE FEE", "TRANSPORT FEE"),
    "SCI_FEE": ("SCI_FEE", "SCIENCE FEE"),
    "ELE_FEE": ("ELE_FEE", "ELECTRICITY FAN"),
    "SPO_FEE": ("SPO_FEE", "SPORT & GAME"),
    "GEN_FEE": ("GEN_FEE", "GENERATOR FEE", "BOARD REGISTRATION FEE", "BOARD FEE"),
    "MED_FEE": ("MED_FEE", "MEDICAL FEE"),
    "EXA_FEE": ("EXA_FEE", "EXAM FEE", "EXAMINATION FEE"),
    "HOS_FEE": ("HOS_FEE", "HOSTEL FEE"),
    "ANU_FEE": ("ANU_FEE", "ANNUAL FEE"),
    "OTH_FEE": ("OTH_FEE", "OTHER FEE"),
    "FIN_FEE": ("FIN_FEE", "FINE"),
    "DUE_FEE": ("DUE_FEE", "OLD DUES FEE", "BALANCE FEE"),
    "BULD_FEE": ("BULD_FEE", "BUILDING FUND"),
    "HAND_FEE": ("HAND_FEE", "HAND BOOK FEE"),
    "LAB_FEE": ("LAB_FEE", "LAB FEE", "PRACTICAL FEE"),
    "NCONS_FEE": ("NCONS_FEE", "NON CONCESSION FEE"),
    "ANUA_FEE": ("ANUA_FEE", "ANNUAL ACTIVITY FEE"),
    "MAGI_FEE": ("MAGI_FEE", "MAGAZINE FEE"),
}


class Command(BaseCommand):
    help = "Incrementally sync current-year receipts exported from old SchoolSOFT StuFee CSV."

    def add_arguments(self, parser):
        parser.add_argument("--stufee-csv", default=DEFAULT_STUFEE_CSV, help="Exported StuFee CSV path.")
        parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="Dry-run/apply report output directory.")
        parser.add_argument("--apply", action="store_true", help="Apply changes after dry-run review.")
        parser.add_argument("--confirm", help="Must be THPSIC when --apply is used.")
        parser.add_argument(
            "--from-rcp",
            type=int,
            help="Override auto watermark. Imports receipts with rcpno greater than this value.",
        )
        parser.add_argument(
            "--backup-out-dir",
            default=r"E:\THPSIC-INTER-COLLEGE\04-backups\daily_backups",
            help="Backup directory used before apply.",
        )

    def handle(self, *args, **options):
        if options["apply"] and options.get("confirm") != "THPSIC":
            raise CommandError("Apply blocked. Use --apply --confirm THPSIC after reviewing dry-run.")

        stufee_path = Path(options["stufee_csv"])
        if not stufee_path.exists():
            raise CommandError(f"StuFee CSV not found: {stufee_path}")

        out_dir = Path(options["out_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        session = AcademicSession.objects.filter(is_active=True).first() or AcademicSession.objects.first()
        if not session:
            raise CommandError("Active academic session not found.")

        auto_watermark = (
            FeeReceipt.objects.filter(carried_forward=False, legacy_receipt_no__isnull=False).aggregate(
                max_rcp=Max("legacy_receipt_no")
            )["max_rcp"]
            or 0
        )
        watermark = options["from_rcp"] if options.get("from_rcp") is not None else auto_watermark

        self.stdout.write(self.style.MIGRATE_HEADING("=== OLD SOFTWARE RECEIPT INCREMENTAL SYNC ==="))
        self.stdout.write(f"Mode: {'APPLY LIVE' if options['apply'] else 'DRY-RUN ONLY'}")
        self.stdout.write(f"CSV: {stufee_path}")
        self.stdout.write(f"Session: {session}")
        self.stdout.write(f"Watermark: import rcpno > {watermark} (auto max={auto_watermark})")

        if options["apply"]:
            call_command("safe_sqlite_backup", out_dir=options["backup_out_dir"], label="before-old-receipt-sync")

        students = {str(s.legacy_sid).strip(): s for s in Student.objects.select_related("current_class", "current_section") if s.legacy_sid}
        existing_by_sid_rcp = set(
            FeeReceipt.objects.filter(legacy_receipt_no__isnull=False)
            .values_list("student__legacy_sid", "legacy_receipt_no")
        )
        existing_by_sid_date_amount = set(
            (
                str(sid).strip(),
                receipt_date.isoformat(),
                self._money_key(amount),
            )
            for sid, receipt_date, amount in FeeReceipt.objects.filter(is_cancelled=False).values_list(
                "student__legacy_sid", "receipt_date", "received_amount"
            )
            if sid and receipt_date
        )
        fee_heads = self._fee_heads()

        preview = []
        exceptions = []
        create_count = skip_count = 0
        total_paid = Decimal("0.00")
        total_concession = Decimal("0.00")

        csv.field_size_limit(2147483647)
        with stufee_path.open("r", encoding="latin-1", errors="replace", newline="") as handle:
            for row in csv.DictReader(handle):
                parsed = self._parse_row(row)
                if not parsed:
                    continue

                if parsed["legacy_receipt_no"] <= watermark:
                    continue

                sid = parsed["legacy_sid"]
                student = students.get(sid)
                if not student:
                    exceptions.append(self._exception(row, parsed, "Student legacy SID not found in SchoolSoft"))
                    continue

                date_amount_key = (sid, parsed["receipt_date"].isoformat(), self._money_key(parsed["paid"]))
                duplicate_reason = ""
                if (int(sid), parsed["legacy_receipt_no"]) in existing_by_sid_rcp:
                    duplicate_reason = "Duplicate legacy receipt number for student"
                elif date_amount_key in existing_by_sid_date_amount:
                    duplicate_reason = "Duplicate student+date+amount"

                if parsed["paid"] == Decimal("0.00"):
                    exceptions.append(
                        self._exception(
                            row,
                            parsed,
                            "ZERO_PAID_DEMAND_NOTE - skipped; no cash collection, print SchoolSoft Due Slip instead",
                        )
                    )
                    continue
                line_items, missing_heads = self._line_items(row, fee_heads)
                billed_total = sum((amount for _, _, amount in line_items), Decimal("0.00"))
                if missing_heads:
                    exceptions.append(
                        self._exception(
                            row,
                            parsed,
                            "Missing fee head mapping: " + "; ".join(missing_heads),
                        )
                    )
                    continue
                receipt_line_items = self._paid_line_items(parsed, line_items)
                line_total = sum((amount for _, _, amount in receipt_line_items), Decimal("0.00"))
                if line_total != parsed["paid"]:
                    exceptions.append(
                        self._exception(
                            row,
                            parsed,
                            f"Receipt line allocation mismatch: paid Rs.{parsed['paid']} vs lines Rs.{line_total}",
                        )
                    )
                    continue
                concession = self._concession_amount(row, billed_total, parsed["net_total"])
                package_review = self._package_review(student, billed_total)

                action = "SKIP" if duplicate_reason else "CREATE"
                if duplicate_reason:
                    skip_count += 1
                else:
                    create_count += 1
                    total_paid += parsed["paid"]
                    total_concession += concession

                before_due, after_due = self._due_preview(student, session, parsed["to_month"], parsed["paid"], concession)
                due_review = self._due_review(parsed["due"], after_due)
                if package_review and not due_review:
                    package_review = ""
                preview.append(
                    {
                        "action": action,
                        "duplicate_reason": duplicate_reason,
                        "old_rcp_no": parsed["legacy_receipt_no"],
                        "legacy_sid": sid,
                        "admission_no": student.admission_no,
                        "student_name": student.full_name,
                        "father_name": student.father_name,
                        "class": student.current_class.name if student.current_class else "",
                        "section": student.current_section.name if student.current_section else "",
                        "receipt_date": parsed["receipt_date"].strftime("%d/%m/%Y"),
                        "from_month": parsed["from_month"],
                        "to_month": parsed["to_month"],
                        "legacy_billed_total": billed_total,
                        "line_total": line_total,
                        "legacy_net_total": parsed["net_total"],
                        "concession_amount": concession,
                        "paid_amount": parsed["paid"],
                        "legacy_due": parsed["due"],
                        "due_before_import": before_due,
                        "estimated_due_after_import": after_due,
                        "due_review": due_review,
                        "package_review": package_review,
                        "missing_fee_heads": "; ".join(missing_heads),
                    }
                )

                if options["apply"] and action == "CREATE":
                    self._create_receipt(
                        student=student,
                        session=session,
                        parsed=parsed,
                        concession=concession,
                        line_items=receipt_line_items,
                    )

        preview_path = out_dir / "OLD_SOFTWARE_RECEIPT_SYNC_PREVIEW.csv"
        exception_path = out_dir / "OLD_SOFTWARE_RECEIPT_SYNC_EXCEPTIONS.csv"
        self._write_csv(preview_path, preview)
        self._write_csv(exception_path, exceptions)

        self.stdout.write(self.style.SUCCESS("Receipt sync summary"))
        self.stdout.write(f"- To create: {create_count}")
        self.stdout.write(f"- Skipped duplicates: {skip_count}")
        self.stdout.write(f"- Exceptions: {len(exceptions)}")
        self.stdout.write(f"- Total paid to import: Rs. {total_paid:,.2f}")
        self.stdout.write(f"- Total concession to import: Rs. {total_concession:,.2f}")
        self.stdout.write(f"- Preview CSV: {preview_path}")
        self.stdout.write(f"- Exceptions CSV: {exception_path}")
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("Dry-run only. Live DB not changed."))

    def _parse_row(self, row):
        rcp = str(row.get("rcpno", "")).strip()
        sid = str(row.get("sid", "")).strip()
        if not rcp.isdigit():
            return None
        if not sid.isdigit():
            return None
        return {
            "legacy_receipt_no": int(rcp),
            "legacy_sid": sid,
            "receipt_date": self._date(row.get("v_date")),
            "paid": self._decimal(row.get("paid")),
            "due": self._decimal(row.get("due")),
            "fee_total": self._decimal(row.get("FEE_TOT")),
            "net_total": self._decimal(row.get("NET_TOT")),
            "from_month": (row.get("FRMONTH") or "").strip(),
            "to_month": (row.get("TOMONTH") or "").strip(),
        }

    def _create_receipt(self, *, student, session, parsed, concession, line_items):
        receipt = FeeReceipt.objects.create(
            legacy_receipt_no=parsed["legacy_receipt_no"],
            receipt_no=f"SF-{parsed['legacy_receipt_no']}",
            student=student,
            session=session,
            student_name_snapshot=student.full_name,
            father_name_snapshot=student.father_name,
            class_snapshot=student.current_class.name if student.current_class else "",
            section_snapshot=student.current_section.name if student.current_section else "",
            receipt_date=parsed["receipt_date"],
            from_month=parsed["from_month"],
            to_month=parsed["to_month"],
            payment_mode=FeeReceipt.PaymentMode.CASH,
            concession_amount=concession,
            late_fee_amount=Decimal("0.00"),
            received_amount=parsed["paid"],
            legacy_fee_total=Decimal("0.00"),
            legacy_net_total=Decimal("0.00"),
            legacy_due_amount=parsed["due"],
            carried_forward=False,
            remarks=f"Old SchoolSOFT incremental receipt #{parsed['legacy_receipt_no']} (CSV sync)",
        )
        for column, head, amount in line_items:
            if amount > 0 and head:
                FeeReceiptLine.objects.create(receipt=receipt, fee_head=head, amount=amount)
        return receipt

    def _fee_heads(self):
        by_key = {}
        for head in FeeHead.objects.filter(is_active=True):
            by_key[self._norm(head.name)] = head
            if head.legacy_column:
                by_key[self._norm(head.legacy_column)] = head
        return by_key

    def _line_items(self, row, fee_heads):
        items = []
        missing = []
        for column in FEE_COLUMNS:
            amount = self._decimal(row.get(column))
            if amount <= 0:
                continue
            head = None
            for hint in FEE_COLUMN_HEAD_HINTS.get(column, (column,)):
                head = fee_heads.get(self._norm(hint))
                if head:
                    break
            if not head:
                missing.append(f"{column}=Rs.{amount}")
            items.append((column, head, amount))
        return items, missing

    def _paid_line_items(self, parsed, line_items):
        remaining = self._money(parsed["paid"])
        if remaining <= 0:
            return []

        # Balance Fee entries are real cash receipts against old balance; keep them
        # under the Balance Fee/Previous Due head when the old CSV identifies one.
        ordered = list(line_items)
        if self._is_balance_fee_month(parsed["from_month"]) or self._is_balance_fee_month(parsed["to_month"]):
            ordered.sort(key=lambda item: 0 if item[0] == "DUE_FEE" else 1)

        allocated = []
        first_head_item = None
        for column, head, billed_amount in ordered:
            if not head or billed_amount <= 0:
                continue
            if first_head_item is None:
                first_head_item = (column, head)
            if remaining <= 0:
                break
            amount = min(self._money(billed_amount), remaining)
            if amount > 0:
                allocated.append((column, head, amount))
                remaining = self._money(remaining - amount)

        if remaining > 0 and first_head_item:
            column, head = first_head_item
            allocated.append((column, head, remaining))
            remaining = Decimal("0.00")

        return allocated

    def _concession_amount(self, row, line_total, net_total):
        by_difference = line_total - net_total
        if by_difference > 0:
            return self._money(by_difference)
        fallback = self._decimal(row.get("CON_TOT")) + self._decimal(row.get("LES_FEE"))
        return self._money(fallback if fallback > 0 else Decimal("0.00"))

    def _package_review(self, student, line_total):
        if not getattr(student, "uses_fee_package", False):
            return ""
        expected = getattr(student, "fee_package_total", Decimal("0.00")) or Decimal("0.00")
        opening = getattr(student, "opening_balance_due", Decimal("0.00")) or Decimal("0.00")
        if expected <= 0:
            expected = Decimal("4500.00")
        expected_total = self._money(expected + opening)
        if line_total > 0 and self._money(line_total) != expected_total:
            return f"PACKAGE_REVIEW: CSV line total Rs.{line_total} vs opening+package Rs.{expected_total}"
        return ""

    def _due_preview(self, student, session, to_month, paid, concession):
        month = self._month_code(to_month) or "AUG"
        try:
            result = calculate_student_due(student=student, session=session, through_month=month)
            before = result.due_amount
            after = max(Decimal("0.00"), self._money(before - paid - concession))
            return before, after
        except Exception as exc:
            return "", f"ERROR: {exc}"

    def _due_review(self, legacy_due, estimated_due):
        if not isinstance(estimated_due, Decimal):
            return f"REVIEW: {estimated_due}"
        difference = self._money(estimated_due - legacy_due)
        if abs(difference) >= Decimal("1.00"):
            return f"DUE_MISMATCH_REVIEW: SchoolSoft after import Rs.{estimated_due} vs old CSV due Rs.{legacy_due}"
        return ""

    def _exception(self, row, parsed, reason):
        return {
            "old_rcp_no": parsed["legacy_receipt_no"] if parsed else row.get("rcpno", ""),
            "legacy_sid": parsed["legacy_sid"] if parsed else row.get("sid", ""),
            "student_name": row.get("sname", ""),
            "receipt_date": row.get("v_date", ""),
            "paid_amount": row.get("paid", ""),
            "reason": reason,
        }

    def _write_csv(self, path, rows):
        if not rows:
            path.write_text("", encoding="utf-8-sig")
            return
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def _date(self, value):
        raw = str(value or "").strip().split(" ")[0]
        for fmt in ("%m/%d/%y", "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        return timezone.localdate()

    def _month_code(self, value):
        raw = str(value or "").strip().upper()
        if raw in ("BALANCE FEE", "MARCH"):
            return "MAR"
        if raw in MONTH_ALIASES:
            return MONTH_ALIASES[raw]
        if raw[:3] in {"APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC", "JAN", "FEB", "MAR"}:
            return raw[:3]
        return ""

    def _is_balance_fee_month(self, value):
        return str(value or "").strip().upper() == "BALANCE FEE"

    def _decimal(self, value):
        try:
            return Decimal(str(value or "0").strip().replace(",", "") or "0")
        except (InvalidOperation, ValueError):
            return Decimal("0.00")

    def _money(self, value):
        return Decimal(value or "0").quantize(Decimal("0.01"))

    def _money_key(self, value):
        return str(self._money(value))

    def _norm(self, value):
        return "".join(ch for ch in str(value or "").upper() if ch.isalnum())
