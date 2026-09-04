"""
THPSIC SchoolSoft - Student Bulk Photo Processor & Matching Engine.
Handles photographer filenames (e.g. 090001.jpg, 090054.jpg, 9791.jpg),
exact class-code routing, smart 4:5 portrait cropping (excluding signature strip),
EXIF auto-transposition, safe member-by-member ZIP extraction, dry-run previews,
live database backups, and audited applications.
"""

import os
import re
import io
import json
import uuid
import base64
import zipfile
import datetime
import tempfile
import shutil
import csv
from pathlib import Path
from PIL import Image, ImageOps

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from core.models import Student, SchoolClass


# Exact mapping from 2-digit class prefix to actual SchoolClass names in database
CLASS_CODE_MAP = {
    "06": ["VI"],
    "07": ["VII"],
    "08": ["VIII"],
    "09": ["IX"],
    "10": ["X"],
    "11": ["XI (ART)", "XI (BIO)", "XI (COM)", "XI (MATHS)"],
    "12": ["XII (ART)", "XII (BIO)", "XII (COM)", "XII (MATHS)"],
    "6": ["VI"],
    "7": ["VII"],
    "8": ["VIII"],
    "9": ["IX"],
}

VALID_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".jfif"}
MAX_SINGLE_FILE_SIZE = 15 * 1024 * 1024  # 15 MB
MAX_TOTAL_UNCOMPRESSED_SIZE = 250 * 1024 * 1024  # 250 MB


def parse_photo_filename(filename, class_hint=None):
    """
    Extracts potential student identifiers from a photo filename.
    """
    stem = Path(filename).stem.strip()
    result = {
        "raw_filename": filename,
        "clean_stem": stem,
        "class_code": None,
        "board_sr": None,
        "adm_no": None,
        "pattern_type": "RAW",
    }

    clean = re.sub(r"[^\w\-]", "", stem)

    # 1. Photographer Standard CCSSSS pattern (e.g. 090054, 110464, 060012)
    m_ccssss = re.match(r"^(0[6-9]|1[0-2])(\d{4})$", clean)
    if m_ccssss:
        result["class_code"] = m_ccssss.group(1)
        result["board_sr"] = m_ccssss.group(2)
        result["pattern_type"] = "CCSSSS"
        return result

    # 2. Class-Sec Prefix + Adm or Serial (e.g., IX-A_9791, 9A_9791, IX_0054)
    m_prefix = re.match(r"^(?:CLASS[-_]?)?([IVXLCDM]+|\d{1,2})[-_]?([A-Z])?[-_](\d+)$", clean, re.IGNORECASE)
    if m_prefix:
        cls_part = m_prefix.group(1).upper()
        num_part = m_prefix.group(3)
        if len(num_part) == 4 and num_part.startswith("0"):
            result["board_sr"] = num_part
            result["class_code"] = cls_part
            result["pattern_type"] = "BOARD_SR_WITH_CLASS"
        else:
            result["adm_no"] = num_part
            result["pattern_type"] = "ADM_WITH_CLASS"
        return result

    # 3. Direct 4-digit or 5-digit Admission Number (e.g., 9791, 10157, 9644, 9791_1)
    m_adm = re.match(r"^(\d{4,6})(?:[-_]\d+)?$", clean)
    if m_adm:
        num = m_adm.group(1)
        if num.startswith("0") and len(num) == 4:
            result["board_sr"] = num
            result["pattern_type"] = "BOARD_SR_ONLY"
        else:
            result["adm_no"] = num
            result["pattern_type"] = "ADM_DIRECT"
        return result

    # 4. "ADM-9791" or "SID-9791"
    m_labeled = re.match(r"^(?:ADM|SID|SCHOLAR)[-_]?(\d+)$", clean, re.IGNORECASE)
    if m_labeled:
        result["adm_no"] = m_labeled.group(1)
        result["pattern_type"] = "ADM_DIRECT"
        return result

    # Fallback digits
    m_digits = re.search(r"(\d{4,6})", clean)
    if m_digits:
        result["adm_no"] = m_digits.group(1)
        result["pattern_type"] = "DIGITS_FALLBACK"

    return result


