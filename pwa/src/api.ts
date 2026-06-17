import type {
  ApiConfig,
  ApiProvider,
  DiagnosticItem,
  DimensionScore,
  FeynmanAnswer,
  FeynmanAssessmentRecord,
  FeynmanFollowUpState,
  FeynmanQuestion,
  KnowledgeNode,
  MemoryEntry,
  Message,
  NodeLearningProfile,
  Persona,
  QuestionDiagnosticItem,
  ResearchBlindReviewExport,
  ResearchDashboard,
  ResearchExperimentExport,
  ResearchExperimentImportResponse,
  ResearchExperimentRecordInput,
  User,
  UserRole,
} from "./types";

export const API_BASE = resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL);
const CSRF_COOKIE_NAME = "__Host-blank_csrf";
const DEV_CSRF_COOKIE_NAME = "blank_csrf";
const CSRF_PROTECTED_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function resolveApiBaseUrl(configured?: string) {
  const fallback =
    typeof window === "undefined"
      ? "http://127.0.0.1:8000"
      : `${window.location.protocol}//${window.location.hostname}:8000`;
  const raw = (configured || fallback).trim();
  if (!raw) {
    throw new Error("API 地址不能为空。");
  }
  const base = new URL(raw, typeof window === "undefined" ? "http://127.0.0.1" : window.location.origin);
  const host = base.hostname.toLowerCase();
  const isLocal = host === "localhost" || host === "127.0.0.1" || host === "::1";
  if (base.protocol !== "https:" && !(base.protocol === "http:" && isLocal)) {
    throw new Error("API 地址必须使用 HTTPS，本地开发仅允许 localhost/127.0.0.1 HTTP。");
  }
  base.pathname = base.pathname.replace(/\/+$/, "");
  base.search = "";
  base.hash = "";
  return base.toString().replace(/\/$/, "");
}

export interface LearningSession {
  id: string;
  material_title: string;
  nodes: KnowledgeNode[];
  active_node_id: string;
  persona: Persona;
  messages: Message[];
  active_messages: Message[];
  message_counts: Record<string, number>;
  memories: MemoryEntry[];
  node_profiles: Record<string, NodeLearningProfile>;
  feynman_questions: Record<string, FeynmanQuestion[]>;
  feynman_answers: Record<string, Record<string, FeynmanAnswer>>;
  feynman_followups?: Record<string, Record<string, FeynmanFollowUpState>>;
  feynman_assessments?: Record<string, FeynmanAssessmentRecord>;
  parse_progress: number;
  parse_source: "ai" | "local";
  parse_provider: string | null;
  parse_model: string | null;
  parse_message: string;
  created_at: string;
  updated_at: string;
}

export interface SessionSummary {
  id: string;
  material_title: string;
  active_node_id: string;
  mastered_count: number;
  node_count: number;
  updated_at: string;
}

export interface ParseJob {
  id: string;
  title: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  message: string;
  session_id: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ParseJobResponse {
  job: ParseJob;
}

export interface ParseJobStatusResponse {
  job: ParseJob;
  session: LearningSession | null;
}

export interface ChatResponse {
  messages: Message[];
  failure_count: number;
  downgraded: boolean;
  node_profiles: Record<string, NodeLearningProfile>;
  chat_source: "ai" | "local";
  chat_provider: string | null;
  chat_model: string | null;
  chat_message: string;
}

export type ChatStreamEvent =
  | {
      type: "thinking";
      thinking: string;
      failure_count: number;
      downgraded: boolean;
    }
  | { type: "thinking_delta"; text: string }
  | { type: "delta"; text: string }
  | {
      type: "done";
      messages: Message[];
      memories?: MemoryEntry[];
      node_profiles?: Record<string, NodeLearningProfile>;
      failure_count: number;
      downgraded: boolean;
    }
  | { type: "error"; error: string };

export type V2ChatStreamEvent =
  | { type: "status"; agent: string; message: string; detail?: string }
  | { type: "thought"; content: string }
  | { type: "message"; content: string }
  | { type: "feynman_result"; data: unknown; feedback?: string }
  | { type: "done"; messages?: Message[]; node_profiles?: Record<string, NodeLearningProfile> }
  | { type: "error"; error: string };

export interface FeynmanResponse {
  diagnostics: DiagnosticItem[];
  question_diagnostics: QuestionDiagnosticItem[];
  dimension_scores: DimensionScore[];
  nodes: KnowledgeNode[];
  node_profiles: Record<string, NodeLearningProfile>;
  feynman_questions: Record<string, FeynmanQuestion[]>;
  feynman_answers: Record<string, Record<string, FeynmanAnswer>>;
  feynman_assessments?: Record<string, FeynmanAssessmentRecord>;
  next_node: KnowledgeNode | null;
  memory: MemoryEntry;
  passed: boolean;
  mastery_state: "not_passed" | "passed_next_available" | "passed_path_complete" | "passed_waiting_prerequisite";
  next_reason: string;
}

export interface FeynmanQuestionResponse {
  questions: FeynmanQuestion[];
  answers: Record<string, FeynmanAnswer>;
  reused: boolean;
}

export interface FeynmanFollowUpResponse {
  needed: boolean;
  reason: string;
  question: FeynmanQuestion | null;
  questions: FeynmanQuestion[];
  answers: Record<string, FeynmanAnswer>;
}

export interface FeynmanAnswerSaveResponse {
  questions: FeynmanQuestion[];
  answers: Record<string, FeynmanAnswer>;
}

export interface AuthResponse {
  user: User;
}

export interface ApiConfigInput {
  provider: ApiProvider;
  base_url: string;
  api_key: string;
  model: string;
  is_active: boolean;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...csrfHeaderFor(method),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const detail = await readError(response);
    throw new Error(detail);
  }

