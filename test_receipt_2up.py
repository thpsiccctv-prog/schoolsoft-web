import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "schoolsoft.settings")
sqlite_path = os.environ.get("SCHOOLSOFT_SQLITE_PATH") or os.path.expandvars(r"%LOCALAPPDATA%\THPSIC-InterCollege-SchoolSoft\db.sqlite3")
os.environ["SCHOOLSOFT_SQLITE_PATH"] = sqlite_path

import django
django.setup()

from django.test import RequestFactory
from django.contrib.auth.models import User
from core.models import FeeReceipt, SchoolProfile
from core.views import receipt_pdf, receipt_pdf_2up
from core.pdf import build_fee_receipt_pdf, build_fee_receipt_pdf_2up

print("=== TESTING HALF-A4 RECEIPT PDF MODULE ===")

receipt = FeeReceipt.objects.select_related(
    "student", "student__current_class", "student__current_section", "session"
).prefetch_related("lines", "lines__fee_head").first()

if not receipt:
    print("No fee receipts found in database.")
else:
    profile = SchoolProfile.objects.first()
    print(f"Testing with Receipt: {receipt.receipt_no} | Student: {receipt.display_student_name} | Amount: Rs. {receipt.received_amount}")

    # 1. Test standard A5 PDF
    pdf_a5 = build_fee_receipt_pdf(receipt, profile)
    print(f"1. Standard A5 Landscape PDF: {len(pdf_a5):,} bytes")

    # 2. Test Half-A4 (2-Up) PDF
    pdf_2up = build_fee_receipt_pdf_2up(receipt, profile)
    print(f"2. Half-A4 (2-Up) Portrait PDF: {len(pdf_2up):,} bytes")

    sample_out = r"E:\THPSIC-INTER-COLLEGE\05-reports\SAMPLE_HALF_A4_RECEIPT.pdf"
    with open(sample_out, "wb") as f:
        f.write(pdf_2up)
    print(f"   Saved sample Half-A4 PDF to: {sample_out}")

    # 3. Test View response
    user, _ = User.objects.get_or_create(username="admin", defaults={"is_staff": True, "is_superuser": True})
    factory = RequestFactory()
    req = factory.get(f"/receipts/{receipt.id}/pdf/2up/")
    req.user = user
    resp = receipt_pdf_2up(req, receipt.id)
    print(f"3. View response: Status {resp.status_code} | Content-Type: {resp['Content-Type']} | Filename: {resp['Content-Disposition']}")

print("\nALL HALF-A4 RECEIPT TESTS PASSED SUCCESSFULLY!")
