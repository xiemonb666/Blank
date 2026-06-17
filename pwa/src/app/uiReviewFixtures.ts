import type {
  ApiConfig,
  DiagnosticItem,
  DimensionScore,
  FeynmanAnswer,
  FeynmanQuestion,
  KnowledgeNode,
  Message,
  NodeLearningProfile,
  ResearchDashboard,
  Stage,
  User,
} from "../types";
import type { AgentWorkflowEvent } from "../hooks/useV2Chat";

export const UI_REVIEW_STAGE = resolveUiReviewStage();
const UI_REVIEW_STATE = import.meta.env.DEV && typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("ui-review-state") : null;
export const UI_REVIEW_EMPTY_EVIDENCE = UI_REVIEW_STATE === "empty";
export const UI_REVIEW_CANVAS_PARSING = UI_REVIEW_STAGE === "canvas" && UI_REVIEW_STATE === "parsing";
export const UI_REVIEW_NODE_ID = "ui-review-node-1";
export const UI_REVIEW_SESSION_ID = "ui-review-session";

export const UI_REVIEW_USER: User = {
  id: "ui-review-user",
  username: "ui-review",
  role: UI_REVIEW_STAGE === "admin" || UI_REVIEW_STAGE === "research" ? "admin" : "learner",
  is_active: true,
  created_at: "2026-06-11T00:00:00Z",
  total_tokens: 18420,
  today_tokens: 3920,
};

export const UI_REVIEW_ADMIN_USERS: User[] = [
  UI_REVIEW_USER,
  {
    id: "ui-review-learner",
    username: "learner-a",
    role: "learner",
    is_active: true,
    created_at: "2026-06-11T00:00:00Z",
    total_tokens: 7340,
    today_tokens: 860,
  },
];

export const UI_REVIEW_API_CONFIGS: ApiConfig[] = [
  {
    id: "ui-review-api",
    provider: "openai",
    base_url: "https://api.openai.com/v1",
    api_key_masked: "sk-...review",
    model: "gpt-4.1-mini",
    is_active: true,
    created_at: "2026-06-11T00:00:00Z",
    updated_at: "2026-06-11T00:00:00Z",
  },
];

