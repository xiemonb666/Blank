import { PointerEvent, ReactNode, useMemo, useState } from "react";
import { BookOpen, ChevronLeft, ChevronRight, Minimize2, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { Header, StageButton } from "./AppChrome";
import { IconAction, StageTransition } from "./DesignPrimitives";
import type { Stage, User } from "../types";

type BlankShellNavItem = {
  stage: Stage;
  icon: ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
};

function BlankShell({
  stage,
  masteredCount,
  nodeCount,
  materialTitle,
  sessionId,
  user,
  resetWorkspace,
  logout,
  extraTopRight,
  navItems,
  isAdminStage,
  isFocusStage,
  error,
  sidePanel,
  leftPanel,
  rightPanel,
  children,
}: {
  stage: Stage;
  masteredCount: number;
  nodeCount: number;
  materialTitle: string;
  sessionId: string | null;
  user: User;
  resetWorkspace: () => void;
  logout: () => void;
  extraTopRight?: ReactNode;
  navItems: BlankShellNavItem[];
  isAdminStage: boolean;
  isFocusStage: boolean;
  error: string;
  sidePanel?: ReactNode;
  leftPanel?: ReactNode;
  rightPanel?: ReactNode;
  children: ReactNode;
}) {
  const [leftSize, setLeftSize] = useState(25);
  const [rightSize, setRightSize] = useState(24);
  const [isLeftCollapsed, setIsLeftCollapsed] = useState(false);
  const [isRightExpanded, setIsRightExpanded] = useState(false);
  const [isZenMode, setIsZenMode] = useState(false);
  const [dragging, setDragging] = useState<"left" | "right" | null>(null);
  const canUseIdeLayout = !isAdminStage;
  const showLeftPanel = canUseIdeLayout && Boolean(leftPanel);
  const resolvedRightPanel = rightPanel ?? sidePanel;
  const showRightPanel = canUseIdeLayout && Boolean(resolvedRightPanel);
  const semanticZoomClass = leftSize <= 20 || isLeftCollapsed ? "semantic-zoom-compact" : "semantic-zoom-full";

  const gridTemplateColumns = useMemo(() => {
    if (!canUseIdeLayout) return undefined;
    const columns = ["76px"];
    if (!isZenMode && showLeftPanel && !isLeftCollapsed) {
      columns.push(`clamp(220px, ${leftSize}vw, 440px)`, "6px");
    }
    columns.push("minmax(0, 1fr)");
    if (!isZenMode && showRightPanel) {
      columns.push("6px", isRightExpanded ? `clamp(260px, ${rightSize}vw, 430px)` : "46px");
    }
    return columns.join(" ");
  }, [canUseIdeLayout, isLeftCollapsed, isRightExpanded, isZenMode, leftSize, rightSize, showLeftPanel, showRightPanel]);

  function beginResize(panel: "left" | "right", event: PointerEvent<HTMLButtonElement>) {
    if (isZenMode) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(panel);
  }

  function updateResize(event: PointerEvent<HTMLButtonElement>) {
    if (!dragging) return;
    const width = window.innerWidth || 1;
    const nextPercent = Math.round((event.clientX / width) * 100);
    if (dragging === "left") {
      setIsLeftCollapsed(false);
      setLeftSize(Math.min(38, Math.max(16, nextPercent)));
      return;
    }
    setIsRightExpanded(true);
    setRightSize(Math.min(34, Math.max(18, 100 - nextPercent)));
  }

  function endResize(event: PointerEvent<HTMLButtonElement>) {
    if (!dragging) return;
    event.currentTarget.releasePointerCapture(event.pointerId);
    setDragging(null);
  }

  return (
    <main className="app-shell">
      <div className="background-grid" />
      <Header
        stage={stage}
        masteredCount={masteredCount}
        nodeCount={nodeCount}
        materialTitle={materialTitle}
        sessionId={sessionId}
        user={user}
        resetWorkspace={resetWorkspace}
        logout={logout}
        extraTopRight={(
          <>
            {extraTopRight}
            {canUseIdeLayout && (
              <IconAction
                className="zen-toggle"
                active={isZenMode}
                onClick={() => setIsZenMode((current) => !current)}
                label={isZenMode ? "退出禅定模式" : "进入禅定模式"}
              >
                {isZenMode ? <Minimize2 size={18} /> : <BookOpen size={18} />}
              </IconAction>
            )}
          </>
        )}
      />

      <section
        className={`workspace ide-workspace ${isAdminStage ? "admin-workspace" : ""} ${isFocusStage ? "focus-workspace" : ""} ${isZenMode ? "zen-mode" : ""} ${dragging ? "is-resizing" : ""}`}
        style={gridTemplateColumns ? { gridTemplateColumns } : undefined}
      >
        <aside className="rail" aria-label="学习阶段">
          {navItems.map((item) => (
            <StageButton
              key={item.stage}
              active={stage === item.stage}
              icon={item.icon}
              label={item.label}
              onClick={item.onClick}
              disabled={item.disabled}
            />
          ))}
        </aside>

        {showLeftPanel && (
          <aside className={`ide-panel left-ide-panel ${isLeftCollapsed ? "collapsed" : ""} ${semanticZoomClass}`} aria-label="知识拓扑与目录">
            <div className="ide-panel-toolbar">
              <span>Knowledge</span>
              <button
                className="icon-button subtle"
                type="button"
                onClick={() => setIsLeftCollapsed((current) => !current)}
                aria-label={isLeftCollapsed ? "展开左侧栏" : "折叠左侧栏"}
                title={isLeftCollapsed ? "展开左侧栏" : "折叠左侧栏"}
              >
                {isLeftCollapsed ? <PanelLeftOpen size={16} /> : <PanelLeftClose size={16} />}
              </button>
            </div>
            <div className="ide-panel-body">{leftPanel}</div>
          </aside>
        )}

        {showLeftPanel && !isZenMode && !isLeftCollapsed && <button className="ide-splitter left-splitter" type="button" aria-label="调整左侧栏宽度" onPointerDown={(event) => beginResize("left", event)} onPointerMove={updateResize} onPointerUp={endResize} onPointerCancel={endResize} />}

        <section className={`main-stage ${isAdminStage ? "admin-stage-shell" : ""}`}>
          {error && <div className="error-banner">{error}</div>}
          <StageTransition transitionKey={`${stage}:${isZenMode ? "zen" : "normal"}`}>
            {children}
          </StageTransition>
        </section>

        {showRightPanel && !isZenMode && <button className="ide-splitter right-splitter" type="button" aria-label="调整右侧栏宽度" onPointerDown={(event) => beginResize("right", event)} onPointerMove={updateResize} onPointerUp={endResize} onPointerCancel={endResize} />}

        {showRightPanel && (
          <aside className={`ide-panel right-ide-panel ${isRightExpanded ? "expanded" : "tabbed"}`} aria-label="辅助研究与诊断面板">
            <div className="right-panel-tabs" aria-label="辅助面板标签">
              <button
                className={`icon-button subtle ${isRightExpanded ? "active" : ""}`}
                type="button"
                onClick={() => setIsRightExpanded((current) => !current)}
                aria-label={isRightExpanded ? "折叠右侧栏" : "展开右侧栏"}
                title={isRightExpanded ? "折叠右侧栏" : "展开右侧栏"}
              >
                {isRightExpanded ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
              </button>
            </div>
            <div className="ide-panel-body">{resolvedRightPanel}</div>
          </aside>
        )}
      </section>
    </main>
  );
}

export { BlankShell };
export type { BlankShellNavItem };
