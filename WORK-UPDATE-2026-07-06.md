# SchoolSoft Work Update - 06 July 2026

This note summarizes the work completed today so another developer/AI/operator can continue safely.

## Current Status

- Project: `D:\english medium\schoolsoft_web`
- Main app: SchoolSoft Django + Windows EXE
- Daily real data entry rule: use Desktop EXE as the primary source of truth.
- Online Render site is for viewing/report backup and should be synced from Desktop when needed.
- Current working tree has uncommitted Accounts module changes. Do not build/release until the pending review items are finished.

## Completed Today

### 1. Desktop-To-Online Sync Script Fixed

File:
- `sync-desktop-to-online.bat`

Problem:
- The sync script failed immediately after pasting the Render PostgreSQL URL because of Windows batch variable expansion inside an `if (...)` block.

Fix:
- Reworked the URL handling so the pasted Render DB URL is read and saved correctly.
- Confirmed the script completed all stages:
  - Desktop DB backup
  - Desktop DB export
  - PostgreSQL driver check
  - Fast batch load to Render
  - Sync complete

Operator note:
- Before running sync, close SchoolSoft EXE.
- Sync replaces online Render DB with Desktop DB data.
- The saved `render-db-url.txt` file must stay local and must not be committed.

### 2. Operator Data Rule Clarified

Decision:
- New admissions, fee receipts, expenses, edits, and cancellations should be entered in Desktop EXE only.
- Online data does not automatically flow back into Desktop.
- When online needs updating, run the sync BAT from Desktop to Render.

Important:
- Old legacy software should no longer be used for new entries.
- Keep old legacy software only for reference until SchoolSoft is fully verified.

### 3. Accounts / Cash Book Phase 1 Started

Goal:
- Add daily expense and cash book workflow similar to old software's AccountMaster / Cash Book.

New/modified functionality:
- Ledger master
- Daily Expense Entry
- Other Receipt Entry
- Voucher Register
- Voucher Detail
- Voucher Edit
- Voucher Cancel with audit reason
- Voucher PDF print
- Cash Book report

Key design decision:
- Cash Book is generated from vouchers and fee receipts without duplicating fee receipt data.
- Expense voucher is single-line for Phase 1:
  - Credit: Cash/Bank account
  - Debit: Expense or Advance head

New accounting models added:
- `AccountGroup`
- `LedgerAccount`
- `VoucherCounter`
- `Voucher`
- `VoucherAuditLog`

New seed command:
- `core/management/commands/seed_accounts.py`

New migration:
- `core/migrations/0013_accounts_phase1.py`

New templates:
- `templates/core/expense_form.html`
- `templates/core/receipt_other_form.html`
- `templates/core/voucher_list.html`
- `templates/core/voucher_detail.html`
- `templates/core/voucher_form.html`
- `templates/core/voucher_cancel_confirm.html`
- `templates/core/cash_book.html`
- `templates/core/ledger_list.html`
- `templates/core/ledger_form.html`
- `templates/core/partials/_form_errors.html`

### 4. Accounts Permissions Added

Files:
- `core/access.py`
- `core/user_admin.py`
- `templates/base.html`

Changes:
- Added accounts access permission path.
- Added Accounts section in sidebar.
- Accounts links include:
  - Daily Expense
  - Other Receipt
  - Voucher Register
  - Cash Book
  - Ledger Master

Important fix:
- New accounts views were initially missing strict permission decorators.
- This was fixed so anonymous or unauthorized users cannot open accounts pages.

### 5. Daily Expense Bugs Fixed During Testing

#### Missing Template Partial

Problem:
- `/accounts/expense/new/` failed with:
  - `TemplateDoesNotExist: core/partials/_form_errors.html`

Fix:
- Created `templates/core/partials/_form_errors.html`.

#### Voucher Number Generation Bug

Problem:
- Saving expense failed with:
  - `AcademicSession object has no attribute start_date`

Cause:
- Code assumed `AcademicSession.start_date`, but the model uses `starts_on`.

Fix:
- Voucher number logic was corrected to use the existing session fields/name.

#### Staff Advance Support

User request:
- Staff Advance entry should show staff names in Paid To, like student selection.

