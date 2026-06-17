import { ArrowRight, Check, Sparkles } from "lucide-react";
import { RichText } from "../components/RichText";
import type { DiagnosticItem, DimensionScore, KnowledgeNode, QuestionDiagnosticItem } from "../types";

interface MasteryStageProps {
  activeNode: KnowledgeNode;
  nextNode?: KnowledgeNode;
  diagnostics: DiagnosticItem[];
  questionDiagnostics: QuestionDiagnosticItem[];
  dimensionScores: DimensionScore[];
  passed: boolean;
  nextReason: string;
  onContinue: () => void;
  isBusy: boolean;
}

export function MasteryStage({
  activeNode,
  nextNode,
  diagnostics,
  questionDiagnostics,
  dimensionScores,
  passed,
  nextReason,
  onContinue,
  isBusy,
}: MasteryStageProps) {
  const hasDiagnostics = diagnostics.length > 0;
  const nextTitle = passed ? nextNode?.title ?? "暂无下一节点" : "继续巩固当前节点";
  const reason = nextReason || (hasDiagnostics ? "本轮诊断已完成，请根据逐题分数决定下一步。" : "完成逐题输出后，这里会显示是否解锁下一节点。");
  const allEvidence = [...dimensionScores, ...questionDiagnostics, ...diagnostics];
  const weakest = allEvidence.reduce<DimensionScore | QuestionDiagnosticItem | DiagnosticItem | null>(
    (current, item) => (!current || item.value < current.value ? item : current),
    null,
  );
  const requiredFix = weakest?.note ?? reason;

  return (
    <div className="mastery-layout">
      <section className="mastery-summary">
        <div className="mastery-mark">
          {hasDiagnostics && passed ? <Check size={34} /> : <Sparkles size={34} />}
        </div>
        <p className="eyebrow">The Mastery</p>
        <h2>{hasDiagnostics ? (passed ? `${activeNode.title} 已点亮` : `${activeNode.title} 需继续练习`) : "等待逐题诊断"}</h2>
        <RichText
          text={
            hasDiagnostics
              ? reason
              : "逐题回答完成后，这里会显示真实诊断、低分考点和下一步是否解锁。"
          }
        />
      </section>

      <section className={`diagnostic-board ${hasDiagnostics ? "" : "empty"}`}>
        {hasDiagnostics ? (
          <>
            <div className="result-brief">
              <div>
                <span>最低项</span>
                <strong>{weakest?.label ?? "暂无"}</strong>
                <small>{weakest ? `${weakest.value} 分` : "等待评分"}</small>
              </div>
              <div>
                <span>必须补的一点</span>
                <div className="result-fix">
                  <RichText text={requiredFix} />
                </div>
              </div>
            </div>

            <div className="score-ribbon" aria-label="四维通关分数">
              {dimensionScores.map((item) => (
                <div key={item.stage}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>

            <details className="evidence-details">
              <summary>
                <span>展开逐题证据</span>
                <b>{questionDiagnostics.length + diagnostics.length} 条</b>
              </summary>
              <div className="evidence-list">
                <div className="diagnostic-section">
                  <strong>逐题掌握</strong>
                  <span>每个问题单独评分，低分项就是下一轮要补的点。</span>
                </div>
                {questionDiagnostics.map((item) => (
                  <div className="diagnostic-row compact" key={`${item.question_id}-${item.label}`}>
                    <div>
                      <strong>{item.label}</strong>
                      <span>
                        <RichText text={item.note} />
                      </span>
                    </div>
                    <b>{item.value}</b>
                  </div>
                ))}
                <div className="diagnostic-section">
                  <strong>总评</strong>
                  <span>总评只用于判断能否继续推进，不替代逐题低分项。</span>
                </div>
                {diagnostics.map((item) => (
                  <div className="diagnostic-row" key={item.label}>
                    <div>
                      <strong>{item.label}</strong>
                      <span>
                        <RichText text={item.note} />
                      </span>
                    </div>
                    <b>{item.value}</b>
                  </div>
                ))}
              </div>
            </details>
          </>
        ) : (
          <div className="empty-diagnostics">
            <strong>暂无诊断</strong>
            <span>当前节点还没有完成逐题输出，不展示预估分数。</span>
          </div>
        )}
      </section>

      <section className="next-panel">
        <p className="eyebrow">Recommended Next</p>
        <h3>{hasDiagnostics ? nextTitle : "等待诊断完成"}</h3>
        <RichText
          text={
            hasDiagnostics
              ? passed && nextNode
                ? `${reason} ${nextNode.summary}`
                : reason
              : "完成逐题输出后，系统会明确说明：未达标、已解锁下一节点，或学习路径已完成。"
          }
        />
        {hasDiagnostics && passed && nextNode ? (
          <button className="primary-button" type="button" onClick={onContinue} disabled={isBusy}>
            继续下一节点
            <ArrowRight size={18} />
          </button>
        ) : (
          <div className="locked-action" role="status" aria-live="polite">
            {hasDiagnostics && !passed ? "先补当前节点" : "等待诊断"}
          </div>
        )}
      </section>
    </div>
  );
}
