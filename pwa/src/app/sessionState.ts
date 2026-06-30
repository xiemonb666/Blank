import type { LearningSession } from "../api";
import type { FeynmanAnswer, FeynmanQuestion, KnowledgeNode, Message, NodeLearningProfile, NodeStatus, Stage } from "../types";

export function currentNodeMessages(session: LearningSession) {
  const activeMessages =
    session.active_messages.length > 0
      ? session.active_messages.filter((message) => message.node_id === session.active_node_id)
      : session.messages.filter((message) => message.node_id === session.active_node_id);
  if (activeMessages.length > 0) {
    return activeMessages.map((message) => ({ ...message, node_id: session.active_node_id }));
  }
  return [];
}

export function resolveMessageCounts(session: LearningSession, activeMessages: Message[]) {
  return {
    ...session.message_counts,
    [session.active_node_id]: activeMessages.length,
  };
}

export function resolveNodeProfiles(session: LearningSession) {
  const profiles = { ...(session.node_profiles ?? {}) };
  for (const node of session.nodes) {
    profiles[node.id] = profiles[node.id] ?? defaultNodeProfile(node);
  }
  return profiles;
}

export function defaultNodeProfile(node: KnowledgeNode): NodeLearningProfile {
  return {
    node_id: node.id,
    stage: "warmup",
    dimension_scores: { warmup: 0, mechanism: 0, transfer: 0, correction: 0 },
    weak_points: [],
    streak: 0,
    failures: 0,
    confusion_requests: 0,
    confusion_resolved: 0,
    confusion_unresolved: 0,
    last_challenge: "",
    next_challenge: `先用一句话说清「${node.title}」解决什么问题。`,
    badge: "",
    updated_at: new Date(0).toISOString(),
  };
}

export function buildFeynmanAnswer(question: FeynmanQuestion, answer: string): FeynmanAnswer {
  return {
    question_id: question.id,
    label: question.label,
    question: question.question,
    focus: question.focus,
    difficulty: question.difficulty,
    stage: question.stage,
    follow_up_of: question.follow_up_of,
    answer: answer.trim(),
  };
}

export function appendMessagesToThread(
  threads: Record<string, Message[]>,
  nodeId: string,
  messages: Message[],
) {
  return {
    ...threads,
    [nodeId]: [...(threads[nodeId] ?? []), ...messages.map((message) => ({ ...message, node_id: nodeId }))],
  };
}

export function replaceThreadMessages(
  threads: Record<string, Message[]>,
  nodeId: string,
  messages: Message[],
) {
  const nodeMessages = messages.filter((message) => message.node_id === nodeId);
  return {
    ...threads,
    [nodeId]: nodeMessages.map((message) => ({ ...message, node_id: nodeId })),
  };
}

export function updateLatestMentorInThread(
  threads: Record<string, Message[]>,
  nodeId: string,
  updater: (message: Message) => Message,
) {
  const thread = threads[nodeId] ?? [];
  const nextThread = [...thread];
  for (let index = nextThread.length - 1; index >= 0; index -= 1) {
    const message = nextThread[index];
    if (message.role === "mentor") {
      nextThread[index] = { ...updater(message), node_id: nodeId };
      return { ...threads, [nodeId]: nextThread };
    }
  }
  return threads;
}

export function stageLabel(stage: Stage) {
  switch (stage) {
    case "canvas":
      return "工作台";
    case "map":
      return "知识拆解";
    case "flow":
      return "沉浸学习";
    case "feynman":
      return "费曼验证";
    case "mastery":
      return "掌握反馈";
    case "evidence":
      return "证据看板";
    case "research":
      return "教师研究端";
    case "admin":
      return "后台管理";
    case "organization":
      return "组织管理";
    case "tasks":
      return "组织任务";
  }
}

export function statusLabel(status: NodeStatus) {
  switch (status) {
    case "mastered":
      return "已掌握";
    case "active":
      return "学习中";
    case "available":
      return "可学习";
    case "locked":
      return "未解锁";
  }
}

export function stageLabelText(stage: NodeLearningProfile["stage"]) {
  switch (stage) {
    case "warmup":
      return "热身理解";
    case "mechanism":
      return "机制拆解";
    case "transfer":
      return "迁移应用";
    case "correction":
      return "反例纠错";
    case "recap":
      return "复述收束";
  }
}
