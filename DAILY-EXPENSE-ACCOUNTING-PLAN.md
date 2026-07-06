# SchoolSoft Daily Expense & Cash Book Plan

Date: 05 July 2026

## Current Finding

Daily expense entry is not yet available in the modern Django SchoolSoft app.

The current app has:
- Fee receipts and fee reports.
- Salary payments.
- Receipt edit/cancel audit workflows.
- Smart active-session filters.

The current app does not yet have:
- Voucher Entry.
- Ledger Master.
- Daily Expense Entry.
- Cash Book / Bank Book generated from accounting vouchers.
- Trial Balance / General Ledger reports.

In the old SchoolSOFT Access software, daily expense was handled from:
- `AccountMaster -> Voucher Entry`
- `AccountMaster -> Ledger Creation Master`
- `Report -> Cash Book`
- `Report -> Ledger / General Ledger / Trial Balance / Bank Book`

## Legacy Access Tables Found

The Access schema contains accounting tables that were not included in the first yearly export/import.

Important legacy tables:
- `MGROUP` - account group master.
- `SUBGROUP` - ledger/account master.
- `MLEDGER` - voucher master/header.
- `LEDGER` - voucher ledger lines.
- `VIEWLEDGER` - reporting view/table for debit/credit.
- `CMASTER` - cash balance/day summary fields.
- `t_cashbook` - temporary/report cash book layout.
- `PROC_LED` - processed ledger/report helper.

The first yearly export script only exported student/fee/marks/staff/transport tables, so old account/voucher data has not yet been imported into Django.

## Important Operating Rule

Daily real entry must continue in the new Desktop EXE only.

Do not enter new work in:
- Old SchoolSOFT Access software.
- Online Render website.
- Django admin, unless specifically instructed.

Why:
- Desktop EXE is the master database.
- Online Render is only a mirror/reporting copy updated by sync.
- Old Access software is now legacy/reference only.

## Recommended New Module

Build a new module named:

`Accounts / Cash Book`

This module should be useful for school daily work, not overly complex like full corporate accounting on day one.

## Phase 0 - Read-Only Accounting Audit

Before changing Django data, export accounting tables from Access folders `1` to `9`.

Rules:
- Use only direct folders `D:\english medium\1` to `D:\english medium\9`.
- Each folder has `SCHOOL7.mdb`.
- Ignore subfolders.
- Do not modify old Access files.

Export these tables for each session:
- `MGROUP`
- `SUBGROUP`
- `MLEDGER`
- `LEDGER`
- `VIEWLEDGER`
- `CMASTER`
- `t_cashbook`
- `PROC_LED`

Save output to:

`D:\english medium\migration_audit\yearly_accounting_exports\<session>\`

Generate an audit report with:
- Ledger count per year.
- Voucher count per year.
- Cash receipt total per year.
- Cash payment total per year.
- Date range per year.
- Top expense ledgers, such as diesel, electricity, sweeper, driver salary, repair, stationery.
- Voucher number collision report.
- Closing cash balance check if possible.

No Django import should happen until this audit is reviewed.

## Phase 1 - MVP For Daily Expense Entry

Build only the daily-use accounting features first.

### Models

Suggested Django models:

1. `AccountGroup`
   - name
   - nature: asset / liability / income / expense
   - legacy_code
   - is_active

2. `LedgerAccount`
   - name
   - group
   - account_type: cash / bank / income / expense / advance / salary / transport / other
   - opening_balance
   - legacy_subcode
   - is_active

3. `Voucher`
   - voucher_no
   - voucher_type: payment / receipt / contra / journal
   - voucher_date
   - session
   - payment_mode: cash / bank / cheque / online / other
   - narration
   - total_amount
   - is_cancelled
   - cancel_reason, cancelled_by, cancelled_at
   - is_edited
   - edit_reason, edited_by, edited_at, edit_count
   - created_by

4. `VoucherLine`
   - voucher
   - ledger
   - debit
   - credit
   - description

5. `VoucherAuditLog`
   - voucher
   - action: created / edited / cancelled
   - reason
   - before_snapshot JSON
   - after_snapshot JSON
   - changed_by
   - changed_at

### Screens

1. Daily Expense Entry
   - Date
   - Paid from: Cash in Hand / Bank
   - Expense head: Diesel, Electricity, Repair, Stationery, Sweeper, Driver, etc.
   - Amount
   - Narration
   - Save & Print Voucher

2. Ledger Master
   - Add/edit expense heads.
   - Keep common ledgers pre-created.

3. Voucher Register
   - Search by date, ledger, voucher no, amount.
   - Show badges for edited/cancelled.
   - No hard delete.

4. Cash Book
   - Date-wise receipts on left, payments on right, closing balance at bottom.
   - Same practical style as old software, but modern UI.

5. Bank Book
   - Same report, filtered to bank ledgers.

## Phase 2 - Automatic Integration

After MVP is stable:

1. Fee receipts should automatically appear in Cash Book receipt side.
   - Do not make the operator enter fee receipt again as account receipt.
   - FeeReceipt remains the source record.

2. Salary payments should appear in payment side.
   - SalaryPayment remains the source record.

3. Daily expense vouchers handle non-fee, non-salary expenses:
   - Diesel
   - Electric bill
   - Sweeper
   - Driver payment
   - Repair
   - Stationery
   - Advance paid/received
   - Bank deposit/withdrawal

## Phase 3 - Legacy Accounting Import

Only after Phase 0 audit is approved:

1. Import legacy account groups and ledgers.
2. Import historical vouchers session-wise.
3. Preserve old voucher numbers with session prefix if needed.
4. Verify old Cash Book totals year by year.
5. Keep imported historical entries read-only or audit-protected.

## Phase 4 - Reports For School Use

Priority reports:

1. Cash Book
   - Daily receipt/payment with closing balance.

2. Expense Register
   - All expenses by date range.

3. Head-wise Expense Summary
   - Diesel total, Electricity total, Salary total, Repair total, etc.

4. Ledger Report
   - One account head full detail.

5. Cash/Bank Summary
   - Opening, receipts, payments, closing.

6. Monthly Income vs Expense
   - Fee collection, other receipt, expenses, balance.

Later reports:
- General Ledger.
- Trial Balance.
- Journal Book.
- Debit/Credit Note.

## Permissions

Recommended permissions:

- Admin: full access.
- Accounts user: create/edit/cancel vouchers, print reports.
- Viewer: view/print only.
- Fee clerk: fee receipts only, no daily expenses unless explicitly given.

Every correction must require a reason.
Every cancellation must require a reason.
No hard delete in normal UI.

## Sync Rules

Desktop EXE remains the master.

When daily expense module is added:
- Expense entries will save in Desktop DB.
- Online Render will be updated using `sync-desktop-to-online.bat`.
- Operator should close SchoolSoft EXE before sync.
- Online website should not be used for daily expense entry.

## Immediate Next Step

Do not build UI first.

First create a read-only accounting export/audit command for folders `1` to `9`, then review:
- Which ledgers exist.
- Which voucher types exist.
- Whether old cash book totals can be reproduced.

After audit approval, build the MVP Daily Expense Entry + Cash Book.