  return response.json() as Promise<T>;
}

export function csrfHeaderFor(method: string): Record<string, string> {
  if (!CSRF_PROTECTED_METHODS.has(method)) {
    return {};
  }
  const token = readCookie(CSRF_COOKIE_NAME) || readCookie(DEV_CSRF_COOKIE_NAME);
  return token ? { "X-CSRF-Token": token } : {};
}

function readCookie(name: string): string {
  if (typeof document === "undefined") {
    return "";
  }
  const encodedName = `${encodeURIComponent(name)}=`;
  const value = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(encodedName));
  return value ? decodeURIComponent(value.slice(encodedName.length)) : "";
}

async function readError(response: Response) {
  try {
    const payload = (await response.json()) as {
      detail?: string | { message?: string; job_id?: string } | Array<{ msg?: string; loc?: string[] }>;
    };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (payload.detail && !Array.isArray(payload.detail) && typeof payload.detail === "object") {
      return payload.detail.message ?? `请求失败：${response.status}`;
    }
    if (Array.isArray(payload.detail)) {
      return payload.detail.map(formatValidationError).join("；");
    }
    return `请求失败：${response.status}`;
  } catch {
    return `请求失败：${response.status}`;
  }
}

function formatValidationError(error: { msg?: string; loc?: string[] }) {
  const field = error.loc?.[error.loc.length - 1];
  const label = field === "username" ? "用户名" : field === "password" ? "密码" : field ?? "字段";
  if (error.msg?.includes("at least 2")) return `${label}至少 2 个字符`;
  if (error.msg?.includes("at least 8")) return `${label}至少 8 个字符`;
  if (error.msg?.includes("pattern")) return `${label}只能包含中文、字母、数字或下划线`;
  return `${label}${error.msg ? `：${error.msg}` : "格式不正确"}`;
}

export function register(username: string, password: string, rememberMe: boolean = true) {
  return request<AuthResponse>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password, remember_me: rememberMe }),
  });
}

export function login(username: string, password: string, rememberMe: boolean = true) {
  return request<AuthResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password, remember_me: rememberMe }),
  });
}

export function getMe() {
  return request<User>("/api/me");
}

export function logout() {
  return request<{ ok: boolean }>(
    "/api/auth/logout",
    {
      method: "POST",
    },
  );
}

export function reauthenticate(password: string) {
  return request<User>(
    "/api/auth/reauth",
    {
      method: "POST",
      body: JSON.stringify({ password }),
    },
  );
}

export function createSession(title: string, content: string) {
  return request<{ session: LearningSession }>(
    "/api/sessions",
    {
      method: "POST",
      body: JSON.stringify({ title, content }),
    },
  );
}

export function createParseJob(title: string, content: string) {
  return request<ParseJobResponse>(
    "/api/parse-jobs",
    {
      method: "POST",
      body: JSON.stringify({ title, content }),
    },
  );
}

export function uploadParseJob(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return request<ParseJobResponse>(
    "/api/parse-jobs/upload",
    {
      method: "POST",
      body: formData,
    },
  );
}

export function getParseJob(jobId: string) {
  return request<ParseJobStatusResponse>(`/api/parse-jobs/${jobId}`);
}

export function listSessions() {
  return request<SessionSummary[]>("/api/sessions");
}

export function getSession(sessionId: string) {
  return request<LearningSession>(`/api/sessions/${sessionId}`);
}

export function deleteSession(sessionId: string) {
  return request<{ ok: boolean }>(
    `/api/sessions/${sessionId}`,
    {
      method: "DELETE",
    },
  );
}

export function selectNode(sessionId: string, nodeId: string) {
  return request<LearningSession>(
    `/api/sessions/${sessionId}/select-node`,
    {
      method: "POST",
      body: JSON.stringify({ node_id: nodeId }),
    },
  );
}

export function updateSessionPersona(sessionId: string, persona: Persona) {
  return request<LearningSession>(
    `/api/sessions/${sessionId}/persona`,
    {
      method: "POST",
      body: JSON.stringify({ persona }),
    },
  );
}

export function sendChatMessage(
  sessionId: string,
  nodeId: string,
  persona: Persona,
  message: string,
  failureCount: number,
  options: { preservePersona?: boolean; confusionEvent?: boolean; starterEvent?: boolean } = {},
) {
  return request<ChatResponse>(
    `/api/sessions/${sessionId}/chat`,
    {
      method: "POST",
      body: JSON.stringify({
        node_id: nodeId,
        persona,
        message,
        failure_count: failureCount,
        preserve_persona: options.preservePersona ?? false,
        confusion_event: options.confusionEvent ?? false,
        starter_event: options.starterEvent ?? false,
      }),
    },
  );
}

