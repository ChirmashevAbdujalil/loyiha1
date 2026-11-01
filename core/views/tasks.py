import mimetypes
import os
from collections import Counter

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .. import services
from ..decorators import head_required
from ..forms import ReviewForm, SubmitForm, TaskForm
from ..models import Assignment, Faculty, Submission, SubmissionFile, Task, TaskFile


def _save_task_files(task, files):
    for f in files:
        TaskFile.objects.create(task=task, file=f, original_name=os.path.basename(f.name)[:255], size=f.size)


def _faculty_groups(form):
    """Tyutorlarni fakultet bo'yicha guruhlab, tanlash ro'yxati uchun."""
    selected = {str(v) for v in (form["tutors"].value() or [])}
    groups = {}
    for tutor in form.fields["tutors"].queryset:
        tutor.checked = str(tutor.pk) in selected
        groups.setdefault(tutor.faculty, []).append(tutor)
    return list(groups.items())


# ------------------------------------------------------------------ ro'yxat

@login_required
def task_list(request):
    if request.user.is_qalqon_only:
        return redirect("qalqon:calendar")
    if not request.user.is_head:
        return my_assignments(request)
    tasks = Task.objects.select_related("created_by").annotate(
        total=Count("assignments"),
        done=Count("assignments", filter=Q(assignments__status=Assignment.Status.APPROVED)),
        review=Count("assignments", filter=Q(assignments__status=Assignment.Status.SUBMITTED)),
    )
    query = request.GET.get("q", "").strip()
    state = request.GET.get("state", "")
    now = timezone.now()
    if query:
        filt = Q(title__icontains=query) | Q(description__icontains=query)
        if query.lstrip("№#").isdigit():
            filt |= Q(pk=int(query.lstrip("№#")))
        tasks = tasks.filter(filt)
    if state == "active":
        tasks = tasks.filter(done__lt=F("total"), deadline__gte=now)
    elif state == "overdue":
        tasks = tasks.filter(done__lt=F("total"), deadline__lt=now)
    elif state == "done":
        tasks = tasks.filter(total__gt=0, done=F("total"))
    tasks = tasks.order_by("-created_at")
    for t in tasks:
        t.percent = round(t.done * 100 / t.total) if t.total else 0
    return render(request, "tasks/list.html", {"tasks": tasks, "query": query, "state": state, "now": now})


@login_required
def my_assignments(request):
    assignments = list(
        request.user.assignments.select_related("task", "task__created_by").order_by("task__deadline")
    )
    counts = Counter(a.display_status for a in assignments)
    status = request.GET.get("status", "open")
    if status == "open":
        shown = [a for a in assignments if a.display_status in ("pending", "rejected", "overdue")]
    elif status in ("submitted", "approved", "overdue"):
        shown = [a for a in assignments if a.display_status == status]
    else:
        status = "all"
        shown = assignments
    if status == "approved":
        shown.reverse()
    return render(request, "tasks/my_list.html", {
        "assignments": shown,
        "counts": counts,
        "open_total": counts["pending"] + counts["rejected"] + counts["overdue"],
        "total": len(assignments),
        "status": status,
    })


# ---------------------------------------------------- yaratish / tahrirlash

@head_required
def task_create(request):
    form = TaskForm(request.POST or None, request.FILES or None)
    if not request.POST and request.GET.get("date"):
        form.initial["execution_date"] = request.GET["date"]
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            task = form.save(commit=False)
            task.created_by = request.user
            task.save()
            _save_task_files(task, form.cleaned_data["files"])
            assignments = [
                Assignment.objects.create(task=task, tutor=tutor) for tutor in form.cleaned_data["tutors"]
            ]
            services.notify_new_assignments(assignments)
        messages.success(
            request, f"Topshiriq {task.number} {len(assignments)} ta tyutorga yuborildi. Ularga bildirishnoma ketdi."
        )
        return redirect(task)
    return render(request, "tasks/form.html", {
        "form": form, "groups": _faculty_groups(form), "faculties": Faculty.objects.all(),
    })


@head_required
def task_edit(request, pk):
    task = get_object_or_404(Task, pk=pk)
    form = TaskForm(request.POST or None, request.FILES or None, instance=task)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            changed_core = any(f in form.changed_data for f in ("title", "description", "execution_date", "deadline"))
            form.save()
            _save_task_files(task, form.cleaned_data["files"])
            remove_ids = request.POST.getlist("remove_file")
            for tf in task.files.filter(pk__in=remove_ids):
                tf.file.delete(save=False)
                tf.delete()

            selected = {t.pk: t for t in form.cleaned_data["tutors"]}
            existing = {a.tutor_id: a for a in task.assignments.all()}
            kept = []
            for tutor_id, a in existing.items():
                if tutor_id in selected:
                    continue
                if a.submissions.exists():
                    kept.append(a.tutor.full_name)
                else:
                    a.delete()
            if changed_core:
                services.notify_task_updated(task)
            new = [
                Assignment.objects.create(task=task, tutor=tutor)
                for tid, tutor in selected.items() if tid not in existing
            ]
            services.notify_new_assignments(new)
        messages.success(request, "Topshiriq saqlandi.")
        if kept:
            messages.warning(
                request,
                "Quyidagi tyutorlar ijro yuborgani sababli ro'yxatdan olib tashlanmadi: " + ", ".join(kept),
            )
        return redirect(task)
    return render(request, "tasks/form.html", {
        "form": form, "task": task, "groups": _faculty_groups(form), "faculties": Faculty.objects.all(),
    })


@head_required
@require_POST
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk)
    for tf in task.files.all():
        tf.file.delete(save=False)
    for sf in SubmissionFile.objects.filter(submission__assignment__task=task):
        sf.file.delete(save=False)
    task.delete()
    messages.success(request, "Topshiriq o'chirildi.")
    return redirect("task_list")


