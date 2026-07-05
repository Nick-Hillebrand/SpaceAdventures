function getLocale(): string {
  return typeof navigator !== "undefined" && navigator.language ? navigator.language : "en-US";
}

function getTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone ?? "UTC";
  } catch {
    return "UTC";
  }
}

export function formatDateTime(isoUtc: string): string {
  return new Intl.DateTimeFormat(getLocale(), {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: getTimeZone(),
  }).format(new Date(isoUtc));
}

export function formatDate(isoUtc: string): string {
  return new Intl.DateTimeFormat(getLocale(), {
    dateStyle: "medium",
    timeZone: getTimeZone(),
  }).format(new Date(isoUtc));
}

export function formatTime(isoUtc: string): string {
  return new Intl.DateTimeFormat(getLocale(), {
    timeStyle: "short",
    timeZone: getTimeZone(),
  }).format(new Date(isoUtc));
}

export function formatRelative(isoUtc: string): string {
  const diffMs = new Date(isoUtc).getTime() - Date.now();
  const rtf = new Intl.RelativeTimeFormat(getLocale(), { numeric: "auto" });
  const abs = Math.abs(diffMs);
  if (abs < 60_000) return rtf.format(Math.round(diffMs / 1_000), "second");
  if (abs < 3_600_000) return rtf.format(Math.round(diffMs / 60_000), "minute");
  if (abs < 86_400_000) return rtf.format(Math.round(diffMs / 3_600_000), "hour");
  return rtf.format(Math.round(diffMs / 86_400_000), "day");
}
