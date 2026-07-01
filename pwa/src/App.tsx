import { CSSProperties, ChangeEvent, DragEvent, FormEvent, useEffect, useRef, useState } from "react";
import { BarChart3, BookOpen, Building2, ClipboardList, Microscope, MessageSquare, Network, Settings, Sparkles, UploadCloud } from "lucide-react";
import { useV2Chat } from "./hooks/useV2Chat";
import { useFeynman } from "./hooks/useFeynman";
import { useParseJob } from "./hooks/useParseJob";
import { useLearningSession } from "./hooks/useLearningSession";
import { BlankShell, type BlankShellNavItem } from "./components/BlankShell";
import {
  AuthScreen,
  EmptyStage,
  SidePanel,
} from "./components/AppChrome";
import { AdminStage } from "./stages/AdminStage";
import { CanvasStage } from "./stages/CanvasStage";
import { EvidenceStage } from "./stages/EvidenceStage";
import { FeynmanStage } from "./stages/FeynmanStage";
import { FlowStage } from "./stages/FlowStage";
import { MapStage } from "./stages/MapStage";
import { MasteryStage } from "./stages/MasteryStage";
import { OrganizationStage } from "./stages/OrganizationStage";
import { ResearchStage } from "./stages/ResearchStage";
import { TasksStage } from "./stages/TasksStage";
import { AUTH_SESSION_STORAGE_KEY, CHAT_SUBMIT_COOLDOWN_MS, LEGACY_TOKEN_STORAGE_KEY } from "./app/constants";
import {
  UI_REVIEW_ADMIN_USERS,
  UI_REVIEW_AGENT_EVENTS,
  UI_REVIEW_ANSWER_MAP,
  UI_REVIEW_ANSWER_TEXT,
  UI_REVIEW_API_CONFIGS,
  UI_REVIEW_CANVAS_PARSING,
  UI_REVIEW_DIAGNOSTICS,
  UI_REVIEW_DIMENSION_SCORES,
  UI_REVIEW_EMPTY_EVIDENCE,
  UI_REVIEW_MESSAGE_COUNTS,
  UI_REVIEW_MESSAGES,
  UI_REVIEW_NODE_ID,
  UI_REVIEW_NODE_PROFILES,
  UI_REVIEW_NODES,
  UI_REVIEW_QUESTION_DIAGNOSTICS,
  UI_REVIEW_QUESTION_MAP,
  UI_REVIEW_QUESTIONS,
  UI_REVIEW_RESEARCH_DASHBOARD,
  UI_REVIEW_SESSION_ID,
  UI_REVIEW_SPEECH_CONFIGS,
  UI_REVIEW_STAGE,
  UI_REVIEW_USER,
} from "./app/uiReviewFixtures";
import {
  appendMessagesToThread,
  buildFeynmanAnswer,
  currentNodeMessages,
  replaceThreadMessages,
  resolveMessageCounts,
  resolveNodeProfiles,
  stageLabel,
  statusLabel,
  updateLatestMentorInThread,
} from "./app/sessionState";
import {
  AdminUserCreateInput,
  AdminUserUpdateInput,
  ApiConfigInput,
  SpeechConfigInput,
  createApiConfig,
  createSpeechConfig,
  createUser,
  createOrganizationTask,
  createParseJob,
  deleteApiConfig,
  deleteSpeechConfig,
  deleteOrganizationKnowledge,
  deleteSession,
  exportBlindReviewAnswers,
  exportOrganizationTrace,
  exportResearchExperiments,
  getSpeechCapabilities,
  getFeynmanQuestions,
  getOrganizationDashboard,
  getOrganizationMemberReport,
  getMe,
  getResearchDashboard,
  importResearchExperiments,
  getSession,
  LearningSession,
  listApiConfigs,
  listOrganizations,
  listSpeechConfigs,
  listMyTasks,
  listOrganizationKnowledge,
  listOrganizationMembers,
  listSessions,
  listUsers,
  login,
  logout as logoutSession,
  reauthenticate,
  register,
  saveFeynmanAnswer,
  selectNode as selectSessionNode,
  SessionSummary,
  streamChatMessage,
  submitFeynman,
  startMyTask,
  synthesizeSpeech,
  transcribeSpeech,
  updateApiConfig,
  updateSpeechConfig,
  updateMyAccount,
  updateSessionPersona,
  updateSessionTutorSettings,
  updateUser,
  uploadParseJob,
  uploadOrganizationKnowledge,
} from "./api";
import type {
  ApiConfig,
  FeynmanAnswer,
  FeynmanAssessmentRecord,
  FeynmanQuestion,
  KnowledgeNode,
  Persona,
  Organization,
  OrganizationDashboard,
  OrganizationKnowledgeItem,
  OrganizationMemberReport,
  OrganizationMemberSummary,
  OrganizationTaskAssignment,
  ResearchDashboard,
  SpeechCapabilities,
  SpeechConfig,
  Stage,
  TutorSettings,
  User,
  UserRole,
} from "./types";

const INITIAL_TUTOR_PROMPT =
  "学习者刚进入这个知识节点，还没有回答。请你先提出第一个苏格拉底式起始问题：问题必须具体、容易开口、只聚焦当前节点的一个核心点。";

function optionalTrimmed(value?: string) {
  const trimmed = (value ?? "").trim();
  return trimmed || undefined;
}

function normalizeAdminUserCreatePayload(payload: AdminUserCreateInput): AdminUserCreateInput {
  return {
    username: payload.username.trim(),
    password: payload.password,
    role: payload.role,
    is_active: payload.is_active ?? true,
    organization_name: optionalTrimmed(payload.organization_name),
    organization_code: optionalTrimmed(payload.organization_code),
  };
}

function normalizeAdminUserUpdatePayload(payload: AdminUserUpdateInput): AdminUserUpdateInput {
  return {
    role: payload.role,
    is_active: payload.is_active,
    organization_name: optionalTrimmed(payload.organization_name),
    organization_code: optionalTrimmed(payload.organization_code),
  };
}

