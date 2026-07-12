#!/usr/bin/env python3
"""Dev-only generator for `frontend/public/missions/<slug>.json`.

Not part of the deployed backend and not imported by `app/` — run manually,
by hand, when adding or refreshing a mission. See
`Architecture/22-ephemeris-and-mission-replay.md` (sequencing note, Step S1)
and `Architecture/27-mission-simulations-3d.md`.

Two independent data paths:

  --horizons   Pulls a real spacecraft trajectory from JPL Horizons for
               missions Horizons actually carries an ephemeris for (e.g.
               Mars Pathfinder, SPK -530). Courtesy rules apply even though
               this only ever runs offline, by hand: one batch call, never
               looped, never proxying a user request.

  --from-yaml  Interpolates curated keyframes (a centripetal-ish Catmull-Rom
               spline in time) for missions Horizons has no ephemeris for at
               all (e.g. Apollo 11 — crewed missions were never tracked by
               the Horizons system). Keyframes are pre-computed by hand from
               cited historical sources; this script only smooths them into
               a dense, scrubber-friendly trajectory.

Both paths, for `frame: geocentric` missions, can compute
`bodyCalibration.moon.phaseDeg` from the Moon's *real* Horizons ephemeris at
a single anchor epoch, so the trajectory terminates exactly where the Moon
actually was — see the "Moon calibration" section of `22-...`. The constants
below (`EARTH_MOON_A_THOUSAND_KM`, `EARTH_MOON_PERIOD_DAYS`) intentionally
mirror the Moon entry in `frontend/src/solar/data.ts` — the scene's
simplified circular/planar model is what is being calibrated, not the real
orbit, so the two must stay in lock-step.

Output: static JSON written to `frontend/public/missions/<slug>.json`,
matching the schema documented in `Architecture/22-...` (G3 section) and
validated by `frontend/scripts/validate-missions.mjs`.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml

HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # courtesy cap, same as the runtime clients
MAX_TRAJECTORY_POINTS = 5000  # Architecture/22-... performance budget

J2000 = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
# Must match the Moon entry in frontend/src/solar/data.ts.
EARTH_MOON_A_THOUSAND_KM = 384.4
EARTH_MOON_PERIOD_DAYS = 27.322

REPO_ROOT = Path(__file__).resolve().parents[2]
MISSIONS_DIR = REPO_ROOT / "frontend" / "public" / "missions"


def _parse_iso(t: str) -> datetime:
    dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _days_since_j2000(dt: datetime) -> float:
    return (dt - J2000).total_seconds() / 86400.0


# ---- Horizons -----------------------------------------------------------


def query_horizons_vectors(
    spk_id: str, center: str, start: datetime, stop: datetime, step: str
) -> list[tuple[datetime, float, float, float]]:
    """Batch VECTORS query over a time range. One call — never looped."""
    params = {
        "format": "json",
        "COMMAND": spk_id,
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "VECTORS",
        "CENTER": center,
        "START_TIME": start.strftime("%Y-%m-%d"),
        "STOP_TIME": stop.strftime("%Y-%m-%d"),
        "STEP_SIZE": step,
        "VEC_TABLE": "1",
        "OUT_UNITS": "KM-S",
        "CSV_FORMAT": "YES",
        "REF_PLANE": "ECLIPTIC",
        "REF_SYSTEM": "J2000",
    }
    resp = httpx.get(HORIZONS_URL, params=params, timeout=30.0)
    resp.raise_for_status()
    if len(resp.content) > MAX_RESPONSE_BYTES:
        raise RuntimeError("Horizons response exceeded size cap")
    return _parse_vectors_csv(resp.json())


def query_horizons_vector_at(
    spk_id: str, center: str, epoch: datetime
) -> tuple[float, float, float]:
    """Single-epoch VECTORS query (used for Moon calibration)."""
    params = {
        "format": "json",
        "COMMAND": spk_id,
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "VECTORS",
        "CENTER": center,
        "TLIST": f"'{epoch.strftime('%Y-%m-%d %H:%M:%S')}'",
        "VEC_TABLE": "1",
        "OUT_UNITS": "KM-S",
        "CSV_FORMAT": "YES",
        "REF_PLANE": "ECLIPTIC",
        "REF_SYSTEM": "J2000",
    }
    resp = httpx.get(HORIZONS_URL, params=params, timeout=30.0)
    resp.raise_for_status()
    points = _parse_vectors_csv(resp.json())
    if not points:
        raise RuntimeError(f"Horizons returned no vector for {spk_id} at {epoch}")
    _, x, y, z = points[0]
    return x, y, z


def _parse_vectors_csv(payload: dict[str, Any]) -> list[tuple[datetime, float, float, float]]:
    result = payload.get("result", "")
    if "error" in payload and "$$SOE" not in result:
        raise RuntimeError(f"Horizons error: {payload['error']}")
    start = result.index("$$SOE") + len("$$SOE")
    end = result.index("$$EOE")
    block = result[start:end].strip("\n")

    points: list[tuple[datetime, float, float, float]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        fields = [f.strip() for f in line.split(",")]
        # fields: JDTDB, Calendar Date (TDB), X, Y, Z, (trailing comma -> "")
        cal = fields[1].replace("A.D. ", "")
        dt = datetime.strptime(cal, "%Y-%b-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
        x, y, z = float(fields[2]), float(fields[3]), float(fields[4])
        points.append((dt, x, y, z))
    return points


def moon_phase_calibration(epoch: datetime) -> float:
    """phaseDeg so the scene's simplified circular Moon matches the real
    Horizons direction (projected to the ecliptic plane) at `epoch`."""
    x, y, _z = query_horizons_vector_at("301", "500@399", epoch)
    angle_real = math.degrees(math.atan2(y, x)) % 360
    days = _days_since_j2000(epoch)
    phase = (angle_real - (360.0 / EARTH_MOON_PERIOD_DAYS) * days) % 360
    return round(phase, 2)


# ---- Catmull-Rom keyframe interpolation ----------------------------------


def _catmull_rom(p0: float, p1: float, p2: float, p3: float, u: float) -> float:
    return 0.5 * (
        2 * p1
        + (-p0 + p2) * u
        + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u
        + (-p0 + 3 * p1 - 3 * p2 + p3) * u * u * u
    )


def interpolate_keyframes(
    keyframes: list[tuple[datetime, float, float, float]], sample_step_seconds: float
) -> list[tuple[datetime, float, float, float]]:
    """Dense, smooth resample of ordered (t, x, y, z) keyframes.

    Clamped-boundary Catmull-Rom per axis, parametrized locally by the
    fraction of elapsed time within each keyframe segment. Segments vary
    widely in duration here (hours near the Moon, ~9 h on the transfer
    legs) — treating each segment's local `u` as uniform is an
    approximation, same spirit as the simulator's own Kepler-with-fixed-
    mean-motion simplification elsewhere in this app.
    """
    if len(keyframes) < 2:
        return keyframes

    t0, t1 = keyframes[0][0], keyframes[-1][0]
    total_seconds = (t1 - t0).total_seconds()
    n = min(MAX_TRAJECTORY_POINTS - 1, max(1, int(total_seconds / sample_step_seconds)))

    out: list[tuple[datetime, float, float, float]] = []
    seg = 0
    for k in range(n + 1):
        t = t0.timestamp() + (t1.timestamp() - t0.timestamp()) * (k / n)
        while seg < len(keyframes) - 2 and keyframes[seg + 1][0].timestamp() < t:
            seg += 1
        left, right = keyframes[seg], keyframes[seg + 1]
        span = right[0].timestamp() - left[0].timestamp()
        u = 0.0 if span <= 0 else (t - left[0].timestamp()) / span

        p0 = keyframes[seg - 1] if seg > 0 else left
        p3 = keyframes[seg + 2] if seg + 2 < len(keyframes) else right

        x = _catmull_rom(p0[1], left[1], right[1], p3[1], u)
        y = _catmull_rom(p0[2], left[2], right[2], p3[2], u)
        z = _catmull_rom(p0[3], left[3], right[3], p3[3], u)
        out.append((datetime.fromtimestamp(t, tz=timezone.utc), x, y, z))
    return out


# ---- assembly -------------------------------------------------------------


def build_output(
    slug: str,
    name_key: str,
    frame: str,
    bodies: list[str],
    trajectory: list[tuple[datetime, float, float, float]],
    milestones: list[dict[str, Any]],
    moon_phase_deg: float | None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "slug": slug,
        "name_key": name_key,
        "frame": frame,
        "t0": _iso(trajectory[0][0]),
        "t1": _iso(trajectory[-1][0]),
        "trajectory": [
            {"t": _iso(t), "x": round(x, 3), "y": round(y, 3), "z": round(z, 3)}
            for t, x, y, z in trajectory
        ],
        "milestones": milestones,
        "bodies": bodies,
    }
    if moon_phase_deg is not None:
        out["bodyCalibration"] = {"moon": {"phaseDeg": moon_phase_deg}}
    return out


def write_output(out: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(out, indent=2, ensure_ascii=False) + "\n"
    size = len(text.encode("utf-8"))
    if size > 500 * 1024:
        raise RuntimeError(
            f"{out_path.name} is {size / 1024:.0f} KB, over the 500 KB budget "
            "(Architecture/22-...) — reduce --sample-step-seconds"
        )
    out_path.write_text(text, encoding="utf-8")
    print(f"wrote {out_path} ({size / 1024:.1f} KB, {len(out['trajectory'])} points)")


# ---- CLI ------------------------------------------------------------------


def cmd_from_yaml(args: argparse.Namespace) -> None:
    data = yaml.safe_load(Path(args.from_yaml).read_text())
    keyframes = [
        (_parse_iso(k["t"]), float(k["x"]), float(k["y"]), float(k["z"]))
        for k in data["keyframes"]
    ]
    keyframes.sort(key=lambda k: k[0])
    trajectory = interpolate_keyframes(keyframes, args.sample_step_seconds)

    moon_phase_deg = None
    if data.get("calibration_epoch"):
        moon_phase_deg = moon_phase_calibration(_parse_iso(data["calibration_epoch"]))

    out = build_output(
        slug=data["slug"],
        name_key=data["name_key"],
        frame=data["frame"],
        bodies=data["bodies"],
        trajectory=trajectory,
        milestones=data["milestones"],
        moon_phase_deg=moon_phase_deg,
    )
    out_path = Path(args.out) if args.out else MISSIONS_DIR / f"{data['slug']}.json"
    write_output(out, out_path)


def cmd_horizons(args: argparse.Namespace) -> None:
    center = "500@10" if args.frame == "heliocentric" else "500@399"
    start = _parse_iso(args.start)
    stop = _parse_iso(args.stop)
    trajectory = query_horizons_vectors(args.spk, center, start, stop, args.step)
    milestones = (
        yaml.safe_load(Path(args.milestones).read_text()) if args.milestones else []
    )
    out = build_output(
        slug=args.slug,
        name_key=args.name_key,
        frame=args.frame,
        bodies=args.bodies.split(","),
        trajectory=trajectory,
        milestones=milestones,
        moon_phase_deg=None,
    )
    out_path = Path(args.out) if args.out else MISSIONS_DIR / f"{args.slug}.json"
    write_output(out, out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    p_yaml = sub.add_parser("from-yaml", help="interpolate curated keyframes")
    p_yaml.add_argument("from_yaml_path", metavar="FILE")
    p_yaml.add_argument("--out")
    p_yaml.add_argument("--sample-step-seconds", type=float, default=900.0)
    p_yaml.set_defaults(
        func=lambda a: cmd_from_yaml(
            argparse.Namespace(
                from_yaml=a.from_yaml_path,
                out=a.out,
                sample_step_seconds=a.sample_step_seconds,
            )
        )
    )

    p_hz = sub.add_parser("horizons", help="pull a real trajectory from JPL Horizons")
    p_hz.add_argument("--spk", required=True)
    p_hz.add_argument("--frame", choices=["heliocentric", "geocentric"], required=True)
    p_hz.add_argument("--bodies", required=True, help="comma-separated, e.g. earth,mars")
    p_hz.add_argument("--start", required=True)
    p_hz.add_argument("--stop", required=True)
    p_hz.add_argument("--step", default="1d")
    p_hz.add_argument("--slug", required=True)
    p_hz.add_argument("--name-key", required=True)
    p_hz.add_argument("--milestones", help="path to a YAML file: [{t, key}, ...]")
    p_hz.add_argument("--out")
    p_hz.set_defaults(func=cmd_horizons)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
