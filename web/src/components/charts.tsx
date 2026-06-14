import {
  Area, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer,
  Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis, Cell, LineChart,
} from "recharts";
import type { WeeklyGame } from "../types";
import { CHART } from "../lib/ui";

const axis = { stroke: CHART.axis, fontSize: 11, tickLine: false };

// Weekly actual vs optimal — the shaded gap IS points-left-on-bench.
export function WeeklyChart({ weekly, playoffStart }: { weekly: WeeklyGame[]; playoffStart?: number }) {
  const data = weekly.map((w) => ({ ...w, gap: Math.max(0, w.optimal - w.pts) }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke={CHART.grid} vertical={false} />
        <XAxis dataKey="week" {...axis} tickFormatter={(w) => `W${w}`} />
        <YAxis {...axis} />
        <Tooltip
          contentStyle={CHART.tip}
          labelFormatter={(w) => `Week ${w}`}
          formatter={(v: number, n: string) => [v.toFixed(1), n === "pts" ? "Started" : n === "optimal" ? "Optimal" : n]}
        />
        {playoffStart && (
          <ReferenceLine x={playoffStart} stroke={CHART.amber} strokeDasharray="3 3"
            label={{ value: "playoffs", fill: CHART.amber, fontSize: 10, position: "insideTopRight" }} />
        )}
        <Area type="monotone" dataKey="optimal" stroke={CHART.faint} strokeWidth={1}
          strokeDasharray="4 3" fill={CHART.faint} fillOpacity={0.12} name="optimal" />
        <Line type="monotone" dataKey="pts" stroke={CHART.green} strokeWidth={2.5}
          dot={{ r: 2.5, fill: CHART.green }} name="pts" />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export interface QuadPoint { x: number; y: number; name: string; tone: string; rid: number }
const TONE_HEX: Record<string, string> = {
  good: CHART.green, bad: CHART.rose, neutral: CHART.sky,
  gold: CHART.amber, green: CHART.green, sky: CHART.sky, amber: CHART.amber,
  violet: CHART.violet, rose: CHART.rose, slate: CHART.faint,
};

// Luck (y) vs Skill (x) quadrant scatter.
export function QuadrantScatter({ points, onSelect }: {
  points: QuadPoint[]; onSelect?: (rid: number) => void;
}) {
  return (
    <ResponsiveContainer width="100%" height={340}>
      <ScatterChart margin={{ top: 16, right: 24, left: 0, bottom: 16 }}>
        <CartesianGrid stroke={CHART.grid} />
        <XAxis type="number" dataKey="x" name="Skill" {...axis}
          domain={["dataMin - 0.3", "dataMax + 0.3"]} tickFormatter={(v) => v.toFixed(1)}
          label={{ value: "Skill →", fill: CHART.axis, fontSize: 11, position: "insideBottomRight", dy: 10 }} />
        <YAxis type="number" dataKey="y" name="Luck" {...axis}
          domain={["dataMin - 0.3", "dataMax + 0.3"]} tickFormatter={(v) => v.toFixed(1)}
          label={{ value: "Luck →", fill: CHART.axis, fontSize: 11, angle: -90, position: "insideTopLeft" }} />
        <ZAxis range={[120, 120]} />
        <ReferenceLine x={0} stroke={CHART.axis} strokeDasharray="3 3" />
        <ReferenceLine y={0} stroke={CHART.axis} strokeDasharray="3 3" />
        <Tooltip
          cursor={{ strokeDasharray: "3 3", stroke: CHART.grid }}
          contentStyle={CHART.tip}
          formatter={(v: number, n: string) => [v.toFixed(2), n]}
          labelFormatter={() => ""}
        />
        <Scatter data={points} onClick={(p: any) => onSelect?.(p.rid)}
          shape={(props: any) => <LabeledDot {...props} />}>
          {points.map((p, i) => <Cell key={i} fill={TONE_HEX[p.tone] || CHART.sky} />)}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}

function LabeledDot(props: any) {
  const { cx, cy, fill, payload } = props;
  if (cx === undefined) return null;
  return (
    <g style={{ cursor: "pointer" }}>
      <circle cx={cx} cy={cy} r={6} fill={fill} stroke="#0e1117" strokeWidth={1.5} />
      <text x={cx} y={cy - 10} textAnchor="middle" fill="#a3acc2" fontSize={10}>
        {payload.name.length > 14 ? payload.name.slice(0, 13) + "…" : payload.name}
      </text>
    </g>
  );
}

// Multi-season finish trajectory (lower finish = better, so invert axis).
export function TrajectoryLine({ seasons, finish }: { seasons: string[]; finish: (number | null)[] }) {
  const data = seasons.map((s, i) => ({ season: s, finish: finish[i] }));
  return (
    <ResponsiveContainer width="100%" height={120}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: -24, bottom: 0 }}>
        <YAxis {...axis} reversed allowDecimals={false} domain={[1, "dataMax"]} width={28} />
        <XAxis dataKey="season" {...axis} />
        <Tooltip contentStyle={CHART.tip} formatter={(v: number) => [`#${v}`, "Finish"]} />
        <Line type="monotone" dataKey="finish" stroke={CHART.violet} strokeWidth={2.5}
          dot={{ r: 3, fill: CHART.violet }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function MiniLine({ data, color = CHART.green, dataKey }: {
  data: any[]; color?: string; dataKey: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={48}>
      <LineChart data={data} margin={{ top: 4, right: 2, left: 2, bottom: 0 }}>
        <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}
