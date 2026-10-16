import datetime as dt
from io import BytesIO

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from .. import services
from ..decorators import head_required
from ..models import Assignment, Faculty, User
from ..utils import month_bounds, parse_date, uz_date, uz_datetime


def _report_params(request):
    today = timezone.localdate()
    first, last = month_bounds(today.year, today.month)
    date_from = parse_date(request.GET.get("from"), first)
    date_to = parse_date(request.GET.get("to"), last)
    if date_to < date_from:
        date_from, date_to = date_to, date_from

    as_of = timezone.now()
    raw = request.GET.get("as_of", "").strip()
    if raw:
        try:
            as_of = timezone.make_aware(dt.datetime.fromisoformat(raw))
        except ValueError:
            pass

    faculty_id = request.GET.get("faculty", "")
    tutor_id = request.GET.get("tutor", "")
    by = "exec" if request.GET.get("by") == "exec" else "deadline"

    qs = Assignment.objects.select_related("task", "tutor", "tutor__faculty").filter(
        task__created_at__lte=as_of, created_at__lte=as_of
    )
    if by == "exec":
        qs = qs.filter(task__execution_date__range=(date_from, date_to))
    else:
        qs = qs.filter(task__deadline__date__range=(date_from, date_to))
    if faculty_id.isdigit():
        qs = qs.filter(tutor__faculty_id=faculty_id)
    if tutor_id.isdigit():
        qs = qs.filter(tutor_id=tutor_id)
    return {
        "qs": qs,
        "date_from": date_from,
        "date_to": date_to,
        "as_of": as_of,
        "faculty_id": faculty_id,
        "tutor_id": tutor_id,
        "by": by,
    }


@head_required
def report(request):
    p = _report_params(request)
    data = services.build_report(p["qs"], p["as_of"])

    # Fakultetlar kesimida qisqa xulosa
    faculty_summary = {}
    for row in data["rows"]:
        key = row["tutor"].faculty
        s = faculty_summary.setdefault(key, {"faculty": key, "tutors": 0, "total": 0, "done": 0, "review": 0, "not_done": 0})
        s["tutors"] += 1
        s["total"] += row["stats"].get("total", 0)
        s["done"] += row["stats"].get("done", 0)
        s["review"] += row["stats"].get("review", 0)
        s["not_done"] += row["stats"].get("not_done", 0)
    for s in faculty_summary.values():
        s["percent"] = round(s["done"] * 100 / s["total"]) if s["total"] else 0

    query = request.GET.copy()
    return render(request, "reports/report.html", {
        **data,
        **{k: v for k, v in p.items() if k != "qs"},
        "as_of_input": timezone.localtime(p["as_of"]).strftime("%Y-%m-%dT%H:%M"),
        "faculties": Faculty.objects.all(),
        "tutors": User.objects.filter(role=User.Role.TUTOR).select_related("faculty").order_by("last_name"),
        "faculty_summary": sorted(faculty_summary.values(), key=lambda s: -s["percent"]),
        "export_query": query.urlencode(),
    })


