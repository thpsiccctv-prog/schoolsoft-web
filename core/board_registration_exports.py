import re

from django.utils import timezone

from .models import Student


DEFAULT_SUBJECT_PROFILES = {
    "class9": ("HS", ["901", "917", "928", "931", "932", "936", "944"]),
    "arts": ("A", ["101", "117", "128", "129", "142", "140", "173"]),
    "science_bio": ("B", ["102", "117", "151", "152", "153", "", "173"]),
    "science_maths": ("B", ["102", "117", "151", "152", "131", "", "173"]),
    "commerce": ("C", ["102", "156", "157", "117", "136", "", "173"]),
}


CLASS9_COLUMNS = [
    "SerialNumber",
    "CandidateName",
    "FatherName",
    "MotherName",
    "CandidateName_HIN",
    "FatherName_HIN",
    "MotherName_HIN",
    "DD",
    "MM",
    "YYYY",
    "Sex",
    "CasteCode",
    "IsMinorityCode",
    "CandidateType1Code",
    "CandidateType2Code",
    "MediumCode",
    "Subject01Code",
    "Subject02Code",
    "Subject03Code",
    "Subject04Code",
    "Subject05Code",
    "Subject06Code",
    "Subject07Code",
    "SubjectVOCCode",
    "SubjectRevVOCCode",
    "MobileNumber",
    "AadhaarNumber",
    "EMAILID",
    "Address1",
    "Address2",
    "Address3",
    "Address4",
    "District",
    "PinCode",
    "State",
    "UniqueIDClass08",
    "Nationality",
    "NationalityOther",
    "ApaarId",
    "PenNumber",
    "SrNumber",
]

CLASS11_UPBOARD_COLUMNS = [
    "SerialNumber",
    "PassingYearHighSchool",
    "RollNumberHighSchool",
    "PassBoardName",
    "MediumCode",
    "SubjectGroupCode",
    "Subject01Code",
    "Subject02Code",
    "Subject03Code",
    "Subject04Code",
    "Subject05Code",
    "Subject06Code",
    "Subject07Code",
    "SubjectVOCCode",
    "MobileNumber",
    "AadhaarNumber",
    "EMAILID",
    "Address1",
    "Address2",
    "Address3",
    "Address4",
    "District",
    "PinCode",
    "State",
    "Nationality",
    "NationalityOther",
    "ApaarId",
    "PenNumber",
    "SrNumber",
]

CLASS11_OTHERS_COLUMNS = [
    "SerialNumber",
    "PassingYearHighSchool",
    "RollNumberHighSchool",
    "PassBoardName",
    "CandidateName",
    "FatherName",
    "MotherName",
    "CandidateName_HIN",
    "FatherName_HIN",
    "MotherName_HIN",
    "Sex",
    "CasteCode",
    "IsMinorityCode",
    "CandidateType1Code",
    "CandidateType2Code",
    "MediumCode",
    "SubjectGroupCode",
    "Subject01Code",
    "Subject02Code",
    "Subject03Code",
    "Subject04Code",
    "Subject05Code",
    "Subject06Code",
    "Subject07Code",
    "SubjectVOCCode",
    "MobileNumber",
    "AadhaarNumber",
    "EMAILID",
    "Address1",
    "Address2",
    "Address3",
    "Address4",
    "District",
    "PinCode",
    "State",
    "Nationality",
    "NationalityOther",
    "ApaarId",
    "PenNumber",
    "SrNumber",
]

EXPORT_DEFINITIONS = {
    "class9": {
        "columns": CLASS9_COLUMNS,
        "filename": "Class9_BoardReg_2026.csv",
    },
    "class11-upboard": {
        "columns": CLASS11_UPBOARD_COLUMNS,
        "filename": "Class11_UPMSP_BoardReg_2026.csv",
    },
    "class11-others": {
        "columns": CLASS11_OTHERS_COLUMNS,
        "filename": "Class11_Others_BoardReg_2026.csv",
    },
}


def export_filename(kind):
    return EXPORT_DEFINITIONS[kind]["filename"]


def export_columns(kind):
    return EXPORT_DEFINITIONS[kind]["columns"]


def board_registration_students(kind):
    students = (
        Student.objects.filter(is_active=True)
        .select_related("current_class", "current_section")
        .order_by("current_class__display_order", "current_section__name", "legacy_sid", "admission_no")
    )
    if kind == "class9":
        return students.filter(current_class__name="IX")
    if kind in {"class11-upboard", "class11-others"}:
        students = students.filter(current_class__name__startswith="XI")
        return [student for student in students if _is_up_board_source(student) is (kind == "class11-upboard")]
    raise ValueError(f"Unknown board registration export kind: {kind}")


