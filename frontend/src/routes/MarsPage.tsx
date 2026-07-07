import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMarsPhotos, useRovers } from "@/hooks/useMars";
import { ErrorBanner } from "@/components/ErrorBanner";
import { RoverViewer } from "@/components/RoverViewer";
import { formatDate, formatDateTime } from "@/lib/dateTime";
import type { MarsPhotoData } from "@/types/api";

const ROVERS = ["curiosity", "opportunity", "spirit", "perseverance"];

function errorTitleKey(code: string): string {
  switch (code) {
    case "NO_INTERNET": return "error.noInternet";
    case "NASA_UNAVAILABLE": return "error.nasaUnavailable";
    case "NASA_AUTH_ERROR": return "error.nasaAuthError";
    case "MARS_ARCHIVE_UNAVAILABLE": return "error.marsArchiveUnavailable";
    case "MARS_NO_LIVE_SOURCE": return "error.marsNoLiveSource";
    case "INVALID_PARAMS": return "error.invalidParams";
    default: return "common.error";
  }
}

function errorDetailKey(code: string): string | undefined {
  switch (code) {
    case "NASA_UNAVAILABLE": return "error.nasaUnavailableDetail";
    case "MARS_ARCHIVE_UNAVAILABLE": return "error.marsArchiveUnavailableDetail";
    case "MARS_NO_LIVE_SOURCE": return "error.marsNoLiveSourceDetail";
    default: return undefined;
  }
}

interface LightboxProps {
  photo: MarsPhotoData;
  onClose: () => void;
}

function Lightbox({ photo, onClose }: LightboxProps) {
  const { t } = useTranslation();
  return (
    <div
      className="mars-lightbox-overlay"
      role="dialog"
      aria-label={`Photo ${photo.id} fullscreen`}
      onClick={onClose}
    >
      <div className="mars-lightbox-inner" onClick={(e) => e.stopPropagation()}>
        <button
          type="button"
          className="mars-lightbox-close"
          aria-label={t("mars.closeLightbox")}
          onClick={onClose}
        >
          {t("mars.closeLightbox")}
        </button>
        <img
          src={photo.img_src}
          alt={`Mars photo ${photo.id} taken by ${photo.rover_name} ${photo.camera_name} on ${formatDate(photo.earth_date)}`}
          className="mars-lightbox-img"
        />
        <dl className="mars-lightbox-meta">
          <dt>Rover</dt><dd>{photo.rover_name}</dd>
          <dt>Camera</dt><dd>{photo.camera_name}</dd>
          <dt>{t("mars.sol")}</dt><dd>{photo.sol}</dd>
          <dt>{t("mars.earthDate")}</dt><dd>{formatDate(photo.earth_date)}</dd>
        </dl>
      </div>
    </div>
  );
}

