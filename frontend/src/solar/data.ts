// Physical and orbital data for the solar system simulator.
//
// Sources: NASA planetary fact sheets (nssdc.gsfc.nasa.gov/planetary/factsheet)
// and JPL approximate Keplerian elements for J2000 (ssd.jpl.nasa.gov).
// Angles in degrees, distances in AU (orbits) or km (radii), periods in days.

export interface OrbitalElements {
  /** Semi-major axis in AU (planets) or in 10^3 km (moons, around parent). */
  a: number;
  /** Eccentricity. */
  e: number;
  /** Inclination to the ecliptic (planets) / parent equator (moons), degrees. */
  i: number;
  /** Longitude of the ascending node at J2000, degrees. */
  om: number;
  /** Longitude of perihelion at J2000, degrees. */
  w: number;
  /** Mean longitude at J2000, degrees. */
  L: number;
  /** Sidereal orbital period in days. Negative = retrograde orbit. */
  periodDays: number;
}

export interface MoonData {
  id: string;
  /** Mean radius, km. */
  radiusKm: number;
  /** Semi-major axis around the parent, 10^3 km. */
  aThousandKm: number;
  /** Orbital period, days. Negative = retrograde. */
  periodDays: number;
  color: string;
  texture?: string;
}

export interface PlanetFacts {
  /** Mass, 10^24 kg. */
  mass: number;
  /** Equatorial surface gravity, m/s^2. */
  gravity: number;
  /** Mean surface (or 1-bar level) temperature, °C. */
  meanTempC: number;
  /** Known natural satellites. */
  moonCount: number;
  /** Sidereal rotation period, hours. Negative = retrograde spin. */
  rotationHours: number;
  /** Axial tilt (obliquity to orbit), degrees. */
  axialTiltDeg: number;
}

export interface PlanetData {
  id: string;
  type: "rocky" | "gas" | "ice";
  radiusKm: number;
  orbit: OrbitalElements;
  facts: PlanetFacts;
  texture: string;
  /** Fallback / tint color, also used for the orbit line. */
  color: string;
  ring?: { innerKm: number; outerKm: number; texture?: string };
  moons: MoonData[];
}

export const SUN = {
  id: "sun",
  radiusKm: 695_700,
  rotationHours: 609.12,
  texture: "/solar/2k_sun.jpg",
  facts: {
    mass: 1_989_000,
    gravity: 274,
    meanTempC: 5505,
    moonCount: 0,
    rotationHours: 609.12,
    axialTiltDeg: 7.25,
  } satisfies PlanetFacts,
};

