from django.urls import path

from . import manage_views as mv
from . import views

app_name = "qalqon"

urlpatterns = [
    path("", views.calendar, name="calendar"),
    path("kirish/", views.QalqonLoginView.as_view(), name="login"),
    path("gps-tekshiruv/", views.gps_check, name="gps_check"),
    path("mening-naryadlarim/", views.my_duties, name="my_duties"),

    path("naryadlar/", views.duty_list, name="duty_list"),
    path("naryadlar/yangi/", views.duty_create, name="duty_create"),
    path("naryadlar/band/", views.busy_members, name="busy_members"),
    path("naryadlar/<int:pk>/", views.duty_detail, name="duty_detail"),
    path("naryadlar/<int:pk>/tahrirlash/", views.duty_edit, name="duty_edit"),
    path("naryadlar/<int:pk>/ochirish/", views.duty_delete, name="duty_delete"),

    path("navbat/<int:pk>/boshlash/", views.duty_start, name="duty_start"),
    path("navbat/<int:pk>/yakunlash/", views.duty_finish, name="duty_finish"),
    path("navbat/<int:pk>/qonunbuzarlik/", views.violation_add, name="violation_add"),
    path("navbat/<int:pk>/rasm/", views.duty_photo, name="duty_photo"),

    path("qonunbuzarliklar/", mv.violation_list, name="violation_list"),
    path("qonunbuzarliklar/excel/", mv.violation_export, name="violation_export"),
    path("qonunbuzarliklar/<int:pk>/tahrirlash/", views.violation_edit, name="violation_edit"),
    path("qonunbuzarliklar/<int:pk>/ochirish/", views.violation_delete, name="violation_delete"),
    path("qonunbuzarliklar/<int:pk>/rasm/", views.violation_photo, name="violation_photo"),

    path("azolar/", mv.member_list, name="member_list"),
    path("azolar/yangi/", mv.member_create, name="member_create"),
    path("azolar/import/", mv.member_import, name="member_import"),
    path("azolar/import/shablon/", mv.member_import_template, name="member_import_template"),
    path("azolar/import/loginlar/", mv.member_import_credentials, name="member_import_credentials"),
    path("azolar/<int:pk>/", mv.member_detail, name="member_detail"),
    path("azolar/<int:pk>/tahrirlash/", mv.member_edit, name="member_edit"),
    path("azolar/<int:pk>/ochirish/", mv.member_delete, name="member_delete"),

    path("binolar/", mv.building_list, name="building_list"),
    path("binolar/yangi/", mv.building_form, name="building_create"),
    path("binolar/<int:pk>/", mv.building_form, name="building_edit"),
    path("binolar/<int:pk>/ochirish/", mv.building_delete, name="building_delete"),

    path("statistika/", mv.stats, name="stats"),
    path("statistika/excel/", mv.stats_export, name="stats_export"),
]
