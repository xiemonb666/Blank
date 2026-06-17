from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


Persona = Literal["plain", "vivid", "academic"]
NodeStatus = Literal["mastered", "active", "available", "locked"]
MessageRole = Literal["mentor", "learner"]
UserRole = Literal["admin", "learner"]
ApiProvider = Literal["openai", "vllm", "ollama", "custom"]
ParseSource = Literal["ai", "local"]
ParseJobStatus = Literal["queued", "running", "completed", "failed"]
ChallengeStage = Literal["warmup", "mechanism", "transfer", "correction", "recap"]


class StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KnowledgeNode(BaseModel):
    id: str
    title: str
    summary: str
    evidence: str = ""
    complexity_reason: str = ""
    complexity: int = Field(ge=1, le=5)
    weight: float = Field(gt=0)
    status: NodeStatus
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    deps: list[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: MessageRole
    text: str
    node_id: str | None = None
    thinking: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class DiagnosticItem(BaseModel):
    label: str
    value: int = Field(ge=0, le=100)
    note: str


class DimensionScore(BaseModel):
    stage: ChallengeStage
    label: str
    value: int = Field(ge=0, le=100)
    note: str


class NodeLearningProfile(BaseModel):
    node_id: str
    stage: ChallengeStage = "warmup"
    dimension_scores: dict[ChallengeStage, int] = Field(default_factory=dict)
    weak_points: list[str] = Field(default_factory=list)
    streak: int = Field(default=0, ge=0)
    failures: int = Field(default=0, ge=0)
    confusion_requests: int = Field(default=0, ge=0)
    confusion_resolved: int = Field(default=0, ge=0)
    confusion_unresolved: int = Field(default=0, ge=0)
    last_challenge: str = ""
    next_challenge: str = ""
    badge: str = ""
    updated_at: datetime = Field(default_factory=utc_now)


class FeynmanQuestion(BaseModel):
    id: str
    label: str
    question: str
    focus: str
    difficulty: int = Field(ge=1, le=5)
    stage: ChallengeStage = "warmup"
    follow_up_of: str | None = None


class FeynmanAnswer(BaseModel):
    question_id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    question: str = Field(min_length=1, max_length=600)
    answer: str = Field(min_length=1, max_length=2000)
    focus: str | None = Field(default=None, max_length=260)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    stage: ChallengeStage | None = None
    follow_up_of: str | None = Field(default=None, max_length=80)


class FeynmanFollowUpState(BaseModel):
    needed: bool
    reason: str = Field(default="", max_length=220)
    question_id: str | None = Field(default=None, max_length=80)


class QuestionDiagnosticItem(BaseModel):
    question_id: str
    label: str
    value: int = Field(ge=0, le=100)
    note: str
    stage: ChallengeStage = "warmup"


class FeynmanAssessmentRecord(BaseModel):
    diagnostics: list[DiagnosticItem] = Field(default_factory=list)
    question_diagnostics: list[QuestionDiagnosticItem] = Field(default_factory=list)
    dimension_scores: list[DimensionScore] = Field(default_factory=list)
    passed: bool = False
    mastery_state: Literal["not_passed", "passed_next_available", "passed_path_complete", "passed_waiting_prerequisite"] = "not_passed"
    next_reason: str = ""
    updated_at: datetime = Field(default_factory=utc_now)


class MemoryEntry(BaseModel):
    id: str
    kind: Literal["fact", "cognitive", "session", "preference", "long_term"]
    scope: Literal["task", "node", "long_term"] = "task"
    node_id: str | None = None
    retention: Literal["short", "medium", "long"] = "short"
    importance: int = Field(default=1, ge=1, le=5)
    title: str
    body: str
    reason: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class LearningSession(BaseModel):
    id: str
    user_id: str
    material_title: str
    material_context: str = ""
    nodes: list[KnowledgeNode]
    active_node_id: str
    persona: Persona = "plain"
    messages: list[ChatMessage]
    memories: list[MemoryEntry] = Field(default_factory=list)
    node_profiles: dict[str, NodeLearningProfile] = Field(default_factory=dict)
    feynman_questions: dict[str, list[FeynmanQuestion]] = Field(default_factory=dict)
    feynman_answers: dict[str, dict[str, FeynmanAnswer]] = Field(default_factory=dict)
    feynman_followups: dict[str, dict[str, FeynmanFollowUpState]] = Field(default_factory=dict)
    feynman_assessments: dict[str, FeynmanAssessmentRecord] = Field(default_factory=dict)
    parse_progress: int = Field(ge=0, le=100, default=100)
    parse_source: ParseSource = "local"
    parse_provider: str | None = None
    parse_model: str | None = None
    parse_message: str = "知识节点已生成"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class LearningSessionPublic(BaseModel):
    id: str
    material_title: str
    nodes: list[KnowledgeNode]
    active_node_id: str
    persona: Persona = "plain"
    messages: list[ChatMessage]
    active_messages: list[ChatMessage] = Field(default_factory=list)
    message_counts: dict[str, int] = Field(default_factory=dict)
    memories: list[MemoryEntry] = Field(default_factory=list)
    node_profiles: dict[str, NodeLearningProfile] = Field(default_factory=dict)
    feynman_questions: dict[str, list[FeynmanQuestion]] = Field(default_factory=dict)
    feynman_answers: dict[str, dict[str, FeynmanAnswer]] = Field(default_factory=dict)
    feynman_followups: dict[str, dict[str, FeynmanFollowUpState]] = Field(default_factory=dict)
    feynman_assessments: dict[str, FeynmanAssessmentRecord] = Field(default_factory=dict)
    parse_progress: int = Field(ge=0, le=100, default=100)
    parse_source: ParseSource = "local"
    parse_provider: str | None = None
    parse_model: str | None = None
    parse_message: str = "知识节点已生成"
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_session(cls, session: LearningSession, include_model_metadata: bool = False) -> "LearningSessionPublic":
        payload = session.model_dump(exclude={"user_id", "material_context"})
        active_messages = [message for message in session.messages if message.node_id == session.active_node_id]
        node_profiles = dict(session.node_profiles)
        for node in session.nodes:
            node_profiles.setdefault(node.id, NodeLearningProfile(node_id=node.id))
        payload["messages"] = active_messages
        payload["active_messages"] = active_messages
        payload["node_profiles"] = node_profiles
        payload["message_counts"] = {
            node.id: sum(1 for message in session.messages if message.node_id == node.id)
            for node in session.nodes
        }
        payload["feynman_questions"] = session.feynman_questions
        payload["feynman_answers"] = session.feynman_answers
        payload["feynman_followups"] = session.feynman_followups
        payload["feynman_assessments"] = session.feynman_assessments
        if not include_model_metadata:
            payload["parse_provider"] = None
            payload["parse_model"] = None
        return cls.model_validate(payload)


class SessionSummary(BaseModel):
    id: str
    material_title: str
    active_node_id: str
    mastered_count: int
    node_count: int
    updated_at: datetime


class ResearchMetric(BaseModel):
    label: str
    value: float
    unit: str = ""
    note: str = ""


class WeakPointSummary(BaseModel):
    label: str
    count: int = Field(ge=0)
    average_score: float = Field(ge=0, le=100)


class FeynmanDistributionBucket(BaseModel):
    label: str
    min_score: int = Field(ge=0, le=100)
    max_score: int = Field(ge=0, le=100)
    count: int = Field(ge=0)


class MaterialQualitySummary(BaseModel):
    session_id: str
    title: str
    node_count: int = Field(ge=0)
    evidence_coverage: float = Field(ge=0, le=1)
    dependency_edges: int = Field(ge=0)
    average_complexity: float = Field(ge=0, le=5)
    updated_at: datetime


class MemoryCategorySummary(BaseModel):
    category: str
    count: int = Field(ge=0)
    long_term_count: int = Field(ge=0)


class ResearchExperimentRecordInput(StrictRequestModel):
    id: str | None = Field(default=None, max_length=80)
    study_id: str = Field(default="default", min_length=1, max_length=80)
    participant_code: str = Field(min_length=1, max_length=80)
    group_label: str = Field(min_length=1, max_length=80)
    material_label: str = Field(default="", max_length=120)
    pretest_score: float | None = Field(default=None, ge=0, le=100)
    posttest_score: float | None = Field(default=None, ge=0, le=100)
    delayed_score: float | None = Field(default=None, ge=0, le=100)
    system_feynman_score: float | None = Field(default=None, ge=0, le=100)
    human_score: float | None = Field(default=None, ge=0, le=100)
    learning_minutes: float | None = Field(default=None, ge=0, le=10000)
    cognitive_load: float | None = Field(default=None, ge=0, le=10)
    notes: str = Field(default="", max_length=240)


class ResearchExperimentRecord(BaseModel):
    id: str
    study_id: str
    participant_code: str
    group_label: str
    material_label: str = ""
    pretest_score: float | None = None
    posttest_score: float | None = None
    delayed_score: float | None = None
    system_feynman_score: float | None = None
    human_score: float | None = None
    learning_minutes: float | None = None
    cognitive_load: float | None = None
    notes: str = ""
    imported_at: datetime
    updated_at: datetime


class ResearchExperimentImportRequest(StrictRequestModel):
    records: list[ResearchExperimentRecordInput] = Field(min_length=1, max_length=500)


class ResearchExperimentImportResponse(BaseModel):
    imported_count: int = Field(ge=0)
    records: list[ResearchExperimentRecord] = Field(default_factory=list)


class ResearchExperimentGroupSummary(BaseModel):
    study_id: str
    group_label: str
    participants: int = Field(ge=0)
    pretest_average: float | None = None
    posttest_average: float | None = None
    delayed_average: float | None = None
    average_gain: float | None = None
    retention_rate: float | None = None
    learning_minutes_average: float | None = None
    cognitive_load_average: float | None = None


class ResearchScoreAgreement(BaseModel):
    paired_count: int = Field(ge=0)
    correlation: float | None = None
    mean_absolute_gap: float | None = None
    system_average: float | None = None
    human_average: float | None = None


class ResearchExperimentExportResponse(BaseModel):
    generated_at: datetime
    records: list[ResearchExperimentRecord] = Field(default_factory=list)


class ResearchBlindReviewAnswer(BaseModel):
    sample_id: str
    session_id: str
    node_id: str
    node_title: str
    question_id: str
    question_label: str
    question: str
    answer: str
    system_score: int | None = Field(default=None, ge=0, le=100)
    system_note: str = ""
    updated_at: datetime


class ResearchBlindReviewExportResponse(BaseModel):
    generated_at: datetime
    answers: list[ResearchBlindReviewAnswer] = Field(default_factory=list)


class ResearchDashboardResponse(BaseModel):
    generated_at: datetime
    metrics: list[ResearchMetric] = Field(default_factory=list)
    weak_points: list[WeakPointSummary] = Field(default_factory=list)
    feynman_distribution: list[FeynmanDistributionBucket] = Field(default_factory=list)
    common_misconceptions: list[WeakPointSummary] = Field(default_factory=list)
    material_quality: list[MaterialQualitySummary] = Field(default_factory=list)
    memory_categories: list[MemoryCategorySummary] = Field(default_factory=list)
    experiment_summaries: list[ResearchExperimentGroupSummary] = Field(default_factory=list)
    score_agreement: ResearchScoreAgreement = Field(default_factory=lambda: ResearchScoreAgreement(paired_count=0))
    experiment_records: list[ResearchExperimentRecord] = Field(default_factory=list)


class UserPublic(BaseModel):
    id: str
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime
    total_tokens: int = 0
    today_tokens: int = 0


class TokenUsageRecord(BaseModel):
    id: str
    user_id: str = ""
    session_id: str | None = None
    source: str
    provider: str = ""
    model: str = ""
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=utc_now)


