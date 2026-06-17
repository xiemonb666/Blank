import { BrainCircuit } from "lucide-react";
import type { ParseJob } from "../api";

export interface ParseMeta {
  source: "ai" | "local";
  provider: string | null;
  model: string | null;
  message: string;
}

export function ParseStatus({
  meta,
  progress,
  status,
}: {
  meta: ParseMeta;
  progress: number;
  status: ParseJob["status"];
}) {
  const label = status === "failed" ? "解析失败" : status === "completed" ? "知识节点已生成" : "正在解析材料";
  return (
    <div className={`parse-status ${status === "failed" ? "failed" : ""}`}>
      <BrainCircuit size={18} />
      <div>
        <strong>
          {label}
          <b>{progress}%</b>
        </strong>
        <span>{meta.message}</span>
      </div>
    </div>
  );
}
