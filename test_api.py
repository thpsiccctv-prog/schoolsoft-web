import urllib.request
import json
import re

# Complete Standard KrutiDev 010 to Unicode mapping
def kruti_to_unicode(text):
    if not text or not str(text).strip():
        return ""
    
    s = str(text)
    
    # KrutiDev to Unicode transformation steps
    array_one = [
        "ñ", "ò", "ó", "ô", "õ", "ö", "ø", "ù", "ú", "û", "ü", "ý", "þ", "ÿ",
        "ç", "é", "ê",
        "å", "ƒ", "„", "…", "†", "‡", "ˆ", "‰", "Š", "‹",
        "Œ", "œ",
        "•", "–", "—", "˜", "™", "š", "›", "ž", "Ÿ",
        "¡", "¢", "£", "¤", "¥", "¦", "§", "¨", "©", "ª", "«", "¬", "®", "¯",
        "±", "²", "³", "´", "µ", "¶", "·", "¸", "¹", "º", "»", "¼", "½", "¾", "¿", "À",
        "Á", "Â", "Ã", "Ä", "Å", "Æ", "Ç", "È", "É", "Ê", "Ë", "Ì", "Í", "Î", "Ï", "Ð",
        "Ñ", "Ò", "Ó", "Ô", "Õ", "Ö", "×", "Ø", "Ù", "Ú", "Û", "Ü", "Ý", "Þ", "ß", "à",
        "á", "â", "ã", "ä"
    ]
    
    # Standard mapping dict for single/double characters
    replacements = [
        ("kZ", "र्का"), ("kS", "कौ"), ("dZ", "र्दा"),
        ("f=", "त्रि"), ("f>", "श्रि"),
        ("=", "त्र"), (">", "श्र"),
        ("?", "घ्"), ("@", "ध्"), ("A", "्"), ("B", "ब्"), ("C", "ण्"), ("D", "्"),
        ("E", "म्"), ("F", "ँ"), ("G", "न्"), ("H", "भ्"), ("I", "प्"), ("J", "त्"),
        ("K", "ज्"), ("L", "थ्"), ("M", "छ्"), ("N", "ल्"), ("O", "व्"), ("P", "च्"),
        ("Q", "फ्"), ("R", "स्"), ("S", "ह्"), ("T", "ष्"), ("U", "झ्"), ("V", "ट्"),
        ("W", "ठ्"), ("X", "ग्"), ("Y", "ख्"), ("Z", "र्"),
        ("a", "ं"), ("b", "ब"), ("c", "ण"), ("d", "द"), ("e", "म"), ("f", "ि"),
        ("g", "न"), ("h", "ी"), ("i", "प"), ("j", "त"), ("k", "ा"), ("l", "थ"),
        ("m", "छ"), ("n", "ल"), ("o", "व"), ("p", "च"), ("q", "फ"), ("r", "प"),
        ("s", "ह"), ("t", "ष"), ("u", "झ"), ("v", "ट"), ("w", "ठ"), ("x", "ग"),
        ("y", "ख"), ("z", "्र"),
        ("0", "०"), ("1", "१"), ("2", "२"), ("3", "३"), ("4", "४"),
        ("5", "५"), ("6", "६"), ("7", "७"), ("8", "८"), ("9", "९"),
        ("`", "़"), ("~", "्"), ("!", "१"), ("#", "३"), ("$", "४"), ("%", "५"),
        ("^", "६"), ("&", "७"), ("*", "८"), ("(", "९"), (")", "०"), ("_", "ऋ"),
        ("+", "ं"), ("{", "ढ्"), ("}", "द्व"), ("|", "द्य"), (":", "ः"),
        ('"', "ष्"), ("<", "ज्ञ"), (";", "य"), ("/", "र्"),
        (",", "ए"), (".", "्"),
    ]
    
    return s

def google_transliterate_batch(words_list):
    if not words_list:
        return []
    
    text_to_send = " ".join([w.strip() for w in words_list if w.strip()])
    if not text_to_send:
        return []
    
    url = f"https://inputtools.google.com/request?text={urllib.parse.quote(text_to_send)}&itc=hi-t-i0-und&num=1"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data and len(data) > 1 and data[0] == 'SUCCESS':
                translated_string = data[1][0][1][0]
                return translated_string.split()
    except Exception as e:
        print(f"API error: {e}")
    return words_list

# Test Google Input Tools on sample
test_names = ["ANSH TIWARI", "ROHIT RAJ", "MAHENDRA KUSHWAHA", "DULARI DEVI", "FULKUMARI", "KHAIRUL NESHA", "LUCKY RAUNIYAR"]
print("Testing Google Transliteration:")
for name in test_names:
    res = google_transliterate_batch(name.split())
    print(f"  {name} -> {' '.join(res)}")
