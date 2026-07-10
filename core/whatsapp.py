"""Free WhatsApp "alert" links (wa.me deep links) - no paid WhatsApp Business API.

How it works: we build a https://wa.me/<number>?text=<message> URL. Clicking it
opens WhatsApp (web or the desktop/mobile app, whichever is installed) with the
message already typed into the chat box for that number. A staff member still
has to look at it and press Send themselves inside WhatsApp - nothing is sent
automatically by the server, no account/API key/approval is needed, and it is
completely free.

Because of that manual-send requirement this is meant for one-at-a-time or
small-batch use (e.g. going down a filtered Due Report list clicking each
link), not for a real bulk-blast to hundreds of parents in one click.
"""

from urllib.parse import quote


def normalize_indian_mobile(raw):
    """Turn a stored mobile number into the digits-only, country-code-prefixed
    form wa.me expects (e.g. "9198xxxxxxx"). Returns None if the number looks
    too short/garbled to be a real mobile number - callers should just not
    show a WhatsApp link in that case rather than guess.
    """
    if not raw:
        return None
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if not digits:
        return None
    if len(digits) == 10:
        return "91" + digits
    if len(digits) == 11 and digits.startswith("0"):
        return "91" + digits[1:]
    if len(digits) == 12 and digits.startswith("91"):
        return digits
    if len(digits) < 10:
        return None
    return digits


def build_wa_link(mobile, message):
    """Return a wa.me URL, or None if the mobile number is unusable."""
    number = normalize_indian_mobile(mobile)
    if not number:
        return None
    return f"https://wa.me/{number}?text={quote(message)}"


def _class_label(class_name, section_name):
    if class_name and section_name:
        return f"{class_name}-{section_name}"
    return class_name or ""


def fee_due_message(father_name, full_name, class_name, section_name, admission_no, due_amount, school_name=""):
    lines = []
    lines.append(f"Namaste {father_name or 'Guardian'} ji,")
    if school_name:
        lines.append(f"{school_name} se suchna:")
    label = _class_label(class_name, section_name)
    lines.append(
        f"{full_name} (Class {label}, Adm No {admission_no}) ki fee me "
        f"Rs. {due_amount} due hai. Kripya jald jama karayein."
    )
    lines.append("Dhanyawad.")
    return "\n".join(lines)


def ptm_message(father_name, full_name, class_name, section_name, date_text, school_name=""):
    label = _class_label(class_name, section_name)
    lines = [f"Namaste {father_name or 'Guardian'} ji,"]
    if school_name:
        lines.append(f"{school_name} se suchna:")
    lines.append(
        f"{full_name} (Class {label}) ke liye PTM (Parent-Teacher Meeting) "
        f"{date_text} ko rakhi gayi hai. Kripya upasthit hokar apne bachche ki "
        f"pragati janiye."
    )
    lines.append("Dhanyawad.")
    return "\n".join(lines)


def discipline_message(father_name, full_name, class_name, section_name, category_label, severity_label, school_name=""):
    label = _class_label(class_name, section_name)
    lines = [f"Namaste {father_name or 'Guardian'} ji,"]
    if school_name:
        lines.append(f"{school_name} se suchna:")
    lines.append(
        f"{full_name} (Class {label}) ke sambandh me ek disciplinary vishay "
        f"hai: {category_label} ({severity_label}). Kripya school se sampark "
        f"karein."
    )
    lines.append("Dhanyawad.")
    return "\n".join(lines)


def general_message(father_name, custom_text, school_name=""):
    lines = [f"Namaste {father_name or 'Guardian'} ji,"]
    if school_name:
        lines.append(f"{school_name} se suchna:")
    lines.append(custom_text)
    return "\n".join(lines)


def family_due_message(family_name, members, total_due, school_name=""):
    """members is an iterable of (student_name, class_label, due_amount)."""
    lines = [f"Namaste {family_name} parivar,"]
    if school_name:
        lines.append(f"{school_name} se suchna:")
    for student_name, class_label, due in members:
        if due and due > 0:
            label = f" ({class_label})" if class_label else ""
            lines.append(f"- {student_name}{label}: Rs. {due} due")
    lines.append(f"Total due: Rs. {total_due}. Kripya jald jama karayein.")
    lines.append("Dhanyawad.")
    return "\n".join(lines)
