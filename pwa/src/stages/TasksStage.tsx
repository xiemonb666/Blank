import { ArrowRight, ClipboardList, RefreshCw } from "lucide-react";
import type { OrganizationTaskAssignment } from "../types";

interface TasksStageProps {
  assignments: OrganizationTaskAssignment[];
  isBusy: boolean;
  onRefresh: () => void;
  onStart: (assignment: OrganizationTaskAssignment) => void;
}

export function TasksStage({ assignments, isBusy, onRefresh, onStart }: TasksStageProps) {
  return (
    <div className="tasks-layout">
      <section className="admin-panel tasks-panel">
        <div className="section-heading admin-heading-row">
          <div>
            <p className="eyebrow">Organization Tasks</p>
            <h2>我的组织任务</h2>
            <span>组织下发的学习材料会生成独立学习记录，费曼验证结果会回到组织统计。</span>
          </div>
          <button className="secondary-button compact" type="button" onClick={onRefresh} disabled={isBusy}>
            <RefreshCw size={16} />
            刷新
          </button>
        </div>

        <div className="organization-list">
          {assignments.map((assignment) => (
            <article className="task-assignment-row" key={assignment.id}>
              <div>
                <ClipboardList size={18} />
                <div>
                  <strong>{assignment.task?.title ?? "组织学习任务"}</strong>
                  <span>{assignment.task?.description || assignment.task?.material_title || "等待开始"}</span>
                  <small>{assignment.status === "started" ? "已开始" : "待开始"} · {new Date(assignment.assigned_at).toLocaleString("zh-CN", { hour12: false })}</small>
                </div>
              </div>
              <button className="primary-button compact" type="button" onClick={() => onStart(assignment)} disabled={isBusy}>
                {assignment.session_id ? "继续" : "开始"}
                <ArrowRight size={16} />
              </button>
            </article>
          ))}
          {assignments.length === 0 && <p className="admin-empty">暂无组织任务。</p>}
        </div>
      </section>
    </div>
  );
}
