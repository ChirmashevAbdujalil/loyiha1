from django.contrib import admin

from .models import Building, Duty, DutyMember, LocationLog, MemberProfile, Violation


@admin.register(Building)
class BuildingAdmin(admin.ModelAdmin):
    list_display = ("name", "short_name", "kind", "latitude", "longitude", "radius_m", "is_active")
    list_filter = ("kind", "is_active")


class DutyMemberInline(admin.TabularInline):
    model = DutyMember
    extra = 0


@admin.register(Duty)
class DutyAdmin(admin.ModelAdmin):
    list_display = ("date", "start_time", "end_time", "building", "radius_m", "created_by")
    list_filter = ("building",)
    date_hierarchy = "date"
    inlines = [DutyMemberInline]


@admin.register(Violation)
class ViolationAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "category", "student_name", "faculty", "course", "dormitory", "room")
    list_filter = ("category", "faculty", "dormitory", "course")
    search_fields = ("student_name", "group_name")


@admin.register(LocationLog)
class LocationLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "duty_member", "action", "distance", "accuracy", "success")
    list_filter = ("action", "success")


admin.site.register(MemberProfile)
