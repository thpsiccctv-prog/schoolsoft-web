from decimal import Decimal, InvalidOperation

from django import template

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
