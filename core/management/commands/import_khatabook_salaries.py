import os
import csv
from decimal import Decimal
from datetime import date
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Staff, SalaryPayment, SalaryPaymentAuditLog, AcademicSession

class Command(BaseCommand):
    help = "Bulk import Khatabook verified salary payments for April, May, July 2026"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Apply changes to the live database")
        parser.add_argument("--confirm", type=str, help="Confirmation keyword THPSIC")

    def handle(self, *args, **options):
        apply_mode = options.get("apply")
        confirm = options.get("confirm")

        salary_schedule = [
            # ASHOK SINGH (Code 14)
            {"code": 14, "month": date(2026, 4, 1), "date": date(2026, 7, 2), "amount": Decimal("16000.00"), "basic": Decimal("15000.00"), "allowances": Decimal("1000.00"), "remarks": "Salary of April + CL 1000"},
            {"code": 14, "month": date(2026, 5, 1), "date": date(2026, 7, 2), "amount": Decimal("16000.00"), "basic": Decimal("15000.00"), "allowances": Decimal("1000.00"), "remarks": "Salary of May + CL 1000"},
            {"code": 14, "month": date(2026, 7, 1), "date": date(2026, 8, 17), "amount": Decimal("16000.00"), "basic": Decimal("15000.00"), "allowances": Decimal("1000.00"), "remarks": "Salary of July + CL 1000"},
            
            # KM ANURADHA SINGH (Code 16)
            {"code": 16, "month": date(2026, 4, 1), "date": date(2026, 8, 17), "amount": Decimal("8000.00"), "basic": Decimal("8000.00"), "allowances": Decimal("0.00"), "remarks": "Salary of April"},
            {"code": 16, "month": date(2026, 5, 1), "date": date(2026, 8, 17), "amount": Decimal("8000.00"), "basic": Decimal("8000.00"), "allowances": Decimal("0.00"), "remarks": "Salary of May"},
            {"code": 16, "month": date(2026, 7, 1), "date": date(2026, 8, 17), "amount": Decimal("8000.00"), "basic": Decimal("8000.00"), "allowances": Decimal("0.00"), "remarks": "Salary of July"},
            
            # HARIKESH YADAV (Code 12)
            {"code": 12, "month": date(2026, 4, 1), "date": date(2026, 7, 2), "amount": Decimal("15467.00"), "basic": Decimal("15467.00"), "allowances": Decimal("0.00"), "remarks": "Salary of April"},
            {"code": 12, "month": date(2026, 5, 1), "date": date(2026, 7, 2), "amount": Decimal("16533.00"), "basic": Decimal("16000.00"), "allowances": Decimal("533.00"), "remarks": "Salary of May"},
            {"code": 12, "month": date(2026, 7, 1), "date": date(2026, 8, 17), "amount": Decimal("14934.00"), "basic": Decimal("14934.00"), "allowances": Decimal("0.00"), "remarks": "Salary of July"},
            
            # JAIPRAKASH PRAJAPATI (Code 11)
            {"code": 11, "month": date(2026, 7, 1), "date": date(2026, 8, 17), "amount": Decimal("15500.00"), "basic": Decimal("15000.00"), "allowances": Decimal("500.00"), "remarks": "Salary of July + 500 CL bonus"},
            
            # MANOJ KUMAR (Code 17)
            {"code": 17, "month": date(2026, 4, 1), "date": date(2026, 7, 2), "amount": Decimal("4000.00"), "basic": Decimal("4000.00"), "allowances": Decimal("0.00"), "remarks": "Salary of April"},
            {"code": 17, "month": date(2026, 5, 1), "date": date(2026, 7, 2), "amount": Decimal("4000.00"), "basic": Decimal("4000.00"), "allowances": Decimal("0.00"), "remarks": "Salary of May"},
            {"code": 17, "month": date(2026, 7, 1), "date": date(2026, 8, 17), "amount": Decimal("4000.00"), "basic": Decimal("4000.00"), "allowances": Decimal("0.00"), "remarks": "Salary of July"},
            
            # SARITA (Code 18)
            {"code": 18, "month": date(2026, 4, 1), "date": date(2026, 4, 22), "amount": Decimal("4000.00"), "basic": Decimal("4000.00"), "allowances": Decimal("0.00"), "remarks": "Salary of April"},
            {"code": 18, "month": date(2026, 5, 1), "date": date(2026, 5, 27), "amount": Decimal("4000.00"), "basic": Decimal("4000.00"), "allowances": Decimal("0.00"), "remarks": "Salary of May"},
            {"code": 18, "month": date(2026, 7, 1), "date": date(2026, 7, 23), "amount": Decimal("4000.00"), "basic": Decimal("4000.00"), "allowances": Decimal("0.00"), "remarks": "Salary of July"},
            
            # SATYNARAYAN SINGH (Code 13)
            {"code": 13, "month": date(2026, 7, 1), "date": date(2026, 8, 17), "amount": Decimal("5000.00"), "basic": Decimal("5000.00"), "allowances": Decimal("0.00"), "remarks": "Salary of July"},
            
            # VINOD YADAV (Code 19)
            {"code": 19, "month": date(2026, 4, 1), "date": date(2026, 7, 2), "amount": Decimal("17400.00"), "basic": Decimal("17400.00"), "allowances": Decimal("0.00"), "remarks": "Salary of April"},
            {"code": 19, "month": date(2026, 5, 1), "date": date(2026, 7, 2), "amount": Decimal("19200.00"), "basic": Decimal("18000.00"), "allowances": Decimal("1200.00"), "remarks": "Salary of May"},
            {"code": 19, "month": date(2026, 7, 1), "date": date(2026, 8, 17), "amount": Decimal("18000.00"), "basic": Decimal("18000.00"), "allowances": Decimal("0.00"), "remarks": "Salary of July"},
        ]

        def get_next_slip_no(sequence_number):
            return f"SAL-2026-{sequence_number:04d}"

        if apply_mode and confirm == "THPSIC":
            with transaction.atomic():
                created_count = 0
                total_amt = Decimal("0.00")
                next_sequence = SalaryPayment.objects.count() + 1
                for entry in salary_schedule:
                    staff = Staff.objects.filter(legacy_emp_code=entry["code"], is_active=True).first()
                    if not staff:
                        self.stdout.write(self.style.ERROR(f"Staff code {entry['code']} not found!"))
                        continue

                    # Check if already exists
                    existing = SalaryPayment.objects.filter(staff=staff, pay_month=entry["month"], is_cancelled=False).first()
                    if existing:
                        self.stdout.write(self.style.WARNING(f"Payment already exists for {staff.full_name} for {entry['month']} (Slip: {existing.slip_no})"))
                        continue

                    slip_no = get_next_slip_no(next_sequence)
                    payment = SalaryPayment.objects.create(
                        slip_no=slip_no,
                        staff=staff,
                        pay_month=entry["month"],
                        payment_date=entry["date"],
                        payment_mode=SalaryPayment.PaymentMode.CASH,
                        basic_pay=entry["basic"],
                        da=Decimal("0.00"),
                        other_allowances=entry["allowances"],
                        pf_deduction=Decimal("0.00"),
                        esi_deduction=Decimal("0.00"),
                        other_deduction=Decimal("0.00"),
                        advance_recovery=Decimal("0.00"),
                        amount_paid=entry["amount"],
                        remarks=entry["remarks"],
                    )
                    next_sequence += 1
                    SalaryPaymentAuditLog.objects.create(
                        payment=payment,
                        action=SalaryPaymentAuditLog.ActionChoices.CREATED,
                        reason="Khatabook verified statement import (April-July 2026)"
                    )
                    created_count += 1
                    total_amt += entry["amount"]

            self.stdout.write(self.style.SUCCESS(
                f"\n[SUCCESS] Successfully imported {created_count} salary payments into live DB!\n"
                f"  Total Amount Disbursed: Rs. {total_amt:,.2f}"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"\n[DRY RUN] Would import {len(salary_schedule)} salary payment vouchers (Total: Rs. {sum(e['amount'] for e in salary_schedule):,.2f}).\n"
                f"Pass '--apply --confirm THPSIC' to execute on live database."
            ))
