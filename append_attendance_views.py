attendance_views_code = '''

# ---------------------------------------------------------------------------
# Attendance Register (उपस्थिति पंजिका) Views
# ---------------------------------------------------------------------------

@login_required
def attendance_register_view(request):
    """Interactive preview and filter bar for Student Monthly Attendance Register."""
    import calendar
    from datetime import date
    from core.models import SchoolClass, Section, Student, AcademicSession, SchoolProfile

    today = date.today()
    selected_month = int(request.GET.get("month", today.month))
    selected_year = int(request.GET.get("year", today.year))
    
    classes = SchoolClass.objects.all().order_by("display_order")
    selected_class_id = request.GET.get("class_id")
    
    selected_class = None
    if selected_class_id:
        selected_class = SchoolClass.objects.filter(pk=selected_class_id).first()
    if not selected_class and classes.exists():
        selected_class = classes.first()

    sections = Section.objects.all().order_by("name")
    selected_section_id = request.GET.get("section_id")
    selected_section = None
    if selected_section_id:
        selected_section = Section.objects.filter(pk=selected_section_id).first()

    students = []
    if selected_class:
        qs = Student.objects.filter(is_active=True, current_class=selected_class)
        if selected_section:
            qs = qs.filter(current_section=selected_section)
        students = qs.select_related("current_class", "current_section").order_by("roll_no", "full_name")

    num_days = calendar.monthrange(selected_year, selected_month)[1]
    days_list = []
    day_abbrs = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for d in range(1, num_days + 1):
        w = calendar.weekday(selected_year, selected_month, d)
        days_list.append({
            "day": d,
            "weekday": day_abbrs[w],
            "is_sunday": (w == 6),
        })

    months_choices = [(m, calendar.month_name[m]) for m in range(1, 13)]
    years_choices = [2025, 2026, 2027]

    context = {
        "classes": classes,
        "sections": sections,
        "selected_class": selected_class,
        "selected_section": selected_section,
        "selected_month": selected_month,
        "selected_month_name": calendar.month_name[selected_month],
        "selected_year": selected_year,
        "months_choices": months_choices,
        "years_choices": years_choices,
        "days_list": days_list,
        "students": students,
        "total_students": len(students),
    }
    return render(request, "core/attendance_register.html", context)


@login_required
def attendance_register_pdf(request):
    """Stream printable A4 Landscape Monthly Attendance Register PDF."""
    import calendar
    from datetime import date
    from core.models import SchoolClass, Section, Student, AcademicSession, SchoolProfile
    from core.pdf import build_attendance_register_pdf

    today = date.today()
    month = int(request.GET.get("month", today.month))
    year = int(request.GET.get("year", today.year))
    
    class_id = request.GET.get("class_id")
    school_class = get_object_or_404(SchoolClass, pk=class_id) if class_id else SchoolClass.objects.first()
    
    section_id = request.GET.get("section_id")
    section = Section.objects.filter(pk=section_id).first() if section_id else None

    qs = Student.objects.filter(is_active=True, current_class=school_class)
    if section:
        qs = qs.filter(current_section=section)
    students = list(qs.select_related("current_class", "current_section").order_by("roll_no", "full_name"))

    session = AcademicSession.objects.filter(is_active=True).first() or AcademicSession.objects.first()
    school_profile = SchoolProfile.objects.first()

    pdf_bytes = build_attendance_register_pdf(
        students=students,
        school_class=school_class,
        section=section,
        month=month,
        year=year,
        session=session,
        school_profile=school_profile,
    )

    sec_name = f"_{section.name}" if section else ""
    filename = f"Attendance_{school_class.name}{sec_name}_{calendar.month_name[month]}_{year}.pdf".replace(" ", "_")
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
'''

views_path = r'E:\THPSIC-INTER-COLLEGE\01-source-code\schoolsoft_web\core\views.py'
with open(views_path, 'r', encoding='utf-8') as f:
    content = f.read()

if "def attendance_register_view" not in content:
    with open(views_path, 'a', encoding='utf-8') as f:
        f.write(attendance_views_code)
    print("attendance_register_view appended to core/views.py successfully!")
else:
    print("Views already present in core/views.py")
