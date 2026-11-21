import re
from urllib.parse import parse_qs, urlsplit

import pytest

from app import create_app
from app.migrations import migrate_database
from app.models import Role, User, db


DEMO_PASSWORD = "test-only password with spaces "


@pytest.fixture
def auth_app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-signing-key",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'auth.db'}",
    })
    with app.app_context():
        migrate_database()
        for name in ("Admin", "Teacher", "Student"):
            account = User(username=name.lower(), display_name=f"Demo {name}", role=Role(name=name))
            account.set_password(DEMO_PASSWORD)
            db.session.add(account)
        db.session.commit()
    yield app
    with app.app_context():
        db.engine.dispose()


@pytest.fixture
def client(auth_app):
    return auth_app.test_client()


def csrf_token(response):
    match = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', response.data)
    assert match, response.data
    return match.group(1).decode()


def sign_in(client, username="student", password=DEMO_PASSWORD, path="/login"):
    token = csrf_token(client.get(path))
    return client.post(path, data={
        "username": username,
        "password": password,
        "csrf_token": token,
    })


@pytest.mark.parametrize("role", ["admin", "teacher", "student"])
def test_valid_login_and_role_dashboard(client, role):
    result = sign_in(client, username=role)
    assert result.status_code == 303
    assert result.location == f"/dashboard/{role}"
    dashboard = client.get(result.location)
    assert dashboard.status_code == 200
    assert f"Demo {role.title()}".encode() in dashboard.data
    assert f"{role.title()} dashboard".encode() in dashboard.data
    assert b"Sign out" in dashboard.data
    assert b"Cryptography" not in dashboard.data
    assert client.get("/login").location == result.location
    assert client.get("/").location == result.location


@pytest.mark.parametrize("username,password", [
    ("student", "incorrect"),
    ("unknown-user", DEMO_PASSWORD),
])
def test_invalid_credentials(client, username, password):
    result = sign_in(client, username=username, password=password)
    assert result.status_code == 401
    assert b"Invalid username or password." in result.data
    assert password.encode() not in result.data
    assert client.get("/dashboard").status_code == 302


@pytest.mark.parametrize("username,password,message", [
    ("", DEMO_PASSWORD, b"Enter your username."),
    ("   ", DEMO_PASSWORD, b"Enter your username."),
    ("student", "", b"Enter your password."),
])
def test_required_fields(client, username, password, message):
    result = sign_in(client, username=username, password=password)
    assert result.status_code == 400
    assert message in result.data
    assert b'aria-invalid="true"' in result.data
    assert client.get("/dashboard/student").status_code == 302


@pytest.mark.parametrize("path", ["/dashboard", "/dashboard/admin", "/dashboard/teacher", "/dashboard/student"])
def test_anonymous_access_is_protected(client, path):
    result = client.get(path)
    assert result.status_code == 302
    destination = urlsplit(result.location)
    assert destination.path == "/login"
    assert parse_qs(destination.query) == {"next": [path]}


def test_session_persists_and_other_roles_are_forbidden(client, auth_app):
    login = sign_in(client)
    cookie = login.headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "; Secure" not in cookie
    assert "no-store" in login.headers["Cache-Control"]
    assert client.get("/dashboard").location == "/dashboard/student"
    assert client.get("/dashboard/student").status_code == 200
    assert client.get("/dashboard/admin").status_code == 403
    assert client.get("/dashboard/teacher").status_code == 403
    assert client.get("/dashboard/unknown").status_code == 404
    assert auth_app.test_client().get("/dashboard/student").status_code == 302


def test_https_cookie_configuration(client, auth_app):
    auth_app.config["SESSION_COOKIE_SECURE"] = True
    response = client.get("/login", base_url="https://localhost")
    assert "; Secure" in response.headers["Set-Cookie"]


@pytest.mark.parametrize("target", [
    "https://example.test/",
    "//example.test/",
    "/dashboard/admin",
    "/%5Cexample.test/",
])
def test_unapproved_return_destinations_fall_back_to_own_dashboard(client, target):
    result = sign_in(client, path=f"/login?next={target}")
    assert result.location == "/dashboard/student"


def test_safe_dashboard_dispatcher_is_honored(client):
    result = sign_in(client, path="/login?next=/dashboard")
    assert result.location == "/dashboard"
    assert client.get(result.location).location == "/dashboard/student"


def test_logout_requires_post_and_clears_session(client):
    login = sign_in(client)
    assert client.get("/logout").status_code == 405
    with client.session_transaction() as session:
        session["example_state"] = "clear this"
    result = client.post("/logout", data={"csrf_token": csrf_token(client.get(login.location))})
    assert result.status_code == 303
    assert result.location == "/login"
    with client.session_transaction() as session:
        assert not session
    assert client.get("/dashboard/student").status_code == 302


@pytest.mark.parametrize("supplied", [{}, {"csrf_token": "invalid"}])
def test_login_rejects_missing_or_invalid_csrf(client, supplied):
    client.get("/login")
    result = client.post("/login", data={"username": "student", "password": DEMO_PASSWORD, **supplied})
    assert result.status_code == 400
    assert b"could not be verified" in result.data
    assert client.get("/dashboard").status_code == 302
    assert client.post("/login", data={
        "username": "student", "password": DEMO_PASSWORD, "csrf_token": csrf_token(result),
    }).status_code == 303


def test_login_rejects_token_from_other_session(client, auth_app):
    token = csrf_token(auth_app.test_client().get("/login"))
    client.get("/login")
    result = client.post("/login", data={
        "username": "student", "password": DEMO_PASSWORD, "csrf_token": token,
    })
    assert result.status_code == 400


@pytest.mark.parametrize("supplied", [{}, {"csrf_token": "invalid"}])
def test_logout_rejects_missing_or_invalid_csrf(client, supplied):
    login = sign_in(client)
    result = client.post("/logout", data=supplied)
    assert result.status_code == 400
    assert b"Form could not be verified" in result.data
    assert client.get(login.location).status_code == 200
