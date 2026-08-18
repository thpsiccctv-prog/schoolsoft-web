import os

templates = [
    r'E:\THPSIC-INTER-COLLEGE\01-source-code\schoolsoft_web\templates\core\feeder_school_list.html',
    r'E:\THPSIC-INTER-COLLEGE\01-source-code\schoolsoft_web\templates\core\feeder_school_detail.html',
    r'E:\THPSIC-INTER-COLLEGE\01-source-code\schoolsoft_web\templates\core\feeder_school_payment.html',
]

for t in templates:
    if os.path.exists(t):
        with open(t, 'r', encoding='utf-8') as f:
            c = f.read()
        c = c.replace('{% load humanize %}', '{% load schoolsoft_extras %}')
        c = c.replace('|intcomma', '|indian_number')
        with open(t, 'w', encoding='utf-8') as f:
            f.write(c)
        print(f"Updated {os.path.basename(t)}")

print("All templates updated to schoolsoft_extras!")
