from django.db import IntegrityError
from rest_framework import mixins, permissions, serializers, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Assignment, Attendance, InternProfile, MealAttendance, SupervisorProfile
from .serializers import (
    AssignmentReviewSerializer,
    AssignmentSerializer,
    AttendanceSerializer,
    InternProfileSerializer,
    MealAttendanceSerializer,
    SupervisorProfileSerializer,
)


class IsIntern(permissions.BasePermission):
   

    message = "Only interns can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and hasattr(request.user, "intern_profile")
        )


class IsSupervisor(permissions.BasePermission):
    

    message = "Only supervisors can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and hasattr(request.user, "supervisor_profile")
        )


class IsAdminOrSupervisor(permissions.BasePermission):
    

    message = "Only administrators or supervisors can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or hasattr(request.user, "supervisor_profile"))
        )


class IsAdminOrSelf(permissions.BasePermission):
   

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        return obj.user_id == request.user.id


class IsAssignmentOwnerSupervisor(permissions.BasePermission):
   

    message = "Only the supervisor who created this assignment can modify it."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or hasattr(request.user, "supervisor_profile"))
        )

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        supervisor_profile = getattr(request.user, "supervisor_profile", None)
        return (
            supervisor_profile is not None
            and obj.created_by_supervisor_id == supervisor_profile.id
        )

# Profile management

class SupervisorProfileViewSet(viewsets.ModelViewSet):
    

    queryset = SupervisorProfile.objects.select_related("user").all()
    serializer_class = SupervisorProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action == "create":
            permission_classes = [permissions.IsAdminUser]
        elif self.action in ["update", "partial_update", "destroy"]:
            permission_classes = [permissions.IsAuthenticated, IsAdminOrSelf]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        queryset = super().get_queryset()
        directorate = self.request.query_params.get("directorate")
        if directorate:
            queryset = queryset.filter(directorate=directorate)
        return queryset


class InternProfileViewSet(viewsets.ModelViewSet):


    queryset = InternProfile.objects.select_related("user", "supervisor__user").all()
    serializer_class = InternProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action == "create":
            permission_classes = [permissions.IsAuthenticated, IsAdminOrSupervisor]
        elif self.action in ["update", "partial_update", "destroy"]:
            permission_classes = [permissions.IsAuthenticated, IsAdminOrSelf]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        queryset = super().get_queryset()
        directorate = self.request.query_params.get("directorate")
        if directorate:
            queryset = queryset.filter(directorate=directorate)
        return queryset

    def perform_create(self, serializer):
        user = self.request.user
        supervisor_profile = getattr(user, "supervisor_profile", None)

        if supervisor_profile is not None and not user.is_staff:
            requested_directorate = serializer.validated_data.get("directorate")
            if requested_directorate and requested_directorate != supervisor_profile.directorate:
                raise PermissionDenied("You can only onboard interns into your own directorate.")
            if serializer.validated_data.get("supervisor") is None:
                serializer.save(
                    supervisor=supervisor_profile, directorate=supervisor_profile.directorate
                )
                return
        serializer.save()





class AttendanceViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
   

    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action == "create":
            permission_classes = [permissions.IsAuthenticated, IsIntern]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        queryset = Attendance.objects.select_related("intern__user").all()

        if user.is_staff:
            return queryset

        intern_profile = getattr(user, "intern_profile", None)
        if intern_profile is not None:
            return queryset.filter(intern=intern_profile)

        supervisor_profile = getattr(user, "supervisor_profile", None)
        if supervisor_profile is not None:
            return queryset.filter(intern__directorate=supervisor_profile.directorate)

        return queryset.none()

    def perform_create(self, serializer):
       
        try:
            serializer.save()
        except IntegrityError:
            raise serializers.ValidationError("You have already clocked in today.")


class MealAttendanceViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):


    serializer_class = MealAttendanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action == "create":
            permission_classes = [permissions.IsAuthenticated, IsIntern]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        queryset = MealAttendance.objects.select_related("intern__user").all()

        if user.is_staff:
            return queryset

        intern_profile = getattr(user, "intern_profile", None)
        if intern_profile is not None:
            return queryset.filter(intern=intern_profile)

        supervisor_profile = getattr(user, "supervisor_profile", None)
        if supervisor_profile is not None:
            return queryset.filter(intern__directorate=supervisor_profile.directorate)

        return queryset.none()

    def perform_create(self, serializer):
        # A unique_together race between two near-simultaneous requests is
        # caught here and surfaced as a clean 400 instead of a 500.
        try:
            serializer.save()
        except IntegrityError:
            raise serializers.ValidationError("You have already logged a meal for today.")



class AssignmentViewSet(viewsets.ModelViewSet):
   

    serializer_class = AssignmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action == "create":
            permission_classes = [permissions.IsAuthenticated, IsSupervisor]
        elif self.action in ["update", "partial_update", "destroy"]:
            permission_classes = [permissions.IsAuthenticated, IsAssignmentOwnerSupervisor]
        elif self.action == "submit":
            permission_classes = [permissions.IsAuthenticated, IsIntern]
        elif self.action == "review":
            permission_classes = [permissions.IsAuthenticated, IsSupervisor]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        user = self.request.user
        queryset = Assignment.objects.select_related(
            "assigned_to_intern__user", "created_by_supervisor__user"
        ).all()

        if user.is_staff:
            return queryset

        intern_profile = getattr(user, "intern_profile", None)
        if intern_profile is not None:
            return queryset.filter(assigned_to_intern=intern_profile)

        supervisor_profile = getattr(user, "supervisor_profile", None)
        if supervisor_profile is not None:
            return queryset.filter(created_by_supervisor=supervisor_profile)

        return queryset.none()

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        assignment = self.get_object()
        if assignment.assigned_to_intern.user_id != request.user.id:
            return Response(
                {"detail": "You can only submit your own assignments."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if assignment.status != Assignment.Status.PENDING:
            return Response(
                {"detail": "Only pending assignments can be submitted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        assignment.status = Assignment.Status.SUBMITTED
        assignment.save(update_fields=["status", "updated_at"])
        serializer = self.get_serializer(assignment)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        assignment = self.get_object()
        is_owning_supervisor = (
            assignment.created_by_supervisor.user_id == request.user.id
        )
        if not request.user.is_staff and not is_owning_supervisor:
            return Response(
                {"detail": "Only the supervisor who created this assignment can review it."},
                status=status.HTTP_403_FORBIDDEN,
            )
        review_serializer = AssignmentReviewSerializer(
            data=request.data, context={"assignment": assignment, "request": request}
        )
        review_serializer.is_valid(raise_exception=True)
        assignment = review_serializer.save()
        return Response(AssignmentSerializer(assignment).data, status=status.HTTP_200_OK)


# --------------------------------------------------------------------------
# Auth helpers
# --------------------------------------------------------------------------


class CurrentUserProfileView(APIView):
    """Returns the authenticated user's account details, role, and profile."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        data = {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "is_staff": user.is_staff,
            "role": None,
            "profile": None,
        }

        intern_profile = getattr(user, "intern_profile", None)
        supervisor_profile = getattr(user, "supervisor_profile", None)

        if intern_profile is not None:
            data["role"] = "intern"
            data["profile"] = InternProfileSerializer(intern_profile).data
        elif supervisor_profile is not None:
            data["role"] = "supervisor"
            data["profile"] = SupervisorProfileSerializer(supervisor_profile).data
        elif user.is_staff:
            data["role"] = "admin"

        return Response(data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """Deletes the authenticated user's auth token, effectively logging them out."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)
