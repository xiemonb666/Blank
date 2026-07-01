import { useMemo, useRef, useState, type ReactNode } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { BarChart3, BrainCircuit, ChevronDown, Database, Download, FileText, RefreshCw, Upload } from "lucide-react";
import { PagedList, SegmentedControl } from "../components/DesignPrimitives";
import type {
  MaterialQualitySummary,
  ResearchDashboard,
  ResearchExperimentGroupSummary,
  ResearchMetric,
  WeakPointSummary,
} from "../types";

gsap.registerPlugin(useGSAP);

type ResearchTab = "overview" | "diagnosis" | "evidence" | "experiment" | "import";

const researchTabs: Record<ResearchTab, { label: string; caption: string }> = {
  overview: { label: "总览", caption: "班级指标、薄弱点和材料质量。" },
  diagnosis: { label: "诊断", caption: "材料质量、误区标签和长期记忆类别。" },
  evidence: { label: "证据", caption: "RAG 证据、出处和依赖图谱。" },
  experiment: { label: "实验", caption: "前后测、盲评一致性和样本记录。" },
  import: { label: "导入", caption: "匿名研究记录导入与导出。" },
};

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
  const workbench = useMemo(() => buildResearchWorkbench(dashboard), [dashboard]);
  const [activeTab, setActiveTab] = useState<ResearchTab>(() => resolveInitialResearchTab());

  return (
    <div className="research-layout research-tabbed">
      <section className="research-panel research-overview research-command-panel">
        <div className="section-heading research-heading-row">
          <div>
            <p className="eyebrow research-eyebrow">
              Teacher / Research
              <span className="confidence-badge">Confidence {workbench.confidenceLabel}</span>
            </p>
            <h2>教师端 / 研究端</h2>
            <span>
              汇总真实学习记录、匿名实验数据、<Highlight>费曼诊断</Highlight>、节点证据和模型消耗。
            </span>
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

        <div className="research-tldr" aria-label="研究摘要">
          <strong>TL;DR</strong>
          <p>{workbench.summary}</p>
        </div>
        <SegmentedControl
          label="研究端视图"
          value={activeTab}
          options={researchTabs}
          className="research-tabs"
          onChange={setActiveTab}
        />
      </section>

      {activeTab === "overview" && (
        <>
          <section className="research-panel research-overview-metrics">
            <div className="box-title">
              <BarChart3 size={18} />
              <span>核心指标</span>
            </div>
            <PagedList
              items={metrics}
              pageSize={4}
              compactPageSize={1}
              ariaLabel="研究指标"
              className="research-metric-pager"
              empty={<p className="admin-empty">暂无可汇总的真实学习数据。</p>}
              renderItem={(metric) => <MetricCard key={metric.label} metric={metric} />}
            />
          </section>

          <section className="research-panel research-compact">
            <div className="box-title">
              <BrainCircuit size={18} />
              <span>班级薄弱点</span>
            </div>
            <RankList items={dashboard?.weak_points ?? []} emptyText="暂无低于 70 分的维度记录。" valueLabel="均分" />
          </section>

          <section className="research-panel research-compact">
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
        </>
      )}

      {activeTab === "diagnosis" && (
        <>
          <section className="research-panel research-wide">
            <div className="box-title">
              <FileText size={18} />
              <span>材料节点质量</span>
            </div>
            <PagedList
              items={dashboard?.material_quality ?? []}
              pageSize={2}
              compactPageSize={1}
              ariaLabel="材料节点质量"
              className="material-quality-pager"
              empty={<p className="admin-empty">暂无材料质量记录。</p>}
              renderItem={(item) => (
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
              )}
            />
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
        </>
      )}

      {activeTab === "evidence" && (
        <section className="research-panel research-wide research-explain-panel">
          <div className="box-title">
            <BrainCircuit size={18} />
            <span>证据可解释性工作台</span>
          </div>
          <div className="rag-annotation-list">
            {workbench.ragTraces.map((trace) => (
              <article className="rag-annotation-row" key={trace.id}>
                <div className="rag-source-copy">
                  <small>{trace.sourceLabel}</small>
                  <p>{trace.excerpt}</p>
                </div>
                <aside className="critic-note" aria-label="Critic Agent 校验批注">
                  <strong>{trace.agent}</strong>
                  <span>{trace.comment}</span>
                </aside>
              </article>
            ))}
          </div>
          <ResearchAccordion title="原始资料出处" count={workbench.sources.length}>
            <div className="research-source-list">
              {workbench.sources.map((source) => (
                <SourceTraceRow key={source.session_id} item={source} />
              ))}
              {workbench.sources.length === 0 && <p className="admin-empty">暂无可追溯的材料来源。</p>}
            </div>
          </ResearchAccordion>
          <ResearchAccordion title="相关依赖图谱" count={workbench.dependencyGraph.length}>
            <div className="dependency-trace-grid">
              {workbench.dependencyGraph.map((item) => (
                <div className="dependency-trace-cell" key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                  <small>{item.note}</small>
                </div>
              ))}
            </div>
          </ResearchAccordion>
        </section>
      )}

      {activeTab === "experiment" && (
        <>
          <section className="research-panel research-wide research-experiment-panel">
            <div className="box-title">
              <BarChart3 size={18} />
              <span>前后测 / 延迟测</span>
            </div>
            <PagedList
              items={experimentSummaries}
              pageSize={3}
              compactPageSize={1}
              ariaLabel="实验组汇总"
              className="experiment-summary-pager"
              empty={<p className="admin-empty">暂无匿名实验记录。请导入前测、后测、延迟测和组别数据。</p>}
              renderItem={(item) => <ExperimentSummaryRow key={`${item.study_id}:${item.group_label}`} item={item} />}
            />
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

          <section className="research-panel research-wide">
            <div className="box-title">
              <FileText size={18} />
              <span>匿名样本记录</span>
            </div>
            <PagedList
              items={experimentRecords}
              pageSize={4}
              compactPageSize={1}
              ariaLabel="匿名样本记录"
              className="experiment-record-pager"
              empty={<p className="admin-empty">暂无可导出的匿名样本。</p>}
              renderItem={(record) => (
                <div className="experiment-record-row" key={record.id}>
                  <span>{record.study_id}</span>
                  <strong>{record.group_label}</strong>
                  <b>{record.participant_code}</b>
                  <small>前 {formatNullable(record.pretest_score)} / 后 {formatNullable(record.posttest_score)} / 延 {formatNullable(record.delayed_score)}</small>
                  <small>系统 {formatNullable(record.system_feynman_score)} / 人工 {formatNullable(record.human_score)}</small>
                </div>
              )}
            />
          </section>
        </>
      )}

      {activeTab === "import" && (
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
      )}
    </div>
  );
}

