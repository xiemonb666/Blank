import { CSSProperties } from "react";
import { ArrowRight, Lock } from "lucide-react";
import { statusLabel } from "../app/sessionState";
import { ParseStatus, type ParseMeta } from "../components/ParseStatus";
import { RichText } from "../components/RichText";
import type { KnowledgeNode } from "../types";

interface MapStageProps {
  nodes: KnowledgeNode[];
  activeNodeId: string;
  parseMeta: ParseMeta;
  onSelectNode: (node: KnowledgeNode) => void;
  onStartFlow: () => void;
  isBusy: boolean;
}

export function MapStage({
  nodes,
  activeNodeId,
  parseMeta,
  onSelectNode,
  onStartFlow,
  isBusy,
}: MapStageProps) {
  const activeNode = nodes.find((node) => node.id === activeNodeId) ?? nodes[0] ?? null;
  const activeDeps = activeNode
    ? activeNode.deps
        .map((depId) => nodes.find((node) => node.id === depId))
        .filter((node): node is KnowledgeNode => Boolean(node))
    : [];

  return (
    <div className="map-layout">
      <section className="map-panel">
        <div className="section-heading">
          <p className="eyebrow">The Constellation</p>
          <h2>知识拓扑图</h2>
        </div>
        <ParseStatus meta={parseMeta} progress={100} status="completed" />

        <div className="constellation" aria-label="知识节点拓扑图">
          <svg className="edge-layer" viewBox="0 0 100 100" preserveAspectRatio="none">
            {nodes.flatMap((node) =>
              node.deps.map((depId) => {
                const dep = nodes.find((item) => item.id === depId);
                if (!dep) return null;
                return (
                  <line
                    key={`${depId}-${node.id}`}
                    x1={dep.x}
                    y1={dep.y}
                    x2={node.x}
                    y2={node.y}
                    className={node.status === "locked" ? "edge locked" : "edge"}
                  />
                );
              }),
            )}
          </svg>

          {nodes.map((node) => (
            <button
              key={node.id}
              type="button"
              className={`knowledge-node ${node.status} ${node.id === activeNodeId ? "selected" : ""}`}
              style={
                {
                  left: `${node.x}%`,
                  top: `${node.y}%`,
                  "--node-scale": node.weight,
                  "--node-tone": node.complexity,
                } as CSSProperties
              }
              onClick={() => onSelectNode(node)}
              disabled={isBusy || node.status === "locked"}
              aria-label={`${node.title}，复杂度 L${node.complexity}`}
            >
              {node.status === "locked" ? <Lock size={16} /> : <span />}
            </button>
          ))}
        </div>
      </section>

      <aside className="node-inspector">
        <div className="section-heading">
          <p className="eyebrow">Node Inspector</p>
          <h3>节点清单</h3>
        </div>
        <div className="node-list">
          {nodes.map((node) => (
            <button
              key={node.id}
              type="button"
              className={`node-row ${node.status} ${node.id === activeNodeId ? "selected" : ""}`}
              onClick={() => onSelectNode(node)}
              disabled={isBusy || node.status === "locked"}
            >
              <span className="node-row-index">L{node.complexity}</span>
              <span>
                <strong>{node.title}</strong>
                <small>{statusLabel(node.status)} · {node.deps.length} 前置</small>
              </span>
            </button>
          ))}
        </div>
        {activeNode && (
          <section className="node-evidence-panel">
            <div>
              <span>复杂度原因</span>
              <RichText text={activeNode.complexity_reason || `复杂度 L${activeNode.complexity}，当前会话没有保存更细原因。`} />
            </div>
            <div>
              <span>前置依赖</span>
              <p>{activeDeps.length > 0 ? activeDeps.map((node) => node.title).join(" -> ") : "无前置依赖。"}</p>
            </div>
          </section>
        )}
        <button className="primary-button" type="button" onClick={onStartFlow} disabled={isBusy}>
          进入学习流
          <ArrowRight size={18} />
        </button>
      </aside>
    </div>
  );
}
