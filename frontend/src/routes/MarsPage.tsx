import { useState } from "react";
import { useMarsPhotos, useRovers } from "@/hooks/useMars";
import { ErrorBanner } from "@/components/ErrorBanner";
import { formatDate, formatDateTime } from "@/lib/dateTime";
import type { MarsPhotoData } from "@/types/api";

const ROVERS = ["curiosity", "opportunity", "spirit", "perseverance"];

function errorTitle(code: string): string {
  switch (code) {
    case "NO_INTERNET":
      return "No internet connection";
    case "NASA_UNAVAILABLE":
      return "NASA services are currently unavailable";
    case "NASA_AUTH_ERROR":
      return "Invalid NASA API Key";
    case "INVALID_PARAMS":
      return "Invalid parameters";
    default:
      return "Something went wrong";
  }
}

interface LightboxProps {
  photo: MarsPhotoData;
  onClose: () => void;
}

function Lightbox({ photo, onClose }: LightboxProps) {
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
          aria-label="Close fullscreen"
          onClick={onClose}
        >
          Close
        </button>
        <img
          src={photo.img_src}
          alt={`Mars photo ${photo.id} taken by ${photo.rover_name} ${photo.camera_name} on ${formatDate(photo.earth_date)}`}
          className="mars-lightbox-img"
        />
        <dl className="mars-lightbox-meta">
          <dt>Rover</dt><dd>{photo.rover_name}</dd>
          <dt>Camera</dt><dd>{photo.camera_name}</dd>
          <dt>Sol</dt><dd>{photo.sol}</dd>
          <dt>Earth date</dt><dd>{formatDate(photo.earth_date)}</dd>
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
      <h1>Mars Explorer</h1>

      <div className="mars-controls">
        <label htmlFor="mars-rover">
          Rover
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
          <legend>Browse by</legend>
          <label>
            <input
              type="radio"
              name="mars-mode"
              value="sol"
              checked={solMode}
              onChange={() => { setSolMode(true); setPage(1); }}
            />
            Sol
          </label>
          <label>
            <input
              type="radio"
              name="mars-mode"
              value="date"
              checked={!solMode}
              onChange={() => { setSolMode(false); setPage(1); }}
            />
            Earth date
          </label>
        </fieldset>

        {solMode ? (
          <label htmlFor="mars-sol">
            Sol
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
            Earth date
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
            Camera
            <select
              id="mars-camera"
              value={camera}
              onChange={(e) => handleCameraChange(e.target.value)}
            >
              <option value="">All cameras</option>
              {cameras.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        )}
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
      ) : !data || data.data.length === 0 ? (
        <p className="mars-empty">No photos found.</p>
      ) : (
        <>
          <p className="mars-badge" aria-label={data.cached ? "cached" : "live"}>
            {data.stale
              ? `Showing cached data from ${formatDateTime(data.fetched_at)}`
              : data.cached
                ? `Served from cache · fetched ${formatDateTime(data.fetched_at)}`
                : `Live · fetched ${formatDateTime(data.fetched_at)}`}
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
                  {photo.camera_name} · sol {photo.sol} · {formatDate(photo.earth_date)}
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
              Previous
            </button>
            <span>Page {page}</span>
            <button
              type="button"
              onClick={() => setPage((p) => p + 1)}
              disabled={data.data.length < 25}
              aria-label="Next page"
            >
              Next
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
