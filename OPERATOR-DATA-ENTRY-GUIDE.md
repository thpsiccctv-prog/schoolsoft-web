# SchoolSoft Operator Guide

Date: 05 July 2026

This guide explains where daily entries must be done, where data is saved, how to back up the software, how to move SchoolSoft to another computer, and what to do with the old Access software.

## 1. Sabse Zaroori Rule

Daily real work sirf Desktop App / EXE me karein.

Use this:

`SchoolSoft.exe`

Do not use the online website for daily fee/admission entries unless the administrator specifically tells you.

Do not continue new entries in the old MS Access SchoolSOFT software.

## 2. Teen Alag Systems Ko Samjhein

### A. Desktop SchoolSoft EXE

This is the main and official software for daily work.

Use it for:

- New fee receipts
- Student admission/edit
- Receipt correction/cancel/void
- Marks, staff, transport, fee setup, reports
- Printing receipts and PDFs

Data is saved on this computer at:

`C:\Users\Admin\AppData\Local\SchoolSoft\db.sqlite3`

Important: the shortcut or EXE file is not the data. The real data is in the `db.sqlite3` file above.

### B. Online Website

URL:

`https://schoolsoft-english-medium.onrender.com`

Use it mainly for:

- Viewing reports from mobile or another place
- Online backup/mirror of desktop data
- Checking dashboard/status

Do not make daily real entries online, because online data does not automatically come back to the Desktop EXE.

### C. Old MS Access SchoolSOFT

The old software is now only for reference/history.

Do not enter new fee receipts, admission, marks, or updates in the old software.

If someone enters data in old software now, it will not automatically come into new SchoolSoft. This will create confusion and split records.

## 3. Where New Entries Will Save

If entry is done in Desktop EXE:

- Data saves in: `C:\Users\Admin\AppData\Local\SchoolSoft\db.sqlite3`
- This is the main school record.
- It works even without internet.

If entry is done on online website:

- Data saves on Render PostgreSQL server.
- It will not automatically appear in Desktop EXE.
- Avoid this for daily work.

If entry is done in old Access software:

- Data stays in old Access files only.
- It will not automatically appear in new SchoolSoft.
- Do not use it for new work.

## 4. Daily Work Procedure

1. Open `SchoolSoft.exe`.
2. Login with your assigned username/password.
3. Do fee/admission/student/marks/staff work inside Desktop EXE only.
4. Print receipt/PDF from the same app.
5. At the end of the day, close SchoolSoft.
6. Take a backup of the database.

## 5. Daily Backup Procedure

At the end of every working day:

1. Close SchoolSoft completely.
2. Open this folder:

   `C:\Users\Admin\AppData\Local\SchoolSoft`

3. Copy this file:

   `db.sqlite3`

