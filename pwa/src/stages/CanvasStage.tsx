import { ChangeEvent, DragEvent, FormEvent, ReactNode } from "react";
import { ArrowRight, FileText, Layers3, Network, PenLine, UploadCloud } from "lucide-react";
import { ParseStatus, type ParseMeta } from "../components/ParseStatus";
import type { ParseJob } from "../api";

interface CanvasStageProps {
  parseProgress: number;
  parseMeta: ParseMeta;
  parseStatus: ParseJob["status"];
  isBusy: boolean;
  isParsing: boolean;
  hasSession: boolean;
  topicDraft: string;
  onTopicDraftChange: (value: string) => void;
  onTopicSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onUpload: (event: ChangeEvent<HTMLInputElement>) => void;
  onDrop: (event: DragEvent<HTMLLabelElement>) => void;
  onOpenMap: () => void;
}

export function CanvasStage({
  parseProgress,
  parseMeta,
  parseStatus,
  isBusy,
  isParsing,
  hasSession,
  topicDraft,
  onTopicDraftChange,
  onTopicSubmit,
  onUpload,
  onDrop,
  onOpenMap,
}: CanvasStageProps) {
  const textState = pipelineState(parseProgress, parseStatus, 5, 30, isParsing);
  const sliceState = pipelineState(parseProgress, parseStatus, 30, 78, isParsing, "生成完成");
  const graphState = pipelineState(parseProgress, parseStatus, 78, 100, isParsing);

  return (
    <div className="canvas-layout">
      <section className="hero-panel">
        <div className="hero-copy">
          <p className="eyebrow">Input &gt; Graph &gt; Socratic Flow &gt; Feynman</p>
          <h2>从一片空白开始，把想学的内容拆成可掌握的路径。</h2>
          <p>
            输入主题或上传学习材料后，系统会生成知识节点路径，再进入拆解、学习、输出和掌握反馈。
          </p>
        </div>

        <div className="input-choice-grid" aria-busy={isParsing}>
          <form className={`topic-form ${isParsing ? "parsing" : ""}`} onSubmit={onTopicSubmit}>
            <div className="input-mode-heading">
              <span className="mode-icon"><PenLine size={18} /></span>
              <div>
                <strong>直接输入想学的内容</strong>
                <small>适合从一个主题开始生成学习路径</small>
              </div>
            </div>
            <textarea
              value={topicDraft}
              onChange={(event) => onTopicDraftChange(event.target.value)}
              placeholder="例如：微积分的积分、Transformer 注意力机制、Mamba 状态空间模型"
              maxLength={500}
              disabled={isBusy || isParsing}
              aria-label="输入想学的内容"
            />
            <div className="topic-form-actions">
              <span>{isParsing ? "当前任务解析完成前不能创建新学习任务" : `${topicDraft.trim().length}/500`}</span>
              <button className="primary-button" type="submit" disabled={isBusy || isParsing || !topicDraft.trim()}>
                生成学习路径
                <ArrowRight size={18} />
              </button>
            </div>
          </form>

          <label
            className={`upload-zone ${isParsing ? "parsing" : ""}`}
            aria-busy={isParsing}
            onDragOver={(event) => event.preventDefault()}
            onDrop={onDrop}
          >
            <input
              type="file"
              accept=".txt,.md,.markdown,.pdf,.csv,.json"
              onChange={onUpload}
              disabled={isBusy || isParsing}
              aria-label="上传学习材料"
            />
            <UploadCloud size={42} />
            <strong>{isBusy || isParsing ? "正在解析当前任务" : "拖拽或选择材料"}</strong>
            <span>{isParsing ? "解析完成前不能上传其他文档" : "支持 PDF、TXT、Markdown、CSV、JSON；扫描版 PDF 请先 OCR"}</span>
          </label>
        </div>
      </section>

      <section className="process-board">
        <div className="section-heading">
          <p className="eyebrow">Parser Pipeline</p>
          <h3>解析队列</h3>
        </div>
        <div className="progress-block">
          <div className="progress-meta">
            <span>结构化转化</span>
            <span>{parseProgress}%</span>
          </div>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${parseProgress}%` }} />
          </div>
        </div>
        <ParseStatus meta={parseMeta} progress={parseProgress} status={parseStatus} />
        <PipelineStep icon={<FileText size={18} />} title="OCR / 字幕 / 文本抽取" state={textState.label} tone={textState.tone} />
        <PipelineStep
          icon={<Layers3 size={18} />}
          title="概念切片与复杂度标记"
          state={sliceState.label}
          tone={sliceState.tone}
        />
        <PipelineStep icon={<Network size={18} />} title="依赖关系图谱生成" state={graphState.label} tone={graphState.tone} />
        <button className="primary-button" type="button" onClick={onOpenMap} disabled={isBusy || isParsing || !hasSession}>
          查看知识拓扑
          <ArrowRight size={18} />
        </button>
      </section>
    </div>
  );
}

function PipelineStep({
  icon,
  title,
  state,
  tone,
}: {
  icon: ReactNode;
  title: string;
  state: string;
  tone: "idle" | "active" | "done";
}) {
  return (
    <div className={`pipeline-step ${tone}`}>
      <div className="step-icon">{icon}</div>
      <span>{title}</span>
      <small>{state}</small>
    </div>
  );
}

function pipelineState(
  progress: number,
  status: ParseJob["status"],
  start: number,
  doneAt: number,
  isParsing: boolean,
  doneLabel = "完成",
): { label: string; tone: "idle" | "active" | "done" } {
  if (status === "failed") return { label: "失败", tone: "idle" };
  if (status === "completed") return { label: doneLabel, tone: "done" };
  if (progress >= doneAt) return { label: doneLabel, tone: "done" };
  if (isParsing && progress >= start) return { label: "进行中", tone: "active" };
  return { label: "等待中", tone: "idle" };
}
