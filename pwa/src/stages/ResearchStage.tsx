import { BarChart3, BrainCircuit, Database, Download, FileText, RefreshCw, Upload } from "lucide-react";
import type { ResearchDashboard, ResearchExperimentGroupSummary, ResearchMetric, WeakPointSummary } from "../types";

interface ResearchStageProps {
  dashboard: ResearchDashboard | null;
  isBusy: boolean;
  importDraft: string;
  onImportDraftChange: (value: string) => void;
  onRefresh: () => void;
  onImport: () => void;
  onExport: () => void;
  onExportBlindReview: () => void;
}

export function ResearchStage({
  dashboard,
  isBusy,
  importDraft,
  onImportDraftChange,
  onRefresh,
  onImport,
  onExport,
  onExportBlindReview,
}: ResearchStageProps) {
  const metrics = dashboard?.metrics ?? [];
  const hasEvidence = Boolean(dashboard && (metrics.some((metric) => metric.value > 0) || dashboard.material_quality.length > 0));
  const experimentSummaries = dashboard?.experiment_summaries ?? [];
  const experimentRecords = dashboard?.experiment_records ?? [];
  const agreement = dashboard?.score_agreement;

  return (
    <div className="research-layout">
      <section className="research-panel research-overview">
        <div className="section-heading research-heading-row">
          <div>
            <p className="eyebrow">Teacher / Research</p>
            <h2>教师端 / 研究端</h2>
            <span>汇总真实学习记录、匿名实验数据、费曼诊断、节点证据和模型消耗。</span>
          </div>
          <div className="research-actions">
            <button className="secondary-button compact" type="button" onClick={onRefresh} disabled={isBusy}>
              <RefreshCw size={16} />
              刷新
            </button>
            <button className="secondary-button compact" type="button" onClick={onExport} disabled={isBusy}>
              <Download size={16} />
              匿名导出
            </button>
            <button className="secondary-button compact" type="button" onClick={onExportBlindReview} disabled={isBusy}>
              <Download size={16} />
              盲评答卷
            </button>
          </div>
        </div>

        <div className="research-metric-grid">
          {metrics.map((metric) => (
            <MetricCard key={metric.label} metric={metric} />
          ))}
          {metrics.length === 0 && <p className="admin-empty">暂无可汇总的真实学习数据。</p>}
        </div>
      </section>

      <section className="research-panel">
        <div className="box-title">
          <BrainCircuit size={18} />
          <span>班级薄弱点</span>
        </div>
        <RankList items={dashboard?.weak_points ?? []} emptyText="暂无低于 70 分的维度记录。" valueLabel="均分" />
      </section>

      <section className="research-panel">
        <div className="box-title">
          <BarChart3 size={18} />
          <span>费曼评分分布</span>
        </div>
        <div className="distribution-bars">
          {(dashboard?.feynman_distribution ?? []).map((bucket) => {
            const maxCount = Math.max(...(dashboard?.feynman_distribution ?? []).map((item) => item.count), 1);
            return (
              <div className="distribution-row" key={bucket.label}>
                <span>{bucket.label}</span>
                <div>
                  <i style={{ inlineSize: `${Math.max(4, (bucket.count / maxCount) * 100)}%` }} />
                </div>
                <strong>{bucket.count}</strong>
              </div>
            );
          })}
          {!hasEvidence && <p className="admin-empty">暂无费曼评分。</p>}
        </div>
      </section>

      <section className="research-panel research-wide">
        <div className="box-title">
          <FileText size={18} />
          <span>材料节点质量</span>
        </div>
        <div className="material-quality-list">
          {(dashboard?.material_quality ?? []).map((item) => (
            <div className="material-quality-row" key={item.session_id}>
              <div>
                <strong>{item.title}</strong>
                <span>{new Date(item.updated_at).toLocaleString("zh-CN", { hour12: false })}</span>
              </div>
              <b>{item.node_count} 节点</b>
              <b>{Math.round(item.evidence_coverage * 100)}% 证据</b>
              <b>{item.dependency_edges} 依赖</b>
              <b>复杂度 {item.average_complexity.toFixed(1)}</b>
            </div>
          ))}
          {(dashboard?.material_quality ?? []).length === 0 && <p className="admin-empty">暂无材料质量记录。</p>}
        </div>
      </section>

      <section className="research-panel">
        <div className="box-title">
          <Database size={18} />
          <span>常见误区</span>
        </div>
        <RankList items={dashboard?.common_misconceptions ?? []} emptyText="暂无误区标签。" valueLabel="次数" />
      </section>

      <section className="research-panel">
        <div className="box-title">
          <Database size={18} />
          <span>长期记忆类别</span>
        </div>
        <div className="memory-category-list">
          {(dashboard?.memory_categories ?? []).map((item) => (
            <div className="memory-category-row" key={item.category}>
              <span>{memoryCategoryLabel(item.category)}</span>
              <strong>{item.count}</strong>
              <small>{item.long_term_count} 条长期</small>
            </div>
          ))}
          {(dashboard?.memory_categories ?? []).length === 0 && <p className="admin-empty">暂无记忆沉淀。</p>}
        </div>
      </section>

      <section className="research-panel research-wide research-experiment-panel">
        <div className="box-title">
          <BarChart3 size={18} />
          <span>前后测 / 延迟测</span>
        </div>
        <div className="experiment-summary-list">
          {experimentSummaries.map((item) => (
            <ExperimentSummaryRow key={`${item.study_id}:${item.group_label}`} item={item} />
          ))}
          {experimentSummaries.length === 0 && <p className="admin-empty">暂无匿名实验记录。请导入前测、后测、延迟测和组别数据。</p>}
        </div>
      </section>

      <section className="research-panel">
        <div className="box-title">
          <BrainCircuit size={18} />
          <span>人工盲评一致性</span>
        </div>
        <div className="agreement-grid">
          <MetricPill label="配对样本" value={agreement ? `${agreement.paired_count}` : "0"} />
          <MetricPill label="相关系数" value={formatNullable(agreement?.correlation, 3)} />
          <MetricPill label="平均差距" value={formatNullable(agreement?.mean_absolute_gap)} />
          <MetricPill label="系统均分" value={formatNullable(agreement?.system_average)} />
          <MetricPill label="人工均分" value={formatNullable(agreement?.human_average)} />
        </div>
      </section>

      <section className="research-panel research-import-panel">
        <div className="box-title">
          <Upload size={18} />
          <span>导入匿名研究记录</span>
        </div>
        <div className="research-import-body">
          <textarea
            value={importDraft}
            onChange={(event) => onImportDraftChange(event.target.value)}
            placeholder='[{"study_id":"study-a","participant_code":"p001","group_label":"Blank","pretest_score":48,"posttest_score":82,"delayed_score":74,"system_feynman_score":80,"human_score":78}]'
            disabled={isBusy}
          />
          <button className="primary-button" type="button" onClick={onImport} disabled={isBusy || !importDraft.trim()}>
            <Upload size={17} />
            导入
          </button>
        </div>
      </section>

      <section className="research-panel research-wide">
        <div className="box-title">
          <FileText size={18} />
          <span>匿名样本记录</span>
        </div>
        <div className="experiment-record-list">
          {experimentRecords.map((record) => (
            <div className="experiment-record-row" key={record.id}>
              <span>{record.study_id}</span>
              <strong>{record.group_label}</strong>
              <b>{record.participant_code}</b>
              <small>前 {formatNullable(record.pretest_score)} / 后 {formatNullable(record.posttest_score)} / 延 {formatNullable(record.delayed_score)}</small>
              <small>系统 {formatNullable(record.system_feynman_score)} / 人工 {formatNullable(record.human_score)}</small>
            </div>
          ))}
          {experimentRecords.length === 0 && <p className="admin-empty">暂无可导出的匿名样本。</p>}
        </div>
      </section>
    </div>
  );
}

