from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers

from .models import Assignment, Attendance, InternProfile, MealAttendance, SupervisorProfile

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "email"]
        read_only_fields = ["id"]


class SupervisorProfileSerializer(serializers.ModelSerializer):
    """
    Handles both read representation and creation of a Supervisor.
    Creating a Supervisor also creates the underlying Django User account.
    """

    username = serializers.CharField(write_only=True)
    password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, validators=[validate_password]
    )
    first_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    last_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    email = serializers.EmailField(write_only=True, required=False, allow_blank=True)
    user = UserSerializer(read_only=True)
    directorate_display = serializers.CharField(source="get_directorate_display", read_only=True)

    class Meta:
        model = SupervisorProfile
        fields = [
            "id",
            "user",
            "username",
            "password",
            "first_name",
            "last_name",
            "email",
            "directorate",
            "directorate_display",
            "staff_number",
            "phone_number",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate_staff_number(self, value):
        queryset = SupervisorProfile.objects.filter(staff_number__iexact=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("A supervisor with this staff number already exists.")
        return value

    def create(self, validated_data):
        username = validated_data.pop("username")
        password = validated_data.pop("password")
        first_name = validated_data.pop("first_name", "")
        last_name = validated_data.pop("last_name", "")
        email = validated_data.pop("email", "")

        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            email=email,
        )
        try:
            supervisor = SupervisorProfile.objects.create(user=user, **validated_data)
        except Exception:
            user.delete()
            raise
        return supervisor


class InternProfileSerializer(serializers.ModelSerializer):
    """
    Handles both read representation and creation of an Intern.
    Creating an Intern also creates the underlying Django User account.
    """

    username = serializers.CharField(write_only=True)
    password = serializers.CharField(
        write_only=True, style={"input_type": "password"}, validators=[validate_password]
    )
    first_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    last_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    email = serializers.EmailField(write_only=True, required=False, allow_blank=True)
    user = UserSerializer(read_only=True)
    directorate_display = serializers.CharField(source="get_directorate_display", read_only=True)
    supervisor = serializers.PrimaryKeyRelatedField(
        queryset=SupervisorProfile.objects.all(), required=False, allow_null=True
    )
    supervisor_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = InternProfile
        fields = [
            "id",
            "user",
            "username",
            "password",
            "first_name",
            "last_name",
            "email",
            "directorate",
            "directorate_display",
            "supervisor",
            "supervisor_name",
            "university",
            "internship_start_date",
            "internship_end_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_supervisor_name(self, obj):
        if obj.supervisor:
            return obj.supervisor.user.get_full_name() or obj.supervisor.user.username
        return None

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate(self, attrs):
        supervisor = attrs.get("supervisor", getattr(self.instance, "supervisor", None))
        directorate = attrs.get("directorate", getattr(self.instance, "directorate", None))
        if supervisor and directorate and supervisor.directorate != directorate:
            raise serializers.ValidationError(
                {"supervisor": "Supervisor must belong to the same directorate as the intern."}
            )

        start_date = attrs.get(
            "internship_start_date", getattr(self.instance, "internship_start_date", None)
        )
        end_date = attrs.get(
            "internship_end_date", getattr(self.instance, "internship_end_date", None)
        )
        if start_date and end_date and end_date < start_date:
            raise serializers.ValidationError(
                {"internship_end_date": "Internship end date cannot be before the start date."}
            )
        return attrs

    def create(self, validated_data):
        username = validated_data.pop("username")
        password = validated_data.pop("password")
        first_name = validated_data.pop("first_name", "")
        last_name = validated_data.pop("last_name", "")
        email = validated_data.pop("email", "")

        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            last_name=last_name,
            email=email,
        )
        try:
            intern = InternProfile.objects.create(user=user, **validated_data)
        except Exception:
            user.delete()
            raise
        return intern


class AttendanceSerializer(serializers.ModelSerializer):
    """
    Represents a single daily clock-in. `date`, `clock_in_time`, and `is_late`
    are always derived server-side and can never be supplied by the client.
    """

    intern_name = serializers.SerializerMethodField(read_only=True)
    directorate = serializers.CharField(source="intern.get_directorate_display", read_only=True)

    class Meta:
        model = Attendance
        fields = [
            "id",
            "intern",
            "intern_name",
            "directorate",
            "date",
            "clock_in_time",
            "is_late",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "intern",
            "date",
            "clock_in_time",
            "is_late",
            "created_at",
            "updated_at",
        ]

    def get_intern_name(self, obj):
        return obj.intern.user.get_full_name() or obj.intern.user.username

    def validate(self, attrs):
        request = self.context["request"]
        intern_profile = getattr(request.user, "intern_profile", None)
        if intern_profile is None:
            raise serializers.ValidationError("Only interns can clock in.")

        today = timezone.localdate()
        if Attendance.objects.filter(intern=intern_profile, date=today).exists():
            raise serializers.ValidationError("You have already clocked in today.")
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        intern_profile = request.user.intern_profile
        now = timezone.now()
        validated_data["intern"] = intern_profile
        validated_data["date"] = timezone.localdate()
        validated_data["clock_in_time"] = now
        return Attendance.objects.create(**validated_data)


class MealAttendanceSerializer(serializers.ModelSerializer):
    """
    Represents a single daily meal log. Enforces exactly one log per intern
    per calendar date; duplicate attempts surface as a 400 Bad Request.
    """

    intern_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = MealAttendance
        fields = [
            "id",
            "intern",
            "intern_name",
            "date",
            "timestamp",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "intern", "date", "timestamp", "created_at", "updated_at"]

    def get_intern_name(self, obj):
        return obj.intern.user.get_full_name() or obj.intern.user.username

    def validate(self, attrs):
        request = self.context["request"]
        intern_profile = getattr(request.user, "intern_profile", None)
        if intern_profile is None:
            raise serializers.ValidationError("Only interns can log meal attendance.")

        today = timezone.localdate()
        if MealAttendance.objects.filter(intern=intern_profile, date=today).exists():
            raise serializers.ValidationError("You have already logged a meal for today.")
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        intern_profile = request.user.intern_profile
        validated_data["intern"] = intern_profile
        validated_data["date"] = timezone.localdate()
        validated_data["timestamp"] = timezone.now()
        return MealAttendance.objects.create(**validated_data)


class AssignmentSerializer(serializers.ModelSerializer):
    """
    Represents an assignment. On create, the supervisor is taken from the
    authenticated request user and must share the intern's directorate.
    `status` cannot be set directly here — it changes only through the
    dedicated `submit` and `review` actions.
    """

    assigned_to_intern_name = serializers.SerializerMethodField(read_only=True)
    created_by_supervisor_name = serializers.SerializerMethodField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Assignment
        fields = [
            "id",
            "title",
            "description",
            "assigned_to_intern",
            "assigned_to_intern_name",
            "created_by_supervisor",
            "created_by_supervisor_name",
            "status",
            "status_display",
            "due_date",
            "supervisor_feedback",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_by_supervisor",
            "status",
            "supervisor_feedback",
            "created_at",
            "updated_at",
        ]

    def get_assigned_to_intern_name(self, obj):
        return obj.assigned_to_intern.user.get_full_name() or obj.assigned_to_intern.user.username

    def get_created_by_supervisor_name(self, obj):
        return (
            obj.created_by_supervisor.user.get_full_name()
            or obj.created_by_supervisor.user.username
        )

    def validate_assigned_to_intern(self, value):
        request = self.context["request"]
        supervisor_profile = getattr(request.user, "supervisor_profile", None)
        if supervisor_profile is None:
            raise serializers.ValidationError("Only supervisors can create assignments.")
        if value.directorate != supervisor_profile.directorate:
            raise serializers.ValidationError(
                "You can only assign work to interns within your own directorate."
            )
        return value

    def create(self, validated_data):
        request = self.context["request"]
        validated_data["created_by_supervisor"] = request.user.supervisor_profile
        validated_data["status"] = Assignment.Status.PENDING
        return Assignment.objects.create(**validated_data)


class AssignmentReviewSerializer(serializers.Serializer):
    """Used exclusively by the supervisor-only `review` action on an assignment."""

    status = serializers.ChoiceField(
        choices=[Assignment.Status.APPROVED, Assignment.Status.REJECTED]
    )
    supervisor_feedback = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        assignment = self.context["assignment"]
        if assignment.status != Assignment.Status.SUBMITTED:
            raise serializers.ValidationError(
                "Only assignments that have been submitted can be approved or rejected."
            )
        return attrs

    def save(self, **kwargs):
        assignment = self.context["assignment"]
        assignment.status = self.validated_data["status"]
        if "supervisor_feedback" in self.validated_data:
            assignment.supervisor_feedback = self.validated_data["supervisor_feedback"]
        assignment.save(update_fields=["status", "supervisor_feedback", "updated_at"])
        return assignment