export const UI_REVIEW_RESEARCH_DASHBOARD: ResearchDashboard = {
  generated_at: "2026-06-11T00:00:00Z",
  metrics: [
    { label: "学习者数", value: 32, unit: "人", note: "来自已保存学习会话的唯一用户数。" },
    { label: "材料数", value: 9, unit: "份", note: "按学习会话统计。" },
    { label: "知识节点", value: 84, unit: "个", note: "所有会话生成的节点总数。" },
    { label: "节点掌握率", value: 0.63, unit: "ratio", note: "已掌握节点数 / 总节点数。" },
    { label: "费曼平均分", value: 74.8, unit: "分", note: "来自节点画像和费曼诊断维度分。" },
    { label: "费曼达标率", value: 0.71, unit: "ratio", note: "维度分不低于 70 的比例。" },
    { label: "今日 Token", value: 18420, unit: "token", note: "后端记录的今日模型消耗。" },
    { label: "实验样本", value: 4, unit: "条", note: "管理员导入的匿名前后测/盲评研究记录。" },
  ],
  weak_points: [
    { label: "transfer", count: 18, average_score: 61.4 },
    { label: "correction", count: 15, average_score: 58.2 },
    { label: "mechanism", count: 9, average_score: 64.6 },
  ],
  feynman_distribution: [
    { label: "0-49", min_score: 0, max_score: 49, count: 3 },
    { label: "50-69", min_score: 50, max_score: 69, count: 21 },
    { label: "70-84", min_score: 70, max_score: 84, count: 38 },
    { label: "85-100", min_score: 85, max_score: 100, count: 14 },
  ],
  common_misconceptions: [
    { label: "条件方向倒置", count: 12, average_score: 0 },
    { label: "忽略边界条件", count: 8, average_score: 0 },
    { label: "只背定义不讲机制", count: 7, average_score: 0 },
  ],
  material_quality: [
    {
      session_id: "ui-review-session",
      title: "条件概率讲义",
      node_count: 12,
      evidence_coverage: 0.92,
      dependency_edges: 18,
      average_complexity: 3.4,
      updated_at: "2026-06-11T00:00:00Z",
    },
    {
      session_id: "ui-review-session-2",
      title: "Transformer 推理效率论文",
      node_count: 10,
      evidence_coverage: 0.86,
      dependency_edges: 14,
      average_complexity: 4.1,
      updated_at: "2026-06-10T00:00:00Z",
    },
  ],
  memory_categories: [
    { category: "cognitive", count: 28, long_term_count: 9 },
    { category: "long_term", count: 11, long_term_count: 11 },
    { category: "preference", count: 6, long_term_count: 4 },
  ],
  experiment_summaries: [
    {
      study_id: "study-a",
      group_label: "Blank",
      participants: 2,
      pretest_average: 49,
      posttest_average: 82,
      delayed_average: 75,
      average_gain: 33,
      retention_rate: 0.914,
      learning_minutes_average: 36,
      cognitive_load_average: 4.2,
    },
    {
      study_id: "study-a",
      group_label: "ChatGPT",
      participants: 2,
      pretest_average: 50,
      posttest_average: 68,
      delayed_average: 60,
      average_gain: 18,
      retention_rate: 0.882,
      learning_minutes_average: 34,
      cognitive_load_average: 6.1,
    },
  ],
  score_agreement: {
    paired_count: 4,
    correlation: 0.91,
    mean_absolute_gap: 3.2,
    system_average: 76.5,
    human_average: 74.8,
  },
  experiment_records: [
    {
      id: "research-record-1",
      study_id: "study-a",
      participant_code: "p001",
      group_label: "Blank",
      material_label: "条件概率讲义",
      pretest_score: 48,
      posttest_score: 82,
      delayed_score: 74,
      system_feynman_score: 80,
      human_score: 78,
      learning_minutes: 36,
      cognitive_load: 4,
      notes: "",
      imported_at: "2026-06-11T00:00:00Z",
      updated_at: "2026-06-11T00:00:00Z",
    },
    {
      id: "research-record-2",
      study_id: "study-a",
      participant_code: "p002",
      group_label: "ChatGPT",
      material_label: "条件概率讲义",
      pretest_score: 50,
      posttest_score: 68,
      delayed_score: 60,
      system_feynman_score: 65,
      human_score: 62,
      learning_minutes: 34,
      cognitive_load: 6,
      notes: "",
      imported_at: "2026-06-11T00:00:00Z",
      updated_at: "2026-06-11T00:00:00Z",
    },
  ],
};

export const UI_REVIEW_NODES: KnowledgeNode[] = [
  {
    id: UI_REVIEW_NODE_ID,
    title: "条件概率与贝叶斯更新",
    summary: "理解先验、似然和后验如何一起改变判断，类似状态递推 h_t = e^{Δt A_t} h_{t-1}+ Δt B_t x_t。",
    evidence: "后验概率等于先验概率在新证据出现后更新得到的判断。Mamba 离散递推示例：h_t = e^{Δt A_t} h_{t-1}+ Δt B_t x_t, y_t = C_t^T h_t",
    complexity_reason: "包含公式含义和条件方向判断，需要先区分先验与似然。",
    complexity: 4,
    weight: 1,
    status: "active",
    x: 28,
    y: 42,
    deps: [],
  },
  {
    id: "ui-review-node-2",
    title: "独立性误判",
    summary: "区分事件独立、条件独立和常见直觉误区。",
    evidence: "条件独立并不等于事件在所有情况下都互不影响。",
    complexity_reason: "需要识别反例并纠正常见直觉误判。",
    complexity: 3,
    weight: 0.82,
    status: "available",
    x: 62,
    y: 34,
    deps: [UI_REVIEW_NODE_ID],
  },
];

