# SchoolSoft Project Ã¢â‚¬â€ Full Context Handoff

## Agent Rules (sabse pehle ye padho)
1. **Ek kaam, ek scope** Ã¢â‚¬â€ is file ko padho, phir sirf wahi ek specific task karo jo user ne diya hai; poora project explore mat karo.
2. **Ye file = source of truth** Ã¢â‚¬â€ "Ab tak kya bana hai" aur "Aage kya karna hai" section hamesha sabse taaza status hai. Kaam khatam hone par (user/Claude confirm karne ke baad) ye file khud update kar dena.
3. **Live DB = hard stop** Ã¢â‚¬â€ `%LOCALAPPDATA%\SchoolSoft\db.sqlite3` ko touch karne se pehle: (1) fresh backup lo, (2) plan ek line me batao, (3) user ka "go ahead" aane tak ruko. Kabhi seedha migrate/import mat chalao bina backup/confirmation ke.
4. **Blind trust nahi** Ã¢â‚¬â€ kisi doosre agent (Antigravity/Cursor/etc.) ka kaam khud files/DB se cross-check karo, phir exact numbers/output Claude ko verify karne ke liye do.
5. **Guess mat karo** Ã¢â‚¬â€ file, number, group, ya scope unclear ho to ruk kar poochho, andaza mat lagao.

Reusable task template (user isi se naya kaam dega):
```
@CURSOR_HANDOFF.md ye padho. Ab sirf ye ek kaam karo: [kaam ka naam].
Live database touch karne se pehle backup lo aur mujhe bata kar ruko.
Kaam khatam hone par exact numbers/output dikhao, taaki main Claude ko dikha kar verify karwa sakoon.
```


Ye THPS English Medium School, Dudahi, Kushinagar ka apna school-management software hai (SchoolSoft), Django 6 par bana hua. Do jagah chalta hai: (1) school ke computer par ek Windows EXE (PyInstaller se banaya gaya, SQLite database, ye hi asli/live data hai), aur (2) online ek Render.com website (PostgreSQL database, sirf dekhne ke liye/backup ke liye, desktop se ek-tarafa sync hoti hai Ã¢â‚¬â€ online se kabhi desktop me wapas nahi aati).

## Ab tak kya-kya bana hai:
Student records, marks, fee collection/receipts, transport, staff/salary, TC/certificates, ID cards — ye sab pehle se stable hain. Sabse bada recent kaam ek naya "demand-based due calculation engine" tha — matlab kisi bhi student ka exact bakaya (due) nikalne ka naya, saaf formula (`core/fee_engine.py`), jo purane receipt-based tarike ki jagah leta hai. 

Sabse abhi-abhi (August 2026) complete hua kaam:
1. **Person/Ledger UI:** School ke "personal ledger" accounts (loans, advances, vendor balances) ko `Person` model se link kiya gaya. Iska UI (`/accounts/persons/`) ban chuka hai aur verify ho chuka hai.
2. **Student Search & Fee Status:** Fee collection search me ab bachche ka naam ke saath SID, Class-Section, Admission No, Father Name, Mobile bhi dikhta hai taaki operator confuse na ho. Fee status panel me total due, advance, last receipt wagaira ekdum clear dikh raha hai.
3. **Salary Module Redesign (Clerk-Friendly):** Salary module ko puri tarah redesign kiya gaya hai taaki partial (thoda-thoda) payment multiple times diya ja sake. Clerk ko koi hisaab nahi karna padta, system "Aaj ka Payment" ke liye remaining balance auto-fill karta hai aur status banner (Paid/Remaining) dikhata hai. (✅ Fully tested and verified by User).
4. **Online Sync Timeout Fix:** `fast_load_data.py` ka batch size 100 se 50 kar diya gaya hai aur Render Database par 7000+ receipts successfully sync ho gaye hain (No timeouts!).

## Kaam karne ka tareeka (bahut zaroori):
Main (Claude/Cowork) is project me sirf **read-only verifier** hoon — main file padh sakta hoon, live database ki backup copy padh kar numbers check kar sakta hoon, lekin main khud live database ko chhoo nahi sakta. Tum (naya agent) jo bhi actual code likhoge/migration chalaoge, wo live machine par ho, aur har risky step (schema change, data import, DB write) se pehle: (1) ek fresh backup lo, (2) chhote test/dry-run pe try karo, (3) mujhe result dikhao verify karne ke liye, (4) tabhi aage badho. 

## Aage kya karna hai (Pending Work):
1. **[MEDIUM / PENDING] Old Wrong Receipt Audit:** SAIF RAZA (SID 2179) ki purani wrong receipt `MR-20260728110300` jaise historical/manual wrong receipts ka audit alag se karna hai. Ye engine bug nahi, manual old-entry cleanup hai.
2. **[LOW / PENDING] Dashboard Polish:** Dashboard ka front-design thoda polish karna (KPI cards me trend dikhana, ek chhota collection-chart).
3. **[DONE]** Staff Master Salary Setup & Salary Banner Test: Tests complete, rule established ("Paisa jab haath mein aaye, tab entry").
4. **[DONE]** Online Sync Robustness: Batch size reduced to 50, successfully pushed 7000+ receipts to Render free tier without timeouts.
5. **[DONE]** Render (online) ka DB password rotate karna
6. **[DONE]** Online view par "Last Backup"/"Last Sync" jaise cards hide karna

**Important correction:** Admission Fee engine bug is **DONE**. New fee engine old students par Admission Fee auto-apply nahi karta. Remaining SAIF RAZA case ek purani wrong receipt/manual audit item hai, code engine bug nahi.

**Status as of last update:** Sibling Detection & Month-Range Concession UI (with double-count warning) are fully integrated into the Admission form and Student Profile. All backend month-range limits successfully implemented. Desktop EXE rebuilt (`f401f68..c2f4284`). Next tasks include Old Wrong Receipt Audit or Dashboard Polish.

## Newly Completed Features (Sibling Detection & Concession UI)
1. **Sibling Detection Check**: New admission form auto-suggests existing siblings when Father's Name or Mobile is typed.
2. **Admission Form Concession**: Directly assign concessions (Type, Amount, Month Range) while adding a student. Backend auto-creates a session-bound `StudentConcession`.
3. **Fee Collection Month-Range Logic**: Fee Engine respects `from_month` and `to_month`. Example: Concession JUL-MAR will show no discount in JUN, but deducts correctly in AUG. A green banner displays the active concession.
4. **Double-Count Guard**: If a clerk manually types a concession amount for a student already receiving an automatic policy concession, an amber warning appears to prevent double discounts.

---
**Note for any agent:**
Always take a backup before touching the live database and wait for the verifier's (Claude's) confirmation on numbers. Follow `CURSOR_HANDOFF.md` instructions stringently.



- **Salary entry rule**: Basic Pay = fixed contractual amount. LWP/absent = Other Deduction field. Never change Basic Pay for deductions.