export default function MarsPage() {
  const [rover, setRover] = useState<string>("curiosity");
  const [solMode, setSolMode] = useState<boolean>(true);
  const [sol, setSol] = useState<string>("1000");
  const [earthDate, setEarthDate] = useState<string>("");
  const [camera, setCamera] = useState<string>("");
  const [page, setPage] = useState<number>(1);
  const [lightboxPhoto, setLightboxPhoto] = useState<MarsPhotoData | null>(null);
  const [show3d, setShow3d] = useState<boolean>(false);
  const { t } = useTranslation();

  const { data: roversData } = useRovers();

  const cameras: string[] =
    roversData?.data.find((r) => r.name === rover)?.cameras ?? [];

  const solNum = solMode && sol ? parseInt(sol, 10) : null;
  const dateParam = !solMode && earthDate ? earthDate : null;

  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useMarsPhotos({
    rover,
    sol: solNum,
    earthDate: dateParam,
    camera: camera || null,
    page,
  });

  function handleRoverChange(newRover: string) {
    setRover(newRover);
    setCamera("");
    setPage(1);
  }

  function handleCameraChange(newCamera: string) {
    setCamera(newCamera);
    setPage(1);
  }

  return (
    <div className="mars-page">
      <h1>{t("mars.title")}</h1>

      <div className="mars-controls">
        <label htmlFor="mars-rover">
          {t("mars.selectRover")}
          <select
            id="mars-rover"
            value={rover}
            onChange={(e) => handleRoverChange(e.target.value)}
          >
            {ROVERS.map((r) => (
              <option key={r} value={r}>
                {r.charAt(0).toUpperCase() + r.slice(1)}
              </option>
            ))}
          </select>
        </label>

        <fieldset className="mars-mode-toggle">
          <legend>{t("mars.browseBy")}</legend>
          <label>
            <input
              type="radio"
              name="mars-mode"
              value="sol"
              checked={solMode}
              onChange={() => { setSolMode(true); setPage(1); }}
            />
            {t("mars.sol")}
          </label>
          <label>
            <input
              type="radio"
              name="mars-mode"
              value="date"
              checked={!solMode}
              onChange={() => { setSolMode(false); setPage(1); }}
            />
            {t("mars.earthDate")}
          </label>
        </fieldset>

        {solMode ? (
          <label htmlFor="mars-sol">
            {t("mars.sol")}
            <input
              id="mars-sol"
              type="number"
              min={0}
              value={sol}
              onChange={(e) => { setSol(e.target.value); setPage(1); }}
            />
          </label>
        ) : (
          <label htmlFor="mars-date">
            {t("mars.earthDate")}
            <input
              id="mars-date"
              type="date"
              value={earthDate}
              onChange={(e) => { setEarthDate(e.target.value); setPage(1); }}
            />
          </label>
        )}

        {cameras.length > 0 && (
          <label htmlFor="mars-camera">
            {t("mars.selectCamera")}
            <select
              id="mars-camera"
              value={camera}
              onChange={(e) => handleCameraChange(e.target.value)}
            >
              <option value="">{t("mars.allCameras")}</option>
              {cameras.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <details
        className="mars-rover-3d"
        onToggle={(e) => setShow3d((e.target as HTMLDetailsElement).open)}
      >
        <summary>{t("mars.rover3dTitle")}</summary>
        {show3d && <RoverViewer rover={rover} />}
      </details>

      {isLoading ? (
        <p role="status">{t("common.loading")}</p>
      ) : isError && error ? (
        <ErrorBanner
          titleKey={errorTitleKey(error.code)}
          detailKey={errorDetailKey(error.code)}
          detail={error.message}
          onRetry={() => refetch()}
          variant="section"
        />
      ) : !data || data.data.length === 0 ? (
        <p className="mars-empty">{t("mars.noPhotos")}</p>
      ) : (
        <>
          <p className="mars-badge" aria-label={data.cached ? "cached" : "live"}>
            {data.stale
              ? t("error.staleData", { date: formatDateTime(data.fetched_at) })
              : data.cached
                ? `${t("common.cached")} · ${t("common.fetchedAt")} ${formatDateTime(data.fetched_at)}`
                : `${t("common.live")} · ${t("common.fetchedAt")} ${formatDateTime(data.fetched_at)}`}
          </p>

          <div className="mars-grid" role="list">
            {data.data.map((photo) => (
              <div key={photo.id} role="listitem" className="mars-photo-card">
                <button
                  type="button"
                  className="mars-photo-btn"
                  onClick={() => setLightboxPhoto(photo)}
                  aria-label={`Open photo ${photo.id}`}
                >
                  <img
                    src={photo.img_src}
                    alt={`Mars photo ${photo.id} by ${photo.rover_name} ${photo.camera_name} on sol ${photo.sol}`}
                    className="mars-photo-thumb"
                    loading="lazy"
                  />
                </button>
                <p className="mars-photo-meta">
                  {photo.camera_name} · {t("mars.sol")} {photo.sol} · {formatDate(photo.earth_date)}
                </p>
              </div>
            ))}
          </div>

          <div className="mars-pagination">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              aria-label="Previous page"
            >
              {t("mars.prevPage")}
            </button>
            <span>{t("mars.page", { n: page })}</span>
            <button
              type="button"
              onClick={() => setPage((p) => p + 1)}
              disabled={data.data.length < 25}
              aria-label="Next page"
            >
              {t("mars.nextPage")}
            </button>
          </div>
        </>
      )}

      {lightboxPhoto && (
        <Lightbox photo={lightboxPhoto} onClose={() => setLightboxPhoto(null)} />
      )}
    </div>
  );
}
