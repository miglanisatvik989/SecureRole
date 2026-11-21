"""Navigation and form behavior added during the visual polish."""

from html import unescape
import re
from urllib.parse import parse_qs, urlsplit

from tests.test_features import demo, sign_in, submit


def find_link(body, label):
    return unescape(re.search(r'href="([^"]+)" aria-label="' + re.escape(label) + '"', body).group(1))


def test_sidebar_has_progressive_disclosure_for_the_current_role(demo):
    app, _ = demo
    page = sign_in(app, "birch").get("/dashboard/teacher").text
    assert 'aria-controls="sidebar-content" aria-expanded="true" hidden' in page
    assert 'id="sidebar-content" class="sidebar-body"' in page
    assert re.search(r'href="/dashboard/teacher" aria-current="page"', page)
    assert "Active sessions" in page and "Sign out" in page
    assert 'href="/users"' not in page


def test_record_form_returns_to_original_filtered_list(demo):
    app, ids = demo
    admin = sign_in(app, "atlas")
    listing = admin.get("/records", query_string={"q": "Dahlia", "teacher": ids["birch"], "sort": "marks-desc"})
    path = find_link(listing.text, "Edit record for Dahlia")
    page = admin.get(path)
    assert 'aria-label="Breadcrumb"' in page.text and "Academic details" in page.text
    result = submit(admin, path, course="Applied Mathematics", marks="87")
    destination = parse_qs(urlsplit(result.location).query)["return_to"][0]
    assert urlsplit(destination).path == "/records"
    assert parse_qs(urlsplit(destination).query) == {
        "q": ["Dahlia"], "teacher": [str(ids["birch"])], "sort": ["marks-desc"],
    }
    assert destination.replace("&", "&amp;") in admin.get(result.location).text


def test_account_return_context_survives_password_reset(demo):
    app, _ = demo
    admin = sign_in(app, "atlas")
    path = find_link(admin.get("/users?q=dahlia&role=Student").text, "Reset password for Dahlia")
    page = admin.get(path)
    assert "password-requirements" in page.text and "12–128 characters" in page.text
    response = submit(admin, path, password="fictional-rotated-password")
    assert urlsplit(response.location).path == "/users"
    assert parse_qs(urlsplit(response.location).query)["q"] == ["dahlia"]
    assert parse_qs(urlsplit(response.location).query)["role"] == ["Student"]


def test_return_context_is_limited_to_the_role_listing(demo):
    app, ids = demo
    teacher = sign_in(app, "birch")
    for target in ("https://example.test/records", "/users?q=fixture"):
        response = teacher.get(f"/records/{ids['first']}/edit", query_string={"return_to": target})
        assert response.status_code == 200
        assert 'href="/dashboard/teacher">My students' in response.text
        assert target not in response.text


def test_activity_labels_show_scope_without_changing_csv_values(demo):
    app, _ = demo
    admin = sign_in(app, "atlas")
    admin.get("/dashboard/admin")
    page = admin.get("/access-logs?action=dashboard.view&decision=Allowed")
    assert "View dashboard" in page.text and 'value="dashboard.view" selected' in page.text
    assert "Local verification checks the full journal" in page.text
    assert 'aria-label="Matching decisions"' in page.text
    csv = admin.get("/access-logs/export.csv?action=dashboard.view&decision=Allowed")
    assert '"dashboard.view"' in csv.text and '"View dashboard"' not in csv.text
