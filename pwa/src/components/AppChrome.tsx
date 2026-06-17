import { FormEvent, ReactNode } from "react";
import {
  ArrowRight,
  BrainCircuit,
  Check,
  CircleDot,
  FileText,
  History,
  RefreshCw,
  Settings,
  Trash2,
  User as UserIcon,
} from "lucide-react";
import { stageLabel } from "../app/sessionState";
import { RichText } from "./RichText";
import type {
  KnowledgeNode,
  MemoryEntry,
  Persona,
  Stage,
  User,
} from "../types";
import type { SessionSummary } from "../api";

function Header({
  stage,
  masteredCount,
  nodeCount,
  materialTitle,
  sessionId,
  user,
  resetWorkspace,
  logout,
  extraTopRight,
}: {
  stage: Stage;
  masteredCount: number;
  nodeCount: number;
  materialTitle: string;
  sessionId: string | null;
  user: User;
  resetWorkspace: () => void;
  logout: () => void;
  extraTopRight?: ReactNode;
}) {
  return (
    <header className="topbar">
      <div className="brand-lockup">
        <div className="brand-mark" aria-hidden="true">
          <CircleDot size={22} />
        </div>
        <div>
          <p className="eyebrow">AI Learning Workspace</p>
          <h1>Blank</h1>
          <span className="material-title">{materialTitle}</span>
        </div>
      </div>

      <div className="topbar-status">
        <div className="status-pill">
          <BrainCircuit size={16} />
          <span>{stageLabel(stage)}</span>
        </div>
        <div className="status-pill">
          <Check size={16} />
          <span>{masteredCount}/{nodeCount} 已掌握</span>
        </div>
        <div className="status-pill session-pill">
          <UserIcon size={16} />
          <span>{user.username} · {user.role === "admin" ? "管理员" : "学习者"}</span>
        </div>
        <div className="status-pill session-pill">
          <span>{sessionId ? "会话已记录" : "等待学习"}</span>
        </div>
        {extraTopRight}
        <button className="icon-button" type="button" onClick={resetWorkspace} aria-label="清空当前工作区">
          <RefreshCw size={18} />
        </button>
        <button className="secondary-button compact" type="button" onClick={logout}>
          退出
        </button>
      </div>
    </header>
  );
}

function StageButton({
  active,
  icon,
  label,
  onClick,
  disabled = false,
}: {
  active: boolean;
  icon: ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button className={`rail-button ${active ? "active" : ""}`} type="button" onClick={onClick} disabled={disabled}>
      {icon}
      <span>{label}</span>
    </button>
  );
}

function AuthScreen({
  mode,
  username,
  password,
  error,
  isBusy,
  onModeChange,
  onUsernameChange,
  onPasswordChange,
  onSubmit,
  onRestore,
}: {
  mode: "login" | "register";
  username: string;
  password: string;
  error: string;
  isBusy: boolean;
  onModeChange: (mode: "login" | "register") => void;
  onUsernameChange: (value: string) => void;
  onPasswordChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onRestore: () => void;
}) {
  return (
    <main className="auth-shell">
      <div className="background-grid" />
      <section className="auth-panel">
        <div>
          <p className="eyebrow">Blank Account</p>
          <h1>Blank</h1>
          <p>登录后学习历史、费曼诊断、认知记录和后台配置会持久保存到数据库。</p>
        </div>
        {error && <div className="error-banner inline">{error}</div>}
        <form className="auth-form" onSubmit={onSubmit}>
          <label>
            <span>用户名</span>
            <input
              value={username}
              minLength={2}
              maxLength={32}
              placeholder="中文、字母、数字或下划线"
              onChange={(event) => onUsernameChange(event.target.value)}
            />
          </label>
          <label>
            <span>密码</span>
            <input
              type="password"
              minLength={8}
              placeholder="至少 8 位，包含字母和数字"
              value={password}
              onChange={(event) => onPasswordChange(event.target.value)}
            />
          </label>
          <button className="primary-button" type="submit" disabled={isBusy}>
            {isBusy ? "处理中..." : mode === "login" ? "登录" : "注册并进入"}
            <ArrowRight size={18} />
          </button>
        </form>
        <div className="auth-switch">
          <button
            className={mode === "login" ? "active" : ""}
            type="button"
            onClick={() => onModeChange("login")}
          >
            登录
          </button>
          <button
            className={mode === "register" ? "active" : ""}
            type="button"
            onClick={() => onModeChange("register")}
          >
            注册
          </button>
          <button type="button" onClick={onRestore} disabled={isBusy}>
            恢复会话
          </button>
        </div>
      </section>
    </main>
  );
}

