import clsx from "clsx";
import { useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import type { Basis, Direction, Label, Recommendation } from "../types";
import { ARCH_TONE, BASIS, POS_BG, REC_KIND, SIGNAL_TONE, TONE, fmt } from "../lib/ui";

// ── Justification atoms ──────────────────────────────────────────────────
export function ConfidenceMeter({ level }: { level: "low" | "med" | "high" }) {
  const lit = level === "high" ? 3 : level === "med" ? 2 : 1;
  return (
    <span role="img" aria-label={`Confidence: ${level}`} className="inline-flex items-center gap-1">
      <span className="flex gap-0.5">
        {[0, 1, 2].map((i) => (
          <span key={i} className={clsx("h-2.5 w-1 rounded-sm",
            i < lit ? "bg-gridiron" : "bg-ink-700")} />
        ))}
      </span>
      <span className="text-[10px] uppercase tracking-wide text-chalk-faint">{level}</span>
    </span>
  );
}

export interface JustifyContent {
  title: string;
  lines: string[];
  basis?: Basis;
  confidence?: "low" | "med" | "high";
  source?: string;
}

export function JustifyBody({ c }: { c: JustifyContent }) {
  return (
    <div className="space-y-1.5">
      <div className="font-semibold text-chalk">{c.title}</div>
      <ul className="space-y-0.5 text-chalk-dim">
        {c.lines.filter(Boolean).map((l, i) => (
          <li key={i} className="leading-snug">· {l}</li>
        ))}
      </ul>
      {(c.basis || c.confidence) && (
        <div className="flex items-center gap-2 border-t border-ink-700 pt-1.5">
          {c.basis && <BasisBadge basis={c.basis} sm />}
          {c.confidence && <ConfidenceMeter level={c.confidence} />}
        </div>
      )}
      {c.source && <div className="text-[10px] text-chalk-faint">Data: {c.source}</div>}
    </div>
  );
}

// Micro-justification: hover + keyboard focus (tap toggles on touch). The bubble
// is portaled to <body> with fixed positioning so table/overflow containers can
// never clip it, and clamped to stay on-screen.
export function HoverJustify({ content, children, className }: {
  content: JustifyContent; children?: ReactNode; className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const [pos, setPos] = useState<{ x: number; y: number; above: boolean } | null>(null);
  const show = () => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const above = r.bottom > window.innerHeight - 210;
    setPos({
      x: Math.min(Math.max(8, r.left), window.innerWidth - 272),
      y: above ? r.top - 6 : r.bottom + 6,
      above,
    });
  };
  const hide = () => setPos(null);
  return (
    <span ref={ref} tabIndex={0}
      className={clsx("inline-flex cursor-help items-center gap-0.5 outline-none", className)}
      onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}
      onClick={(e) => { e.stopPropagation(); pos ? hide() : show(); }}>
      {children}
      <span aria-hidden className="text-[9px] leading-none text-chalk-faint">ⓘ</span>
      {pos && createPortal(
        <div role="tooltip"
          style={{
            position: "fixed", left: pos.x, top: pos.y, width: 264, zIndex: 80,
            transform: pos.above ? "translateY(-100%)" : "none",
          }}
          className="card pointer-events-none p-2.5 text-xs leading-relaxed shadow-card">
          <JustifyBody c={content} />
        </div>, document.body)}
    </span>
  );
}

export function Card({ className, children, glow }: {
  className?: string; children: ReactNode; glow?: boolean;
}) {
  return (
    <div className={clsx("card card-pad", glow && "shadow-glow", className)}>{children}</div>
  );
}

export function SectionTitle({ icon, children, hint, help }: {
  icon?: string; children: ReactNode; hint?: ReactNode; help?: JustifyContent;
}) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-chalk-dim">
        {icon && <span aria-hidden className="text-gridiron">{icon}</span>}
        {children}
        {help && <Help content={help} />}
      </h2>
      {hint && <span className="text-xs text-chalk-faint">{hint}</span>}
    </div>
  );
}

