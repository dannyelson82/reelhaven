// Small display helpers.

const LANGUAGE_NAMES = new Intl.DisplayNames(['en'], { type: 'language' });

/** "fra" -> "French"; null -> "Untagged". */
export function languageName(code: string | null): string {
  if (!code) return 'Untagged';
  try {
    return LANGUAGE_NAMES.of(code) ?? code;
  } catch {
    return code;
  }
}

export function formatBytes(bytes: number | null): string {
  if (bytes === null) return '–';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  return `${value.toFixed(value >= 100 || unit === 0 ? 0 : 1)} ${units[unit]}`;
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null) return '–';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.round(seconds % 60);
  return h
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${m}:${String(s).padStart(2, '0')}`;
}

/** 1920x1080 -> "1080p"; 3840x2160 -> "4K". */
export function resolutionLabel(width: number | null, height: number | null): string | null {
  if (!width || !height) return null;
  if (width >= 3200 || height >= 2000) return '4K';
  if (width >= 1800 || height >= 1000) return '1080p';
  if (width >= 1200 || height >= 700) return '720p';
  return `${height}p`;
}

export const HDR_LABELS: Record<string, string> = {
  hdr10: 'HDR10',
  hdr10plus: 'HDR10+',
  hlg: 'HLG',
  dolby_vision: 'Dolby Vision',
};

/** A rough time left: "under a minute", "12 min", "1 h 05 min". */
export function formatTimeLeft(seconds: number): string {
  if (seconds < 60) return 'under a minute';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, '0')} min`;
}
