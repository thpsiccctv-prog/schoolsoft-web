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
    Handles all standard character mappings, matras ('f' chhoti-ee, 'Z' reph),
    multi-character consonants ('k, "k, Hk, /k, [k, Fk), conjuncts, halants,
    and UP Board specific ligatures.
    """
    if is_corrupt_string(text):
        return ""

    text = str(text).strip()
    if not text:
        return ""

    # Check if already Unicode Devanagari
    devanagari_chars = sum(1 for c in text if '\u0900' <= c <= '\u097f')
    if devanagari_chars > len(text) * 0.4:
        return text

    modified_substring = text

    # Pre-substitutions for known composite combinations
    special_pre = [
        ("f=k", "त्रि"),
        ("f=", "त्रि"),
        ("f>", "श्रि"),
    ]
    for src, dst in special_pre:
        modified_substring = modified_substring.replace(src, dst)

    # Move "f" (chhoti-ee) after the complete consonant cluster
    # In KrutiDev, "f" is typed before 1-char or 2-char consonants/conjuncts
    cluster_pattern = re.compile(
        r"f("
        r"(?:[A-Z_`~=><\?@'.]|~)*?"
        r"(?:'k|\"k|Hk|/k|\?k|\[k|Fk|\{k|=k|[XPTUCEOILR]k|[çæØ=>K}íêìã]|Vª|Mª|[a-z0-9;])"
        r"(?:z|\+)?)"
    )
    modified_substring = cluster_pattern.sub(r"\1f", modified_substring)
    modified_substring = modified_substring.replace("f", "ि")

    # Move "half R" (Z) to correct position and replace
    modified_substring = "  " + modified_substring + "  "
    position_of_r = modified_substring.find("Z")
    set_of_matras = ["‚", "ks", "kS", "k", "h", "q", "w", "`", "s", "S", "a", "¡", "%", "W", "•", "·", "∙", "~j", "~", "ि"]
    while position_of_r != -1:
        modified_substring = modified_substring.replace("Z", "", 1)
        if position_of_r - 1 < len(modified_substring) and modified_substring[position_of_r - 1] in set_of_matras:
            modified_substring = modified_substring[:position_of_r - 2] + "j~" + modified_substring[position_of_r - 2:]
        else:
            modified_substring = modified_substring[:position_of_r - 1] + "j~" + modified_substring[position_of_r - 1:]
        position_of_r = modified_substring.find("Z")
    modified_substring = modified_substring.strip()

    array_one = [
        "ñ", "Q+Z", "sas", "aa", ")Z", "ZZ", "‘", "’", "“", "”",
        "å", "ƒ", "„", "…", "†", "‡", "ˆ", "‰", "Š", "‹",
        "¶+", "d+", "[+k", "[+", "x+", "T+", "t+", "M+", "<+", "Q+", ";+", "j+", "u+",
        "Ùk", "Ù", "Dr", "–", "—", "é", "™", "=kk",
        "à", "á", "â", "ã", "ºz", "º", "í", "{k", "{", "=", "«",
        "Nî", "Vî", "Bî", "Mî", "<î", "|", "K", "}",
        "J", "Vª", "Mª", "<ªª", "Nª", "Ø", "Ý", "nzZ", "æ", "ç", "Á", "xz", "#", ":",
        "v‚", "vks", "vkS", "vk", "v", "b±", "Ã", "bZ", "b", "m", "Å", ",s", ",", "_",
        "ô", "d", "Dk", "D", "[k", "[", "x", "Xk", "X", "Ä", "?k", "?", "³",
        "pkS", "p", "Pk", "P", "N", "t", "Tk", "T", ">", "÷", "¥",
        "ê", "ë", "V", "B", "ì", "ï", "M", "<", ".k", ".",
        "r", "Rk", "R", "Fk", "F", ")", "n", "/k", "èk", "/", "Ë", "è", "u", "Uk", "U",
        "i", "Ik", "I", "Q", "¶", "c", "Ck", "C", "Hk", "H", "e", "Ek", "E",
        ";", "¸", "j", "y", "Yk", "Y", "G", "o", "Ok", "O",
        "'k", "'", "\"k", "\"", "l", "Lk", "L", "g",
        "È", "z",
        "Ì", "Í", "Î", "Ï", "Ñ", "Ò", "Ó", "Ô", "Ö", "Ø", "Ük", "Ü",
        "‚", "ks", "kS", "k", "h", "q", "w", "`", "s", "S",
        "a", "¡", "%", "W", "•", "·", "∙", "~j", "~", "\\", "+", " ः",
        "^", "*", "Þ", "ß", "(", "¼", "½", "¿", "À", "¾", "A", "-", "&", "Œ", "]", "~ ", "@"
    ]

    array_two = [
        "॰", "QZ+", "sa", "a", "र्द्ध", "Z", "\"", "\"", "'", "'",
        "०", "१", "२", "३", "४", "५", "६", "७", "८", "९",
        "फ़्", "क़", "ख़", "ख़्", "ग़", "ज़्", "ज़", "ड़", "ढ़", "फ़", "य़", "ऱ", "ऩ",
        "त्त", "त्त्", "क्त", "दृ", "कृ", "न्न", "न्न्", "=k",
        "ह्न", "ह्य", "हृ", "ह्म", "ह्र", "ह्", "द्द", "क्ष", "क्ष्", "त्र", "त्र्",
        "छ्य", "ट्य", "ठ्य", "ड्य", "ढ्य", "द्य", "ज्ञ", "द्व",
        "श्र", "ट्र", "ड्र", "ढ्र", "छ्र", "क्र", "फ्र", "र्द्र", "द्र", "प्र", "प्र", "ग्र", "रु", "रू",
        "ऑ", "ओ", "औ", "आ", "अ", "ईं", "ई", "ई", "इ", "उ", "ऊ", "ऐ", "ए", "ऋ",
        "क्क", "क", "क", "क्", "ख", "ख्", "ग", "ग", "ग्", "घ", "घ", "घ्", "ङ",
        "चै", "च", "च", "च्", "छ", "ज", "ज", "ज्", "झ", "झ्", "ञ",
        "ट्ट", "ट्ठ", "ट", "ठ", "ड्ड", "ड्ढ", "ड", "ढ", "ण", "ण्",
        "त", "त", "त्", "थ", "थ्", "द्ध", "द", "ध", "ध", "ध्", "ध्", "ध्", "न", "न", "न्",
        "प", "प", "प्", "फ", "फ्", "ब", "ब", "ब्", "भ", "भ्", "म", "म", "म्",
        "य", "य्", "र", "ल", "ल", "ल्", "ळ", "व", "व", "व्",
        "श", "श्", "ष", "ष्", "स", "स", "स्", "ह",
        "ीं", "्र",
        "द्द", "ट्ट", "ट्ठ", "ड्ड", "कृ", "भ", "्य", "ड्ढ", "झ्", "क्र", "श", "श्",
        "ॉ", "ो", "ौ", "ा", "ी", "ु", "ू", "ृ", "े", "ै",
        "ं", "ँ", "ः", "ॅ", "ऽ", "ऽ", "ऽ", "्र", "्", "?", "़", ":",
        "‘", "’", "“", "”", ";", "(", ")", "{", "}", "=", "।", ".", "-", "॰", ",", "् ", "/"
    ]

    for input_symbol_idx in range(len(array_one)):
        modified_substring = modified_substring.replace(array_one[input_symbol_idx], array_two[input_symbol_idx])

    res = modified_substring.replace("््", "्")
    res = re.sub(r"\s+", " ", res).strip()
    return res
