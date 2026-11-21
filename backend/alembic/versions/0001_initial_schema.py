"""Initial MeetFlow PostgreSQL + pgvector schema.

Revision ID: 0001_initial_schema
Revises:
"""

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("""CREATE TABLE IF NOT EXISTS users (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), email VARCHAR(255) UNIQUE NOT NULL,
      full_name VARCHAR(200) NOT NULL, password_hash TEXT NOT NULL, timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
      is_active SMALLINT NOT NULL DEFAULT 1, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS organizations (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), name VARCHAR(200) NOT NULL, slug VARCHAR(220) UNIQUE NOT NULL,
      settings_json TEXT NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS organization_memberships (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
      user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, role VARCHAR(20) NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), UNIQUE(organization_id,user_id))""")
    op.execute("""CREATE TABLE IF NOT EXISTS meetings (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
      created_by UUID NOT NULL REFERENCES users(id), title VARCHAR(300) NOT NULL, summary TEXT,
      meeting_date DATE NOT NULL, source_type VARCHAR(40) NOT NULL DEFAULT 'transcript_text', audio_file_path TEXT,
      status VARCHAR(20) NOT NULL DEFAULT 'UPLOADED', topics_json TEXT NOT NULL DEFAULT '[]', pipeline_log_json TEXT NOT NULL DEFAULT '[]',
      is_deleted SMALLINT NOT NULL DEFAULT 0, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS meeting_participants (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
      user_id UUID REFERENCES users(id) ON DELETE SET NULL, display_name TEXT NOT NULL, role_in_meeting TEXT DEFAULT 'participant',
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS transcripts (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), meeting_id UUID UNIQUE NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
      organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, raw_text TEXT NOT NULL,
      provider VARCHAR(80) NOT NULL DEFAULT 'whisper_compatible', language VARCHAR(20) NOT NULL DEFAULT 'en',
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS speakers (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
      meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE, speaker_key TEXT NOT NULL, speaker_label TEXT NOT NULL,
      mapped_user_id UUID REFERENCES users(id) ON DELETE SET NULL, is_unknown SMALLINT NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS transcript_segments (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), transcript_id UUID NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
      meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE, organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
      speaker_id UUID REFERENCES speakers(id) ON DELETE SET NULL, speaker_label TEXT NOT NULL, text TEXT NOT NULL,
      start_time DOUBLE PRECISION NOT NULL DEFAULT 0, end_time DOUBLE PRECISION NOT NULL DEFAULT 0, confidence DOUBLE PRECISION,
      segment_index INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS decisions (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
      meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE, source_segment_id UUID REFERENCES transcript_segments(id) ON DELETE SET NULL,
      subject VARCHAR(300) NOT NULL, statement TEXT NOT NULL, decision_type VARCHAR(20) NOT NULL,
      status VARCHAR(20) NOT NULL DEFAULT 'PENDING_REVIEW', key_value VARCHAR(255), evidence_quote TEXT,
      participants_json TEXT NOT NULL DEFAULT '[]', confidence DOUBLE PRECISION NOT NULL DEFAULT 0.85, needs_review SMALLINT NOT NULL DEFAULT 0,
      embedding_json TEXT NOT NULL DEFAULT '[]', embedding vector(128), current_version INTEGER NOT NULL DEFAULT 1,
      confirmed_by UUID REFERENCES users(id) ON DELETE SET NULL, confirmed_at TIMESTAMPTZ, is_deleted SMALLINT NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS decision_versions (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), decision_id UUID NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
      organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, version_number INTEGER NOT NULL, statement TEXT NOT NULL,
      key_value VARCHAR(255), status VARCHAR(20) NOT NULL, source_meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
      evidence_quote TEXT, changed_by UUID REFERENCES users(id) ON DELETE SET NULL, change_reason TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS decision_relationships (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
      source_decision_id UUID NOT NULL REFERENCES decisions(id) ON DELETE CASCADE, target_decision_id UUID NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
      relationship_type VARCHAR(20) NOT NULL, similarity_score DOUBLE PRECISION, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS decision_conflicts (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
      existing_decision_id UUID NOT NULL REFERENCES decisions(id) ON DELETE CASCADE, new_decision_id UUID NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
      existing_meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE, new_meeting_id UUID NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
      conflict_type VARCHAR(30) NOT NULL, severity VARCHAR(20) NOT NULL DEFAULT 'HIGH', explanation TEXT NOT NULL, suggested_resolution TEXT NOT NULL,
      existing_evidence TEXT, new_evidence TEXT, status VARCHAR(30) NOT NULL DEFAULT 'OPEN', resolved_by UUID REFERENCES users(id) ON DELETE SET NULL,
      resolved_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS action_items (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
      meeting_id UUID REFERENCES meetings(id) ON DELETE SET NULL, source_segment_id UUID REFERENCES transcript_segments(id) ON DELETE SET NULL,
      title TEXT NOT NULL, description TEXT, assigned_user_id UUID REFERENCES users(id) ON DELETE SET NULL, assigned_name TEXT, deadline TEXT,
      priority VARCHAR(20) NOT NULL DEFAULT 'MEDIUM', status VARCHAR(20) NOT NULL DEFAULT 'OPEN', dependencies_json TEXT NOT NULL DEFAULT '[]',
      evidence_quote TEXT, confidence DOUBLE PRECISION NOT NULL DEFAULT 0.85, review_status VARCHAR(20) NOT NULL DEFAULT 'NEEDS_REVIEW',
      external_provider TEXT, external_task_id TEXT, sync_status TEXT NOT NULL DEFAULT 'NOT_SYNCED', is_deleted SMALLINT NOT NULL DEFAULT 0,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS approvals (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
      action_type VARCHAR(40) NOT NULL, target_provider TEXT NOT NULL, proposed_content_json TEXT NOT NULL, payload_hash TEXT NOT NULL,
      idempotency_key TEXT NOT NULL, source_meeting_id UUID REFERENCES meetings(id) ON DELETE SET NULL, source_entity_id TEXT,
      supporting_evidence TEXT, requested_by UUID NOT NULL REFERENCES users(id), status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
      reviewer_id UUID REFERENCES users(id) ON DELETE SET NULL, reviewed_at TIMESTAMPTZ, review_comment TEXT, recurring_policy_id TEXT,
      execution_error TEXT, executed_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS integration_connections (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
      provider VARCHAR(30) NOT NULL, workspace_name TEXT, project_id TEXT, config_json TEXT NOT NULL DEFAULT '{}',
      status VARCHAR(20) NOT NULL DEFAULT 'CONNECTED', connected_by UUID NOT NULL REFERENCES users(id),
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      UNIQUE(organization_id,provider))""")
    op.execute("""CREATE TABLE IF NOT EXISTS external_execution_records (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
      approval_id UUID NOT NULL REFERENCES approvals(id) ON DELETE CASCADE, provider TEXT NOT NULL, idempotency_key TEXT UNIQUE NOT NULL,
      external_reference_id TEXT, request_payload_json TEXT NOT NULL, response_payload_json TEXT, status VARCHAR(20) NOT NULL,
      attempt_count INTEGER NOT NULL DEFAULT 1, executed_by UUID REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS notifications (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
      user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, notification_type TEXT NOT NULL, title TEXT NOT NULL, message TEXT NOT NULL,
      is_read SMALLINT NOT NULL DEFAULT 0, related_entity_id TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS reminders (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
      action_item_id UUID NOT NULL REFERENCES action_items(id) ON DELETE CASCADE, user_id UUID REFERENCES users(id) ON DELETE SET NULL,
      scheduled_for TIMESTAMPTZ NOT NULL, reminder_type VARCHAR(20) NOT NULL DEFAULT 'UPCOMING', timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
      status VARCHAR(20) NOT NULL DEFAULT 'PENDING_APPROVAL', approval_id UUID REFERENCES approvals(id) ON DELETE SET NULL,
      dedup_key TEXT UNIQUE NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS weekly_digests (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
      user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, period_start DATE NOT NULL, period_end DATE NOT NULL,
      delivery_day VARCHAR(20) NOT NULL DEFAULT 'Monday', delivery_time VARCHAR(10) NOT NULL DEFAULT '09:00', timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
      digest_format VARCHAR(20) NOT NULL DEFAULT 'markdown', content_json TEXT NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'PENDING_APPROVAL',
      approval_id UUID REFERENCES approvals(id) ON DELETE SET NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("""CREATE TABLE IF NOT EXISTS audit_logs (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(), organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
      actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL, event_type TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
      details_json TEXT NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    op.execute("CREATE INDEX IF NOT EXISTS idx_meetings_org ON meetings(organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_decisions_org ON decisions(organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_conflicts_org ON decision_conflicts(organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_org ON action_items(organization_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_approvals_org_status ON approvals(organization_id,status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_decisions_embedding ON decisions USING ivfflat (embedding vector_cosine_ops)")


def downgrade() -> None:
    from alembic import op
    op.execute("DROP TABLE IF EXISTS audit_logs CASCADE")
    op.execute("DROP TABLE IF EXISTS weekly_digests CASCADE")
