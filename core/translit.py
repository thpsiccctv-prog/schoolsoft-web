import re

# Common UP / Indian School Surnames & Titles vocabulary mapping
VOCAB_MAP = {
    "KUMAR": "कुमार", "KUMARI": "कुमारी", "DEVI": "देवी", "SINGH": "सिंह",
    "KUSHWAHA": "कुशवाहा", "YADAV": "यादव", "GUPTA": "गुप्ता", "SHARMA": "शर्मा",
    "TIWARI": "तिवारी", "PANDEY": "पाण्डेय", "DUBEY": "दुबे", "UPADHYAY": "उपाध्याय",
    "MISHRA": "मिश्रा", "VERMA": "वर्मा", "PATEL": "पटेल", "PRASAD": "प्रसाद",
    "ANSARI": "अंसारी", "KHATOON": "खातून", "ALI": "अली", "ALAM": "आलम",
    "AHMAD": "अहमद", "AHMED": "अहमद", "SHAH": "शाह", "KHAN": "खान",
    "BEGUM": "बेगम", "PRAVEEN": "परवीन", "PARVEEN": "परवीन", "CHAUHAN": "चौहान",
    "MADDHESHIYA": "मधेशिया", "MADHESHIYA": "मधेशिया", "RAUNIYAR": "रौनियार",
    "JAISWAL": "जायसवाल", "PRAJAPATI": "प्रजापति", "VISHWAKARMA": "विश्वकर्मा",
    "SRIVASTAVA": "श्रीवास्तव", "KHARWAR": "खरवार", "NISHAD": "निषाद",
    "GOND": "गोंड", "BHARTI": "भारती", "RAM": "राम", "LAL": "लाल",
    "CHAUDHARY": "चौधरी", "CHOUDHARY": "चौधरी", "PASWAN": "पासवान",
    "KANNAUJIYA": "कन्नौजिया", "SAHANI": "साहनी", "SAH": "साह", "PAL": "पाल",
    "GIRI": "गिरी", "GOSWAMI": "गोस्वामी", "BAITHA": "बैठा", "DHOBI": "धोबी",
    "HAJAM": "हजाम", "THAKUR": "ठाकुर", "MALLAH": "मल्लाह", "BIND": "बिंद",
    "RAWAT": "रावत", "MAURYA": "मौर्या", "RAO": "राव", "SHEKH": "शेख", "SHAIKH": "शेख",
    "SIDDIQUI": "सिद्दीकी", "QURESHI": "कुरैशी", "IDRISI": "इदरीसी", "MANSOORI": "मंसूरी",
    
    # Common First Names
    "HARIOM": "हरिओम", "MANISHA": "मनीषा", "SANJANA": "संजना", "PRIYANKA": "प्रियंका",
    "ANJALI": "अंजलि", "POOJA": "पूजा", "NEHA": "नेहा", "ARCHANA": "अर्चना",
    "ROHIT": "रोहित", "RAHUL": "राहुल", "AMIT": "अमित", "SUMIT": "सुमित",
    "VIKASH": "विकास", "VIKAS": "विकास", "VISHAL": "विशाल", "AKASH": "आकाश",
    "AJEET": "अजीत", "AJAY": "अजय", "VIJAY": "विजय", "SANJAY": "संजय",
    "SUNIL": "सुनील", "ANIL": "अनिल", "DEEPAK": "दीपक", "DIPAK": "दीपक",
    "AMARJEET": "अमरजीत", "RAMJEET": "रामजीत", "BALIRAM": "बलीराम",
    "KRISHNA": "कृष्णा", "SHIVAM": "शिवम", "SATYAM": "सत्यम", "SUNDARAM": "सुन्दरम",
    "PRINCE": "प्रिंस", "RITIK": "ऋतिक", "HRITIK": "ऋतिक", "SACHIN": "सचिन",
    "ANURAG": "अनुराग", "ABHISHEK": "अभिषेक", "ASHISH": "आशीष", "ALOK": "आलोक",
    "MOHAMMAD": "मोहम्मद", "MOHD": "मोहम्मद", "MD": "मोहम्मद", "SALMAN": "सलमान",
    "IMRAN": "इमरान", "KAMRAN": "कामरान", "FAIZAN": "फैजान", "ARBAZ": "अरबाज",
    "SAMEER": "समीर", "DANISH": "दानिश", "TARIQ": "तारिक", "JUNAID": "जुनैद",
    "REETA": "रीता", "RITA": "रीता", "GEETA": "गीता", "SEETA": "सीता",
    "SUSHILA": "सुशीला", "SHAKUNTLA": "शकुंतला", "KISHORI": "किशोरी",
    "SHUGANTI": "सुगंती", "SUGANTI": "सुगंती", "KALAWATI": "कलावती",
    "VIDYAWATI": "विद्यावती", "LAKHPATTI": "लखपती", "PHULPATI": "फूलपती",
    "BUNNILAL": "बुन्नीलाल", "LALLAN": "लल्लन", "CHANDRIKA": "चन्द्रिका",
    "MAINEJAR": "मैनेजर", "SURESH": "सुरेश", "RAMESH": "रमेश", "MAHESH": "महेश",
    "DINESH": "दिनेश", "KAMLESH": "कमलेश", "NAGESHWAR": "नागेश्वर", "GIRISH": "गिरीश",
    "HARILAL": "हरीलाल", "MOTILAL": "मोतीलाल", "HEERALAL": "हीरालाल", "HIRA": "हीरा",
}

