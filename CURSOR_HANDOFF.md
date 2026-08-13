# SchoolSoft Project — Full Context Handoff

## Agent Rules (sabse pehle ye padho)
1. **Ek kaam, ek scope** — is file ko padho, phir sirf wahi ek specific task karo jo user ne diya hai; poora project explore mat karo.
2. **Ye file = source of truth** — "Ab tak kya bana hai" aur "Aage kya karna hai" section hamesha sabse taaza status hai. Kaam khatam hone par (user/Claude confirm karne ke baad) ye file khud update kar dena.
3. **Live DB = hard stop** — `%LOCALAPPDATA%\SchoolSoft\db.sqlite3` ko touch karne se pehle: (1) fresh backup lo, (2) plan ek line me batao, (3) user ka "go ahead" aane tak ruko. Kabhi seedha migrate/import mat chalao bina backup/confirmation ke.
4. **Blind trust nahi** — kisi doosre agent (Antigravity/Cursor/etc.) ka kaam khud files/DB se cross-check karo, phir exact numbers/output Claude ko verify karne ke liye do.
5. **Guess mat karo** — file, number, group, ya scope unclear ho to ruk kar poochho, andaza mat lagao.

Reusable task template (user isi se naya kaam dega):
```
@CURSOR_HANDOFF.md ye padho. Ab sirf ye ek kaam karo: [kaam ka naam].
Live database touch karne se pehle backup lo aur mujhe bata kar ruko.
Kaam khatam hone par exact numbers/output dikhao, taaki main Claude ko dikha kar verify karwa sakoon.
```

---

## Project Overview

THPS English Medium School, Dudahi, Kushinagar ka apna school-management software (SchoolSoft), Django 6 par bana hua. Do jagah chalta hai:
1. **School ke computer par Windows EXE** (PyInstaller se banaya gaya, SQLite database — ye hi asli/live data hai)
2. **Online Render.com website** (PostgreSQL database, sirf dekhne ke liye/backup ke liye, desktop se ek-tarafa sync hoti hai — online se kabhi desktop mein wapas nahi aati)

---

## Ab tak kya-kya bana hai

### Core Modules (Stable)
Student records, marks, fee collection/receipts, transport, staff/salary, TC/certificates, ID cards — ye sab pehle se stable hain.

### Fee Engine (`core/fee_engine.py`)
Demand-based due calculation engine — kisi bhi student ka exact bakaya (due) nikalne ka formula, jo purane receipt-based tarike ki jagah leta hai.

### Recent Work (August 2026 — is session mein complete hua)

#### 1. Premium ID Cards (Student + Staff)
- Canvas-based ReportLab design — deep teal + gold theme
- Student card: circular photo (PIL crop), blood group badge, QR
- Staff card: designation, emp code, QR
- QR privacy: sirf name/class/code — no phone/address
- Files: `core/pdf.py` (`_StudentIDCardPremium`, `_StaffIDCardPremium`)
- URLs: `staff/<pk>/id-card/pdf/`, `staff/id-cards/pdf/`
- School website: `thpsic.com`

#### 2. Voucher Edit Bug Fix
- **Bug:** `TypeError: Object of type date is not JSON serializable` — `VoucherAuditLog` JSONField crash
- **Fix:** `_json_safe()` helper using `DjangoJSONEncoder` in `voucher_edit` view
- Commit: `d49a975`

#### 3. StudentConcession Feature (Complete)
Full fee concession/waiver system with month-range support.

**Model** (`core/models.py` — `StudentConcession`):
- Fields: `student`, `session`, `concession_type`, `amount_type`, `amount`
- Month range: `from_month`, `to_month` (APR-MAR choices, blank = full session)
- `is_active`, `reason`, `approved_by_name`, `created_by`
- `months_in_range(target_index)` — counts applicable months for fee engine
- `get_monthly_discount_amount(monthly_fee)` — per-month discount
- `clean()` — validates: no percent for one_time/full_free, from <= to, inactive student can't have active concession
- Signal: `deactivate_concession_on_leave` — auto-deactivates when student leaves

**Concession types:**
| Type | Behaviour |
|------|-----------|
| `monthly_waiver` | Per-month × months in range |
| `sibling_discount` | Same as monthly_waiver |
| `one_time` | Fixed amount deducted once (no multiplication) |
| `full_free` | Entire session demand waived |

**Fee Engine** (`core/fee_engine.py` — `calculate_student_due`):
- `policy_concession_amount` field in `DueResult`
- Monthly waiver: `per_month_discount × months_in_range(target_index)`
- One-time: fixed `concession.amount` regardless of through_month
- Full_free: waives `scheduled_fee_demand + transport_demand`

**Migrations:**
- `0034_studentconcession` — initial model
- `0035_studentconcession_month_range` — adds from_month, to_month
- `0036_fix_amount_validator_drift` — restores MinValueValidator (drift fix)
- All 3 applied on production DB ✓

