import { defaultNodeProfile, stageLabelText } from "../app/sessionState";
import { RichText } from "../components/RichText";
import type {
  DimensionScore,
  FeynmanAnswer,
  FeynmanQuestion,
  KnowledgeNode,
  MemoryEntry,
  NodeLearningProfile,
  QuestionDiagnosticItem,
} from "../types";

interface EvidenceStageProps {
  nodes: KnowledgeNode[];
  activeNode: KnowledgeNode;
  messageCounts: Record<string, number>;
  profiles: Record<string, NodeLearningProfile>;
  questionsByNodeId: Record<string, FeynmanQuestion[]>;
  answersByNodeId: Record<string, Record<string, FeynmanAnswer>>;
  dimensionScores: DimensionScore[];
  questionDiagnostics: QuestionDiagnosticItem[];
  memories: MemoryEntry[];
}

export function EvidenceStage({
  nodes,
  activeNode,
  messageCounts,
  profiles,
  questionsByNodeId,
  answersByNodeId,
  dimensionScores,
  questionDiagnostics,
  memories,
}: EvidenceStageProps) {
  const dependencyCount = nodes.reduce((total, node) => total + node.deps.length, 0);
  const totalMessages = nodes.reduce((total, node) => total + (messageCounts[node.id] ?? 0), 0);
  const availableCount = nodes.filter((node) => node.status === "available" || node.status === "active" || node.status === "mastered").length;
  const masteredCount = nodes.filter((node) => node.status === "mastered").length;
  const allQuestions = Object.values(questionsByNodeId).flat();
  const answeredCount = Object.values(answersByNodeId).reduce(
    (total, answerMap) => total + Object.values(answerMap).filter((answer) => answer.answer.trim()).length,
    0,
  );
  const downgradedNodes = nodes.filter((node) => (profiles[node.id]?.failures ?? 0) >= 2).length;
  const confusionRequests = nodes.reduce((total, node) => total + (profiles[node.id]?.confusion_requests ?? 0), 0);
  const confusionResolved = nodes.reduce((total, node) => total + (profiles[node.id]?.confusion_resolved ?? 0), 0);
  const confusionUnresolved = nodes.reduce((total, node) => total + (profiles[node.id]?.confusion_unresolved ?? 0), 0);
  const weakScore = [...dimensionScores, ...questionDiagnostics].reduce<DimensionScore | QuestionDiagnosticItem | null>(
    (current, item) => (!current || item.value < current.value ? item : current),
    null,
  );
  const longTermCount = memories.filter((memory) => memory.retention === "long" || memory.scope === "long_term").length;
  const activeProfile = profiles[activeNode.id] ?? defaultNodeProfile(activeNode);
  const hasFeynmanEvidence = dimensionScores.length > 0 || questionDiagnostics.length > 0;
  const radarItems = buildMasteryRadar({
    activeProfile,
    dimensionScores,
    questionDiagnostics,
    questions: questionsByNodeId[activeNode.id] ?? [],
    answers: answersByNodeId[activeNode.id] ?? {},
  });
  const radarPoints = radarPolygonPoints(radarItems.map((item) => item.value));
  const radarAxisPoints = radarItems.map((_, index) => radarPointFor(index, radarItems.length, 92));
  const evidenceChain = [
    {
      label: "解析结构",
      value: `${nodes.length} 节点`,
      detail: `${dependencyCount} 条依赖`,
    },
    {
      label: "学习过程",
      value: `${totalMessages} 轮`,
      detail: confusionRequests > 0 ? `听不懂 ${confusionResolved}/${confusionRequests} 已解决` : downgradedNodes > 0 ? `${downgradedNodes} 个节点降维` : "未触发降维",
    },
    {
      label: "费曼输出",
      value: `${answeredCount}/${allQuestions.length || 0}`,
      detail: hasFeynmanEvidence ? `最低项 ${weakScore?.label ?? "暂无"}` : "等待评分证据",
    },
    {
      label: "记忆沉淀",
      value: `${memories.length} 条`,
      detail: `${longTermCount} 条长期`,
    },
  ];

  return (
    <div className="evidence-layout">
      <section className="evidence-hero">
        <p className="eyebrow">Evidence Dashboard</p>
        <h2>学习证据看板</h2>
        <RichText text="当前看板只统计这一次真实学习记录：解析结构、学习过程、费曼输出和记忆系统。没有发生的数据不会显示成预估值。" />
      </section>

      <section className="evidence-chain" aria-label="学习证据链">
        {evidenceChain.map((item, index) => (
          <article key={item.label} className={index === 0 ? "active" : ""}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <div>
              <strong>{item.label}</strong>
              <b>{item.value}</b>
              <small>{item.detail}</small>
            </div>
          </article>
        ))}
      </section>

      <section className="evidence-grid">
        <article className="evidence-card primary">
          <span>材料解析质量</span>
          <strong>{nodes.length}</strong>
          <p>知识节点</p>
          <small>{dependencyCount} 条依赖，{availableCount}/{nodes.length || 0} 个节点已解锁。</small>
        </article>
        <article className="evidence-card">
          <span>学习过程</span>
          <strong>{totalMessages}</strong>
          <p>消息记录</p>
          <small>
            {confusionRequests > 0
              ? `我听不懂 ${confusionRequests} 次；模型判断解决 ${confusionResolved} 次，待解决 ${confusionUnresolved} 次。`
              : downgradedNodes > 0
                ? `${downgradedNodes} 个节点触发过降维。`
                : "当前没有降维触发记录。"}
          </small>
        </article>
        <article className="evidence-card">
          <span>费曼输出</span>
          <strong>{answeredCount}/{allQuestions.length}</strong>
          <p>已回答题目</p>
          <small>{hasFeynmanEvidence ? `最低分项：${weakScore?.label ?? "暂无"} ${weakScore?.value ?? ""}` : "完成输出后才展示评分证据。"}</small>
        </article>
        <article className="evidence-card">
          <span>记忆系统</span>
          <strong>{memories.length}</strong>
          <p>真实记忆条目</p>
          <small>{longTermCount} 条长期记忆；无触发时不创建预估记录。</small>
        </article>
      </section>

      <section className="evidence-detail">
        <div className="evidence-node">
          <span>当前节点</span>
          <strong>{activeNode.title}</strong>
          <RichText text={activeNode.summary} />
          <small>
            当前关卡：{stageLabelText(activeProfile.stage)} · 连续卡顿 {activeProfile.failures} 次 · 我听不懂 {activeProfile.confusion_requests} 次 · 已解决 {activeProfile.confusion_resolved} 次
          </small>
        </div>
        <div className="evidence-node">
          <span>掌握进度</span>
          <strong>{masteredCount}/{nodes.length || 0}</strong>
          <p>{masteredCount > 0 ? "已有节点通过费曼诊断。" : "还没有节点通过费曼诊断。"}</p>
          <small>掌握状态来自后端评分写回，不由前端预填。</small>
        </div>
      </section>

      <section className="mastery-radar-panel" aria-label="掌握雷达图">
        <div className="radar-copy">
          <span>Mastery Radar</span>
          <strong>掌握雷达</strong>
          <p>根据当前节点的费曼维度、逐题证据和卡顿恢复记录生成；缺失维度按 0 处理，不补假数据。</p>
        </div>
        <div className="radar-chart-wrap">
          <svg className="radar-chart" viewBox="0 0 240 240" role="img" aria-label="当前节点掌握雷达图">
            {[0.25, 0.5, 0.75, 1].map((scale) => (
              <polygon
                key={scale}
                points={radarPolygonPoints(new Array(radarItems.length).fill(Math.round(scale * 100)))}
                className="radar-grid-shape"
              />
            ))}
            {radarAxisPoints.map((point, index) => (
              <line key={radarItems[index].label} x1="120" y1="120" x2={point.x} y2={point.y} className="radar-axis" />
            ))}
            <polygon points={radarPoints} className="radar-value-shape" />
            {radarItems.map((item, index) => {
              const point = radarPointFor(index, radarItems.length, item.value * 0.92);
              const label = radarPointFor(index, radarItems.length, 108);
              return (
                <g key={item.label}>
                  <circle cx={point.x} cy={point.y} r="4" className="radar-dot" />
                  <text x={label.x} y={label.y} textAnchor={label.x < 112 ? "end" : label.x > 128 ? "start" : "middle"} dominantBaseline="middle">
                    {item.shortLabel}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
        <div className="radar-axis-list">
          {radarItems.map((item) => (
            <div key={item.label}>
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <small>{item.note}</small>
            </div>
          ))}
        </div>
      </section>

      {!hasFeynmanEvidence && (
        <section className="evidence-empty">
          <strong>暂无费曼评分证据</strong>
          <span>完成逐题输出后，这里会显示四维得分、最低分考点和逐题诊断。</span>
        </section>
      )}
    </div>
  );
}

interface MasteryRadarInput {
  activeProfile: NodeLearningProfile;
  dimensionScores: DimensionScore[];
  questionDiagnostics: QuestionDiagnosticItem[];
  questions: FeynmanQuestion[];
  answers: Record<string, FeynmanAnswer>;
}

interface RadarItem {
  label: string;
  shortLabel: string;
  value: number;
  note: string;
}

function buildMasteryRadar(input: MasteryRadarInput): RadarItem[] {
  const scoreForStage = (stage: "warmup" | "mechanism" | "transfer" | "correction") => {
    const dimension = input.dimensionScores.find((item) => item.stage === stage);
    const profileScore = input.activeProfile.dimension_scores[stage];
    const diagnosticValues = input.questionDiagnostics
      .filter((item) => item.stage === stage || (stage === "correction" && item.stage === "recap"))
      .map((item) => item.value);
    if (dimension) return clampScore(dimension.value);
    if (typeof profileScore === "number") return clampScore(profileScore);
    if (diagnosticValues.length > 0) return clampScore(Math.round(diagnosticValues.reduce((sum, value) => sum + value, 0) / diagnosticValues.length));
    return 0;
  };
  const answered = Object.values(input.answers).filter((answer) => answer.answer.trim()).length;
  const evidenceCoverage = input.questions.length > 0 ? Math.round((answered / input.questions.length) * 100) : 0;
  const resiliencePenalty = input.activeProfile.failures * 14 + input.activeProfile.confusion_unresolved * 20;
  const resilienceBonus = input.activeProfile.confusion_resolved * 8 + input.activeProfile.streak * 6;
  const resilience = clampScore(70 - resiliencePenalty + resilienceBonus);
  return [
    { label: "基础理解", shortLabel: "基础", value: scoreForStage("warmup"), note: "来自 warmup 维度、逐题诊断或节点画像。" },
    { label: "机制解释", shortLabel: "机制", value: scoreForStage("mechanism"), note: "衡量能否讲清内部因果和步骤。" },
    { label: "迁移应用", shortLabel: "迁移", value: scoreForStage("transfer"), note: "衡量能否把节点用到新场景。" },
    { label: "纠错复述", shortLabel: "纠错", value: scoreForStage("correction"), note: "包含 correction 与 recap 的表现。" },
    { label: "学习韧性", shortLabel: "韧性", value: resilience, note: "由卡顿、听不懂解决数和连续推进记录推导。" },
    { label: "证据完整度", shortLabel: "证据", value: clampScore(evidenceCoverage), note: "按当前节点逐题回答覆盖率计算。" },
  ];
}

function clampScore(value: number) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, Math.round(value)));
}

function radarPointFor(index: number, total: number, score: number) {
  const radius = Math.max(0, Math.min(100, score)) * 0.92;
  const angle = -Math.PI / 2 + (Math.PI * 2 * index) / total;
  return {
    x: 120 + Math.cos(angle) * radius,
    y: 120 + Math.sin(angle) * radius,
  };
}

function radarPolygonPoints(values: number[]) {
  return values
    .map((value, index) => {
      const point = radarPointFor(index, values.length, value);
      return `${point.x.toFixed(1)},${point.y.toFixed(1)}`;
    })
    .join(" ");
}
