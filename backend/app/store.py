from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import hashlib
import os
from threading import Lock

from .models import (
    ApiConfig,
    AuditLogEntry,
    FeynmanDistributionBucket,
    LearningSession,
    MaterialQualitySummary,
    MemoryCategorySummary,
    OrganizationDashboardResponse,
    OrganizationKnowledgeItem,
    OrganizationLearningTask,
    OrganizationMemberReport,
    OrganizationMemberSummary,
    OrganizationPublic,
    OrganizationSessionTrace,
    OrganizationTraceExportResponse,
    OrganizationTaskAssignment,
    ParseJob,
    ResearchDashboardResponse,
    ResearchBlindReviewAnswer,
    ResearchExperimentGroupSummary,
    ResearchExperimentRecord,
    ResearchExperimentRecordInput,
    ResearchScoreAgreement,
    ResearchMetric,
    SessionSummary,
    SpeechConfig,
    TokenUsageRecord,
    UserPublic,
    WeakPointSummary,
)
from .security import (
    TOKEN_TTL_SECONDS,
    TOKEN_TTL_REMEMBER_SECONDS,
    audit_log_retention_limit,
    max_active_tokens_per_user,
    normalize_username,
    parse_job_retention_per_user,
    session_retention_per_user,
    accepted_token_storage_keys,
    token_storage_key,
    validate_api_provider,
    validate_api_config_parts,
    validate_speech_config_parts,
    validate_speech_config_kind,
)
from .secrets import decrypt_secret, encrypt_secret, secret_is_encrypted

MAX_SESSION_MESSAGES = 160
MAX_SESSION_MEMORIES = 80
MAX_AUDIT_DETAIL_CHARS = 2000
STALE_RUNNING_PARSE_JOB_SECONDS = 10 * 60


class ParseJobCreateBlocked(RuntimeError):
    def __init__(self, reason: str, job: ParseJob) -> None:
        super().__init__(reason)
        self.reason = reason
        self.job = job


class _ConnectionWrapper:
    """PostgreSQL 连接包装器，向 Store 暴露统一 execute 接口。"""

    def __init__(self, raw) -> None:
        self._raw = raw

    def _normalize_sql(self, sql: str) -> str:
        normalized = sql.replace("?", "%s")
        stripped = normalized.lstrip()
        if stripped.lower().startswith("insert or ignore into "):
            leading = normalized[: len(normalized) - len(stripped)]
            statement = leading + stripped.replace("insert or ignore into ", "insert into ", 1)
            return f"{statement} on conflict do nothing"
        return normalized

    def execute(self, sql: str, parameters=()):
        cur = self._raw.cursor()
        cur.execute(self._normalize_sql(sql), parameters)
        return cur

    def executemany(self, sql: str, parameters_seq):
        cur = self._raw.cursor()
        cur.executemany(self._normalize_sql(sql), parameters_seq)
        return cur

    def close(self) -> None:
        return