def match_photo_to_student(parsed_info, excel_mapping=None, class_filter=None):
    """
    Matches parsed filename info to a Student record in the database using strict class routing.
    Returns (status, student, message)
    Status: 'MATCHED_NEW', 'MATCHED_REPLACE', 'AMBIGUOUS', 'NO_MATCH'
    """
    raw_filename = parsed_info["raw_filename"]
    clean_stem = parsed_info["clean_stem"]

    # 1. Excel mapping override
    if excel_mapping and (raw_filename in excel_mapping or clean_stem in excel_mapping):
        mapped_val = str(excel_mapping.get(raw_filename) or excel_mapping.get(clean_stem)).strip()
        students = Student.objects.filter(is_active=True).filter(
            Q(admission_no=mapped_val) | Q(legacy_sid=mapped_val) | Q(board_sr_number=mapped_val)
        )
        if class_filter:
            students = students.filter(current_class=class_filter)

        if students.count() == 1:
            stu = students.first()
            status = "MATCHED_REPLACE" if stu.photo else "MATCHED_NEW"
            return status, stu, f"Matched via Excel Mapping: {mapped_val}"
        elif students.count() > 1:
            matches_str = ", ".join([f"{s.full_name} ({s.current_class})" for s in students[:3]])
            return "AMBIGUOUS", None, f"Excel mapping '{mapped_val}' matched multiple students: {matches_str}"

    # 2. Photographer CCSSSS Pattern (Strict Class Routing, Zero Silent Fallback)
    if parsed_info["pattern_type"] == "CCSSSS":
        cc = parsed_info["class_code"]
        bsr = parsed_info["board_sr"]
        valid_classes = CLASS_CODE_MAP.get(cc, [])

        if not valid_classes:
            return "NO_MATCH", None, f"Unknown Class Prefix '{cc}' in filename"

        qs = Student.objects.filter(is_active=True, board_sr_number=bsr, current_class__name__in=valid_classes)

        if qs.count() == 1:
            stu = qs.first()
            status = "MATCHED_REPLACE" if stu.photo else "MATCHED_NEW"
            return status, stu, f"Matched Board Sr {bsr} in Class {stu.current_class.name} (prefix {cc})"
        elif qs.count() > 1:
            matches_str = ", ".join([f"{s.full_name} ({s.current_class.name})" for s in qs[:3]])
            return "AMBIGUOUS", None, f"Board Sr '{bsr}' matches {qs.count()} students in Class {cc}: {matches_str}"
        else:
            return "NO_MATCH", None, f"No student found with Board Sr {bsr} in Class {cc}"

    # 3. Direct Admission No / Legacy SID
    if parsed_info["adm_no"]:
        adm = parsed_info["adm_no"]
        qs = Student.objects.filter(is_active=True).filter(
            Q(admission_no=adm) | Q(legacy_sid=adm)
        )
        if class_filter:
            qs = qs.filter(current_class=class_filter)

        if qs.count() == 1:
            stu = qs.first()
            status = "MATCHED_REPLACE" if stu.photo else "MATCHED_NEW"
            return status, stu, f"Matched Admission No {adm}"
        elif qs.count() > 1:
            matches_str = ", ".join([f"{s.full_name} ({s.current_class})" for s in qs[:3]])
            return "AMBIGUOUS", None, f"Admission No '{adm}' matches multiple students: {matches_str}"

    # 4. Board Sr Only with Explicit Class Filter
    if parsed_info["board_sr"]:
        bsr = parsed_info["board_sr"]
        if class_filter:
            qs = Student.objects.filter(is_active=True, board_sr_number=bsr, current_class=class_filter)
            if qs.count() == 1:
                stu = qs.first()
                status = "MATCHED_REPLACE" if stu.photo else "MATCHED_NEW"
                return status, stu, f"Matched Board Sr {bsr} in {class_filter.name}"
            elif qs.count() > 1:
                matches_str = ", ".join([f"{s.full_name} ({s.current_class})" for s in qs[:3]])
                return "AMBIGUOUS", None, f"Board Sr '{bsr}' matches {qs.count()} students in {class_filter.name}: {matches_str}"
            else:
                return "NO_MATCH", None, f"No student with Board Sr {bsr} in {class_filter.name}"
        else:
            # Without class filter, check if globally unique
            qs = Student.objects.filter(is_active=True, board_sr_number=bsr)
            if qs.count() == 1:
                stu = qs.first()
                status = "MATCHED_REPLACE" if stu.photo else "MATCHED_NEW"
                return status, stu, f"Matched unique Board Sr {bsr} ({stu.current_class})"
            elif qs.count() > 1:
                matches_str = ", ".join([f"{s.full_name} ({s.current_class})" for s in qs[:3]])
                return "AMBIGUOUS", None, f"Board Sr '{bsr}' exists in multiple classes ({matches_str}). Please select Class filter."

    return "NO_MATCH", None, "No active student matched"