@head_required
def report_export(request):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    p = _report_params(request)
    data = services.build_report(p["qs"], p["as_of"])
    tasks, rows, totals = data["tasks"], data["rows"], data["totals"]

    wb = Workbook()
    ws = wb.active
    ws.title = "Ijro hisoboti"

    thin = Side(style="thin", color="D0D5DD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    head_fill = PatternFill("solid", fgColor="1E1B4B")
    fills = {
        services.REPORT_DONE: PatternFill("solid", fgColor="C6F6D5"),
        services.REPORT_REVIEW: PatternFill("solid", fgColor="FEEBC8"),
        services.REPORT_NOT_DONE: PatternFill("solid", fgColor="FED7D7"),
        services.REPORT_NOT_DUE: PatternFill("solid", fgColor="E2E8F0"),
    }
    fonts = {
        services.REPORT_DONE: Font(bold=True, color="22543D"),
        services.REPORT_REVIEW: Font(bold=True, color="7B341E"),
        services.REPORT_NOT_DONE: Font(bold=True, color="9B2C2C"),
        services.REPORT_NOT_DUE: Font(color="4A5568"),
    }
    labels = {
        services.REPORT_DONE: "✔ Bajardi",
        services.REPORT_REVIEW: "◷ Tasdiqlashda",
        services.REPORT_NOT_DONE: "✘ Bajarmadi",
        services.REPORT_NOT_DUE: "… Muddati kelmagan",
    }

    fixed_cols = 4  # №, F.I.Sh, Fakultet, (oxirida statistikalar)
    last_col = 3 + len(tasks) + 4
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(last_col, 6))
    ws["A1"] = "Tyutorlar ijro intizomi bo'yicha hisobot"
    ws["A1"].font = Font(size=15, bold=True, color="1E1B4B")
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(last_col, 6))
    ws["A2"] = (
        f"Davr: {uz_date(p['date_from'])} — {uz_date(p['date_to'])}   |   "
        f"Holat: {uz_datetime(p['as_of'])} holatiga   |   "
        f"Umumiy ijro: {totals.get('done', 0)}/{totals.get('total', 0)} ({totals.get('percent', 0)}%)"
    )
    ws["A2"].font = Font(size=10, color="475467")

    header_row = 4
    headers = ["№", "Tyutor F.I.Sh", "Fakultet"]
    headers += [f"{t.number}\n{t.title[:60]}\nMuddat: {timezone.localtime(t.deadline):%d.%m.%Y %H:%M}" for t in tasks]
    headers += ["Jami", "Bajardi", "Bajarmadi", "Foiz"]
    for col, text in enumerate(headers, 1):
        c = ws.cell(row=header_row, column=col, value=text)
        c.font = Font(bold=True, color="FFFFFF", size=10)
        c.fill = head_fill
        c.alignment = center
        c.border = border
    ws.row_dimensions[header_row].height = 75

    for i, row in enumerate(rows, 1):
        r = header_row + i
        tutor = row["tutor"]
        ws.cell(row=r, column=1, value=i).alignment = center
        ws.cell(row=r, column=2, value=tutor.full_name).alignment = left
        ws.cell(row=r, column=3, value=tutor.faculty.label if tutor.faculty else "—").alignment = left
        for j, cell in enumerate(row["cells"]):
            c = ws.cell(row=r, column=4 + j)
            if cell:
                text = labels[cell["state"]]
                if cell["late"] and cell["state"] in (services.REPORT_DONE, services.REPORT_REVIEW):
                    text += " (kechikib)"
                c.value = text
                c.fill = fills[cell["state"]]
                c.font = fonts[cell["state"]]
            else:
                c.value = "—"
                c.font = Font(color="98A2B3")
            c.alignment = center
        stats = row["stats"]
        base = 4 + len(tasks)
        for k, value in enumerate(
            [stats.get("total", 0), stats.get("done", 0), stats.get("not_done", 0), f"{stats.get('percent', 0)}%"]
        ):
            c = ws.cell(row=r, column=base + k, value=value)
            c.alignment = center
            c.font = Font(bold=True)
        pct = stats.get("percent", 0)
        ws.cell(row=r, column=base + 3).fill = (
            fills[services.REPORT_DONE] if pct >= 80 else fills[services.REPORT_REVIEW] if pct >= 50
            else fills[services.REPORT_NOT_DONE]
        )
        for col in range(1, last_col + 1):
            ws.cell(row=r, column=col).border = border
        ws.row_dimensions[r].height = 22

    # Jami qatori
    r = header_row + len(rows) + 1
    ws.cell(row=r, column=2, value="JAMI").font = Font(bold=True)
    for j, t in enumerate(tasks):
        c = ws.cell(row=r, column=4 + j, value=f"{t.report_done}/{t.report_total}")
        c.alignment = center
        c.font = Font(bold=True)
    base = 4 + len(tasks)
    for k, value in enumerate(
        [totals.get("total", 0), totals.get("done", 0), totals.get("not_done", 0), f"{totals.get('percent', 0)}%"]
    ):
        c = ws.cell(row=r, column=base + k, value=value)
        c.alignment = center
        c.font = Font(bold=True)
    for col in range(1, last_col + 1):
        ws.cell(row=r, column=col).border = border
        ws.cell(row=r, column=col).fill = PatternFill("solid", fgColor="F2F4F7")

    # Shartli belgilar
    r += 2
    ws.cell(row=r, column=2, value="Shartli belgilar:").font = Font(bold=True)
    for k, state in enumerate(
        [services.REPORT_DONE, services.REPORT_NOT_DONE, services.REPORT_REVIEW, services.REPORT_NOT_DUE]
    ):
        c = ws.cell(row=r + 1 + k, column=2, value=labels[state])
        c.fill = fills[state]
        c.font = fonts[state]

    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 32
    ws.column_dimensions["C"].width = 18
    for j in range(len(tasks)):
        ws.column_dimensions[get_column_letter(4 + j)].width = 22
    for k in range(4):
        ws.column_dimensions[get_column_letter(4 + len(tasks) + k)].width = 11
    ws.freeze_panes = ws.cell(row=header_row + 1, column=fixed_cols)
    ws.sheet_view.zoomScale = 90
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    buffer = BytesIO()
    wb.save(buffer)
    stamp = timezone.localtime(p["as_of"]).strftime("%Y-%m-%d_%H-%M")
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="ijro_hisoboti_{stamp}.xlsx"'
    return response