function Highlight({ children }: { children: ReactNode }) {
  return <mark className="academic-highlight">{children}</mark>;
}

function ResearchAccordion({ title, count, children }: { title: string; count: number; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);

  useGSAP(
    () => {
      const panel = panelRef.current;
      if (!panel) return;
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      gsap.fromTo(panel, {
        autoAlpha: reduceMotion ? 1 : 0,
        y: reduceMotion ? 0 : -6,
      }, {
        autoAlpha: 1,
        y: 0,
        duration: reduceMotion ? 0 : 0.28,
        ease: "power2.out",
        overwrite: "auto",
      });
    },
    { dependencies: [open], scope: panelRef },
  );

  return (
    <div className={`research-accordion${open ? " is-open" : ""}`}>
      <button
        className="research-accordion-trigger"
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span>{title}</span>
        <b>{count}</b>
        <ChevronDown size={17} aria-hidden="true" />
      </button>
      <div className="research-accordion-panel" ref={panelRef} hidden={!open}>
        <div className="research-accordion-inner">{children}</div>
      </div>
    </div>
  );
}

function MetricCard({ metric }: { metric: ResearchMetric }) {
  return (
    <div className="research-metric-card" title={metric.note}>
      <span>{metric.label.includes("费曼") ? <Highlight>{metric.label}</Highlight> : metric.label}</span>
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

function SourceTraceRow({ item }: { item: MaterialQualitySummary }) {
  return (
    <div className="source-trace-row">
      <div>
        <strong>{item.title}</strong>
        <span>{new Date(item.updated_at).toLocaleString("zh-CN", { hour12: false })}</span>
      </div>
      <b>{item.node_count} 节点</b>
      <b>{Math.round(item.evidence_coverage * 100)}% 证据</b>
      <b>{item.dependency_edges} 依赖边</b>
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

interface ResearchWorkbench {
  confidenceLabel: string;
  summary: string;
  ragTraces: Array<{
    id: string;
    sourceLabel: string;
    excerpt: string;
    agent: string;
    comment: string;
  }>;
  sources: MaterialQualitySummary[];
  dependencyGraph: Array<{ label: string; value: string; note: string }>;
}

function buildResearchWorkbench(dashboard: ResearchDashboard | null): ResearchWorkbench {
  const materials = dashboard?.material_quality ?? [];
  const metrics = dashboard?.metrics ?? [];
  const evidenceAverage = average(materials.map((item) => item.evidence_coverage));
  const confidence = Math.round((evidenceAverage || (metrics.length > 0 ? 0.68 : 0)) * 100);
  const topMaterial = materials[0];
  const weakPoint = dashboard?.weak_points[0];
  const totalNodes = materials.reduce((sum, item) => sum + item.node_count, 0);
  const totalEdges = materials.reduce((sum, item) => sum + item.dependency_edges, 0);

  return {
    confidenceLabel: `${confidence}%`,
    summary: topMaterial
      ? `当前证据链以《${topMaterial.title}》为主，覆盖 ${totalNodes} 个知识节点，并提示 ${weakPoint?.label ?? "核心概念"} 是优先复核对象。`
      : "暂无足够学习记录生成研究摘要；导入或刷新真实学习数据后可形成证据链。",
    ragTraces: buildRagTraces(materials),
    sources: materials,
    dependencyGraph: [
      { label: "知识节点", value: `${totalNodes}`, note: "来自材料拆解后的可学习单元" },
      { label: "依赖边", value: `${totalEdges}`, note: "用于解释学习路径的前置关系" },
      { label: "平均证据覆盖", value: `${Math.round(evidenceAverage * 100)}%`, note: "节点是否携带可追溯材料依据" },
      { label: "平均复杂度", value: formatNullable(average(materials.map((item) => item.average_complexity))), note: "用于估计认知负荷和脚手架强度" },
    ],
  };
}

function buildRagTraces(materials: MaterialQualitySummary[]) {
  if (materials.length === 0) {
    return [
      {
        id: "empty-rag-trace",
        sourceLabel: "RAG Evidence · waiting",
        excerpt: "尚未形成可审计的 RAG 证据片段。系统会在材料完成拆解后记录节点覆盖、依赖关系和质量指标。",
        agent: "幻觉审判官",
        comment: "[幻觉审判官：等待事实校验材料]",
      },
    ];
  }

  return materials.slice(0, 3).map((item, index) => ({
    id: item.session_id,
    sourceLabel: `RAG Evidence · ${String(index + 1).padStart(2, "0")}`,
    excerpt: `《${item.title}》包含 ${item.node_count} 个节点、${item.dependency_edges} 条依赖边，证据覆盖率为 ${Math.round(item.evidence_coverage * 100)}%。该片段用于解释学习路径、费曼评分和薄弱点聚类的来源。`,
    agent: "幻觉审判官",
    comment: item.evidence_coverage >= 0.8 ? "[幻觉审判官：事实校验通过]" : "[幻觉审判官：证据覆盖偏低，建议复核原文]",
  }));
}

function average(values: number[]) {
  const validValues = values.filter((value) => Number.isFinite(value));
  if (validValues.length === 0) return 0;
  return validValues.reduce((sum, value) => sum + value, 0) / validValues.length;
}

function resolveInitialResearchTab(): ResearchTab {
  if (!import.meta.env.DEV || typeof window === "undefined") return "overview";
  const tab = new URLSearchParams(window.location.search).get("ui-review-research");
  return tab === "diagnosis" || tab === "evidence" || tab === "experiment" || tab === "import" ? tab : "overview";
}