def find_signature_boundary(img):
    """
    Scans the bottom half of the image from y = 0.50*H to 0.96*H to auto-detect
    the top edge of the signature slip (white/light box with low saturation).
    Returns the Y coordinate where the signature box begins, or None if not found.
    """
    w, h = img.size
    img_rgb = img.convert("RGB")
    pixels = img_rgb.load()
    
    consecutive_white_rows = 0
    first_white_y = None
    
    for y in range(int(h * 0.50), int(h * 0.96)):
        white_count = 0
        lum_sum = 0
        sat_sum = 0
        for x in range(w):
            r, g, b = pixels[x, y]
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            sat = max(r, g, b) - min(r, g, b)
            lum_sum += lum
            sat_sum += sat
            if lum > 200 and sat < 25:
                white_count += 1
                
        pct_white = white_count / float(w)
        avg_lum = lum_sum / float(w)
        avg_sat = sat_sum / float(w)
        
        # Detected mostly white paper area with low color saturation
        if pct_white > 0.40 and avg_lum > 190 and avg_sat < 22:
            if consecutive_white_rows == 0:
                first_white_y = y
            consecutive_white_rows += 1
            if consecutive_white_rows >= 6:
                return first_white_y
        else:
            consecutive_white_rows = 0
            first_white_y = None
            
    return None


def process_image_bytes(image_bytes, crop_mode="smart_portrait", target_size=(480, 600), quality=85):
    """
    Processes raw image bytes:
    - Auto-rotates via EXIF.
    - Smart 4:5 center-crop with signature boundary auto-detection.
    - Cuts off handwritten signature box completely.
    - Resizes to standard 480x600 px JPEG.
    """
    img = Image.open(io.BytesIO(image_bytes))
    img = ImageOps.exif_transpose(img)

    if img.mode != "RGB":
        img = img.convert("RGB")

    orig_w, orig_h = img.size
    target_w, target_h = target_size
    target_aspect = target_w / float(target_h)

    if crop_mode == "smart_portrait":
        sig_y = find_signature_boundary(img)
        if sig_y:
            # Cut slightly above detected signature box (margin of 8-12px)
            effective_h = max(int(orig_h * 0.50), sig_y - max(8, int(orig_h * 0.02)))
        else:
            # Safe default fallback cutting off bottom 24% signature margin
            effective_h = orig_h * 0.76

        effective_aspect = orig_w / float(effective_h)

        if effective_aspect > target_aspect:
            new_w = effective_h * target_aspect
            offset_x = (orig_w - new_w) / 2.0
            crop_box = (
                int(offset_x),
                int(orig_h * 0.01),
                int(offset_x + new_w),
                int(orig_h * 0.01 + effective_h)
            )
        else:
            new_h = orig_w / target_aspect
            crop_box = (
                0,
                int(orig_h * 0.01),
                orig_w,
                int(orig_h * 0.01 + new_h)
            )

        crop_box = (
            max(0, crop_box[0]),
            max(0, crop_box[1]),
            min(orig_w, crop_box[2]),
            min(orig_h, crop_box[3]),
        )
        img = img.crop(crop_box)

    img = img.resize(target_size, Image.Resampling.LANCZOS)

    out_buf = io.BytesIO()
    img.save(out_buf, format="JPEG", quality=quality, optimize=True)
    return out_buf.getvalue()


