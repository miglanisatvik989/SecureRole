"""Shared server-side filters and pagination for account and record lists."""

from dataclasses import dataclass

from flask import request
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from app.models import Role, StudentRecord, SUPPORTED_ROLES, User, db

PAGE_SIZE = 20
NAME_SORTS = (("name", "Name (A–Z)"), ("name-desc", "Name (Z–A)"))
RECORD_SORTS = NAME_SORTS + (("marks-desc", "Marks (high to low)"), ("marks", "Marks (low to high)"))
AVAILABILITY = (("recorded", "Has a record"), ("waiting", "Awaiting record"))


@dataclass
class Listing:
    rows: list
    total: int
    page: int
    pages: int
    filters: dict
    fields: tuple


def search_text():
    return request.args.get("q", "").strip()[:100]


def selected(field, options, default=""):
    value = request.args.get(field, default)
    return value if any(value == key for key, _ in options) else default


def paginate(statement, filters, fields, *, page_size=PAGE_SIZE):
    total = db.session.scalar(db.select(func.count()).select_from(statement.order_by(None).subquery()))
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(pages, max(1, request.args.get("page", 1, type=int)))
    rows = db.session.scalars(statement.limit(page_size).offset((page - 1) * page_size)).all()
    return Listing(rows, total, page, pages, filters, fields)


def teacher_options():
    teachers = db.session.execute(db.select(User.id, User.display_name, User.username)
                                  .where(User.role.has(Role.name == "Teacher"))
                                  .order_by(func.lower(User.display_name), User.id)).all()
    return (("unassigned", "Unassigned"),) + tuple(
        (str(identity), f"{name} (@{username})") for identity, name, username in teachers
    )


def assigned_filter(statement, teacher):
    if teacher == "unassigned":
        return statement.where(User.role.has(Role.name == "Student"), User.assigned_teacher_id.is_(None))
    if teacher:
        return statement.where(User.assigned_teacher_id == int(teacher))
    return statement


def matching(statement, q, *columns):
    if q:
        return statement.where(or_(*(column.icontains(q, autoescape=True) for column in columns)))
    return statement


def name_order(sort):
    name = func.lower(User.display_name)
    return name.desc() if sort == "name-desc" else name.asc()


def student_listing(statement, *, admin=False):
    """Filter an already scoped student query, including students with no record."""
    q = search_text()
    record = selected("record", AVAILABILITY)
    sort = selected("sort", RECORD_SORTS, "name")
    filters = dict(q=q, record=record, sort=sort)
    fields = [("record", "Record availability", "All students", AVAILABILITY)]
    statement = statement.outerjoin(User.student_record).options(
        joinedload(User.student_record), joinedload(User.assigned_teacher)
    )
    search_columns = [User.display_name, User.username]
    if admin:
        teachers = teacher_options()
        courses = tuple((course, course) for course in db.session.scalars(
            db.select(StudentRecord.course).distinct().order_by(func.lower(StudentRecord.course), StudentRecord.course)
        ))
        teacher = selected("teacher", teachers)
        course = selected("course", courses)
        filters.update(teacher=teacher, course=course)
        fields = [("teacher", "Assigned teacher", "All teachers", teachers),
                  ("course", "Course", "All courses", courses), *fields]
        statement = assigned_filter(statement, teacher)
        if course:
            statement = statement.where(StudentRecord.course == course)
        search_columns.append(StudentRecord.course)
    statement = matching(statement, q, *search_columns)
    if record:
        statement = statement.where(StudentRecord.id.is_not(None) if record == "recorded"
                                    else StudentRecord.id.is_(None))
    if sort in {"marks", "marks-desc"}:
        score = StudentRecord.marks.desc() if sort == "marks-desc" else StudentRecord.marks.asc()
        statement = statement.order_by(StudentRecord.marks.is_(None), score)
    fields.append(("sort", "Sort by", None, RECORD_SORTS))
    return paginate(statement.order_by(name_order(sort), User.id), filters, tuple(fields))


def account_listing():
    q = search_text()
    roles = tuple((name, name) for name in SUPPORTED_ROLES)
    teachers = teacher_options()
    role = selected("role", roles)
    teacher = selected("teacher", teachers)
    sort = selected("sort", NAME_SORTS, "name")
    statement = db.select(User).options(joinedload(User.role), joinedload(User.assigned_teacher))
    statement = matching(statement, q, User.display_name, User.username, User.email)
    if role:
        statement = statement.where(User.role.has(Role.name == role))
    statement = assigned_filter(statement, teacher).order_by(name_order(sort), User.id)
    fields = (("role", "Role", "All roles", roles),
              ("teacher", "Assigned teacher", "Any assignment", teachers),
              ("sort", "Sort by", None, NAME_SORTS))
    return paginate(statement, dict(q=q, role=role, teacher=teacher, sort=sort), fields)
