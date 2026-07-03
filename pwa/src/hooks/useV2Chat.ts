import { useCallback, useRef, useState } from "react";
import { API_BASE, csrfHeaderFor } from "../api";
import type { Message, NodeLearningProfile, TutorSettings } from "../types";

export interface V2ChatStreamEvent {
  type: "status" | "thought" | "thought_delta" | "message" | "feynman_result" | "done" | "error";
  agent?: string;
  message?: string;
  content?: string;
  detail?: string;
  data?: unknown;
  feedback?: string;
  messages?: Message[];
  node_profiles?: Record<string, NodeLearningProfile>;
  error?: string;
}

export interface AgentWorkflowEvent {
  id: number;
  type: V2ChatStreamEvent["type"];
  agent: string;
  message: string;
  detail?: string;
  timestamp: string;
}

export interface AgentWorkflowTrace {
  agentStatus: string | null;
  agentEvents: AgentWorkflowEvent[];
  thoughts: string[];
  streamingText: string;
  isStreaming: boolean;
}

const V2_MODE_KEY = "blank_v2_mode";
const V2_MODE_DEFAULT = true;
const EMPTY_TRACE: AgentWorkflowTrace = {
  agentStatus: null,
  agentEvents: [],
  thoughts: [],
  streamingText: "",
  isStreaming: false,
};

export interface V2SendOptions {
  onEvent?: (event: V2ChatStreamEvent) => void;
  onStatus?: (agent: string, message: string) => void;
  onThought?: (content: string) => void;
  onMessageDelta?: (delta: string) => void;
  onFeynmanResult?: (data: unknown, feedback: string) => void;
  onDone?: (event: V2ChatStreamEvent) => void;
  onError?: (error: string) => void;
  confusionEvent?: boolean;
  starterEvent?: boolean;
}