**UI:**
- Admission form (`student_form.html`): concession section with sibling detection panel + prefill on edit
- `student_update` view: passes `existing_concession` to template context
- `_handle_student_concession()`: handles full_free (amount=None, amount_type='full') correctly, saves to `approved_by_name` field
- Receipt form (`receipt_form.html`, `receipt_edit.html`): green banner when policy concession active
- `receipt-form.js`: amber double-count warning when manual concession entered + policy concession active
- `student_fee_defaults` API: returns `active_concession` JSON (type, amount, month_range, reason, approved_by)

**Admin:** `StudentConcessionAdmin` registered in `core/admin.py`

**Tests:** `core/test_concession.py` — 23 tests
- `MonthsInRangeTests` (7 tests, no DB)
- `MonthlyWaiverFeeEngineTests` (4 tests)
- `OneTimeConcessionTests` (1 test)
- `InactiveConcessionTests` (1 test)
- `FullFreeConcessionTests` (1 test)
- `ConcessionModelCleanTests` (5 tests)
- `StudentFeeDefaultsApiConcessionTests` (3 tests)

**Git commits (concession feature):**
```
bba7cfb  Implement automated StudentConcession system
fe79def  Fix Student concession signal using is_active
f401f68  Implement month-ranged student concessions safely
c2f4284  feat: Concession UI + month-range backend + double-count guard
3300aed  fix: restore MinValueValidator on StudentConcession.amount
```

#### 4. Sibling Detection
- New endpoint: `check_siblings` — matches on mobile or father name
- Admission form shows existing siblings in a blue info panel
- Suggests concession assignment if siblings found

#### 5. Dashboard KPI Cards
- `core/views.py` `dashboard()` — added: "Today's Collection" (with trend vs prev collection day), "This Month Collection", "Receipts Issued Today"
- Existing cards (Active Students, Total Due) untouched
- Commit: `3d583ea`

#### 6. Family Ledger — Concession Shortcut
- `templates/core/family_detail.html` — "Actions" column header + "Add Concession" button per sibling row
- Links to `{% url 'core:student_update' row.student.pk %}#concession-section`
- Wrapped in `{% if not is_readonly %}` — readonly users se hidden
- Commit: `3d583ea`

#### 7. Handoff Doc + Cleanup
- Stray temp files deleted: `append_model.py`, `update_*.py`
- `build-desktop.bat` `--clean` flag restored
- `CURSOR_HANDOFF.md` updated

---

## Current Git Status (as of Aug 13, 2026)

```
Latest commit: 3d583ea  feat: dashboard KPI cards + family ledger concession shortcut
Branch: main
Remote: github.com/thpsicdudahi-jk1/schoolsoft-web ✓ pushed
EXE: dist\SchoolSoft\SchoolSoft.exe (prev build — rebuild needed after dashboard change)
Production DB: all 36 migrations applied ✓
Tests: 23/23 pass (core.test_concession) ✓
System check: no issues ✓
```

---

## Aage kya karna hai (Pending Work)

| Priority | Task | Notes |
|----------|------|-------|
| HIGH | Manual UI test — Concession feature | 4 tests: admission save, fee banner, month range deduction, double-count warning |
| MEDIUM | Old Wrong Receipt Audit | SAIF RAZA (SID 2179) `MR-20260728110300` — manual cleanup, not engine bug |
| MEDIUM | NEELU MISS salary Jan/Feb 2026 | Entry karo jab cash mile |
| MEDIUM | SATYAM remaining ₹7,000 May 2026 | Entry karo jab cash mile |
| LOW | EXE rebuild | `build-desktop.bat` chalao — dashboard + family_detail changes include karne ke liye |
| LOW | Online sync batch size | Already 50, monitor if needed |

---

## Technical Reference

### Key Files
| File | Purpose |
|------|---------|
| `core/models.py` | All models incl. `StudentConcession` (line ~1396) |
| `core/fee_engine.py` | `calculate_student_due()`, `DueResult` dataclass |
| `core/pdf.py` | ID cards, receipts, TC PDFs |
| `core/views.py` | All views incl. `_handle_student_concession()`, `student_fee_defaults()` |
| `core/test_concession.py` | 23 concession tests |
| `static/core/receipt-form.js` | Fee collection JS — banner + double-count warning |
| `templates/core/student_form.html` | Admission form + concession section |
| `templates/core/receipt_form.html` | Fee collection form |

### ACADEMIC_MONTHS order
```python
("APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC","JAN","FEB","MAR")
# index: 0      1     2     3     4     5     6     7     8     9    10    11
```

### Concession Math Example
- Monthly waiver ₹500, range JUL–MAR, through AUG:
  - `months_in_range(4)` = JUL(3)+AUG(4) = 2 months
  - `policy_concession_amount` = ₹500 × 2 = ₹1,000

### Salary Rule
Basic Pay = fixed contractual amount. LWP/absent = Other Deduction field. Never change Basic Pay for deductions.

### DB Paths
- Production (live): `%LOCALAPPDATA%\SchoolSoft\db.sqlite3`
- Seed (EXE build): `<project_root>\db.seed.sqlite3`
- Online (read-only): Render PostgreSQL
