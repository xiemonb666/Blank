import { FormEvent, useEffect, useRef } from "react";
import { ArrowRight, Gauge, Send, Volume2 } from "lucide-react";
import { communicationTypes, learningStyles, personas } from "../app/constants";
import { stageLabelText, statusLabel } from "../app/sessionState";
import { AgentWorkflowPanel } from "../components/AgentWorkflowPanel";
import { PagedList, SegmentedControl } from "../components/DesignPrimitives";
import { RichText } from "../components/RichText";
import { ThoughtProcess } from "../components/ThoughtProcess";
import type { AgentWorkflowEvent } from "../hooks/useV2Chat";
import type { KnowledgeNode, Message, NodeLearningProfile, Persona, TutorCommunicationType, TutorLearningStyle, TutorSettings } from "../types";

interface FlowStageProps {
  activeNode: KnowledgeNode;
  nodes: KnowledgeNode[];
  messages: Message[];
  draft: string;
  nodeMessageCounts: Record<string, number>;
  profile: NodeLearningProfile | null;
  persona: Persona;
  tutorSettings: TutorSettings;
  onPersonaChange: (persona: Persona) => void;
  onTutorSettingsChange: (settings: TutorSettings) => void;
  onDraftChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onSend: () => void;
  onConfuse: () => void;
  onFeynman: () => void;
  onSelectNode: (node: KnowledgeNode) => Promise<void>;
  isBusy: boolean;
  isCoolingDown: boolean;
  v2Enabled?: boolean;
  agentStatus?: string | null;
  agentEvents?: AgentWorkflowEvent[];
  isAgentStreaming?: boolean;
  thoughts?: string[];
  ttsEnabled: boolean;
  isSpeaking: boolean;
  onSpeakText: (text: string) => void;
}

