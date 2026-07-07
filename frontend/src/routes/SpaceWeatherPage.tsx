import { useState, useMemo, type ReactElement } from "react";
import { useTranslation } from "react-i18next";
import { useSpaceWeatherEvents } from "@/hooks/useSpaceWeather";
import { ErrorBanner } from "@/components/ErrorBanner";
import { formatDate, formatDateTime } from "@/lib/dateTime";
import type { SpaceWeatherEventData, SpaceWeatherEventType } from "@/types/api";

type Tab = SpaceWeatherEventType;

const TABS = [
  { id: "FLR" as Tab, labelKey: "spaceWeather.flares" },
  { id: "GST" as Tab, labelKey: "spaceWeather.storms" },
  { id: "CME" as Tab, labelKey: "spaceWeather.cme" },
  { id: "SEP" as Tab, labelKey: "spaceWeather.sep" },
  { id: "RBE" as Tab, labelKey: "spaceWeather.rbe" },
];

const TAB_COLORS: Record<Tab, string> = {
  FLR: "#fb923c",
  GST: "#a78bfa",
  CME: "#facc15",
  SEP: "#34d399",
  RBE: "#38bdf8",
};

// ── Icons ──────────────────────────────────────────────────────────────────────

function IconFlare() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="sw-tab-icon">
      <path d="M12 2a1 1 0 0 1 1 1v2a1 1 0 0 1-2 0V3a1 1 0 0 1 1-1zm5.657 3.636a1 1 0 0 1 0 1.414l-1.414 1.414a1 1 0 0 1-1.414-1.414l1.414-1.414a1 1 0 0 1 1.414 0zm-11.314 0a1 1 0 0 1 1.414 0l1.414 1.414a1 1 0 0 1-1.414 1.414L6.343 7.05a1 1 0 0 1 0-1.414zM12 7a5 5 0 1 1 0 10A5 5 0 0 1 12 7zm7 4a1 1 0 0 1 0 2h-2a1 1 0 0 1 0-2h2zM7 11a1 1 0 0 1 0 2H5a1 1 0 0 1 0-2h2zm9.95 4.243a1 1 0 0 1 0 1.414l-1.414 1.414a1 1 0 0 1-1.414-1.414l1.414-1.414a1 1 0 0 1 1.414 0zM7.464 15.05a1 1 0 0 1 1.414 1.414L7.464 17.878a1 1 0 0 1-1.414-1.414l1.414-1.414zM12 19a1 1 0 0 1 1 1v2a1 1 0 0 1-2 0v-2a1 1 0 0 1 1-1z"/>
    </svg>
  );
}

function IconStorm() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="sw-tab-icon">
      <path d="M12 3a9 9 0 0 1 8.66 11.495A4.5 4.5 0 0 1 17.5 22H6a4 4 0 0 1 0-8h.08A9 9 0 0 1 12 3zm-1 10h-2l-1 4h2l-1 3 4-5h-2l1-2z"/>
    </svg>
  );
}

function IconCme() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="sw-tab-icon">
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1.41 16.09V20h-2.67v-1.93c-1.71-.36-3.16-1.46-3.27-3.4h1.96c.1 1.05.82 1.87 2.65 1.87 1.96 0 2.4-.98 2.4-1.59 0-.83-.44-1.61-2.67-2.14-2.48-.6-4.18-1.62-4.18-3.67 0-1.72 1.39-2.84 3.11-3.21V4h2.67v1.95c1.86.45 2.79 1.86 2.85 3.39H14.3c-.05-1.11-.64-1.87-2.22-1.87-1.5 0-2.4.68-2.4 1.64 0 .84.65 1.39 2.67 1.91s4.18 1.39 4.18 3.91c-.01 1.83-1.38 2.83-3.12 3.16z"/>
    </svg>
  );
}

function IconSep() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="sw-tab-icon">
      <path d="M7 2v11h3v9l7-12h-4l4-8z"/>
    </svg>
  );
}