def build_rows(kind):
    students = list(board_registration_students(kind))
    row_builder = {
        "class9": _class9_row,
        "class11-upboard": _class11_upboard_row,
        "class11-others": _class11_others_row,
    }[kind]
    return [row_builder(index, student) for index, student in enumerate(students, start=1)]


def _class9_row(index, student):
    dd, mm, yyyy = _dob_parts(student)
    return [
        _board_serial(index, student),
        _text(student.full_name),
        _text(student.father_name),
        _text(student.mother_name),
        _text(getattr(student, "full_name_hindi", "")),
        _text(getattr(student, "father_name_hindi", "")),
        _text(getattr(student, "mother_name_hindi", "")),
        dd,
        mm,
        yyyy,
        _gender_code(student),
        _caste_code(student),
        "1" if student.is_minority else "0",
        _candidate_type_1(student),
        _candidate_type_2(student),
        _medium_code(student),
        _subject(student, 1),
        _subject(student, 2),
        _subject(student, 3),
        _subject(student, 4),
        _subject(student, 5),
        _subject(student, 6),
        _subject(student, 7),
        _text(getattr(student, "subject_voc_code", "")),
        _text(getattr(student, "subject_rev_voc_code", "")),
        _mobile(student),
        _digits(getattr(student, "aadhaar_no", "")),
        _text(student.email),
        _text(getattr(student, "address_street_area", "")),
        _text(student.village_locality),
        _text(student.post),
        _text(student.block),
        _district_code(student),
        _digits(student.pin_code),
        _text(getattr(student, "state", "") or "Uttar Pradesh"),
        _text(getattr(student, "class8_unique_id", "")),
        _text(student.nationality or "Indian"),
        _text(getattr(student, "nationality_other", "")),
        _text(student.apaar_id),
        _text(student.pen_number),
        _student_sr_number(student),
    ]


def _class11_upboard_row(index, student):
    return [
        _board_serial(index, student),
        _text(student.previous_passing_year),
        _text(student.previous_roll_no),
        _text(student.previous_board_name),
        _medium_code(student),
        _subject_group(student),
        _subject(student, 1),
        _subject(student, 2),
        _subject(student, 3),
        _subject(student, 4),
        _subject(student, 5),
        _subject(student, 6),
        _subject(student, 7),
        _text(getattr(student, "subject_voc_code", "")),
        _mobile(student),
        _digits(getattr(student, "aadhaar_no", "")),
        _text(student.email),
        _text(getattr(student, "address_street_area", "")),
        _text(student.village_locality),
        _text(student.post),
        _text(student.block),
        _district_code(student),
        _digits(student.pin_code),
        _text(getattr(student, "state", "") or "Uttar Pradesh"),
        _text(student.nationality or "Indian"),
        _text(getattr(student, "nationality_other", "")),
        _text(student.apaar_id),
        _text(student.pen_number),
        _student_sr_number(student),
    ]


def _class11_others_row(index, student):
    return [
        _board_serial(index, student),
        _text(student.previous_passing_year),
        _text(student.previous_roll_no),
        _text(student.previous_board_name),
        _text(student.full_name),
        _text(student.father_name),
        _text(student.mother_name),
        _text(getattr(student, "full_name_hindi", "")),
        _text(getattr(student, "father_name_hindi", "")),
        _text(getattr(student, "mother_name_hindi", "")),
        _gender_code(student),
        _caste_code(student),
        "1" if student.is_minority else "0",
        _candidate_type_1(student),
        _candidate_type_2(student),
        _medium_code(student),
        _subject_group(student),
        _subject(student, 1),
        _subject(student, 2),
        _subject(student, 3),
        _subject(student, 4),
        _subject(student, 5),
        _subject(student, 6),
        _subject(student, 7),
        _text(getattr(student, "subject_voc_code", "")),
        _mobile(student),
        _digits(getattr(student, "aadhaar_no", "")),
        _text(student.email),
        _text(getattr(student, "address_street_area", "")),
        _text(student.village_locality),
        _text(student.post),
        _text(student.block),
        _district_code(student),
        _digits(student.pin_code),
        _text(getattr(student, "state", "") or "Uttar Pradesh"),
        _text(student.nationality or "Indian"),
        _text(getattr(student, "nationality_other", "")),
        _text(student.apaar_id),
        _text(student.pen_number),
        _student_sr_number(student),
    ]


def _serial(index):
    return f"{index:04d}"


def _board_serial(index, student):
    return _text(getattr(student, "board_sr_number", "")) or _serial(index)