@head_required
def task_detail(request, pk):
    task = get_object_or_404(Task.objects.select_related("created_by"), pk=pk)
    assignments = list(
        task.assignments.select_related("tutor", "tutor__faculty").prefetch_related("submissions")
        .order_by("tutor__faculty__name", "tutor__last_name")
    )
    counts = Counter(a.display_status for a in assignments)
    total = len(assignments)
    return render(request, "tasks/detail.html", {
        "task": task,
        "assignments": assignments,
        "counts": counts,
        "total": total,
        "percent": round(counts["approved"] * 100 / total) if total else 0,
    })


# --------------------------------------------------------------- ijro

def _get_assignment_for(request, pk):
    a = get_object_or_404(
        Assignment.objects.select_related("task", "task__created_by", "tutor", "tutor__faculty"), pk=pk
    )
    if not (request.user.is_head or a.tutor_id == request.user.pk):
        raise PermissionDenied
    return a


@login_required
def assignment_detail(request, pk):
    a = _get_assignment_for(request, pk)
    if a.tutor_id == request.user.pk and a.seen_at is None:
        a.seen_at = timezone.now()
        a.save(update_fields=["seen_at"])
    submissions = a.submissions.select_related("reviewed_by").prefetch_related("files")
    return render(request, "tasks/assignment.html", {
        "a": a,
        "task": a.task,
        "submissions": submissions,
        "submit_form": SubmitForm(),
        "review_form": ReviewForm(),
        "open_submit": request.GET.get("close") == "1",
    })


@login_required
@require_POST
def assignment_submit(request, pk):
    a = _get_assignment_for(request, pk)
    if a.tutor_id != request.user.pk:
        raise PermissionDenied
    if not a.can_submit:
        messages.error(request, "Bu ijro allaqachon yuborilgan.")
        return redirect(a)
    form = SubmitForm(request.POST, request.FILES)
    if not form.is_valid():
        submissions = a.submissions.select_related("reviewed_by").prefetch_related("files")
        return render(request, "tasks/assignment.html", {
            "a": a, "task": a.task, "submissions": submissions,
            "submit_form": form, "review_form": ReviewForm(), "open_submit": True,
        }, status=400)
    with transaction.atomic():
        sub = Submission.objects.create(
            assignment=a, comment=form.cleaned_data["comment"], link=form.cleaned_data["link"]
        )
        for f in form.cleaned_data["files"]:
            SubmissionFile.objects.create(
                submission=sub, file=f, original_name=os.path.basename(f.name)[:255], size=f.size
            )
        a.status = Assignment.Status.SUBMITTED
        a.submitted_at = sub.created_at
        a.save(update_fields=["status", "submitted_at"])
        services.notify_submitted(a)
    messages.success(request, "Ijro yopildi va bo'lim boshlig'iga tasdiqlash uchun yuborildi.")
    return redirect(a)


@head_required
@require_POST
def assignment_review(request, pk):
    a = _get_assignment_for(request, pk)
    form = ReviewForm(request.POST)
    sub = a.submissions.filter(decision=Submission.Decision.WAITING).first()
    if a.status != Assignment.Status.SUBMITTED or sub is None:
        messages.error(request, "Bu ijro tasdiqlash holatida emas.")
        return redirect(a)
    if not form.is_valid():
        for errors in form.errors.values():
            for e in errors:
                messages.error(request, e)
        return redirect(a)
    approved = form.cleaned_data["action"] == "approve"
    comment = form.cleaned_data["comment"].strip()
    now = timezone.now()
    with transaction.atomic():
        sub.decision = Submission.Decision.APPROVED if approved else Submission.Decision.REJECTED
        sub.review_comment = comment
        sub.reviewed_by = request.user
        sub.reviewed_at = now
        sub.save()
        a.status = Assignment.Status.APPROVED if approved else Assignment.Status.REJECTED
        a.approved_at = now if approved else None
        a.save(update_fields=["status", "approved_at"])
        services.notify_reviewed(a, approved, comment)
    if approved:
        messages.success(request, f"{a.tutor.full_name} ijrosi tasdiqlandi.")
    else:
        messages.warning(request, f"{a.tutor.full_name} ijrosi qayta ishlash uchun qaytarildi.")
    next_url = request.POST.get("next")
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return redirect(next_url)
    return redirect(a)


@head_required
def review_queue(request):
    assignments = (
        Assignment.objects.filter(status=Assignment.Status.SUBMITTED)
        .select_related("task", "tutor", "tutor__faculty")
        .prefetch_related("submissions__files")
        .order_by("submitted_at")
    )
    return render(request, "tasks/review_queue.html", {"assignments": assignments, "review_form": ReviewForm()})


# ------------------------------------------------------------ fayllar

def _file_response(field, name):
    try:
        handle = field.open("rb")
    except FileNotFoundError:
        raise Http404("Fayl topilmadi")
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    inline = content_type.startswith("image/") or content_type == "application/pdf"
    return FileResponse(handle, as_attachment=not inline, filename=name, content_type=content_type)


@login_required
def task_file(request, pk):
    tf = get_object_or_404(TaskFile.objects.select_related("task"), pk=pk)
    if not (request.user.is_head or tf.task.assignments.filter(tutor=request.user).exists()):
        raise PermissionDenied
    return _file_response(tf.file, tf.original_name)


@login_required
def submission_file(request, pk):
    sf = get_object_or_404(SubmissionFile.objects.select_related("submission__assignment"), pk=pk)
    if not (request.user.is_head or sf.submission.assignment.tutor_id == request.user.pk):
        raise PermissionDenied
    return _file_response(sf.file, sf.original_name)
