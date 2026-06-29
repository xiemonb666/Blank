import { useEffect, useRef, useState } from "react";
import { ArrowRight, Mic, Square, Volume2 } from "lucide-react";
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
  asrEnabled: boolean;
  ttsEnabled: boolean;
  isSpeaking: boolean;
  onSpeakText: (text: string) => void;
  onTranscribeAudio: (audio: Blob) => Promise<string>;
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
  asrEnabled,
  ttsEnabled,
  isSpeaking,
  onSpeakText,
  onTranscribeAudio,
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
              <div className="question-card-topline">
                <span>{current.follow_up_of ? "动态追问" : `导师提问 ${currentIndex + 1}`} · {stageLabelText(current.stage)}</span>
                {ttsEnabled && (
                  <button
                    className="secondary-button compact voice-inline-button"
                    type="button"
                    onClick={() => onSpeakText(`${current.question}\n${current.focus}`)}
                    disabled={isBusy || isSpeaking}
                  >
                    <Volume2 size={14} />
                    <small>{isSpeaking ? "播报中" : "朗读题目"}</small>
                  </button>
                )}
              </div>
              <h3>{current.question}</h3>
              <p>{current.focus}</p>
            </div>

            <div className="answer-studio">
              <RecorderStudio
                disabled={isBusy}
                asrEnabled={asrEnabled}
                value={answers[current.id] ?? ""}
                onChange={onAnswerChange}
                onTranscribeAudio={onTranscribeAudio}
              />
              <textarea
                value={answers[current.id] ?? ""}
                onChange={(event) => onAnswerChange(event.target.value)}
                placeholder={asrEnabled ? "可以直接讲出来，转写后请确认并补充关键句。" : "讲完后把关键句写在这里；当前环境尚未启用自动转写。"}
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

function RecorderStudio({
  disabled,
  asrEnabled,
  value,
  onChange,
  onTranscribeAudio,
}: {
  disabled: boolean;
  asrEnabled: boolean;
  value: string;
  onChange: (value: string) => void;
  onTranscribeAudio: (audio: Blob) => Promise<string>;
}) {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [durationMs, setDurationMs] = useState(0);
  const [levels, setLevels] = useState<number[]>(() => Array.from({ length: 28 }, () => 6));
  const [status, setStatus] = useState(
    asrEnabled
      ? "录音结束后会调用 SenseVoice 转写；默认不长期保存音频，只写入你确认后的文本。"
      : "当前环境未启用 ASR，麦克风仅用于本地音量反馈。",
  );
  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const animationRef = useRef<number | null>(null);
  const startRef = useRef(0);

  useEffect(() => {
    return () => stopRecording("录音已停止。", false);
  }, []);

  useEffect(() => {
    if (isRecording || isTranscribing) return;
    setStatus(
      asrEnabled
        ? "录音结束后会调用 SenseVoice 转写；默认不长期保存音频，只写入你确认后的文本。"
        : "当前环境未启用 ASR，麦克风仅用于本地音量反馈。",
    );
  }, [asrEnabled, isRecording, isTranscribing]);

  async function startRecording() {
    if (disabled || isRecording || isTranscribing) return;
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
      const preferredMimeType = resolveRecorderMimeType();
      const recorder = preferredMimeType ? new MediaRecorder(stream, { mimeType: preferredMimeType }) : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || preferredMimeType || "audio/webm" });
        chunksRef.current = [];
        if (!blob.size) {
          setStatus("没有录到有效音频，请重试或直接使用文本回答。");
          return;
        }
        if (!asrEnabled) {
          setStatus("录音已停止。当前环境未启用自动转写，请把关键句写入文本框后继续。");
          return;
        }
        void transcribeBlob(blob);
      };
      recorder.start();
      streamRef.current = stream;
      contextRef.current = audioContext;
      mediaRecorderRef.current = recorder;
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

  async function transcribeBlob(blob: Blob) {
    setIsTranscribing(true);
    setStatus("录音已结束，正在用 SenseVoice 转写，请稍候。");
    try {
      const transcript = (await onTranscribeAudio(blob)).trim();
      if (!transcript) {
        throw new Error("没有识别出可用文本，请再讲慢一点，或改用键盘输入。");
      }
      const nextValue = value.trim() ? `${value.trim()}\n${transcript}` : transcript;
      onChange(nextValue);
      setStatus("转写已写入文本框。请先确认和修改，再继续下一题。");
    } catch (caught) {
      setStatus(caught instanceof Error ? caught.message : "转写失败，请直接使用文本回答。");
    } finally {
      setIsTranscribing(false);
    }
  }

  function stopRecording(nextStatus = "录音已停止，请把关键句写入文本框后继续。", shouldTranscribe = true) {
    if (animationRef.current !== null) {
      window.cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
    const recorder = mediaRecorderRef.current;
    mediaRecorderRef.current = null;
    if (recorder && recorder.state !== "inactive") {
      recorder.stop();
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    void contextRef.current?.close();
    contextRef.current = null;
    setIsRecording(false);
    if (!shouldTranscribe) {
      chunksRef.current = [];
      setStatus(nextStatus);
    } else if (!asrEnabled) {
      setStatus("录音已停止。当前环境未启用自动转写，请把关键句写入文本框后继续。");
    }
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
          disabled={disabled || isTranscribing}
        >
          {isRecording ? <Square size={16} /> : <Mic size={16} />}
          <span>{isTranscribing ? "转写中" : isRecording ? "停止" : "讲出来"}</span>
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

function resolveRecorderMimeType() {
  if (typeof MediaRecorder === "undefined" || typeof MediaRecorder.isTypeSupported !== "function") {
    return "";
  }
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  return candidates.find((item) => MediaRecorder.isTypeSupported(item)) ?? "";
}