def save_student_photo(student, processed_jpeg_bytes):
    """
    Saves processed photo bytes to student's photo field and creates backup of old photo.
    """
    media_root = Path(settings.MEDIA_ROOT)
    photos_dir = media_root / "student_photos"
    backup_dir = photos_dir / "_backup"
    photos_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.mkdir(parents=True, exist_ok=True)

    old_photo_rel = None
    if student.photo and hasattr(student.photo, "path") and os.path.exists(student.photo.path):
        try:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            old_name = Path(student.photo.path).name
            backup_filename = f"{student.admission_no or student.pk}_{ts}_{old_name}"
            backup_path = backup_dir / backup_filename
            shutil.copy2(student.photo.path, backup_path)
            old_photo_rel = f"student_photos/_backup/{backup_filename}"
        except Exception:
            pass

    identifier = student.admission_no or student.legacy_sid or student.pk
    filename = f"{identifier}.jpg"
    rel_path = f"student_photos/{filename}"
    full_path = photos_dir / filename

    with open(full_path, "wb") as f:
        f.write(processed_jpeg_bytes)

    student.photo = rel_path
    student.doc_photo_received = True
    student.save(update_fields=["photo", "doc_photo_received", "updated_at"])
    return rel_path, old_photo_rel


def parse_excel_mapping_file(file_obj):
    """
    Parses an Excel (.xlsx / .xls) or CSV mapping file.
    """
    mapping = {}
    try:
        import openpyxl
        wb = openpyxl.load_workbook(file_obj, data_only=True)
        sheet = wb.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return mapping

        header = [str(cell).strip().lower() if cell is not None else "" for cell in rows[0]]
        col_file = 0
        col_id = 1

        for idx, h in enumerate(header):
            if any(k in h for k in ["file", "photo", "image", "pic", "नाम"]):
                col_file = idx
            elif any(k in h for k in ["adm", "scholar", "board", "sid", "roll", "id", "अनुक्रमांक"]):
                col_id = idx

        for row in rows[1:]:
            if not row or len(row) <= max(col_file, col_id):
                continue
            f_val = str(row[col_file]).strip() if row[col_file] is not None else ""
            id_val = str(row[col_id]).strip() if row[col_id] is not None else ""
            if f_val and id_val:
                mapping[f_val] = id_val
                mapping[Path(f_val).stem] = id_val

    except Exception:
        pass

    return mapping


def _safe_extract_zip(zip_file_obj, target_dir):
    """
    Extracts only valid image files from ZIP member-by-member:
    - Rejects absolute paths and drive letters.
    - Rejects '..' path traversal.
    - Skips directories.
    - Filters by VALID_IMAGE_EXTENSIONS.
    - Enforces per-file (15MB) and total uncompressed (250MB) size caps.
    Returns list of safely extracted (safe_rel_path, original_filename) tuples and list of skipped unsafe files.
    """
    extracted_files = []
    skipped_unsafe = []
    total_uncompressed = 0

    with zipfile.ZipFile(zip_file_obj, "r") as zf:
        for member in zf.infolist():
            # 1. Skip directories
            if member.is_dir() or member.filename.endswith("/") or member.filename.endswith("\\"):
                continue

            fname = member.filename
            # 2. Reject absolute paths or drive letters
            if fname.startswith("/") or fname.startswith("\\") or (len(fname) > 1 and fname[1] == ":"):
                skipped_unsafe.append((fname, "Rejected: Absolute path"))
                continue

            # 3. Reject path traversal
            parts = Path(fname).parts
            if ".." in parts or any(p.startswith("..") for p in parts):
                skipped_unsafe.append((fname, "Rejected: Path traversal ('..')"))
                continue

            # 4. Check extension
            ext = Path(fname).suffix.lower()
            if ext not in VALID_IMAGE_EXTENSIONS:
                continue

            # 5. Check single file size cap
            if member.file_size > MAX_SINGLE_FILE_SIZE:
                skipped_unsafe.append((fname, f"Rejected: File size exceeds 15 MB ({member.file_size / (1024*1024):.1f} MB)"))
                continue

            # 6. Check cumulative size cap (zip bomb protection)
            total_uncompressed += member.file_size
            if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_SIZE:
                skipped_unsafe.append((fname, "Rejected: Total archive extraction limit (250 MB) exceeded"))
                break

            # Safe extraction destination
            safe_basename = Path(fname).name
            dest_path = target_dir / safe_basename
            
            # Avoid collision in temp directory
            counter = 1
            while dest_path.exists():
                stem = Path(safe_basename).stem
                dest_path = target_dir / f"{stem}_{counter}{ext}"
                counter += 1

            with zf.open(member) as source, open(dest_path, "wb") as target:
                shutil.copyfileobj(source, target)

            extracted_files.append((dest_path, safe_basename))

    return extracted_files, skipped_unsafe


