import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import Assignment, Attendance, Directorate, InternProfile, MealAttendance, SupervisorProfile

User = get_user_model()


def auth_client(user):
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


class BaseSetup(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser("admin", "admin@ucaa.go.ug", "AdminPass123!")

        self.ans_supervisor_user = User.objects.create_user("jdoe_sup", password="SupPass123!")
        self.ans_supervisor = SupervisorProfile.objects.create(
            user=self.ans_supervisor_user,
            directorate=Directorate.AIR_NAVIGATION_SERVICES,
            staff_number="UCAA-001",
        )

        self.hra_supervisor_user = User.objects.create_user("mssy_sup", password="SupPass123!")
        self.hra_supervisor = SupervisorProfile.objects.create(
            user=self.hra_supervisor_user,
            directorate=Directorate.HR_ADMINISTRATION,
            staff_number="UCAA-002",
        )

        self.ans_intern_user = User.objects.create_user("aintern", password="InternPass123!")
        self.ans_intern = InternProfile.objects.create(
            user=self.ans_intern_user,
            directorate=Directorate.AIR_NAVIGATION_SERVICES,
            supervisor=self.ans_supervisor,
            internship_start_date=datetime.date(2026, 1, 1),
            internship_end_date=datetime.date(2026, 6, 30),
        )

        self.hra_intern_user = User.objects.create_user("bintern", password="InternPass123!")
        self.hra_intern = InternProfile.objects.create(
            user=self.hra_intern_user,
            directorate=Directorate.HR_ADMINISTRATION,
            supervisor=self.hra_supervisor,
            internship_start_date=datetime.date(2026, 1, 1),
            internship_end_date=datetime.date(2026, 6, 30),
        )

        self.admin_client = auth_client(self.admin_user)
        self.ans_supervisor_client = auth_client(self.ans_supervisor_user)
        self.hra_supervisor_client = auth_client(self.hra_supervisor_user)
        self.ans_intern_client = auth_client(self.ans_intern_user)
        self.hra_intern_client = auth_client(self.hra_intern_user)


class LateFlagModelTests(TestCase):
    """Directly exercises Attendance.save()'s late-flag derivation logic."""

    def setUp(self):
        supervisor_user = User.objects.create_user("sup1", password="x")
        self.supervisor = SupervisorProfile.objects.create(
            user=supervisor_user, directorate=Directorate.AIR_NAVIGATION_SERVICES, staff_number="S1"
        )
        intern_user = User.objects.create_user("intern1", password="x")
        self.intern = InternProfile.objects.create(
            user=intern_user,
            directorate=Directorate.AIR_NAVIGATION_SERVICES,
            supervisor=self.supervisor,
            internship_start_date=datetime.date(2026, 1, 1),
            internship_end_date=datetime.date(2026, 6, 30),
        )

    def _make_attendance(self, hour, minute, day=1):
        local_dt = datetime.datetime(2026, 2, day, hour, minute, 0)
        aware_dt = timezone.make_aware(local_dt)
        return Attendance.objects.create(
            intern=self.intern, date=aware_dt.date(), clock_in_time=aware_dt
        )

    def test_clock_in_before_cutoff_is_not_late(self):
        attendance = self._make_attendance(8, 0, day=1)
        self.assertFalse(attendance.is_late)

    def test_clock_in_exactly_at_cutoff_is_not_late(self):
        attendance = self._make_attendance(8, 30, day=2)
        self.assertFalse(attendance.is_late)

    def test_clock_in_after_cutoff_is_late(self):
        attendance = self._make_attendance(8, 31, day=3)
        self.assertTrue(attendance.is_late)

    def test_clock_in_well_after_cutoff_is_late(self):
        attendance = self._make_attendance(9, 45, day=4)
        self.assertTrue(attendance.is_late)

    def test_unique_together_blocks_second_attendance_same_day(self):
        self._make_attendance(8, 0, day=5)
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            self._make_attendance(9, 0, day=5)


class AttendanceApiTests(BaseSetup):
    def test_intern_can_clock_in(self):
        response = self.ans_intern_client.post("/api/attendance/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("is_late", response.data)
        self.assertEqual(Attendance.objects.filter(intern=self.ans_intern).count(), 1)

    def test_intern_cannot_clock_in_twice_same_day(self):
        first = self.ans_intern_client.post("/api/attendance/", {}, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self.ans_intern_client.post("/api/attendance/", {}, format="json")
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Attendance.objects.filter(intern=self.ans_intern).count(), 1)

    def test_supervisor_cannot_clock_in(self):
        response = self.ans_supervisor_client.post("/api/attendance/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_supervisor_sees_only_own_directorate_attendance(self):
        self.ans_intern_client.post("/api/attendance/", {}, format="json")
        self.hra_intern_client.post("/api/attendance/", {}, format="json")

        response = self.ans_supervisor_client.get("/api/attendance/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if "results" in response.data else response.data
        intern_ids = {row["intern"] for row in results}
        self.assertEqual(intern_ids, {self.ans_intern.id})

    def test_intern_cannot_delete_or_update_attendance(self):
        create_response = self.ans_intern_client.post("/api/attendance/", {}, format="json")
        record_id = create_response.data["id"]
        patch_response = self.ans_intern_client.patch(
            f"/api/attendance/{record_id}/", {"is_late": False}, format="json"
        )
        self.assertEqual(patch_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        delete_response = self.ans_intern_client.delete(f"/api/attendance/{record_id}/")
        self.assertEqual(delete_response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class MealAttendanceApiTests(BaseSetup):
    def test_intern_can_log_meal(self):
        response = self.ans_intern_client.post("/api/meals/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(MealAttendance.objects.filter(intern=self.ans_intern).count(), 1)

    def test_duplicate_meal_log_same_day_rejected(self):
        first = self.ans_intern_client.post("/api/meals/", {}, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self.ans_intern_client.post("/api/meals/", {}, format="json")
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(MealAttendance.objects.filter(intern=self.ans_intern).count(), 1)

    def test_supervisor_cannot_log_meal(self):
        response = self.ans_supervisor_client.post("/api/meals/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_model_level_unique_constraint(self):
        MealAttendance.objects.create(intern=self.ans_intern, date=timezone.localdate())
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            MealAttendance.objects.create(intern=self.ans_intern, date=timezone.localdate())


class AssignmentApiTests(BaseSetup):
    def test_supervisor_can_create_assignment_for_own_directorate_intern(self):
        payload = {
            "title": "Radar systems orientation",
            "description": "Shadow the radar control team for a week.",
            "assigned_to_intern": self.ans_intern.id,
        }
        response = self.ans_supervisor_client.post("/api/assignments/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "PENDING")
        self.assertEqual(Assignment.objects.count(), 1)
        self.assertEqual(Assignment.objects.first().created_by_supervisor, self.ans_supervisor)

    def test_supervisor_cannot_create_assignment_cross_directorate(self):
        payload = {
            "title": "Cross directorate task",
            "description": "This should not be allowed.",
            "assigned_to_intern": self.hra_intern.id,
        }
        response = self.ans_supervisor_client.post("/api/assignments/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Assignment.objects.count(), 0)

    def test_intern_cannot_create_assignment(self):
        payload = {
            "title": "Self-assigned task",
            "description": "Interns should not be able to do this.",
            "assigned_to_intern": self.ans_intern.id,
        }
        response = self.ans_intern_client.post("/api/assignments/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_full_assignment_lifecycle(self):
        create_response = self.ans_supervisor_client.post(
            "/api/assignments/",
            {
                "title": "Weekly report",
                "description": "Compile the weekly ANS operations report.",
                "assigned_to_intern": self.ans_intern.id,
            },
            format="json",
        )
        assignment_id = create_response.data["id"]

        # Supervisor cannot review before the intern submits.
        premature_review = self.ans_supervisor_client.post(
            f"/api/assignments/{assignment_id}/review/", {"status": "APPROVED"}, format="json"
        )
        self.assertEqual(premature_review.status_code, status.HTTP_400_BAD_REQUEST)

        # Wrong intern cannot submit.
        wrong_intern_submit = self.hra_intern_client.post(
            f"/api/assignments/{assignment_id}/submit/", {}, format="json"
        )
        self.assertEqual(wrong_intern_submit.status_code, status.HTTP_404_NOT_FOUND)

        # Correct intern submits.
        submit_response = self.ans_intern_client.post(
            f"/api/assignments/{assignment_id}/submit/", {}, format="json"
        )
        self.assertEqual(submit_response.status_code, status.HTTP_200_OK)
        self.assertEqual(submit_response.data["status"], "SUBMITTED")

        # Intern cannot submit again.
        resubmit_response = self.ans_intern_client.post(
            f"/api/assignments/{assignment_id}/submit/", {}, format="json"
        )
        self.assertEqual(resubmit_response.status_code, status.HTTP_400_BAD_REQUEST)

        # A supervisor from a different directorate cannot review it.
        other_review = self.hra_supervisor_client.post(
            f"/api/assignments/{assignment_id}/review/", {"status": "APPROVED"}, format="json"
        )
        self.assertEqual(other_review.status_code, status.HTTP_404_NOT_FOUND)

        # The creating supervisor approves it.
        review_response = self.ans_supervisor_client.post(
            f"/api/assignments/{assignment_id}/review/",
            {"status": "APPROVED", "supervisor_feedback": "Great work."},
            format="json",
        )
        self.assertEqual(review_response.status_code, status.HTTP_200_OK)
        self.assertEqual(review_response.data["status"], "APPROVED")
        self.assertEqual(review_response.data["supervisor_feedback"], "Great work.")

    def test_reject_flow(self):
        create_response = self.ans_supervisor_client.post(
            "/api/assignments/",
            {
                "title": "Draft memo",
                "description": "Draft the internal memo on runway inspection.",
                "assigned_to_intern": self.ans_intern.id,
            },
            format="json",
        )
        assignment_id = create_response.data["id"]
        self.ans_intern_client.post(f"/api/assignments/{assignment_id}/submit/", {}, format="json")
        review_response = self.ans_supervisor_client.post(
            f"/api/assignments/{assignment_id}/review/",
            {"status": "REJECTED", "supervisor_feedback": "Please revise section 2."},
            format="json",
        )
        self.assertEqual(review_response.status_code, status.HTTP_200_OK)
        self.assertEqual(review_response.data["status"], "REJECTED")


class ProfileRegistrationApiTests(BaseSetup):
    def test_admin_can_create_supervisor(self):
        payload = {
            "username": "newsupervisor",
            "password": "StrongPass123!",
            "first_name": "New",
            "last_name": "Supervisor",
            "directorate": "AAS",
            "staff_number": "UCAA-100",
        }
        response = self.admin_client.post("/api/supervisors/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(username="newsupervisor").exists())

    def test_non_admin_cannot_create_supervisor(self):
        payload = {
            "username": "sneakysupervisor",
            "password": "StrongPass123!",
            "directorate": "AAS",
            "staff_number": "UCAA-101",
        }
        response = self.ans_supervisor_client.post("/api/supervisors/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_supervisor_can_onboard_intern_into_own_directorate(self):
        payload = {
            "username": "newintern",
            "password": "StrongPass123!",
            "directorate": "ANS",
            "internship_start_date": "2026-03-01",
            "internship_end_date": "2026-08-31",
        }
        response = self.ans_supervisor_client.post("/api/interns/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = InternProfile.objects.get(user__username="newintern")
        self.assertEqual(created.supervisor, self.ans_supervisor)

    def test_login_returns_token(self):
        response = APIClient().post(
            "/api/auth/login/",
            {"username": "aintern", "password": "InternPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.data)

    def test_logout_deletes_token(self):
        response = self.ans_intern_client.post("/api/auth/logout/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Token.objects.filter(user=self.ans_intern_user).exists())

    def test_me_endpoint_reports_intern_role(self):
        response = self.ans_intern_client.get("/api/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["role"], "intern")