// Standalone help icon (ⓘ) with a portaled explanation tooltip.
export function Help({ content }: { content: JustifyContent }) {
  return <HoverJustify content={content} className="text-chalk-faint" />;
}

export function Stat({ label, value, sub, tone, className, help }: {
  label: ReactNode; value: ReactNode; sub?: ReactNode; tone?: Direction;
  className?: string; help?: JustifyContent;
}) {
  return (
    <div className={clsx("rounded-xl2 bg-ink-850/70 px-3.5 py-3", className)}>
      <div className="flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide text-chalk-faint">
        {label}{help && <Help content={help} />}
      </div>
      <div className={clsx("stat mt-0.5 text-2xl font-semibold", tone && TONE[tone].text)}>{value}</div>
      {sub && <div className="mt-0.5 text-xs text-chalk-dim">{sub}</div>}
    </div>
  );
}

export function ToneDot({ tone, className }: { tone: Direction; className?: string }) {
  return <span className={clsx("inline-block h-2 w-2 rounded-full", TONE[tone].dot, className)} />;
}

export function BasisBadge({ basis, sm }: { basis: Basis; sm?: boolean }) {
  const b = BASIS[basis];
  return (
    <span className={clsx("pill border", b.cls, sm && "text-[10px] px-1.5 py-0")}>{b.label}</span>
  );
}

export function ProjectedBadge() {
  return (
    <span
      title="Offseason projection — not a settled fact"
      className="pill border border-amber/30 bg-amber/10 text-amber text-[10px]"
    >
      ◔ projected
    </span>
  );
}

export function PositionTag({ pos }: { pos: string }) {
  return (
    <span className={clsx("pill font-semibold", POS_BG[pos] || "bg-ink-700 text-chalk-dim")}>{pos}</span>
  );
}

export function SignalTag({ signal }: { signal?: string }) {
  if (!signal) return null;
  const s = SIGNAL_TONE[signal] || SIGNAL_TONE.HOLD;
  return <span className={clsx("pill border font-semibold", s.cls)}>{s.label}</span>;
}

export function TeamAvatar({ url, name, size = 40 }: { url: string | null; name: string; size?: number }) {
  const initials = name.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
  if (url)
    return (
      <img src={url} alt="" width={size} height={size}
        className="rounded-full bg-ink-800 object-cover ring-1 ring-ink-600"
        style={{ width: size, height: size }} />
    );
  return (
    <div className="flex items-center justify-center rounded-full bg-ink-700 font-semibold text-chalk-dim ring-1 ring-ink-600"
      style={{ width: size, height: size, fontSize: size * 0.36 }}>{initials}</div>
  );
}

const MEDAL: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };
const PLACE_LABEL: Record<number, string> = { 1: "1st", 2: "2nd", 3: "3rd" };
export function PodiumBadges({ podiums, className }: {
  podiums?: { season: string; place: number }[]; className?: string;
}) {
  if (!podiums?.length) return null;
  return (
    <span className={clsx("inline-flex flex-wrap items-center gap-1", className)}>
      {podiums.map((p, i) => (
        <span key={i} title={`${PLACE_LABEL[p.place]} place — ${p.season}`}
          className="pill bg-ink-800 text-[10px] leading-none">
          <span aria-hidden>{MEDAL[p.place]}</span>
          <span className="text-chalk-faint">{`'${p.season.slice(2)}`}</span>
        </span>
      ))}
    </span>
  );
}

export function Bar({ value, tone = "neutral" }: { value: number; tone?: Direction }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-700">
      <div className={clsx("h-full rounded-full", TONE[tone].dot)}
        style={{ width: `${Math.max(2, Math.min(100, value * 100))}%` }} />
    </div>
  );
}