def _student_sr_number(student):
    return _text(getattr(student, "admission_no", "")) or _text(getattr(student, "legacy_sid", ""))


def _text(value):
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()


def _digits(value):
    return "".join(re.findall(r"\d", str(value or "")))


def _mobile(student):
    digits = _digits(student.mobile_primary or student.mobile_secondary)
    if len(digits) > 10 and digits.startswith("91"):
        return digits[-10:]
    return digits[:10]


def _dob_parts(student):
    if not student.date_of_birth:
        return "", "", ""
    return (
        student.date_of_birth.strftime("%d"),
        student.date_of_birth.strftime("%m"),
        student.date_of_birth.strftime("%Y"),
    )


def _gender_code(student):
    return {
        Student.Gender.MALE: "1",
        Student.Gender.FEMALE: "2",
        Student.Gender.OTHER: "3",
    }.get(student.gender, "")


def _medium_code(student):
    med = getattr(student, "exam_medium", "") or ""
    if str(med).upper() in ("E", "ENG", "ENGLISH", "2"):
        return "2"
    return "1"  # Default Hindi medium (1 for UP Board)


def _subject_group(student):
    group = getattr(student, "subject_group", "") or ""
    if not group:
        group, _codes = _default_subject_profile(student)
    return "" if group in ("HS", "HIGH_SCHOOL", "HIGH SCHOOL") else str(group)


def _subject(student, index):
    saved = _text(getattr(student, f"subject_{index}_code", ""))
    if saved:
        return saved
    _group, default_codes = _default_subject_profile(student)
    if index - 1 < len(default_codes):
        return default_codes[index - 1]
    return ""


def _default_subject_profile(student):
    class_name = ""
    if student.current_class:
        class_name = _text(student.current_class.name).upper()
    if class_name == "IX":
        return DEFAULT_SUBJECT_PROFILES["class9"]
    if class_name.startswith("XI"):
        if "ART" in class_name:
            return DEFAULT_SUBJECT_PROFILES["arts"]
        if "BIO" in class_name:
            return DEFAULT_SUBJECT_PROFILES["science_bio"]
        if "MATH" in class_name:
            return DEFAULT_SUBJECT_PROFILES["science_maths"]
        if "COM" in class_name:
            return DEFAULT_SUBJECT_PROFILES["commerce"]
    return "", ["", "", "", "", "", "", ""]


def _candidate_type_1(student):
    return _text(getattr(student, "board_candidate_type_1_code", "")) or "1"


def _candidate_type_2(student):
    board_code = _text(getattr(student, "board_candidate_type_2_code", ""))
    if board_code:
        return board_code
    return {
        Student.Disability.NONE: "0",
        Student.Disability.VISUALLY_IMPAIRED: "1",
        Student.Disability.HEARING_IMPAIRED: "2",
        Student.Disability.PHYSICALLY_DISABLED: "6",
    }.get(student.disability, "0")


def _caste_code(student):
    board_code = _text(getattr(student, "board_caste_code", ""))
    if board_code:
        return board_code
    category = _text(student.category).upper()
    if "SC" in category:
        return "1"
    if "ST" in category:
        return "2"
    if "OBC" in category or "BACKWARD" in category:
        return "3"
    if "EWS" in category:
        return "5"
    if "GEN" in category or "GENERAL" in category:
        return "4"
    return ""


def _district_code(student):
    district = _text(student.district).upper()
    if district and district.isdigit():
        return district
    if not district or "KUSH" in district or "KUSHI" in district:
        return "78"
    return district


def _is_up_board_source(student):
    source = _text(getattr(student, "previous_board_source", "")).lower()
    if source in ("upboard", "up_board", "up"):
        return True
    if source in ("other", "others", "cbse", "icse"):
        return False

    board_name = _text(student.previous_board_name).upper()
    if not board_name:
        return True
    # Exact markers (original)
    up_markers = ["UP BOARD", "U.P", "UPMSP", "UTTAR PRADESH", "MADHYAMIK SHIKSHA"]
    if any(marker in board_name for marker in up_markers):
        return True
    # Typo-tolerant: strip spaces and check compressed form
    # Catches: "u p bourd", "up bourd", "u p bord", "up bord" etc.
    compressed = board_name.replace(" ", "")
    if compressed.startswith("UPBO") or compressed.startswith("UPBAR"):
        return True
    # "U P B..." pattern after stripping dots/spaces
    if board_name.startswith("U P B") or board_name.startswith("U.P.B"):
        return True
    return False


def output_timestamp():
    return timezone.localtime().strftime("%Y%m%d-%H%M%S")
