import { useEffect, useRef, useState } from "react";
import { ArrowRight, Mic, Square } from "lucide-react";
import { stageLabelText } from "../app/sessionState";
import type { FeynmanQuestion, KnowledgeNode } from "../types";

interface FeynmanStageProps {
  activeNode: KnowledgeNode;
  questions: FeynmanQuestion[];
  answers: Record<string, string>;
  currentIndex: number;
  onAnswerChange: (value: string) => void;
  onMove: (offset: number) => void;
  onContinue: () => void;
  onReload: () => void;
  onComplete: () => void;
  isBusy: boolean;
}

export function FeynmanStage({
  activeNode,
  questions,
  answers,
  currentIndex,
  onAnswerChange,
  onMove,
  onContinue,
  onReload,
  onComplete,
  isBusy,
}: FeynmanStageProps) {
  const current = questions[currentIndex] ?? null;
  const answeredCount = questions.filter((question) => (answers[question.id] ?? "").trim()).length;
  const isLast = questions.length > 0 && currentIndex === questions.length - 1;

  return (
    <div className="feynman-stage">
      <aside className="feynman-queue">
        <div className="queue-heading">
          <p className="eyebrow">Feynman Stage</p>
          <h2>讲台</h2>
          <strong>{activeNode.title}</strong>
        </div>
        <div className="question-capsules" aria-label="费曼问题进度">
          {questions.length === 0 ? (
            <button className="question-pill question-generator active" type="button" onClick={onReload} disabled={isBusy}>
              {isBusy ? "正在生成问题" : "生成验证问题"}
            </button>
          ) : (
            questions.map((question, index) => (
              <button
                key={question.id}
                type="button"
                className={`question-capsule ${index === currentIndex ? "active" : ""} ${
                  (answers[question.id] ?? "").trim() ? "answered" : ""
                }`}
                onClick={() => onMove(index - currentIndex)}
                disabled={isBusy}
                title={`${question.label}：${stageLabelText(question.stage)}`}
              >
                <span>{index + 1}</span>
                <small>{question.follow_up_of ? "追问" : stageLabelText(question.stage)}</small>
              </button>
            ))
          )}
        </div>
        <div className="feynman-progress">
          <strong>{answeredCount}/{questions.length || 0}</strong>
          <span>已回答</span>
        </div>
        <p className="queue-note">按题讲清，不需要一次讲完整个节点。完成后进入真实诊断。</p>
      </aside>

      <section className={`feynman-dialogue ${current ? "" : "empty-state"}`}>
        {current ? (
          <>
            <div className="question-card">
              <span>{current.follow_up_of ? "动态追问" : `导师提问 ${currentIndex + 1}`} · {stageLabelText(current.stage)}</span>
              <h3>{current.question}</h3>
              <p>{current.focus}</p>
            </div>

            <div className="answer-studio">
              <RecorderStudio disabled={isBusy} />
              <textarea
                value={answers[current.id] ?? ""}
                onChange={(event) => onAnswerChange(event.target.value)}
                placeholder="讲完后把关键句写在这里；当前版本不会自动转写语音。"
                disabled={isBusy}
              />
            </div>

            <div className="flow-actions">
              <button className="secondary-button" type="button" onClick={() => onMove(-1)} disabled={isBusy || currentIndex === 0}>
                上一题
              </button>
              {!isLast && (
                <button
                  className="primary-button"
                  type="button"
                  onClick={onContinue}
                  disabled={isBusy || !(answers[current.id] ?? "").trim()}
                >
                  {isBusy ? "处理中..." : "下一题"}
                  <ArrowRight size={18} />
                </button>
              )}
              {isLast && (
                <button
                  className="primary-button"
                  type="button"
                  onClick={current.follow_up_of ? onComplete : onContinue}
                  disabled={isBusy || (current.follow_up_of ? answeredCount < questions.length : !(answers[current.id] ?? "").trim())}
                >
                  {isBusy ? "诊断中..." : "提交逐题诊断"}
                  <ArrowRight size={18} />
                </button>
              )}
            </div>
          </>
        ) : (
          <div className="question-card empty">
            <span>等待模型出题</span>
            <h3>{isBusy ? "正在拆分细粒度验证问题" : "还没有验证问题"}</h3>
            <p>点击左侧生成验证问题后，再逐题回答。</p>
          </div>
        )}
      </section>
    </div>
  );
}

function RecorderStudio({ disabled }: { disabled: boolean }) {
  const [isRecording, setIsRecording] = useState(false);
  const [durationMs, setDurationMs] = useState(0);
  const [levels, setLevels] = useState<number[]>(() => Array.from({ length: 28 }, () => 6));
  const [status, setStatus] = useState("麦克风只用于本地音量反馈，不会上传音频。");
  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const animationRef = useRef<number | null>(null);
  const startRef = useRef(0);

  useEffect(() => {
    return () => stopRecording("录音已停止。");
  }, []);

  async function startRecording() {
    if (disabled || isRecording) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus("当前浏览器不支持麦克风录音，请继续使用文本回答。");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const audioContext = new AudioContext();
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 512;
      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      streamRef.current = stream;
      contextRef.current = audioContext;
      startRef.current = performance.now();
      setIsRecording(true);
      setStatus("正在听取麦克风输入，请像给同学讲解一样作答。");

      const tick = () => {
        analyser.getByteTimeDomainData(data);
        const bucketSize = Math.max(1, Math.floor(data.length / 28));
        const nextLevels = Array.from({ length: 28 }, (_, index) => {
          let sum = 0;
          const start = index * bucketSize;
          const end = Math.min(data.length, start + bucketSize);
          for (let cursor = start; cursor < end; cursor += 1) {
            sum += Math.abs(data[cursor] - 128);
          }
          const average = sum / Math.max(1, end - start);
          return Math.max(6, Math.min(54, 6 + average * 2.1));
        });
        setLevels(nextLevels);
        setDurationMs(performance.now() - startRef.current);
        animationRef.current = window.requestAnimationFrame(tick);
      };
      tick();
    } catch {
      setStatus("无法访问麦克风，请检查浏览器权限，或直接使用文本回答。");
      setIsRecording(false);
    }
  }

  function stopRecording(nextStatus = "录音已停止，请把关键句写入文本框后继续。") {
    if (animationRef.current !== null) {
      window.cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    void contextRef.current?.close();
    contextRef.current = null;
    setIsRecording(false);
    setStatus(nextStatus);
  }

  const seconds = Math.floor(durationMs / 1000);
  const timeLabel = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;

  return (
    <section className={`recorder-studio ${isRecording ? "recording" : ""}`} aria-live="polite">
      <div className="recorder-controls">
        <button
          className="record-button"
          type="button"
          onClick={isRecording ? () => stopRecording() : startRecording}
          disabled={disabled}
        >
          {isRecording ? <Square size={16} /> : <Mic size={16} />}
          <span>{isRecording ? "停止" : "讲出来"}</span>
        </button>
        <strong>{timeLabel}</strong>
      </div>
      <div className="waveform" aria-label={isRecording ? "实时麦克风波形" : "麦克风波形待开始"}>
        {levels.map((level, index) => (
          <span key={index} style={{ height: `${isRecording ? level : 6}px` }} />
        ))}
      </div>
      <p>{status}</p>
    </section>
  );
}
