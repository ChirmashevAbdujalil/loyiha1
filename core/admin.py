from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Assignment, Faculty, Notification, Submission, SubmissionFile, Task, TaskFile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "last_name", "first_name", "role", "faculty", "is_active")
    list_filter = ("role", "faculty", "is_active")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Ijro tizimi", {"fields": ("role", "middle_name", "faculty", "position", "phone")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Ijro tizimi", {"fields": ("role", "first_name", "last_name", "faculty")}),
    )


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ("name", "short_name")
    search_fields = ("name", "short_name")


class TaskFileInline(admin.TabularInline):
    model = TaskFile
    extra = 0


class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 0


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "execution_date", "deadline", "created_by")
    search_fields = ("title",)
    inlines = [TaskFileInline, AssignmentInline]


class SubmissionFileInline(admin.TabularInline):
    model = SubmissionFile
    extra = 0


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("assignment", "created_at", "decision", "reviewed_at")
    list_filter = ("decision",)
    inlines = [SubmissionFileInline]


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("task", "tutor", "status", "submitted_at", "approved_at")
    list_filter = ("status",)


admin.site.register(Notification)
admin.site.site_header = "Ijro nazorati — boshqaruv"