function IconRbe() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="currentColor" className="sw-tab-icon">
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm0-13a5 5 0 1 0 0 10A5 5 0 0 0 12 7zm0 8a3 3 0 1 1 0-6 3 3 0 0 1 0 6zm0-5a2 2 0 1 0 0 4 2 2 0 0 0 0-4z"/>
    </svg>
  );
}

const TAB_ICONS: Record<Tab, ReactElement> = {
  FLR: <IconFlare />,
  GST: <IconStorm />,
  CME: <IconCme />,
  SEP: <IconSep />,
  RBE: <IconRbe />,
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function errorTitleKey(code: string): string {
  switch (code) {
    case "NO_INTERNET": return "error.noInternet";
    case "NASA_UNAVAILABLE": return "error.nasaUnavailable";
    case "NASA_AUTH_ERROR": return "error.nasaAuthError";
    default: return "common.error";
  }
}

function todayIso(): string {
  const now = new Date();
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}-${String(now.getUTCDate()).padStart(2, "0")}`;
}

function addDaysIso(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function parseRaw(raw: string): Record<string, unknown> {
  try { return JSON.parse(raw) as Record<string, unknown>; }
  catch { return {}; }
}

function renderTimestamp(value: unknown): string {
  if (typeof value === "string" && value.length >= 10) {
    try { return formatDateTime(value); }
    catch { return String(value); }
  }
  return value != null ? String(value) : "—";
}

// ── Flare dashboard ────────────────────────────────────────────────────────────

const FLR_CLASS_COLORS: Record<string, string> = {
  X: "#ef4444", M: "#f97316", C: "#facc15", B: "#22c55e", A: "#6b7280",
};
const FLR_CLASS_ORDER = ["X", "M", "C", "B", "A"] as const;

function flareClassScore(classType: string): number {
  const letter = classType[0]?.toUpperCase() ?? "";
  const idx = (FLR_CLASS_ORDER as readonly string[]).indexOf(letter);
  const num = parseFloat(classType.slice(1)) || 0;
  return idx >= 0 ? (4 - idx) * 100 + num : -1;
}

interface FlareRow {
  id: string;
  date: string;
  classType: string;
  peakTime: string;
  sourceLocation: string;
}

function FlareDashboard({ events }: { events: SpaceWeatherEventData[] }) {
  const flares: FlareRow[] = useMemo(() => events.map((e) => {
    const d = parseRaw(e.raw_json);
    return {
      id: e.id,
      date: e.start_date.slice(0, 10),
      classType: typeof d.classType === "string" ? d.classType : "",
      peakTime: typeof d.peakTime === "string" ? d.peakTime : "",
      sourceLocation: typeof d.sourceLocation === "string" ? d.sourceLocation : "",
    };
  }), [events]);

  const sorted = useMemo(
    () => [...flares].sort((a, b) =>
      flareClassScore(b.classType) - flareClassScore(a.classType) || b.date.localeCompare(a.date)
    ),
    [flares],
  );

  const classCounts = useMemo(() => {
    const c: Record<string, number> = { X: 0, M: 0, C: 0, B: 0, A: 0 };
    for (const f of flares) {
      const l = f.classType[0]?.toUpperCase();
      if (l && l in c) c[l]++;
    }
    return c;
  }, [flares]);

  const maxCount = Math.max(...Object.values(classCounts), 1);
  const activeDays = new Set(flares.map((f) => f.date)).size;
  const peak = sorted[0]?.classType || "—";
  const peakColor = FLR_CLASS_COLORS[peak[0]?.toUpperCase()] ?? "#9ca3af";

  return (
    <div className="sw-dashboard">
      <div className="sw-stats-row">
        <div className="sw-stat-tile">
          <span className="sw-stat-tile__value" data-testid="flare-total">{flares.length}</span>
          <span className="sw-stat-tile__label">Total flares</span>
        </div>
        <div className="sw-stat-tile">
          <span className="sw-stat-tile__value" style={{ color: peakColor }} data-testid="flare-peak">
            {peak}
          </span>
          <span className="sw-stat-tile__label">Peak class</span>
        </div>
        <div className="sw-stat-tile">
          <span className="sw-stat-tile__value">{activeDays}</span>
          <span className="sw-stat-tile__label">Active days</span>
        </div>
      </div>

      <div className="sw-dist">
        {FLR_CLASS_ORDER.map((letter) => {
          const count = classCounts[letter];
          return (
            <div key={letter} className="sw-dist__row">
              <span className="sw-dist__label" style={{ color: FLR_CLASS_COLORS[letter] }}>
                {letter}
              </span>
              <div className="sw-dist__track" role="presentation">
                <div
                  className="sw-dist__fill"
                  style={{ width: `${(count / maxCount) * 100}%`, background: FLR_CLASS_COLORS[letter] }}
                />
              </div>
              <span className="sw-dist__count">{count}</span>
            </div>
          );
        })}
      </div>

      <div className="sw-event-list" role="list">
        {sorted.map((flare) => {
          const letter = flare.classType[0]?.toUpperCase() ?? "";
          const color = FLR_CLASS_COLORS[letter] ?? "#9ca3af";
          const timeLabel = flare.peakTime
            ? renderTimestamp(flare.peakTime)
            : formatDate(flare.date);
          return (
            <div
              key={flare.id}
              className="sw-event-row"
              role="listitem"
              aria-label={`FLR event ${flare.id}`}
            >
              <span className="sw-flare-row__class" style={{ color }}>
                {flare.classType || "—"}
              </span>
              <span className="sw-event-row__time">{timeLabel}</span>
              {flare.sourceLocation && (
                <span className="sw-event-row__loc">{flare.sourceLocation}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Activity Timeline (used by the RBE dashboard) ───────────────────────────────

function ActivityTimeline({ events, start, end, color }: {
  events: SpaceWeatherEventData[];
  start: string;
  end: string;
  color: string;
}) {
  const bars = useMemo(() => {
    const startMs = new Date(`${start}T00:00:00Z`).getTime();
    const endMs = new Date(`${end}T23:59:59Z`).getTime();
    if (Number.isNaN(startMs) || Number.isNaN(endMs)) return [];
    const msPerDay = 86_400_000;
    const totalDays = Math.max(1, Math.round((endMs - startMs) / msPerDay) + 1);
    const counts: Record<string, number> = {};
    for (let i = 0; i < totalDays; i++) {
      counts[new Date(startMs + i * msPerDay).toISOString().slice(0, 10)] = 0;
    }
    for (const e of events) {
      const day = e.start_date.slice(0, 10);
      if (day in counts) counts[day]++;
    }
    const max = Math.max(...Object.values(counts), 1);
    return Object.entries(counts).map(([date, count]) => ({
      date,
      count,
      h: count === 0 ? 0 : Math.max(0.08, count / max),
    }));
  }, [events, start, end]);

  if (bars.length < 3 || events.length === 0) return null;

  const totalEvents = events.length;
  const activeDays = bars.filter((b) => b.count > 0).length;

  return (
    <div className="sw-timeline" aria-hidden="true">
      <div className="sw-timeline-header">
        <span className="sw-timeline-stat">{totalEvents} events over {activeDays} active day{activeDays !== 1 ? "s" : ""}</span>
      </div>
      <div className="sw-timeline-bars">
        {bars.map(({ date, count, h }) => (
          <div key={date} className="sw-timeline-bar-wrap" title={count > 0 ? `${date}: ${count} event${count !== 1 ? "s" : ""}` : date}>
            <div
              className="sw-timeline-bar"
              style={{ height: `${h * 100}%`, background: color }}
            />
          </div>
        ))}
      </div>
      <div className="sw-timeline-labels">
        <span>{start}</span>
        <span>{end}</span>
      </div>
    </div>
  );
}

// ── Storm dashboard (GST) ───────────────────────────────────────────────────────

const KP_LEVELS = [
  { key: "G5", label: "Extreme", min: 9, color: "#ef4444" },
  { key: "G4", label: "Severe", min: 8, color: "#f97316" },
  { key: "G3", label: "Strong", min: 7, color: "#f59e0b" },
  { key: "G2", label: "Moderate", min: 6, color: "#eab308" },
  { key: "G1", label: "Minor", min: 5, color: "#84cc16" },
] as const;

function kpLevel(kp: number): { key: string; label: string; color: string } {
  return KP_LEVELS.find((l) => kp >= l.min) ?? { key: "—", label: "Below G1", color: "#6b7280" };
}

interface StormRow {
  id: string;
  date: string;
  maxKp: number;
}

function StormDashboard({ events }: { events: SpaceWeatherEventData[] }) {
  const storms: StormRow[] = useMemo(() => events.map((e) => {
    const d = parseRaw(e.raw_json);
    const allKp = Array.isArray(d.allKpIndex) ? d.allKpIndex : [];
    const kpValues = allKp
      .map((k: unknown) => (k && typeof k === "object" ? (k as Record<string, unknown>).kpIndex : null))
      .filter((v): v is number => typeof v === "number");
    return { id: e.id, date: e.start_date.slice(0, 10), maxKp: kpValues.length ? Math.max(...kpValues) : 0 };
  }), [events]);

  const sorted = useMemo(
    () => [...storms].sort((a, b) => b.maxKp - a.maxKp || b.date.localeCompare(a.date)),
    [storms],
  );

  const levelCounts = useMemo(() => {
    const c: Record<string, number> = { G1: 0, G2: 0, G3: 0, G4: 0, G5: 0 };
    for (const s of storms) {
      const lvl = kpLevel(s.maxKp).key;
      if (lvl in c) c[lvl]++;
    }
    return c;
  }, [storms]);

  const maxCount = Math.max(...Object.values(levelCounts), 1);
  const activeDays = new Set(storms.map((s) => s.date)).size;
  const maxKpOverall = Math.max(...storms.map((s) => s.maxKp), 0);
  const peakColor = kpLevel(maxKpOverall).color;

  return (
    <div className="sw-dashboard">
      <div className="sw-stats-row">
        <div className="sw-stat-tile">
          <span className="sw-stat-tile__value">{storms.length}</span>
          <span className="sw-stat-tile__label">Total storms</span>
        </div>
        <div className="sw-stat-tile">
          <span className="sw-stat-tile__value" style={{ color: peakColor }}>{maxKpOverall || "—"}</span>
          <span className="sw-stat-tile__label">Peak Kp</span>
        </div>
        <div className="sw-stat-tile">
          <span className="sw-stat-tile__value">{activeDays}</span>
          <span className="sw-stat-tile__label">Active days</span>
        </div>
      </div>

      <div className="sw-dist">
        {KP_LEVELS.map((lvl) => (
          <div key={lvl.key} className="sw-dist__row">
            <span className="sw-dist__label" style={{ color: lvl.color }}>{lvl.key}</span>
            <div className="sw-dist__track" role="presentation">
              <div
                className="sw-dist__fill"
                style={{ width: `${(levelCounts[lvl.key] / maxCount) * 100}%`, background: lvl.color }}
              />
            </div>
            <span className="sw-dist__count">{levelCounts[lvl.key]}</span>
          </div>
        ))}
      </div>

      <div className="sw-event-list" role="list">
        {sorted.map((storm) => {
          const lvl = kpLevel(storm.maxKp);
          return (
            <div key={storm.id} className="sw-event-row" role="listitem" aria-label={`GST event ${storm.id}`}>
              <span className="sw-event-row__badge" style={{ color: lvl.color, borderColor: lvl.color }}>
                Kp {storm.maxKp || "—"}
              </span>
              <span className="sw-event-row__time">{formatDate(storm.date)}</span>
              <span className="sw-event-row__loc">{lvl.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── CME dashboard ────────────────────────────────────────────────────────────────

const CME_SPEED_BUCKETS = [
  { key: "<500", label: "<500", test: (s: number) => s < 500 },
  { key: "500-999", label: "500–999", test: (s: number) => s >= 500 && s < 1000 },
  { key: "1000-1499", label: "1000–1499", test: (s: number) => s >= 1000 && s < 1500 },
  { key: "1500-1999", label: "1500–1999", test: (s: number) => s >= 1500 && s < 2000 },
  { key: "2000+", label: "2000+", test: (s: number) => s >= 2000 },
] as const;

function cmeSpeedColor(speed: number): string {
  if (speed >= 2000) return "#ef4444";
  if (speed >= 1000) return "#f97316";
  if (speed >= 500) return "#facc15";
  return "#22c55e";
}

interface CmeRow {
  id: string;
  date: string;
  speed: number | null;
  type: string;
}

function CmeDashboard({ events }: { events: SpaceWeatherEventData[] }) {
  const cmes: CmeRow[] = useMemo(() => events.map((e) => {
    const d = parseRaw(e.raw_json);
    const analyses = Array.isArray(d.cmeAnalyses) ? d.cmeAnalyses : [];
    const first = analyses[0] as Record<string, unknown> | undefined;
    return {
      id: e.id,
      date: e.start_date.slice(0, 10),
      speed: first && typeof first.speed === "number" ? first.speed : null,
      type: first && typeof first.type === "string" ? first.type : "",
    };
  }), [events]);

  const sorted = useMemo(
    () => [...cmes].sort((a, b) => (b.speed ?? -1) - (a.speed ?? -1) || b.date.localeCompare(a.date)),
    [cmes],
  );

  const speeds = cmes.map((c) => c.speed).filter((s): s is number => s !== null);
  const maxSpeed = speeds.length ? Math.max(...speeds) : 0;
  const avgSpeed = speeds.length ? Math.round(speeds.reduce((a, b) => a + b, 0) / speeds.length) : 0;

  const bucketCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const b of CME_SPEED_BUCKETS) c[b.key] = 0;
    for (const s of speeds) {
      const b = CME_SPEED_BUCKETS.find((bucket) => bucket.test(s));
      if (b) c[b.key]++;
    }
    return c;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cmes]);

  const maxBucket = Math.max(...Object.values(bucketCounts), 1);

  return (
    <div className="sw-dashboard">
      <div className="sw-stats-row">
        <div className="sw-stat-tile">
          <span className="sw-stat-tile__value">{cmes.length}</span>
          <span className="sw-stat-tile__label">Total CMEs</span>
        </div>
        <div className="sw-stat-tile">
          <span className="sw-stat-tile__value" style={{ color: cmeSpeedColor(maxSpeed) }}>{maxSpeed || "—"}</span>
          <span className="sw-stat-tile__label">Max speed (km/s)</span>
        </div>
        <div className="sw-stat-tile">
          <span className="sw-stat-tile__value">{avgSpeed || "—"}</span>
          <span className="sw-stat-tile__label">Avg speed (km/s)</span>
        </div>
      </div>

      <div className="sw-dist">
        {CME_SPEED_BUCKETS.map((b) => (
          <div key={b.key} className="sw-dist__row">
            <span className="sw-dist__label">{b.label}</span>
            <div className="sw-dist__track" role="presentation">
              <div
                className="sw-dist__fill"
                style={{ width: `${(bucketCounts[b.key] / maxBucket) * 100}%`, background: "#facc15" }}
              />
            </div>
            <span className="sw-dist__count">{bucketCounts[b.key]}</span>
          </div>
        ))}
      </div>

      <div className="sw-event-list" role="list">
        {sorted.map((cme) => {
          const color = cmeSpeedColor(cme.speed ?? 0);
          return (
            <div key={cme.id} className="sw-event-row" role="listitem" aria-label={`CME event ${cme.id}`}>
              <span className="sw-event-row__badge" style={{ color, borderColor: color }}>
                {cme.speed !== null ? `${Math.round(cme.speed)} km/s` : "—"}
              </span>
              <span className="sw-event-row__time">{formatDate(cme.date)}</span>
              {cme.type && <span className="sw-event-row__loc">{cme.type}</span>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── SEP dashboard ────────────────────────────────────────────────────────────────

function instrumentNames(data: Record<string, unknown>): string[] {
  const instruments = Array.isArray(data.instruments) ? data.instruments : [];
  return instruments
    .map((i: unknown) => (i && typeof i === "object" ? (i as Record<string, unknown>).displayName : null))
    .filter((v): v is string => typeof v === "string");
}

interface SepRow {
  id: string;
  date: string;
  instruments: string[];
}

function SepDashboard({ events }: { events: SpaceWeatherEventData[] }) {
  const seps: SepRow[] = useMemo(() => events.map((e) => {
    const d = parseRaw(e.raw_json);
    return { id: e.id, date: e.start_date.slice(0, 10), instruments: instrumentNames(d) };
  }), [events]);

  const sorted = useMemo(() => [...seps].sort((a, b) => b.date.localeCompare(a.date)), [seps]);
  const activeDays = new Set(seps.map((s) => s.date)).size;

  const instrumentCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const s of seps) for (const inst of s.instruments) c[inst] = (c[inst] ?? 0) + 1;
    return c;
  }, [seps]);

  const topInstruments = useMemo(
    () => Object.entries(instrumentCounts).sort((a, b) => b[1] - a[1]).slice(0, 5),
    [instrumentCounts],
  );
  const maxInstrCount = Math.max(...topInstruments.map(([, count]) => count), 1);

  return (
    <div className="sw-dashboard">
      <div className="sw-stats-row">
        <div className="sw-stat-tile">
          <span className="sw-stat-tile__value">{seps.length}</span>
          <span className="sw-stat-tile__label">Total events</span>
        </div>
        <div className="sw-stat-tile">
          <span className="sw-stat-tile__value">{Object.keys(instrumentCounts).length}</span>
          <span className="sw-stat-tile__label">Instruments</span>
        </div>
        <div className="sw-stat-tile">
          <span className="sw-stat-tile__value">{activeDays}</span>
          <span className="sw-stat-tile__label">Active days</span>
        </div>
      </div>

      {topInstruments.length > 0 && (
        <div className="sw-dist">
          {topInstruments.map(([name, count]) => (
            <div key={name} className="sw-dist__row sw-dist__row--wide">
              <span className="sw-dist__label sw-dist__label--text" title={name}>{name}</span>
              <div className="sw-dist__track" role="presentation">
                <div
                  className="sw-dist__fill"
                  style={{ width: `${(count / maxInstrCount) * 100}%`, background: "#34d399" }}
                />
              </div>
              <span className="sw-dist__count">{count}</span>
            </div>
          ))}
        </div>
      )}

      <div className="sw-event-list" role="list">
        {sorted.map((sep) => (
          <div key={sep.id} className="sw-event-row" role="listitem" aria-label={`SEP event ${sep.id}`}>
            <span className="sw-event-row__time">{formatDate(sep.date)}</span>
            <span className="sw-event-row__loc">
              {sep.instruments[0] ?? "—"}
              {sep.instruments.length > 1 ? ` +${sep.instruments.length - 1}` : ""}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── RBE dashboard ────────────────────────────────────────────────────────────────

interface RbeRow {
  id: string;
  date: string;
  rbId: string;
}

function RbeDashboard({ events, start, end }: { events: SpaceWeatherEventData[]; start: string; end: string }) {
  const rbes: RbeRow[] = useMemo(() => events.map((e) => {
    const d = parseRaw(e.raw_json);
    return { id: e.id, date: e.start_date.slice(0, 10), rbId: typeof d.rbID === "string" ? d.rbID : "" };
  }), [events]);

  const sorted = useMemo(() => [...rbes].sort((a, b) => b.date.localeCompare(a.date)), [rbes]);
  const activeDays = new Set(rbes.map((r) => r.date)).size;

  return (
    <div className="sw-dashboard">
      <div className="sw-stats-row">
        <div className="sw-stat-tile">
          <span className="sw-stat-tile__value">{rbes.length}</span>
          <span className="sw-stat-tile__label">Total events</span>
        </div>
        <div className="sw-stat-tile">
          <span className="sw-stat-tile__value">{activeDays}</span>
          <span className="sw-stat-tile__label">Active days</span>
        </div>
        <div className="sw-stat-tile">
          <span className="sw-stat-tile__value">{sorted[0] ? formatDate(sorted[0].date) : "—"}</span>
          <span className="sw-stat-tile__label">Most recent</span>
        </div>
      </div>

      <ActivityTimeline events={events} start={start} end={end} color={TAB_COLORS.RBE} />

      <div className="sw-event-list" role="list">
        {sorted.map((rbe) => (
          <div key={rbe.id} className="sw-event-row" role="listitem" aria-label={`RBE event ${rbe.id}`}>
            <span className="sw-event-row__time">{formatDate(rbe.date)}</span>
            {rbe.rbId && <span className="sw-event-row__loc">{rbe.rbId}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── TabPanel ──────────────────────────────────────────────────────────────────

function TabPanel({ eventType, start, end }: { eventType: Tab; start: string; end: string }) {
  const { t } = useTranslation();
  const { data, isLoading, isError, error, refetch } = useSpaceWeatherEvents(eventType, start, end);

  if (isLoading) {
    return <p role="status" className="sw-loading">{t("common.loading")}</p>;
  }

  if (isError && error) {
    return (
      <ErrorBanner
        titleKey={errorTitleKey(error.code)}
        detail={error.message}
        onRetry={() => refetch()}
        variant="section"
      />
    );
  }

  if (!data || data.data.length === 0) {
    return <p className="sw-empty">{t("spaceWeather.noEvents")}</p>;
  }

  return (
    <>
      <p className="sw-status-badge" aria-label={data.cached ? "cached" : "live"}>
        <span className={`sw-status-dot ${data.cached ? "sw-status-dot--cached" : "sw-status-dot--live"}`} />
        {data.stale
          ? t("error.staleData", { date: formatDateTime(data.fetched_at) })
          : data.cached
            ? `${t("common.cached")} · ${t("common.fetchedAt")} ${formatDateTime(data.fetched_at)}`
            : `${t("common.live")} · ${t("common.fetchedAt")} ${formatDateTime(data.fetched_at)}`}
      </p>

      {eventType === "FLR" && <FlareDashboard events={data.data} />}
      {eventType === "GST" && <StormDashboard events={data.data} />}
      {eventType === "CME" && <CmeDashboard events={data.data} />}
      {eventType === "SEP" && <SepDashboard events={data.data} />}
      {eventType === "RBE" && <RbeDashboard events={data.data} start={start} end={end} />}
    </>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SpaceWeatherPage() {
  const defaultEnd = todayIso();
  const defaultStart = addDaysIso(defaultEnd, -29);
  const [start, setStart] = useState(defaultStart);
  const [end, setEnd] = useState(defaultEnd);
  const [activeTab, setActiveTab] = useState<Tab>("FLR");
  const { t } = useTranslation();

  return (
    <div className="sw-page">
      <h1>{t("spaceWeather.title")}</h1>

      <div className="sw-controls">
        <div className="sw-date-row">
          <label className="sw-date-label" htmlFor="sw-start">
            {t("common.start")}
            <input
              id="sw-start"
              type="date"
              value={start}
              max={end}
              onChange={(e) => setStart(e.target.value)}
              className="sw-date-input"
            />
          </label>
          <span className="sw-date-arrow" aria-hidden="true">→</span>
          <label className="sw-date-label" htmlFor="sw-end">
            {t("common.end")}
            <input
              id="sw-end"
              type="date"
              value={end}
              min={start}
              onChange={(e) => setEnd(e.target.value)}
              className="sw-date-input"
            />
          </label>
        </div>
      </div>

      <div className="sw-tabs" role="tablist" aria-label={t("spaceWeather.title")}>
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`sw-panel-${tab.id}`}
            id={`sw-tab-${tab.id}`}
            onClick={() => setActiveTab(tab.id)}
            className={`sw-tab sw-tab--${tab.id}${activeTab === tab.id ? " sw-tab--active" : ""}`}
          >
            {TAB_ICONS[tab.id]}
            {t(tab.labelKey)}
          </button>
        ))}
      </div>

      {TABS.map((tab) => (
        <div
          key={tab.id}
          id={`sw-panel-${tab.id}`}
          role="tabpanel"
          aria-labelledby={`sw-tab-${tab.id}`}
          hidden={activeTab !== tab.id}
          className="sw-panel"
        >
          {activeTab === tab.id && (
            <TabPanel eventType={tab.id} start={start} end={end} />
          )}
        </div>
      ))}
    </div>
  );
}