export async function streamChatMessage(
  sessionId: string,
  nodeId: string,
  persona: Persona,
  message: string,
  failureCount: number,
  onEvent: (event: ChatStreamEvent) => void,
  options: { preservePersona?: boolean; confusionEvent?: boolean; starterEvent?: boolean } = {},
) {
  const response = await fetch(`${API_BASE}/api/sessions/${sessionId}/chat/stream`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...csrfHeaderFor("POST"),
    },
    body: JSON.stringify({
      node_id: nodeId,
      persona,
      message,
      failure_count: failureCount,
      preserve_persona: options.preservePersona ?? false,
      confusion_event: options.confusionEvent ?? false,
      starter_event: options.starterEvent ?? false,
    }),
  });

  if (!response.ok || !response.body) {
    throw new Error(await readError(response));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      onEvent(JSON.parse(trimmed) as ChatStreamEvent);
    }
  }
  const tail = buffer.trim();
  if (tail) {
    onEvent(JSON.parse(tail) as ChatStreamEvent);
  }
}

export function getFeynmanQuestions(sessionId: string, nodeId: string) {
  return request<FeynmanQuestionResponse>(
    `/api/sessions/${sessionId}/feynman/questions`,
    {
      method: "POST",
      body: JSON.stringify({ node_id: nodeId }),
    },
  );
}

export function getFeynmanFollowUp(sessionId: string, nodeId: string, answer: FeynmanAnswer) {
  return request<FeynmanFollowUpResponse>(
    `/api/sessions/${sessionId}/feynman/follow-up`,
    {
      method: "POST",
      body: JSON.stringify({
        node_id: nodeId,
        answer,
      }),
    },
  );
}

export function saveFeynmanAnswer(sessionId: string, nodeId: string, answer: FeynmanAnswer) {
  return request<FeynmanAnswerSaveResponse>(
    `/api/sessions/${sessionId}/feynman/answer`,
    {
      method: "POST",
      body: JSON.stringify({
        node_id: nodeId,
        answer,
      }),
    },
  );
}

export function submitFeynman(sessionId: string, nodeId: string, answers: FeynmanAnswer[]) {
  return request<FeynmanResponse>(
    `/api/sessions/${sessionId}/feynman`,
    {
      method: "POST",
      body: JSON.stringify({
        node_id: nodeId,
        answers,
      }),
    },
  );
}

export async function streamChatMessageV2(
  sessionId: string,
  message: string,
  persona: string,
  onEvent: (event: V2ChatStreamEvent) => void,
) {
  const response = await fetch(`${API_BASE}/api/v2/chat/stream`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...csrfHeaderFor("POST"),
    },
    body: JSON.stringify({ session_id: sessionId, message, persona }),
  });

  if (!response.ok || !response.body) {
    throw new Error(await readError(response));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("data:")) continue;
      const jsonStr = trimmed.slice(5).trim();
      if (!jsonStr) continue;
      try {
        onEvent(JSON.parse(jsonStr) as V2ChatStreamEvent);
      } catch {
        // 忽略解析失败的行
      }
    }
  }
  const tail = buffer.trim();
  if (tail && tail.startsWith("data:")) {
    const jsonStr = tail.slice(5).trim();
    if (jsonStr) {
      try {
        onEvent(JSON.parse(jsonStr) as V2ChatStreamEvent);
      } catch {
        // 忽略
      }
    }
  }
}

export function listUsers() {
  return request<User[]>("/api/admin/users");
}

export function updateUser(userId: string, payload: { role?: UserRole; is_active?: boolean }) {
  return request<User>(
    `/api/admin/users/${userId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function listApiConfigs() {
  return request<ApiConfig[]>("/api/admin/api-configs");
}

export function getResearchDashboard() {
  return request<ResearchDashboard>("/api/admin/research-dashboard");
}

export function importResearchExperiments(records: ResearchExperimentRecordInput[]) {
  return request<ResearchExperimentImportResponse>(
    "/api/admin/research-experiments",
    {
      method: "POST",
      body: JSON.stringify({ records }),
    },
  );
}

export function exportResearchExperiments() {
  return request<ResearchExperimentExport>("/api/admin/research-experiments/export");
}

export function exportBlindReviewAnswers() {
  return request<ResearchBlindReviewExport>("/api/admin/research-blind-review/export");
}

export function createApiConfig(payload: ApiConfigInput) {
  return request<ApiConfig>(
    "/api/admin/api-configs",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function updateApiConfig(configId: string, payload: Partial<ApiConfigInput>) {
  return request<ApiConfig>(
    `/api/admin/api-configs/${configId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
  );
}

export function deleteApiConfig(configId: string) {
  return request<{ ok: boolean }>(
    `/api/admin/api-configs/${configId}`,
    {
      method: "DELETE",
    },
  );
}