export function FlowStage({
  activeNode,
  nodes,
  messages,
  draft,
  nodeMessageCounts,
  profile,
  persona,
  tutorSettings,
  onPersonaChange,
  onTutorSettingsChange,
  onDraftChange,
  onSubmit,
  onSend,
  onConfuse,
  onFeynman,
  onSelectNode,
  isBusy,
  isCoolingDown,
  v2Enabled,
  agentStatus,
  agentEvents = [],
  isAgentStreaming,
  thoughts,
  ttsEnabled,
  isSpeaking,
  onSpeakText,
}: FlowStageProps) {
  const messageListRef = useRef<HTMLDivElement | null>(null);
  const messageEndRef = useRef<HTMLDivElement | null>(null);
  const stageTitle = profile ? stageLabelText(profile.stage) : "等待导师出题";
  const stageCopy = profile ? stageFocusCopy(profile.stage) : "上传材料并进入学习后，导师会把当前节点拆成可回答的小问题。";
  const nextChallenge = profile?.next_challenge || "先回答当前导师问题，再推进到下一挑战。";
  const stageOrder = ["warmup", "mechanism", "transfer", "correction", "recap"] as const;
  const currentStageIndex = profile ? Math.max(0, stageOrder.indexOf(profile.stage)) : 0;
  const latestMessage = messages.length > 0 ? messages[messages.length - 1] : null;
  const visibleMessages = messages;
  const latestThought = thoughts && thoughts.length > 0 ? thoughts[thoughts.length - 1] : "";
  const scrollSignal = [
    activeNode.id,
    messages.length,
    latestMessage?.role ?? "",
    latestMessage?.text.length ?? 0,
    latestMessage?.thinking?.length ?? 0,
    thoughts?.length ?? 0,
    latestThought.length,
    agentEvents.length,
    agentStatus ?? "",
    isAgentStreaming ? "streaming" : "idle",
  ].join(":");

  useEffect(() => {
    const list = messageListRef.current;
    const anchor = messageEndRef.current;
    if (!list || !anchor || typeof window === "undefined") return;

    const frameId = window.requestAnimationFrame(() => {
      const isInnerScrollable = list.scrollHeight > list.clientHeight + 2;
      if (isInnerScrollable) {
        list.scrollTop = list.scrollHeight;
        return;
      }
      anchor.scrollIntoView({ block: "end", behavior: "auto" });
    });

    return () => window.cancelAnimationFrame(frameId);
  }, [scrollSignal]);

  return (
    <div className="flow-layout">
      <aside className="learning-card">
        <NodeCardStack
          nodes={nodes}
          activeNode={activeNode}
          messageCounts={nodeMessageCounts}
          isBusy={isBusy}
          onSelectNode={onSelectNode}
        />
        <div className="persona-box learning-persona">
          <div className="box-title">
            <Gauge size={18} />
            <span>风格调音台</span>
          </div>
          <SegmentedControl
            label="教学风格"
            value={persona}
            options={personas}
            disabled={isBusy}
            className="persona-switcher"
            onChange={onPersonaChange}
          />
          <p>{personas[persona].caption}</p>
        </div>
        <div className="persona-box learning-persona">
          <div className="box-title">
            <Gauge size={18} />
            <span>导师参数</span>
          </div>
          <label className="tutor-depth-control">
            <span>知识深度 L{tutorSettings.depth_level}</span>
            <input
              type="range"
              min={1}
              max={10}
              value={tutorSettings.depth_level}
              onChange={(event) =>
                onTutorSettingsChange({
                  ...tutorSettings,
                  depth_level: Number(event.target.value),
                })
              }
              disabled={isBusy}
            />
          </label>
          <SegmentedTutorControl<TutorLearningStyle>
            label="学习风格"
            value={tutorSettings.learning_style}
            options={learningStyles}
            disabled={isBusy}
            onChange={(learning_style) => onTutorSettingsChange({ ...tutorSettings, learning_style })}
          />
          <SegmentedTutorControl<TutorCommunicationType>
            label="沟通类型"
            value={tutorSettings.communication_type}
            options={communicationTypes}
            disabled={isBusy}
            onChange={(communication_type) => onTutorSettingsChange({ ...tutorSettings, communication_type })}
          />
        </div>
      </aside>

      <section className="chat-panel">
        <section className="learning-route" aria-label="学习航线">
          {stageOrder.map((stage, index) => (
            <div
              key={stage}
              className={`route-step ${index < currentStageIndex ? "done" : ""} ${index === currentStageIndex ? "active" : ""}`}
            >
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{stageLabelText(stage)}</strong>
            </div>
          ))}
        </section>
        <section className="flow-mission" aria-label="当前学习任务">
          <div>
            <span>本轮任务</span>
            <strong>{stageTitle}</strong>
          </div>
          <p>{stageCopy}</p>
          <b>
            <span>当前挑战</span>
            {nextChallenge}
          </b>
        </section>

        {v2Enabled && (
          <AgentWorkflowPanel
            events={agentEvents}
            activeStatus={agentStatus}
            isStreaming={isAgentStreaming}
          />
        )}

        <div key={activeNode.id} className="message-thread" aria-label={`${activeNode.title} 的独立对话线程`}>
          <div className="thread-title">
            <span>独立对话</span>
            <strong>{activeNode.title}</strong>
            <small>{messages.length} 条记录</small>
          </div>
          <div className="message-list" ref={messageListRef}>
            {v2Enabled && thoughts && thoughts.length > 0 && <ThoughtProcess thoughts={thoughts} />}
            {messages.length > 0 ? (
              visibleMessages.map((message, index) => {
                const canSpeak = ttsEnabled && message.role === "mentor" && Boolean(message.text.trim());
                return (
                  <div
                    key={`${message.node_id ?? activeNode.id}-${message.created_at ?? index}-${message.role}-${index}`}
                    className={`message ${message.role}`}
                  >
                    <div className="message-kicker">
                      <span>{message.role === "mentor" ? "AI 导师" : "学习者"}</span>
                      <div className="message-kicker-actions">
                        {canSpeak && (
                          <button
                            className="secondary-button compact voice-inline-button"
                            type="button"
                            onClick={() => onSpeakText(message.text)}
                            disabled={isBusy || isSpeaking}
                          >
                            <Volume2 size={14} />
                            <small>{isSpeaking ? "播报中" : "朗读"}</small>
                          </button>
                        )}
                        <b>{stageTitle}</b>
                      </div>
                    </div>
                    {message.thinking && <ThinkingBlock text={message.thinking} />}
                    <RichText text={message.text} />
                  </div>
                );
              })
            ) : (
              <div className="message-empty">AI 导师正在准备第一个问题。</div>
            )}
            <div className="message-scroll-anchor" ref={messageEndRef} aria-hidden="true" />
          </div>
        </div>

        <form className="composer" onSubmit={onSubmit}>
          <input
            value={draft}
            onChange={(event) => onDraftChange(event.target.value)}
            placeholder={isBusy ? "AI 正在处理..." : isCoolingDown ? "请稍等再发送..." : "回答导师的问题..."}
            disabled={isBusy}
          />
          <button
            className="icon-button dark"
            type="button"
            aria-label="发送回答"
            onClick={onSend}
            disabled={isBusy || isCoolingDown || !draft.trim()}
          >
            <Send size={18} />
          </button>
        </form>

        <div className="flow-actions">
          <button className="secondary-button" type="button" onClick={onConfuse} disabled={isBusy}>
            我听不懂
          </button>
          <button className="primary-button" type="button" onClick={onFeynman} disabled={isBusy}>
            进入费曼舞台
            <ArrowRight size={18} />
          </button>
        </div>
      </section>
    </div>
  );
}