export const UI_REVIEW_QUESTIONS: FeynmanQuestion[] = [
  {
    id: "ui-review-q1",
    label: "先验",
    question: "如果你要向同学解释“先验概率”，会用什么生活例子？",
    focus: "重点说明：它是看到新证据之前的判断，不是最终结论。",
    difficulty: 2,
    stage: "warmup",
  },
  {
    id: "ui-review-q2",
    label: "贝叶斯更新",
    question: "请讲清楚先验、似然和后验三者之间的关系。",
    focus: "不要只背公式，要说出新证据如何改变原判断。",
    difficulty: 4,
    stage: "mechanism",
  },
  {
    id: "ui-review-q3",
    label: "迁移",
    question: "把贝叶斯更新迁移到“医学筛查阳性”的场景，你会提醒别人注意什么？",
    focus: "需要提到基础患病率和假阳性对判断的影响。",
    difficulty: 4,
    stage: "transfer",
  },
  {
    id: "ui-review-q4",
    label: "纠错",
    question: "有人说“检测准确率 99%，阳性就等于 99% 患病”，你如何纠正？",
    focus: "指出把 P(阳性|患病) 当成 P(患病|阳性) 的错误。",
    difficulty: 5,
    stage: "correction",
  },
  {
    id: "ui-review-q5",
    label: "复述",
    question: "用 90 秒总结这个节点的核心判断流程。",
    focus: "把先验、证据、更新和结论边界串起来。",
    difficulty: 3,
    stage: "recap",
  },
];

export const UI_REVIEW_ANSWER_TEXT: Record<string, string> = {
  "ui-review-q1": "先验就像考试前根据平时作业判断自己大概能拿多少分，它是在看到这次试卷难度和临场发挥之前的初始估计。",
  "ui-review-q2": "先验是原来的判断，似然是新证据在不同假设下出现的可能性，后验是把两者合起来之后的新判断。",
};

export const UI_REVIEW_DIMENSION_SCORES: DimensionScore[] = [
  { stage: "warmup", label: "基础理解", value: 82, note: "能用生活例子说明先验，但还需要区分它和最终结论。" },
  { stage: "mechanism", label: "机制拆解", value: 68, note: "能说出三者关系，但对似然的方向解释不够稳定。" },
  { stage: "transfer", label: "迁移应用", value: 74, note: "能迁移到筛查场景，仍需强调基础率。" },
  { stage: "correction", label: "反例纠错", value: 63, note: "能发现结论不严谨，但没有明确指出条件概率倒置。" },
];

export const UI_REVIEW_DIAGNOSTICS: DiagnosticItem[] = [
  { label: "概念覆盖", value: 76, note: "覆盖先验、似然、后验，但条件方向需要补强。" },
  { label: "逻辑连贯", value: 69, note: "解释顺序基本成立，纠错环节跳步较明显。" },
  { label: "表达负荷", value: 81, note: "表述简洁，适合继续压缩成口头讲解。" },
];

export const UI_REVIEW_QUESTION_DIAGNOSTICS = UI_REVIEW_QUESTIONS.slice(0, 4).map((question, index) => ({
  question_id: question.id,
  label: question.label,
  value: [82, 68, 74, 63][index],
  note: ["例子准确。", "似然方向需要更清楚。", "能联系基础率。", "需指出条件倒置。"][index],
  stage: question.stage,
}));