function SidePanel({
  sessions,
  activeSessionId,
  isBusy,
  memories,
  longTermCount,
  showMemories,
  evidenceNode,
  downgraded,
  failureCount,
  persona,
  onOpen,
  onDelete,
}: {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  isBusy: boolean;
  memories: MemoryEntry[];
  longTermCount: number;
  showMemories: boolean;
  evidenceNode?: KnowledgeNode | null;
  downgraded: boolean;
  failureCount: number;
  persona: Persona;
  onOpen: (session: SessionSummary) => void;
  onDelete: (session: SessionSummary) => void;
}) {
  return (
    <aside className={`side-panel ${showMemories ? "with-memory" : ""} ${evidenceNode ? "with-node-evidence" : ""}`}>
      <HistoryPanel
        sessions={sessions}
        activeSessionId={activeSessionId}
        isBusy={isBusy}
        onOpen={onOpen}
        onDelete={onDelete}
      />
      {evidenceNode && <NodeEvidenceBoard node={evidenceNode} />}
      {showMemories && (
        <section className="task-status-panel">
          <MemoryBoard memories={memories} longTermCount={longTermCount} />
          <DowngradeBox downgraded={downgraded} failureCount={failureCount} persona={persona} />
        </section>
      )}
    </aside>
  );
}

function NodeEvidenceBoard({ node }: { node: KnowledgeNode }) {
  const evidence = node.evidence || "当前节点暂无可展示原文证据；请重新解析包含 evidence 的材料以补齐。";
  const lengthClass = evidence.length > 520 ? "long" : evidence.length > 220 ? "medium" : "short";

  return (
    <section className={`node-evidence-board ${lengthClass}`} aria-label="选中节点证据">
      <div className="box-title">
        <FileText size={18} />
        <span>选中节点证据</span>
      </div>
      <strong>{node.title}</strong>
      <div className="node-evidence-scroll">
        <RichText text={evidence} />
      </div>
    </section>
  );
}

function HistoryPanel({
  sessions,
  activeSessionId,
  isBusy,
  onOpen,
  onDelete,
}: {
  sessions: SessionSummary[];
  activeSessionId: string | null;
  isBusy: boolean;
  onOpen: (session: SessionSummary) => void;
  onDelete: (session: SessionSummary) => void;
}) {
  return (
    <section className="history-panel">
      <div className="section-heading">
        <p className="eyebrow">History</p>
        <h3>
          <History size={20} />
          学习记录
        </h3>
      </div>
      <div className="history-list">
        {sessions.length === 0 && <p>暂无历史。创建会话后会自动记录。</p>}
        {sessions.map((session) => (
          <div key={session.id} className={`history-row ${session.id === activeSessionId ? "active" : ""}`}>
            <button type="button" className="history-open" onClick={() => onOpen(session)}>
              <strong>{session.material_title}</strong>
              <span>{session.mastered_count}/{session.node_count} 已掌握</span>
            </button>
            <button
              type="button"
              className="history-delete"
              aria-label={`删除 ${session.material_title}`}
              onClick={() => onDelete(session)}
              disabled={isBusy}
            >
              <Trash2 size={16} />
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

function EmptyStage({ onBack }: { onBack: () => void }) {
  return (
    <section className="empty-stage">
      <FileText size={34} />
      <h2>还没有可学习的材料</h2>
      <p>上传 PDF、文本或 Markdown 后，系统会生成知识节点，再进入拆解、学习、输出和掌握反馈。</p>
      <button className="primary-button" type="button" onClick={onBack}>
        返回上传
        <ArrowRight size={18} />
      </button>
    </section>
  );
}

function MemoryBoard({ memories, longTermCount }: { memories: MemoryEntry[]; longTermCount: number }) {
  const visible = memories.slice(-3).reverse();
  return (
    <section className="memory-board">
      <div className="box-title">
        <BrainCircuit size={18} />
        <span>任务记忆</span>
      </div>
      <div className="memory-rules">
        <strong>长期判断</strong>
        <span>连续卡顿、稳定偏好、明确目标、费曼薄弱点才进入长期。</span>
      </div>
      <div className="memory-list">
        {visible.length === 0 && <p>当前节点暂无记忆，系统不会展示预估记录。</p>}
        {visible.map((memory) => (
          <article className={`memory-chip ${memory.retention}`} key={memory.id}>
            <span>{memory.retention === "long" ? "长期" : memory.retention === "medium" ? "中期" : "短期"}</span>
            <strong>{memory.title}</strong>
            <p>{memory.reason || memory.body}</p>
          </article>
        ))}
      </div>
      <small>长期记忆 {longTermCount} 条</small>
    </section>
  );
}

function DowngradeBox({
  downgraded,
  failureCount,
  persona,
}: {
  downgraded: boolean;
  failureCount: number;
  persona: Persona;
}) {
  return (
    <div className={`downgrade-box ${downgraded ? "active" : ""}`}>
      <strong>自适应降维</strong>
      <span>
        {downgraded
          ? "已临时切换为大白话解释，降低当前知识点负荷。"
          : persona === "plain"
            ? "当前已使用大白话讲解，保持低负荷推进。"
            : `连续卡顿 ${failureCount}/2 次后自动降级；点“我听不懂”会按当前风格主动重讲。`}
      </span>
    </div>
  );
}

export {
  Header,
  StageButton,
  AuthScreen,
  SidePanel,
  HistoryPanel,
  EmptyStage,
  MemoryBoard,
  NodeEvidenceBoard,
  DowngradeBox,
};
