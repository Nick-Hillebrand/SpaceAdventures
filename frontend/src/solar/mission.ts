// Mission replay data model + static-file loaders.
//
// Mission JSON lives in frontend/public/missions/ (Architecture/22-
// ephemeris-and-mission-replay.md, G3 schema) and is generated offline by
// backend/scripts/build_mission.py — never fetched from a live upstream at
// request time.

export interface MissionTrajectoryPoint {
  /** ISO 8601 timestamp. */
  t: string;
  /** Ecliptic J2000 km, relative to the mission's frame origin. */
  x: number;
  y: number;
  z: number;
}

export interface MissionMilestone {
  /** ISO 8601 timestamp, within [t0, t1]. */
  t: string;
  /** i18n key for the milestone's localized label/description. */
  key: string;
  lat?: number | null;
  lng?: number | null;
}

export interface MissionBodyCalibration {
  moon?: { phaseDeg: number };
}

export type MissionFrame = "geocentric" | "heliocentric";

export interface MissionSpec {
  slug: string;
  name_key: string;
  frame: MissionFrame;
  t0: string;
  t1: string;
  trajectory: MissionTrajectoryPoint[];
  milestones: MissionMilestone[];
  bodies: string[];
  bodyCalibration?: MissionBodyCalibration;
}

export interface MissionIndexEntry {
  slug: string;
  name_key: string;
}

export interface MissionIndex {
  missions: MissionIndexEntry[];
}

/** Fetches the static mission catalogue at /missions/index.json. */
export async function fetchMissionIndex(): Promise<MissionIndex> {
  const res = await fetch("/missions/index.json");
  if (!res.ok) throw new Error(`Failed to load mission index (${res.status})`);
  return (await res.json()) as MissionIndex;
}

/** Fetches a single mission spec at /missions/<slug>.json. */
export async function fetchMissionSpec(slug: string): Promise<MissionSpec> {
  const res = await fetch(`/missions/${encodeURIComponent(slug)}.json`);
  if (!res.ok) throw new Error(`Failed to load mission "${slug}" (${res.status})`);
  return (await res.json()) as MissionSpec;
}
