"""Academic record pages and permission-scoped mutations."""

from flask import Blueprint, abort, flash, redirect, request, url_for
from flask_login import current_user
from sqlalchemy.orm import joinedload

from app.forms import DeleteRecordForm, RecordForm
from app.models import StudentRecord, User, db
from app.rbac import Action, is_allowed, require_permission, scoped_records, scoped_students
from app.workspace import render_workspace, save_changes

records = Blueprint("records", __name__)


def record_rows(limit=None):
    statement = scoped_records(current_user.id).options(
        joinedload(StudentRecord.student).joinedload(User.assigned_teacher)
    ).order_by(StudentRecord.id.desc()).limit(limit)
    return db.session.scalars(statement).all()


def scoped_record(record_id, action):
    return db.session.scalar(scoped_records(current_user.id, action).where(StudentRecord.id == record_id))


def record_return_url():
    if current_user.role.name == "Admin":
        return url_for("records.index")
    return url_for("main.dashboard")


@records.get("/records")
def index():
    require_permission(Action.LIST_RECORDS)
    return render_workspace("records/list.html", rows=record_rows(), active="records")


@records.get("/records/new")
def pick_student():
    require_permission(Action.LIST_RECORDS)
    students = db.session.scalars(scoped_students(current_user.id, Action.CREATE_RECORD)
                                  .where(~User.student_record.has()).order_by(User.display_name, User.id)).all()
    return render_workspace("records/pick.html", students=students, active="records")


@records.get("/records/<int:record_id>")
def detail(record_id):
    require_permission(Action.VIEW_RECORD, record_id=record_id)
    record = scoped_record(record_id, Action.VIEW_RECORD)
    if record is None:
        abort(403)
    return render_workspace("records/detail.html", record=record, active="records",
                            can_edit=is_allowed(current_user.id, Action.EDIT_RECORD, record_id=record_id),
                            can_delete=is_allowed(current_user.id, Action.DELETE_RECORD, record_id=record_id),
                            delete_form=DeleteRecordForm())


@records.route("/students/<int:student_id>/record/new", methods=["GET", "POST"])
def create(student_id):
    form = RecordForm()
    error, status = None, 200
    if form.validate_on_submit():
        def change():
            require_permission(Action.CREATE_RECORD, student_id=student_id, atomic=True)
            student = db.session.get(User, student_id, populate_existing=True)
            if student.student_record is not None:
                raise ValueError("This student already has an academic record.")
            db.session.add(StudentRecord(student=student, course=form.course.data, marks=form.marks.data))

        error, status = save_changes(change)
        if error is None:
            flash("Academic record created.", "success")
            return redirect(record_return_url(), code=303)
    elif request.method == "POST":
        require_permission(Action.CREATE_RECORD, student_id=student_id, atomic=True)
        db.session.rollback()
        status = 400
    else:
        require_permission(Action.CREATE_RECORD, student_id=student_id)
    if error and not is_allowed(getattr(current_user, "id", None), Action.CREATE_RECORD, student_id=student_id):
        require_permission(Action.CREATE_RECORD, student_id=student_id)
    student = db.session.get(User, student_id)
    if student is None:
        abort(403)
    if request.method == "GET" and student.student_record is not None:
        error, status = "This student already has an academic record.", 409
    return render_workspace("workspace_form.html", title="Add academic record", subject=student.display_name,
                            form=form, fields=(form.course, form.marks), error=error, status=status,
                            cancel=record_return_url(), active="records")


@records.route("/records/<int:record_id>/edit", methods=["GET", "POST"])
def edit(record_id):
    error, status = None, 200
    if request.method == "GET":
        require_permission(Action.EDIT_RECORD, record_id=record_id)
        record = scoped_record(record_id, Action.EDIT_RECORD)
        if record is None:
            abort(403)
        form = RecordForm(obj=record)
    else:
        form = RecordForm()
        if form.validate():
            def change():
                require_permission(Action.EDIT_RECORD, record_id=record_id, atomic=True)
                record = scoped_record(record_id, Action.EDIT_RECORD)
                record.course = form.course.data
                record.marks = form.marks.data

            error, status = save_changes(change)
            if error is None:
                flash("Academic record updated.", "success")
                return redirect(url_for("records.detail", record_id=record_id), code=303)
        else:
            require_permission(Action.EDIT_RECORD, record_id=record_id, atomic=True)
            db.session.rollback()
            status = 400
        record = scoped_record(record_id, Action.EDIT_RECORD) if current_user.is_authenticated else None
        if record is None:
            require_permission(Action.EDIT_RECORD, record_id=record_id)
            abort(403)
    return render_workspace("workspace_form.html", title="Edit academic record", subject=record.student.display_name,
                            form=form, fields=(form.course, form.marks), error=error, status=status,
                            cancel=url_for("records.detail", record_id=record_id), active="records")


@records.route("/records/<int:record_id>/delete", methods=["GET", "POST"])
def delete(record_id):
    form = DeleteRecordForm()
    error, status = None, 200
    if form.validate_on_submit():
        def change():
            require_permission(Action.DELETE_RECORD, record_id=record_id, atomic=True)
            db.session.delete(scoped_record(record_id, Action.DELETE_RECORD))

        error, status = save_changes(change)
        if error is None:
            flash("Academic record deleted.", "success")
            return redirect(url_for("records.index"), code=303)
    else:
        require_permission(Action.DELETE_RECORD, record_id=record_id)
    record = scoped_record(record_id, Action.DELETE_RECORD) if current_user.is_authenticated else None
    if record is None:
        require_permission(Action.DELETE_RECORD, record_id=record_id)
        abort(403)
    return render_workspace("records/delete.html", record=record, form=form, error=error,
                            status=status, active="records")
