const UNITS = ["B", "KB", "MB", "GB", "TB"] as const;

/**
 * Human-readable byte size for display only (file list, upload dialog).
 * 0 → "0 B"; negative or non-finite → "—".
 */
export function formatBytes(bytes: number, decimals = 1): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes === 0) return "0 B";
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), UNITS.length - 1);
  const value = bytes / Math.pow(1024, i);
  return `${value.toFixed(i === 0 ? 0 : decimals)} ${UNITS[i]}`;
}