export const PLANETS: PlanetData[] = [
  {
    id: "mercury",
    type: "rocky",
    radiusKm: 2439.7,
    orbit: { a: 0.38710, e: 0.20563, i: 7.005, om: 48.331, w: 77.456, L: 252.251, periodDays: 87.969 },
    facts: { mass: 0.330, gravity: 3.7, meanTempC: 167, moonCount: 0, rotationHours: 1407.6, axialTiltDeg: 0.034 },
    texture: "/solar/2k_mercury.jpg",
    color: "#9c8e84",
    moons: [],
  },
  {
    id: "venus",
    type: "rocky",
    radiusKm: 6051.8,
    orbit: { a: 0.72333, e: 0.00677, i: 3.395, om: 76.680, w: 131.533, L: 181.980, periodDays: 224.701 },
    facts: { mass: 4.87, gravity: 8.9, meanTempC: 464, moonCount: 0, rotationHours: -5832.5, axialTiltDeg: 177.4 },
    texture: "/solar/2k_venus_atmosphere.jpg",
    color: "#d9b98a",
    moons: [],
  },
  {
    id: "earth",
    type: "rocky",
    radiusKm: 6371.0,
    orbit: { a: 1.00000, e: 0.01671, i: 0.0, om: -11.261, w: 102.947, L: 100.464, periodDays: 365.256 },
    facts: { mass: 5.97, gravity: 9.8, meanTempC: 15, moonCount: 1, rotationHours: 23.934, axialTiltDeg: 23.44 },
    texture: "/solar/2k_earth_daymap.jpg",
    color: "#5b8cc9",
    moons: [
      { id: "moon", radiusKm: 1737.4, aThousandKm: 384.4, periodDays: 27.322, color: "#b8b5ad", texture: "/solar/2k_moon.jpg" },
    ],
  },
  {
    id: "mars",
    type: "rocky",
    radiusKm: 3389.5,
    orbit: { a: 1.52368, e: 0.09340, i: 1.850, om: 49.558, w: 336.041, L: 355.445, periodDays: 686.980 },
    facts: { mass: 0.642, gravity: 3.7, meanTempC: -65, moonCount: 2, rotationHours: 24.623, axialTiltDeg: 25.19 },
    texture: "/solar/2k_mars.jpg",
    color: "#c1653f",
    moons: [
      { id: "phobos", radiusKm: 11.1, aThousandKm: 9.38, periodDays: 0.319, color: "#8f8377" },
      { id: "deimos", radiusKm: 6.2, aThousandKm: 23.46, periodDays: 1.263, color: "#9a8e80" },
    ],
  },
  {
    id: "jupiter",
    type: "gas",
    radiusKm: 69_911,
    orbit: { a: 5.20260, e: 0.04849, i: 1.303, om: 100.464, w: 14.331, L: 34.396, periodDays: 4332.59 },
    facts: { mass: 1898, gravity: 23.1, meanTempC: -110, moonCount: 95, rotationHours: 9.925, axialTiltDeg: 3.13 },
    texture: "/solar/2k_jupiter.jpg",
    color: "#c8a97e",
    moons: [
      { id: "io", radiusKm: 1821.6, aThousandKm: 421.8, periodDays: 1.769, color: "#d8c458" },
      { id: "europa", radiusKm: 1560.8, aThousandKm: 671.1, periodDays: 3.551, color: "#c2b5a3" },
      { id: "ganymede", radiusKm: 2634.1, aThousandKm: 1070.4, periodDays: 7.155, color: "#a5967f" },
      { id: "callisto", radiusKm: 2410.3, aThousandKm: 1882.7, periodDays: 16.689, color: "#7d7268" },
    ],
  },
  {
    id: "saturn",
    type: "gas",
    radiusKm: 58_232,
    orbit: { a: 9.55491, e: 0.05551, i: 2.489, om: 113.666, w: 93.057, L: 49.954, periodDays: 10_759.22 },
    facts: { mass: 568, gravity: 9.0, meanTempC: -140, moonCount: 274, rotationHours: 10.656, axialTiltDeg: 26.73 },
    texture: "/solar/2k_saturn.jpg",
    color: "#d9c398",
    ring: { innerKm: 74_500, outerKm: 140_220, texture: "/solar/2k_saturn_ring_alpha.png" },
    moons: [
      { id: "enceladus", radiusKm: 252.1, aThousandKm: 238.04, periodDays: 1.370, color: "#e8ecec" },
      { id: "rhea", radiusKm: 763.8, aThousandKm: 527.1, periodDays: 4.518, color: "#c9c5bc" },
      { id: "titan", radiusKm: 2574.7, aThousandKm: 1221.9, periodDays: 15.945, color: "#d8a94e" },
    ],
  },
  {
    id: "uranus",
    type: "ice",
    radiusKm: 25_362,
    orbit: { a: 19.21845, e: 0.04630, i: 0.773, om: 74.006, w: 173.005, L: 313.238, periodDays: 30_688.5 },
    facts: { mass: 86.8, gravity: 8.7, meanTempC: -195, moonCount: 28, rotationHours: -17.24, axialTiltDeg: 97.77 },
    texture: "/solar/2k_uranus.jpg",
    color: "#9bd1d6",
    ring: { innerKm: 41_837, outerKm: 51_149 },
    moons: [
      { id: "miranda", radiusKm: 235.8, aThousandKm: 129.9, periodDays: 1.413, color: "#b7b3ae" },
      { id: "titania", radiusKm: 788.4, aThousandKm: 435.9, periodDays: 8.706, color: "#a89f96" },
      { id: "oberon", radiusKm: 761.4, aThousandKm: 583.5, periodDays: 13.463, color: "#9d938a" },
    ],
  },
  {
    id: "neptune",
    type: "ice",
    radiusKm: 24_622,
    orbit: { a: 30.11039, e: 0.00899, i: 1.770, om: 131.784, w: 48.124, L: 304.880, periodDays: 60_182 },
    facts: { mass: 102, gravity: 11.0, meanTempC: -200, moonCount: 16, rotationHours: 16.11, axialTiltDeg: 28.32 },
    texture: "/solar/2k_neptune.jpg",
    color: "#5077d8",
    moons: [
      { id: "triton", radiusKm: 1353.4, aThousandKm: 354.8, periodDays: -5.877, color: "#c4bfc8" },
    ],
  },
];

export const AU_KM = 149_597_870.7;

export type BodyId = "sun" | (typeof PLANETS)[number]["id"] | string;