class SessionStore:
    def __init__(self, db_path_or_dsn: str) -> None:
        dsn = str(db_path_or_dsn).strip()
        self._is_postgres = dsn.startswith(("postgresql://", "postgres://", "postgresql+psycopg2://"))
        if not self._is_postgres:
            raise RuntimeError("Blank 默认存储已迁移到 PostgreSQL。请通过 BLANK_DATABASE_URL 配置 postgresql:// 连接字符串。")
        try:
            from psycopg2.extras import RealDictCursor
            from psycopg2.pool import ThreadedConnectionPool
        except ImportError as exc:
            raise RuntimeError("PostgreSQL 模式需要安装 psycopg2-binary。请执行 pip install psycopg2-binary") from exc
        minconn = bounded_int_env("BLANK_DB_POOL_MIN_CONN", 1, 1, 20)
        maxconn = bounded_int_env("BLANK_DB_POOL_MAX_CONN", 20, minconn, 100)
        self._pool = ThreadedConnectionPool(minconn=minconn, maxconn=maxconn, dsn=dsn, cursor_factory=RealDictCursor)
        self._lock = Lock()
        self._striped_locks = [Lock() for _ in range(64)]
        self.db_path = None
        self._pg_lock = Lock()
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[_ConnectionWrapper]:
        connection = self._pool.getconn()
        try:
            yield _ConnectionWrapper(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            self._pool.putconn(connection)

    def _sql(self, sql: str) -> str:
        """将 Store 内部占位符 ? 转换为 PostgreSQL 的 %s。"""
        return sql.replace("?", "%s")

    def _lock_for(self, key: str) -> Lock:
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        return self._striped_locks[int.from_bytes(digest[:2], "big") % len(self._striped_locks)]

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    create table if not exists users (
                        id text primary key,
                        username text not null unique,
                        password_hash text not null,
                        role text not null,
                        is_active integer not null,
                        created_at text not null,
                        updated_at text not null,
                        password_changed_at text,
                        default_credentials_seeded integer not null default 0
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists organizations (
                        id text primary key,
                        code text not null unique,
                        name text not null,
                        owner_user_id text not null,
                        created_at text not null,
                        updated_at text not null,
                        foreign key(owner_user_id) references users(id)
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists organization_memberships (
                        organization_id text not null,
                        user_id text not null,
                        role text not null,
                        joined_at text not null,
                        primary key(organization_id, user_id),
                        foreign key(organization_id) references organizations(id),
                        foreign key(user_id) references users(id)
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists auth_tokens (
                        token text primary key,
                        user_id text not null,
                        created_at text not null,
                        last_reauth_at text not null,
                        expires_at text not null,
                        foreign key(user_id) references users(id)
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists sessions (
                        id text primary key,
                        user_id text not null default '',
                        organization_id text,
                        task_id text,
                        visibility text not null default 'personal',
                        material_title text not null,
                        payload text not null,
                        created_at text not null,
                        updated_at text not null,
                        foreign key(user_id) references users(id)
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists organization_learning_tasks (
                        id text primary key,
                        organization_id text not null,
                        creator_user_id text not null,
                        title text not null,
                        description text not null default '',
                        template_session_id text not null,
                        material_title text not null,
                        created_at text not null,
                        updated_at text not null,
                        foreign key(organization_id) references organizations(id),
                        foreign key(creator_user_id) references users(id)
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists organization_task_assignments (
                        id text primary key,
                        task_id text not null,
                        organization_id text not null,
                        user_id text not null,
                        status text not null,
                        session_id text,
                        assigned_at text not null,
                        started_at text,
                        completed_at text,
                        unique(task_id, user_id),
                        foreign key(task_id) references organization_learning_tasks(id),
                        foreign key(organization_id) references organizations(id),
                        foreign key(user_id) references users(id)
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists organization_knowledge_items (
                        id text primary key,
                        organization_id text not null,
                        uploader_user_id text not null,
                        title text not null,
                        chunk_count integer not null default 0,
                        created_at text not null,
                        updated_at text not null,
                        foreign key(organization_id) references organizations(id),
                        foreign key(uploader_user_id) references users(id)
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists organization_knowledge_chunks (
                        id text primary key,
                        item_id text not null,
                        organization_id text not null,
                        chunk_index integer not null,
                        text text not null,
                        foreign key(item_id) references organization_knowledge_items(id),
                        foreign key(organization_id) references organizations(id)
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists sag_chunks (
                        id text primary key,
                        tenant_id text not null,
                        user_id text not null default '',
                        session_id text not null,
                        source_id text not null,
                        chunk_index integer not null,
                        text text not null,
                        text_hash text not null,
                        keywords text not null default '[]',
                        created_at text not null,
                        unique(tenant_id, session_id, source_id, chunk_index)
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists sag_entities (
                        id text primary key,
                        tenant_id text not null,
                        user_id text not null default '',
                        session_id text not null,
                        source_id text not null,
                        name text not null,
                        type text not null,
                        description text not null default '',
                        created_at text not null,
                        unique(tenant_id, session_id, source_id, name)
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists sag_events (
                        id text primary key,
                        tenant_id text not null,
                        user_id text not null default '',
                        session_id text not null,
                        source_id text not null,
                        chunk_index integer not null,
                        label text not null,
                        description text not null,
                        created_at text not null
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists sag_chunk_entities (
                        chunk_id text not null,
                        entity_id text not null,
                        primary key(chunk_id, entity_id),
                        foreign key(chunk_id) references sag_chunks(id) on delete cascade,
                        foreign key(entity_id) references sag_entities(id) on delete cascade
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists sag_event_entities (
                        event_id text not null,
                        entity_id text not null,
                        primary key(event_id, entity_id),
                        foreign key(event_id) references sag_events(id) on delete cascade,
                        foreign key(entity_id) references sag_entities(id) on delete cascade
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists api_configs (
                        id text primary key,
                        provider text not null,
                        base_url text not null,
                        api_key text not null,
                        model text not null,
                        is_active integer not null,
                        created_at text not null,
                        updated_at text not null
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists speech_configs (
                        id text primary key,
                        kind text not null,
                        provider text not null,
                        base_url text not null,
                        api_key text not null,
                        model text not null,
                        path text not null,
                        is_active integer not null,
                        voice text not null default '',
                        language text not null default '',
                        response_format text not null default '',
                        created_at text not null,
                        updated_at text not null
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists parse_jobs (
                        id text primary key,
                        user_id text not null,
                        title text not null,
                        content text not null,
                        status text not null,
                        progress integer not null,
                        message text not null,
                        session_id text,
                        error text,
                        created_at text not null,
                        updated_at text not null,
                        foreign key(user_id) references users(id)
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists audit_logs (
                        id text primary key,
                        actor_user_id text,
                        actor_username text,
                        action text not null,
                        target_type text not null,
                        target_id text,
                        detail text not null,
                        created_at text not null
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists llm_token_usage (
                        id text primary key,
                        user_id text not null default '',
                        session_id text,
                        source text not null,
                        provider text not null default '',
                        model text not null default '',
                        prompt_tokens integer not null default 0,
                        completion_tokens integer not null default 0,
                        total_tokens integer not null default 0,
                        created_at text not null
                    )
                    """
                )
            )
            connection.execute(
                self._sql(
                    """
                    create table if not exists research_experiment_records (
                        id text primary key,
                        study_id text not null,
                        participant_code text not null,
                        group_label text not null,
                        material_label text not null default '',
                        pretest_score double precision,
                        posttest_score double precision,
                        delayed_score double precision,
                        system_feynman_score double precision,
                        human_score double precision,
                        learning_minutes double precision,
                        cognitive_load double precision,
                        notes text not null default '',
                        imported_at text not null,
                        updated_at text not null,
                        unique(study_id, participant_code, group_label, material_label)
                    )
                    """
                )
            )
            self._ensure_column(connection, "sessions", "user_id", "text not null default ''")
            self._ensure_column(connection, "sessions", "organization_id", "text")
            self._ensure_column(connection, "sessions", "task_id", "text")
            self._ensure_column(connection, "sessions", "visibility", "text not null default 'personal'")
            self._ensure_column(connection, "users", "updated_at", "text not null default ''")
            self._ensure_column(connection, "users", "password_changed_at", "text")
            self._ensure_column(connection, "users", "default_credentials_seeded", "integer not null default 0")
            self._ensure_column(connection, "auth_tokens", "last_reauth_at", "text not null default ''")
            self._ensure_column(connection, "auth_tokens", "expires_at", "text not null default ''")
            connection.execute(
                self._sql("update auth_tokens set last_reauth_at = created_at where last_reauth_at = ''")
            )
            connection.execute(
                self._sql("update auth_tokens set expires_at = created_at where expires_at = ''")
            )
            connection.execute(
                self._sql("create index if not exists idx_sessions_updated_at on sessions(updated_at)")
            )
            connection.execute(
                self._sql("create index if not exists idx_sessions_user_id on sessions(user_id)")
            )
            connection.execute(
                self._sql("create index if not exists idx_sessions_organization_id on sessions(organization_id, updated_at)")
            )
            connection.execute(
                self._sql("create index if not exists idx_sessions_task_id on sessions(task_id)")
            )
            connection.execute(
                self._sql("create index if not exists idx_tokens_user_id on auth_tokens(user_id)")
            )
            connection.execute(
                self._sql("create index if not exists idx_memberships_user_id on organization_memberships(user_id)")
            )
            connection.execute(
                self._sql("create index if not exists idx_memberships_org_role on organization_memberships(organization_id, role)")
            )
            connection.execute(
                self._sql("create index if not exists idx_org_tasks_org on organization_learning_tasks(organization_id, updated_at)")
            )
            connection.execute(
                self._sql("create index if not exists idx_org_assignments_user on organization_task_assignments(user_id, assigned_at)")
            )
            connection.execute(
                self._sql("create index if not exists idx_org_knowledge_org on organization_knowledge_items(organization_id, updated_at)")
            )
            connection.execute(self._sql("create index if not exists idx_sag_chunks_scope on sag_chunks(tenant_id, session_id, source_id, chunk_index)"))
            connection.execute(self._sql("create index if not exists idx_sag_entities_scope on sag_entities(tenant_id, session_id, source_id, name)"))
            connection.execute(self._sql("create index if not exists idx_sag_events_scope on sag_events(tenant_id, session_id, source_id, chunk_index)"))
            connection.execute(
                self._sql("create index if not exists idx_parse_jobs_user_id on parse_jobs(user_id, updated_at)")
            )
            connection.execute(
                self._sql("create index if not exists idx_audit_logs_created_at on audit_logs(created_at)")
            )
            connection.execute(
                self._sql("create index if not exists idx_audit_logs_actor_user_id on audit_logs(actor_user_id, created_at)")
            )
            connection.execute(
                self._sql("create index if not exists idx_llm_token_usage_user_created on llm_token_usage(user_id, created_at)")
            )
            connection.execute(
                self._sql("create index if not exists idx_llm_token_usage_created_at on llm_token_usage(created_at)")
            )
            connection.execute(
                self._sql("create index if not exists idx_speech_configs_kind_active on speech_configs(kind, is_active, updated_at)")
            )
            connection.execute(
                self._sql("create index if not exists idx_research_records_study_group on research_experiment_records(study_id, group_label)")
            )
            connection.execute(
                self._sql("create index if not exists idx_research_records_updated_at on research_experiment_records(updated_at)")
            )
            connection.execute(
                "create unique index if not exists idx_users_username_lower on users(lower(username))"
            )
            self._encrypt_plain_api_keys(connection)
            self._encrypt_plain_speech_api_keys(connection)

    def _ensure_column(
        self,
        connection,
        table_name: str,
        column_name: str,
        definition: str,
    ) -> None:
        cur = connection.execute(
            self._sql(
                "select 1 from information_schema.columns where table_name = ? and column_name = ?"
            ),
            (table_name, column_name),
        )
        if cur.fetchone():
            return
        connection.execute(f"alter table {table_name} add column {column_name} {definition}")

    def _encrypt_plain_api_keys(self, connection) -> None:
        rows = connection.execute(self._sql("select id, api_key from api_configs")).fetchall()
        for row in rows:
            api_key = row["api_key"]
            if not api_key or secret_is_encrypted(api_key):
                continue
            connection.execute(
                self._sql("update api_configs set api_key = ? where id = ?"),
                (encrypt_secret(api_key, self.db_path or ""), row["id"]),
            )

    def _encrypt_plain_speech_api_keys(self, connection) -> None:
        rows = connection.execute(self._sql("select id, api_key from speech_configs")).fetchall()
        for row in rows:
            api_key = row["api_key"]
            if not api_key or secret_is_encrypted(api_key):
                continue
            connection.execute(
                self._sql("update speech_configs set api_key = ? where id = ?"),
                (encrypt_secret(api_key, self.db_path or ""), row["id"]),
            )

    def save(self, session: LearningSession) -> LearningSession:
        return self.save_session(session)

    def save_session(self, session: LearningSession) -> LearningSession:
        compact_session_for_storage(session)
        payload = session.model_dump_json()
        with self._lock_for(session.user_id or session.id), self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    insert into sessions
                        (id, user_id, organization_id, task_id, visibility, material_title, payload, created_at, updated_at)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    on conflict(id) do update set
                        user_id = excluded.user_id,
                        organization_id = excluded.organization_id,
                        task_id = excluded.task_id,
                        visibility = excluded.visibility,
                        material_title = excluded.material_title,
                        payload = excluded.payload,
                        updated_at = excluded.updated_at
                    """
                ),
                (
                    session.id,
                    session.user_id,
                    session.organization_id,
                    session.task_id,
                    session.visibility,
                    session.material_title,
                    payload,
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                ),
            )
            self._prune_sessions_for_user(connection, session.user_id, session.id)
        return session

    def get(self, session_id: str) -> LearningSession | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql("select payload, user_id, organization_id, task_id, visibility from sessions where id = ?"),
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def get_session(self, session_id: str, user_id: str | None = None) -> LearningSession | None:
        with self._connect() as connection:
            if user_id is None:
                row = connection.execute(
                    self._sql("select payload, user_id, organization_id, task_id, visibility from sessions where id = ?"),
                    (session_id,),
                ).fetchone()
            else:
                row = connection.execute(
                    self._sql("select payload, user_id, organization_id, task_id, visibility from sessions where id = ? and user_id = ?"),
                    (session_id, user_id),
                ).fetchone()
        if row is None:
            return None
        return self._row_to_session(row)

    def delete_session(self, session_id: str, user_id: str | None = None) -> bool:
        with self._lock, self._connect() as connection:
            if user_id is None:
                cursor = connection.execute(self._sql("delete from sessions where id = ?"), (session_id,))
            else:
                cursor = connection.execute(
                    self._sql("delete from sessions where id = ? and user_id = ?"),
                    (session_id, user_id),
                )
        return cursor.rowcount > 0

    def list(self, user_id: str | None = None) -> list[SessionSummary]:
        with self._connect() as connection:
            if user_id is None:
                rows = connection.execute(
                    self._sql("select payload, user_id, organization_id, task_id, visibility from sessions order by updated_at desc limit 60")
                ).fetchall()
            else:
                rows = connection.execute(
                    self._sql("select payload, user_id, organization_id, task_id, visibility from sessions where user_id = ? order by updated_at desc limit 60"),
                    (user_id,),
                ).fetchall()

        summaries: list[SessionSummary] = []
        for row in rows:
            session = self._row_to_session(row)
            summaries.append(
                SessionSummary(
                    id=session.id,
                    material_title=session.material_title,
                    active_node_id=session.active_node_id,
                    mastered_count=sum(1 for node in session.nodes if node.status == "mastered"),
                    node_count=len(session.nodes),
                    updated_at=session.updated_at,
                )
            )
        return summaries

    def _row_to_session(self, row) -> LearningSession:
        payload = json.loads(row["payload"])
        payload.setdefault("user_id", row["user_id"] or "")
        row_get = row.get if hasattr(row, "get") else lambda _key, default=None: default
        payload.setdefault("organization_id", row_get("organization_id"))
        payload.setdefault("task_id", row_get("task_id"))
        payload.setdefault("visibility", row_get("visibility") or "personal")
        return LearningSession.model_validate(payload)

    def _prune_sessions_for_user(self, connection, user_id: str, keep_session_id: str) -> None:
        retention = session_retention_per_user()
        connection.execute(
            self._sql(
                """
                with keep as (
                    select id from sessions
                    where user_id = ?
                    order by updated_at desc
                    limit ?
                )
                delete from sessions
                where user_id = ?
                  and id != ?
                  and id not in (select id from keep)
                """
            ),
            (user_id, retention, user_id, keep_session_id),
        )

    def create_user(
        self,
        user_id: str,
        username: str,
        password_hash: str,
        role: str,
        is_active: bool,
        created_at: str,
        password_changed_at: str | None = None,
        default_credentials_seeded: bool = False,
    ) -> UserPublic:
        normalized_username = normalize_username(username)
        with self._lock, self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    insert into users
                        (id, username, password_hash, role, is_active, created_at, updated_at,
                         password_changed_at, default_credentials_seeded)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (
                    user_id,
                    normalized_username,
                    password_hash,
                    role,
                    int(is_active),
                    created_at,
                    created_at,
                    password_changed_at,
                    int(default_credentials_seeded),
                ),
            )
        user = self.get_user_by_id(user_id)
        if user is None:
            raise RuntimeError("用户创建失败")
        return user

    def create_default_admin_if_empty(
        self,
        user_id: str,
        username: str,
        password_hash: str,
        created_at: str,
    ) -> UserPublic | None:
        normalized_username = normalize_username(username)
        with self._lock, self._connect() as connection:
            has_users = connection.execute(self._sql("select 1 from users limit 1")).fetchone() is not None
            if has_users:
                return None
            connection.execute(
                self._sql(
                    """
                    insert into users
                        (id, username, password_hash, role, is_active, created_at, updated_at,
                         password_changed_at, default_credentials_seeded)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (user_id, normalized_username, password_hash, "admin", 1, created_at, created_at, None, 1),
            )
        return self.get_user_by_id(user_id)

    def create_user_atomic(
        self,
        user_id: str,
        username: str,
        password_hash: str,
        role_factory: Callable[[bool], str],
        is_active: bool,
        created_at: str,
    ) -> UserPublic:
        normalized_username = normalize_username(username)
        with self._lock, self._connect() as connection:
            existing_username = connection.execute(
                self._sql("select id from users where lower(username) = lower(?)"),
                (normalized_username,),
            ).fetchone()
            if existing_username is not None:
                from psycopg2 import IntegrityError
                raise IntegrityError("username already exists")
            has_users = connection.execute(self._sql("select 1 from users limit 1")).fetchone() is not None
            role = role_factory(not has_users)
            connection.execute(
                self._sql(
                    """
                    insert into users
                        (id, username, password_hash, role, is_active, created_at, updated_at,
                         password_changed_at, default_credentials_seeded)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (user_id, normalized_username, password_hash, role, int(is_active), created_at, created_at, created_at, 0),
            )
        user = self.get_user_by_id(user_id)
        if user is None:
            raise RuntimeError("用户创建失败")
        return user

    def get_user_password_hash(self, username: str) -> tuple[UserPublic, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql("select * from users where lower(username) = lower(?)"),
                (username,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_user(row), row["password_hash"]

    def get_user_by_id(self, user_id: str) -> UserPublic | None:
        with self._connect() as connection:
            row = connection.execute(self._sql("select * from users where id = ?"), (user_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_user(row)

    def list_users(self, limit: int = 200) -> list[UserPublic]:
        actual_limit = max(1, min(limit, 500))
        with self._connect() as connection:
            rows = connection.execute(
                self._sql("select * from users order by created_at desc limit ?"),
                (actual_limit,),
            ).fetchall()
            user_ids = [row["id"] for row in rows]
            usage_totals = self._token_usage_totals_for_users(connection, user_ids)
        return [
            self._row_to_user(
                row,
                total_tokens=usage_totals.get(row["id"], (0, 0))[0],
                today_tokens=usage_totals.get(row["id"], (0, 0))[1],
            )
            for row in rows
        ]

    def update_user(self, user_id: str, role: str | None, is_active: bool | None, updated_at: str) -> UserPublic | None:
        current = self.get_user_by_id(user_id)
        if current is None:
            return None
        next_role = role if role is not None else current.role
        next_active = current.is_active if is_active is None else is_active
        with self._lock, self._connect() as connection:
            connection.execute(
                self._sql("update users set role = ?, is_active = ?, updated_at = ? where id = ?"),
                (next_role, int(next_active), updated_at, user_id),
            )
        return self.get_user_by_id(user_id)

    def update_account(
        self,
        user_id: str,
        username: str | None,
        password_hash: str | None,
        password_changed_at: str | None,
        updated_at: str,
    ) -> UserPublic | None:
        current = self.get_user_by_id(user_id)
        if current is None:
            return None
        next_username = normalize_username(username) if username is not None else current.username
        with self._lock, self._connect() as connection:
            if next_username != current.username:
                existing = connection.execute(
                    self._sql("select id from users where lower(username) = lower(?) and id != ?"),
                    (next_username, user_id),
                ).fetchone()
                if existing is not None:
                    raise ValueError("该账号无法使用")
            if password_hash is None:
                connection.execute(
                    self._sql("update users set username = ?, updated_at = ? where id = ?"),
                    (next_username, updated_at, user_id),
                )
            else:
                connection.execute(
                    self._sql(
                        """
                        update users
                        set username = ?,
                            password_hash = ?,
                            password_changed_at = ?,
                            default_credentials_seeded = 0,
                            updated_at = ?
                        where id = ?
                        """
                    ),
                    (next_username, password_hash, password_changed_at, updated_at, user_id),
                )
        return self.get_user_by_id(user_id)

    def create_organization(
        self,
        organization_id: str,
        code: str,
        name: str,
        owner_user_id: str,
        created_at: str,
    ) -> OrganizationPublic:
        with self._lock, self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    insert into organizations (id, code, name, owner_user_id, created_at, updated_at)
                    values (?, ?, ?, ?, ?, ?)
                    """
                ),
                (organization_id, code, name.strip(), owner_user_id, created_at, created_at),
            )
            connection.execute(
                self._sql(
                    """
                    insert into organization_memberships (organization_id, user_id, role, joined_at)
                    values (?, ?, ?, ?)
                    on conflict(organization_id, user_id) do update set role = excluded.role
                    """
                ),
                (organization_id, owner_user_id, "org_manager", created_at),
            )
        organization = self.get_organization_by_id(organization_id)
        if organization is None:
            raise RuntimeError("组织创建失败")
        return organization

    def add_organization_member(
        self,
        organization_id: str,
        user_id: str,
        role: str,
        joined_at: str,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    insert into organization_memberships (organization_id, user_id, role, joined_at)
                    values (?, ?, ?, ?)
                    on conflict(organization_id, user_id) do update set role = excluded.role
                    """
                ),
                (organization_id, user_id, role, joined_at),
            )

    def clear_user_organization_memberships(self, user_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                self._sql("delete from organization_memberships where user_id = ?"),
                (user_id,),
            )

    def get_organization_by_id(self, organization_id: str) -> OrganizationPublic | None:
        with self._connect() as connection:
            row = connection.execute(self._sql("select * from organizations where id = ?"), (organization_id,)).fetchone()
        if row is None:
            return None
        return self._row_to_organization(row)

    def get_organization_by_code(self, code: str) -> OrganizationPublic | None:
        normalized_code = code.strip().upper()
        with self._connect() as connection:
            row = connection.execute(
                self._sql("select * from organizations where upper(code) = upper(?)"),
                (normalized_code,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_organization(row)

    def list_organizations(self, limit: int = 200) -> list[OrganizationPublic]:
        actual_limit = max(1, min(limit, 500))
        with self._connect() as connection:
            rows = connection.execute(
                self._sql("select * from organizations order by updated_at desc limit ?"),
                (actual_limit,),
            ).fetchall()
        return [self._row_to_organization(row) for row in rows]

    def get_user_membership(self, user_id: str) -> dict[str, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql(
                    """
                    select organization_memberships.organization_id, organization_memberships.role,
                           organizations.name, organizations.code
                    from organization_memberships
                    join organizations on organizations.id = organization_memberships.organization_id
                    where organization_memberships.user_id = ?
                    order by organization_memberships.joined_at desc
                    limit 1
                    """
                ),
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "organization_id": row["organization_id"],
            "role": row["role"],
            "organization_name": row["name"],
            "organization_code": row["code"],
        }

    def current_organization_for_user(self, user_id: str) -> OrganizationPublic | None:
        membership = self.get_user_membership(user_id)
        if membership is None:
            return None
        organization = self.get_organization_by_id(membership["organization_id"])
        if organization is None:
            return None
        return organization.model_copy(update={"current_user_role": membership["role"]})

    def organization_member_ids(self, organization_id: str, role: str | None = None) -> list[str]:
        with self._connect() as connection:
            if role is None:
                rows = connection.execute(
                    self._sql("select user_id from organization_memberships where organization_id = ?"),
                    (organization_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    self._sql("select user_id from organization_memberships where organization_id = ? and role = ?"),
                    (organization_id, role),
                ).fetchall()
        return [row["user_id"] for row in rows]

    def list_organization_members(self, organization_id: str) -> list[OrganizationMemberSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                self._sql(
                    """
                    select users.*, organization_memberships.joined_at
                    from organization_memberships
                    join users on users.id = organization_memberships.user_id
                    where organization_memberships.organization_id = ?
                    order by organization_memberships.joined_at desc
                    """
                ),
                (organization_id,),
            ).fetchall()
        summaries: list[OrganizationMemberSummary] = []
        for row in rows:
            session_summaries = self._learning_summary_for_user(row["id"], organization_id)
            summaries.append(
                OrganizationMemberSummary(
                    user=self._row_to_user(row),
                    joined_at=row["joined_at"],
                    **session_summaries,
                )
            )
        return summaries

    def create_organization_task(
        self,
        task_id: str,
        organization_id: str,
        creator_user_id: str,
        title: str,
        description: str,
        template_session_id: str,
        material_title: str,
        assignee_user_ids: list[str],
        assignment_id_factory: Callable[[], str],
        created_at: str,
    ) -> tuple[OrganizationLearningTask, list[OrganizationTaskAssignment]]:
        with self._lock, self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    insert into organization_learning_tasks
                        (id, organization_id, creator_user_id, title, description,
                         template_session_id, material_title, created_at, updated_at)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (
                    task_id,
                    organization_id,
                    creator_user_id,
                    title.strip(),
                    description.strip(),
                    template_session_id,
                    material_title.strip(),
                    created_at,
                    created_at,
                ),
            )
            for user_id in assignee_user_ids:
                connection.execute(
                    self._sql(
                        """
                        insert into organization_task_assignments
                            (id, task_id, organization_id, user_id, status, session_id, assigned_at, started_at, completed_at)
                        values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        on conflict(task_id, user_id) do nothing
                        """
                    ),
                    (assignment_id_factory(), task_id, organization_id, user_id, "assigned", None, created_at, None, None),
                )
        task = self.get_organization_task(task_id)
        assignments = self.list_task_assignments_for_task(task_id)
        if task is None:
            raise RuntimeError("组织任务创建失败")
        return task, assignments

    def get_organization_task(self, task_id: str) -> OrganizationLearningTask | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql("select * from organization_learning_tasks where id = ?"),
                (task_id,),
            ).fetchone()
        return self._row_to_org_task(row) if row is not None else None

    def list_task_assignments_for_task(self, task_id: str) -> list[OrganizationTaskAssignment]:
        with self._connect() as connection:
            rows = connection.execute(
                self._sql("select * from organization_task_assignments where task_id = ? order by assigned_at desc"),
                (task_id,),
            ).fetchall()
        return [self._row_to_org_assignment(row) for row in rows]

    def list_assignments_for_user(self, user_id: str) -> list[OrganizationTaskAssignment]:
        with self._connect() as connection:
            rows = connection.execute(
                self._sql(
                    """
                    select * from organization_task_assignments
                    where user_id = ?
                    order by assigned_at desc
                    limit 200
                    """
                ),
                (user_id,),
            ).fetchall()
        assignments = [self._row_to_org_assignment(row) for row in rows]
        return [
            assignment.model_copy(update={"task": self.get_organization_task(assignment.task_id)})
            for assignment in assignments
        ]

    def get_assignment_for_user(self, task_id: str, user_id: str) -> OrganizationTaskAssignment | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql("select * from organization_task_assignments where task_id = ? and user_id = ?"),
                (task_id, user_id),
            ).fetchone()
        if row is None:
            return None
        assignment = self._row_to_org_assignment(row)
        return assignment.model_copy(update={"task": self.get_organization_task(assignment.task_id)})

    def mark_assignment_started(self, task_id: str, user_id: str, session_id: str, started_at: str) -> OrganizationTaskAssignment | None:
        with self._lock, self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    update organization_task_assignments
                    set status = 'started', session_id = ?, started_at = coalesce(started_at, ?)
                    where task_id = ? and user_id = ?
                    """
                ),
                (session_id, started_at, task_id, user_id),
            )
        return self.get_assignment_for_user(task_id, user_id)

    def create_organization_knowledge_item(
        self,
        item_id: str,
        organization_id: str,
        uploader_user_id: str,
        title: str,
        chunks: list[str],
        chunk_id_factory: Callable[[], str],
        created_at: str,
    ) -> OrganizationKnowledgeItem:
        with self._lock, self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    insert into organization_knowledge_items
                        (id, organization_id, uploader_user_id, title, chunk_count, created_at, updated_at)
                    values (?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (item_id, organization_id, uploader_user_id, title.strip(), len(chunks), created_at, created_at),
            )
            for index, chunk in enumerate(chunks):
                connection.execute(
                    self._sql(
                        """
                        insert into organization_knowledge_chunks
                            (id, item_id, organization_id, chunk_index, text)
                        values (?, ?, ?, ?, ?)
                        """
                    ),
                    (chunk_id_factory(), item_id, organization_id, index, chunk),
                )
        item = self.get_organization_knowledge_item(item_id)
        if item is None:
            raise RuntimeError("组织知识库保存失败")
        return item

    def get_organization_knowledge_item(self, item_id: str) -> OrganizationKnowledgeItem | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql("select * from organization_knowledge_items where id = ?"),
                (item_id,),
            ).fetchone()
        return self._row_to_org_knowledge_item(row) if row is not None else None

    def list_organization_knowledge(self, organization_id: str) -> list[OrganizationKnowledgeItem]:
        with self._connect() as connection:
            rows = connection.execute(
                self._sql(
                    """
                    select * from organization_knowledge_items
                    where organization_id = ?
                    order by updated_at desc
                    limit 200
                    """
                ),
                (organization_id,),
            ).fetchall()
        return [self._row_to_org_knowledge_item(row) for row in rows]

    def delete_organization_knowledge_item(self, organization_id: str, item_id: str) -> bool:
        with self._lock, self._connect() as connection:
            connection.execute(
                self._sql("delete from organization_knowledge_chunks where organization_id = ? and item_id = ?"),
                (organization_id, item_id),
            )
            cursor = connection.execute(
                self._sql("delete from organization_knowledge_items where organization_id = ? and id = ?"),
                (organization_id, item_id),
            )
        return cursor.rowcount > 0

    def organization_knowledge_context(self, organization_id: str, limit: int = 6) -> str:
        with self._connect() as connection:
            rows = connection.execute(
                self._sql(
                    """
                    select organization_knowledge_items.title, organization_knowledge_chunks.text
                    from organization_knowledge_chunks
                    join organization_knowledge_items on organization_knowledge_items.id = organization_knowledge_chunks.item_id
                    where organization_knowledge_chunks.organization_id = ?
                    order by organization_knowledge_items.updated_at desc, organization_knowledge_chunks.chunk_index asc
                    limit ?
                    """
                ),
                (organization_id, max(1, min(limit, 20))),
            ).fetchall()
        lines = []
        for row in rows:
            lines.append(f"【{row['title']}】{row['text']}")
        return "\n".join(lines)

    def replace_sag_index(self, index) -> None:
        from .services_v2.sag_service import SagIndex

        if not isinstance(index, SagIndex):
            raise TypeError("replace_sag_index 需要 SagIndex 实例。")
        timestamp = datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            self._delete_sag_source(connection, index.tenant_id, index.session_id, index.source_id)
            entity_ids: dict[str, str] = {}
            for entity in index.entities:
                entity_id = stable_sag_id(index.tenant_id, index.session_id, index.source_id, "entity", entity.name)
                entity_ids[entity.name] = entity_id
                connection.execute(
                    self._sql(
                        """
                        insert into sag_entities
                            (id, tenant_id, user_id, session_id, source_id, name, type, description, created_at)
                        values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        on conflict(tenant_id, session_id, source_id, name) do update set
                            type = excluded.type,
                            description = excluded.description
                        """
                    ),
                    (
                        entity_id,
                        index.tenant_id,
                        index.user_id,
                        index.session_id,
                        index.source_id,
                        entity.name,
                        entity.type,
                        entity.description,
                        timestamp,
                    ),
                )
            for chunk in index.chunks:
                chunk_id = stable_sag_id(index.tenant_id, index.session_id, index.source_id, "chunk", str(chunk.index))
                connection.execute(
                    self._sql(
                        """
                        insert into sag_chunks
                            (id, tenant_id, user_id, session_id, source_id, chunk_index, text, text_hash, keywords, created_at)
                        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """
                    ),
                    (
                        chunk_id,
                        chunk.tenant_id,
                        chunk.user_id,
                        chunk.session_id,
                        chunk.source_id,
                        chunk.index,
                        chunk.text,
                        chunk.text_hash,
                        json.dumps(list(chunk.keywords), ensure_ascii=False),
                        timestamp,
                    ),
                )
                for name in chunk.entity_names:
                    entity_id = entity_ids.get(name)
                    if entity_id:
                        connection.execute(
                            self._sql("insert into sag_chunk_entities (chunk_id, entity_id) values (?, ?) on conflict do nothing"),
                            (chunk_id, entity_id),
                        )
            for event_index, event in enumerate(index.events):
                event_id = stable_sag_id(
                    index.tenant_id,
                    index.session_id,
                    index.source_id,
                    "event",
                    str(event.chunk_index),
                    str(event_index),
                    event.label,
                    event.description,
                )
                connection.execute(
                    self._sql(
                        """
                        insert into sag_events
                            (id, tenant_id, user_id, session_id, source_id, chunk_index, label, description, created_at)
                        values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """
                    ),
                    (
                        event_id,
                        index.tenant_id,
                        index.user_id,
                        index.session_id,
                        index.source_id,
                        event.chunk_index,
                        event.label,
                        event.description,
                        timestamp,
                    ),
                )
                for name in event.entity_names:
                    entity_id = entity_ids.get(name)
                    if entity_id:
                        connection.execute(
                            self._sql("insert into sag_event_entities (event_id, entity_id) values (?, ?) on conflict do nothing"),
                            (event_id, entity_id),
                        )

    def delete_sag_source(self, tenant_id: str, session_id: str, source_id: str) -> None:
        with self._lock, self._connect() as connection:
            self._delete_sag_source(connection, tenant_id, session_id, source_id)

    def _delete_sag_source(self, connection, tenant_id: str, session_id: str, source_id: str) -> None:
        params = (tenant_id, session_id, source_id)
        connection.execute(
            self._sql(
                """
                delete from sag_event_entities
                where event_id in (
                    select id from sag_events where tenant_id = ? and session_id = ? and source_id = ?
                )
                """
            ),
            params,
        )
        connection.execute(
            self._sql(
                """
                delete from sag_chunk_entities
                where chunk_id in (
                    select id from sag_chunks where tenant_id = ? and session_id = ? and source_id = ?
                )
                """
            ),
            params,
        )
        connection.execute(self._sql("delete from sag_events where tenant_id = ? and session_id = ? and source_id = ?"), params)
        connection.execute(self._sql("delete from sag_entities where tenant_id = ? and session_id = ? and source_id = ?"), params)
        connection.execute(self._sql("delete from sag_chunks where tenant_id = ? and session_id = ? and source_id = ?"), params)

    def load_sag_index(
        self,
        *,
        tenant_id: str,
        session_id: str,
        source_id: str | None = None,
        user_id: str | None = None,
    ):
        from .services_v2.sag_service import SagEntity, SagEvent, SagIndex, SagIndexedChunk

        filters = ["tenant_id = ?", "session_id = ?"]
        params: list[str] = [tenant_id, session_id]
        if source_id:
            filters.append("source_id = ?")
            params.append(source_id)
        if user_id:
            filters.append("user_id = ?")
            params.append(user_id)
        where_clause = " and ".join(filters)

        with self._connect() as connection:
            chunks_rows = connection.execute(
                self._sql(f"select * from sag_chunks where {where_clause} order by source_id, chunk_index"),
                tuple(params),
            ).fetchall()
            entity_rows = connection.execute(
                self._sql(f"select * from sag_entities where {where_clause} order by name"),
                tuple(params),
            ).fetchall()
            event_rows = connection.execute(
                self._sql(f"select * from sag_events where {where_clause} order by source_id, chunk_index, id"),
                tuple(params),
            ).fetchall()
            chunk_entity_rows = connection.execute(
                self._sql(
                    f"""
                    select sag_chunk_entities.chunk_id, sag_entities.name
                    from sag_chunk_entities
                    join sag_entities on sag_entities.id = sag_chunk_entities.entity_id
                    where sag_entities.{where_clause}
                    """
                ),
                tuple(params),
            ).fetchall()
            event_entity_rows = connection.execute(
                self._sql(
                    f"""
                    select sag_event_entities.event_id, sag_entities.name
                    from sag_event_entities
                    join sag_entities on sag_entities.id = sag_event_entities.entity_id
                    where sag_entities.{where_clause}
                    """
                ),
                tuple(params),
            ).fetchall()

        chunk_entities: dict[str, list[str]] = defaultdict(list)
        for row in chunk_entity_rows:
            chunk_entities[row["chunk_id"]].append(row["name"])
        event_entities: dict[str, list[str]] = defaultdict(list)
        for row in event_entity_rows:
            event_entities[row["event_id"]].append(row["name"])

        chunks = []
        for row in chunks_rows:
            try:
                keywords = tuple(json.loads(row["keywords"] or "[]"))
            except json.JSONDecodeError:
                keywords = ()
            chunks.append(
                SagIndexedChunk(
                    index=int(row["chunk_index"]),
                    text=row["text"],
                    text_hash=row["text_hash"],
                    tenant_id=row["tenant_id"],
                    user_id=row["user_id"],
                    session_id=row["session_id"],
                    source_id=row["source_id"],
                    keywords=keywords,
                    entity_names=tuple(chunk_entities.get(row["id"], [])),
                )
            )
        entities = [
            SagEntity(name=row["name"], type=row["type"], description=row["description"])
            for row in entity_rows
        ]
        events = [
            SagEvent(
                label=row["label"],
                description=row["description"],
                chunk_index=int(row["chunk_index"]),
                source_id=row["source_id"],
                entity_names=tuple(event_entities.get(row["id"], [])),
            )
            for row in event_rows
        ]
        return SagIndex(
            tenant_id=tenant_id,
            user_id=user_id or (chunks[0].user_id if chunks else ""),
            session_id=session_id,
            source_id=source_id or (chunks[0].source_id if chunks else ""),
            chunks=tuple(chunks),
            entities=tuple(entities),
            events=tuple(events),
        )

    def create_token(self, token: str, user_id: str, created_at: str, remember_me: bool = False) -> None:
        expires_at = (
            datetime.fromisoformat(created_at) + timedelta(seconds=TOKEN_TTL_REMEMBER_SECONDS if remember_me else TOKEN_TTL_SECONDS)
        ).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                self._sql(
                    "insert into auth_tokens (token, user_id, created_at, last_reauth_at, expires_at) values (?, ?, ?, ?, ?)"
                ),
                (token, user_id, created_at, created_at, expires_at),
            )
            self._prune_tokens_for_user(connection, user_id)

    def _prune_tokens_for_user(self, connection, user_id: str) -> None:
        rows = connection.execute(
            self._sql("select token, created_at, expires_at from auth_tokens where user_id = ? order by created_at desc"),
            (user_id,),
        ).fetchall()
        active_seen = 0
        to_delete: list[str] = []
        max_tokens = max_active_tokens_per_user()
        for row in rows:
            if token_is_expired(row["expires_at"]):
                to_delete.append(row["token"])
                continue
            active_seen += 1
            if active_seen > max_tokens:
                to_delete.append(row["token"])
        if to_delete:
            connection.executemany(
                self._sql("delete from auth_tokens where token = ?"),
                [(token,) for token in to_delete],
            )

    def get_user_by_token(self, token: str) -> UserPublic | None:
        current_storage_key = token_storage_key(token)
        accepted_keys = accepted_token_storage_keys(token)
        placeholders = ", ".join("?" for _ in accepted_keys)
        with self._connect() as connection:
            row = connection.execute(
                self._sql(
                    f"""
                    select users.*, auth_tokens.token as stored_token, auth_tokens.created_at as token_created_at,
                           auth_tokens.expires_at as token_expires_at
                    from auth_tokens
                    join users on users.id = auth_tokens.user_id
                    where auth_tokens.token in ({placeholders})
                    order by case when auth_tokens.token = ? then 0 else 1 end
                    limit 1
                    """
                ),
                (*accepted_keys, current_storage_key),
            ).fetchone()
        if row is None:
            return None
        if token_is_expired(row["token_expires_at"]):
            self.delete_token(token)
            return None
        if row["stored_token"] != current_storage_key:
            self._migrate_token_storage_key(row["stored_token"], current_storage_key)
        return self._row_to_user(row)

    def _migrate_token_storage_key(self, previous_storage_key: str, current_storage_key: str) -> None:
        with self._lock, self._connect() as connection:
            existing_key = connection.execute(
                self._sql("select token from auth_tokens where token = ?"),
                (current_storage_key,),
            ).fetchone()
            if existing_key is not None:
                connection.execute(self._sql("delete from auth_tokens where token = ?"), (previous_storage_key,))
                return
            connection.execute(
                self._sql("update auth_tokens set token = ? where token = ?"),
                (current_storage_key, previous_storage_key),
            )

    def delete_token(self, token: str) -> None:
        storage_keys = accepted_token_storage_keys(token)
        placeholders = ", ".join("?" for _ in storage_keys)
        with self._lock, self._connect() as connection:
            connection.execute(self._sql(f"delete from auth_tokens where token in ({placeholders})"), storage_keys)

    def delete_user_tokens(self, user_id: str) -> int:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(self._sql("delete from auth_tokens where user_id = ?"), (user_id,))
            return cursor.rowcount

    def token_recently_reauthenticated(self, token: str, max_age_seconds: int) -> bool:
        storage_keys = accepted_token_storage_keys(token)
        placeholders = ", ".join("?" for _ in storage_keys)
        with self._connect() as connection:
            row = connection.execute(
                self._sql(f"select last_reauth_at from auth_tokens where token in ({placeholders}) limit 1"),
                storage_keys,
            ).fetchone()
        if row is None:
            return False
        try:
            return seconds_since(row["last_reauth_at"]) <= max_age_seconds
        except (TypeError, ValueError):
            return False

    def mark_token_reauthenticated(self, token: str, reauth_at: str) -> None:
        storage_keys = accepted_token_storage_keys(token)
        placeholders = ", ".join("?" for _ in storage_keys)
        with self._lock, self._connect() as connection:
            connection.execute(
                self._sql(f"update auth_tokens set last_reauth_at = ? where token in ({placeholders})"),
                (reauth_at, *storage_keys),
            )

    def create_parse_job(
        self,
        job_id: str,
        user_id: str,
        title: str,
        content: str,
        created_at: str,
    ) -> ParseJob:
        with self._lock, self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    insert into parse_jobs
                        (id, user_id, title, content, status, progress, message, session_id, error, created_at, updated_at)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (
                    job_id,
                    user_id,
                    title,
                    content,
                    "queued",
                    5,
                    "已加入解析队列",
                    None,
                    None,
                    created_at,
                    created_at,
                ),
            )
        job = self._get_parse_job_unchecked(job_id)
        if job is None:
            raise RuntimeError("解析任务创建失败")
        return job

    def create_parse_job_guarded(
        self,
        job_id: str,
        user_id: str,
        title: str,
        content: str,
        created_at: str,
        min_submit_interval_seconds: int,
    ) -> ParseJob:
        with self._lock, self._connect() as connection:
            self._release_stale_parse_jobs(connection, user_id, created_at)
            recent_row = connection.execute(
                self._sql(
                    """
                    select * from parse_jobs
                    where user_id = ?
                    order by created_at desc
                    limit 1
                    """
                ),
                (user_id,),
            ).fetchone()
            if recent_row is not None:
                recent = self._row_to_parse_job(recent_row)
                if recent.status in {"queued", "running"}:
                    raise ParseJobCreateBlocked("running", recent)
                if seconds_since(recent.created_at) < min_submit_interval_seconds:
                    raise ParseJobCreateBlocked("too_frequent", recent)

            connection.execute(
                self._sql(
                    """
                    insert into parse_jobs
                        (id, user_id, title, content, status, progress, message, session_id, error, created_at, updated_at)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (
                    job_id,
                    user_id,
                    title,
                    content,
                    "queued",
                    5,
                    "已加入解析队列",
                    None,
                    None,
                    created_at,
                    created_at,
                ),
            )
            row = connection.execute(self._sql("select * from parse_jobs where id = ?"), (job_id,)).fetchone()
            self._prune_parse_jobs_for_user(connection, user_id)
        if row is None:
            raise RuntimeError("解析任务创建失败")
        return self._row_to_parse_job(row)

    def release_stale_parse_jobs(self, user_id: str | None = None, updated_at: str | None = None) -> int:
        timestamp = updated_at or datetime.now(UTC).isoformat()
        with self._lock, self._connect() as connection:
            return self._release_stale_parse_jobs(connection, user_id, timestamp)

    def update_parse_job(
        self,
        job_id: str,
        status: str,
        progress: int,
        message: str,
        updated_at: str,
        session_id: str | None = None,
        error: str | None = None,
    ) -> ParseJob | None:
        with self._lock, self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    update parse_jobs
                    set status = ?, progress = ?, message = ?, session_id = ?, error = ?, updated_at = ?
                    where id = ?
                    """
                ),
                (status, progress, message, session_id, error, updated_at, job_id),
            )
            if status in {"completed", "failed"}:
                row = connection.execute(self._sql("select user_id from parse_jobs where id = ?"), (job_id,)).fetchone()
                if row is not None:
                    self._prune_parse_jobs_for_user(connection, row["user_id"])
        return self._get_parse_job_unchecked(job_id)

    def get_parse_job(self, job_id: str, user_id: str | None = None) -> ParseJob | None:
        self.release_stale_parse_jobs(user_id)
        return self._get_parse_job_unchecked(job_id, user_id)

    def _get_parse_job_unchecked(self, job_id: str, user_id: str | None = None) -> ParseJob | None:
        with self._connect() as connection:
            if user_id is None:
                row = connection.execute(self._sql("select * from parse_jobs where id = ?"), (job_id,)).fetchone()
            else:
                row = connection.execute(
                    self._sql("select * from parse_jobs where id = ? and user_id = ?"),
                    (job_id, user_id),
                ).fetchone()
        if row is None:
            return None
        return self._row_to_parse_job(row)

    def get_parse_job_content(self, job_id: str) -> tuple[str, str, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql("select user_id, title, content from parse_jobs where id = ?"),
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return row["user_id"], row["title"], row["content"]

    def clear_parse_job_content(self, job_id: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                self._sql("update parse_jobs set content = '' where id = ?"),
                (job_id,),
            )

    def get_recent_parse_job(self, user_id: str) -> ParseJob | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql(
                    """
                    select * from parse_jobs
                    where user_id = ?
                    order by created_at desc
                    limit 1
                    """
                ),
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_parse_job(row)

    def _prune_parse_jobs_for_user(self, connection, user_id: str) -> None:
        retention = parse_job_retention_per_user()
        connection.execute(
            self._sql(
                """
                with keep as (
                    select id from parse_jobs
                    where user_id = ?
                      and status not in ('queued', 'running')
                    order by updated_at desc
                    limit ?
                )
                delete from parse_jobs
                where user_id = ?
                  and status not in ('queued', 'running')
                  and id not in (select id from keep)
                """
            ),
            (user_id, retention, user_id),
        )

    def _release_stale_parse_jobs(self, connection, user_id: str | None, updated_at: str) -> int:
        user_clause = "and user_id = %s" if user_id is not None else ""
        parameters: tuple[object, ...] = (user_id,) if user_id is not None else ()
        rows = connection.execute(
            self._sql(
                f"""
                select id, updated_at from parse_jobs
                where status in ('queued', 'running')
                {user_clause}
                """
            ),
            parameters,
        ).fetchall()
        stale_ids = [row["id"] for row in rows if seconds_since(row["updated_at"]) > STALE_RUNNING_PARSE_JOB_SECONDS]
        if not stale_ids:
            return 0
        placeholders = ", ".join(["?"] * len(stale_ids))
        connection.execute(
            self._sql(
                f"""
                update parse_jobs
                set status = ?, progress = ?, message = ?, session_id = ?, error = ?, updated_at = ?, content = ?
                where id in ({placeholders})
                """
            ),
            (
                "failed",
                100,
                "解析任务已超时",
                None,
                "解析任务长时间未更新，已自动释放上传锁，请重新上传材料。",
                updated_at,
                "",
                *stale_ids,
            ),
        )
        return len(stale_ids)

    def upsert_api_config(
        self,
        config_id: str,
        provider: str,
        base_url: str,
        api_key: str,
        model: str,
        is_active: bool,
        created_at: str,
        updated_at: str,
    ) -> ApiConfig:
        normalized_provider, normalized_base_url, normalized_api_key, normalized_model = validate_api_config_parts(
            provider,
            base_url,
            api_key,
            model,
        )
        stored_api_key = encrypt_secret(normalized_api_key, self.db_path or "")
        with self._lock, self._connect() as connection:
            if is_active:
                connection.execute(self._sql("update api_configs set is_active = 0 where id != ?"), (config_id,))
            existing = connection.execute(
                self._sql("select created_at from api_configs where id = ?"),
                (config_id,),
            ).fetchone()
            actual_created_at = existing["created_at"] if existing else created_at
            connection.execute(
                self._sql(
                    """
                    insert into api_configs (id, provider, base_url, api_key, model, is_active, created_at, updated_at)
                    values (?, ?, ?, ?, ?, ?, ?, ?)
                    on conflict(id) do update set
                        provider = excluded.provider,
                        base_url = excluded.base_url,
                        api_key = excluded.api_key,
                        model = excluded.model,
                        is_active = excluded.is_active,
                        updated_at = excluded.updated_at
                    """
                ),
                (
                    config_id,
                    normalized_provider,
                    normalized_base_url,
                    stored_api_key,
                    normalized_model,
                    int(is_active),
                    actual_created_at,
                    updated_at,
                ),
            )
        config = self.get_api_config(config_id)
        if config is None:
            raise RuntimeError("API 配置保存失败")
        return config

    def get_api_config(self, config_id: str) -> ApiConfig | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql("select * from api_configs where id = ?"),
                (config_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_api_config(row)

    def get_api_config_secret(self, config_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql("select api_key from api_configs where id = ?"),
                (config_id,),
            ).fetchone()
        return None if row is None else decrypt_secret(row["api_key"], self.db_path or "")

    def list_api_configs(self, limit: int = 100) -> list[ApiConfig]:
        actual_limit = max(1, min(limit, 200))
        with self._connect() as connection:
            rows = connection.execute(
                self._sql("select * from api_configs order by updated_at desc limit ?"),
                (actual_limit,),
            ).fetchall()
        return [self._row_to_api_config(row) for row in rows]

    def get_active_api_config_secret_record(self) -> dict[str, str] | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql(
                    """
                    select * from api_configs
                    where is_active = 1
                    order by updated_at desc
                    limit 1
                    """
                )
            ).fetchone()
        if row is None:
            return None
        provider, base_url, api_key, model = validate_api_config_parts(
            row["provider"],
            row["base_url"],
            decrypt_secret(row["api_key"], self.db_path or ""),
            row["model"],
        )
        return {
            "id": row["id"],
            "provider": provider,
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
        }

    def delete_api_config(self, config_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(self._sql("delete from api_configs where id = ?"), (config_id,))
        return cursor.rowcount > 0

    def upsert_speech_config(
        self,
        config_id: str,
        kind: str,
        provider: str,
        base_url: str,
        api_key: str,
        model: str,
        path: str,
        is_active: bool,
        voice: str | None,
        language: str | None,
        response_format: str | None,
        created_at: str,
        updated_at: str,
    ) -> SpeechConfig:
        (
            normalized_kind,
            normalized_provider,
            normalized_base_url,
            normalized_api_key,
            normalized_model,
            normalized_path,
            normalized_voice,
            normalized_language,
            normalized_response_format,
        ) = validate_speech_config_parts(
            kind,
            provider,
            base_url,
            api_key,
            model,
            path,
            voice,
            language,
            response_format,
        )
        stored_api_key = encrypt_secret(normalized_api_key, self.db_path or "")
        with self._lock, self._connect() as connection:
            if is_active:
                connection.execute(
                    self._sql("update speech_configs set is_active = 0 where kind = ? and id != ?"),
                    (normalized_kind, config_id),
                )
            existing = connection.execute(
                self._sql("select created_at from speech_configs where id = ?"),
                (config_id,),
            ).fetchone()
            actual_created_at = existing["created_at"] if existing else created_at
            connection.execute(
                self._sql(
                    """
                    insert into speech_configs
                        (id, kind, provider, base_url, api_key, model, path, is_active, voice, language, response_format, created_at, updated_at)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    on conflict(id) do update set
                        kind = excluded.kind,
                        provider = excluded.provider,
                        base_url = excluded.base_url,
                        api_key = excluded.api_key,
                        model = excluded.model,
                        path = excluded.path,
                        is_active = excluded.is_active,
                        voice = excluded.voice,
                        language = excluded.language,
                        response_format = excluded.response_format,
                        updated_at = excluded.updated_at
                    """
                ),
                (
                    config_id,
                    normalized_kind,
                    normalized_provider,
                    normalized_base_url,
                    stored_api_key,
                    normalized_model,
                    normalized_path,
                    int(is_active),
                    normalized_voice,
                    normalized_language,
                    normalized_response_format,
                    actual_created_at,
                    updated_at,
                ),
            )
        config = self.get_speech_config(config_id)
        if config is None:
            raise RuntimeError("语音配置保存失败")
        return config

    def get_speech_config(self, config_id: str) -> SpeechConfig | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql("select * from speech_configs where id = ?"),
                (config_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_speech_config(row)

    def get_speech_config_secret(self, config_id: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                self._sql("select api_key from speech_configs where id = ?"),
                (config_id,),
            ).fetchone()
        return None if row is None else decrypt_secret(row["api_key"], self.db_path or "")

    def list_speech_configs(self, limit: int = 100) -> list[SpeechConfig]:
        actual_limit = max(1, min(limit, 200))
        with self._connect() as connection:
            rows = connection.execute(
                self._sql("select * from speech_configs order by kind asc, updated_at desc limit ?"),
                (actual_limit,),
            ).fetchall()
        return [self._row_to_speech_config(row) for row in rows]

    def get_active_speech_config_secret_record(self, kind: str) -> dict[str, str] | None:
        normalized_kind = validate_speech_config_kind(kind)
        with self._connect() as connection:
            row = connection.execute(
                self._sql(
                    """
                    select * from speech_configs
                    where kind = ? and is_active = 1
                    order by updated_at desc
                    limit 1
                    """
                ),
                (normalized_kind,),
            ).fetchone()
        if row is None:
            return None
        (
            config_kind,
            provider,
            base_url,
            api_key,
            model,
            path,
            voice,
            language,
            response_format,
        ) = validate_speech_config_parts(
            row["kind"],
            row["provider"],
            row["base_url"],
            decrypt_secret(row["api_key"], self.db_path or ""),
            row["model"],
            row["path"],
            row["voice"],
            row["language"],
            row["response_format"],
        )
        return {
            "id": row["id"],
            "kind": config_kind,
            "provider": provider,
            "base_url": base_url,
            "api_key": api_key,
            "model": model,
            "path": path,
            "voice": voice,
            "language": language,
            "response_format": response_format,
        }

    def delete_speech_config(self, config_id: str) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(self._sql("delete from speech_configs where id = ?"), (config_id,))
        return cursor.rowcount > 0

    def create_audit_log(
        self,
        log_id: str,
        actor_user_id: str | None,
        actor_username: str | None,
        action: str,
        target_type: str,
        target_id: str | None,
        detail: str,
        created_at: str,
    ) -> None:
        safe_detail = detail[:MAX_AUDIT_DETAIL_CHARS]
        with self._lock, self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    insert into audit_logs
                        (id, actor_user_id, actor_username, action, target_type, target_id, detail, created_at)
                    values (?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (log_id, actor_user_id, actor_username, action, target_type, target_id, safe_detail, created_at),
            )
            self._prune_audit_logs(connection)

    def _prune_audit_logs(self, connection) -> None:
        retention = audit_log_retention_limit()
        connection.execute(
            self._sql(
                """
                with keep as (
                    select id from audit_logs
                    order by created_at desc
                    limit ?
                )
                delete from audit_logs
                where id not in (select id from keep)
                """
            ),
            (retention,),
        )

    def list_audit_logs(self, limit: int = 200) -> list[AuditLogEntry]:
        actual_limit = max(1, min(limit, 500))
        with self._connect() as connection:
            rows = connection.execute(
                self._sql("select * from audit_logs order by created_at desc limit ?"),
                (actual_limit,),
            ).fetchall()
        return [self._row_to_audit_log(row) for row in rows]

    def record_token_usage(self, record: TokenUsageRecord) -> None:
        total_tokens = record.total_tokens or record.prompt_tokens + record.completion_tokens
        with self._connect() as connection:
            connection.execute(
                self._sql(
                    """
                    insert into llm_token_usage
                        (id, user_id, session_id, source, provider, model, prompt_tokens, completion_tokens, total_tokens, created_at)
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (
                    record.id,
                    record.user_id,
                    record.session_id,
                    record.source,
                    record.provider,
                    record.model,
                    max(0, record.prompt_tokens),
                    max(0, record.completion_tokens),
                    max(0, total_tokens),
                    record.created_at.isoformat(),
                ),
            )

    def research_dashboard(self, organization_id: str | None = None) -> ResearchDashboardResponse:
        sessions = self._all_sessions_for_research(organization_id)
        experiment_records = self.list_research_experiment_records(limit=500)
        usage_total, usage_today = (
            self._token_usage_totals_for_organization(organization_id)
            if organization_id
            else self._token_usage_totals()
        )
        total_nodes = sum(len(session.nodes) for session in sessions)
        mastered_nodes = sum(1 for session in sessions for node in session.nodes if node.status == "mastered")
        total_messages = sum(len(session.messages) for session in sessions)
        score_values: list[int] = []
        weak_scores: dict[str, list[int]] = defaultdict(list)
        weak_point_counts: Counter[str] = Counter()
        memory_counts: Counter[str] = Counter()
        long_memory_counts: Counter[str] = Counter()
        material_quality: list[MaterialQualitySummary] = []

        for session in sessions:
            material_quality.append(material_quality_summary(session))
            for memory in session.memories:
                category = memory.kind or "unknown"
                memory_counts[category] += 1
                if memory.retention == "long" or memory.scope == "long_term":
                    long_memory_counts[category] += 1
            for profile in session.node_profiles.values():
                for point in profile.weak_points:
                    normalized = point.strip()
                    if normalized:
                        weak_point_counts[normalized] += 1
                for stage, score in profile.dimension_scores.items():
                    normalized_score = clamp_score(score)
                    score_values.append(normalized_score)
                    if normalized_score < 70:
                        weak_scores[stage].append(normalized_score)
            for assessment in session.feynman_assessments.values():
                for item in assessment.dimension_scores:
                    normalized_score = clamp_score(item.value)
                    score_values.append(normalized_score)
                    if normalized_score < 70:
                        weak_scores[item.stage].append(normalized_score)
                for item in assessment.question_diagnostics:
                    if item.value < 70:
                        weak_point_counts[item.label] += 1

        average_score = round(sum(score_values) / len(score_values), 1) if score_values else 0.0
        pass_rate = round(sum(1 for value in score_values if value >= 70) / len(score_values), 3) if score_values else 0.0
        mastery_rate = round(mastered_nodes / total_nodes, 3) if total_nodes else 0.0
        metrics = [
            ResearchMetric(label="学习者数", value=float(len({session.user_id for session in sessions if session.user_id})), unit="人", note="来自已保存学习会话的唯一用户数。"),
            ResearchMetric(label="材料数", value=float(len(sessions)), unit="份", note="按学习会话统计，不含已清空的解析任务原文。"),
            ResearchMetric(label="知识节点", value=float(total_nodes), unit="个", note="所有会话生成的节点总数。"),
            ResearchMetric(label="节点掌握率", value=mastery_rate, unit="ratio", note="已掌握节点数 / 总节点数。"),
            ResearchMetric(label="费曼平均分", value=average_score, unit="分", note="来自节点画像和费曼诊断维度分。"),
            ResearchMetric(label="费曼达标率", value=pass_rate, unit="ratio", note="维度分不低于 70 的比例。"),
            ResearchMetric(label="学习轮次", value=float(total_messages), unit="条", note="学习者和导师消息总量。"),
            ResearchMetric(label="今日 Token", value=float(usage_today), unit="token", note="后端记录的今日模型消耗。"),
            ResearchMetric(label="累计 Token", value=float(usage_total), unit="token", note="后端记录的累计模型消耗。"),
            ResearchMetric(label="实验样本", value=float(len(experiment_records)), unit="条", note="管理员导入的匿名前后测/盲评研究记录。"),
        ]

        weak_points = [
            WeakPointSummary(
                label=stage_label,
                count=len(values),
                average_score=round(sum(values) / len(values), 1),
            )
            for stage_label, values in sorted(weak_scores.items(), key=lambda item: (-len(item[1]), item[0]))
        ]
        common_misconceptions = [
            WeakPointSummary(label=label, count=count, average_score=0)
            for label, count in weak_point_counts.most_common(8)
        ]
        memory_categories = [
            MemoryCategorySummary(
                category=category,
                count=count,
                long_term_count=long_memory_counts.get(category, 0),
            )
            for category, count in sorted(memory_counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        return ResearchDashboardResponse(
            generated_at=datetime.now(UTC),
            metrics=metrics,
            weak_points=weak_points[:8],
            feynman_distribution=feynman_distribution(score_values),
            common_misconceptions=common_misconceptions,
            material_quality=sorted(material_quality, key=lambda item: item.updated_at, reverse=True)[:12],
            memory_categories=memory_categories,
            experiment_summaries=experiment_group_summaries(experiment_records),
            score_agreement=score_agreement_summary(experiment_records),
            experiment_records=experiment_records[:80],
        )

    def import_research_experiment_records(
        self,
        records: list[ResearchExperimentRecordInput],
        imported_at: str,
        id_factory: Callable[[], str],
    ) -> list[ResearchExperimentRecord]:
        saved: list[ResearchExperimentRecord] = []
        with self._lock, self._connect() as connection:
            for record in records:
                record_id = record.id or id_factory()
                connection.execute(
                    self._sql(
                        """
                        insert into research_experiment_records
                            (id, study_id, participant_code, group_label, material_label,
                             pretest_score, posttest_score, delayed_score, system_feynman_score,
                             human_score, learning_minutes, cognitive_load, notes, imported_at, updated_at)
                        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        on conflict(study_id, participant_code, group_label, material_label) do update set
                            pretest_score = excluded.pretest_score,
                            posttest_score = excluded.posttest_score,
                            delayed_score = excluded.delayed_score,
                            system_feynman_score = excluded.system_feynman_score,
                            human_score = excluded.human_score,
                            learning_minutes = excluded.learning_minutes,
                            cognitive_load = excluded.cognitive_load,
                            notes = excluded.notes,
                            updated_at = excluded.updated_at
                        """
                    ),
                    (
                        record_id,
                        record.study_id.strip(),
                        record.participant_code.strip(),
                        record.group_label.strip(),
                        record.material_label.strip(),
                        record.pretest_score,
                        record.posttest_score,
                        record.delayed_score,
                        record.system_feynman_score,
                        record.human_score,
                        record.learning_minutes,
                        record.cognitive_load,
                        record.notes.strip(),
                        imported_at,
                        imported_at,
                    ),
                )
            keys = [(record.study_id.strip(), record.participant_code.strip(), record.group_label.strip(), record.material_label.strip()) for record in records]
            for study_id, participant_code, group_label, material_label in keys:
                row = connection.execute(
                    self._sql(
                        """
                        select * from research_experiment_records
                        where study_id = ? and participant_code = ? and group_label = ? and material_label = ?
                        """
                    ),
                    (study_id, participant_code, group_label, material_label),
                ).fetchone()
                if row is not None:
                    saved.append(self._row_to_research_experiment_record(row))
        return saved

    def list_research_experiment_records(self, limit: int = 500) -> list[ResearchExperimentRecord]:
        actual_limit = max(1, min(limit, 2000))
        with self._connect() as connection:
            rows = connection.execute(
                self._sql("select * from research_experiment_records order by updated_at desc limit ?"),
                (actual_limit,),
            ).fetchall()
        return [self._row_to_research_experiment_record(row) for row in rows]

    def export_blind_review_answers(self, limit: int = 2000, organization_id: str | None = None, user_id: str | None = None) -> list[ResearchBlindReviewAnswer]:
        answers: list[ResearchBlindReviewAnswer] = []
        for session in self._all_sessions_for_research(organization_id=organization_id, user_id=user_id):
            node_by_id = {node.id: node for node in session.nodes}
            for node_id, answer_map in session.feynman_answers.items():
                node = node_by_id.get(node_id)
                assessment = session.feynman_assessments.get(node_id)
                diagnostic_by_question_id = {
                    diagnostic.question_id: diagnostic
                    for diagnostic in (assessment.question_diagnostics if assessment else [])
                }
                for answer in answer_map.values():
                    diagnostic = diagnostic_by_question_id.get(answer.question_id)
                    answers.append(
                        ResearchBlindReviewAnswer(
                            sample_id=f"{session.id[:8]}-{node_id[:8]}-{answer.question_id[:16]}",
                            session_id=session.id,
                            node_id=node_id,
                            node_title=node.title if node else "",
                            question_id=answer.question_id,
                            question_label=answer.label,
                            question=answer.question,
                            answer=answer.answer,
                            system_score=diagnostic.value if diagnostic else None,
                            system_note=diagnostic.note if diagnostic else "",
                            updated_at=assessment.updated_at if assessment else session.updated_at,
                        )
                    )
                    if len(answers) >= limit:
                        return answers
        return answers

    def _all_sessions_for_research(
        self,
        organization_id: str | None = None,
        user_id: str | None = None,
    ) -> list[LearningSession]:
        with self._connect() as connection:
            if organization_id is not None and user_id is not None:
                rows = connection.execute(
                    self._sql(
                        """
                        select payload, user_id, organization_id, task_id, visibility
                        from sessions
                        where organization_id = ? and user_id = ?
                          and visibility != 'organization_task_template'
                        order by updated_at desc
                        limit 500
                        """
                    ),
                    (organization_id, user_id),
                ).fetchall()
            elif organization_id is not None:
                rows = connection.execute(
                    self._sql(
                        """
                        select payload, user_id, organization_id, task_id, visibility
                        from sessions
                        where organization_id = ?
                          and visibility != 'organization_task_template'
                        order by updated_at desc
                        limit 500
                        """
                    ),
                    (organization_id,),
                ).fetchall()
            elif user_id is not None:
                rows = connection.execute(
                    self._sql(
                        """
                        select payload, user_id, organization_id, task_id, visibility
                        from sessions
                        where user_id = ?
                          and visibility != 'organization_task_template'
                        order by updated_at desc
                        limit 500
                        """
                    ),
                    (user_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    self._sql(
                        """
                        select payload, user_id, organization_id, task_id, visibility
                        from sessions
                        where visibility != 'organization_task_template'
                        order by updated_at desc
                        limit 500
                        """
                    )
                ).fetchall()
        return [self._row_to_session(row) for row in rows]

    def _token_usage_totals(self) -> tuple[int, int]:
        start_of_today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                self._sql(
                    """
                    select coalesce(sum(total_tokens), 0) as total_tokens,
                           coalesce(sum(case when created_at >= ? then total_tokens else 0 end), 0) as today_tokens
                    from llm_token_usage
                    """
                ),
                (start_of_today,),
            ).fetchone()
        if row is None:
            return 0, 0
        return int(row["total_tokens"] or 0), int(row["today_tokens"] or 0)

    def _token_usage_totals_for_users(self, connection, user_ids: list[str]) -> dict[str, tuple[int, int]]:
        if not user_ids:
            return {}
        placeholders = ", ".join("?" for _ in user_ids)
        start_of_today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        rows = connection.execute(
            self._sql(
                f"""
                select user_id,
                       coalesce(sum(total_tokens), 0) as total_tokens,
                       coalesce(sum(case when created_at >= ? then total_tokens else 0 end), 0) as today_tokens
                from llm_token_usage
                where user_id in ({placeholders})
                group by user_id
                """
            ),
            (start_of_today, *user_ids),
        ).fetchall()
        return {
            row["user_id"]: (int(row["total_tokens"] or 0), int(row["today_tokens"] or 0))
            for row in rows
        }

    def _token_usage_totals_for_organization(self, organization_id: str) -> tuple[int, int]:
        user_ids = self.organization_member_ids(organization_id)
        if not user_ids:
            return 0, 0
        with self._connect() as connection:
            totals = self._token_usage_totals_for_users(connection, user_ids)
        return (
            sum(item[0] for item in totals.values()),
            sum(item[1] for item in totals.values()),
        )

    def _learning_summary_for_user(self, user_id: str, organization_id: str | None = None) -> dict[str, int | float]:
        sessions = self._all_sessions_for_research(organization_id=organization_id, user_id=user_id)
        node_count = sum(len(session.nodes) for session in sessions)
        mastered_count = sum(1 for session in sessions for node in session.nodes if node.status == "mastered")
        scores: list[int] = []
        for session in sessions:
            for assessment in session.feynman_assessments.values():
                scores.extend(clamp_score(item.value) for item in assessment.dimension_scores)
            for profile in session.node_profiles.values():
                scores.extend(clamp_score(value) for value in profile.dimension_scores.values())
        return {
            "session_count": len(sessions),
            "mastered_count": mastered_count,
            "node_count": node_count,
            "average_feynman_score": round(sum(scores) / len(scores), 1) if scores else 0.0,
        }

    def organization_member_report(self, organization_id: str, user_id: str) -> OrganizationMemberReport | None:
        membership = self.get_user_membership(user_id)
        if membership is None or membership["organization_id"] != organization_id:
            return None
        user = self.get_user_by_id(user_id)
        if user is None:
            return None
        sessions = self._all_sessions_for_research(organization_id=organization_id, user_id=user_id)
        summaries = [
            SessionSummary(
                id=session.id,
                material_title=session.material_title,
                active_node_id=session.active_node_id,
                mastered_count=sum(1 for node in session.nodes if node.status == "mastered"),
                node_count=len(session.nodes),
                updated_at=session.updated_at,
            )
            for session in sessions
        ]
        session_traces = [organization_session_trace(session) for session in sessions]
        dimension_scores = [
            score
            for session in sessions
            for assessment in session.feynman_assessments.values()
            for score in assessment.dimension_scores
        ]
        summary = self._learning_summary_for_user(user_id, organization_id)
        return OrganizationMemberReport(
            user=user,
            sessions=summaries,
            session_traces=session_traces,
            feynman_answers=self.export_blind_review_answers(organization_id=organization_id, user_id=user_id),
            dimension_scores=dimension_scores,
            mastered_count=int(summary["mastered_count"]),
            node_count=int(summary["node_count"]),
            average_feynman_score=float(summary["average_feynman_score"]),
        )

    def organization_trace_export(self, organization_id: str) -> OrganizationTraceExportResponse | None:
        organization = self.get_organization_by_id(organization_id)
        if organization is None:
            return None
        reports: list[OrganizationMemberReport] = []
        for user_id in self.organization_member_ids(organization_id):
            report = self.organization_member_report(organization_id, user_id)
            if report is not None:
                reports.append(report)
        return OrganizationTraceExportResponse(
            generated_at=datetime.now(UTC),
            organization=organization,
            members=reports,
        )

    def _row_to_user(self, row, total_tokens: int = 0, today_tokens: int = 0) -> UserPublic:
        row_get = row.get if hasattr(row, "get") else lambda _key, default=None: default
        membership = self.get_user_membership(row["id"])
        organization_id = membership["organization_id"] if membership else None
        organization_name = membership["organization_name"] if membership else None
        organization_code = membership["organization_code"] if membership else None
        default_seeded = bool(row_get("default_credentials_seeded", 0))
        password_changed_at = row_get("password_changed_at")
        return UserPublic(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            organization_id=organization_id,
            organization_name=organization_name,
            organization_code=organization_code,
            default_credentials_seeded=default_seeded,
            password_changed_at=password_changed_at,
            security_notice=(
                {"kind": "default_admin_credentials", "can_defer": True}
                if default_seeded and not password_changed_at
                else None
            ),
            total_tokens=max(0, total_tokens),
            today_tokens=max(0, today_tokens),
        )

    def _row_to_organization(self, row) -> OrganizationPublic:
        with self._connect() as connection:
            count_row = connection.execute(
                self._sql("select count(*) as count from organization_memberships where organization_id = ?"),
                (row["id"],),
            ).fetchone()
        return OrganizationPublic(
            id=row["id"],
            code=row["code"],
            name=row["name"],
            owner_user_id=row["owner_user_id"],
            member_count=int(count_row["count"] or 0) if count_row else 0,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_org_task(self, row) -> OrganizationLearningTask:
        return OrganizationLearningTask(
            id=row["id"],
            organization_id=row["organization_id"],
            creator_user_id=row["creator_user_id"],
            title=row["title"],
            description=row["description"],
            template_session_id=row["template_session_id"],
            material_title=row["material_title"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_org_assignment(self, row) -> OrganizationTaskAssignment:
        return OrganizationTaskAssignment(
            id=row["id"],
            task_id=row["task_id"],
            organization_id=row["organization_id"],
            user_id=row["user_id"],
            status=row["status"],
            session_id=row["session_id"],
            assigned_at=row["assigned_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )

    def _row_to_org_knowledge_item(self, row) -> OrganizationKnowledgeItem:
        return OrganizationKnowledgeItem(
            id=row["id"],
            organization_id=row["organization_id"],
            uploader_user_id=row["uploader_user_id"],
            title=row["title"],
            chunk_count=int(row["chunk_count"] or 0),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_api_config(self, row) -> ApiConfig:
        return ApiConfig(
            id=row["id"],
            provider=safe_api_provider_for_display(row["provider"]),
            base_url=row["base_url"],
            api_key_masked=mask_secret(decrypt_secret(row["api_key"], self.db_path or "")),
            model=row["model"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_speech_config(self, row) -> SpeechConfig:
        return SpeechConfig(
            id=row["id"],
            kind=validate_speech_config_kind(row["kind"]),
            provider=safe_speech_provider_for_display(row["provider"]),
            base_url=row["base_url"],
            api_key_masked=mask_secret(decrypt_secret(row["api_key"], self.db_path or "")),
            model=row["model"],
            path=row["path"],
            is_active=bool(row["is_active"]),
            voice=row["voice"] or None,
            language=row["language"] or None,
            response_format=row["response_format"] or None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_parse_job(self, row) -> ParseJob:
        return ParseJob(
            id=row["id"],
            user_id=row["user_id"],
            title=row["title"],
            status=row["status"],
            progress=row["progress"],
            message=row["message"],
            session_id=row["session_id"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_audit_log(self, row) -> AuditLogEntry:
        return AuditLogEntry(
            id=row["id"],
            actor_user_id=row["actor_user_id"],
            actor_username=row["actor_username"],
            action=row["action"],
            target_type=row["target_type"],
            target_id=row["target_id"],
            detail=row["detail"],
            created_at=row["created_at"],
        )

    def _row_to_research_experiment_record(self, row) -> ResearchExperimentRecord:
        return ResearchExperimentRecord(
            id=row["id"],
            study_id=row["study_id"],
            participant_code=row["participant_code"],
            group_label=row["group_label"],
            material_label=row["material_label"],
            pretest_score=row["pretest_score"],
            posttest_score=row["posttest_score"],
            delayed_score=row["delayed_score"],
            system_feynman_score=row["system_feynman_score"],
            human_score=row["human_score"],
            learning_minutes=row["learning_minutes"],
            cognitive_load=row["cognitive_load"],
            notes=row["notes"],
            imported_at=row["imported_at"],
            updated_at=row["updated_at"],
        )


def mask_secret(value: str) -> str:
    if not value:
        return ""
    return f"已保存（{len(value)} 字符）"


def safe_api_provider_for_display(provider: str) -> str:
    try:
        return validate_api_provider(provider)
    except ValueError:
        compact = "".join(char if char.isprintable() and not char.isspace() else "?" for char in str(provider))
        return f"invalid:{compact[:64] or 'unknown'}"


def safe_speech_provider_for_display(provider: str) -> str:
    compact = "".join(char if char.isprintable() and not char.isspace() else "?" for char in str(provider))
    return compact[:80] or "unknown"


def compact_session_for_storage(session: LearningSession) -> None:
    if len(session.messages) > MAX_SESSION_MESSAGES:
        session.messages = session.messages[-MAX_SESSION_MESSAGES:]
    if len(session.memories) > MAX_SESSION_MEMORIES:
        session.memories = session.memories[-MAX_SESSION_MEMORIES:]


def material_quality_summary(session: LearningSession) -> MaterialQualitySummary:
    node_count = len(session.nodes)
    evidence_count = sum(1 for node in session.nodes if node.evidence.strip())
    dependency_edges = sum(len(node.deps) for node in session.nodes)
    average_complexity = (
        round(sum(max(1, min(5, node.complexity)) for node in session.nodes) / node_count, 2)
        if node_count
        else 0.0
    )
    return MaterialQualitySummary(
        session_id=session.id,
        title=session.material_title,
        node_count=node_count,
        evidence_coverage=round(evidence_count / node_count, 3) if node_count else 0.0,
        dependency_edges=dependency_edges,
        average_complexity=average_complexity,
        updated_at=session.updated_at,
    )


def organization_session_trace(session: LearningSession) -> OrganizationSessionTrace:
    return OrganizationSessionTrace(
        session=SessionSummary(
            id=session.id,
            material_title=session.material_title,
            active_node_id=session.active_node_id,
            mastered_count=sum(1 for node in session.nodes if node.status == "mastered"),
            node_count=len(session.nodes),
            updated_at=session.updated_at,
        ),
        nodes=session.nodes,
        messages=session.messages,
        node_profiles=session.node_profiles,
        feynman_questions=session.feynman_questions,
        feynman_answers=session.feynman_answers,
        feynman_followups=session.feynman_followups,
        feynman_assessments=session.feynman_assessments,
    )


def feynman_distribution(scores: list[int]) -> list[FeynmanDistributionBucket]:
    buckets = [
        ("0-49", 0, 49),
        ("50-69", 50, 69),
        ("70-84", 70, 84),
        ("85-100", 85, 100),
    ]
    return [
        FeynmanDistributionBucket(
            label=label,
            min_score=min_score,
            max_score=max_score,
            count=sum(1 for score in scores if min_score <= score <= max_score),
        )
        for label, min_score, max_score in buckets
    ]


def experiment_group_summaries(records: list[ResearchExperimentRecord]) -> list[ResearchExperimentGroupSummary]:
    grouped: dict[tuple[str, str], list[ResearchExperimentRecord]] = defaultdict(list)
    for record in records:
        grouped[(record.study_id, record.group_label)].append(record)
    summaries: list[ResearchExperimentGroupSummary] = []
    for (study_id, group_label), group_records in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1])):
        pretest_average = average_optional(record.pretest_score for record in group_records)
        posttest_average = average_optional(record.posttest_score for record in group_records)
        delayed_average = average_optional(record.delayed_score for record in group_records)
        gains = [
            record.posttest_score - record.pretest_score
            for record in group_records
            if record.pretest_score is not None and record.posttest_score is not None
        ]
        retention_rates = [
            record.delayed_score / record.posttest_score
            for record in group_records
            if record.delayed_score is not None and record.posttest_score not in {None, 0}
        ]
        summaries.append(
            ResearchExperimentGroupSummary(
                study_id=study_id,
                group_label=group_label,
                participants=len({record.participant_code for record in group_records}),
                pretest_average=round_optional(pretest_average),
                posttest_average=round_optional(posttest_average),
                delayed_average=round_optional(delayed_average),
                average_gain=round_optional(average_optional(gains)),
                retention_rate=round_optional(average_optional(retention_rates), digits=3),
                learning_minutes_average=round_optional(average_optional(record.learning_minutes for record in group_records)),
                cognitive_load_average=round_optional(average_optional(record.cognitive_load for record in group_records)),
            )
        )
    return summaries[:24]


def score_agreement_summary(records: list[ResearchExperimentRecord]) -> ResearchScoreAgreement:
    pairs = [
        (float(record.system_feynman_score), float(record.human_score))
        for record in records
        if record.system_feynman_score is not None and record.human_score is not None
    ]
    if not pairs:
        return ResearchScoreAgreement(paired_count=0)
    system_scores = [pair[0] for pair in pairs]
    human_scores = [pair[1] for pair in pairs]
    gaps = [abs(system - human) for system, human in pairs]
    return ResearchScoreAgreement(
        paired_count=len(pairs),
        correlation=round_optional(pearson_correlation(system_scores, human_scores), digits=3),
        mean_absolute_gap=round_optional(average_optional(gaps)),
        system_average=round_optional(average_optional(system_scores)),
        human_average=round_optional(average_optional(human_scores)),
    )


def average_optional(values) -> float | None:
    actual = [float(value) for value in values if value is not None]
    if not actual:
        return None
    return sum(actual) / len(actual)


def round_optional(value: float | None, digits: int = 1) -> float | None:
    return None if value is None else round(value, digits)


def pearson_correlation(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_denominator = sum((x - left_mean) ** 2 for x in left) ** 0.5
    right_denominator = sum((y - right_mean) ** 2 for y in right) ** 0.5
    denominator = left_denominator * right_denominator
    if denominator == 0:
        return None
    return numerator / denominator


def clamp_score(value: object) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


def stable_sag_id(*parts: str) -> str:
    raw = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def bounded_int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def token_is_expired(expires_at: str) -> bool:
    try:
        expires = datetime.fromisoformat(str(expires_at))
    except ValueError:
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return datetime.now(UTC) > expires


def seconds_since(iso_value) -> float:
    value = iso_value if hasattr(iso_value, "tzinfo") else datetime.fromisoformat(str(iso_value))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return (datetime.now(UTC) - value).total_seconds()
