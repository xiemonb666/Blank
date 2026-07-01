import { ChangeEvent, CSSProperties, FormEvent, useState } from "react";
import { ArrowRight, BarChart3, ClipboardList, Database, Download, FileUp, RefreshCw, Send, Users } from "lucide-react";
import type {
  OrganizationDashboard,
  OrganizationKnowledgeItem,
  OrganizationMemberReport,
  OrganizationMemberSummary,
} from "../types";

type OrganizationTab = "members" | "tasks" | "knowledge" | "research";

interface OrganizationStageProps {
  dashboard: OrganizationDashboard | null;
  members: OrganizationMemberSummary[];
  knowledge: OrganizationKnowledgeItem[];
  report: OrganizationMemberReport | null;
  taskTitle: string;
  taskDescription: string;
  taskContent: string;
  taskTargetMode: "all" | "selected";
  selectedTaskMemberIds: string[];
  isBusy: boolean;
  onTaskTitleChange: (value: string) => void;
  onTaskDescriptionChange: (value: string) => void;
  onTaskContentChange: (value: string) => void;
  onTaskTargetModeChange: (value: "all" | "selected") => void;
  onToggleTaskMember: (userId: string) => void;
  onRefresh: () => void;
  onExportTrace: () => void;
  onCreateTask: (event: FormEvent<HTMLFormElement>) => void;
  onUploadKnowledge: (event: ChangeEvent<HTMLInputElement>) => void;
  onDeleteKnowledge: (item: OrganizationKnowledgeItem) => void;
  onSelectMember: (member: OrganizationMemberSummary) => void;
}

