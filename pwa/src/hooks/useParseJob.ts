import { useEffect, useRef, useState } from "react";
import { getParseJob, type LearningSession, type ParseJob } from "../api";
import { PARSE_JOB_STORAGE_KEY } from "../app/constants";
import type { ParseMeta } from "../components/ParseStatus";

type ParseJobUpdate = {
  job: ParseJob;
  session: LearningSession | null;
};

interface UseParseJobOptions {
  enabled: boolean;
  initialProgress: number;
  initialMeta: ParseMeta;
  initialIsParsing: boolean;
  onComplete: (update: ParseJobUpdate) => Promise<void> | void;
  onFailed: (message: string) => Promise<void> | void;
  onError: (message: string) => void;
}

function useParseJob({
  enabled,
  initialProgress,
  initialMeta,
  initialIsParsing,
  onComplete,
  onFailed,
  onError,
}: UseParseJobOptions) {
  const [parseProgress, setParseProgress] = useState(initialProgress);
  const [parseMeta, setParseMeta] = useState<ParseMeta>(initialMeta);
  const [parseJobId, setParseJobId] = useState(() => localStorage.getItem(PARSE_JOB_STORAGE_KEY) ?? "");
  const [isParsing, setIsParsing] = useState(initialIsParsing);
  const [parseStatus, setParseStatus] = useState<ParseJob["status"]>(
    initialIsParsing ? "running" : initialProgress >= 100 ? "completed" : "queued",
  );
  const callbacksRef = useRef({ onComplete, onFailed, onError });

  useEffect(() => {
    callbacksRef.current = { onComplete, onFailed, onError };
  }, [onComplete, onError, onFailed]);

  useEffect(() => {
    if (!enabled || !parseJobId) return;
    let cancelled = false;
    let consecutiveErrors = 0;
    setIsParsing(true);
    const poll = async () => {
      try {
        const response = await getParseJob(parseJobId);
        if (cancelled) return;
        consecutiveErrors = 0;
        setParseProgress(response.job.progress);
        setParseStatus(response.job.status);
        setParseMeta({
          source: "local",
          provider: null,
          model: null,
          message: response.job.error ?? response.job.message,
        });
        if (response.job.status === "completed" || response.job.status === "failed") {
          setIsParsing(false);
          setParseJobId("");
          localStorage.removeItem(PARSE_JOB_STORAGE_KEY);
        }
        if (response.job.status === "completed") {
          await callbacksRef.current.onComplete(response);
          return;
        }
        if (response.job.status === "failed") {
          await callbacksRef.current.onFailed(response.job.error ?? "解析失败，请检查 API 配置。");
        }
      } catch (caught) {
        if (!cancelled) {
          consecutiveErrors += 1;
          const message = caught instanceof Error ? caught.message : "解析状态读取失败。";
          if (message.includes("解析任务不存在") || consecutiveErrors >= 3) {
            setIsParsing(false);
            setParseJobId("");
            localStorage.removeItem(PARSE_JOB_STORAGE_KEY);
            setParseStatus("failed");
            setParseMeta({
              source: "local",
              provider: null,
              model: null,
              message: "解析任务已中断，请重新上传材料。",
            });
          }
          callbacksRef.current.onError(message);
        }
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [enabled, parseJobId]);

  function begin(job: ParseJob) {
    setParseJobId(job.id);
    localStorage.setItem(PARSE_JOB_STORAGE_KEY, job.id);
    setIsParsing(true);
    setParseStatus(job.status);
    setParseProgress(job.progress);
    setParseMeta({
      source: "local",
      provider: null,
      model: null,
      message: job.message,
    });
  }

  function reset() {
    setParseProgress(0);
    setParseStatus("queued");
    setParseMeta({
      source: "local",
      provider: null,
      model: null,
      message: "上传材料后开始解析",
    });
    setParseJobId("");
    setIsParsing(false);
    localStorage.removeItem(PARSE_JOB_STORAGE_KEY);
  }

  return {
    parseProgress,
    setParseProgress,
    parseMeta,
    setParseMeta,
    parseStatus,
    isParsing,
    begin,
    reset,
  };
}

export { useParseJob };