function App() {
  const [token, setToken] = useState(() => {
    localStorage.removeItem(LEGACY_TOKEN_STORAGE_KEY);
    return UI_REVIEW_STAGE ? "ui-review-token" : localStorage.getItem(AUTH_SESSION_STORAGE_KEY) ?? "";
  });
  const [user, setUser] = useState<User | null>(() => (UI_REVIEW_STAGE ? UI_REVIEW_USER : null));
  const [stage, setStage] = useState<Stage>(UI_REVIEW_STAGE ?? "canvas");
  const initialMaterialTitle = UI_REVIEW_STAGE && UI_REVIEW_STAGE !== "canvas" ? "UI 审查样例：条件概率讲义" : UI_REVIEW_CANVAS_PARSING ? "正在解析：条件概率讲义.md" : "等待上传材料";
  const initialParseMeta = {
    source: (UI_REVIEW_STAGE && UI_REVIEW_STAGE !== "canvas" ? "ai" : "local") as "ai" | "local",
    provider: UI_REVIEW_STAGE && UI_REVIEW_STAGE !== "canvas" ? "ui-review" : null as string | null,
    model: UI_REVIEW_STAGE && UI_REVIEW_STAGE !== "canvas" ? "design-snapshot" : null as string | null,
    message: UI_REVIEW_STAGE && UI_REVIEW_STAGE !== "canvas"
      ? "开发审查样例，仅用于截图验证，不写入学习记录。"
      : UI_REVIEW_CANVAS_PARSING
        ? "正在切片材料并生成依赖图，解析完成前不能上传其他文档。"
        : "上传材料后开始解析",
  };
  const initialFeynmanAssessments: Record<string, FeynmanAssessmentRecord> =
    (UI_REVIEW_STAGE === "mastery" || UI_REVIEW_STAGE === "evidence") && !UI_REVIEW_EMPTY_EVIDENCE
      ? {
          [UI_REVIEW_NODE_ID]: {
            diagnostics: UI_REVIEW_DIAGNOSTICS,
            question_diagnostics: UI_REVIEW_QUESTION_DIAGNOSTICS,
            dimension_scores: UI_REVIEW_DIMENSION_SCORES,
            passed: false,
            mastery_state: "not_passed",
            next_reason: "最低项是反例纠错，请先补“条件概率倒置”这一点，再解锁下一节点。",
            updated_at: "2026-06-11T00:00:00Z",
          },
        }
      : {};
  const [feynmanAssessmentsByNodeId, setFeynmanAssessmentsByNodeId] =
    useState<Record<string, FeynmanAssessmentRecord>>(() => initialFeynmanAssessments);
  const [failureCount, setFailureCount] = useState(0);
  const [downgradedOverride, setDowngradedOverride] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState("");
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [adminUsers, setAdminUsers] = useState<User[]>(() => (UI_REVIEW_STAGE === "admin" ? UI_REVIEW_ADMIN_USERS : []));
  const [adminOrganizations, setAdminOrganizations] = useState<Organization[]>([]);
  const [apiConfigs, setApiConfigs] = useState<ApiConfig[]>(() => (UI_REVIEW_STAGE === "admin" ? UI_REVIEW_API_CONFIGS : []));
  const [speechConfigs, setSpeechConfigs] = useState<SpeechConfig[]>(() => (UI_REVIEW_STAGE === "admin" ? UI_REVIEW_SPEECH_CONFIGS : []));
  const [researchDashboard, setResearchDashboard] = useState<ResearchDashboard | null>(() =>
    UI_REVIEW_STAGE === "research" ? UI_REVIEW_RESEARCH_DASHBOARD : null,
  );
  const [speechCapabilities, setSpeechCapabilities] = useState<SpeechCapabilities>({
    asr_enabled: false,
    tts_enabled: false,
  });
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [researchImportDraft, setResearchImportDraft] = useState("");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authUsername, setAuthUsername] = useState("");
  const [authPassword, setAuthPassword] = useState("");
  const [authRegisterRole, setAuthRegisterRole] = useState<Exclude<UserRole, "admin">>("learner");
  const [authOrganizationName, setAuthOrganizationName] = useState("");
  const [authOrganizationCode, setAuthOrganizationCode] = useState("");
  const [showDefaultAdminNotice, setShowDefaultAdminNotice] = useState(false);
  const [accountUsernameDraft, setAccountUsernameDraft] = useState("");
  const [accountCurrentPassword, setAccountCurrentPassword] = useState("");
  const [accountNewPassword, setAccountNewPassword] = useState("");
  const [organizationDashboard, setOrganizationDashboard] = useState<OrganizationDashboard | null>(null);
  const [organizationMembers, setOrganizationMembers] = useState<OrganizationMemberSummary[]>([]);
  const [organizationKnowledge, setOrganizationKnowledge] = useState<OrganizationKnowledgeItem[]>([]);
  const [organizationReport, setOrganizationReport] = useState<OrganizationMemberReport | null>(null);
  const [organizationTaskTitle, setOrganizationTaskTitle] = useState("");
  const [organizationTaskDescription, setOrganizationTaskDescription] = useState("");
  const [organizationTaskContent, setOrganizationTaskContent] = useState("");
  const [organizationTaskTargetMode, setOrganizationTaskTargetMode] = useState<"all" | "selected">("all");
  const [organizationTaskMemberIds, setOrganizationTaskMemberIds] = useState<string[]>([]);
  const [myTasks, setMyTasks] = useState<OrganizationTaskAssignment[]>([]);
  const [topicDraft, setTopicDraft] = useState("");
  const [apiConfigForm, setApiConfigForm] = useState<ApiConfigInput>({
    provider: "openai",
    base_url: "https://api.openai.com/v1",
    api_key: "",
    model: UI_REVIEW_STAGE === "admin" ? "gpt-4.1-mini" : "",
    is_active: true,
  });
  const [speechConfigForm, setSpeechConfigForm] = useState<SpeechConfigInput>({
    kind: "asr",
    provider: "sensevoice-openai",
    base_url: "http://127.0.0.1:10098",
    api_key: "",
    model: "SenseVoiceSmall",
    path: "/v1/audio/transcriptions",
    is_active: true,
    voice: "",
    language: "zh",
    response_format: "",
  });
  const [lastChatSubmitAt, setLastChatSubmitAt] = useState(0);
  const lastChatSubmitAtRef = useRef(0);
  const introRequestedRef = useRef<Set<string>>(new Set());
  const speechAudioRef = useRef<HTMLAudioElement | null>(null);
  const speechUrlRef = useRef<string>("");

  const v2Chat = useV2Chat();
  const learningSession = useLearningSession({
    initialPersona: "plain",
    initialSessionId: UI_REVIEW_STAGE ? UI_REVIEW_SESSION_ID : null,
    initialMaterialTitle,
    initialNodes: UI_REVIEW_STAGE && UI_REVIEW_STAGE !== "canvas" ? UI_REVIEW_NODES : [],
    initialActiveNodeId: UI_REVIEW_STAGE && UI_REVIEW_STAGE !== "canvas" ? UI_REVIEW_NODE_ID : "",
    initialMessageThreads: UI_REVIEW_STAGE && UI_REVIEW_STAGE !== "canvas" ? UI_REVIEW_MESSAGES : {},
    initialMessageCountsByNodeId: UI_REVIEW_STAGE && UI_REVIEW_STAGE !== "canvas" ? UI_REVIEW_MESSAGE_COUNTS : {},
    initialNodeProfiles: UI_REVIEW_STAGE && UI_REVIEW_STAGE !== "canvas" ? UI_REVIEW_NODE_PROFILES : {},
  });
  const {
    persona,
    setPersona,
    tutorSettings,
    setTutorSettings,
    sessionId,
    setSessionId,
    materialTitle,
    setMaterialTitle,
    nodes,
    setNodes,
    activeNodeId,
    setActiveNodeId,
    messageThreads,
    setMessageThreads,
    setMessageCountsByNodeId,
    setDraftsByNodeId,
    memories,
    setMemories,
    nodeProfiles,
    setNodeProfiles,
    activeNode,
    activeProfile,
    activeNodeMessages,
    activeDraft,
    nodeMessageCounts,
    masteredCount,
    nextNode,
  } = learningSession;
  const parseJob = useParseJob({
    enabled: Boolean(token && user),
    initialProgress: UI_REVIEW_STAGE && UI_REVIEW_STAGE !== "canvas" ? 100 : UI_REVIEW_CANVAS_PARSING ? 54 : 0,
    initialMeta: initialParseMeta,
    initialIsParsing: UI_REVIEW_CANVAS_PARSING,
    onComplete: async (response) => {
      setMaterialTitle(response.job.title);
      if (response.session) {
        hydrateSession(response.session);
        await refreshSessions();
        setStage("map");
        return;
      }
      setError("解析任务已完成，但学习记录没有保存成功，请重新上传解析。");
      await refreshSessions();
    },
    onFailed: async (message) => {
      setError(message);
      await refreshSessions();
    },
    onError: setError,
  });
  const feynman = useFeynman({
    initialQuestionsByNodeId: UI_REVIEW_STAGE && UI_REVIEW_STAGE !== "canvas" ? UI_REVIEW_QUESTION_MAP : {},
    initialAnswersByNodeId: UI_REVIEW_STAGE && UI_REVIEW_STAGE !== "canvas" ? UI_REVIEW_ANSWER_MAP : {},
    initialQuestions: UI_REVIEW_STAGE && UI_REVIEW_STAGE !== "canvas" ? UI_REVIEW_QUESTIONS : [],
    initialAnswerTexts: UI_REVIEW_STAGE && UI_REVIEW_STAGE !== "canvas" ? UI_REVIEW_ANSWER_TEXT : {},
    initialStep: UI_REVIEW_STAGE && UI_REVIEW_STAGE !== "canvas" ? 1 : 0,
  });
  const feynmanQuestionsByNodeId = feynman.questionsByNodeId;
  const feynmanAnswersByNodeId = feynman.answersByNodeId;
  const feynmanQuestions = feynman.questions;
  const feynmanAnswers = feynman.answerTexts;
  const feynmanStep = feynman.currentIndex;
  const isFeynmanAdvancing = feynman.isAdvancing;
  const parseMeta = parseJob.parseMeta;
  const parseProgress = parseJob.parseProgress;
  const parseStatus = parseJob.parseStatus;
  const isParsing = parseJob.isParsing;
  const activeFeynmanAssessment = activeNode ? feynmanAssessmentsByNodeId[activeNode.id] : null;
  const activeDiagnostics = activeFeynmanAssessment?.diagnostics ?? [];
  const activeQuestionDiagnostics = activeFeynmanAssessment?.question_diagnostics ?? [];
  const activeDimensionScores = activeFeynmanAssessment?.dimension_scores ?? [];
  const activeMasteryPassed = activeFeynmanAssessment?.passed ?? false;
  const activeMasteryReason = activeFeynmanAssessment?.next_reason ?? "";
  const activeAgentTrace = activeNode ? v2Chat.traceForNode(activeNode.id) : null;

  const downgraded = downgradedOverride || (failureCount >= 2 && persona !== "plain");

  const hasSession = Boolean(sessionId && activeNode);
  const isAdminStage = stage === "admin" && user?.role === "admin";
  const isFocusStage = stage === "feynman" || stage === "mastery" || stage === "evidence" || stage === "research" || stage === "organization" || stage === "tasks";
  const needsActiveNode = stage === "map" || stage === "flow" || stage === "feynman" || stage === "mastery" || stage === "evidence";

  useEffect(() => {
    if (token && !user) {
      void restoreSession();
    }
  }, [token, user]);

  useEffect(() => {
    return () => {
      if (speechAudioRef.current) {
        speechAudioRef.current.pause();
        speechAudioRef.current = null;
      }
      if (speechUrlRef.current) {
        URL.revokeObjectURL(speechUrlRef.current);
        speechUrlRef.current = "";
      }
    };
  }, []);

  useEffect(() => {
    if (!lastChatSubmitAt) return;
    const remaining = CHAT_SUBMIT_COOLDOWN_MS - (Date.now() - lastChatSubmitAt);
    if (remaining <= 0) {
      lastChatSubmitAtRef.current = 0;
      setLastChatSubmitAt(0);
      return;
    }
    const timer = window.setTimeout(() => {
      lastChatSubmitAtRef.current = 0;
      setLastChatSubmitAt(0);
    }, remaining);
    return () => window.clearTimeout(timer);
  }, [lastChatSubmitAt]);

  useEffect(() => {
    if (UI_REVIEW_STAGE) return;
    if (stage !== "flow" || !sessionId || !activeNode) return;
    if (isBusy || isParsing || v2Chat.isStreaming) return;
    if (activeNodeMessages.length > 0) return;
    const key = `${sessionId}:${activeNode.id}`;
    if (introRequestedRef.current.has(key)) return;
    introRequestedRef.current.add(key);
    void sendLearningMessage(INITIAL_TUTOR_PROMPT, {
      preservePersona: true,
      starterEvent: true,
      skipCooldown: true,
    });
  }, [stage, sessionId, activeNode?.id, activeNodeMessages.length, isBusy, isParsing, v2Chat.isStreaming]);

  if (!token || !user) {
    return (
      <AuthScreen
        mode={authMode}
        username={authUsername}
        password={authPassword}
        registerRole={authRegisterRole}
        organizationName={authOrganizationName}
        organizationCode={authOrganizationCode}
        error={error}
        isBusy={isBusy}
        onModeChange={setAuthMode}
        onUsernameChange={setAuthUsername}
        onPasswordChange={setAuthPassword}
        onRegisterRoleChange={setAuthRegisterRole}
        onOrganizationNameChange={setAuthOrganizationName}
        onOrganizationCodeChange={setAuthOrganizationCode}
        onSubmit={handleAuthSubmit}
        onRestore={restoreSession}
      />
    );
  }

  async function handleMaterialUpload(event: ChangeEvent<HTMLInputElement>) {
    if (isBusy || isParsing) {
      event.target.value = "";
      setError("当前任务仍在处理中，请完成后再创建新的学习任务。");
      return;
    }
    const file = event.target.files?.[0];
    if (!file) return;
    await runBusy(async () => {
      const response = await uploadParseJob(file);
      beginParseJob(response.job);
    });
  }

  async function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    if (isBusy || isParsing) {
      setError("当前任务仍在处理中，请完成后再创建新的学习任务。");
      return;
    }
    const file = event.dataTransfer.files?.[0];
    if (file) {
      await runBusy(async () => {
        const response = await uploadParseJob(file);
        beginParseJob(response.job);
      });
      return;
    }
  }

  async function handleTopicSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isBusy || isParsing) {
      setError("当前任务仍在解析中，请完成后再创建新的学习任务。");
      return;
    }
    const topic = topicDraft.trim().replace(/\s+/g, " ");
    if (!topic) {
      setError("请先输入想学习的内容。");
      return;
    }
    if (topic.length < 2) {
      setError("学习主题太短，请再补充一点具体范围。");
      return;
    }
    const title = topic.length > 48 ? `想学：${topic.slice(0, 48)}...` : `想学：${topic}`;
    const content = [
      `用户想学习的主题：${topic}`,
      "",
      "请围绕这个主题生成适合学习闭环的知识路径：从基础概念、前置依赖、核心机制、典型例子、常见误区到迁移应用逐步展开。",
      "拆解时请优先保留可教学、可提问、可用费曼法验证的知识节点。",
    ].join("\n");

    await runBusy(async () => {
      const response = await createParseJob(title, content);
      beginParseJob(response.job);
      setTopicDraft("");
    });
  }

  async function selectNode(node: KnowledgeNode) {
    if (node.status === "locked") return;
    resetFeynmanState();
    if (sessionId) {
      await runBusy(async () => {
        const session = await selectSessionNode(sessionId, node.id);
        hydrateSession(session);
        setStage("flow");
      });
      return;
    }

    setActiveNodeId(node.id);
    setNodes((current) =>
      current.map((item) =>
        item.id === node.id && item.status === "available"
          ? { ...item, status: "active" }
          : item.status === "active" && item.id !== node.id
            ? { ...item, status: "available" }
            : item,
      ),
    );
    setStage("flow");
  }

  async function handleComposerSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitMessage();
  }

  async function submitMessage() {
    await sendLearningMessage(activeDraft.trim(), { restoreDraftOnError: true });
  }

  async function handleConfuse() {
    await sendLearningMessage(
      "我听不懂。请你按照我当前选择的讲解风格，主动把这个知识点换一种方式重新讲解，并且一步一步引导我回答。",
      {
        preservePersona: true,
        confusionEvent: true,
        failureCountOverride: Math.max(failureCount, 2),
      },
    );
  }

  async function sendLearningMessage(
    rawText: string,
    options: {
      preservePersona?: boolean;
      confusionEvent?: boolean;
      starterEvent?: boolean;
      failureCountOverride?: number;
      restoreDraftOnError?: boolean;
      skipCooldown?: boolean;
    } = {},
  ) {
    const text = rawText.trim();
    if (!text || isBusy) return;
    if (!sessionId || !activeNode) {
      setError("请先上传材料并选择一个知识节点。");
      return;
    }
    const now = Date.now();
    if (!options.skipCooldown && now - lastChatSubmitAtRef.current < CHAT_SUBMIT_COOLDOWN_MS) {
      setError("发送太频繁，请稍等再试。");
      return;
    }
    if (!options.skipCooldown) {
      lastChatSubmitAtRef.current = now;
      setLastChatSubmitAt(now);
    }

    const optimisticMessages = options.starterEvent
      ? [{ role: "mentor" as const, text: "", node_id: activeNode.id }]
      : [
          { role: "learner" as const, text, node_id: activeNode.id },
          { role: "mentor" as const, text: "", node_id: activeNode.id },
        ];

    setMessageThreads((current) =>
      appendMessagesToThread(current, activeNode.id, optimisticMessages),
    );
    setMessageCountsByNodeId((current) => ({
      ...current,
      [activeNode.id]: (current[activeNode.id] ?? messageThreads[activeNode.id]?.length ?? 0) + optimisticMessages.length,
    }));
    if (options.restoreDraftOnError) {
      setDraftsByNodeId((current) => ({ ...current, [activeNode.id]: "" }));
    }
    if (options.failureCountOverride !== undefined) {
      setFailureCount(options.failureCountOverride);
    }

    if (v2Chat.v2Enabled) {
      await runBusy(async () => {
        let streamError = "";
        try {
          await v2Chat.send(sessionId, activeNode.id, text, persona, {
            confusionEvent: options.confusionEvent,
            starterEvent: options.starterEvent,
            onMessageDelta: (delta) => {
              setMessageThreads((current) =>
                updateLatestMentorInThread(current, activeNode.id, (message) => ({
                  ...message,
                  text: message.text + delta,
                })),
              );
            },
            onThought: (thought) => {
              setMessageThreads((current) =>
                updateLatestMentorInThread(current, activeNode.id, (message) => ({
                  ...message,
                  thinking: (message.thinking ?? "") + thought,
                })),
              );
            },
            onError: (err) => {
              streamError = err;
            },
            onDone: (event) => {
              if (event.messages) {
                setMessageThreads((current) => replaceThreadMessages(current, activeNode.id, event.messages ?? []));
                setMessageCountsByNodeId((current) => ({ ...current, [activeNode.id]: event.messages?.length ?? 0 }));
              }
              if (event.node_profiles) {
                setNodeProfiles(event.node_profiles);
              }
            },
          });
          if (streamError) {
            throw new Error(streamError);
          }
        } catch (caught) {
          const message = caught instanceof Error ? caught.message : "导师回复失败，请检查 API 配置。";
          setMessageThreads((current) => {
            const next = updateLatestMentorInThread(current, activeNode.id, (item) => ({
              ...item,
              text: `发送失败：${message}`,
            }));
            return next === current
              ? appendMessagesToThread(current, activeNode.id, [
                  { role: "mentor", text: `发送失败：${message}`, node_id: activeNode.id },
                ])
              : next;
          });
          if (options.restoreDraftOnError) {
            setDraftsByNodeId((current) => ({ ...current, [activeNode.id]: text }));
          }
          if (options.starterEvent) {
            introRequestedRef.current.delete(`${sessionId}:${activeNode.id}`);
          }
          throw caught;
        }
      });
      return;
    }

    await runBusy(async () => {
      try {
        let streamError = "";
        await streamChatMessage(
          sessionId,
          activeNode.id,
          persona,
          text,
          options.failureCountOverride ?? failureCount,
          (event) => {
          if (event.type === "thinking") {
            setFailureCount(event.failure_count);
            setDowngradedOverride(event.downgraded);
            setMessageThreads((current) =>
              updateLatestMentorInThread(current, activeNode.id, (message) => ({ ...message, thinking: event.thinking })),
            );
            return;
          }
          if (event.type === "thinking_delta") {
            setMessageThreads((current) =>
              updateLatestMentorInThread(current, activeNode.id, (message) => ({
                ...message,
                thinking: `${message.thinking ?? ""}${event.text}`,
              })),
            );
            return;
          }
          if (event.type === "delta") {
            setMessageThreads((current) =>
              updateLatestMentorInThread(current, activeNode.id, (message) => ({
                ...message,
                text: `${message.text}${event.text}`,
              })),
            );
            return;
          }
          if (event.type === "done") {
            setMessageThreads((current) => replaceThreadMessages(current, activeNode.id, event.messages));
            setMessageCountsByNodeId((current) => ({ ...current, [activeNode.id]: event.messages.length }));
            if (event.memories) {
              setMemories(event.memories);
            }
            if (event.node_profiles) {
              setNodeProfiles(event.node_profiles);
            }
            setFailureCount(event.failure_count);
            setDowngradedOverride(event.downgraded);
            return;
          }
          if (event.type === "error") {
            streamError = event.error;
          }
        },
          {
            preservePersona: options.preservePersona,
            confusionEvent: options.confusionEvent,
            starterEvent: options.starterEvent,
          },
        );
        if (streamError) {
          throw new Error(streamError);
        }
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : "导师回复失败，请检查 API 配置。";
        setMessageThreads((current) => {
          const next = updateLatestMentorInThread(current, activeNode.id, (item) => ({
            ...item,
            text: `发送失败：${message}`,
          }));
          return next === current
            ? appendMessagesToThread(current, activeNode.id, [
                { role: "mentor", text: `发送失败：${message}`, node_id: activeNode.id },
              ])
            : next;
        });
        if (options.restoreDraftOnError) {
          setDraftsByNodeId((current) => ({ ...current, [activeNode.id]: text }));
        }
        if (options.starterEvent) {
          introRequestedRef.current.delete(`${sessionId}:${activeNode.id}`);
        }
        throw caught;
      }
    });
  }

  async function completeFeynman() {
    if (!sessionId || !activeNode) {
      setError("请先上传材料并选择一个知识节点。");
      return;
    }
    if (feynmanQuestions.length === 0) {
      setError("请先生成逐题验证问题。");
      return;
    }
    const answers = feynman.buildAnswersForNode(activeNode.id);
    const missing = answers.find((item) => !item.answer);
    if (missing) {
      setError(`请先回答「${missing.label}」。`);
      return;
    }
    await runBusy(async () => {
      const response = await submitFeynman(sessionId, activeNode.id, answers);
      applyFeynmanResult(response);
      await refreshSessions();
      setStage("mastery");
    });
  }

  function applyFeynmanResult(response: Awaited<ReturnType<typeof submitFeynman>>) {
    setNodes(response.nodes);
    setNodeProfiles(response.node_profiles ?? {});
    feynman.replaceCache(response.feynman_questions ?? {}, response.feynman_answers ?? {});
    setFeynmanAssessmentsByNodeId((current) => ({
      ...current,
      ...(response.feynman_assessments ?? {}),
    }));
    setMemories((current) => [...current, response.memory]);
  }

  async function enterFeynmanStage() {
    if (!sessionId || !activeNode) {
      setError("请先上传材料并选择一个知识节点。");
      return;
    }
    setStage("feynman");
    const cachedQuestions = feynmanQuestionsByNodeId[activeNode.id] ?? [];
    if (cachedQuestions.length > 0) {
      hydrateFeynmanNodeState(activeNode.id);
      return;
    }
    await runBusy(async () => {
      const response = await getFeynmanQuestions(sessionId, activeNode.id);
      syncFeynmanNodeState(activeNode.id, response.questions, response.answers ?? {}, 0);
    });
  }

  function answerCurrentFeynman(value: string) {
    feynman.answerCurrent(activeNodeId, value);
  }

  async function continueFeynmanStep() {
    if (!sessionId || !activeNode || isFeynmanAdvancing) return;
    const question = feynmanQuestions[feynmanStep];
    if (!question) return;
    const answer = buildFeynmanAnswer(question, feynmanAnswers[question.id] ?? "");
    if (!answer.answer) {
      setError(`请先回答「${question.label}」。`);
      return;
    }
    setError("");
    feynman.setIsAdvancing(true);
    try {
      let currentQuestions = feynmanQuestions;
      let currentAnswers = {
        ...(feynmanAnswersByNodeId[activeNode.id] ?? {}),
        [question.id]: answer,
      };
      const saved = await saveFeynmanAnswer(sessionId, activeNode.id, answer);
      currentQuestions = saved.questions.length ? saved.questions : currentQuestions;
      currentAnswers = { ...currentAnswers, ...saved.answers };
      const currentQuestionIndex = Math.max(0, currentQuestions.findIndex((item) => item.id === question.id));
      if (currentQuestionIndex >= currentQuestions.length - 1) {
        const answers = currentQuestions.map((item) => currentAnswers[item.id] ?? buildFeynmanAnswer(item, feynmanAnswers[item.id] ?? ""));
        const missing = answers.find((item) => !item.answer);
        if (missing) {
          throw new Error(`请先回答「${missing.label}」。`);
        }
        const response = await submitFeynman(sessionId, activeNode.id, answers);
        applyFeynmanResult(response);
        await refreshSessions();
        setStage("mastery");
        return;
      }
      syncFeynmanNodeState(activeNode.id, currentQuestions, currentAnswers, currentQuestionIndex + 1);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "下一题失败，请检查模型服务。");
    } finally {
      feynman.setIsAdvancing(false);
    }
  }

  function moveFeynmanStep(offset: number) {
    feynman.moveStep(offset);
  }

  async function transcribeAnswerAudio(audio: Blob) {
    const response = await transcribeSpeech(audio, {
      language: "zh",
      prompt: activeNode ? `当前知识点：${activeNode.title}` : undefined,
    });
    return response.text;
  }

  async function changePersona(nextPersona: Persona) {
    const previousPersona = persona;
    setPersona(nextPersona);
    if (UI_REVIEW_STAGE) return;
    if (!sessionId) return;
    try {
      setError("");
      const session = await updateSessionPersona(sessionId, nextPersona);
      setPersona(session.persona);
      setTutorSettings(session.tutor_settings ?? tutorSettings);
    } catch (caught) {
      setPersona(previousPersona);
      setError(caught instanceof Error ? caught.message : "切换教学风格失败，请稍后重试。");
    }
  }

  async function changeTutorSettings(nextSettings: TutorSettings) {
    const previousSettings = tutorSettings;
    setTutorSettings(nextSettings);
    if (UI_REVIEW_STAGE) return;
    if (!sessionId) return;
    try {
      setError("");
      const session = await updateSessionTutorSettings(sessionId, nextSettings);
      setTutorSettings(session.tutor_settings ?? nextSettings);
    } catch (caught) {
      setTutorSettings(previousSettings);
      setError(caught instanceof Error ? caught.message : "保存导师参数失败，请稍后重试。");
    }
  }

  function resetWorkspace() {
    setSessionId(null);
    setMaterialTitle("等待上传材料");
    parseJob.reset();
    setNodes([]);
    setActiveNodeId("");
    setMessageThreads({});
    setMessageCountsByNodeId({});
    setFeynmanAssessmentsByNodeId({});
    setMemories([]);
    setNodeProfiles({});
    feynman.clearAll();
    resetFeynmanState();
    setDraftsByNodeId({});
    setPersona("plain");
    setTutorSettings({ depth_level: 5, learning_style: "active", communication_type: "socratic" });
    setStage("canvas");
    setFailureCount(0);
    setDowngradedOverride(false);
    setTopicDraft("");
    setError("");
  }

  function hydrateSession(session: LearningSession) {
    setSessionId(session.id);
    setMaterialTitle(session.material_title);
    parseJob.setParseMeta({
      source: session.parse_source ?? "local",
      provider: session.parse_provider ?? null,
      model: session.parse_model ?? null,
      message: session.parse_message ?? "知识节点已生成",
    });
    setNodes(session.nodes);
    setActiveNodeId(session.active_node_id);
    setPersona(session.persona ?? "plain");
    setTutorSettings(session.tutor_settings ?? { depth_level: 5, learning_style: "active", communication_type: "socratic" });
    hydrateActiveNodeThread(session);
    setMemories(session.memories);
    setNodeProfiles(resolveNodeProfiles(session));
    parseJob.setParseProgress(session.parse_progress);
    feynman.hydrateFromSession(session.active_node_id, session.feynman_questions ?? {}, session.feynman_answers ?? {});
    setFeynmanAssessmentsByNodeId(session.feynman_assessments ?? {});
    setError("");
  }

  function resetFeynmanState() {
    feynman.resetCurrentNode();
  }

  function hydrateFeynmanNodeState(
    nodeId: string,
    questionsByNodeId = feynmanQuestionsByNodeId,
    answersByNodeId = feynmanAnswersByNodeId,
  ) {
    feynman.hydrateNodeState(nodeId, questionsByNodeId, answersByNodeId);
  }

  function syncFeynmanNodeState(
    nodeId: string,
    questions: FeynmanQuestion[],
    answers: Record<string, FeynmanAnswer>,
    nextStep?: number,
  ) {
    feynman.syncNodeState(nodeId, questions, answers, nextStep);
  }

  function hydrateActiveNodeThread(session: LearningSession) {
    const activeMessages = currentNodeMessages(session);
    setMessageThreads({
      [session.active_node_id]: activeMessages,
    });
    setMessageCountsByNodeId(resolveMessageCounts(session, activeMessages));
  }

  function beginParseJob(job: Awaited<ReturnType<typeof uploadParseJob>>["job"]) {
    parseJob.begin(job);
    setStage("canvas");
    setMaterialTitle(job.title);
  }

  async function handleAuthSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runBusy(async () => {
      const response =
        authMode === "register"
          ? await register(authUsername.trim(), authPassword, {
              role: authRegisterRole,
              organization_name: authRegisterRole === "org_manager" ? authOrganizationName.trim() : undefined,
              organization_code: authRegisterRole === "org_member" ? authOrganizationCode.trim() : undefined,
            })
          : await login(authUsername.trim(), authPassword);
      localStorage.setItem(AUTH_SESSION_STORAGE_KEY, "cookie");
      setToken("cookie");
      setUser(response.user);
      setShowDefaultAdminNotice(Boolean(response.security_notice ?? response.user.security_notice));
      setAccountUsernameDraft(response.user.username);
      setAuthPassword("");
      await refreshSessions();
      await refreshSpeech();
      if (response.user.role === "admin") {
        await refreshAdmin();
      }
      if (response.user.role === "org_manager") {
        await refreshOrganization();
      }
      if (response.user.role === "org_member") {
        await refreshMyTasks();
      }
    });
  }

  async function restoreSession() {
    await runBusy(async () => {
      try {
        const currentUser = await getMe();
        localStorage.setItem(AUTH_SESSION_STORAGE_KEY, "cookie");
        localStorage.removeItem(LEGACY_TOKEN_STORAGE_KEY);
        setToken("cookie");
        setUser(currentUser);
        setShowDefaultAdminNotice(Boolean(currentUser.security_notice));
        setAccountUsernameDraft(currentUser.username);
        await refreshSessions();
        await refreshSpeech();
        if (currentUser.role === "admin") {
          await refreshAdmin();
        }
        if (currentUser.role === "org_manager") {
          await refreshOrganization();
        }
        if (currentUser.role === "org_member") {
          await refreshMyTasks();
        }
      } catch (caught) {
        localStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
        localStorage.removeItem(LEGACY_TOKEN_STORAGE_KEY);
        setToken("");
        setUser(null);
        throw caught;
      }
    });
  }

  async function refreshSessions() {
    if (!token) return;
    const history = await listSessions();
    setSessions(history);
  }

  async function refreshSpeech() {
    try {
      const capabilities = await getSpeechCapabilities();
      setSpeechCapabilities(capabilities);
    } catch {
      setSpeechCapabilities({ asr_enabled: false, tts_enabled: false });
    }
  }

  async function openHistorySession(summary: SessionSummary) {
    await runBusy(async () => {
      const session = await getSession(summary.id);
      hydrateSession(session);
      setStage("map");
    });
  }

  async function removeHistorySession(summary: SessionSummary) {
    const confirmed = window.confirm(`删除学习记录「${summary.material_title}」？`);
    if (!confirmed) return;
    await runBusy(async () => {
      await deleteSession(summary.id);
      await refreshSessions();
      if (summary.id === sessionId) {
        resetWorkspace();
      }
    });
  }

  async function refreshAdmin() {
    if (!token) return;
    const [users, configs, speech, organizations] = await Promise.all([
      listUsers(),
      listApiConfigs(),
      listSpeechConfigs(),
      listOrganizations(),
    ]);
    setAdminUsers(users);
    setApiConfigs(configs);
    setSpeechConfigs(speech);
    setAdminOrganizations(organizations);
  }

  async function refreshResearch() {
    if (!token || user?.role !== "admin") return;
    const dashboard = await getResearchDashboard();
    setResearchDashboard(dashboard);
  }

  async function refreshOrganization() {
    const [dashboard, members, knowledge] = await Promise.all([
      getOrganizationDashboard(),
      listOrganizationMembers(),
      listOrganizationKnowledge(),
    ]);
    setOrganizationDashboard(dashboard);
    setOrganizationMembers(members);
    setOrganizationKnowledge(knowledge);
    if (!organizationReport && members.length > 0) {
      const report = await getOrganizationMemberReport(members[0].user.id);
      setOrganizationReport(report);
    }
  }

  async function refreshMyTasks() {
    const assignments = await listMyTasks();
    setMyTasks(assignments);
  }

  async function selectOrganizationMember(member: OrganizationMemberSummary) {
    await runBusy(async () => {
      const report = await getOrganizationMemberReport(member.user.id);
      setOrganizationReport(report);
    });
  }

  async function createOrganizationLearningTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runBusy(async () => {
      const selectedMemberIds = organizationTaskTargetMode === "selected" ? organizationTaskMemberIds : [];
      if (organizationTaskTargetMode === "selected" && selectedMemberIds.length === 0) {
        throw new Error("请选择至少一个组织成员。");
      }
      await createOrganizationTask({
        title: organizationTaskTitle.trim(),
        description: organizationTaskDescription.trim(),
        content: organizationTaskContent.trim(),
        assign_all: organizationTaskTargetMode === "all",
        member_ids: selectedMemberIds,
      });
      setOrganizationTaskTitle("");
      setOrganizationTaskDescription("");
      setOrganizationTaskContent("");
      setOrganizationTaskTargetMode("all");
      setOrganizationTaskMemberIds([]);
      await refreshOrganization();
    });
  }

  function toggleOrganizationTaskMember(userId: string) {
    setOrganizationTaskMemberIds((current) =>
      current.includes(userId) ? current.filter((item) => item !== userId) : [...current, userId],
    );
  }

  async function uploadOrganizationKnowledgeFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    await runBusy(async () => {
      await uploadOrganizationKnowledge(file);
      await refreshOrganization();
    });
  }

  async function removeOrganizationKnowledge(item: OrganizationKnowledgeItem) {
    const confirmed = window.confirm(`删除组织知识库「${item.title}」？`);
    if (!confirmed) return;
    await runBusy(async () => {
      await deleteOrganizationKnowledge(item.id);
      await refreshOrganization();
    });
  }

  async function startOrganizationTask(assignment: OrganizationTaskAssignment) {
    await runBusy(async () => {
      const response = await startMyTask(assignment.task_id);
      hydrateSession(response.session);
      await refreshSessions();
      await refreshMyTasks();
      setStage("map");
    });
  }

  async function saveDefaultAdminAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runBusy(async () => {
      const updated = await updateMyAccount({
        current_password: accountCurrentPassword,
        username: accountUsernameDraft.trim() || undefined,
        new_password: accountNewPassword || undefined,
      });
      setUser(updated);
      setShowDefaultAdminNotice(Boolean(updated.security_notice));
      setAccountCurrentPassword("");
      setAccountNewPassword("");
    });
  }

  async function importResearchData() {
    const parsed = JSON.parse(researchImportDraft.trim());
    const records = Array.isArray(parsed) ? parsed : parsed.records;
    if (!Array.isArray(records)) {
      throw new Error("请粘贴研究记录数组，或包含 records 数组的 JSON。");
    }
    await runAdminWrite(() => importResearchExperiments(records));
    setResearchImportDraft("");
    await refreshResearch();
  }

  async function exportResearchData() {
    const payload = await exportResearchExperiments();
    const dashboard = researchDashboard ?? await getResearchDashboard();
    setResearchDashboard(dashboard);
    const exportPayload = {
      generated_at: payload.generated_at,
      record_count: payload.records.length,
      records: payload.records,
      dashboard,
    };
    const blob = new Blob([JSON.stringify(exportPayload, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `blank-research-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function exportBlindReviewData() {
    const payload = await exportBlindReviewAnswers();
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `blank-blind-review-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function exportOrganizationTraceData() {
    const payload = await exportOrganizationTrace();
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `blank-organization-trace-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function saveApiConfig(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runBusy(async () => {
      await runAdminWrite(() => createApiConfig(apiConfigForm));
      setApiConfigForm((current) => ({ ...current, api_key: "" }));
      await refreshAdmin();
    });
  }

  async function saveSpeechConfig(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await runBusy(async () => {
      await runAdminWrite(() => createSpeechConfig(speechConfigForm));
      setSpeechConfigForm((current) => ({ ...current, api_key: "" }));
      await refreshAdmin();
      await refreshSpeech();
    });
  }

  async function toggleApiConfig(config: ApiConfig) {
    await runBusy(async () => {
      await runAdminWrite(() => updateApiConfig(config.id, { is_active: !config.is_active }));
      await refreshAdmin();
    });
  }

  async function toggleSpeechConfig(config: SpeechConfig) {
    await runBusy(async () => {
      await runAdminWrite(() => updateSpeechConfig(config.id, { is_active: !config.is_active }));
      await refreshAdmin();
      await refreshSpeech();
    });
  }

  async function removeApiConfig(config: ApiConfig) {
    const confirmed = window.confirm(`删除 ${config.provider} / ${config.model || "未设置模型"} 配置？`);
    if (!confirmed) return;
    await runBusy(async () => {
      await runAdminWrite(() => deleteApiConfig(config.id));
      await refreshAdmin();
    });
  }

  async function removeSpeechConfig(config: SpeechConfig) {
    const confirmed = window.confirm(`删除 ${config.kind.toUpperCase()} / ${config.model} 语音配置？`);
    if (!confirmed) return;
    await runBusy(async () => {
      await runAdminWrite(() => deleteSpeechConfig(config.id));
      await refreshAdmin();
      await refreshSpeech();
    });
  }

  async function createAdminUserAccount(payload: AdminUserCreateInput) {
    await runBusy(async () => {
      await runAdminWrite(() => createUser(normalizeAdminUserCreatePayload(payload)));
      await refreshAdmin();
    });
  }

  async function changeUserRole(targetUser: User, payload: AdminUserUpdateInput) {
    await runBusy(async () => {
      await runAdminWrite(() => updateUser(targetUser.id, normalizeAdminUserUpdatePayload(payload)));
      await refreshAdmin();
    });
  }

  async function toggleUserActive(targetUser: User) {
    await runBusy(async () => {
      await runAdminWrite(() => updateUser(targetUser.id, { is_active: !targetUser.is_active }));
      await refreshAdmin();
    });
  }

  async function runAdminWrite<T>(action: () => Promise<T>): Promise<T> {
    try {
      return await action();
    } catch (caught) {
      if (!(caught instanceof Error) || !caught.message.includes("重新验证管理员密码")) {
        throw caught;
      }
      const password = window.prompt("请输入当前管理员密码以继续");
      if (!password) {
        throw caught;
      }
      await reauthenticate(password);
      return action();
    }
  }

  async function logout() {
    try {
      await logoutSession();
    } catch {
      // Local logout should still clear UI state if the session has already expired.
    }
    localStorage.removeItem(AUTH_SESSION_STORAGE_KEY);
    localStorage.removeItem(LEGACY_TOKEN_STORAGE_KEY);
    stopSpeechPlayback();
    setToken("");
    setUser(null);
    setSpeechCapabilities({ asr_enabled: false, tts_enabled: false });
    setSessionId(null);
    setSessions([]);
    setAdminUsers([]);
    setAdminOrganizations([]);
    setApiConfigs([]);
    setSpeechConfigs([]);
    setOrganizationDashboard(null);
    setOrganizationMembers([]);
    setOrganizationKnowledge([]);
    setOrganizationReport(null);
    setOrganizationTaskTargetMode("all");
    setOrganizationTaskMemberIds([]);
    setMyTasks([]);
    setShowDefaultAdminNotice(false);
    resetWorkspace();
  }

  async function runBusy(action: () => Promise<void>) {
    setIsBusy(true);
    setError("");
    try {
      await action();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "请求失败，请检查后端服务。");
    } finally {
      setIsBusy(false);
    }
  }

  function stopSpeechPlayback() {
    if (speechAudioRef.current) {
      speechAudioRef.current.pause();
      speechAudioRef.current = null;
    }
    if (speechUrlRef.current) {
      URL.revokeObjectURL(speechUrlRef.current);
      speechUrlRef.current = "";
    }
    setIsSpeaking(false);
  }

  async function playSpeechText(text: string) {
    const normalized = text.trim();
    if (!normalized || !speechCapabilities.tts_enabled) return;
    stopSpeechPlayback();
    setIsSpeaking(true);
    try {
      const { blob } = await synthesizeSpeech(normalized, {
        language: "zh",
        voice: speechCapabilities.tts_voice ?? undefined,
      });
      const url = URL.createObjectURL(blob);
      speechUrlRef.current = url;
      const audio = new Audio(url);
      speechAudioRef.current = audio;
      audio.onended = () => stopSpeechPlayback();
      audio.onerror = () => {
        stopSpeechPlayback();
        setError("语音播报失败，请检查 TTS 服务。");
      };
      await audio.play();
    } catch (caught) {
      stopSpeechPlayback();
      setError(caught instanceof Error ? caught.message : "语音播报失败，请检查 TTS 服务。");
    }
  }

  const shellNavItems: BlankShellNavItem[] = [
    {
      stage: "canvas",
      icon: <UploadCloud size={18} />,
      label: "输入",
      onClick: () => setStage("canvas"),
    },
    {
      stage: "map",
      icon: <Network size={18} />,
      label: "拆解",
      onClick: () => setStage("map"),
      disabled: !hasSession,
    },
    {
      stage: "flow",
      icon: <BookOpen size={18} />,
      label: "学习",
      onClick: () => setStage("flow"),
      disabled: !hasSession,
    },
    {
      stage: "feynman",
      icon: <MessageSquare size={18} />,
      label: "输出",
      onClick: enterFeynmanStage,
      disabled: !hasSession,
    },
    {
      stage: "mastery",
      icon: <Sparkles size={18} />,
      label: "掌握",
      onClick: () => setStage("mastery"),
      disabled: !hasSession,
    },
    {
      stage: "evidence",
      icon: <BarChart3 size={18} />,
      label: "证据",
      onClick: () => setStage("evidence"),
      disabled: !hasSession,
    },
  ];

  if (user.role === "admin") {
    shellNavItems.push({
      stage: "research",
      icon: <Microscope size={18} />,
      label: "研究",
      onClick: () => {
        setStage("research");
        void refreshResearch();
      },
    });
    shellNavItems.push({
      stage: "admin",
      icon: <Settings size={18} />,
      label: "后台",
      onClick: () => {
        setStage("admin");
        void refreshAdmin();
      },
    });
  }
  if (user.role === "org_manager") {
    shellNavItems.push({
      stage: "organization",
      icon: <Building2 size={18} />,
      label: "组织",
      onClick: () => {
        setStage("organization");
        void refreshOrganization();
      },
    });
  }
  if (user.role === "org_member") {
    shellNavItems.push({
      stage: "tasks",
      icon: <ClipboardList size={18} />,
      label: "任务",
      onClick: () => {
        setStage("tasks");
        void refreshMyTasks();
      },
    });
  }

  const shellSidePanel = !isAdminStage && !isFocusStage ? (
    <SidePanel
      sessions={sessions}
      activeSessionId={sessionId}
      isBusy={isBusy}
      memories={stage === "flow" && activeNode ? memories.filter((memory) => memory.node_id === activeNode.id || memory.scope === "long_term") : []}
      longTermCount={memories.filter((memory) => memory.retention === "long" || memory.scope === "long_term").length}
      showMemories={stage === "flow" && Boolean(activeNode)}
      evidenceNode={stage === "map" ? activeNode : null}
      downgraded={downgraded}
      failureCount={failureCount}
      persona={persona}
      onOpen={openHistorySession}
      onDelete={removeHistorySession}
    />
  ) : null;

  const shouldShowKnowledgePanel = hasSession && (stage === "map" || stage === "flow");
  const shellLeftPanel = shouldShowKnowledgePanel ? (
    <div className="knowledge-sidecar">
      <section className="semantic-topology" aria-label="知识拓扑侧栏预览">
        <div className="sidecar-heading">
          <span>Topology</span>
          <strong>{nodes.length} 个节点</strong>
        </div>
        <div className="sidecar-constellation">
          <svg className="edge-layer" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
            {nodes.flatMap((node) =>
              node.deps.map((depId) => {
                const dep = nodes.find((item) => item.id === depId);
                if (!dep) return null;
                return (
                  <line
                    key={`sidecar-${depId}-${node.id}`}
                    x1={dep.x}
                    y1={dep.y}
                    x2={node.x}
                    y2={node.y}
                    className={node.status === "locked" ? "edge locked" : "edge"}
                  />
                );
              }),
            )}
          </svg>
          {nodes.map((node) => (
            <button
              key={`sidecar-${node.id}`}
              type="button"
              className={`sidecar-node ${node.status} ${node.id === activeNodeId ? "active" : ""}`}
              style={
                {
                  left: `${node.x}%`,
                  top: `${node.y}%`,
                  "--node-scale": node.weight,
                } as CSSProperties
              }
              onClick={() => selectNode(node)}
              disabled={isBusy || node.status === "locked"}
              aria-label={`选择 ${node.title}`}
              title={node.title}
            >
              <span />
            </button>
          ))}
        </div>
      </section>

      <section className="sidecar-directory" aria-label="知识节点目录">
        <div className="sidecar-heading">
          <span>Outline</span>
          <strong>{activeNode?.title ?? "未选择节点"}</strong>
        </div>
        <div className="sidecar-node-list">
          {nodes.map((node) => (
            <button
              key={`sidecar-row-${node.id}`}
              className={`sidecar-node-row ${node.status} ${node.id === activeNodeId ? "active" : ""}`}
              type="button"
              onClick={() => selectNode(node)}
              disabled={isBusy || node.status === "locked"}
            >
              <span>L{node.complexity}</span>
              <strong>{node.title}</strong>
              <small>{statusLabel(node.status)} · {nodeMessageCounts[node.id] ?? 0}</small>
            </button>
          ))}
        </div>
      </section>
    </div>
  ) : null;

  const shouldShowAuxiliaryScores = activeDimensionScores.length > 0 && (stage === "map" || stage === "flow");
  const hasAuxiliaryPanel = Boolean(shellSidePanel) || shouldShowAuxiliaryScores;
  const shellRightPanel = hasAuxiliaryPanel ? (
    <div className="auxiliary-sidecar">
      {shouldShowAuxiliaryScores && (
        <section className="auxiliary-card compact-radar">
          <div className="sidecar-heading">
            <span>Feynman</span>
            <strong>{activeMasteryPassed ? "已通过" : "待巩固"}</strong>
          </div>
          <div className="mini-score-list">
            {activeDimensionScores.map((score) => (
              <div key={score.stage} className="mini-score-row">
                <span>{score.label}</span>
                <strong>{score.value}</strong>
                <i style={{ "--score": `${Math.max(0, Math.min(100, score.value))}%` } as CSSProperties} />
              </div>
            ))}
          </div>
        </section>
      )}
      {shellSidePanel}
    </div>
  ) : null;

  return (
    <BlankShell
      stage={stage}
      masteredCount={masteredCount}
      nodeCount={nodes.length}
      materialTitle={materialTitle}
      sessionId={sessionId}
      user={user}
      resetWorkspace={resetWorkspace}
      logout={logout}
      extraTopRight={null}
      navItems={shellNavItems}
      isAdminStage={isAdminStage}
      isFocusStage={isFocusStage}
      error={error}
      sidePanel={shellSidePanel}
      leftPanel={shellLeftPanel}
      rightPanel={shellRightPanel}
    >
      {stage === "canvas" && (
        <CanvasStage
          parseProgress={parseProgress}
          parseMeta={parseMeta}
          parseStatus={parseStatus}
          isBusy={isBusy || isParsing}
          isParsing={isParsing}
          hasSession={hasSession}
          topicDraft={topicDraft}
          onTopicDraftChange={setTopicDraft}
          onTopicSubmit={handleTopicSubmit}
          onUpload={handleMaterialUpload}
          onDrop={handleDrop}
          onOpenMap={() => {
            if (hasSession) setStage("map");
          }}
        />
      )}

      {stage === "map" && activeNode && (
        <MapStage
          nodes={nodes}
          activeNodeId={activeNodeId}
          parseMeta={parseMeta}
          onSelectNode={selectNode}
          onStartFlow={() => setStage("flow")}
          isBusy={isBusy}
        />
      )}

      {stage === "flow" && activeNode && (
        <FlowStage
          activeNode={activeNode}
          nodes={nodes}
          messages={activeNodeMessages}
          draft={activeDraft}
          nodeMessageCounts={nodeMessageCounts}
          profile={activeProfile}
          persona={persona}
          tutorSettings={tutorSettings}
          onPersonaChange={changePersona}
          onTutorSettingsChange={changeTutorSettings}
          onDraftChange={(value) =>
            setDraftsByNodeId((current) => ({ ...current, [activeNode.id]: value }))
          }
          onSubmit={handleComposerSubmit}
          onSend={submitMessage}
          onConfuse={handleConfuse}
          onFeynman={enterFeynmanStage}
          onSelectNode={selectNode}
          isBusy={isBusy}
          isCoolingDown={Date.now() - lastChatSubmitAt < CHAT_SUBMIT_COOLDOWN_MS}
          v2Enabled={v2Chat.v2Enabled}
          agentStatus={UI_REVIEW_STAGE === "flow" ? "graph: 本轮工作流完成" : activeAgentTrace?.agentStatus}
          agentEvents={UI_REVIEW_STAGE === "flow" ? UI_REVIEW_AGENT_EVENTS : activeAgentTrace?.agentEvents}
          isAgentStreaming={UI_REVIEW_STAGE === "flow" ? false : activeAgentTrace?.isStreaming}
          thoughts={activeAgentTrace?.thoughts}
          ttsEnabled={speechCapabilities.tts_enabled}
          isSpeaking={isSpeaking}
          onSpeakText={playSpeechText}
        />
      )}

      {stage === "feynman" && activeNode && (
        <FeynmanStage
          activeNode={activeNode}
          questions={feynmanQuestions}
          answers={feynmanAnswers}
          currentIndex={feynmanStep}
          onAnswerChange={answerCurrentFeynman}
          onMove={moveFeynmanStep}
          onContinue={continueFeynmanStep}
          onReload={enterFeynmanStage}
          onComplete={completeFeynman}
          isBusy={isBusy || isFeynmanAdvancing}
          asrEnabled={speechCapabilities.asr_enabled}
          ttsEnabled={speechCapabilities.tts_enabled}
          isSpeaking={isSpeaking}
          onSpeakText={playSpeechText}
          onTranscribeAudio={transcribeAnswerAudio}
        />
      )}

      {stage === "mastery" && activeNode && (
        <MasteryStage
          activeNode={activeNode}
          nextNode={nextNode}
          diagnostics={activeDiagnostics}
          questionDiagnostics={activeQuestionDiagnostics}
          dimensionScores={activeDimensionScores}
          passed={activeMasteryPassed}
          nextReason={activeMasteryReason}
          onContinue={() => {
            if (nextNode) selectNode(nextNode);
          }}
          isBusy={isBusy}
        />
      )}

      {stage === "evidence" && activeNode && (
        <EvidenceStage
          nodes={nodes}
          activeNode={activeNode}
          messageCounts={nodeMessageCounts}
          profiles={nodeProfiles}
          questionsByNodeId={feynmanQuestionsByNodeId}
          answersByNodeId={feynmanAnswersByNodeId}
          dimensionScores={activeDimensionScores}
          questionDiagnostics={activeQuestionDiagnostics}
          memories={memories}
        />
      )}

      {stage === "research" && user.role === "admin" && (
        <ResearchStage
          dashboard={researchDashboard}
          isBusy={isBusy}
          importDraft={researchImportDraft}
          onImportDraftChange={setResearchImportDraft}
          onRefresh={() => {
            void runBusy(refreshResearch);
          }}
          onImport={() => {
            void runBusy(importResearchData);
          }}
          onExport={() => {
            void runBusy(exportResearchData);
          }}
          onExportBlindReview={() => {
            void runBusy(exportBlindReviewData);
          }}
        />
      )}

      {stage === "organization" && user.role === "org_manager" && (
        <OrganizationStage
          dashboard={organizationDashboard}
          members={organizationMembers}
          knowledge={organizationKnowledge}
          report={organizationReport}
          taskTitle={organizationTaskTitle}
          taskDescription={organizationTaskDescription}
          taskContent={organizationTaskContent}
          taskTargetMode={organizationTaskTargetMode}
          selectedTaskMemberIds={organizationTaskMemberIds}
          isBusy={isBusy}
          onTaskTitleChange={setOrganizationTaskTitle}
          onTaskDescriptionChange={setOrganizationTaskDescription}
          onTaskContentChange={setOrganizationTaskContent}
          onTaskTargetModeChange={setOrganizationTaskTargetMode}
          onToggleTaskMember={toggleOrganizationTaskMember}
          onRefresh={() => {
            void runBusy(refreshOrganization);
          }}
          onExportTrace={() => {
            void runBusy(exportOrganizationTraceData);
          }}
          onCreateTask={createOrganizationLearningTask}
          onUploadKnowledge={uploadOrganizationKnowledgeFile}
          onDeleteKnowledge={removeOrganizationKnowledge}
          onSelectMember={selectOrganizationMember}
        />
      )}

      {stage === "tasks" && user.role === "org_member" && (
        <TasksStage
          assignments={myTasks}
          isBusy={isBusy}
          onRefresh={() => {
            void runBusy(refreshMyTasks);
          }}
          onStart={startOrganizationTask}
        />
      )}

      {needsActiveNode && !activeNode && <EmptyStage onBack={() => setStage("canvas")} />}

      {isAdminStage && (
        <AdminStage
          users={adminUsers}
          organizations={adminOrganizations}
          apiConfigs={apiConfigs}
          speechConfigs={speechConfigs}
          form={apiConfigForm}
          speechForm={speechConfigForm}
          isBusy={isBusy}
          v2Enabled={v2Chat.v2Enabled}
          onFormChange={setApiConfigForm}
          onSpeechFormChange={setSpeechConfigForm}
          onSaveConfig={saveApiConfig}
          onSaveSpeechConfig={saveSpeechConfig}
          onRefresh={refreshAdmin}
          onToggleV2={v2Chat.toggleV2}
          onEditConfig={(config) => {
            if (!isKnownApiProvider(config.provider)) return;
            setApiConfigForm({
              provider: config.provider,
              base_url: config.base_url,
              api_key: "",
              model: config.model,
              is_active: config.is_active,
            });
          }}
          onToggleConfig={toggleApiConfig}
          onDeleteConfig={removeApiConfig}
          onEditSpeechConfig={(config) => {
            setSpeechConfigForm({
              kind: config.kind,
              provider: config.provider,
              base_url: config.base_url,
              api_key: "",
              model: config.model,
              path: config.path,
              is_active: config.is_active,
              voice: config.voice ?? "",
              language: config.language ?? "",
              response_format: config.response_format ?? "",
            });
          }}
          onToggleSpeechConfig={toggleSpeechConfig}
          onDeleteSpeechConfig={removeSpeechConfig}
          onCreateUser={createAdminUserAccount}
          onRoleChange={changeUserRole}
          onActiveToggle={toggleUserActive}
        />
      )}

      {showDefaultAdminNotice && user.security_notice?.kind === "default_admin_credentials" && (
        <div className="modal-backdrop" role="presentation">
          <section className="account-modal" role="dialog" aria-modal="true" aria-label="修改默认管理员账号">
            <div className="section-heading">
              <p className="eyebrow">Security Notice</p>
              <h3>默认管理员账号仍在使用初始密码</h3>
              <span>可以现在修改账号和密码，也可以下次登录时再处理。</span>
            </div>
            <form className="admin-form" onSubmit={saveDefaultAdminAccount}>
              <label>
                <span>账号</span>
                <input value={accountUsernameDraft} onChange={(event) => setAccountUsernameDraft(event.target.value)} />
              </label>
              <label>
                <span>当前密码</span>
                <input type="password" value={accountCurrentPassword} onChange={(event) => setAccountCurrentPassword(event.target.value)} />
              </label>
              <label>
                <span>新密码</span>
                <input type="password" value={accountNewPassword} onChange={(event) => setAccountNewPassword(event.target.value)} placeholder="至少 8 位，包含字母和数字" />
              </label>
              <div className="flow-actions">
                <button className="secondary-button" type="button" onClick={() => setShowDefaultAdminNotice(false)}>
                  下次登录修改
                </button>
                <button className="primary-button" type="submit" disabled={isBusy}>
                  现在修改
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </BlankShell>
  );
}

function isKnownApiProvider(provider: string): provider is ApiConfigInput["provider"] {
  return provider === "openai" || provider === "vllm" || provider === "ollama" || provider === "custom";
}

export { App };
