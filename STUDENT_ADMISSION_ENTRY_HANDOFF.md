CONTEXT — SchoolSoft (School ERP)
I have a desktop School ERP called "SchoolSoft", built with Django + Vanilla CSS
(no Tailwind/Bootstrap), packaged into a Windows desktop app with PyInstaller in
ONEDIR mode. The screen in focus is the "Student Admission Entry" form
(URL: /students/new/). Target users are clerks doing fast, repetitive data entry,
so the look must be "compact but modern / premium SaaS", but stay dense and readable.

CURRENT DESIGN (this is the APPROVED, final look — do not redesign unless asked):
- The whole form is scoped under a wrapper class `.student-entry`.
- Design tokens live as CSS variables on `.student-entry`:
  --entry-accent:#0f766e; --entry-accent-dark:#0b4f4a; --entry-line:#d7e3ea;
  --entry-line-strong:#b9cbd6; --entry-ink:#0f172a; --entry-focus (green focus ring).
  A deep sidebar-green (#14342a) is used for gradients so the form matches the
  dark-green sidebar.
- Layout uses a 4-column CSS grid:
  `.entry-grid.entry-grid-four` with helpers `.entry-span-2` and `.entry-span-full`.
  Every field is `.entry-field` (label stacked over input).
- Sections are `.entry-card` with `.entry-card-title` (colored accent bar via ::before).
- Right rail: `.student-entry-rail` containing `.student-photo-card` and
  `.student-command-card` (Active toggle + Save `.entry-btn-primary` + Save & New).
- A "PREMIUM COLOR LAYER" block is appended at the END of styles.css: soft green
  page gradient, thin teal→green top edge on each card, green kicker pill
  (`.entry-kicker`), tinted inputs, deep-green Save gradient, tinted table header
  for Recent Admissions (`.recent-admissions-table`).

SOURCE FILES (the source of truth — edit ONLY these):
- static/core/styles.css            (all styles; the color layer is at the bottom)
- templates/core/student_form.html  (uses the entry-* grid classes)
- templates/base.html               (links styles.css with a ?v= cache-buster)

**CRITICAL BUILD GOTCHA — this wasted a lot of time, read carefully:**
The project has FOUR copies of styles.css (and duplicate templates):
  1. static/core/styles.css                                  <- SOURCE (edit this)
  2. staticfiles/core/styles.css                             <- collectstatic output
  3. dist/SchoolSoft/_internal/static/core/styles.css        <- bundled in the EXE
  4. dist/SchoolSoft/_internal/staticfiles/core/styles.css   <- bundled in the EXE
The DESKTOP APP (.exe) reads from dist/SchoolSoft/_internal/, NOT from source.
So editing only the source shows changes in the browser (127.0.0.1:8000) but the
desktop app keeps showing the OLD design. Same problem exists for the templates.

Because it is a PyInstaller ONEDIR build, files under _internal/ are plain files on
disk. After any CSS/template change you MUST propagate the change, or the desktop
app will look stale/broken (e.g. CSS updates but template doesn't -> fields stack
in one column).

CORRECT WAY to make changes:
1. Edit the SOURCE files only (static/core/styles.css, templates/...).
2. Run `python manage.py collectstatic --noinput` to refresh staticfiles/.
3. Rebuild the EXE with PyInstaller so dist/_internal/ is regenerated.
   (Quick local test only: you may copy the source files over the 3 stale copies to
   preview without a full rebuild — but always do a real rebuild before shipping.)
4. Fully CLOSE and reopen the desktop app (not just refresh). In a browser use Ctrl+F5.

TASK:
[describe what you want changed here]

Please keep the existing `.student-entry` / `.entry-*` class system and tokens,
edit only the SOURCE files, and remind me to collectstatic + rebuild the EXE at the end.
