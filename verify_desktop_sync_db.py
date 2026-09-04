import os
import sqlite3
import sys
from decimal import Decimal


def main():
    db_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH")
    if not db_path:
        print("ERROR: SCHOOLSOFT_SQLITE_PATH missing.")
        return 1
    if not os.path.exists(db_path):
        print(f"ERROR: Desktop DB not found: {db_path}")
        return 1

    conn = sqlite3.connect(db_path)

    def one(sql):
        return conn.execute(sql).fetchone()[0]

    problems = []
    students = one("select count(*) from core_student")
    receipts = one("select count(*) from core_feereceipt")
    fee = Decimal(str(one(
        "select coalesce(sum(received_amount),0) from core_feereceipt "
        "where receipt_date >= '2026-06-01' and receipt_date <= '2026-07-12' "
        "and is_cancelled=0"
    )))
    vouchers = one(
        "select count(*) from core_voucher "
        "where voucher_date >= '2026-06-01' and voucher_date <= '2026-07-12' "
        "and is_cancelled=0"
    )
    salaries = one(
        "select count(*) from core_salarypayment "
        "where payment_date >= '2026-06-01' and payment_date <= '2026-07-12' "
        "and is_cancelled=0"
    )
    ob, ob_date = conn.execute(
        "select opening_balance, opening_balance_date from core_ledgeraccount "
        "where name='Cash in Hand'"
    ).fetchone()
    ob = Decimal(str(ob))
    cash_id = one("select id from core_ledgeraccount where name='Cash in Hand'")

    fr = Decimal(str(one(
        "select coalesce(sum(received_amount),0) from core_feereceipt "
        "where receipt_date >= '2026-06-01' and receipt_date <= '2026-07-12' "
        "and is_cancelled=0 and payment_mode='cash'"
    )))
    vin = Decimal(str(one(
        "select coalesce(sum(amount),0) from core_voucher "
        "where voucher_date >= '2026-06-01' and voucher_date <= '2026-07-12' "
        f"and is_cancelled=0 and debit_account_id={cash_id}"
    )))
    vout = Decimal(str(one(
        "select coalesce(sum(amount),0) from core_voucher "
        "where voucher_date >= '2026-06-01' and voucher_date <= '2026-07-12' "
        f"and is_cancelled=0 and credit_account_id={cash_id}"
    )))
    salary_out = Decimal(str(one(
        "select coalesce(sum("
        "basic_pay + da + other_allowances - pf_deduction - esi_deduction "
        "- other_deduction - advance_recovery"
        "),0) from core_salarypayment "
        "where payment_date >= '2026-06-01' and payment_date <= '2026-07-12' "
        "and is_cancelled=0 and payment_mode='cash'"
    )))
    closing = ob + fr + vin - vout - salary_out

    classes = one("select count(*) from core_schoolclass")

    print("Desktop DB safety snapshot:")
    print(f"  Students: {students}")
    print(f"  Fee receipts: {receipts}")
    print(f"  School Classes: {classes}")
    print(f"  Cash opening: {ob} @ {ob_date}")

    if students < 1600:
        problems.append(f"students below 1600 (found {students})")
    if receipts < 720:
        problems.append(f"fee receipts below 720 (found {receipts})")
    if classes != 13:
        problems.append(f"classes expected 13, found {classes}")

    if problems:
        print("")
        print("SAFETY CHECK FAILED:")
        for problem in problems:
            print(f"  - {problem}")
        print("")
        print("Online sync blocked. Verify Desktop DB before syncing.")
        return 1

    print("Safety check OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
