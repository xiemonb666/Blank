import { Atom, Network } from "lucide-react";

interface V2ModeToggleProps {
  enabled: boolean;
  onToggle: () => void;
}

export function V2ModeToggle({ enabled, onToggle }: V2ModeToggleProps) {
  return (
    <button
      className={`v2-toggle ${enabled ? "active" : ""}`}
      type="button"
      onClick={onToggle}
      aria-pressed={enabled}
      title={enabled ? "当前默认使用 V2 多智能体链路" : "当前使用 V1 过时回退链路"}
    >
      {enabled ? <Network size={14} /> : <Atom size={14} />}
      <span>{enabled ? "V2 多智能体" : "V1 过时"}</span>
    </button>
  );
}
