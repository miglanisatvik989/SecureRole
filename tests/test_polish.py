"""Dashboard, lookup and audit report checks against isolated data."""

import csv
from datetime import datetime, timezone
from html import unescape
import io
import re

import pytest

from app.audit_integrity import Verification
from app.models import AccessLog, StudentRecord, User, db
from tests.test_features import demo, metric, sign_in


@pytest.mark.parametrize("username,role,expected", [
    ("atlas", "Admin", ("All records", "All records", "All records", "Allowed", "Allowed", "Allowed", "Allowed")),
    ("birch", "Teacher", ("Assigned only", "Assigned only", "Assigned only", "Restricted", "Restricted", "Restricted", "Restricted")),
    ("dahlia", "Student", ("Own only", "Restricted", "Restricted", "Restricted", "Restricted", "Restricted", "Restricted")),
])
def test_permissions_panel_matches_policy(demo, username, role, expected):
    app, _ = demo
    body = sign_in(app, username).get(f"/dashboard/{role.lower()}").text
    panel = body[body.index('id="permissions-title"'):]
    assert "My permissions" in panel and f'class="role-badge">{role}<' in panel
    assert tuple(re.findall(r'<dd><span[^>]+>([^<]+)</span></dd>', panel)) == expected
    if role == "Student":
        assert 'aria-label="Academic marks out of 100"' in body and 'value="82.0"' in body


def test_admin_record_filters_sorting_and_empty_state(demo):
    app, ids = demo
    admin = sign_in(app, "atlas")
    body = admin.get("/records?sort=marks-desc").text
    assert body.index("@fern") < body.index("@dahlia") < body.index("@elm")
    assert "4 results" in body and "Awaiting record" in body
    body = admin.get("/records", query_string={"teacher": ids["birch"], "course": "Applied Mathematics", "q": "MATHEMATICS"}).text
    assert "1 result" in body and "@dahlia" in body and "@fern" not in body
    body = admin.get("/records", query_string={"teacher": ids["birch"], "record": "waiting", "q": "elm"}).text
    assert "1 result" in body and "@elm" in body and "@dahlia" not in body
    response = admin.get("/records?q=NoSuchName")
    assert response.status_code == 200 and "No students match your filters" in response.text
    assert 'href="/records">Clear filters' in response.text


def test_teacher_filters_never_expand_assignment_scope(demo):
    app, ids = demo
    teacher = sign_in(app, "birch")
    body = teacher.get("/dashboard/teacher", query_string={"q": "fern", "teacher": ids["cedar"]}).data
    assert b"No students match your filters" in body and b"Earth Science" not in body
    metric(body, "Assigned students", 2)
    assert b"0 results" in body
    body = teacher.get("/dashboard/teacher?record=waiting&sort=marks").data
    assert b"Add record for Elm" in body and b"Edit record for Dahlia" not in body
    body = teacher.get("/dashboard/teacher?record=recorded").data
    assert b"View record for Dahlia" in body and b"Edit record for Dahlia" in body


def test_user_email_and_assignment_filters(demo):
    app, ids = demo
    with app.app_context():
        db.session.get(User, ids["dahlia"]).email = "records@example.test"
        db.session.commit()
    admin = sign_in(app, "atlas")
    body = admin.get("/users", query_string={
        "q": "RECORDS@EXAMPLE", "role": "Student", "teacher": ids["birch"], "sort": "name-desc",
    }).text
    assert "1 result" in body and "@dahlia" in body and "@elm" not in body
    assert 'value="name-desc" selected' in body
    assert "No accounts match your filters" in admin.get("/users?q=%25").text
    body = admin.get("/users?role=Student&teacher=unassigned").text
    assert "1 result" in body and "@grove" in body and "@dahlia" not in body