def run_bulk_photo_dry_run(zip_file_obj, excel_mapping=None, class_filter=None, crop_mode="smart_portrait"):
    """
    Safely extracts uploaded ZIP archive, runs strict matching & generates dry-run preview.
    """
    session_token = str(uuid.uuid4())
    temp_dir = Path(tempfile.gettempdir()) / "schoolsoft_photo_uploads" / session_token
    temp_dir.mkdir(parents=True, exist_ok=True)

    extracted_files, skipped_unsafe = _safe_extract_zip(zip_file_obj, temp_dir)

    items = []
    summary = {
        "total_files": len(extracted_files) + len(skipped_unsafe),
        "matched_new": 0,
        "matched_replace": 0,
        "ambiguous": 0,
        "no_match": 0,
        "invalid_files": 0,
        "skipped_unsafe": len(skipped_unsafe),
    }

    # Add unsafe skipped files to preview table
    for fname, reason in skipped_unsafe:
        items.append({
            "temp_file_rel": "",
            "filename": fname,
            "status": "INVALID",
            "message": f"SKIPPED (Unsafe): {reason}",
            "student_id": None,
            "adm_no": "—",
            "board_sr": "—",
            "student_name": "—",
            "class_sec": "—",
            "has_existing_photo": False,
            "thumbnail_b64": "",
        })

    for file_path, original_fname in extracted_files:
        rel_file = str(file_path.relative_to(temp_dir)).replace("\\", "/")

        try:
            with open(file_path, "rb") as f:
                raw_bytes = f.read()

            thumb_bytes = process_image_bytes(raw_bytes, crop_mode=crop_mode, target_size=(120, 150), quality=75)
            thumb_b64 = "data:image/jpeg;base64," + base64.b64encode(thumb_bytes).decode("ascii")

            parsed = parse_photo_filename(original_fname, class_hint=class_filter.name if class_filter else None)
            status, stu, msg = match_photo_to_student(parsed, excel_mapping=excel_mapping, class_filter=class_filter)

            if status == "MATCHED_NEW":
                summary["matched_new"] += 1
            elif status == "MATCHED_REPLACE":
                summary["matched_replace"] += 1
            elif status == "AMBIGUOUS":
                summary["ambiguous"] += 1
            elif status == "NO_MATCH":
                summary["no_match"] += 1

            items.append({
                "temp_file_rel": rel_file,
                "filename": original_fname,
                "status": status,
                "message": msg,
                "student_id": stu.pk if stu else None,
                "adm_no": stu.admission_no if stu else (parsed.get("adm_no") or "—"),
                "board_sr": stu.board_sr_number if stu else (parsed.get("board_sr") or "—"),
                "student_name": stu.full_name if stu else "—",
                "class_sec": f"{stu.current_class.name if stu.current_class else ''}{(' - ' + stu.current_section.name) if stu and stu.current_section else ''}" if stu else "—",
                "has_existing_photo": bool(stu.photo) if stu else False,
                "thumbnail_b64": thumb_b64,
            })

        except Exception as e:
            summary["invalid_files"] += 1
            items.append({
                "temp_file_rel": rel_file,
                "filename": original_fname,
                "status": "INVALID",
                "message": f"Corrupt or invalid image: {str(e)}",
                "student_id": None,
                "adm_no": "—",
                "board_sr": "—",
                "student_name": "—",
                "class_sec": "—",
                "has_existing_photo": False,
                "thumbnail_b64": "",
            })

    # Save manifest for live apply
    manifest_path = temp_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "session_token": session_token,
            "crop_mode": crop_mode,
            "summary": summary,
            "items": items,
        }, f, indent=2)

    return {
        "session_token": session_token,
        "summary": summary,
        "items": items,
    }