export function OrganizationStage({
  dashboard,
  members,
  knowledge,
  report,
  taskTitle,
  taskDescription,
  taskContent,
  taskTargetMode,
  selectedTaskMemberIds,
  isBusy,
  onTaskTitleChange,
  onTaskDescriptionChange,
  onTaskContentChange,
  onTaskTargetModeChange,
  onToggleTaskMember,
  onRefresh,
  onExportTrace,
  onCreateTask,
  onUploadKnowledge,
  onDeleteKnowledge,
  onSelectMember,
}: OrganizationStageProps) {
  const [activeTab, setActiveTab] = useState<OrganizationTab>("members");
  const organization = dashboard?.organization;
  const research = dashboard?.dashboard;
  const metrics = research?.metrics ?? [];
  const assignableMembers = members.filter((member) => member.user.role === "org_member");
  const selectedSet = new Set(selectedTaskMemberIds);
  const taskTargetCount = taskTargetMode === "all" ? assignableMembers.length : selectedTaskMemberIds.length;

  return (
    <div className="organization-layout">
      <section className="admin-panel organization-hero">
        <div className="section-heading admin-heading-row">
          <div>
            <p className="eyebrow">Organization</p>
            <h2>{organization?.name ?? "组织管理台"}</h2>
            <span>组织 ID：{organization?.code ?? "读取中"} · 成员 {organization?.member_count ?? members.length} 人</span>
          </div>
          <div className="research-actions">
            <button className="secondary-button compact" type="button" onClick={onRefresh} disabled={isBusy}>
              <RefreshCw size={16} />
              刷新
            </button>
            <button className="secondary-button compact" type="button" onClick={onExportTrace} disabled={isBusy}>
              <Download size={16} />
              导出溯源
            </button>
          </div>
        </div>
        <div className="admin-status-strip" aria-label="组织统计">
          {metrics.slice(0, 4).map((metric) => (
            <div key={metric.label}>
              <span>{metric.label}</span>
              <strong>{formatMetric(metric.value, metric.unit)}</strong>
            </div>
          ))}
          {metrics.length === 0 && (
            <div>
              <span>学习记录</span>
              <strong>0</strong>
            </div>
          )}
        </div>
      </section>

      <nav className="organization-tabs" aria-label="组织管理标签">
        {(["members", "tasks", "knowledge", "research"] as OrganizationTab[]).map((tab) => (
          <button className={activeTab === tab ? "active" : ""} type="button" key={tab} onClick={() => setActiveTab(tab)}>
            {tabLabel(tab)}
          </button>
        ))}
      </nav>

      {activeTab === "members" && (
        <div className="organization-tab-grid">
          <section className="admin-panel organization-members">
            <div className="box-title">
              <Users size={18} />
              <span>成员学习情况</span>
            </div>
            <div className="organization-list">
              {members.map((member) => (
                <button
                  className={`organization-member-row ${report?.user.id === member.user.id ? "active" : ""}`}
                  type="button"
                  key={member.user.id}
                  onClick={() => onSelectMember(member)}
                >
                  <strong>{member.user.username}</strong>
                  <span>{member.user.role === "org_manager" ? "组织管理者" : "组织成员"}</span>
                  <b>{member.session_count} 份材料</b>
                  <b>{member.mastered_count}/{member.node_count} 已掌握</b>
                  <b>费曼 {Math.round(member.average_feynman_score)}</b>
                </button>
              ))}
              {members.length === 0 && <p className="admin-empty">暂无组织成员。</p>}
            </div>
          </section>

          <section className="admin-panel organization-report">
            <div className="box-title">
              <BarChart3 size={18} />
              <span>成员详细诊断</span>
            </div>
            {report ? (
              <>
                <div className="organization-report-header">
                  <strong>{report.user.username}</strong>
                  <span>{report.sessions.length} 份材料 · 平均费曼 {Math.round(report.average_feynman_score)}</span>
                </div>
                <div className="mini-score-list">
                  {report.dimension_scores.slice(0, 8).map((score, index) => (
                    <div className="mini-score-row" key={`${score.stage}-${index}`}>
                      <span>{score.label}</span>
                      <strong>{score.value}</strong>
                      <i style={{ "--score": `${Math.max(0, Math.min(100, score.value))}%` } as CSSProperties} />
                    </div>
                  ))}
                  {report.dimension_scores.length === 0 && <p className="admin-empty">暂无费曼维度记录。</p>}
                </div>
                <div className="organization-session-list">
                  {report.sessions.slice(0, 5).map((session) => (
                    <div className="organization-session-row" key={session.id}>
                      <strong>{session.material_title}</strong>
                      <span>{session.mastered_count}/{session.node_count} 已掌握</span>
                      <small>{formatDate(session.updated_at)}</small>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="admin-empty">选择一个成员查看学习详情和费曼能力图。</p>
            )}
          </section>
        </div>
      )}

      {activeTab === "tasks" && (
        <section className="admin-panel organization-task-panel">
          <div className="box-title">
            <Send size={18} />
            <span>批量下发学习任务</span>
          </div>
          <form className="admin-form organization-task-form" onSubmit={onCreateTask}>
            <label>
              <span>任务标题</span>
              <input value={taskTitle} onChange={(event) => onTaskTitleChange(event.target.value)} placeholder="例如：牛顿第二定律预习" />
            </label>
            <label>
              <span>说明</span>
              <input value={taskDescription} onChange={(event) => onTaskDescriptionChange(event.target.value)} placeholder="给成员看的任务说明" />
            </label>
            <label>
              <span>学习材料</span>
              <textarea value={taskContent} onChange={(event) => onTaskContentChange(event.target.value)} placeholder="粘贴组织要下发的材料文本" />
            </label>
            <div className="auth-role-switch organization-target-switch" aria-label="任务下发范围">
              <button className={taskTargetMode === "all" ? "active" : ""} type="button" onClick={() => onTaskTargetModeChange("all")}>
                全部成员
              </button>
              <button className={taskTargetMode === "selected" ? "active" : ""} type="button" onClick={() => onTaskTargetModeChange("selected")}>
                指定成员
              </button>
            </div>
            <div className={`organization-member-picker ${taskTargetMode === "all" ? "muted" : ""}`}>
              {assignableMembers.map((member) => (
                <label className="organization-check-row" key={member.user.id}>
                  <input
                    type="checkbox"
                    checked={selectedSet.has(member.user.id)}
                    disabled={isBusy || taskTargetMode === "all"}
                    onChange={() => onToggleTaskMember(member.user.id)}
                  />
                  <span>{member.user.username}</span>
                  <b>{member.session_count} 份材料</b>
                  <small>费曼 {Math.round(member.average_feynman_score)}</small>
                </label>
              ))}
              {assignableMembers.length === 0 && <p className="admin-empty">暂无可下发成员。</p>}
            </div>
            <button className="primary-button" type="submit" disabled={isBusy}>
              下发给 {taskTargetCount} 名成员
              <ArrowRight size={18} />
            </button>
          </form>
        </section>
      )}

      {activeTab === "knowledge" && (
        <section className="admin-panel organization-knowledge-panel">
          <div className="box-title">
            <Database size={18} />
            <span>组织专属知识库</span>
          </div>
          <label className="secondary-button organization-upload-button">
            <FileUp size={16} />
            上传资料
            <input type="file" accept=".txt,.md,.pdf,text/plain,application/pdf" onChange={onUploadKnowledge} disabled={isBusy} />
          </label>
          <div className="organization-list">
            {knowledge.map((item) => (
              <div className="admin-row" key={item.id}>
                <div>
                  <strong>{item.title}</strong>
                  <span>{item.chunk_count} 个片段</span>
                  <small>{formatDate(item.updated_at)}</small>
                </div>
                <button className="secondary-button compact danger" type="button" onClick={() => onDeleteKnowledge(item)} disabled={isBusy}>
                  删除
                </button>
              </div>
            ))}
            {knowledge.length === 0 && <p className="admin-empty">暂无组织知识库资料。</p>}
          </div>
        </section>
      )}

      {activeTab === "research" && (
        <section className="admin-panel organization-research-panel">
          <div className="box-title">
            <ClipboardList size={18} />
            <span>组织研究</span>
          </div>
          <div className="organization-research-grid">
            <div className="organization-research-card">
              <strong>费曼分布</strong>
              {(research?.feynman_distribution ?? []).map((bucket) => (
                <div className="distribution-row" key={bucket.label}>
                  <strong>{bucket.label}</strong>
                  <div>
                    <i style={{ "--score": `${Math.min(100, bucket.count * 12)}%` } as CSSProperties} />
                  </div>
                  <small>{bucket.count} 次</small>
                </div>
              ))}
              {(research?.feynman_distribution ?? []).length === 0 && <p className="admin-empty">暂无费曼分布。</p>}
            </div>
            <div className="organization-research-card">
              <strong>材料质量</strong>
              {(research?.material_quality ?? []).slice(0, 6).map((material) => (
                <div className="material-quality-row" key={material.session_id}>
                  <strong>{material.title}</strong>
                  <span>{material.node_count} 节点</span>
                  <b>{formatPercent(material.evidence_coverage)}</b>
                </div>
              ))}
              {(research?.material_quality ?? []).length === 0 && <p className="admin-empty">暂无材料质量记录。</p>}
            </div>
            <div className="organization-research-card organization-member-rank">
              <strong>成员明细</strong>
              {members.map((member) => (
                <div className="organization-session-row" key={member.user.id}>
                  <strong>{member.user.username}</strong>
                  <span>{member.mastered_count}/{member.node_count} 已掌握</span>
                  <small>费曼 {Math.round(member.average_feynman_score)}</small>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function tabLabel(tab: OrganizationTab) {
  switch (tab) {
    case "members":
      return "成员";
    case "tasks":
      return "任务";
    case "knowledge":
      return "知识库";
    case "research":
      return "组织研究";
  }
}

function formatMetric(value: number, unit: string) {
  if (unit === "ratio") return formatPercent(value);
  return `${Math.round(value)}${unit}`;
}

function formatPercent(value: number) {
  return `${Math.round(value * 100)}%`;
}

function formatDate(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
