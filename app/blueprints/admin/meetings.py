# app/blueprints/admin/routes_meetings.py
from datetime import datetime, timedelta
from flask import request, redirect, url_for, flash
from flask_login import login_required, current_user
from ...extensions import db
from ...models.task import TaskRequest
from ...models.meeting import Meeting
from ...services.email_service import send_email
from ...security import roles_required
from . import admin_bp  

def _ics_for_meeting(task, meeting):
    dt_start = meeting.scheduled_for.strftime("%Y%m%dT%H%M%SZ")
    dt_end = (meeting.scheduled_for + timedelta(minutes=meeting.duration_minutes or 30)).strftime("%Y%m%dT%H%M%SZ")
    uid = f"task-{task.id}-meeting-{meeting.id}@taskdesk"
    title = f"Review: Task #{task.id} — {task.title}"
    desc = (meeting.notes or "").replace("\n", "\\n")
    loc = meeting.join_url or "Online"
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//TaskDesk//EN\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\nDTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}\r\n"
        f"DTSTART:{dt_start}\r\nDTEND:{dt_end}\r\n"
        f"SUMMARY:{title}\r\n"
        f"LOCATION:{loc}\r\n"
        f"DESCRIPTION:{desc}\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )

@admin_bp.post("/tasks/<int:task_id>/meetings", endpoint="meeting_create")
@login_required
@roles_required("admin")
def meeting_create(task_id):
    t = TaskRequest.query.get_or_404(task_id)
    when_raw = (request.form.get("scheduled_for") or "").strip()
    provider = (request.form.get("provider") or "internal").strip()
    duration = int(request.form.get("duration_minutes") or 30)
    join_url = (request.form.get("join_url") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    try:
        scheduled_for = datetime.strptime(when_raw, "%Y-%m-%dT%H:%M")
    except Exception:
        flash("Provide a valid date & time.", "warning")
        return redirect(url_for("admin.task_triage", task_id=t.id))

    m = Meeting(task_id=t.id, provider=provider, status="scheduled",
                scheduled_for=scheduled_for, duration_minutes=duration,
                join_url=join_url or None, notes=notes or None,
                created_by_id=current_user.id)
    db.session.add(m); db.session.commit()

    try:
        if t.client and t.client.email:
            ics_text = _ics_for_meeting(t, m)
            send_email(
                to=t.client.email,
                subject=f"Review meeting scheduled — Task #{t.id}",
                template="meeting_scheduled_client.html",
                task=t, meeting=m,
                attachments=[("review_meeting.ics", "text/calendar", ics_text)],
                task_link=url_for("client.task_view", task_id=t.id, _external=True),
            )
    except Exception:
        pass

    flash("Review meeting scheduled and client notified.", "success")
    return redirect(url_for("admin.task_triage", task_id=t.id))


@admin_bp.post("/meetings/<int:meeting_id>/cancel", endpoint="meeting_cancel")
@login_required
@roles_required("admin")
def meeting_cancel(meeting_id):
    m = Meeting.query.get_or_404(meeting_id)
    m.status = "canceled"; db.session.commit()
    t = m.task
    try:
        if t.client and t.client.email:
            send_email(
                to=t.client.email,
                subject=f"Review meeting canceled — Task #{t.id}",
                template="meeting_canceled_client.html",
                task=t, meeting=m,
                task_link=url_for("client.task_view", task_id=t.id, _external=True),
            )
    except Exception:
        pass
    flash("Meeting canceled. Client notified.", "info")
    return redirect(url_for("admin.task_triage", task_id=m.task_id))


@admin_bp.post("/meetings/<int:meeting_id>/reschedule", endpoint="meeting_reschedule")
@login_required
@roles_required("admin")
def meeting_reschedule(meeting_id):
    m = Meeting.query.get_or_404(meeting_id)
    when_raw = (request.form.get("scheduled_for") or "").strip()
    duration = int(request.form.get("duration_minutes") or (m.duration_minutes or 30))
    join_url = (request.form.get("join_url") or m.join_url or "").strip()
    notes = (request.form.get("notes") or m.notes or "").strip()
    try:
        new_dt = datetime.strptime(when_raw, "%Y-%m-%dT%H:%M")
    except Exception:
        flash("Provide a valid new date & time.", "warning")
        return redirect(url_for("admin.task_triage", task_id=m.task_id))
    m.scheduled_for = new_dt; m.duration_minutes = duration
    m.join_url = join_url or None; m.notes = notes or None
    m.status = "rescheduled"; db.session.commit()

    t = m.task
    try:
        if t.client and t.client.email:
            ics_text = _ics_for_meeting(t, m)
            send_email(
                to=t.client.email,
                subject=f"Review meeting rescheduled — Task #{t.id}",
                template="meeting_rescheduled_client.html",
                task=t, meeting=m,
                attachments=[("review_meeting.ics", "text/calendar", ics_text)],
                task_link=url_for("client.task_view", task_id=t.id, _external=True),
            )
    except Exception:
        pass
    flash("Meeting rescheduled. Client notified.", "success")
    return redirect(url_for("admin.task_triage", task_id=m.task_id))


@admin_bp.post("/meetings/<int:meeting_id>/complete", endpoint="meeting_complete")
@login_required
@roles_required("admin")
def meeting_complete(meeting_id):
    m = Meeting.query.get_or_404(meeting_id)
    m.status = "completed"; db.session.commit()
    flash("Meeting marked as completed.", "success")
    return redirect(url_for("admin.task_triage", task_id=m.task_id))



