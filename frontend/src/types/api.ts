export interface ApodData {
  date: string;
  title: string;
  explanation: string;
  url: string;
  hdurl?: string | null;
  media_type: string;
  copyright?: string | null;
  thumbnail_url?: string | null;
}

export interface ApodResponse {
  data: ApodData;
  cached: boolean;
  stale: boolean;
  fetched_at: string;
  is_today: boolean;
}

export interface NeoData {
  id: string;
  name: string;
  close_approach_date: string;
  absolute_magnitude_h?: number | null;
  estimated_diameter_min_km?: number | null;
  estimated_diameter_max_km?: number | null;
  is_potentially_hazardous: boolean;
  relative_velocity_kph?: number | null;
  miss_distance_km?: number | null;
  orbiting_body?: string | null;
  nasa_jpl_url?: string | null;
}

export interface NeoFeedResponse {
  data: NeoData[];
  cached: boolean;
  stale: boolean;
  fetched_at: string;
  is_today: boolean;
}

export type SpaceWeatherEventType = "FLR" | "GST" | "RBE" | "SEP" | "CME";

export interface SpaceWeatherEventData {
  id: string;
  event_type: SpaceWeatherEventType;
  start_date: string;
  raw_json: string;
}

export interface SpaceWeatherResponse {
  data: SpaceWeatherEventData[];
  cached: boolean;
  stale: boolean;
  fetched_at: string;
  is_today: boolean;
}

export interface MarsPhotoData {
  id: number;
  sol: number;
  earth_date: string;
  rover_name: string;
  camera_name: string;
  img_src: string;
}

export interface MarsPhotosResponse {
  data: MarsPhotoData[];
  cached: boolean;
  stale: boolean;
  fetched_at: string;
  is_today: boolean;
}

export interface RoverInfo {
  name: string;
  cameras: string[];
}

export interface RoversResponse {
  data: RoverInfo[];
}

export interface IssPosition {
  satlatitude: number;
  satlongitude: number;
  sataltitude: number;
  azimuth: number;
  elevation: number;
  ra?: number;
  dec?: number;
  timestamp: number;
  timestamp_ms: number;
  eclipsed: boolean;
}

export interface IssPositionsResponse {
  positions: IssPosition[];
  fetched_at: string;
  cached: boolean;
  quota_exhausted: boolean;
}

export interface IssTleResponse {
  tle_line0: string;
  tle_line1: string;
  tle_line2: string;
  fetched_at: string;
  cached: boolean;
  quota_exhausted: boolean;
}

export interface IssPass {
  startUTC: number;
  maxUTC: number;
  endUTC: number;
  startAzCompass?: string;
  endAzCompass?: string;
  maxEl: number;
  mag?: number;
  duration: number;
}

export interface IssPassesResponse {
  passes: IssPass[];
  fetched_at: string;
  cached: boolean;
  quota_exhausted: boolean;
}

export interface IssQuotaResponse {
  used: number;
  cap: number;
  window_start: string;
  resets_at: string;
}

export interface LivestreamUrl {
  title: string;
  url: string;
  feature_image: string;
}

export interface LaunchData {
  ll2_id: string;
  name: string;
  net: string; // ISO8601
  status_abbrev: string;
  status_name: string;
  agency_name: string;
  agency_type: string | null;
  rocket_name: string;
  rocket_family: string | null;
  mission_name: string | null;
  mission_description: string | null;
  mission_type: string | null;
  pad_name: string;
  pad_location: string;
  image_url: string | null;
  livestream_urls: LivestreamUrl[];
  fetched_at: string;
}

export interface LaunchesResponse {
  data: LaunchData[];
  last_synced_at: string | null;
  cached: boolean;
}

export interface LaunchHistoryEntry {
  change_type: string;
  old_value: string | null;
  new_value: string | null;
  detected_at: string;
}

export interface LaunchHistoryResponse {
  data: LaunchHistoryEntry[];
}

export interface EphemerisPointDto {
  t: string;
  x: number;
  y: number;
  z: number;
}

export interface EphemeridesResponse {
  slug: string;
  name_key: string;
  points: EphemerisPointDto[];
}

export interface SubscriptionData {
  id: string;
  type: "launch" | "agency" | "iss_pass";
  ll2_id: string | null;
  agency_name: string | null;
  notify_email: boolean;
  notify_sms: boolean;
  notify_push: boolean;
  created_at: string;
}

export type SubscriptionsResponse = SubscriptionData[];

export interface CreateSubscriptionRequest {
  type: "launch" | "agency" | "iss_pass";
  ll2_id?: string;
  agency_name?: string;
  notify_email: boolean;
  notify_sms: boolean;
  notify_push: boolean;
}

export interface VapidPublicKeyResponse {
  public_key: string;
}

export interface PushSubscribeRequest {
  endpoint: string;
  keys: {
    p256dh: string;
    auth: string;
  };
}

export interface TokenResponse {
  access_token: string;
}

export interface UserResponse {
  id: number;
  first_name: string;
  last_name: string;
  email: string | null;
  phone: string | null;
  email_verified: boolean;
  phone_verified: boolean;
  created_at: string;
  consent_notifications_at: string | null;
  is_pro: boolean;
  location_name: string | null;
  location_lat: number | null;
  location_lng: number | null;
  location_tz: string | null;
  ical_token: string | null;
}

export interface IcalRotateResponse {
  ical_token: string;
}

export interface SettingsStatus {
  nasa_key_set: boolean;
  n2yo_key_set: boolean;
}

export interface LocationCandidate {
  name: string;
  country?: string | null;
  admin1?: string | null;
  latitude: number;
  longitude: number;
  timezone: string;
}

export interface LocationSearchResponse {
  candidates: LocationCandidate[];
}

export interface SetLocationRequest {
  name: string;
  latitude: number;
  longitude: number;
  timezone: string;
}

export interface LocationOut {
  location_name: string | null;
  location_lat: number | null;
  location_lng: number | null;
  location_tz: string | null;
}
