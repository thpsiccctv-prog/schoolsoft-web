import re

def is_corrupt_string(text):
    if not text:
        return True
    s = str(text).strip()
    if not s or s == "0":
        return True
    # If the text consists exclusively of '?' marks and spaces/digits, it's corrupted Unicode loss
    clean = re.sub(r"[\s\d_]", "", s)
    if clean and all(c == '?' for c in clean):
        return True
    return False


def krutidev_to_unicode(text):
    """
    Converts KrutiDev 010 encoded legacy Hindi strings to clean UTF-8 Devanagari Unicode.
    Handles matras ('f' chhoti-ee, 'Z' reph, conjuncts, halants, and numbers).
    """
    if is_corrupt_string(text):
        return ""

    text = str(text).strip()

    # If already Unicode Devanagari
    devanagari_chars = sum(1 for c in text if '\u0900' <= c <= '\u097f')
    if devanagari_chars > len(text) * 0.4:
        return text

    modified_text = text

    # Step 1: Special compound characters / ligatures
    special_map = [
        ("ñ", "ह्न"), ("ò", "ह्र"), ("ó", "ह्ल"), ("ô", "ह्व"),
        ("õ", "क्त"), ("ö", "रु"), ("ø", "रू"),
        ("ù", "हृ"), ("ú", "ष्ट"), ("û", "ष्ठ"),
        ("ü", "द्ग"), ("ý", "द्द"), ("þ", "द्ध"),
        ("ÿ", "द्ब"), ("ç", "द्म"), ("é", "द्य"), ("ê", "द्व"),
        ("å", "०"), ("ƒ", "१"), ("„", "२"), ("…", "३"),
        ("†", "४"), ("‡", "५"), ("ˆ", "६"), ("‰", "७"),
        ("Š", "८"), ("‹", "९"),
        ("•", "ै"), ("š", "श"), ("›", "श"), ("¡", "।"),
        ("f=", "त्रि"), ("f>", "श्रि"),
        ("=", "त्र"), (">", "श्र"),
    ]
    for src, dst in special_map:
        modified_text = modified_text.replace(src, dst)

    # Step 2: Handle 'f' (chhoti-ee matra)
    # Move 'f' to appear as '\u093F' after the following consonant or conjunct
    modified_text = re.sub(
        r"f('k|\"k|Hk|\/k|\?k|(?:[A-Z_`~=><\?@']|(?:[a-z][\+~]))*?([a-z0-9]|(?:\[\[)|(?:\])|[=><]))",
        lambda m: m.group(1) + "\u093f",
        modified_text
    )

    # Step 3: Handle 'Z' (reph - half 'r' on top)
    modified_text = re.sub(r"('k|\"k|Hk|\/k|\?k|[a-zA-Z_`~=><\?@'])([khsSwqaF]*)Z", r"Z\1\2", modified_text)

    # Step 4: Primary character and matra mapping
    rules = [
        # Numbers
        ("0", "०"), ("1", "१"), ("2", "२"), ("3", "३"), ("4", "४"),
        ("5", "५"), ("6", "६"), ("7", "७"), ("8", "८"), ("9", "९"),

        # Vowels & independent forms
        ("vkS", "औ"), ("vks", "ओ"), ("vk", "आ"), ("v", "अ"),
        ("bZ", "ई"), ("b", "इ"), ("mQ", "ऊ"), ("m", "उ"),
        (",s", "ऐ"), (",", "ए"), ("_", "ऋ"),

        # Matras
        ("kS", "ौ"), ("ks", "ो"), ("k", "ा"),
        ("S", "ै"), ("s", "े"),
        ("h", "ी"), ("f", "ि"),
        ("w", "ू"), ("q", "ु"),
        ("a", "ं"), ("A", "्"),
        ("`", "़"), ("~", "्"),

        # Sh & Conjuncts
        ("'k", "श"), ("\"k", "ष"), ("'K", "श्"),
        ("'", "श्"), ("\"", "ष्"),
        ("Hk", "भ"), ("H", "भ्"),
        ("/k", "ध"), ("/", "ध्"), ("@", "ध्"),
        ("?k", "घ"), ("?", "घ्"),
        ("M+", "ड़"), ("{+", "ढ़"),
        ("M", "छ्"), ("N", "छ"),
        ("K", "ज्ञ"), ("<", "ज्ञ"),
        ("=", "त्र"), (">", "श्र"),

        # Consonants (full)
        ("d", "क"), ("y", "ल"), ("x", "ग"), ("c", "ब"),
        ("p", "च"), ("t", "ज"), ("u", "न"),
        ("j", "र"), ("l", "स"), ("n", "द"), ("g", "ह"),
        ("i", "प"), ("q", "फ"), ("e", "म"),
        ("r", "त"), ("o", "व"), (";", "य"),
        ("z", "्र"), ("Z", "र्"),

        # Consonants (half / uppercase / special)
        ("D", "क्"), ("Y", "ल्"), ("X", "ग्"), ("B", "ब्"),
        ("P", "च्"), ("T", "ज्"), ("U", "न्"),
        ("J", "र्"), ("L", "स्"), ("G", "ह्"),
        ("I", "प्"), ("Q", "फ्"), ("E", "म्"),
        ("R", "त्"), ("O", "व्"),
        ("V", "ट"), ("W", "ठ"),
        ("{", "क्ष"), ("}", "द्व"),
        ("[", "ख"), ("]", "ढ"),
        (":", "ः"),

        # Punctuation & symbols
        ("+", "ं"), ("!", "१"), ("#", "३"),
        ("$", "४"), ("%", "५"), ("^", "६"), ("&", "७"),
        ("*", "८"), ("(", "९"), (")", "०"),
        (".", "्"), ("\\", "्"),
    ]

    out = []
    i = 0
    L = len(modified_text)
    while i < L:
        matched = False
        for src, dst in rules:
            if modified_text.startswith(src, i):
                out.append(dst)
                i += len(src)
                matched = True
                break
        if not matched:
            out.append(modified_text[i])
            i += 1

    res = "".join(out)
    res = res.replace("््", "्")
    res = re.sub(r"\s+", " ", res).strip()
    return res