class AuditLogEntry(BaseModel):
    id: str
    actor_user_id: str | None = None
    actor_username: str | None = None
    action: str
    target_type: str
    target_id: str | None = None
    detail: str = ""
    created_at: datetime


class UserCreateRequest(StrictRequestModel):
    username: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9_\u4e00-\u9fff]+$")
    password: str = Field(min_length=8, max_length=128)
    admin_bootstrap_key: str | None = Field(default=None, max_length=256)
    remember_me: bool = False


class LoginRequest(StrictRequestModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    remember_me: bool = False


class ReauthRequest(StrictRequestModel):
    password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    token: str = ""
    user: UserPublic


class UserUpdateRequest(StrictRequestModel):
    role: UserRole | None = None
    is_active: bool | None = None


class SessionCreateRequest(StrictRequestModel):
    title: str = Field(default="未命名材料", min_length=1, max_length=120)
    content: str = Field(default="", max_length=20000)


class SessionCreateResponse(BaseModel):
    session: LearningSessionPublic


class ParseJob(BaseModel):
    id: str
    user_id: str
    title: str
    status: ParseJobStatus
    progress: int = Field(ge=0, le=100)
    message: str
    session_id: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class ParseJobPublic(BaseModel):
    id: str
    title: str
    status: ParseJobStatus
    progress: int = Field(ge=0, le=100)
    message: str
    session_id: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_job(cls, job: ParseJob) -> "ParseJobPublic":
        return cls.model_validate(job.model_dump(exclude={"user_id"}))


class ParseJobCreateResponse(BaseModel):
    job: ParseJobPublic


class ParseJobStatusResponse(BaseModel):
    job: ParseJobPublic
    session: LearningSessionPublic | None = None


class ChatRequest(StrictRequestModel):
    node_id: str
    persona: Persona
    message: str = Field(min_length=1, max_length=2000)
    failure_count: int = Field(default=0, ge=0, le=10)
    preserve_persona: bool = False
    confusion_event: bool = False
    starter_event: bool = False


class ChatResponse(BaseModel):
    messages: list[ChatMessage]
    failure_count: int
    downgraded: bool
    node_profiles: dict[str, NodeLearningProfile] = Field(default_factory=dict)
    chat_source: ParseSource = "local"
    chat_provider: str | None = None
    chat_model: str | None = None
    chat_message: str = "导师回复已生成"


class PersonaRequest(StrictRequestModel):
    persona: Persona


class NodeSelectRequest(StrictRequestModel):
    node_id: str


class FeynmanQuestionResponse(BaseModel):
    questions: list[FeynmanQuestion]
    answers: dict[str, FeynmanAnswer] = Field(default_factory=dict)
    reused: bool = False


class FeynmanFollowUpRequest(StrictRequestModel):
    node_id: str
    answer: FeynmanAnswer


class FeynmanFollowUpResponse(BaseModel):
    needed: bool
    reason: str = ""
    question: FeynmanQuestion | None = None
    questions: list[FeynmanQuestion] = Field(default_factory=list)
    answers: dict[str, FeynmanAnswer] = Field(default_factory=dict)


class FeynmanAnswerSaveRequest(StrictRequestModel):
    node_id: str
    answer: FeynmanAnswer


class FeynmanAnswerSaveResponse(BaseModel):
    questions: list[FeynmanQuestion] = Field(default_factory=list)
    answers: dict[str, FeynmanAnswer] = Field(default_factory=dict)


class FeynmanRequest(StrictRequestModel):
    node_id: str
    explanation: str = Field(default="", max_length=8000)
    answers: list[FeynmanAnswer] = Field(default_factory=list, max_length=8)


class FeynmanResponse(BaseModel):
    diagnostics: list[DiagnosticItem]
    question_diagnostics: list[QuestionDiagnosticItem] = Field(default_factory=list)
    dimension_scores: list[DimensionScore] = Field(default_factory=list)
    nodes: list[KnowledgeNode]
    node_profiles: dict[str, NodeLearningProfile] = Field(default_factory=dict)
    feynman_questions: dict[str, list[FeynmanQuestion]] = Field(default_factory=dict)
    feynman_answers: dict[str, dict[str, FeynmanAnswer]] = Field(default_factory=dict)
    feynman_assessments: dict[str, FeynmanAssessmentRecord] = Field(default_factory=dict)
    next_node: KnowledgeNode | None
    memory: MemoryEntry
    passed: bool
    mastery_state: Literal["not_passed", "passed_next_available", "passed_path_complete", "passed_waiting_prerequisite"]
    next_reason: str


class ApiConfig(BaseModel):
    id: str
    provider: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=500)
    api_key_masked: str
    model: str = Field(default="", max_length=120)
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ApiConfigCreateRequest(StrictRequestModel):
    provider: ApiProvider
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=1000)
    model: str = Field(default="", max_length=120)
    is_active: bool = True


class ApiConfigUpdateRequest(StrictRequestModel):
    provider: ApiProvider | None = None
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    api_key: str | None = Field(default=None, max_length=1000)
    model: str | None = Field(default=None, max_length=120)
    is_active: bool | None = None


class HealthResponse(BaseModel):
    ok: bool
    service: str
