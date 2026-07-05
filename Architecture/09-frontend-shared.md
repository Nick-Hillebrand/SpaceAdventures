# Frontend Shared Concerns

---

## i18n (Internationalisation)

**Library:** `i18next` + `react-i18next` + `i18next-browser-languagedetector`

**Supported locales:** `en`, `de`, `fr`, `ja`, `ru`, `es`

**Critical config:** set `load: 'languageOnly'` — `navigator.language` returns `"en-US"` which must resolve to `en.json`, not fail.

Language stored in `localStorage` under `space-adventures-lang`.

**Rule: no hardcoded English strings in JSX.** Every user-visible string uses `t("some.key")`. NASA API content (titles, explanations) is displayed as-is with a note that scientific content is in English.

### Translation Key Structure (en.json)

```json
{
  "nav": { "apod": "Picture of the Day", "neo": "Near-Earth Objects", "spaceWeather": "Space Weather", "mars": "Mars Explorer", "iss": "ISS Tracker", "launches": "Rocket Launches", "settings": "Settings", "login": "Log In", "myAccount": "My Account", "logout": "Log Out" },
  "apod": { "title": "Astronomy Picture of the Day", "explanation": "Explanation", "copyright": "Copyright", "noImage": "No image available" },
  "neo": { "title": "Near-Earth Objects", "hazardous": "Potentially Hazardous", "diameter": "Diameter", "velocity": "Velocity", "missDistance": "Miss Distance" },
  "spaceWeather": { "title": "Space Weather", "flares": "Solar Flares", "storms": "Geomagnetic Storms", "cme": "Coronal Mass Ejections" },
  "mars": { "title": "Mars Explorer", "selectRover": "Select Rover", "selectCamera": "Select Camera", "sol": "Sol" },
  "iss": { "title": "ISS Tracker", "latitude": "Latitude", "longitude": "Longitude", "altitude": "Altitude", "velocity": "Velocity", "azimuth": "Azimuth", "elevation": "Elevation", "eclipsed": "In Shadow", "yes": "Yes", "no": "No", "nextVisiblePass": "Next Visible Pass", "nextRadioPass": "Next Radio Pass", "duration": "Duration", "maxElevation": "Max Elevation", "quotaUsed": "API Quota: {{used}} / {{cap}} used this hour", "quotaWarning": "N2YO API quota nearly exhausted — showing cached data", "quotaExhausted": "N2YO API quota exhausted for this hour. Live updates paused. Resets at {{time}}.", "locationDenied": "Location access denied — using default observer position (0°N 0°E)" },
  "launches": { "title": "Rocket Launches", "lastUpdated": "Last updated {{time}}", "filterAll": "All", "filterGo": "Go", "filterTbd": "TBD", "filterHold": "Hold", "searchAgency": "Search by agency…", "watchLive": "Watch Live", "moreStreams": "More streams", "noStreams": "No livestream available", "countdownPrefix": "T−", "countdownPostfix": "T+", "netLabel": "NET", "statusGo": "Go for Launch", "statusTbd": "To Be Determined", "statusHold": "Launch Hold", "noLaunches": "No upcoming launches found" },
  "auth": { "registerTitle": "Create Account", "loginTitle": "Log In", "firstName": "First Name", "lastName": "Last Name", "email": "Email Address", "phone": "Phone Number", "password": "Password", "confirmPassword": "Confirm Password", "emailOrPhone": "At least one of email or phone is required", "passwordMismatch": "Passwords do not match", "passwordTooShort": "Password must be at least 8 characters", "alreadyHaveAccount": "Already have an account?", "noAccount": "Don't have an account?", "verifyEmail": "Enter the code sent to your email", "verifyPhone": "Enter the code sent to your phone", "resendOtp": "Resend code", "verifyButton": "Verify", "logoutSuccess": "You have been logged out" },
  "account": { "title": "My Account", "profileTab": "Profile", "subscriptionsTab": "My Subscriptions", "verified": "Verified", "unverified": "Unverified", "resendOtp": "Resend verification code", "noSubscriptions": "You have no active subscriptions", "subscribeToAgency": "Subscribe to an agency", "agencyPlaceholder": "Agency name (e.g. SpaceX)", "channelEmail": "Email", "channelSms": "SMS", "unsubscribe": "Unsubscribe", "verifyChannelPrompt": "Verify your {{channel}} to enable notifications" },
  "subscriptions": { "subscribeButton": "Subscribe", "subscribedButton": "Subscribed", "modalTitle": "Get Launch Notifications", "thisLaunch": "Subscribe to this launch", "allFromAgency": "Subscribe to all {{agency}} launches", "notifyVia": "Notify me via", "loginRequired": "Create a free account or log in to receive launch notifications", "success": "Subscription saved", "removed": "Subscription removed" },
  "settings": { "title": "Settings", "language": "Language", "apiKey": "NASA API Key", "n2yoApiKey": "N2YO API Key" },
  "common": { "loading": "Loading…", "error": "Something went wrong", "retry": "Retry", "noData": "No data available", "cached": "Served from cache", "fetchedAt": "Fetched at" },
  "error": { "backendDown": "Cannot reach the server", "backendDownDetail": "The application backend is not responding. Please check your connection or try again later.", "noInternet": "No internet connection", "noInternetDetail": "The server cannot reach the internet. Please check your network connection and try again.", "nasaUnavailable": "NASA services are currently unavailable", "nasaUnavailableDetail": "Live data could not be retrieved from NASA. Showing cached data where available.", "nasaAuthError": "Invalid NASA API Key", "nasaAuthErrorDetail": "The configured NASA API key was rejected. Please update it in Settings.", "internalError": "An unexpected server error occurred", "internalErrorDetail": "Please try again. If the problem persists, check the server logs.", "staleData": "Showing cached data from {{date}}" }
}
```