function MetricCard({ metric }: { metric: ResearchMetric }) {
  return (
    <div className="research-metric-card" title={metric.note}>
      <span>{metric.label}</span>
      <strong>{formatMetricValue(metric)}</strong>
      <small>{metric.note}</small>
    </div>
  );
}

function RankList({ items, emptyText, valueLabel }: { items: WeakPointSummary[]; emptyText: string; valueLabel: string }) {
  if (items.length === 0) {
    return <p className="admin-empty">{emptyText}</p>;
  }
  return (
    <div className="research-rank-list">
      {items.map((item) => (
        <div className="research-rank-row" key={item.label}>
          <span>{item.label}</span>
          <strong>{item.count}</strong>
          <small>{valueLabel} {item.average_score > 0 ? item.average_score.toFixed(1) : item.count}</small>
        </div>
      ))}
    </div>
  );
}

function ExperimentSummaryRow({ item }: { item: ResearchExperimentGroupSummary }) {
  return (
    <div className="experiment-summary-row">
      <div>
        <strong>{item.group_label}</strong>
        <span>{item.study_id} · {item.participants} 人</span>
      </div>
      <b>前测 {formatNullable(item.pretest_average)}</b>
      <b>后测 {formatNullable(item.posttest_average)}</b>
      <b>延迟 {formatNullable(item.delayed_average)}</b>
      <b>提升 {formatSigned(item.average_gain)}</b>
      <b>保持 {formatRatio(item.retention_rate)}</b>
    </div>
  );
}

function MetricPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="agreement-pill">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatMetricValue(metric: ResearchMetric) {
  if (metric.unit === "ratio") return `${Math.round(metric.value * 100)}%`;
  if (metric.unit === "token") return formatTokenCount(metric.value);
  if (metric.unit === "分") return metric.value.toFixed(1);
  return `${Number.isInteger(metric.value) ? metric.value.toFixed(0) : metric.value.toFixed(1)}${metric.unit}`;
}

function formatTokenCount(value: number) {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}m`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(value >= 10_000 ? 0 : 1)}k`;
  return `${Math.round(value)}`;
}

function formatNullable(value: number | null | undefined, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return value.toFixed(digits);
}

function formatSigned(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

function formatRatio(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${Math.round(value * 100)}%`;
}

function memoryCategoryLabel(category: string) {
  if (category === "cognitive") return "认知卡点";
  if (category === "long_term") return "长期画像";
  if (category === "preference") return "学习偏好";
  if (category === "fact") return "事实记录";
  if (category === "session") return "会话摘要";
  return category;
}
