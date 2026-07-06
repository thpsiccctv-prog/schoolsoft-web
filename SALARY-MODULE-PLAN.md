# Phase 2: Salary Module Implementation Plan (Revised)

Based on management feedback, we will abandon the 2-voucher approach. Instead, we will use a **SalaryPayment-first** design. The `SalaryPayment` model will be the single source of truth for payroll, and the Cash Book will read directly from it to show clean, net outflow lines.

## Goal
To build a dedicated, transparent Salary Management system that:
1. Uses `SalaryPayment` as the core record (Gross, Deductions, Advance Recovery, Net Paid).
2. Integrates directly into the Cash Book showing a single, clear "Net Paid" line.
3. Automatically tracks Staff Advances correctly (Given via Voucher - Recovered via Salary).
4. Ensures only staff belonging to the current session appear in dropdowns.

## Proposed Changes

### 1. Staff Session Filtering (Global Fix)
Currently, old inactive staff show up in the dropdowns. 
- **Fix:** In `core/forms.py` (for `VoucherForm` Staff Advance) and the new Salary forms, we will filter the `Staff` queryset: `is_active=True` AND `(date_of_leaving__isnull=True OR date_of_leaving >= current_session.starts_on)`.

### 2. Models & Database (`core/models.py`)
- **`SalaryPayment` Model Updates:**
  - Add `advance_recovery = models.DecimalField(default=0.00)` to strictly track recoveries.
  - Link to `AcademicSession` (to lock salaries to the active session).
  - Add `is_cancelled = models.BooleanField(default=False)` and audit fields (`cancel_reason`, `cancelled_by`, `cancelled_at`).
  - Update `total_deductions` and `net_pay` properties to include `advance_recovery`.

### 3. Views & Forms (`core/views.py`, `core/forms.py`)
- **`salary_generate` View:**
  - **Form:** Select Month (e.g. July 2026) and Staff (filtered by session).
  - Auto-fill basic pay, DA, allowances from `Staff` master.
  - Auto-calculate pending Staff Advance: `(Total Given in Vouchers) - (Total Recovered in SalaryPayments)`.
  - Calculate `net_payable = gross - deductions - advance_recovery`.
  - Save creates the `SalaryPayment` record (No auto-vouchers generated).
- **Cash Book Integration (`core/views.py -> cash_book`):**
  - Modify the Cash Book query to `UNION` `SalaryPayment` records along with Vouchers and Fee Receipts.
  - Cash Book will display: `Particulars: Salary - {Staff Name}`, `Amount Out: {net_pay}`.
- **Salary Register & Reports:**
  - Month-wise paid/unpaid list. Blocks duplicate generation for the same month/staff combo.
  - Dedicated "Staff Advance Ledger" report (calculated dynamically).

### 4. Templates (`templates/core/`)
- `[NEW]` `salary_generate.html`: Form to generate and save salary.
- `[NEW]` `salary_list.html`: Month-wise salary register with View/Print/Cancel buttons.
- `[NEW]` `salary_pdf.html`: Professional printable Salary Slip.
- `[NEW]` `report_staff_advance.html`: Report showing advance given vs recovered per staff.

## Verification Plan
- **Cash Book Accuracy:** Generate a salary with Rs. 10k gross, Rs. 2k recovery. Verify Cash Book only shows Rs. 8k outflow.
- **Staff Filter:** Verify old/left teachers do not appear in the Staff Advance or Salary generation dropdowns.
- **Advance Ledger:** Verify the Staff Advance report correctly shows zero balance after recovery.
