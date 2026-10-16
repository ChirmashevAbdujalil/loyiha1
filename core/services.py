"""Bildirishnomalar va hisobot hisob-kitoblari."""
from collections import defaultdict

from django.urls import reverse

from .models import Assignment, Notification, Submission
from .utils import uz_datetime


def notify(user, kind, title, message="", url=""):
    return Notification.objects.create(user=user, kind=kind, title=title, message=message, url=url)


def notify_new_assignments(assignments):
    Notification.objects.bulk_create(
        [
            Notification(
                user=a.tutor,
                kind=Notification.Kind.NEW_TASK,
                title=f"Yangi topshiriq: {a.task.title}",
                message=f"Ijro muddati: {uz_datetime(a.task.deadline)}",
                url=reverse("assignment_detail", args=[a.pk]),
            )
            for a in assignments
        ]
    )


def notify_task_updated(task):
    Notification.objects.bulk_create(
        [
            Notification(
                user=a.tutor,
                kind=Notification.Kind.UPDATED,
                title=f"Topshiriq o'zgartirildi: {task.title}",
                message=f"Ijro muddati: {uz_datetime(task.deadline)}",
                url=reverse("assignment_detail", args=[a.pk]),
            )
            for a in task.assignments.select_related("tutor")
            if a.status != Assignment.Status.APPROVED
        ]
    )


def notify_submitted(assignment):
    notify(
        assignment.task.created_by,
        Notification.Kind.SUBMITTED,
        f"{assignment.tutor.full_name} ijroni yopdi",
        assignment.task.title,
        reverse("assignment_detail", args=[assignment.pk]),
    )


def notify_reviewed(assignment, approved, comment=""):
    if approved:
        kind, title = Notification.Kind.APPROVED, f"Ijro tasdiqlandi: {assignment.task.title}"
    else:
        kind, title = Notification.Kind.REJECTED, f"Ijro qaytarildi: {assignment.task.title}"
    notify(assignment.tutor, kind, title, comment, reverse("assignment_detail", args=[assignment.pk]))


# ---------------------------------------------------------------- hisobot

REPORT_DONE = "done"          # tasdiqlangan — yashil
REPORT_REVIEW = "review"      # yuborilgan, tasdiq kutilmoqda — sariq
REPORT_NOT_DONE = "not_done"  # bajarilmagan — qizil
REPORT_NOT_DUE = "not_due"    # muddati hali kelmagan, bajarilmagan — kulrang/ko'k


def assignment_state_at(assignment, submissions, as_of):
    """Ijroning `as_of` vaqtidagi holati — tarix (Submission) asosida tiklanadi.

    submissions — shu ijroning barcha yuborishlari, yangisi birinchi.
    """
    for sub in submissions:
        if sub.created_at > as_of:
            continue
        if sub.reviewed_at and sub.reviewed_at <= as_of:
            if sub.decision == Submission.Decision.APPROVED:
                return REPORT_DONE, sub
            break  # qaytarilgan — demak bajarilmagan
        return REPORT_REVIEW, sub
    if assignment.task.deadline > as_of:
        return REPORT_NOT_DUE, None
    return REPORT_NOT_DONE, None


def build_report(assignments, as_of):
    """Tyutor × topshiriq matritsasi.

    Qaytaradi: tasks (ustunlar), rows (har bir tyutor uchun kataklar va
    statistika), totals.
    """
    assignments = list(assignments)
    subs_by_assignment = defaultdict(list)
    for sub in (
        Submission.objects.filter(assignment__in=assignments)
        .order_by("-created_at")
        .only("assignment_id", "created_at", "reviewed_at", "decision", "link", "comment")
    ):
        subs_by_assignment[sub.assignment_id].append(sub)

    tasks = sorted({a.task for a in assignments}, key=lambda t: (t.deadline, t.pk))
    tutors = sorted(
        {a.tutor for a in assignments},
        key=lambda u: ((u.faculty.name if u.faculty else "яяя"), u.last_name, u.first_name),
    )
    cell_map = {}
    for a in assignments:
        state, sub = assignment_state_at(a, subs_by_assignment[a.pk], as_of)
        late = bool(sub and sub.created_at > a.task.deadline)
        cell_map[(a.tutor_id, a.task_id)] = {"state": state, "submission": sub, "late": late, "assignment": a}

    rows = []
    totals = defaultdict(int)
    for tutor in tutors:
        cells = []
        stats = defaultdict(int)
        for task in tasks:
            cell = cell_map.get((tutor.pk, task.pk))
            cells.append(cell)
            if cell:
                stats[cell["state"]] += 1
                stats["total"] += 1
        due = stats["total"] - stats[REPORT_NOT_DUE]
        stats["percent"] = round(stats[REPORT_DONE] * 100 / stats["total"]) if stats["total"] else 0
        stats["due"] = due
        for key in (REPORT_DONE, REPORT_REVIEW, REPORT_NOT_DONE, REPORT_NOT_DUE, "total"):
            totals[key] += stats[key]
        rows.append({"tutor": tutor, "cells": cells, "stats": dict(stats)})

    for task in tasks:
        task.report_done = sum(1 for r in rows for c in r["cells"]
                               if c and c["assignment"].task_id == task.pk and c["state"] == REPORT_DONE)
        task.report_total = sum(1 for r in rows for c in r["cells"]
                                if c and c["assignment"].task_id == task.pk)

    totals["percent"] = round(totals[REPORT_DONE] * 100 / totals["total"]) if totals["total"] else 0
    return {"tasks": tasks, "rows": rows, "totals": dict(totals)}
