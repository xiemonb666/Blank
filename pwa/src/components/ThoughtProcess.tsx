import { useState } from "react";
import { BrainCircuit, ChevronDown, ChevronUp } from "lucide-react";
import { RichText } from "./RichText";

interface ThoughtProcessProps {
  thoughts: string[];
}

export function ThoughtProcess({ thoughts }: ThoughtProcessProps) {
  const [expanded, setExpanded] = useState(false);
  if (!thoughts || thoughts.length === 0) return null;

  return (
    <div className="thought-process">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="thought-process-toggle"
      >
        <BrainCircuit size={14} />
        <span>思考过程 ({thoughts.length})</span>
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {expanded && (
        <div className="thought-process-body">
          {thoughts.map((t, i) => (
            <RichText key={i} text={t} />
          ))}
        </div>
      )}
    </div>
  );
}
