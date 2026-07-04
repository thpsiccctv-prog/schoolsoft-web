from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import (
    AcademicSession,
    ExamMark,
    ExamTerm,
    ExamTest,
    FeeHead,
    FeeReceipt,
    FeeReceiptLine,
    FeeStructure,
    SalaryPayment,
    SchoolClass,
    SchoolProfile,
    Staff,
    Student,
    StudentTransport,
    Subject,
    TransferCertificate,
    TransportBus,
    TransportRoute,
)


class AuthenticatedClientMixin:
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_superuser(
            username="tester",
            email="tester@example.com",
            password="testpass123",
        )
        self.client.force_login(self.user)


class WorkspaceAuthTests(TestCase):
    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("core:dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("core:login"), response["Location"])


class DashboardTests(AuthenticatedClientMixin, TestCase):
    def test_dashboard_loads(self):
        response = self.client.get(reverse("core:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dashboard")

    def test_student_list_loads(self):
        response = self.client.get(reverse("core:student_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Students")

    def test_student_detail_loads_from_list(self):
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(
            legacy_sid=1001,
            admission_no="A-1001",
            full_name="Detail Student",
            father_name="Detail Father",
            current_class=school_class,
            mobile_primary="9999999999",
        )

        list_response = self.client.get(reverse("core:student_list"), {"q": "Detail Student"})
        detail_response = self.client.get(reverse("core:student_detail", args=[student.id]))

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, reverse("core:student_detail", args=[student.id]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Detail Student")
        self.assertContains(detail_response, "Detail Father")
        self.assertContains(detail_response, "Form PDF")
        self.assertContains(detail_response, "Marksheet")

    def test_school_profile_page_loads(self):
        SchoolProfile.objects.create(
            legacy_comp_code=9,
            name="THPS ENGLISH MEDIUM SCHOOL",
            address_line1="DUDAHI 274302",
            address_line2="KUSHINAGAR",
            address_line3="(U.P)",
            phone="7379568527",
            email="thpses@gmail.com",
            current_year="2026-27",
            is_active=True,
        )

        response = self.client.get(reverse("core:school_profile_detail"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "THPS ENGLISH MEDIUM SCHOOL")
        self.assertContains(response, "7379568527")
        self.assertContains(response, "thpses@gmail.com")
        self.assertContains(response, "2026-27")

    def test_fee_structure_report_loads_and_filters(self):
        session = AcademicSession.objects.create(name="2026-27", is_active=True)
        class_one = SchoolClass.objects.create(name="I", display_order=1)
        class_two = SchoolClass.objects.create(name="II", display_order=2)
        tuition = FeeHead.objects.create(name="Tuition Fee")
        zero_head = FeeHead.objects.create(name="Zero Fee")
        FeeStructure.objects.create(
            session=session,
            school_class=class_one,
            fee_head=tuition,
            amount=Decimal("500.00"),
        )
        FeeStructure.objects.create(
            session=session,
            school_class=class_one,
            fee_head=zero_head,
            amount=Decimal("0.00"),
        )
        FeeStructure.objects.create(
            session=session,
            school_class=class_two,
            fee_head=tuition,
            amount=Decimal("700.00"),
        )

        response = self.client.get(reverse("core:fee_structure_report"), {"class": class_one.id})
        all_rows_response = self.client.get(
            reverse("core:fee_structure_report"),
            {"class": class_one.id, "rows": "all"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fee Structure")
        self.assertContains(response, "Tuition Fee")
        self.assertContains(response, "500.00")
        self.assertNotContains(response, "700.00")
        self.assertNotContains(response, "Zero Fee")

        self.assertEqual(all_rows_response.status_code, 200)
        self.assertContains(all_rows_response, "Zero Fee")


class FeeReceiptTests(AuthenticatedClientMixin, TestCase):
    def test_payable_amount_uses_lines_late_fee_and_concession(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Test Student", current_class=school_class)
        tuition = FeeHead.objects.create(name="Tuition Fee")
        exam = FeeHead.objects.create(name="Exam Fee")
        receipt = FeeReceipt.objects.create(
            receipt_no="R-1",
            student=student,
            session=session,
            concession_amount=Decimal("20.00"),
            late_fee_amount=Decimal("5.00"),
            received_amount=Decimal("185.00"),
        )
        FeeReceiptLine.objects.create(receipt=receipt, fee_head=tuition, amount=Decimal("150.00"))
        FeeReceiptLine.objects.create(receipt=receipt, fee_head=exam, amount=Decimal("50.00"))

        self.assertEqual(receipt.line_total, Decimal("200.00"))
        self.assertEqual(receipt.payable_amount, Decimal("185.00"))

    def test_receipt_pages_load(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Test Student", current_class=school_class)
        fee_head = FeeHead.objects.create(name="Tuition Fee")
        receipt = FeeReceipt.objects.create(
            receipt_no="R-2",
            student=student,
            session=session,
            received_amount=Decimal("100.00"),
            legacy_fee_total=Decimal("100.00"),
            legacy_net_total=Decimal("100.00"),
        )
        FeeReceiptLine.objects.create(receipt=receipt, fee_head=fee_head, amount=Decimal("100.00"))

        list_response = self.client.get(reverse("core:receipt_list"))
        detail_response = self.client.get(reverse("core:receipt_detail", args=[receipt.id]))
        pdf_response = self.client.get(reverse("core:receipt_pdf", args=[receipt.id]))

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertContains(detail_response, "R-2")
    def test_receipt_list_filters(self):
        session = AcademicSession.objects.create(name="2026-27")
        class_one = SchoolClass.objects.create(name="I", display_order=1)
        class_two = SchoolClass.objects.create(name="II", display_order=2)
        first_student = Student.objects.create(full_name="First Fee Student", current_class=class_one)
        second_student = Student.objects.create(full_name="Second Fee Student", current_class=class_two)
        FeeReceipt.objects.create(
            receipt_no="FILTER-1",
            student=first_student,
            session=session,
            receipt_date="2026-07-01",
            payment_mode=FeeReceipt.PaymentMode.CASH,
            received_amount=Decimal("100.00"),
            legacy_net_total=Decimal("100.00"),
        )
        FeeReceipt.objects.create(
            receipt_no="FILTER-2",
            student=second_student,
            session=session,
            receipt_date="2026-08-01",
            payment_mode=FeeReceipt.PaymentMode.ONLINE,
            received_amount=Decimal("200.00"),
            legacy_net_total=Decimal("200.00"),
        )

        response = self.client.get(
            reverse("core:receipt_list"),
            {
                "date_from": "2026-07-01",
                "date_to": "2026-07-31",
                "class": class_one.id,
                "payment_mode": FeeReceipt.PaymentMode.CASH,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "FILTER-1")
        self.assertContains(response, "First Fee Student")
        self.assertNotContains(response, "FILTER-2")
        self.assertNotContains(response, "Second Fee Student")

    def test_manual_receipt_create(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Test Student", current_class=school_class)
        fee_head = FeeHead.objects.create(name="Tuition Fee")

        get_response = self.client.get(reverse("core:receipt_create"))
        self.assertEqual(get_response.status_code, 200)
        self.assertContains(get_response, "Student Search")
        self.assertContains(get_response, "data-fee-total")

        post_response = self.client.post(
            reverse("core:receipt_create"),
            data={
                "student": student.id,
                "session": session.id,
                "receipt_date": "2026-07-01",
                "from_month": "JULY",
                "to_month": "JULY",
                "payment_mode": FeeReceipt.PaymentMode.CASH,
                "concession_amount": "10.00",
                "late_fee_amount": "0.00",
                "received_amount": "90.00",
                "remarks": "Test receipt",
                f"fee_head_{fee_head.id}": "100.00",
            },
        )

        receipt = FeeReceipt.objects.get(remarks="Test receipt")
        self.assertRedirects(post_response, reverse("core:receipt_detail", args=[receipt.id]))
        self.assertEqual(receipt.receipt_no[:3], "MR-")
        self.assertEqual(receipt.legacy_net_total, Decimal("90.00"))
        self.assertEqual(receipt.lines.count(), 1)

    def test_student_fee_defaults_api(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Test Student", current_class=school_class)
        fee_head = FeeHead.objects.create(name="Tuition Fee")
        FeeStructure.objects.create(
            session=session,
            school_class=school_class,
            fee_head=fee_head,
            amount=Decimal("500.00"),
        )

        response = self.client.get(
            reverse("core:student_fee_defaults", args=[student.id]),
            {"session": session.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["amounts"][f"fee_head_{fee_head.id}"], "500.00")

    def test_due_report_loads(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Due Student", current_class=school_class)
        FeeReceipt.objects.create(
            receipt_no="DUE-1",
            student=student,
            session=session,
            received_amount=Decimal("50.00"),
            legacy_net_total=Decimal("100.00"),
            legacy_due_amount=Decimal("50.00"),
        )

        response = self.client.get(reverse("core:due_report"))
        pdf_response = self.client.get(reverse("core:due_report_pdf"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertContains(response, "Due Report")
        self.assertContains(response, "Due Student")

class Month2DocumentTests(AuthenticatedClientMixin, TestCase):
    def test_admission_form_pdf(self):
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Doc Student", current_class=school_class)

        response = self.client.get(reverse("core:admission_form_pdf", args=[student.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_character_certificate_pdf(self):
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Doc Student", current_class=school_class)

        response = self.client.get(reverse("core:character_certificate_pdf", args=[student.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_tc_create_and_pdf(self):
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Leaving Student", current_class=school_class)

        get_response = self.client.get(reverse("core:tc_detail", args=[student.id]))
        self.assertEqual(get_response.status_code, 200)

        post_response = self.client.post(
            reverse("core:tc_detail", args=[student.id]),
            data={
                "issue_date": "2026-07-01",
                "last_class_studied": school_class.id,
                "last_section": "",
                "reason_for_leaving": "Family relocation",
                "conduct": TransferCertificate.Conduct.GOOD,
                "general_progress": TransferCertificate.Conduct.GOOD,
                "qualified_for_promotion": "on",
                "promoted_to_class": "",
                "fees_paid_upto": "June 2026",
                "remarks": "",
            },
        )
        self.assertRedirects(post_response, reverse("core:tc_detail", args=[student.id]))

        tc = TransferCertificate.objects.get(student=student)
        self.assertTrue(tc.tc_number.startswith("TC-"))

        pdf_response = self.client.get(reverse("core:tc_pdf", args=[student.id]))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")

    def test_marksheet_pdf(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Marks Student", current_class=school_class)
        subject = Subject.objects.create(name="Mathematics")
        term = ExamTerm.objects.create(session=session, name="Half Yearly")
        exam_test = ExamTest.objects.create(
            term=term,
            school_class=school_class,
            subject=subject,
            max_marks=Decimal("100.00"),
        )
        ExamMark.objects.create(exam_test=exam_test, student=student, marks_obtained=Decimal("85.00"))

        select_response = self.client.get(reverse("core:marksheet_select", args=[student.id]))
        self.assertEqual(select_response.status_code, 200)
        self.assertContains(select_response, "Half Yearly")

        pdf_response = self.client.get(reverse("core:marksheet_pdf", args=[student.id, term.id]))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")

    def test_marks_report_loads_and_filters(self):
        session = AcademicSession.objects.create(name="2026-27")
        class_one = SchoolClass.objects.create(name="I", display_order=1)
        class_two = SchoolClass.objects.create(name="II", display_order=2)
        first_student = Student.objects.create(
            full_name="Marks Report Student",
            father_name="Report Father",
            current_class=class_one,
        )
        second_student = Student.objects.create(full_name="Other Report Student", current_class=class_two)
        subject = Subject.objects.create(name="Mathematics")
        term = ExamTerm.objects.create(session=session, name="Quarterly")
        first_test = ExamTest.objects.create(
            term=term,
            school_class=class_one,
            subject=subject,
            max_marks=Decimal("100.00"),
        )
        second_test = ExamTest.objects.create(
            term=term,
            school_class=class_two,
            subject=subject,
            max_marks=Decimal("100.00"),
        )
        ExamMark.objects.create(
            exam_test=first_test,
            student=first_student,
            marks_obtained=Decimal("80.00"),
        )
        ExamMark.objects.create(
            exam_test=second_test,
            student=second_student,
            marks_obtained=Decimal("70.00"),
        )

        response = self.client.get(
            reverse("core:marks_report"),
            {"term": term.id, "class": class_one.id, "q": "Marks Report"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Marks Report Student")
        self.assertContains(response, "80.00")
        self.assertContains(response, "PDF")
        self.assertNotContains(response, "Other Report Student")

    def test_exam_mark_auto_grade(self):
        session = AcademicSession.objects.create(name="2026-27")
        school_class = SchoolClass.objects.create(name="I", display_order=1)
        student = Student.objects.create(full_name="Grade Student", current_class=school_class)
        subject = Subject.objects.create(name="Science")
        term = ExamTerm.objects.create(session=session, name="Annual")
        exam_test = ExamTest.objects.create(
            term=term,
            school_class=school_class,
            subject=subject,
            max_marks=Decimal("100.00"),
        )
        mark = ExamMark.objects.create(exam_test=exam_test, student=student, marks_obtained=Decimal("92.00"))

        self.assertEqual(mark.grade, "A1")


class StaffTests(AuthenticatedClientMixin, TestCase):
    def test_staff_list_loads(self):
        Staff.objects.create(full_name="Test Teacher", designation="Teacher", basic_pay=Decimal("15000.00"))

        response = self.client.get(reverse("core:staff_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Teacher")

    def test_staff_detail_and_filters(self):
        active_staff = Staff.objects.create(
            legacy_emp_code=1,
            full_name="Active Teacher",
            designation="Teacher",
            staff_type=Staff.StaffType.TEACHING,
            phone="9999999999",
            basic_pay=Decimal("1.00"),
        )
        Staff.objects.create(
            legacy_emp_code=2,
            full_name="Left Clerk",
            staff_type=Staff.StaffType.ADMIN,
            is_active=False,
        )

        list_response = self.client.get(
            reverse("core:staff_list"),
            {"staff_type": Staff.StaffType.TEACHING, "status": "active"},
        )
        detail_response = self.client.get(reverse("core:staff_detail", args=[active_staff.id]))

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Active Teacher")
        self.assertNotContains(list_response, "Left Clerk")
        self.assertContains(list_response, reverse("core:staff_detail", args=[active_staff.id]))

        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Active Teacher")
        self.assertContains(detail_response, "Salary Defaults")
        self.assertContains(detail_response, "legacy placeholder values")
        self.assertContains(detail_response, "No salary payments recorded yet.")

    def test_salary_payment_create_and_pdf(self):
        staff = Staff.objects.create(
            full_name="Pay Teacher",
            designation="Teacher",
            basic_pay=Decimal("15000.00"),
            da=Decimal("1000.00"),
            other_allowances=Decimal("500.00"),
        )

        get_response = self.client.get(reverse("core:salary_payment_create"))
        self.assertEqual(get_response.status_code, 200)

        post_response = self.client.post(
            reverse("core:salary_payment_create"),
            data={
                "staff": staff.id,
                "pay_month": "2026-07-01",
                "payment_date": "2026-07-05",
                "payment_mode": SalaryPayment.PaymentMode.CASH,
                "basic_pay": "15000.00",
                "da": "1000.00",
                "other_allowances": "500.00",
                "pf_deduction": "1200.00",
                "esi_deduction": "0.00",
                "other_deduction": "0.00",
                "remarks": "July salary",
            },
        )

        payment = SalaryPayment.objects.get(staff=staff)
        self.assertRedirects(post_response, reverse("core:salary_payslip_pdf", args=[payment.id]))
        self.assertTrue(payment.slip_no.startswith("SAL-"))
        self.assertEqual(payment.gross_pay, Decimal("16500.00"))
        self.assertEqual(payment.net_pay, Decimal("15300.00"))

        pdf_response = self.client.get(reverse("core:salary_payslip_pdf", args=[payment.id]))
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")


class TransportTests(AuthenticatedClientMixin, TestCase):
    def test_transport_list_loads(self):
        school_class = SchoolClass.objects.create(name="VIII", display_order=8)
        student = Student.objects.create(
            legacy_sid=2,
            full_name="Transport Student",
            father_name="Test Father",
            current_class=school_class,
        )
        bus = TransportBus.objects.create(name="Bus 01", vehicle_no="MARSHAL")
        route = TransportRoute.objects.create(name="Shahpur", monthly_charge=Decimal("400.00"))
        StudentTransport.objects.create(
            student=student,
            route=route,
            bus=bus,
            legacy_route_name="Shahpur",
            legacy_bus_label="MARSHAL",
            stop_name="Main Chowk",
        )
        inactive_student = Student.objects.create(
            legacy_sid=3,
            full_name="Inactive Transport Student",
            father_name="Old Father",
            current_class=school_class,
        )
        StudentTransport.objects.create(
            student=inactive_student,
            route=route,
            bus=bus,
            legacy_route_name="Shahpur",
            legacy_bus_label="MARSHAL",
            stop_name="Old Stop",
            is_active=False,
            is_transport_enabled=False,
        )

        response = self.client.get(reverse("core:transport_list"))
        search_response = self.client.get(reverse("core:transport_list"), {"q": "Transport"})
        all_status_response = self.client.get(reverse("core:transport_list"), {"status": "all"})
        route_response = self.client.get(reverse("core:transport_list"), {"route": route.id, "status": "all"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(all_status_response.status_code, 200)
        self.assertEqual(route_response.status_code, 200)
        self.assertContains(response, "Transport Student")
        self.assertContains(response, "Shahpur")
        self.assertContains(response, "MARSHAL")
        self.assertContains(response, reverse("core:student_detail", args=[student.id]))
        self.assertContains(response, "Enabled")
        self.assertNotContains(response, "Old Stop")
        self.assertContains(all_status_response, "Old Stop")
        self.assertContains(route_response, "2")
        self.assertContains(route_response, "Legacy BUS_APPLICABLE")


# Create your tests here.
