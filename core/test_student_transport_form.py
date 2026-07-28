from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core.models import AcademicSession, SchoolClass, Student, StudentTransport, TransportRoute
from core.tests import AuthenticatedClientMixin


class StudentTransportFormTests(AuthenticatedClientMixin, TestCase):
    def test_student_transport_create(self):
        school_class = SchoolClass.objects.create(name="IX", display_order=9)
        session = AcademicSession.objects.create(name="2026-27-transport-create", starts_on=date(2026, 4, 1), ends_on=date(2027, 3, 31), is_active=True)
        route = TransportRoute.objects.create(name="New Route", monthly_charge=Decimal("500.00"), is_active=True)
        
        post_data = {
            "full_name": "New Transport Kid",
            "father_name": "Test Father",
            "current_class": school_class.id,
            "gender": Student.Gender.UNKNOWN,
            "disability": Student.Disability.NONE,
            "transport_required": "on",
            "transport_route": route.id,
            "stop_name": "Test Stop",
            "action": "save",
        }
        
        response = self.client.post(reverse("core:student_create"), data=post_data)
        
        student = Student.objects.get(full_name="New Transport Kid")
        self.assertRedirects(response, reverse("core:student_detail", args=[student.id]))
        
        transport = StudentTransport.objects.get(student=student, session=session)
        self.assertEqual(transport.route, route)
        self.assertEqual(transport.stop_name, "Test Stop")
        self.assertEqual(transport.monthly_amount, Decimal("500.00"))
        self.assertTrue(transport.is_active)

    def test_student_transport_update_deactivate(self):
        school_class = SchoolClass.objects.create(name="X", display_order=10)
        session = AcademicSession.objects.create(name="2026-27-transport-update", starts_on=date(2026, 4, 1), ends_on=date(2027, 3, 31), is_active=True)
        student = Student.objects.create(full_name="Update Kid", father_name="F", current_class=school_class)
        route = TransportRoute.objects.create(name="R1", monthly_charge=Decimal("100"), is_active=True)
        transport = StudentTransport.objects.create(
            student=student, session=session, route=route, stop_name="S1", is_active=True, monthly_amount=Decimal("100")
        )
        
        post_data = {
            "full_name": "Update Kid",
            "father_name": "F",
            "current_class": school_class.id,
            "gender": Student.Gender.UNKNOWN,
            "disability": Student.Disability.NONE,
        }
        response = self.client.post(reverse("core:student_update", args=[student.id]), data=post_data)
        self.assertRedirects(response, reverse("core:student_detail", args=[student.id]))
        
        transport.refresh_from_db()
        self.assertFalse(transport.is_active)

    def test_student_transport_validation(self):
        school_class = SchoolClass.objects.create(name="XI", display_order=11)
        
        post_data = {
            "full_name": "Invalid Kid",
            "father_name": "F",
            "current_class": school_class.id,
            "gender": Student.Gender.UNKNOWN,
            "disability": Student.Disability.NONE,
            "transport_required": "on",
        }
        response = self.client.post(reverse("core:student_create"), data=post_data)

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertFormError(form, "transport_route", "Please select a route if transport is required.")
        self.assertFormError(form, "stop_name", "Please enter a stop name if transport is required.")