def test_lists_paginate_with_filters_and_stable_order(demo):
    app, ids = demo
    with app.app_context():
        teacher = db.session.get(User, ids["birch"])
        student = db.session.get(User, ids["elm"])
        for index in range(21):
            db.session.add(User(username=f"fixture-{index:02}", display_name=f"Fixture {index:02}",
                                role=student.role, assigned_teacher=teacher, password_hash=student.password_hash))
        db.session.commit()
    admin = sign_in(app, "atlas")
    for endpoint in ("/users", "/records"):
        response = admin.get(endpoint, query_string={"q": "fixture-", "teacher": ids["birch"], "sort": "name-desc"})
        assert response.status_code == 200 and "21 results" in response.text
        assert "@fixture-20" in response.text and "@fixture-00" not in response.text
        target = unescape(re.search(r'rel="next" href="([^"]+)"', response.text).group(1))
        assert "q=fixture-" in target and f"teacher={ids['birch']}" in target and "sort=name-desc" in target
        second = admin.get(target).text
        assert "Page 2 of 2" in second and "@fixture-00" in second and "@fixture-20" not in second


def test_audit_csv_uses_scope_snapshot_and_safe_text(demo):
    app, ids = demo
    with app.app_context():
        actor = db.session.get(User, ids["dahlia"])
        actor.display_name = "=A1"
        stamp = datetime(2025, 1, 3, 12, 30, tzinfo=timezone.utc)
        db.session.add(AccessLog(actor=actor, action="test.report", resource=" +fixture", decision="Denied", timestamp=stamp))
        db.session.add(AccessLog(action="test.report", resource="plain, quoted", decision="Denied", timestamp=stamp))
        db.session.add(AccessLog(action="test.report", resource="allowed", decision="Allowed", timestamp=stamp))
        db.session.commit()
        last = db.session.scalar(db.select(db.func.max(AccessLog.id)))
    admin = sign_in(app, "atlas")
    result = admin.get("/access-logs/export.csv", query_string={"decision": "Denied", "action": "test.report", "snapshot": last})
    assert result.status_code == 200 and result.mimetype == "text/csv"
    assert "recorded-audit-events.csv" in result.headers["Content-Disposition"]
    assert "no-store" in result.headers["Cache-Control"]
    reader = csv.DictReader(io.StringIO(result.text))
    rows = list(reader)
    assert reader.fieldnames == ["Audit entry ID", "UTC timestamp", "Actor name", "Historical actor role",
                                 "Requested action", "Resource", "Authorization decision"]
    assert len(rows) == 2 and rows[0]["Actor name"] == "Anonymous"
    assert rows[0]["Resource"] == "plain, quoted"
    assert rows[1]["Actor name"] == "'=A1" and rows[1]["Historical actor role"] == "Student"
    assert rows[1]["Resource"] == "' +fixture" and rows[1]["UTC timestamp"] == "2025-01-03T12:30:00+00:00"
    assert all(row["Authorization decision"] == "Denied" for row in rows)
    filtered = admin.get("/access-logs/export.csv?q=dahlia&action=test.report")
    assert len(list(csv.DictReader(io.StringIO(filtered.text)))) == 1
    body = admin.get("/access-logs?q=dahlia&decision=Denied").text
    assert "/access-logs/export.csv?decision=Denied" in body and "q=dahlia" in body
    assert sign_in(app, "birch").get("/access-logs/export.csv").status_code == 403
    assert sign_in(app, "dahlia").get("/access-logs/export.csv").status_code == 403
    assert app.test_client().get("/access-logs/export.csv").status_code == 302


def test_audit_export_refuses_unverified_journal(demo, monkeypatch):
    app, _ = demo
    admin = sign_in(app, "atlas")
    monkeypatch.setattr("app.activity.inspect_audit", lambda *args: Verification(False, "Fixture mismatch"))
    response = admin.get("/access-logs/export.csv")
    assert response.status_code == 503
    assert b"Audit integrity check failed" in response.data
    assert "Content-Disposition" not in response.headers