export function useV2Chat() {
  const [v2Enabled, setV2EnabledState] = useState(() => {
    if (typeof window === "undefined") return V2_MODE_DEFAULT;
    const saved = localStorage.getItem(V2_MODE_KEY);
    return saved === null ? V2_MODE_DEFAULT : saved === "true";
  });

  const [tracesByNodeId, setTracesByNodeId] = useState<Record<string, AgentWorkflowTrace>>({});
  const abortRef = useRef<AbortController | null>(null);
  const eventIdRef = useRef(0);
  const streamingNodeRef = useRef<string | null>(null);

  const setV2Enabled = useCallback((value: boolean) => {
    setV2EnabledState(value);
    if (typeof window !== "undefined") {
      localStorage.setItem(V2_MODE_KEY, String(value));
    }
  }, []);

  const toggleV2 = useCallback(() => {
    const next = !v2Enabled;
    setV2EnabledState(next);
    if (typeof window !== "undefined") {
      localStorage.setItem(V2_MODE_KEY, String(next));
    }
  }, [v2Enabled]);

  const reset = useCallback(() => {
    setTracesByNodeId({});
    abortRef.current?.abort();
    abortRef.current = null;
    streamingNodeRef.current = null;
    eventIdRef.current = 0;
  }, []);

  const resetNodeTrace = useCallback((nodeId: string) => {
    setTracesByNodeId((current) => ({
      ...current,
      [nodeId]: { ...EMPTY_TRACE },
    }));
  }, []);

  const updateTrace = useCallback((nodeId: string, updater: (trace: AgentWorkflowTrace) => AgentWorkflowTrace) => {
    setTracesByNodeId((current) => {
      const trace = current[nodeId] ?? EMPTY_TRACE;
      return {
        ...current,
        [nodeId]: updater(trace),
      };
    });
  }, []);

  const appendAgentEvent = useCallback((nodeId: string, event: Omit<AgentWorkflowEvent, "id" | "timestamp">) => {
    eventIdRef.current += 1;
    const timestamp = new Date().toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
    const nextEvent: AgentWorkflowEvent = {
      ...event,
      id: eventIdRef.current,
      timestamp,
    };
    updateTrace(nodeId, (trace) => ({
      ...trace,
      agentEvents: [...trace.agentEvents.slice(-23), nextEvent],
    }));
  }, [updateTrace]);

  const traceForNode = useCallback((nodeId?: string | null): AgentWorkflowTrace => {
    if (!nodeId) return EMPTY_TRACE;
    return tracesByNodeId[nodeId] ?? EMPTY_TRACE;
  }, [tracesByNodeId]);

  const anyStreaming = Object.values(tracesByNodeId).some((trace) => trace.isStreaming);

  const abort = useCallback(() => {
    const nodeId = streamingNodeRef.current;
    abortRef.current?.abort();
    abortRef.current = null;
    streamingNodeRef.current = null;
    if (nodeId) {
      updateTrace(nodeId, (trace) => ({ ...trace, isStreaming: false }));
    }
  }, [updateTrace]);

  const send = useCallback(
    async (
      sessionId: string,
      nodeId: string,
      message: string,
      persona: string,
      tutorSettings?: TutorSettings,
      options: V2SendOptions = {},
    ) => {
      resetNodeTrace(nodeId);
      updateTrace(nodeId, (trace) => ({ ...trace, isStreaming: true }));
      appendAgentEvent(nodeId, {
        type: "status",
        agent: "graph",
        message: "工作流连接中",
      });
      const controller = new AbortController();
      abortRef.current = controller;
      streamingNodeRef.current = nodeId;

      try {
        const response = await fetch(`${API_BASE}/api/v2/chat/stream`, {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            ...csrfHeaderFor("POST"),
          },
          body: JSON.stringify({
            session_id: sessionId,
            message,
            persona,
            tutor_settings: tutorSettings,
            confusion_event: options.confusionEvent ?? false,
            starter_event: options.starterEvent ?? false,
          }),
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          const errorText = await response.text();
          const message = errorText || `HTTP ${response.status}`;
          appendAgentEvent(nodeId, {
            type: "error",
            agent: "graph",
            message,
          });
          options.onError?.(message);
          throw new Error(message);
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
            let event: V2ChatStreamEvent;
            try {
              event = JSON.parse(jsonStr) as V2ChatStreamEvent;
            } catch {
              // 忽略解析失败的行
              continue;
            }
            options.onEvent?.(event);
            switch (event.type) {
              case "status":
                if (event.agent && event.message) {
                  updateTrace(nodeId, (trace) => ({
                    ...trace,
                    agentStatus: `${event.agent}: ${event.message}`,
                  }));
                  appendAgentEvent(nodeId, {
                    type: "status",
                    agent: event.agent,
                    message: event.message,
                    detail: event.detail,
                  });
                  options.onStatus?.(event.agent, event.message);
                }
                break;
              case "thought":
              case "thought_delta":
                const thoughtContent = event.content ?? "";
                if (thoughtContent) {
                  updateTrace(nodeId, (trace) => ({
                    ...trace,
                    thoughts: [...trace.thoughts, thoughtContent],
                  }));
                  appendAgentEvent(nodeId, {
                    type: "thought",
                    agent: "socrates",
                    message: "公开思考已生成",
                  });
                  options.onThought?.(thoughtContent);
                }
                break;
              case "message":
                if (event.content) {
                  updateTrace(nodeId, (trace) => ({
                    ...trace,
                    streamingText: trace.streamingText + event.content,
                  }));
                  options.onMessageDelta?.(event.content);
                }
                break;
              case "feynman_result":
                appendAgentEvent(nodeId, {
                  type: "feynman_result",
                  agent: "feynman",
                  message: "五维度评分已返回",
                  detail: event.feedback,
                });
                options.onFeynmanResult?.(event.data, event.feedback ?? "");
                break;
              case "done":
                appendAgentEvent(nodeId, {
                  type: "done",
                  agent: "graph",
                  message: "本轮工作流完成",
                });
                options.onDone?.(event);
                break;
              case "error":
                if (event.error) {
                  appendAgentEvent(nodeId, {
                    type: "error",
                    agent: "graph",
                    message: event.error,
                  });
                  options.onError?.(event.error);
                  throw new Error(event.error);
                }
                break;
            }
          }
        }
      } finally {
        updateTrace(nodeId, (trace) => ({ ...trace, isStreaming: false }));
        abortRef.current = null;
        if (streamingNodeRef.current === nodeId) {
          streamingNodeRef.current = null;
        }
      }
    },
    [appendAgentEvent, resetNodeTrace, updateTrace],
  );

  return {
    v2Enabled,
    setV2Enabled,
    toggleV2,
    tracesByNodeId,
    traceForNode,
    isStreaming: anyStreaming,
    send,
    abort,
    reset,
  };
}