def create_pre_apply_database_backup():
    """
    Creates an instant snapshot backup of the SQLite database before applying photos.
    Stored under 04-backups/daily_backups/<ts>-before-bulk-photo-apply/db.sqlite3.
    """
    db_path = getattr(settings, "DATABASES", {}).get("default", {}).get("NAME")
    if not db_path or not os.path.exists(db_path):
        return None

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_folder = Path(settings.BASE_DIR).parent / "04-backups" / "daily_backups" / f"{ts}-before-bulk-photo-apply"
    backup_folder.mkdir(parents=True, exist_ok=True)

    backup_file = backup_folder / "db.sqlite3"
    shutil.copy2(db_path, backup_file)
    return str(backup_file)


def apply_bulk_photos(session_token, selected_filenames=None):
    """
    Applies dry-run matches to disk and database.
    Requires selected_filenames list.
    Creates live DB snapshot backup before executing.
    Generates post-apply CSV audit report.
    """
    temp_dir = Path(tempfile.gettempdir()) / "schoolsoft_photo_uploads" / session_token
    manifest_path = temp_dir / "manifest.json"

    if not manifest_path.exists():
        raise ValueError("Invalid or expired session token. Please re-run photo dry run.")

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    crop_mode = data.get("crop_mode", "smart_portrait")
    items = data.get("items", [])

    # 1. Live Database Snapshot Backup
    db_backup_path = create_pre_apply_database_backup()

    results = {
        "applied_count": 0,
        "replaced_count": 0,
        "skipped_count": 0,
        "error_count": 0,
        "db_backup_path": db_backup_path or "N/A",
        "report_csv_path": None,
        "details": [],
    }

    selected_set = set(selected_filenames) if selected_filenames else set()
    audit_rows = []
    ts_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for item in items:
        fname = item["filename"]

        # Only apply explicitly checked filenames
        if selected_set and fname not in selected_set:
            results["skipped_count"] += 1
            audit_rows.append([fname, item.get("adm_no", ""), item.get("student_name", ""), item.get("class_sec", ""), item.get("board_sr", ""), "SKIPPED", "", "", "User Unchecked", ts_now])
            continue

        if item["status"] not in ["MATCHED_NEW", "MATCHED_REPLACE"] or not item["student_id"]:
            results["skipped_count"] += 1
            audit_rows.append([fname, item.get("adm_no", ""), item.get("student_name", ""), item.get("class_sec", ""), item.get("board_sr", ""), "SKIPPED", "", "", item["status"], ts_now])
            continue

        file_path = temp_dir / item["temp_file_rel"]
        if not file_path.exists():
            results["error_count"] += 1
            audit_rows.append([fname, item.get("adm_no", ""), item.get("student_name", ""), item.get("class_sec", ""), item.get("board_sr", ""), "ERROR", "", "", "Temp file missing", ts_now])
            continue

        try:
            student = Student.objects.get(pk=item["student_id"], is_active=True)
            with open(file_path, "rb") as f:
                raw_bytes = f.read()

            processed_bytes = process_image_bytes(raw_bytes, crop_mode=crop_mode, target_size=(480, 600), quality=85)
            new_rel_path, old_rel_path = save_student_photo(student, processed_bytes)

            action = "REPLACED" if item["status"] == "MATCHED_REPLACE" else "NEW"
            if action == "REPLACED":
                results["replaced_count"] += 1
            else:
                results["applied_count"] += 1

            audit_rows.append([
                fname,
                student.admission_no or "",
                student.full_name,
                f"{student.current_class.name if student.current_class else ''}-{student.current_section.name if student.current_section else ''}",
                student.board_sr_number or "",
                action,
                old_rel_path or "None",
                new_rel_path,
                "SUCCESS",
                ts_now
            ])

        except Exception as e:
            results["error_count"] += 1
            audit_rows.append([fname, item.get("adm_no", ""), item.get("student_name", ""), item.get("class_sec", ""), item.get("board_sr", ""), "ERROR", "", "", str(e), ts_now])

    # 2. Save Audit CSV Report
    reports_dir = Path(settings.BASE_DIR).parent / "05-reports" / "photo-upload"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = reports_dir / f"PHOTO_APPLY_AUDIT_{report_ts}.csv"

    with open(report_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Filename", "Adm No", "Student Name", "Class-Sec", "Board Sr", "Action", "Old Photo Backup", "New Photo Path", "Status", "Timestamp"])
        writer.writerows(audit_rows)

    results["report_csv_path"] = str(report_file)

    # Cleanup temp directory
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass

    return results