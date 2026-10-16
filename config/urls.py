from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from core import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", auth_views.LoginView.as_view(template_name="auth/login.html", redirect_authenticated_user=True),
         name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("profile/", views.profile, name="profile"),

    path("faculties/", views.faculty_list, name="faculty_list"),
    path("faculties/<int:pk>/edit/", views.faculty_edit, name="faculty_edit"),
    path("faculties/<int:pk>/delete/", views.faculty_delete, name="faculty_delete"),

    path("tutors/", views.tutor_list, name="tutor_list"),
    path("tutors/new/", views.tutor_create, name="tutor_create"),
    path("tutors/<int:pk>/", views.tutor_detail, name="tutor_detail"),
    path("tutors/<int:pk>/edit/", views.tutor_edit, name="tutor_edit"),
    path("tutors/<int:pk>/delete/", views.tutor_delete, name="tutor_delete"),

    path("tasks/", views.task_list, name="task_list"),
    path("tasks/new/", views.task_create, name="task_create"),
    path("tasks/<int:pk>/", views.task_detail, name="task_detail"),
    path("tasks/<int:pk>/edit/", views.task_edit, name="task_edit"),
    path("tasks/<int:pk>/delete/", views.task_delete, name="task_delete"),
    path("review/", views.review_queue, name="review_queue"),

    path("ijro/<int:pk>/", views.assignment_detail, name="assignment_detail"),
    path("ijro/<int:pk>/submit/", views.assignment_submit, name="assignment_submit"),
    path("ijro/<int:pk>/review/", views.assignment_review, name="assignment_review"),

    path("files/task/<int:pk>/", views.task_file, name="task_file"),
    path("files/submission/<int:pk>/", views.submission_file, name="submission_file"),

    path("reports/", views.report, name="report"),
    path("reports/export/", views.report_export, name="report_export"),

    path("notifications/", views.notification_list, name="notification_list"),
    path("notifications/feed/", views.notification_feed, name="notification_feed"),
    path("notifications/read-all/", views.notification_read_all, name="notification_read_all"),
    path("notifications/<int:pk>/", views.notification_open, name="notification_open"),

    path("admin/", admin.site.urls),
]