All six locale files must have all these keys. Translate the values; do not change the keys.

---

## Timezone Policy

> **The backend stores and computes everything in UTC. The frontend displays every date and time in the user's local timezone as reported by the browser. No timezone is ever stored in the database or sent by the backend.**

### `src/lib/dateTime.ts` — the ONLY place that formats dates/times

```ts
const userLocale = navigator.language
const userTz = Intl.DateTimeFormat().resolvedOptions().timeZone

export function formatDateTime(isoUtc: string): string {
  return new Intl.DateTimeFormat(userLocale, {
    dateStyle: 'medium', timeStyle: 'short', timeZone: userTz
  }).format(new Date(isoUtc))
}

export function formatDate(isoUtc: string): string {
  return new Intl.DateTimeFormat(userLocale, {
    dateStyle: 'medium', timeZone: userTz
  }).format(new Date(isoUtc))
}

export function formatTime(isoUtc: string): string {
  return new Intl.DateTimeFormat(userLocale, {
    timeStyle: 'short', timeZone: userTz
  }).format(new Date(isoUtc))
}

export function formatRelative(isoUtc: string): string {
  const diffMs = new Date(isoUtc).getTime() - Date.now()
  const rtf = new Intl.RelativeTimeFormat(userLocale, { numeric: 'auto' })
  const abs = Math.abs(diffMs)
  if (abs < 60_000) return rtf.format(Math.round(diffMs / 1_000), 'second')
  if (abs < 3_600_000) return rtf.format(Math.round(diffMs / 60_000), 'minute')
  if (abs < 86_400_000) return rtf.format(Math.round(diffMs / 3_600_000), 'hour')
  return rtf.format(Math.round(diffMs / 86_400_000), 'day')
}
```

**No component may call `.toLocaleString()`, `.toLocaleDateString()`, or hardcode a timezone.** Every date/time display uses one of these four functions.

### Usage map

| Feature | Field | Function |
|---|---|---|
| APOD | `date` | `formatDate` |
| NEO close approach | `close_approach_date` | `formatDate` |
| Space weather events | `beginTime`, `peakTime`, `endTime` | `formatDateTime` |
| Mars photos | `earth_date` | `formatDate` |
| ISS passes | `startUTC`, `maxUTC`, `endUTC` | `formatDateTime` |
| ISS quota reset | `resets_at` | `formatTime` |
| Launch NET (TBD/Hold) | `net` | `formatDateTime` |
| Launch T+ label | `net` | `formatDateTime` |
| "Last updated" | `last_synced_at` | `formatRelative` |
| "Fetched at" badge | `fetched_at` | `formatDateTime` |
| Notification log | `sent_at` | `formatDateTime` |

Date pickers send `YYYY-MM-DD` strings — no timezone conversion needed.
Email notifications show times in **UTC only**, clearly labelled.

---

## State Management

- **Server state:** TanStack Query — one hook per API route
- **UI state:** `useState` / `useReducer` local to each page
- **Persisted preferences:** `localStorage` via `useLocalStorage` hook (language, API keys, rover selection, launches view)
- No Redux / Zustand needed

### TanStack Query global config

```ts
new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      retryDelay: i => Math.min(1000 * 2 ** i, 10000),
      staleTime: Infinity,
    },
  },
})
```

Per-query overrides (on the `useQuery` call, not global):
- ISS positions: `staleTime: 270_000`
- Launches: `staleTime: 300_000`

Every hook must expose `error` and `isError` — pass to `<ErrorBanner>`, never swallow silently.

---

## Error Handling

### `<ErrorBanner>` component

```tsx
interface ErrorBannerProps {
  titleKey: string
  detailKey?: string
  detailValues?: object
  onRetry?: () => void
  action?: ReactNode
  variant: "page" | "section"
}
```

`variant: "page"` = full-viewport centred. `variant: "section"` = inline within content area.

### When to use which variant

| Error | Variant | Notes |
|---|---|---|
| Backend unreachable | page | All tabs affected |
| `NO_INTERNET` | page | All tabs affected; show cached data below if available |
| `NASA_UNAVAILABLE` / `NASA_ERROR` | section | Nav stays usable; show cached data below if available |
| `NASA_AUTH_ERROR` | section | Include link to `/settings` |
| `N2YO_QUOTA_EXHAUSTED` (no cache) | section | ISS tab only |
| `INTERNAL_ERROR` | section | |

---

## Settings Page

| Setting | Storage | Effect |
|---|---|---|
| Language (6 options with flag icons) | `localStorage` | `i18n.changeLanguage()` immediately |
| NASA API Key (password field) | `localStorage` | `POST /api/v1/settings/nasa-api-key` |
| N2YO API Key (password field) | `localStorage` | `POST /api/v1/settings/n2yo-api-key` |

`GET /api/v1/settings` returns only `{ nasa_key_set: bool, n2yo_key_set: bool }` — never the key values.
Keys stored in-process on the backend (lost on restart — by design for this scope).
