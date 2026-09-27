"""Baseline: the schema previously created by ``init_db()`` / ``create_all``.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-26

Databases created by the old startup ``create_all`` already contain exactly these
tables. For them this revision is a no-op (detected via the ``users`` table), so
``alembic upgrade head`` works on both fresh and pre-existing databases without
touching existing data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0001_baseline'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "users" in sa.inspect(op.get_bind()).get_table_names():
        # Legacy database created by create_all(): schema already matches.
        return
    op.create_table('rubrics',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('source_filename', sa.String(length=512), nullable=False),
    sa.Column('source_type', sa.String(length=16), nullable=False),
    sa.Column('file_path', sa.String(length=1024), nullable=True),
    sa.Column('structured_data', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('hashed_password', sa.String(length=255), nullable=False),
    sa.Column('full_name', sa.String(length=255), nullable=False),
    sa.Column('role', sa.Enum('INSTRUCTOR', 'TA', name='userrole'), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('batch_jobs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('rubric_id', sa.UUID(), nullable=False),
    sa.Column('status', sa.Enum('QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', name='batchjobstatus'), nullable=False),
    sa.Column('total_count', sa.Integer(), nullable=False),
    sa.Column('completed_count', sa.Integer(), nullable=False),
    sa.Column('failed_count', sa.Integer(), nullable=False),
    sa.Column('submission_ids', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('errors', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('run_plagiarism', sa.Boolean(), nullable=False),
    sa.Column('created_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['rubric_id'], ['rubrics.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_batch_jobs_rubric_id'), 'batch_jobs', ['rubric_id'], unique=False)
    op.create_index(op.f('ix_batch_jobs_status'), 'batch_jobs', ['status'], unique=False)
    op.create_table('plagiarism_reports',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('rubric_id', sa.UUID(), nullable=False),
    sa.Column('batch_job_id', sa.UUID(), nullable=True),
    sa.Column('flags', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('matrix', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['batch_job_id'], ['batch_jobs.id'], ),
    sa.ForeignKeyConstraint(['rubric_id'], ['rubrics.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_plagiarism_reports_rubric_id'), 'plagiarism_reports', ['rubric_id'], unique=False)
    op.create_table('student_submissions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('student_id', sa.String(length=128), nullable=False),
    sa.Column('rubric_id', sa.UUID(), nullable=True),
    sa.Column('batch_job_id', sa.UUID(), nullable=True),
    sa.Column('source_filename', sa.String(length=512), nullable=False),
    sa.Column('file_path', sa.String(length=1024), nullable=False),
    sa.Column('status', sa.Enum('UPLOADED', 'PROCESSING', 'OCR_COMPLETE', 'EVALUATED', 'FAILED', name='submissionstatus'), nullable=False),
    sa.Column('review_status', sa.Enum('PENDING', 'REVIEWED', 'APPROVED', 'OVERRIDDEN', 'REJECTED', name='reviewstatus'), nullable=False),
    sa.Column('reviewer_notes', sa.Text(), nullable=True),
    sa.Column('reviewed_by', sa.UUID(), nullable=True),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('page_count', sa.Integer(), nullable=True),
    sa.Column('extracted_text', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('evaluation_result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('annotated_pdf_path', sa.String(length=1024), nullable=True),
    sa.Column('total_marks', sa.Float(), nullable=True),
    sa.Column('plagiarism_score', sa.Float(), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['batch_job_id'], ['batch_jobs.id'], ),
    sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['rubric_id'], ['rubrics.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_student_submissions_batch_job_id'), 'student_submissions', ['batch_job_id'], unique=False)
    op.create_index(op.f('ix_student_submissions_review_status'), 'student_submissions', ['review_status'], unique=False)
    op.create_index(op.f('ix_student_submissions_rubric_id'), 'student_submissions', ['rubric_id'], unique=False)
    op.create_index(op.f('ix_student_submissions_status'), 'student_submissions', ['status'], unique=False)
    op.create_index(op.f('ix_student_submissions_student_id'), 'student_submissions', ['student_id'], unique=False)
    op.create_table('evaluation_logs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('submission_id', sa.UUID(), nullable=False),
    sa.Column('stage', sa.String(length=64), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['submission_id'], ['student_submissions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_evaluation_logs_submission_id'), 'evaluation_logs', ['submission_id'], unique=False)
    op.create_table('extracted_answers',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('submission_id', sa.UUID(), nullable=False),
    sa.Column('question_number', sa.String(length=32), nullable=False),
    sa.Column('page_index', sa.Integer(), nullable=False),
    sa.Column('bbox', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('extracted_text', sa.Text(), nullable=False),
    sa.Column('is_blank', sa.Boolean(), nullable=False),
    sa.Column('ocr_confidence', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['submission_id'], ['student_submissions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_extracted_answers_submission_id'), 'extracted_answers', ['submission_id'], unique=False)
    op.create_table('review_audits',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('submission_id', sa.UUID(), nullable=False),
    sa.Column('reviewer_id', sa.UUID(), nullable=True),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('question', sa.String(length=32), nullable=True),
    sa.Column('old_marks', sa.Float(), nullable=True),
    sa.Column('new_marks', sa.Float(), nullable=True),
    sa.Column('old_remarks', sa.Text(), nullable=True),
    sa.Column('new_remarks', sa.Text(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['submission_id'], ['student_submissions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_review_audits_submission_id'), 'review_audits', ['submission_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_review_audits_submission_id'), table_name='review_audits')
    op.drop_table('review_audits')
    op.drop_index(op.f('ix_extracted_answers_submission_id'), table_name='extracted_answers')
    op.drop_table('extracted_answers')
    op.drop_index(op.f('ix_evaluation_logs_submission_id'), table_name='evaluation_logs')
    op.drop_table('evaluation_logs')
    op.drop_index(op.f('ix_student_submissions_student_id'), table_name='student_submissions')
    op.drop_index(op.f('ix_student_submissions_status'), table_name='student_submissions')
    op.drop_index(op.f('ix_student_submissions_rubric_id'), table_name='student_submissions')
    op.drop_index(op.f('ix_student_submissions_review_status'), table_name='student_submissions')
    op.drop_index(op.f('ix_student_submissions_batch_job_id'), table_name='student_submissions')
    op.drop_table('student_submissions')
    op.drop_index(op.f('ix_plagiarism_reports_rubric_id'), table_name='plagiarism_reports')
    op.drop_table('plagiarism_reports')
    op.drop_index(op.f('ix_batch_jobs_status'), table_name='batch_jobs')
    op.drop_index(op.f('ix_batch_jobs_rubric_id'), table_name='batch_jobs')
    op.drop_table('batch_jobs')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_table('users')
    op.drop_table('rubrics')
    for enum_name in ('reviewstatus', 'submissionstatus', 'batchjobstatus', 'userrole'):
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