export function ArchetypeBanner({ archetype, children }: {
  archetype: { name: string; blurb: string; tone: string }; children?: ReactNode;
}) {
  const t = ARCH_TONE[archetype.tone] || ARCH_TONE.slate;
  return (
    <div className={clsx("relative overflow-hidden rounded-xl2 border p-4 sm:p-5", t.bg, t.border)}>
      <div className={clsx("absolute left-0 top-0 h-full w-1", t.bar)} />
      <div className="pl-2">
        <div className="text-[11px] font-semibold uppercase tracking-widest text-chalk-faint">Power archetype</div>
        <div className={clsx("mt-0.5 text-2xl font-extrabold tracking-tight", t.text)}>{archetype.name}</div>
        <p className="mt-1 max-w-2xl text-sm text-chalk-dim">{archetype.blurb}</p>
        {children}
      </div>
    </div>
  );
}

export function LabelChip({ label }: { label: Label }) {
  return (
    <span
      title={`${label.detail}\n${label.evidence.join(" · ")}`}
      className={clsx(
        "pill border bg-ink-850 border-ink-600 text-chalk gap-1.5 py-1",
        )}
    >
      <ToneDot tone={label.direction} />
      <span className="font-medium">{label.label}</span>
      {label.projected && <span className="text-amber text-[10px]" title="projected">◔</span>}
    </span>
  );
}

export function LabelRow({ label }: { label: Label }) {
  return (
    <div className="flex items-start gap-3 rounded-xl2 border border-ink-700/60 bg-ink-850/50 p-3">
      <div className={clsx("mt-1 h-2.5 w-2.5 shrink-0 rounded-full", TONE[label.direction].dot)} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-chalk">{label.label}</span>
          <BasisBadge basis={label.basis} sm />
          {label.projected && <ProjectedBadge />}
        </div>
        <p className="mt-0.5 text-sm text-chalk-dim">{label.detail}</p>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {label.evidence.map((e, i) => (
            <span key={i} className="pill bg-ink-800 text-chalk-dim text-[11px]">{e}</span>
          ))}
        </div>
      </div>
      <div className="hidden shrink-0 text-right sm:block">
        <div className="text-[10px] uppercase tracking-wide text-chalk-faint">conf</div>
        <div className="stat text-sm text-chalk-dim">{fmt(label.confidence * 100, 0)}%</div>
      </div>
    </div>
  );
}

export function RecCard({ rec }: { rec: Recommendation }) {
  const k = REC_KIND[rec.kind] || REC_KIND.advice;
  return (
    <div className={clsx("rounded-xl2 border bg-ink-850/60 p-3.5", k.card)}>
      <div className="flex items-center gap-2">
        <span className={clsx("pill border font-semibold uppercase", k.badge)}>{rec.kind}</span>
        <span className="font-semibold text-chalk">{rec.title}</span>
        <span className="ml-auto"><BasisBadge basis={rec.basis} sm /></span>
      </div>
      <p className="mt-1.5 text-sm text-chalk-dim">{rec.detail}</p>
      {rec.players.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {rec.players.map((p, i) => (
            <span key={i} className="pill bg-ink-800 text-chalk text-xs">
              {p.pos && <span className="mr-1 text-chalk-faint">{p.pos}</span>}
              {p.name}
              {p.note && <span className="ml-1 text-chalk-faint">· {p.note}</span>}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex h-64 items-center justify-center text-chalk-faint">
      <div className="flex items-center gap-3">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-ink-600 border-t-gridiron" />
        {label}
      </div>
    </div>
  );
}

export function ErrorState({ error }: { error: Error }) {
  return (
    <Card className="border-rose/40">
      <div className="text-rose font-semibold">Couldn't load data</div>
      <p className="mt-1 text-sm text-chalk-dim">{error.message}</p>
      <p className="mt-2 text-xs text-chalk-faint">Run the ETL: <code>python -m etl.build</code></p>
    </Card>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="rounded-xl2 border border-dashed border-ink-700 p-6 text-center text-sm text-chalk-faint">{children}</div>;
}
