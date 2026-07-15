from django.contrib import admin

from .models import Assignment, Attendance, InternProfile, MealAttendance, SupervisorProfile


@admin.register(SupervisorProfile)
class SupervisorProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "directorate", "staff_number", "phone_number", "created_at")
    list_filter = ("directorate",)
    search_fields = ("user__username", "user__first_name", "user__last_name", "staff_number")


@admin.register(InternProfile)
class InternProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "directorate",
        "supervisor",
        "internship_start_date",
        "internship_end_date",
    )
    list_filter = ("directorate",)
    search_fields = ("user__username", "user__first_name", "user__last_name")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("intern", "date", "clock_in_time", "is_late")
    list_filter = ("is_late", "date")
    search_fields = ("intern__user__username",)


@admin.register(MealAttendance)
class MealAttendanceAdmin(admin.ModelAdmin):
    list_display = ("intern", "date", "timestamp")
    list_filter = ("date",)
    search_fields = ("intern__user__username",)


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "assigned_to_intern",
        "created_by_supervisor",
        "status",
        "due_date",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("title", "assigned_to_intern__user__username")
