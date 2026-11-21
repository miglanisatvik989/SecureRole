"""SQLite triggers installed by schema migration 1."""

# A fixed role catalog prevents renaming or replacing a role that is in use.
RULES = {
    "roles_no_update": ("BEFORE UPDATE ON roles", "1", "Role definitions are fixed."),
    "roles_no_delete": ("BEFORE DELETE ON roles", "1", "Role definitions are fixed."),
    "roles_no_replace": (
        "BEFORE INSERT ON roles",
        "EXISTS (SELECT 1 FROM roles WHERE id=NEW.id OR name=NEW.name)",
        "Role definitions cannot be replaced.",
    ),
    "users_no_replace": (
        "BEFORE INSERT ON users",
        "EXISTS (SELECT 1 FROM users WHERE id=NEW.id OR username=NEW.username OR email=NEW.email)",
        "An existing account cannot be replaced.",
    ),
    "users_no_collision": (
        "BEFORE UPDATE ON users",
        """NEW.id != OLD.id OR EXISTS (
            SELECT 1 FROM users WHERE id!=OLD.id AND (username=NEW.username OR email=NEW.email)
        )""",
        "Account identity cannot change or replace another account.",
    ),
    "users_keep_admin_on_delete": (
        "BEFORE DELETE ON users",
        """OLD.role_id=(SELECT id FROM roles WHERE name='Admin') AND NOT EXISTS (
            SELECT 1 FROM users WHERE role_id=OLD.role_id AND id!=OLD.id
        )""",
        "At least one account must retain the Admin role.",
    ),
    "users_preserve_relationships": (
        "BEFORE UPDATE OF role_id ON users",
        """OLD.role_id!=NEW.role_id AND (
            (OLD.role_id=(SELECT id FROM roles WHERE name='Admin') AND NOT EXISTS (
                SELECT 1 FROM users WHERE role_id=OLD.role_id AND id!=OLD.id
            )) OR
            ((SELECT name FROM roles WHERE id=NEW.role_id) IS NOT 'Student' AND EXISTS (
                SELECT 1 FROM student_records WHERE student_user_id=OLD.id
            )) OR
            ((SELECT name FROM roles WHERE id=NEW.role_id) IS NOT 'Teacher' AND EXISTS (
                SELECT 1 FROM users WHERE assigned_teacher_id=OLD.id
            ))
        )""",
        "The role change would invalidate an administrator, record, or teacher assignment.",
    ),
    "audit_no_update": ("BEFORE UPDATE ON access_logs", "1", "Audit entries are append-only."),
    "audit_no_delete": ("BEFORE DELETE ON access_logs", "1", "Audit entries are append-only."),
    "audit_head_no_insert": ("BEFORE INSERT ON audit_chain_state", "1", "The audit head already exists."),
    "audit_head_no_delete": ("BEFORE DELETE ON audit_chain_state", "1", "The audit head is protected."),
    "audit_head_consistency": (
        "BEFORE UPDATE ON audit_chain_state",
        """NEW.id IS NOT OLD.id OR NEW.key_tag IS NOT OLD.key_tag
        OR NEW.head_id IS NOT (SELECT id FROM access_logs ORDER BY id DESC LIMIT 1)
        OR NEW.head_mac IS NOT (SELECT entry_mac FROM access_logs ORDER BY id DESC LIMIT 1)""",
        "The audit head must match the latest entry.",
    ),
    "audit_link": (
        "BEFORE INSERT ON access_logs",
        """NOT EXISTS (
            SELECT 1 FROM audit_chain_state
            WHERE id=1 AND NEW.id=head_id+1 AND NEW.previous_mac=head_mac
        ) OR EXISTS (SELECT 1 FROM access_logs WHERE id=NEW.id)
        OR NEW.entry_mac IS NULL OR length(NEW.entry_mac)!=64
        OR NEW.entry_mac GLOB '*[^0-9a-f]*'
        OR (NEW.actor_user_id IS NULL AND NEW.actor_role IS NOT NULL)
        OR (NEW.actor_user_id IS NOT NULL AND (NEW.actor_role IS NULL
             OR NEW.actor_role NOT IN ('Admin', 'Teacher', 'Student')))""",
        "Audit entries must append to the current integrity chain.",
    ),
}

ASSIGNMENT_INVALID = """NEW.assigned_teacher_id IS NOT NULL AND (
    NEW.assigned_teacher_id=NEW.id
    OR (SELECT name FROM roles WHERE id=NEW.role_id) IS NOT 'Student'
    OR (SELECT r.name FROM users u JOIN roles r ON r.id=u.role_id
        WHERE u.id=NEW.assigned_teacher_id) IS NOT 'Teacher'
)"""

OWNER_INVALID = """(SELECT r.name FROM users u JOIN roles r ON r.id=u.role_id
                    WHERE u.id=NEW.student_user_id) IS NOT 'Student'"""


def install_rules(connection):
    for name, (when, predicate, message) in RULES.items():
        rejecting_trigger(connection, name, when, predicate, message)
    for kind, suffix in (("INSERT", ""), ("UPDATE", " OF assigned_teacher_id, role_id")):
        rejecting_trigger(connection, f"assignment_{kind.lower()}", f"BEFORE {kind}{suffix} ON users",
                          ASSIGNMENT_INVALID, "Only Students can be assigned to Teachers.")
    for kind, suffix in (("INSERT", ""), ("UPDATE", " OF student_user_id")):
        rejecting_trigger(connection, f"owner_{kind.lower()}", f"BEFORE {kind}{suffix} ON student_records",
                          OWNER_INVALID, "Only Students can own records.")

    connection.exec_driver_sql("""
        CREATE TRIGGER audit_advance AFTER INSERT ON access_logs BEGIN
            UPDATE audit_chain_state SET head_id=NEW.id, head_mac=NEW.entry_mac WHERE id=1;
        END
    """)
    connection.exec_driver_sql("""
        CREATE TRIGGER revoke_on_password_change AFTER UPDATE OF password_hash ON users
        WHEN OLD.password_hash IS NOT NEW.password_hash BEGIN
            UPDATE auth_sessions SET revoked_at=unixepoch()
            WHERE user_id=OLD.id AND revoked_at IS NULL;
        END
    """)


def rejecting_trigger(connection, name, when, predicate, message):
    # Identifiers, predicates and messages are constants defined by this migration.
    connection.exec_driver_sql(f"""
        CREATE TRIGGER {name} {when} WHEN {predicate} BEGIN
            SELECT RAISE(ABORT, '{message}');
        END
    """)
