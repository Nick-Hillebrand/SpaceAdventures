import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import Globe from "globe.gl";
import {
  useIssPositions,
  useIssQuota,
  useIssRadioPasses,
  useIssTle,
  useIssVisualPasses,
  useMyIssPasses,
} from "@/hooks/useIss";
import { useMe } from "@/hooks/useAuth";
import { useCreateSubscription, useDeleteSubscription, useSubscriptions } from "@/hooks/useSubscriptions";
import { ErrorBanner } from "@/components/ErrorBanner";
import { formatDateTime, formatTime } from "@/lib/dateTime";
import type { IssPosition } from "@/types/api";

const DEFAULT_LAT = 0;
const DEFAULT_LNG = 0;
const DEFAULT_ALT = 0;
const GLOBE_FALLBACK_HEIGHT = 480;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function fmtDeg(value: number, posLabel: string, negLabel: string): string {
  return `${Math.abs(value).toFixed(4)}° ${value >= 0 ? posLabel : negLabel}`;
}

export default function IssPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const globeRef = useRef<any>(null);
  const hasCenteredRef = useRef(false);
  const queryClient = useQueryClient();
  const { t } = useTranslation();

  const [observerLat] = useState<number>(DEFAULT_LAT);
  const [observerLng] = useState<number>(DEFAULT_LNG);
  const [observerAlt] = useState<number>(DEFAULT_ALT);
  const [locationDenied] = useState<boolean>(false);
  const [currentPos, setCurrentPos] = useState<IssPosition | null>(null);
  const [updating, setUpdating] = useState<boolean>(false);
  const [issAlertError, setIssAlertError] = useState<string | null>(null);

  const { data: posData, isError: posError, error: posErr } = useIssPositions();
  const { data: tleData } = useIssTle();
  const { data: visualData } = useIssVisualPasses(observerLat, observerLng, observerAlt);
  const { data: radioData } = useIssRadioPasses(observerLat, observerLng, observerAlt);
  const { data: quotaData } = useIssQuota();
  const { data: user } = useMe();
  const hasLocation =
    typeof user?.location_lat === "number" && typeof user?.location_lng === "number";
  const {
    data: myPassesData,
    isLoading: myPassesLoading,
    isError: myPassesIsError,
    error: myPassesErr,
  } = useMyIssPasses(hasLocation);
  const { data: subscriptions } = useSubscriptions();
  const createSubscription = useCreateSubscription();
  const deleteSubscription = useDeleteSubscription();

  // P17: Guard containerRef.current inside useEffect
  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;

    const g = new Globe()(el)
      .width(el.clientWidth || el.parentElement?.clientWidth || GLOBE_FALLBACK_HEIGHT)
      .height(el.clientHeight || GLOBE_FALLBACK_HEIGHT)
      .globeImageUrl("/globe/earth-blue-marble.jpg")
      .bumpImageUrl("/globe/earth-topology.png")
      .backgroundImageUrl("/globe/night-sky.png")
      .showAtmosphere(true)
      .atmosphereColor("#4f9cf9")
      .atmosphereAltitude(0.18)
      .pointAltitude(0.015)
      .pointRadius(0.55)
      .pointColor(() => "#f87171")
      .pointLabel((d: { label: string }) => d.label)
      .ringColor(() => (frac: number) => `rgba(248, 113, 113, ${1 - frac})`)
      .ringMaxRadius(4)
      .ringPropagationSpeed(2)
      .ringRepeatPeriod(1200);

    g.pointOfView({ lat: 20, lng: 0, altitude: 2.5 });

    const handleResize = () => {
      if (!containerRef.current) return;
      g.width(containerRef.current.clientWidth);
      g.height(containerRef.current.clientHeight || GLOBE_FALLBACK_HEIGHT);
    };
    window.addEventListener("resize", handleResize);

    globeRef.current = g;

    return () => {
      window.removeEventListener("resize", handleResize);
      globeRef.current = null;
      g._destructor?.();
    };
  }, [t]);

  // Keep the ISS marker in sync with the interpolated position
  useEffect(() => {
    if (!globeRef.current || !currentPos) return;

    const marker = {
      lat: currentPos.satlatitude,
      lng: currentPos.satlongitude,
      label: `ISS · ${currentPos.sataltitude.toFixed(0)} km`,
    };

    globeRef.current.pointsData([marker]);
    globeRef.current.ringsData([marker]);

    if (!hasCenteredRef.current) {
      hasCenteredRef.current = true;
      globeRef.current.pointOfView({ lat: marker.lat, lng: marker.lng, altitude: 2.2 }, 1000);
    }
  }, [currentPos]);

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

  const issPassSubscription = subscriptions?.find((s) => s.type === "iss_pass") ?? null;

  async function handleSubscribeIssPass() {
    setIssAlertError(null);
    try {
      await createSubscription.mutateAsync({
        type: "iss_pass",
        notify_email: true,
        notify_sms: false,
        notify_push: true,
      });
    } catch (err) {
      const code = (err as { code?: string }).code;
      if (code === "CONSENT_REQUIRED") {
        setIssAlertError(t("iss.alertMeConsentRequired"));
      } else if (code === "PRO_REQUIRED") {
        setIssAlertError(t("iss.alertMeProRequired"));
      } else if (code !== "ALREADY_SUBSCRIBED") {
        setIssAlertError(t("iss.alertMeFailed"));
      }
    }
  }

  return (
    <div className="iss-page">
      <div className="iss-header">
        <h1>{t("iss.title")}</h1>
        {currentPos && !updating && (
          <span className="iss-live-badge iss-live-badge--live">
            <span className="iss-live-dot" aria-hidden="true" />
            {t("iss.live")}
          </span>
        )}
      </div>

      {locationDenied && (
        <p className="iss-location-denied" role="status">
          {t("iss.locationDenied")}
        </p>
      )}

      {quotaWarning && (
        <p className="iss-quota-warning" role="status">
          {t("iss.quotaWarning")}
        </p>
      )}

      {quotaExhausted && quotaData && (
        <p className="iss-quota-exhausted" role="alert">
          {t("iss.quotaExhausted", { time: formatTime(quotaData.resets_at) })}
        </p>
      )}

      {updating && (
        <p className="iss-updating" aria-live="polite">
          {t("iss.updating")}
        </p>
      )}

      {posError && posErr && (
        <ErrorBanner
          titleKey="iss.unavailable"
          detail={posErr.message}
          variant="section"
        />
      )}

      {/* Globe */}
      <div className="iss-globe-wrap">
        <div
          ref={containerRef}
          className="iss-globe"
          aria-label={t("iss.globeTrackerAria")}
          data-testid="iss-globe"
        />
        {currentPos && (
          <div className="iss-globe-overlay" aria-hidden="true">
            <span className="iss-globe-overlay__lat">{fmtDeg(currentPos.satlatitude, "N", "S")}</span>
            <span className="iss-globe-overlay__lng">{fmtDeg(currentPos.satlongitude, "E", "W")}</span>
          </div>
        )}
      </div>

      {/* Data panel */}
      {currentPos && (
        <section className="iss-data-panel" aria-label={t("iss.dataPanelAria")}>
          <dl className="iss-stat-grid">
            <div className="iss-stat-tile">
              <dt>{t("iss.latitude")}</dt>
              <dd>{fmtDeg(currentPos.satlatitude, "N", "S")}</dd>
            </div>
            <div className="iss-stat-tile">
              <dt>{t("iss.longitude")}</dt>
              <dd>{fmtDeg(currentPos.satlongitude, "E", "W")}</dd>
            </div>
            <div className="iss-stat-tile">
              <dt>{t("iss.altitude")}</dt>
              <dd>{currentPos.sataltitude.toFixed(1)} km</dd>
            </div>
            <div className="iss-stat-tile">
              <dt>{t("iss.azimuth")}</dt>
              <dd>{currentPos.azimuth.toFixed(1)}°</dd>
            </div>
            <div className="iss-stat-tile">
              <dt>{t("iss.elevation")}</dt>
              <dd>{currentPos.elevation.toFixed(1)}°</dd>
            </div>
            <div
              className={`iss-stat-tile ${currentPos.eclipsed ? "iss-stat-tile--eclipsed" : "iss-stat-tile--sunlit"}`}
            >
              <dt>{t("iss.eclipsed")}</dt>
              <dd>{currentPos.eclipsed ? t("iss.yes") : t("iss.no")}</dd>
            </div>
          </dl>

          <div className="iss-panel-grid">
            {tleData && (
              <details className="iss-tle">
                <summary>{t("iss.tleData")}</summary>
                <pre>{[tleData.tle_line0, tleData.tle_line1, tleData.tle_line2].join("\n")}</pre>
              </details>
            )}

            {nextVisualPass && (
              <div className="iss-next-pass iss-pass-card">
                <h3>{t("iss.nextVisiblePass")}</h3>
                <p>{formatDateTime(new Date(nextVisualPass.startUTC * 1000).toISOString())}</p>
                <p>{t("iss.duration")}: {nextVisualPass.duration} s · {t("iss.maxElevation")}: {nextVisualPass.maxEl}°</p>
              </div>
            )}

            {nextRadioPass && (
              <div className="iss-next-radio-pass iss-pass-card">
                <h3>{t("iss.nextRadioPass")}</h3>
                <p>{formatDateTime(new Date(nextRadioPass.startUTC * 1000).toISOString())}</p>
                <p>{t("iss.duration")}: {nextRadioPass.duration} s</p>
              </div>
            )}
          </div>
        </section>
      )}

      {user && (
        <section
          className="iss-my-passes"
          aria-label={t("iss.myPassesAria")}
          data-testid="iss-my-passes-section"
        >
          <h2>{t("iss.tonightOverCity", { city: user.location_name ?? "" })}</h2>

          {!hasLocation ? (
            <p data-testid="iss-set-location-prompt">
              {t("iss.setLocationPrompt")} <Link to="/account">{t("iss.goToAccount")}</Link>
            </p>
          ) : myPassesLoading ? (
            <p role="status">{t("common.loading")}</p>
          ) : myPassesIsError ? (
            myPassesErr?.code === "LOCATION_REQUIRED" ? (
              <p data-testid="iss-set-location-prompt">
                {t("iss.setLocationPrompt")} <Link to="/account">{t("iss.goToAccount")}</Link>
              </p>
            ) : (
              <ErrorBanner
                titleKey="iss.myPassesUnavailable"
                detail={myPassesErr?.message}
                variant="section"
              />
            )
          ) : !myPassesData?.passes.length ? (
            <p data-testid="iss-no-upcoming-passes">{t("iss.noUpcomingPasses")}</p>
          ) : (
            <>
              <ul data-testid="iss-upcoming-passes-list">
                {myPassesData.passes.map((p, i) => (
                  <li key={p.startUTC} data-testid={`iss-pass-${i}`}>
                    {formatDateTime(new Date(p.startUTC * 1000).toISOString())} ·{" "}
                    {t("iss.duration")}: {p.duration} s · {t("iss.maxElevation")}: {p.maxEl}°
                  </li>
                ))}
              </ul>

              {issPassSubscription ? (
                <button
                  type="button"
                  onClick={() => deleteSubscription.mutate(issPassSubscription.id)}
                  disabled={deleteSubscription.isPending}
                  data-testid="iss-alert-unsubscribe"
                >
                  {t("iss.alertMeDisable")}
                </button>
              ) : user.is_pro ? (
                <button
                  type="button"
                  onClick={handleSubscribeIssPass}
                  disabled={createSubscription.isPending}
                  data-testid="iss-alert-subscribe"
                >
                  {t("iss.alertMe")}
                </button>
              ) : (
                <p data-testid="iss-alert-pro-required">{t("iss.alertMeProRequired")}</p>
              )}

              {issAlertError && (
                <span role="alert" data-testid="iss-alert-error">
                  {issAlertError}
                </span>
              )}
            </>
          )}
        </section>
      )}

      {quotaData && (
        <p className="iss-quota-info" aria-label="quota-info">
          {t("iss.quotaUsed", { used: quotaData.used, cap: quotaData.cap })}
        </p>
      )}
    </div>
  );
}