function SegmentedTutorControl<T extends string>({
  label,
  value,
  options,
  disabled,
  onChange,
}: {
  label: string;
  value: T;
  options: Record<T, { label: string; caption: string }>;
  disabled: boolean;
  onChange: (value: T) => void;
}) {
  return (
    <div className="tutor-segment">
      <span>{label}</span>
      <SegmentedControl
        label={label}
        value={value}
        options={options}
        disabled={disabled}
        className="persona-switcher compact"
        onChange={onChange}
      />
    </div>
  );
}

function NodeCardStack({
  nodes,
  activeNode,
  messageCounts,
  isBusy,
  onSelectNode,
}: {
  nodes: KnowledgeNode[];
  activeNode: KnowledgeNode;
  messageCounts: Record<string, number>;
  isBusy: boolean;
  onSelectNode: (node: KnowledgeNode) => Promise<void>;
}) {
  const activeIndex = Math.max(nodes.findIndex((node) => node.id === activeNode.id), 0);
  const maxItems = 5;
  const start = Math.min(Math.max(activeIndex - 2, 0), Math.max(nodes.length - maxItems, 0));
  const cards = nodes.slice(start, start + maxItems);

  return (
    <div className="node-card-stack" aria-label="知识点列表">
      <div className="stack-heading">
        <p className="eyebrow">Node List</p>
        <strong>{activeNode.title}</strong>
      </div>
      <PagedList
        items={cards}
        pageSize={3}
        ariaLabel="知识点列表"
        className="node-strip-pager"
        renderItem={(node) => (
          <button
            type="button"
            key={node.id}
            className={`node-strip ${node.id === activeNode.id ? "active" : node.status}`}
            onClick={() => {
              if (isBusy || node.id === activeNode.id || node.status === "locked") return;
              void onSelectNode(node);
            }}
            aria-current={node.id === activeNode.id ? "true" : undefined}
            aria-disabled={isBusy || node.status === "locked"}
            title={`${node.title}：${node.summary}`}
          >
            <span className="node-strip-level">L{node.complexity}</span>
            <span className="node-strip-copy">
              <strong>{node.title}</strong>
              <em>{node.summary}</em>
            </span>
            <span className="node-strip-meta">
              <small>{statusLabel(node.status)}</small>
              <small>{messageCounts[node.id] ?? 0} 条</small>
            </span>
          </button>
        )}
      />
    </div>
  );
}

function ThinkingBlock({ text }: { text: string }) {
  return (
    <details className="thinking-block">
      <summary>公开思考</summary>
      <div className="thinking-body">
        <RichText text={text} />
      </div>
    </details>
  );
}

function stageFocusCopy(stage: NodeLearningProfile["stage"]): string {
  switch (stage) {
    case "warmup":
      return "先用自己的话解释概念，确认不是在背定义。";
    case "mechanism":
      return "把概念内部关系拆清楚，说明为什么这样推导。";
    case "transfer":
      return "换一个真实场景应用它，检查能否离开原材料。";
    case "correction":
      return "处理反例和常见误区，修正容易混淆的判断方向。";
    case "recap":
      return "压缩成一段可复述的话，为费曼输出做准备。";
    default:
      return "回答当前问题，导师会根据表现调整下一步。";
  }
}
