from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

# The exact clock-in cutoff after which an intern is flagged as late.
LATE_CUTOFF_HOUR = 8
LATE_CUTOFF_MINUTE = 30


class Directorate(models.TextChoices):
    AIR_NAVIGATION_SERVICES = "ANS", "Air Navigation Services"
    AIRPORTS_AVIATION_SECURITY = "AAS", "Airports & Aviation Security"
    HR_ADMINISTRATION = "HRA", "HR & Administration"


class SupervisorProfile(models.Model):
    """Extends Django's built-in User model for staff who supervise interns."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="supervisor_profile",
    )
    directorate = models.CharField(max_length=3, choices=Directorate.choices)
    staff_number = models.CharField(max_length=20, unique=True)
    phone_number = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__first_name", "user__last_name"]

    def __str__(self):
        full_name = self.user.get_full_name() or self.user.username
        return f"{full_name} - Supervisor ({self.get_directorate_display()})"


class InternProfile(models.Model):
    """Extends Django's built-in User model for interns undergoing placement."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="intern_profile",
    )
    directorate = models.CharField(max_length=3, choices=Directorate.choices)
    supervisor = models.ForeignKey(
        SupervisorProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="interns",
    )
    university = models.CharField(max_length=255, blank=True)
    internship_start_date = models.DateField()
    internship_end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__first_name", "user__last_name"]

    def __str__(self):
        full_name = self.user.get_full_name() or self.user.username
        return f"{full_name} - Intern ({self.get_directorate_display()})"

    def clean(self):
        if self.supervisor_id and self.supervisor.directorate != self.directorate:
            raise ValidationError(
                "An intern's supervisor must belong to the same directorate as the intern."
            )
        if (
            self.internship_start_date
            and self.internship_end_date
            and self.internship_end_date < self.internship_start_date
        ):
            raise ValidationError("Internship end date cannot be before the start date.")


class Attendance(models.Model):
    """Daily clock-in record for an intern. One record per intern per calendar date."""

    intern = models.ForeignKey(
        InternProfile, on_delete=models.CASCADE, related_name="attendance_records"
    )
    date = models.DateField(default=timezone.localdate)
    clock_in_time = models.DateTimeField(default=timezone.now)
    is_late = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("intern", "date")
        ordering = ["-date", "-clock_in_time"]
        verbose_name_plural = "Attendance records"

    def __str__(self):
        flag = "LATE" if self.is_late else "ON TIME"
        return f"{self.intern} - {self.date} ({flag})"

    def save(self, *args, **kwargs):
        # is_late is always derived from clock_in_time, never trusted from client input.
        local_clock_in = timezone.localtime(self.clock_in_time)
        cutoff = local_clock_in.replace(
            hour=LATE_CUTOFF_HOUR, minute=LATE_CUTOFF_MINUTE, second=0, microsecond=0
        )
        self.is_late = local_clock_in > cutoff
        super().save(*args, **kwargs)


class MealAttendance(models.Model):
    """Meal log for an intern. Strictly one log allowed per intern per calendar date."""

    intern = models.ForeignKey(
        InternProfile, on_delete=models.CASCADE, related_name="meal_records"
    )
    date = models.DateField(default=timezone.localdate)
    timestamp = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("intern", "date")
        ordering = ["-date", "-timestamp"]
        verbose_name_plural = "Meal attendance records"

    def __str__(self):
        return f"{self.intern} - meal on {self.date}"


class Assignment(models.Model):
    """Work item created by a supervisor for an intern within the same directorate."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    title = models.CharField(max_length=255)
    description = models.TextField()
    assigned_to_intern = models.ForeignKey(
        InternProfile, on_delete=models.CASCADE, related_name="assignments"
    )
    created_by_supervisor = models.ForeignKey(
        SupervisorProfile, on_delete=models.CASCADE, related_name="created_assignments"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    due_date = models.DateField(null=True, blank=True)
    supervisor_feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} -> {self.assigned_to_intern} [{self.status}]"

    def clean(self):
        if (
            self.assigned_to_intern_id
            and self.created_by_supervisor_id
            and self.assigned_to_intern.directorate != self.created_by_supervisor.directorate
        ):
            raise ValidationError(
                "Supervisors can only create assignments for interns within their own directorate."
            )
