"""Fakultetlar va tyutorlar (faqat bo'lim boshlig'i uchun)."""
from collections import Counter

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..decorators import head_required
from ..forms import FacultyForm, TutorForm
from ..models import Assignment, Faculty, User


# ------------------------------------------------------------- fakultetlar

@head_required
def faculty_list(request):
    form = FacultyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        faculty = form.save()
        messages.success(request, f"«{faculty.name}» qo'shildi.")
        return redirect("faculty_list")
    faculties = Faculty.objects.annotate(
        tutor_count=Count("tutors", filter=Q(tutors__role=User.Role.TUTOR, tutors__is_active=True))
    )
    return render(request, "faculties/list.html", {"faculties": faculties, "form": form})


@head_required
def faculty_edit(request, pk):
    faculty = get_object_or_404(Faculty, pk=pk)
    form = FacultyForm(request.POST or None, instance=faculty)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Fakultet ma'lumotlari saqlandi.")
        return redirect("faculty_list")
    return render(request, "faculties/edit.html", {"form": form, "faculty": faculty})


@head_required
@require_POST
def faculty_delete(request, pk):
    faculty = get_object_or_404(Faculty, pk=pk)
    if faculty.tutors.exists():
        messages.error(request, "Bu fakultetga tyutorlar biriktirilgan. Avval ularni boshqa fakultetga o'tkazing.")
    else:
        faculty.delete()
        messages.success(request, f"«{faculty.name}» o'chirildi.")
    return redirect("faculty_list")


# ---------------------------------------------------------------- tyutorlar

def _tutor_stats(assignments):
    counts = Counter(a.display_status for a in assignments)
    total = len(assignments)
    counts["total"] = total
    counts["percent"] = round(counts["approved"] * 100 / total) if total else 0
    return counts


@head_required
def tutor_list(request):
    if not Faculty.objects.exists():
        messages.info(request, "Avval fakultetlarni qo'shing, so'ngra tyutorlarni biriktiring.")
        return redirect("faculty_list")
    tutors = User.objects.filter(role=User.Role.TUTOR).select_related("faculty")
    faculty_id = request.GET.get("faculty", "")
    query = request.GET.get("q", "").strip()
    show = request.GET.get("show", "active")
    if faculty_id.isdigit():
        tutors = tutors.filter(faculty_id=faculty_id)
    if query:
        tutors = tutors.filter(
            Q(first_name__icontains=query) | Q(last_name__icontains=query)
            | Q(middle_name__icontains=query) | Q(username__icontains=query) | Q(phone__icontains=query)
        )
    if show == "active":
        tutors = tutors.filter(is_active=True)
    elif show == "inactive":
        tutors = tutors.filter(is_active=False)
    tutors = list(tutors.order_by("faculty__name", "last_name", "first_name"))

    assignments = Assignment.objects.filter(tutor__in=tutors).select_related("task")
    by_tutor = {}
    for a in assignments:
        by_tutor.setdefault(a.tutor_id, []).append(a)
    for t in tutors:
        t.stats = _tutor_stats(by_tutor.get(t.pk, []))

    groups = {}
    for t in tutors:
        groups.setdefault(t.faculty, []).append(t)
    return render(request, "tutors/list.html", {
        "groups": groups.items(),
        "tutor_total": len(tutors),
        "faculties": Faculty.objects.all(),
        "faculty_id": faculty_id,
        "query": query,
        "show": show,
    })


@head_required
def tutor_create(request):
    if not Faculty.objects.exists():
        messages.info(request, "Avval kamida bitta fakultet qo'shing.")
        return redirect("faculty_list")
    initial = {"faculty": request.GET.get("faculty")} if request.GET.get("faculty") else None
    form = TutorForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        tutor = form.save()
        messages.success(request, f"{tutor.full_name} tyutor sifatida qo'shildi. Login: {tutor.username}")
        if "add_another" in request.POST:
            return redirect(f"{request.path}?faculty={tutor.faculty_id}")
        return redirect("tutor_list")
    return render(request, "tutors/form.html", {"form": form})


@head_required
def tutor_edit(request, pk):
    tutor = get_object_or_404(User, pk=pk, role=User.Role.TUTOR)
    form = TutorForm(request.POST or None, instance=tutor)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Tyutor ma'lumotlari saqlandi.")
        return redirect("tutor_detail", pk=tutor.pk)
    return render(request, "tutors/form.html", {"form": form, "tutor": tutor})


@head_required
def tutor_detail(request, pk):
    tutor = get_object_or_404(User.objects.select_related("faculty"), pk=pk, role=User.Role.TUTOR)
    assignments = list(
        tutor.assignments.select_related("task").prefetch_related("submissions").order_by("-task__deadline")
    )
    status = request.GET.get("status", "")
    stats = _tutor_stats(assignments)
    if status:
        assignments = [a for a in assignments if a.display_status == status]
    return render(request, "tutors/detail.html", {
        "tutor": tutor, "assignments": assignments, "stats": stats, "status": status,
    })


@head_required
@require_POST
def tutor_delete(request, pk):
    tutor = get_object_or_404(User, pk=pk, role=User.Role.TUTOR)
    if tutor.assignments.exists():
        tutor.is_active = False
        tutor.save(update_fields=["is_active"])
        messages.warning(
            request,
            f"{tutor.full_name}ga topshiriqlar biriktirilgan, shuning uchun o'chirilmadi — "
            "hisobotlar saqlanib qolishi uchun nofaol holatga o'tkazildi.",
        )
    else:
        name = tutor.full_name
        tutor.delete()
        messages.success(request, f"{name} o'chirildi.")
    return redirect("tutor_list")