4. Paste it into a safe backup location, for example:

   `D:\SchoolSoft Backups\`

   or an external pen drive/hard disk.

5. Rename the copied file with date:

   `SchoolSoft_backup_2026-07-05.sqlite3`

Recommended backup schedule:

- Daily: copy `db.sqlite3`
- Weekly: copy the full folder `C:\Users\Admin\AppData\Local\SchoolSoft`
- Before any software update/import/sync: take one extra backup

## 6. Moving SchoolSoft To Another Computer

Use this when you want to run the same SchoolSoft data on another desktop/laptop.

### On Old Computer

1. Close SchoolSoft completely.
2. Copy the data folder:

   `C:\Users\Admin\AppData\Local\SchoolSoft`

3. Also copy the app folder or installer/EXE folder:

   `D:\english medium\schoolsoft_web\dist\SchoolSoft`

   The important app file inside it is:

   `SchoolSoft.exe`

4. Keep both on pen drive/external disk:

   - `SchoolSoft` data folder
   - `dist\SchoolSoft` app folder

### On New Computer

1. Paste the app folder somewhere safe, for example:

   `D:\SchoolSoft\SchoolSoft`

2. Run `SchoolSoft.exe` once, then close it.
3. Open this folder on the new computer:

   `%LOCALAPPDATA%`

4. Paste the old `SchoolSoft` data folder there, so the final path becomes:

   `C:\Users\<NewUser>\AppData\Local\SchoolSoft\db.sqlite3`

5. Create a desktop shortcut for:

   `SchoolSoft.exe`

6. Open SchoolSoft and verify dashboard values.

Latest verified reference values before future new entries:

- Active Students: `364`
- Total Students: `1,215`
- Current Session Receipts: `101`
- Total Dues: `Rs. 2,15,700`

These numbers will change after new real entries.

## 7. Important Rule For Multiple Computers

Do not enter data on two different computers independently.

Example problem:

- Computer A receives fee receipt no. 102.
- Computer B also receives another fee receipt no. 102.
- Later both data files cannot be safely merged without special work.

Current recommended setup:

- One master desktop computer for all real entries.
- Other computers/mobile/online website for viewing reports only.

If the school needs multiple counters entering data at the same time, then a proper network/server setup should be planned separately.

## 8. Online Sync Procedure

The Desktop EXE database is the master.

The online website is a copy/mirror for reporting.

When online website needs to be updated:

1. Stop making entries for a few minutes.
2. Close SchoolSoft EXE completely.
3. Take backup of Desktop DB:

   `C:\Users\Admin\AppData\Local\SchoolSoft\db.sqlite3`

4. Run this file from the project/app folder:

   `sync-desktop-to-online.bat`

5. First time only, it will ask for Render External Database URL.
   Paste the URL that starts with:

   `postgresql://...`

   It will save this URL locally in:

   `render-db-url.txt`

   This file is ignored by Git and should not be shared publicly.

6. The script will:

   - Backup the Desktop DB into `sync-backups`
   - Export fresh Desktop data into `data.json`
   - Replace the online Render database with the Desktop data
   - Print final counts

7. After sync, open the online website and check the dashboard:

   `https://schoolsoft-english-medium.onrender.com`

Important:

- Sync is not automatic.
- Desktop entries do not instantly appear online.
- Online entries do not come back to desktop automatically.
- Sync direction is one-way: Desktop -> Online.
- Do not run sync while operators are making entries.

## 9. What Not To Do

Do not:

- Delete `db.sqlite3`
- Rename `db.sqlite3` unless restoring backup
- Copy only the desktop shortcut and think data is copied
- Enter new records in old MS Access software
- Enter the same receipt online and desktop both
- Run import/sync without backup
- Edit database directly in SQLite tools unless instructed

## 10. Emergency Restore From Backup

If data becomes wrong or software shows unexpected values:

1. Close SchoolSoft completely.
2. Open:

   `C:\Users\Admin\AppData\Local\SchoolSoft`

3. Rename current database:

   `db.sqlite3` -> `db.problem_2026-07-05.sqlite3`

4. Copy the latest good backup into this folder.
5. Rename backup copy to:

   `db.sqlite3`

6. Open SchoolSoft again.
7. Verify dashboard and recent receipts.

## 11. Operator Checklist

Daily start:

- [ ] Open Desktop `SchoolSoft.exe`
- [ ] Login with assigned user
- [ ] Check dashboard current session

During work:

- [ ] Make entries only in Desktop EXE
- [ ] Print receipt/PDF if needed
- [ ] Use Cancel/Void for wrong receipt, not hard delete
- [ ] Use Edit/Correct only with a clear reason

Daily end:

- [ ] Close SchoolSoft
- [ ] Copy `db.sqlite3` backup
- [ ] Save backup with date

Monthly/weekly:

- [ ] Ask administrator if online website needs sync
- [ ] Take full folder backup

## Final Decision

From now on:

1. New real entries: Desktop EXE only.
2. Online website: report/mobile/backup mirror only.
3. Old Access software: no new entry, reference only.
4. Main data file: `C:\Users\Admin\AppData\Local\SchoolSoft\db.sqlite3`.
5. To move to another computer: copy both the app folder and the `SchoolSoft` data folder.