Fix:
- `Staff Advance` and other Advance Given ledgers are now allowed in Daily Expense.
- When `Expense / Advance Head (Debit)` is `Staff Advance`, the `Paid To` field switches to a staff dropdown.
- Staff dropdown is populated from active `Staff.full_name`.
- For normal expenses like Diesel/Electricity, Paid To remains a text box.

Files changed:
- `core/forms.py`
- `core/views.py`
- `templates/core/expense_form.html`

Verification:
- `manage.py check` passed.
- `manage.py test core` passed: 26/26.
- Focused shell validation confirmed Staff Advance voucher form is valid.

### 6. Manual Testing Done

Tested in browser:
- Daily Expense created successfully.
- Voucher numbers generated:
  - Example: `CPMT-2026-27-0001`
  - Example: `CPMT-2026-27-0002`
- Voucher Register listed entries.
- Cash Book showed payments and closing balance.
- Voucher cancellation worked with reason.
- Cancelled voucher PDF showed cancelled watermark.
- Ledger Master page opened.
- Staff Advance dropdown behavior was implemented after the user's latest request.

## Current Known Issues / Pending Work

### 1. UI Polish Still Needed

Accounts pages are functional but still visually plain compared with premium Students/Fees modules.

Pages needing polish:
- Daily Expense
- Voucher Register
- Voucher Detail
- Cash Book
- Ledger Master

Recommendation:
- Do not redesign logic yet.
- First commit functional MVP.
- Then do a separate UI-only polish commit.

### 2. Staff Advance Business Flow Needs Final Decision

Current behavior:
- Staff Advance is a voucher:
  - Debit: Staff Advance
  - Credit: Cash in Hand / Bank
  - Paid To: staff name selected from dropdown

Still pending:
- Whether Staff Advance should be linked to actual Staff ID instead of storing staff name text.

Recommendation:
- Keep Phase 1 as text snapshot for speed and simplicity.
- In Phase 2, add optional `staff` foreign key if staff-wise advance balance is required.

### 3. Opening Balance Needs Final Setup

Current Cash in Hand opening balance appears to be `0.00`.

Pending:
- Decide real opening balance for current session / current date.
- Set it in Ledger Master for `Cash in Hand`.

### 4. Commit / Build Pending

Uncommitted files currently include Accounts module changes and sync script fix.

Before commit:
1. Run `git diff HEAD --stat`.
2. Confirm only expected files changed.
3. Run:
   - `.\.venv\Scripts\python.exe manage.py check`
   - `.\.venv\Scripts\python.exe manage.py test core`
4. Optionally test one more Staff Advance in browser.

Suggested commits:
1. `feat(accounts): add daily expense and cash book phase 1`
2. `fix(sync): repair desktop to online sync URL handling`
3. `docs: add accounts phase 1 handoff update`

After commit:
1. `python manage.py collectstatic --noinput`
2. Close SchoolSoft EXE fully.
3. Run `build-desktop.bat`.
4. Open EXE and verify Accounts pages.

## How To Enter Staff Advance

1. Open `Accounts -> Daily Expense`.
2. Set date and payment mode.
3. `Paid Out From (Credit)`: select `Cash in Hand` or `Bank Account`.
4. `Expense / Advance Head (Debit)`: select `Staff Advance`.
5. `Paid To`: staff dropdown will appear.
6. Select staff name.
7. Enter amount.
8. Narration example: `Staff advance for July`.
9. Save.

Cash Book effect:
- It will show as payment out.
- Closing balance will reduce.

## Important Safety Notes

- Do not use hard delete for real accounting records.
- Use cancel/void with reason for wrong vouchers.
- Sync is one-way: Desktop DB to Online Render DB.
- Do not enter daily data directly online unless a future two-way sync system is built.
- Do not commit local secrets:
  - `render-db-url.txt`
  - database backups
  - sync logs containing credentials

## Suggested Next Step

Recommended next action:
1. Browser-test Staff Advance dropdown once.
2. Commit Accounts MVP and sync fix separately.
3. Rebuild EXE.
4. Give operator a short Hindi guide for daily expense entry.

