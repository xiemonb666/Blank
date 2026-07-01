import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";

gsap.registerPlugin(useGSAP);

export function StageTransition({
  transitionKey,
  children,
}: {
  transitionKey: string;
  children: ReactNode;
}) {
  const scopeRef = useRef<HTMLDivElement | null>(null);

  useGSAP(
    () => {
      const element = scopeRef.current;
      if (!element) return;
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const timeline = gsap.timeline({
        defaults: {
          duration: reduceMotion ? 0 : 0.26,
          ease: "power2.out",
          overwrite: "auto",
        },
      });
      timeline.fromTo(
        element,
        { autoAlpha: reduceMotion ? 1 : 0, y: reduceMotion ? 0 : 8 },
        { autoAlpha: 1, y: 0, clearProps: "transform,visibility" },
      );
    },
    { dependencies: [transitionKey], scope: scopeRef, revertOnUpdate: true },
  );

  return (
    <div className="stage-transition" ref={scopeRef}>
      {children}
    </div>
  );
}

export function Panel({
  title,
  kicker,
  actions,
  className = "",
  children,
}: {
  title?: string;
  kicker?: string;
  actions?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`ui-panel ${className}`}>
      {(title || kicker || actions) && (
        <div className="ui-panel-head">
          <div>
            {kicker && <span>{kicker}</span>}
            {title && <strong>{title}</strong>}
          </div>
          {actions && <div className="ui-panel-actions">{actions}</div>}
        </div>
      )}
      <div className="ui-panel-body">{children}</div>
    </section>
  );
}

export function IconAction({
  label,
  title,
  active = false,
  disabled = false,
  className = "",
  onClick,
  children,
}: {
  label: string;
  title?: string;
  active?: boolean;
  disabled?: boolean;
  className?: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      className={`icon-button ${active ? "active" : ""} ${className}`}
      type="button"
      aria-label={label}
      title={title ?? label}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  orientation = "horizontal",
  disabled = false,
  className = "",
  onChange,
}: {
  label: string;
  value: T;
  options: Record<T, { label: string; caption?: string; icon?: ReactNode }>;
  orientation?: "horizontal" | "vertical";
  disabled?: boolean;
  className?: string;
  onChange: (value: T) => void;
}) {
  return (
    <div className={`segmented-control ${orientation === "vertical" ? "vertical" : ""} ${className}`} role="tablist" aria-label={label} aria-orientation={orientation}>
      {(Object.keys(options) as T[]).map((key) => (
        <button
          key={key}
          type="button"
          className={value === key ? "active" : ""}
          onClick={() => onChange(key)}
          disabled={disabled}
          title={options[key].caption}
          aria-current={value === key ? "page" : undefined}
        >
          {options[key].icon && <span className="segmented-icon" aria-hidden="true">{options[key].icon}</span>}
          <span className="segmented-label">{options[key].label}</span>
        </button>
      ))}
    </div>
  );
}

export function PagedList<T>({
  items,
  pageSize,
  mediumPageSize,
  mediumQuery = "(max-width: 1080px)",
  compactPageSize,
  compactQuery = "(max-width: 720px)",
  renderItem,
  empty,
  ariaLabel,
  className = "",
}: {
  items: T[];
  pageSize: number;
  mediumPageSize?: number;
  mediumQuery?: string;
  compactPageSize?: number;
  compactQuery?: string;
  renderItem: (item: T, index: number) => ReactNode;
  empty?: ReactNode;
  ariaLabel: string;
  className?: string;
}) {
  const [page, setPage] = useState(0);
  const [isMedium, setIsMedium] = useState(false);
  const [isCompact, setIsCompact] = useState(false);
  const effectivePageSize = isCompact && compactPageSize ? compactPageSize : isMedium && mediumPageSize ? mediumPageSize : pageSize;
  const pageCount = Math.max(1, Math.ceil(items.length / effectivePageSize));
  const safePage = Math.min(page, pageCount - 1);
  const visibleItems = useMemo(
    () => items.slice(safePage * effectivePageSize, safePage * effectivePageSize + effectivePageSize),
    [items, effectivePageSize, safePage],
  );

  useEffect(() => {
    if (!compactPageSize) return;
    const media = window.matchMedia(compactQuery);
    const syncCompact = () => setIsCompact(media.matches);
    syncCompact();
    media.addEventListener("change", syncCompact);
    return () => media.removeEventListener("change", syncCompact);
  }, [compactPageSize, compactQuery]);

  useEffect(() => {
    if (!mediumPageSize) return;
    const media = window.matchMedia(mediumQuery);
    const syncMedium = () => setIsMedium(media.matches);
    syncMedium();
    media.addEventListener("change", syncMedium);
    return () => media.removeEventListener("change", syncMedium);
  }, [mediumPageSize, mediumQuery]);

  useEffect(() => {
    setPage((current) => Math.min(current, pageCount - 1));
  }, [pageCount]);

  function move(offset: number) {
    setPage((current) => Math.min(pageCount - 1, Math.max(0, current + offset)));
  }

  return (
    <div className={`paged-list ${className}`} aria-label={ariaLabel}>
      <div className="paged-list-body">
        {visibleItems.length > 0 ? visibleItems.map((item, index) => renderItem(item, safePage * effectivePageSize + index)) : empty}
      </div>
      {pageCount > 1 && (
        <div className="pager" aria-label={`${ariaLabel}分页`}>
          <button type="button" onClick={() => move(-1)} disabled={safePage === 0} aria-label="上一页">
            <ChevronLeft size={16} />
          </button>
          <span>{safePage + 1}/{pageCount}</span>
          <button type="button" onClick={() => move(1)} disabled={safePage >= pageCount - 1} aria-label="下一页">
            <ChevronRight size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
