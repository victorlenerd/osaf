export function percent(rate: number): string {
  return `${Math.round(Math.max(0, Math.min(1, rate)) * 100)}%`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  // Date-only strings (YYYY-MM-DD) would parse as UTC midnight and show a day early in western time zones.
  const d = new Date(/^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T00:00:00` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function mapsUrl(opts: { lat?: number; lng?: number; name: string; address: string }): string {
  if (typeof opts.lat === "number" && typeof opts.lng === "number") {
    return `https://www.google.com/maps/search/?api=1&query=${opts.lat},${opts.lng}`;
  }
  return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${opts.name} ${opts.address}`)}`;
}

export function pluralize(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
