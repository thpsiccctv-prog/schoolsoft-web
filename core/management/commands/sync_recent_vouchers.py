import csv
from datetime import datetime, date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Staff, SalaryPayment, Voucher, LedgerAccount, AccountGroup, AcademicSession

class Command(BaseCommand):
    help = 'Safely import April 2026+ Vouchers and Salary from LEDGER.csv'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Dry run without saving')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING("Running in DRY-RUN mode. No data will be saved."))

        ledger_csv = r'D:\english medium\migration_audit\exports\LEDGER.csv'
        subgroup_csv = r'D:\english medium\migration_audit\exports\SubGroup.csv'

        # Load SubGroup lookup
        subgroups = {}
        try:
            with open(subgroup_csv, 'r', encoding='utf-8-sig', errors='ignore') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    subgroups[row['SUBCODE']] = {
                        'NAME': row['NAME'].strip(),
                        'CODE': row['CODE'].strip()  # CODE '9' is SALARY
                    }
        except Exception as e:
            self.stderr.write(f"Error loading SubGroup: {e}")
            return

        # Fetch/Create necessary base models
        session = AcademicSession.objects.filter(is_active=True).first()
        if not session and not dry_run:
            session = AcademicSession.objects.create(name="2026-27", starts_on=date(2026, 4, 1), ends_on=date(2027, 3, 31))
            self.stdout.write("Created fallback AcademicSession.")

        expense_group = None
        # Real example from the legacy ledger: "PRAGATI PERSONAL/ADVANCE A/C" - money
        # personally advanced by an individual to cover a school cash shortfall, then
        # repaid later (CPMT "Pragati ka paisa wapas kar diya gya"). This is a LIABILITY
        # (school owes it back), not an EXPENSE - lumping it under "Legacy Expenses"
        # would silently inflate expense totals on any future P&L/expense report even
        # though it has zero effect on the Cash Book itself (which only cares whether a
        # transaction touches the Cash ledger, not how the other side is classified).
        # Any legacy ledger whose name contains one of these words is routed to a
        # dedicated "Legacy Loans & Advances" liability group instead.
        loan_group = None
        LOAN_KEYWORDS = ("PERSONAL/ADVANCE", "PERSONAL ADVANCE", "LOAN", "ADVANCE A/C")
        cash_ledger = None
        if not dry_run:
            expense_group, _ = AccountGroup.objects.get_or_create(
                name="Legacy Expenses",
                defaults={'group_type': AccountGroup.GroupType.EXPENSE}
            )
            loan_group, _ = AccountGroup.objects.get_or_create(
                name="Legacy Loans & Advances",
                defaults={'group_type': AccountGroup.GroupType.LIABILITY}
            )
            from core.views import _get_cash_account
            cash_ledger = _get_cash_account()
            if not cash_ledger:
                cash_ledger, _ = LedgerAccount.objects.get_or_create(
                    name="Cash in Hand",
                    defaults={'group': expense_group, 'is_cash_or_bank': True}
                )

        salary_created = 0
        salary_skipped = 0
        voucher_created = 0
        voucher_skipped = 0
        # Real incident (July 2026): rows whose SUBCODE/CONTRASUB didn't resolve in
        # SubGroup.csv used to vanish silently (a bare `continue`, no log, no counter) -
        # this is exactly how a legitimate transaction (e.g. a one-off "Pragati
        # Personal/Advance" loan ledger that isn't in the standard SubGroup list) can
        # disappear from the Cash Book with zero trace that it was ever seen. Every
        # unresolved row is now counted and logged with enough detail to look it up
        # and fix (in SubGroup.csv, or by hand) on the next run.
        unresolved_skipped = 0
        unresolved_rows = []

        try:
            with open(ledger_csv, 'r', encoding='utf-8-sig', errors='ignore') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    v_date_str = row['V_DATE'].split(' ')[0] # '23/07/2018'
                    try:
                        v_date = datetime.strptime(v_date_str, '%d/%m/%Y').date()
                    except ValueError:
                        continue

                    if v_date < date(2026, 4, 1):
                        continue

                    v_type = row['V_TYPE']
                    if v_type not in ['CPMT', 'CREC']:
                        continue

                    cr_val = row.get('CR', '0')
                    try:
                        amount = Decimal(cr_val)
                    except:
                        amount = Decimal('0')

                    if amount <= 0:
                        continue

                    v_no = row['V_NO']
                    narration = row['NARRATION'].strip()

                    subcode = row['SUBCODE']
                    contrasub = row['CONTRASUB']

                    # Usually in CPMT: SUBCODE is 10001 (Cash) and CONTRASUB is the expense
                    target_subcode = contrasub if subcode == '10001' else subcode
                    target_sub = subgroups.get(target_subcode)

                    if not target_sub:
                        unresolved_skipped += 1
                        unresolved_rows.append(
                            f"  V_NO={v_no} V_TYPE={v_type} DATE={v_date} AMOUNT={amount} "
                            f"SUBCODE={subcode} CONTRASUB={contrasub} (tried={target_subcode}) "
                            f"NARRATION={narration[:80]!r}"
                        )
                        self.stderr.write(self.style.WARNING(
                            f"Unresolved SUBCODE/CONTRASUB '{target_subcode}' for {v_type} {v_no} "
                            f"on {v_date} (Rs {amount}) - '{narration[:60]}' - NOT imported. "
                            f"Add this code to SubGroup.csv or create the ledger by hand."
                        ))
                        continue

                    # If this is a SALARY payment
                    if target_sub['CODE'] == '9':
                        staff_name = target_sub['NAME']
                        staff = Staff.objects.filter(full_name=staff_name).first()
                        if not staff:
                            self.stderr.write(f"Staff not found for salary payment: {staff_name}")
                            salary_skipped += 1
                            continue
                        
                        slip_no = f"LEG-SAL-{v_no}-{row.get('S_NO', '1')}"
                        pay_month = date(v_date.year, v_date.month, 1)

                        if dry_run:
                            if SalaryPayment.objects.filter(staff=staff, pay_month=pay_month, is_cancelled=False).exists():
                                salary_skipped += 1
                            else:
                                salary_created += 1
                        else:
                            salary, created = SalaryPayment.objects.get_or_create(
                                staff=staff,
                                pay_month=pay_month,
                                is_cancelled=False,
                                defaults={
                                    'slip_no': slip_no,
                                    'payment_date': v_date,
                                    'basic_pay': amount,
                                    'remarks': narration[:250],
                                    'payment_mode': SalaryPayment.PaymentMode.CASH
                                }
                            )
                            if created:
                                salary_created += 1
                            else:
                                salary.basic_pay += amount
                                salary.remarks = f"{salary.remarks} | {narration}"[:250]
                                salary.save()
                                salary_skipped += 1

                    # If this is an EXPENSE/RECEIPT voucher
                    else:
                        ledger_name = target_sub['NAME']
                        voucher_no = f"LEG-{v_type}-{v_no}-{row.get('S_NO', '1')}"

                        if dry_run:
                            if Voucher.objects.filter(voucher_no=voucher_no).exists():
                                voucher_skipped += 1
                            else:
                                voucher_created += 1
                        else:
                            ledger_group = (
                                loan_group
                                if any(kw in ledger_name.upper() for kw in LOAN_KEYWORDS)
                                else expense_group
                            )
                            target_ledger, _ = LedgerAccount.objects.get_or_create(
                                name=ledger_name,
                                defaults={'group': ledger_group}
                            )

                            db_v_type = Voucher.VoucherType.CASH_PAYMENT if v_type == 'CPMT' else Voucher.VoucherType.CASH_RECEIPT
                            
                            debit_acc = target_ledger if db_v_type == Voucher.VoucherType.CASH_PAYMENT else cash_ledger
                            credit_acc = cash_ledger if db_v_type == Voucher.VoucherType.CASH_PAYMENT else target_ledger

                            _, created = Voucher.objects.get_or_create(
                                voucher_no=voucher_no,
                                defaults={
                                    'session': session,
                                    'voucher_type': db_v_type,
                                    'voucher_date': v_date,
                                    'debit_account': debit_acc,
                                    'credit_account': credit_acc,
                                    'amount': amount,
                                    'narration': narration,
                                    'payment_mode': Voucher.PaymentMode.CASH
                                }
                            )
                            if created:
                                voucher_created += 1
                            else:
                                voucher_skipped += 1

        except Exception as e:
            self.stderr.write(f"Error processing LEDGER: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"Voucher Sync Summary:\n"
            f"Salary Created: {salary_created}\n"
            f"Salary Skipped (dupes): {salary_skipped}\n"
            f"Voucher Created: {voucher_created}\n"
            f"Voucher Skipped (dupes): {voucher_skipped}\n"
            f"Unresolved (SUBCODE/CONTRASUB not found - NOT imported at all): {unresolved_skipped}\n"
            f"{'(DRY RUN - no data saved)' if dry_run else '(Data saved to database)'}"
        ))
        if unresolved_rows:
            self.stdout.write(self.style.WARNING(
                f"\n{unresolved_skipped} row(s) could not be matched to any ledger and were "
                f"skipped entirely - these transactions are MISSING from the Cash Book until "
                f"fixed. Details:"
            ))
            for line in unresolved_rows:
                self.stdout.write(line)
