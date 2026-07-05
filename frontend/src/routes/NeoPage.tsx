import { useMemo, useState } from "react";
import { useNeoFeed } from "@/hooks/useNeo";
import { ErrorBanner } from "@/components/ErrorBanner";
import { formatDate, formatDateTime } from "@/lib/dateTime";
import type { NeoData } from "@/types/api";

type SortKey = "name" | "close_approach_date" | "diameter" | "velocity" | "miss_distance";
type SortDir = "asc" | "desc";

function errorTitle(code: string): string {
  switch (code) {
    case "NO_INTERNET":
      return "No internet connection";
    case "NASA_UNAVAILABLE":
      return "NASA services are currently unavailable";
    case "NASA_AUTH_ERROR":
      return "Invalid NASA API Key";
    case "NASA_ERROR":
      return "NASA returned an error";
    case "INVALID_RANGE":
      return "Invalid date range";
    default:
      return "Something went wrong";
  }
}

function todayIso(): string {
  const now = new Date();
  const y = now.getUTCFullYear();
  const m = String(now.getUTCMonth() + 1).padStart(2, "0");
  const d = String(now.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function addDaysIso(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

function compareNumber(a: number | null | undefined, b: number | null | undefined): number {
  const aa = a ?? -Infinity;
  const bb = b ?? -Infinity;
  return aa === bb ? 0 : aa < bb ? -1 : 1;
}

function sortRows(rows: NeoData[], key: SortKey, dir: SortDir): NeoData[] {
  const factor = dir === "asc" ? 1 : -1;
  const copy = [...rows];
  copy.sort((a, b) => {
    switch (key) {
      case "name":
        return factor * a.name.localeCompare(b.name);
      case "close_approach_date":
        return factor * a.close_approach_date.localeCompare(b.close_approach_date);
      case "diameter":
        return factor * compareNumber(a.estimated_diameter_max_km, b.estimated_diameter_max_km);
      case "velocity":
        return factor * compareNumber(a.relative_velocity_kph, b.relative_velocity_kph);
      case "miss_distance":
        return factor * compareNumber(a.miss_distance_km, b.miss_distance_km);
      default:
        return 0;
    }
  });
  return copy;
}

function fmtNumber(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export default function NeoPage() {
  const defaultEnd = todayIso();
  const defaultStart = addDaysIso(defaultEnd, -6);
  const [start, setStart] = useState<string>(defaultStart);
  const [end, setEnd] = useState<string>(defaultEnd);
  const [sortKey, setSortKey] = useState<SortKey>("close_approach_date");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data, isLoading, isError, error, refetch } = useNeoFeed(start, end);

  const rows = useMemo(() => {
    if (!data?.data) return [];
    return sortRows(data.data, sortKey, sortDir);
  }, [data?.data, sortKey, sortDir]);

  const selected = useMemo(
    () => rows.find((row) => row.id === selectedId) ?? null,
    [rows, selectedId],
  );

  function toggleSort(nextKey: SortKey) {
    if (nextKey === sortKey) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(nextKey);
      setSortDir("asc");
    }
  }

  function sortIndicator(key: SortKey): string {
    if (key !== sortKey) return "";
    return sortDir === "asc" ? " ↑" : " ↓";
  }

  return (
    <div className="neo-page">
      <h1>Near-Earth Objects</h1>

      <div className="neo-filters">
        <label htmlFor="neo-start">
          Start
          <input
            id="neo-start"
            type="date"
            value={start}
            max={end}
            onChange={(event) => setStart(event.target.value)}
          />
        </label>
        <label htmlFor="neo-end">
          End
          <input
            id="neo-end"
            type="date"
            value={end}
            min={start}
            max={addDaysIso(start, 6)}
            onChange={(event) => setEnd(event.target.value)}
          />
        </label>
        <p className="neo-hint">Maximum 7-day range.</p>
      </div>

      {isLoading ? (
        <p role="status">Loading…</p>
      ) : isError && error ? (
        <ErrorBanner
          title={errorTitle(error.code)}
          detail={error.message}
          onRetry={() => refetch()}
          variant="section"
        />
      ) : !data || rows.length === 0 ? (
        <p className="neo-empty">No near-earth objects found in this range.</p>
      ) : (
        <>
          <p
            className="neo-badge"
            aria-label={data.cached ? "cached" : "live"}
          >
            {data.stale
              ? `Showing cached data from ${formatDateTime(data.fetched_at)}`
              : data.cached
                ? `Served from cache · fetched ${formatDateTime(data.fetched_at)}`
                : `Live · fetched ${formatDateTime(data.fetched_at)}`}
          </p>

          <table className="neo-table" aria-label="Near-earth objects">
            <thead>
              <tr>
                <th>
                  <button type="button" onClick={() => toggleSort("name")}>
                    Name{sortIndicator("name")}
                  </button>
                </th>
                <th>
                  <button type="button" onClick={() => toggleSort("close_approach_date")}>
                    Close Approach{sortIndicator("close_approach_date")}
                  </button>
                </th>
                <th>
                  <button type="button" onClick={() => toggleSort("diameter")}>
                    Diameter (km){sortIndicator("diameter")}
                  </button>
                </th>
                <th>
                  <button type="button" onClick={() => toggleSort("velocity")}>
                    Velocity (kph){sortIndicator("velocity")}
                  </button>
                </th>
                <th>
                  <button type="button" onClick={() => toggleSort("miss_distance")}>
                    Miss Distance (km){sortIndicator("miss_distance")}
                  </button>
                </th>
                <th>Hazardous</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className={row.is_potentially_hazardous ? "neo-row neo-row--hazardous" : "neo-row"}
                  data-hazardous={row.is_potentially_hazardous ? "true" : "false"}
                  onClick={() => setSelectedId(row.id)}
                >
                  <td>
                    <button
                      type="button"
                      className="neo-row-button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedId(row.id);
                      }}
                    >
                      {row.name}
                    </button>
                  </td>
                  <td>{formatDate(row.close_approach_date)}</td>
                  <td>{fmtNumber(row.estimated_diameter_max_km, 3)}</td>
                  <td>{fmtNumber(row.relative_velocity_kph)}</td>
                  <td>{fmtNumber(row.miss_distance_km)}</td>
                  <td>
                    {row.is_potentially_hazardous ? (
                      <span className="neo-hazard-badge" aria-label="Potentially Hazardous">
                        Potentially Hazardous
                      </span>
                    ) : (
                      <span className="neo-safe">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {selected ? (
        <aside
          className="neo-drawer"
          role="dialog"
          aria-label={`Details for ${selected.name}`}
        >
          <button
            type="button"
            className="neo-drawer-close"
            onClick={() => setSelectedId(null)}
            aria-label="Close details"
          >
            Close
          </button>
          <h2>{selected.name}</h2>
          <dl>
            <dt>ID</dt>
            <dd>{selected.id}</dd>
            <dt>Close approach</dt>
            <dd>{formatDate(selected.close_approach_date)}</dd>
            <dt>Absolute magnitude (H)</dt>
            <dd>{fmtNumber(selected.absolute_magnitude_h, 2)}</dd>
            <dt>Diameter min (km)</dt>
            <dd>{fmtNumber(selected.estimated_diameter_min_km, 3)}</dd>
            <dt>Diameter max (km)</dt>
            <dd>{fmtNumber(selected.estimated_diameter_max_km, 3)}</dd>
            <dt>Velocity (kph)</dt>
            <dd>{fmtNumber(selected.relative_velocity_kph)}</dd>
            <dt>Miss distance (km)</dt>
            <dd>{fmtNumber(selected.miss_distance_km)}</dd>
            <dt>Orbiting body</dt>
            <dd>{selected.orbiting_body ?? "—"}</dd>
            <dt>Hazardous</dt>
            <dd>{selected.is_potentially_hazardous ? "Yes" : "No"}</dd>
            {selected.nasa_jpl_url ? (
              <>
                <dt>JPL</dt>
                <dd>
                  <a href={selected.nasa_jpl_url} target="_blank" rel="noreferrer">
                    View on JPL
                  </a>
                </dd>
              </>
            ) : null}
          </dl>
        </aside>
      ) : null}
    </div>
  );
}
