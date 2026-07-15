from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from .views import (
    AssignmentViewSet,
    AttendanceViewSet,
    CurrentUserProfileView,
    InternProfileViewSet,
    LogoutView,
    MealAttendanceViewSet,
    SupervisorProfileViewSet,
)

router = DefaultRouter()
router.register(r"supervisors", SupervisorProfileViewSet, basename="supervisor")
router.register(r"interns", InternProfileViewSet, basename="intern")
router.register(r"attendance", AttendanceViewSet, basename="attendance")
router.register(r"meals", MealAttendanceViewSet, basename="meal")
router.register(r"assignments", AssignmentViewSet, basename="assignment")

urlpatterns = [
    # Token authentication: POST {"username": ..., "password": ...} -> {"token": "..."}
    path("auth/login/", obtain_auth_token, name="api-token-login"),
    path("auth/logout/", LogoutView.as_view(), name="api-token-logout"),
    path("me/", CurrentUserProfileView.as_view(), name="current-user-profile"),
    path("", include(router.urls)),
]