const UI_REVIEW_NODE_PROFILE: NodeLearningProfile = {
  node_id: UI_REVIEW_NODE_ID,
  stage: "mechanism",
  dimension_scores: {
    warmup: 82,
    mechanism: 68,
    transfer: 74,
    correction: 63,
  },
  weak_points: ["似然方向", "条件概率倒置"],
  streak: 1,
  failures: 1,
  confusion_requests: 2,
  confusion_resolved: 1,
  confusion_unresolved: 1,
  last_challenge: "用医学筛查例子解释后验概率。",
  next_challenge: "纠正把 P(阳性|患病) 当成 P(患病|阳性) 的说法。",
  badge: "待补强",
  updated_at: "2026-06-11T00:00:00Z",
};

export const UI_REVIEW_MESSAGES: Record<string, Message[]> = {
  [UI_REVIEW_NODE_ID]: [
    { role: "mentor", node_id: UI_REVIEW_NODE_ID, text: "先别背公式。你会怎样用一个现实场景解释先验概率？" },
    { role: "learner", node_id: UI_REVIEW_NODE_ID, text: UI_REVIEW_ANSWER_TEXT["ui-review-q1"] },
    { role: "mentor", node_id: UI_REVIEW_NODE_ID, text: "这个例子成立。下一步把“看到新证据后如何更新”讲出来，比如 h_t = e^{Δt A_t} h_{t-1}+ Δt B_t x_t, y_t = C_t^T h_t 这种递推关系。" },
  ],
};

export const UI_REVIEW_AGENT_EVENTS: AgentWorkflowEvent[] = [
  {
    id: 1,
    type: "status",
    agent: "router",
    message: "意图识别完成：question",
    detail: "学习者正在补充机制解释",
    timestamp: "21:08:12",
  },
  {
    id: 2,
    type: "status",
    agent: "graphrag",
    message: "本轮使用材料片段回退",
    detail: "GraphRAG 未启用，使用当前材料片段回退",
    timestamp: "21:08:13",
  },
  {
    id: 3,
    type: "thought",
    agent: "socrates",
    message: "公开思考已生成",
    timestamp: "21:08:14",
  },
  {
    id: 4,
    type: "status",
    agent: "critic",
    message: "事实核查通过",
    timestamp: "21:08:16",
  },
  {
    id: 5,
    type: "done",
    agent: "graph",
    message: "本轮工作流完成",
    timestamp: "21:08:18",
  },
];

export const UI_REVIEW_MESSAGE_COUNTS: Record<string, number> = {
  [UI_REVIEW_NODE_ID]: UI_REVIEW_MESSAGES[UI_REVIEW_NODE_ID].length,
};

export const UI_REVIEW_NODE_PROFILES: Record<string, NodeLearningProfile> = {
  [UI_REVIEW_NODE_ID]: UI_REVIEW_NODE_PROFILE,
};

export const UI_REVIEW_QUESTION_MAP: Record<string, FeynmanQuestion[]> = {
  [UI_REVIEW_NODE_ID]: UI_REVIEW_QUESTIONS,
};

const UI_REVIEW_FEYNMAN_ANSWERS = Object.fromEntries(
  UI_REVIEW_QUESTIONS.map((question) => [
    question.id,
    {
      question_id: question.id,
      label: question.label,
      question: question.question,
      answer: UI_REVIEW_ANSWER_TEXT[question.id] ?? "",
      focus: question.focus,
      difficulty: question.difficulty,
      stage: question.stage,
      follow_up_of: question.follow_up_of ?? null,
    },
  ]),
) as Record<string, FeynmanAnswer>;

export const UI_REVIEW_ANSWER_MAP: Record<string, Record<string, FeynmanAnswer>> = {
  [UI_REVIEW_NODE_ID]: UI_REVIEW_FEYNMAN_ANSWERS,
};

function resolveUiReviewStage(): Stage | null {
  if (!import.meta.env.DEV || typeof window === "undefined") return null;
  const stage = new URLSearchParams(window.location.search).get("ui-review");
  if (stage === "canvas" || stage === "map" || stage === "flow" || stage === "feynman" || stage === "mastery" || stage === "evidence" || stage === "research" || stage === "admin") return stage;
  return null;
}
