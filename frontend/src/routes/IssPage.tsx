import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import Globe from "globe.gl";
import {
  useIssPositions,
  useIssQuota,
  useIssRadioPasses,
  useIssTle,
  useIssVisualPasses,
} from "@/hooks/useIss";
import { ErrorBanner } from "@/components/ErrorBanner";
import { formatDateTime, formatTime } from "@/lib/dateTime";
import type { IssPosition } from "@/types/api";

const DEFAULT_LAT = 0;
const DEFAULT_LNG = 0;
const DEFAULT_ALT = 0;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function fmtDeg(value: number, posLabel: string, negLabel: string): string {
  return `${Math.abs(value).toFixed(4)}° ${value >= 0 ? posLabel : negLabel}`;
}

export default function IssPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  const [observerLat] = useState<number>(DEFAULT_LAT);
  const [observerLng] = useState<number>(DEFAULT_LNG);
  const [observerAlt] = useState<number>(DEFAULT_ALT);
  const [locationDenied] = useState<boolean>(false);
  const [currentPos, setCurrentPos] = useState<IssPosition | null>(null);
  const [updating, setUpdating] = useState<boolean>(false);

  const { data: posData, isError: posError, error: posErr } = useIssPositions();
  const { data: tleData } = useIssTle();
  const { data: visualData } = useIssVisualPasses(observerLat, observerLng, observerAlt);
  const { data: radioData } = useIssRadioPasses(observerLat, observerLng, observerAlt);
  const { data: quotaData } = useIssQuota();

  // P17: Guard containerRef.current inside useEffect
  useEffect(() => {
    if (!containerRef.current) return;
    const g = new Globe()(containerRef.current);
    g.globeImageUrl("//unpacked.globe.gl/earthmap.jpg");
    return () => {
      g._destructor?.();
    };
  }, []);

  // Client-side position interpolation
  useEffect(() => {
    if (!posData?.positions?.length) return;

    const positions = posData.positions;
    const fetchedAtMs = new Date(posData.fetched_at).getTime();

    const interval = setInterval(() => {
      const offset = Math.floor((Date.now() - fetchedAtMs) / 1000);
      if (offset >= 300) {
        setUpdating(true);
        setCurrentPos(positions[299]);
      } else {
        setUpdating(false);
        setCurrentPos(positions[clamp(offset, 0, 299)]);
      }
    }, 1000);

    // Invalidate 30 s before the 300-entry batch expires
    const invalidateTimeout = setTimeout(
      () => {
        queryClient.invalidateQueries({ queryKey: ["iss", "positions"] });
      },
      Math.max(0, (fetchedAtMs + 270_000) - Date.now()),
    );

    return () => {
      clearInterval(interval);
      clearTimeout(invalidateTimeout);
    };
  }, [posData, queryClient]);

  const quotaWarning = quotaData && quotaData.used >= 800 && quotaData.used < quotaData.cap;
  const quotaExhausted = posData?.quota_exhausted || tleData?.quota_exhausted;

  const nextVisualPass = visualData?.passes?.[0] ?? null;
  const nextRadioPass = radioData?.passes?.[0] ?? null;

  return (
    <div className="iss-page">
      <h1>ISS Tracker</h1>

      {locationDenied && (
        <p className="iss-location-denied" role="status">
          Location access denied — using default observer position (0°N 0°E)
        </p>
      )}

      {quotaWarning && (
        <p className="iss-quota-warning" role="status">
          N2YO API quota nearly exhausted — showing cached data
        </p>
      )}

      {quotaExhausted && quotaData && (
        <p className="iss-quota-exhausted" role="alert">
          N2YO API quota exhausted for this hour. Live updates paused. Resets at{" "}
          {formatTime(quotaData.resets_at)}.
        </p>
      )}

      {updating && (
        <p className="iss-updating" aria-live="polite">
          Updating…
        </p>
      )}

      {posError && posErr && (
        <ErrorBanner
          title="ISS data unavailable"
          detail={posErr.message}
          variant="section"
        />
      )}

      {/* Globe */}
      <div
        ref={containerRef}
        className="iss-globe"
        aria-label="ISS globe tracker"
        data-testid="iss-globe"
      />

      {/* Data panel */}
      {currentPos && (
        <section className="iss-data-panel" aria-label="ISS data">
          <dl>
            <dt>Latitude</dt>
            <dd>{fmtDeg(currentPos.satlatitude, "N", "S")}</dd>
            <dt>Longitude</dt>
            <dd>{fmtDeg(currentPos.satlongitude, "E", "W")}</dd>
            <dt>Altitude</dt>
            <dd>{currentPos.sataltitude.toFixed(1)} km</dd>
            <dt>Azimuth</dt>
            <dd>{currentPos.azimuth.toFixed(1)}°</dd>
            <dt>Elevation</dt>
            <dd>{currentPos.elevation.toFixed(1)}°</dd>
            <dt>In Shadow</dt>
            <dd>{currentPos.eclipsed ? "Yes" : "No"}</dd>
          </dl>

          {tleData && (
            <details className="iss-tle">
              <summary>TLE data</summary>
              <pre>{[tleData.tle_line0, tleData.tle_line1, tleData.tle_line2].join("\n")}</pre>
            </details>
          )}

          {nextVisualPass && (
            <div className="iss-next-pass">
              <h3>Next Visible Pass</h3>
              <p>{formatDateTime(new Date(nextVisualPass.startUTC * 1000).toISOString())}</p>
              <p>Duration: {nextVisualPass.duration} s · Max elevation: {nextVisualPass.maxEl}°</p>
            </div>
          )}

          {nextRadioPass && (
            <div className="iss-next-radio-pass">
              <h3>Next Radio Pass</h3>
              <p>{formatDateTime(new Date(nextRadioPass.startUTC * 1000).toISOString())}</p>
              <p>Duration: {nextRadioPass.duration} s</p>
            </div>
          )}
        </section>
      )}

      {quotaData && (
        <p className="iss-quota-info" aria-label="quota-info">
          API Quota: {quotaData.used} / {quotaData.cap} used this hour
        </p>
      )}
    </div>
  );
}
