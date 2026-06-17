import { ReactNode } from "react";
import { Header, StageButton } from "./AppChrome";
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
  children: ReactNode;
}) {
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
        extraTopRight={extraTopRight}
      />

      <section className={`workspace ${isAdminStage ? "admin-workspace" : ""} ${isFocusStage ? "focus-workspace" : ""}`}>
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

        <section className={`main-stage ${isAdminStage ? "admin-stage-shell" : ""}`}>
          {error && <div className="error-banner">{error}</div>}
          {children}
        </section>

        {sidePanel}
      </section>
    </main>
  );
}

export { BlankShell };
export type { BlankShellNavItem };
