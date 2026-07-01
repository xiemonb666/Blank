import { BrainCircuit, Check, ChevronDown, ChevronUp, GitBranch, GraduationCap, Loader2, Map, Network, Radar, Route, ShieldCheck, Sparkles, Target, Waypoints } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import type { AgentWorkflowEvent } from "../hooks/useV2Chat";

interface AgentWorkflowPanelProps {
  events: AgentWorkflowEvent[];
  activeStatus?: string | null;
  isStreaming?: boolean;
}

const AGENTS = [
  { id: "router", label: "Router", caption: "识别意图", icon: Route },
  { id: "planner", label: "Planner", caption: "拆解目标", icon: Map },
  { id: "analyst", label: "Analyst", caption: "机制分析", icon: Waypoints },
  { id: "coach", label: "Coach", caption: "降低负荷", icon: Target },
  { id: "memory", label: "Memory", caption: "沉淀线索", icon: Sparkles },
  { id: "graphrag", label: "RAG", caption: "召回材料", icon: Network },
  { id: "socrates", label: "Socrates", caption: "引导追问", icon: BrainCircuit },
  { id: "feynman", label: "Feynman", caption: "复述评分", icon: GraduationCap },
  { id: "critic", label: "Critic", caption: "事实核查", icon: ShieldCheck },
  { id: "graph", label: "Graph", caption: "汇总输出", icon: GitBranch },
] as const;

const AGENT_LABELS: Record<string, string> = Object.fromEntries(AGENTS.map((agent) => [agent.id, agent.label]));
const AUTO_COLLAPSE_DELAY_MS = 1600;

export function AgentWorkflowPanel({ events, activeStatus, isStreaming }: AgentWorkflowPanelProps) {
  const activeAgent = latestAgent(events) ?? agentFromStatus(activeStatus);
  const completedAgents = new Set(events.map((event) => event.agent));
  const latestEvent = events[events.length - 1] ?? null;
  const recentEvents = events.slice(-5).reverse();
  const hasTerminalEvent = latestEvent?.type === "done" || latestEvent?.type === "error";
  const [collapsed, setCollapsed] = useState(true);
  const [manualOverride, setManualOverride] = useState(false);
  const statusLabel = latestEvent?.type === "error" ? "异常" : isStreaming ? "运行中" : hasTerminalEvent ? "已完成" : "待命";
  const compactAgents = useMemo(
    () => AGENTS.filter((agent) => completedAgents.has(agent.id)).map((agent) => agent.label),
    [completedAgents],
  );

  useEffect(() => {
    if (isStreaming) {
      setCollapsed(false);
      setManualOverride(false);
      return;
    }
    if (manualOverride) return;
    if (!hasTerminalEvent) {
      setCollapsed(true);
      return;
    }
    const timer = window.setTimeout(() => setCollapsed(true), AUTO_COLLAPSE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [hasTerminalEvent, isStreaming, latestEvent?.id, manualOverride]);

  const toggleCollapsed = () => {
    setManualOverride(true);
    setCollapsed((value) => !value);
  };

  return (
    <section className={`agent-workflow-panel ${isStreaming ? "running" : ""} ${collapsed ? "collapsed" : ""}`} aria-label="多智能体工作流">
      <button
        className="agent-workflow-head"
        type="button"
        onClick={toggleCollapsed}
        aria-expanded={!collapsed}
      >
        <div>
          <span>Multi-Agent Trace</span>
          <strong>{activeStatus || "V2 多智能体链路待命"}</strong>
        </div>
        <b>
          {isStreaming ? <Loader2 size={15} /> : <Radar size={15} />}
          {statusLabel}
        </b>
        {collapsed ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
      </button>

      {collapsed && (
        <button
          className="agent-workflow-compact"
          type="button"
          onClick={toggleCollapsed}
          aria-label="展开多智能体工作流"
        >
          <span className="agent-compact-score">{completedAgents.size > 0 ? `${completedAgents.size}步` : "待命"}</span>
          <span className="agent-compact-copy">
            <strong>{compactTitle(latestEvent, activeAgent, activeStatus)}</strong>
            <small>{compactSummary(compactAgents, latestEvent)}</small>
          </span>
          <span className="agent-compact-dots" aria-hidden="true">
            {AGENTS.map((agent) => (
              <i
                key={agent.id}
                className={`${completedAgents.has(agent.id) ? "complete" : ""} ${activeAgent === agent.id ? "active" : ""}`}
              />
            ))}
          </span>
        </button>
      )}

      {!collapsed && (
        <>
          <div className="agent-orbit" aria-label="智能体节点">
            {AGENTS.map((agent, index) => {
              const Icon = agent.icon;
              const active = activeAgent === agent.id;
              const complete = completedAgents.has(agent.id);
              return (
                <div
                  key={agent.id}
                  className={`agent-node ${active ? "active" : ""} ${complete ? "complete" : ""}`}
                  style={{ "--agent-index": index } as CSSProperties}
                >
                  <span className="agent-node-icon">
                    <Icon size={16} />
                  </span>
                  <span className="agent-node-copy">
                    <strong>{agent.label}</strong>
                    <small>{agent.caption}</small>
                  </span>
                  {complete && <Check className="agent-node-check" size={13} />}
                </div>
              );
            })}
          </div>

          <div className="agent-event-stream" aria-label="最近智能体事件">
            {recentEvents.length > 0 ? (
              recentEvents.map((event) => (
                <div key={event.id} className={`agent-event ${event.type}`}>
                  <time>{event.timestamp}</time>
                  <strong>{AGENT_LABELS[event.agent] ?? event.agent}</strong>
                  <span>{event.message}</span>
                </div>
              ))
            ) : (
              <div className="agent-event empty">
                <time>--:--:--</time>
                <strong>Graph</strong>
                <span>发送消息后展示实时协作路径</span>
              </div>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function latestAgent(events: AgentWorkflowEvent[]) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const agent = events[index]?.agent;
    if (agent) return agent;
  }
  return null;
}

function agentFromStatus(status?: string | null) {
  if (!status) return null;
  const [agent] = status.split(":");
  return agent?.trim() || null;
}

function compactTitle(event: AgentWorkflowEvent | null, activeAgent: string | null, activeStatus?: string | null) {
  if (event?.type === "error") return "工作流异常，需要检查本轮输出";
  if (event?.type === "done") return "工作流完成，导师回复已生成";
  if (activeStatus) return activeStatus;
  if (activeAgent) return `${AGENT_LABELS[activeAgent] ?? activeAgent} 已就绪`;
  return "V2 多智能体链路待命";
}

function compactSummary(agentLabels: string[], latestEvent: AgentWorkflowEvent | null) {
  const lastStep = latestEvent ? `${AGENT_LABELS[latestEvent.agent] ?? latestEvent.agent}: ${latestEvent.message}` : "等待发送消息";
  if (agentLabels.length === 0) return lastStep;
  return `${agentLabels.slice(-3).join(" -> ")} · ${lastStep}`;
}
