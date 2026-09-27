"""Academic hierarchy: courses, TAs, students, exams, review lifecycle.

Revision ID: 0002_academic_hierarchy
Revises: 0001_baseline
Create Date: 2026-09-26

Non-destructive. Existing rows are preserved:

* ``userrole``: value ``INSTRUCTOR`` is renamed to ``PROFESSOR``.
* ``reviewstatus`` is rebuilt with the new lifecycle and legacy values mapped:
  PENDING → AI_EVALUATED (if evaluated) / NOT_EVALUATED, REVIEWED → TA_PENDING
  (legacy catch-all action; must be re-confirmed), APPROVED → TA_APPROVED,
  OVERRIDDEN → TA_OVERRIDDEN, REJECTED → ESCALATED.
* Legacy submissions/rubrics keep NULL course/exam/owner columns. They stay
  reachable through the legacy workbench (AUTH_ENABLED=false) and can be attached
  to a professor's course with ``python -m scripts.claim_legacy_data``.
* ai_total_marks / ta_total_marks / min_confidence are backfilled from stored
  evaluation results and review audits.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_academic_hierarchy"
down_revision: Union[str, None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_REVIEW_STATUSES = (
    "NOT_EVALUATED",
    "AI_EVALUATED",
    "TA_PENDING",
    "TA_APPROVED",
    "TA_OVERRIDDEN",
    "ESCALATED",
    "PROFESSOR_APPROVED",
    "PUBLISHED",
)
OLD_REVIEW_STATUSES = ("PENDING", "REVIEWED", "APPROVED", "OVERRIDDEN", "REJECTED")

# (table, name, local cols, referent table, remote cols, ondelete)
NEW_FOREIGN_KEYS = [
    ("batch_jobs", "fk_batch_jobs_exam_id", ["exam_id"], "exams", ["id"], None),
    ("plagiarism_reports", "fk_plagiarism_reports_exam_id", ["exam_id"], "exams", ["id"], None),
    ("rubrics", "fk_rubrics_owner_id", ["owner_id"], "users", ["id"], None),
    ("student_submissions", "fk_submissions_course_id", ["course_id"], "courses", ["id"], None),
    ("student_submissions", "fk_submissions_exam_id", ["exam_id"], "exams", ["id"], None),
    ("student_submissions", "fk_submissions_student_record_id", ["student_record_id"], "students", ["id"], None),
    ("student_submissions", "fk_submissions_uploaded_by", ["uploaded_by"], "users", ["id"], None),
    ("student_submissions", "fk_submissions_assigned_ta_id", ["assigned_ta_id"], "users", ["id"], None),
    ("student_submissions", "fk_submissions_approved_by", ["approved_by"], "users", ["id"], None),
    ("student_submissions", "fk_submissions_escalated_by", ["escalated_by"], "users", ["id"], None),
]


def _rebuild_review_status(values: tuple[str, ...], mapping_sql: str) -> None:
    """Swap the reviewstatus enum for a new value set, remapping rows in between."""
    op.drop_index("ix_student_submissions_review_status", table_name="student_submissions")
    op.execute(
        "ALTER TABLE student_submissions ALTER COLUMN review_status TYPE VARCHAR(32) "
        "USING review_status::text"
    )
    op.execute(mapping_sql)
    op.execute("DROP TYPE reviewstatus")
    postgresql.ENUM(*values, name="reviewstatus").create(op.get_bind())
    op.execute(
        "ALTER TABLE student_submissions ALTER COLUMN review_status TYPE reviewstatus "
        "USING review_status::reviewstatus"
    )
    op.create_index(
        "ix_student_submissions_review_status", "student_submissions", ["review_status"]
    )


def upgrade() -> None:
    # --- Roles: INSTRUCTOR → PROFESSOR -------------------------------------------
    op.execute("ALTER TYPE userrole RENAME VALUE 'INSTRUCTOR' TO 'PROFESSOR'")
    userrole = postgresql.ENUM("PROFESSOR", "TA", name="userrole", create_type=False)

    # --- New tables --------------------------------------------------------------
    op.create_table(
        "students",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_students_student_id"), "students", ["student_id"], unique=True)

    op.create_table(
        "courses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("course_code", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("semester", sa.String(length=64), nullable=True),
        sa.Column("academic_year", sa.String(length=16), nullable=True),
        sa.Column("professor_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Enum("ACTIVE", "ARCHIVED", name="coursestatus"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["professor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "professor_id", "course_code", "semester", "academic_year", name="uq_course_offering"
        ),
    )
    op.create_index(op.f("ix_courses_course_code"), "courses", ["course_code"])
    op.create_index(op.f("ix_courses_professor_id"), "courses", ["professor_id"])
    op.create_index(op.f("ix_courses_status"), "courses", ["status"])

    op.create_table(
        "course_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("course_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", userrole, nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "user_id", name="uq_course_member"),
    )
    op.create_index(op.f("ix_course_members_course_id"), "course_members", ["course_id"])
    op.create_index(op.f("ix_course_members_user_id"), "course_members", ["user_id"])

    op.create_table(
        "enrollments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("course_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Enum("ACTIVE", "DROPPED", name="enrollmentstatus"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "student_id", name="uq_enrollment"),
    )
    op.create_index(op.f("ix_enrollments_course_id"), "enrollments", ["course_id"])
    op.create_index(op.f("ix_enrollments_student_id"), "enrollments", ["student_id"])

    op.create_table(
        "exams",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("course_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("exam_type", sa.String(length=32), nullable=False),
        sa.Column("total_marks", sa.Float(), nullable=True),
        sa.Column("exam_date", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("DRAFT", "PROCESSING", "TA_REVIEW", "APPROVED", "LOCKED", "PUBLISHED", name="examstatus"),
            nullable=False,
        ),
        sa.Column("rubric_id", sa.UUID(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["rubric_id"], ["rubrics.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_exams_course_id"), "exams", ["course_id"])
    op.create_index(op.f("ix_exams_rubric_id"), "exams", ["rubric_id"])
    op.create_index(op.f("ix_exams_status"), "exams", ["status"])

    op.create_table(
        "exam_audits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("exam_id", sa.UUID(), nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["exam_id"], ["exams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_exam_audits_exam_id"), "exam_audits", ["exam_id"])

    op.create_table(
        "exam_tas",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("exam_id", sa.UUID(), nullable=False),
        sa.Column("ta_id", sa.UUID(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["exams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ta_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exam_id", "ta_id", name="uq_exam_ta"),
    )
    op.create_index(op.f("ix_exam_tas_exam_id"), "exam_tas", ["exam_id"])
    op.create_index(op.f("ix_exam_tas_ta_id"), "exam_tas", ["ta_id"])

    op.create_table(
        "integrity_flags",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("exam_id", sa.UUID(), nullable=False),
        sa.Column("question", sa.String(length=32), nullable=False),
        sa.Column("submission_a_id", sa.UUID(), nullable=False),
        sa.Column("submission_b_id", sa.UUID(), nullable=False),
        sa.Column("student_a", sa.String(length=128), nullable=False),
        sa.Column("student_b", sa.String(length=128), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status", sa.Enum("OPEN", "DISMISSED", "CONFIRMED", name="integrityflagstatus"), nullable=False
        ),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["exams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["submission_a_id"], ["student_submissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submission_b_id"], ["student_submissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "exam_id", "question", "submission_a_id", "submission_b_id", name="uq_integrity_pair"
        ),
    )
    op.create_index(op.f("ix_integrity_flags_exam_id"), "integrity_flags", ["exam_id"])
    op.create_index(op.f("ix_integrity_flags_status"), "integrity_flags", ["status"])

    # --- New columns on existing tables (all nullable or defaulted) --------------
    op.add_column("batch_jobs", sa.Column("exam_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_batch_jobs_exam_id"), "batch_jobs", ["exam_id"])
    op.add_column("plagiarism_reports", sa.Column("exam_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_plagiarism_reports_exam_id"), "plagiarism_reports", ["exam_id"])

    op.add_column("review_audits", sa.Column("reason", sa.String(length=64), nullable=True))
    op.add_column("review_audits", sa.Column("actor_role", sa.String(length=16), nullable=True))
    op.add_column("review_audits", sa.Column("from_status", sa.String(length=32), nullable=True))
    op.add_column("review_audits", sa.Column("to_status", sa.String(length=32), nullable=True))
    op.create_index(op.f("ix_review_audits_reviewer_id"), "review_audits", ["reviewer_id"])

    op.add_column("rubrics", sa.Column("owner_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_rubrics_owner_id"), "rubrics", ["owner_id"])

    for name, col_type in (
        ("course_id", sa.UUID()),
        ("exam_id", sa.UUID()),
        ("student_record_id", sa.UUID()),
        ("uploaded_by", sa.UUID()),
        ("assigned_ta_id", sa.UUID()),
        ("approved_by", sa.UUID()),
        ("approved_at", sa.DateTime(timezone=True)),
        ("escalation_reason", sa.String(length=64)),
        ("escalation_notes", sa.Text()),
        ("escalated_by", sa.UUID()),
        ("escalated_at", sa.DateTime(timezone=True)),
        ("ai_total_marks", sa.Float()),
        ("ta_total_marks", sa.Float()),
        ("professor_total_marks", sa.Float()),
        ("min_confidence", sa.Float()),
    ):
        op.add_column("student_submissions", sa.Column(name, col_type, nullable=True))
    op.add_column(
        "student_submissions",
        sa.Column("needs_manual_grading", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("student_submissions", "needs_manual_grading", server_default=None)
    for col in ("assigned_ta_id", "course_id", "exam_id", "min_confidence", "student_record_id", "uploaded_by"):
        op.create_index(f"ix_student_submissions_{col}", "student_submissions", [col])

    for table, name, local, referent, remote, ondelete in NEW_FOREIGN_KEYS:
        op.create_foreign_key(name, table, referent, local, remote, ondelete=ondelete)

    # --- Review lifecycle ----------------------------------------------------------
    _rebuild_review_status(
        NEW_REVIEW_STATUSES,
        """
        UPDATE student_submissions SET review_status = CASE
            WHEN review_status = 'PENDING' AND evaluation_result IS NOT NULL THEN 'AI_EVALUATED'
            WHEN review_status = 'PENDING' THEN 'NOT_EVALUATED'
            WHEN review_status = 'REVIEWED' THEN 'TA_PENDING'
            WHEN review_status = 'APPROVED' THEN 'TA_APPROVED'
            WHEN review_status = 'OVERRIDDEN' THEN 'TA_OVERRIDDEN'
            WHEN review_status = 'REJECTED' THEN 'ESCALATED'
            ELSE 'NOT_EVALUATED'
        END
        """,
    )
    op.execute(
        "UPDATE student_submissions SET escalation_reason = 'legacy_rejected' "
        "WHERE review_status = 'ESCALATED'"
    )

    # --- Backfill per-stage totals & confidence from stored results --------------
    op.execute(
        """
        UPDATE student_submissions s SET ai_total_marks = s.total_marks - COALESCE((
            SELECT SUM(a.new_marks - a.old_marks) FROM review_audits a
            WHERE a.submission_id = s.id AND a.action = 'override'
              AND a.new_marks IS NOT NULL AND a.old_marks IS NOT NULL
        ), 0)
        WHERE s.evaluation_result IS NOT NULL AND s.total_marks IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE student_submissions SET ta_total_marks = total_marks
        WHERE review_status IN ('TA_APPROVED', 'TA_OVERRIDDEN')
        """
    )
    op.execute(
        """
        UPDATE student_submissions s SET min_confidence = (
            SELECT MIN((r->>'confidence')::float)
            FROM jsonb_array_elements(s.evaluation_result->'results') r
            WHERE r ? 'confidence'
        )
        WHERE s.evaluation_result IS NOT NULL
          AND jsonb_typeof(s.evaluation_result->'results') = 'array'
        """
    )


def downgrade() -> None:
    # Lossy by nature: the richer lifecycle collapses onto the legacy values.
    _rebuild_review_status(
        OLD_REVIEW_STATUSES,
        """
        UPDATE student_submissions SET review_status = CASE
            WHEN review_status IN ('NOT_EVALUATED', 'AI_EVALUATED', 'TA_PENDING') THEN 'PENDING'
            WHEN review_status IN ('TA_APPROVED', 'PROFESSOR_APPROVED', 'PUBLISHED') THEN 'APPROVED'
            WHEN review_status = 'TA_OVERRIDDEN' THEN 'OVERRIDDEN'
            WHEN review_status = 'ESCALATED' THEN 'REJECTED'
            ELSE 'PENDING'
        END
        """,
    )

    for table, name, *_ in reversed(NEW_FOREIGN_KEYS):
        op.drop_constraint(name, table, type_="foreignkey")
    for col in ("assigned_ta_id", "course_id", "exam_id", "min_confidence", "student_record_id", "uploaded_by"):
        op.drop_index(f"ix_student_submissions_{col}", table_name="student_submissions")
    for col in (
        "needs_manual_grading", "min_confidence", "professor_total_marks", "ta_total_marks",
        "ai_total_marks", "escalated_at", "escalated_by", "escalation_notes", "escalation_reason",
        "approved_at", "approved_by", "assigned_ta_id", "uploaded_by", "student_record_id",
        "exam_id", "course_id",
    ):
        op.drop_column("student_submissions", col)

    op.drop_index(op.f("ix_rubrics_owner_id"), table_name="rubrics")
    op.drop_column("rubrics", "owner_id")
    op.drop_index(op.f("ix_review_audits_reviewer_id"), table_name="review_audits")
    for col in ("to_status", "from_status", "actor_role", "reason"):
        op.drop_column("review_audits", col)
    op.drop_index(op.f("ix_plagiarism_reports_exam_id"), table_name="plagiarism_reports")
    op.drop_column("plagiarism_reports", "exam_id")
    op.drop_index(op.f("ix_batch_jobs_exam_id"), table_name="batch_jobs")
    op.drop_column("batch_jobs", "exam_id")

    for table in ("integrity_flags", "exam_tas", "exam_audits", "exams", "enrollments", "course_members", "courses", "students"):
        op.drop_table(table)
    for enum_name in ("integrityflagstatus", "examstatus", "enrollmentstatus", "coursestatus"):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)

    op.execute("ALTER TYPE userrole RENAME VALUE 'PROFESSOR' TO 'INSTRUCTOR'")
