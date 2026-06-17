import { Loader2 } from "lucide-react";

interface AgentStatusBadgeProps {
  status: string | null;
}

export function AgentStatusBadge({ status }: AgentStatusBadgeProps) {
  if (!status) return null;
  return (
    <div className="agent-status-badge">
      <Loader2 size={14} />
      <span>{status}</span>
    </div>
  );
}
