with open(r'E:\THPSIC-INTER-COLLEGE\01-source-code\schoolsoft_web\core\views.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = '''def receipt_pdf(request, pk):
    receipt = get_object_or_404(
        FeeReceipt.objects.select_related(
            "student",
            "student__current_class",
            "student__current_section",
            "session",
        ).prefetch_related("lines", "lines__fee_head"),
        pk=pk,
    )
    pdf_bytes = build_fee_receipt_pdf(receipt, get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{receipt.receipt_no}.pdf"'
    return response'''

replacement = '''def receipt_pdf(request, pk):
    receipt = get_object_or_404(
        FeeReceipt.objects.select_related(
            "student",
            "student__current_class",
            "student__current_section",
            "session",
        ).prefetch_related("lines", "lines__fee_head"),
        pk=pk,
    )
    pdf_bytes = build_fee_receipt_pdf(receipt, get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{receipt.receipt_no}.pdf"'
    return response


def receipt_pdf_2up(request, pk):
    receipt = get_object_or_404(
        FeeReceipt.objects.select_related(
            "student",
            "student__current_class",
            "student__current_section",
            "session",
        ).prefetch_related("lines", "lines__fee_head"),
        pk=pk,
    )
    pdf_bytes = build_fee_receipt_pdf_2up(receipt, get_active_school_profile())
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="receipt_{receipt.receipt_no}_2up.pdf"'
    return response'''

if target in content:
    content = content.replace(target, replacement, 1)
    with open(r'E:\THPSIC-INTER-COLLEGE\01-source-code\schoolsoft_web\core\views.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("receipt_pdf_2up added to core/views.py successfully!")
else:
    print("Target not found in core/views.py")
