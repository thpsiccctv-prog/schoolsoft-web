# SchoolSoft Project â€” Full Context Handoff

## Agent Rules (sabse pehle ye padho)
1. **Ek kaam, ek scope** â€” is file ko padho, phir sirf wahi ek specific task karo jo user ne diya hai; poora project explore mat karo.
2. **Ye file = source of truth** â€” "Ab tak kya bana hai" aur "Aage kya karna hai" section hamesha sabse taaza status hai. Kaam khatam hone par (user/Claude confirm karne ke baad) ye file khud update kar dena.
3. **Live DB = hard stop** â€” `%LOCALAPPDATA%\SchoolSoft\db.sqlite3` ko touch karne se pehle: (1) fresh backup lo, (2) plan ek line me batao, (3) user ka "go ahead" aane tak ruko. Kabhi seedha migrate/import mat chalao bina backup/confirmation ke.
4. **Blind trust nahi** â€” kisi doosre agent (Antigravity/Cursor/etc.) ka kaam khud files/DB se cross-check karo, phir exact numbers/output Claude ko verify karne ke liye do.
5. **Guess mat karo** â€” file, number, group, ya scope unclear ho to ruk kar poochho, andaza mat lagao.

Reusable task template (user isi se naya kaam dega):
```
@CURSOR_HANDOFF.md ye padho. Ab sirf ye ek kaam karo: [kaam ka naam].
Live database touch karne se pehle backup lo aur mujhe bata kar ruko.
Kaam khatam hone par exact numbers/output dikhao, taaki main Claude ko dikha kar verify karwa sakoon.
```


Ye THPS English Medium School, Dudahi, Kushinagar ka apna school-management software hai (SchoolSoft), Django 6 par bana hua. Do jagah chalta hai: (1) school ke computer par ek Windows EXE (PyInstaller se banaya gaya, SQLite database, ye hi asli/live data hai), aur (2) online ek Render.com website (PostgreSQL database, sirf dekhne ke liye/backup ke liye, desktop se ek-tarafa sync hoti hai â€” online se kabhi desktop me wapas nahi aati).

## Ab tak kya-kya bana hai:
Student records, marks, fee collection/receipts, transport, staff/salary, TC/certificates, ID cards â€” ye sab pehle se stable hain. Sabse bada recent kaam ek naya "demand-based due calculation engine" tha â€” matlab kisi bhi student ka exact bakaya (due) nikalne ka naya, saaf formula (`core/fee_engine.py`), jo purane receipt-based tarike ki jagah leta hai. Isko banane me kaafi mehnat lagi â€” 23 students ka data haath se verify karke formula lock kiya gaya (â‚¹96,750 ka locked baseline), phir schema migrate hui, fee/transport data Excel se import hua, PDF (Devanagari/Hindi font) sahi kiya gaya, aur phir sab online deploy hua.

Sabse abhi-abhi complete hua kaam: school ke "personal ledger" accounts (jaise Pragati ka â‚¹35,400 ka loan school ko, ya managers Reji Joy/Pragati Singh ka cash-advance, ya vendor Pintuji ka bakaya) â€” inko ek `Person` model se link kiya gaya taaki naam se confuse na ho (jaise "Pragati" Lender aur "Pragati Singh" Manager alag log hain, par naam milta-julta hai). Iska UI (`/accounts/persons/` list + detail page, sidebar me "Persons (Advances)") ban chuka hai aur verify ho chuka hai â€” ye kaam ab DONE hai, dobara mat banana.

## Kaam karne ka tareeka (bahut zaroori):
Main (Claude/Cowork) is project me sirf **read-only verifier** hoon â€” main file padh sakta hoon, live database ki backup copy padh kar numbers check kar sakta hoon, lekin main khud live database ko chhoo nahi sakta. Tum (naya agent) jo bhi actual code likhoge/migration chalaoge, wo live machine par ho, aur har risky step (schema change, data import, DB write) se pehle: (1) ek fresh backup lo, (2) chhote test/dry-run pe try karo, (3) mujhe result dikhao verify karne ke liye, (4) tabhi aage badho. Isi discipline se humne kai baar galtiyan pakà¤¡à¤¼à¥€ hain (jaise ek baar "opening balance" ko galat legacy field se nikalne ki koshish hui thi, jisse accuracy 20/23 se 12/23 gir gayi thi â€” pakà¤¡à¤¼ kar revert kiya gaya).

## Aage kya karna hai (meri raay):
1. **[DONE]** Render (online) ka DB password rotate karna
2. **[DONE]** Online view par "Last Backup"/"Last Sync" jaise cards hide karna
3. Render ka free-tier database ~1 August 2026 ko expire ho sakta hai â€” iska renewal plan dekhna hai
4. Dashboard ka front-design thoda polish karna (KPI cards me trend dikhana, ek chhota collection-chart) â€” ye cosmetic hai, low-priority, jab baaki sab stable ho jaye tab karna

**Status as of last update:** Person/Ledger UI, DB password rotation, and hiding online backup/sync cards are all complete and verified. Agla kaam upar ki list me se user chunega.

---
**Note for any agent:**
Person/Ledger UI is DONE (see status line above) â€” do not redo it. Pick your task from the "Aage kya karna hai" list above, or from the specific task the user gives you using the Agent Rules template. Always take a backup before touching the live database and wait for the verifier's (Claude's) confirmation on numbers.