# Phonetic Rules for words not in dictionary
def phonetic_transliterate_word(w):
    w = w.strip().upper()
    if not w:
        return ""
    if w in VOCAB_MAP:
        return VOCAB_MAP[w]
    
    # Custom rule-based phonetics
    rules = [
        ("KSH", "क्ष"), ("TR", "त्र"), ("GY", "ज्ञ"), ("SHR", "श्र"),
        ("CHH", "छ"), ("KH", "ख"), ("GH", "घ"), ("CH", "च"),
        ("JH", "झ"), ("TH", "थ"), ("DH", "ध"), ("PH", "फ"),
        ("BH", "भ"), ("SH", "श"),
        
        ("K", "क"), ("G", "ग"), ("C", "क"), ("J", "ज"), ("Z", "ज़"),
        ("T", "त"), ("D", "द"), ("N", "न"), ("P", "प"), ("F", "फ"),
        ("B", "ब"), ("M", "म"), ("Y", "य"), ("R", "र"), ("L", "ल"),
        ("V", "व"), ("W", "व"), ("S", "स"), ("H", "ह"),
        
        ("AA", "ा"), ("EE", "ी"), ("OO", "ू"), ("AI", "ै"), ("AU", "ौ"),
        ("A", "ा"), ("I", "ि"), ("U", "ु"), ("E", "े"), ("O", "ो"),
    ]
    
    # Let's handle character by character phonetics
    res = []
    i = 0
    L = len(w)
    while i < L:
        matched = False
        # Try 3-char, 2-char, 1-char
        for length in (3, 2, 1):
            if i + length <= L:
                sub = w[i:i+length]
                for k, v in rules:
                    if k == sub:
                        # If first letter is a vowel, use full vowel form
                        if i == 0:
                            vowel_init = {
                                "A": "अ", "AA": "आ", "I": "इ", "EE": "ई",
                                "U": "उ", "OO": "ऊ", "E": "ए", "AI": "ऐ",
                                "O": "ओ", "AU": "औ", "RI": "ऋ"
                            }
                            if sub in vowel_init:
                                res.append(vowel_init[sub])
                                i += length
                                matched = True
                                break
                        res.append(v)
                        i += length
                        matched = True
                        break
            if matched:
                break
        if not matched:
            res.append(w[i])
            i += 1
            
    out_str = "".join(res)
    # If ends with 'ा' and was short 'A', trim if needed
    return out_str

def english_to_hindi(text):
    if not text:
        return ""
    words = text.strip().split()
    converted = []
    for w in words:
        w_clean = re.sub(r"[^A-Za-z]", "", w).upper()
        if not w_clean:
            continue
        if w_clean in VOCAB_MAP:
            converted.append(VOCAB_MAP[w_clean])
        else:
            converted.append(phonetic_transliterate_word(w_clean))
    return " ".join(converted)
