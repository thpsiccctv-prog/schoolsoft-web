from decimal import Decimal, InvalidOperation

from django import template

from ..whatsapp import build_wa_link, discipline_message, fee_due_message, general_message, ptm_message

register = template.Library()


@register.filter
def indian_number(value):
    if value is None or value == "":
        return "0"

    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return value

    sign = "-" if number < 0 else ""
    number = abs(number)
    has_fraction = number != number.to_integral_value()
    text = f"{number:.2f}" if has_fraction else f"{number:.0f}"
    whole, _, fraction = text.partition(".")

    if len(whole) > 3:
        last_three = whole[-3:]
        prefix = whole[:-3]
        groups = []
        while len(prefix) > 2:
            groups.insert(0, prefix[-2:])
            prefix = prefix[:-2]
        if prefix:
            groups.insert(0, prefix)
        whole = ",".join(groups + [last_three])

    return f"{sign}{whole}.{fraction}" if fraction else f"{sign}{whole}"


@register.simple_tag
def wa_fee_link(mobile, father_name, full_name, class_name, section_name, admission_no, due_amount, school_name=""):
    message = fee_due_message(father_name, full_name, class_name, section_name, admission_no, due_amount, school_name)
    return build_wa_link(mobile, message) or ""


@register.simple_tag
def wa_ptm_link(mobile, father_name, full_name, class_name, section_name, date_text, school_name=""):
    message = ptm_message(father_name, full_name, class_name, section_name, date_text, school_name)
    return build_wa_link(mobile, message) or ""


@register.simple_tag
def wa_discipline_link(mobile, father_name, full_name, class_name, section_name, category_label, severity_label, school_name=""):
    message = discipline_message(father_name, full_name, class_name, section_name, category_label, severity_label, school_name)
    return build_wa_link(mobile, message) or ""


@register.simple_tag
def wa_general_link(mobile, father_name, custom_text, school_name=""):
    message = general_message(father_name, custom_text, school_name)
    return build_wa_link(mobile, message) or ""
