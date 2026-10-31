const STAR = "M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.4l-5.9 3.2 1.3-6.6L2.5 9.4l6.6-.8L12 2.5z";

function Row({ size, color }: { size: number; color: string }) {
  return (
    <span className="inline-flex gap-0.5" aria-hidden>
      {[0, 1, 2, 3, 4].map((i) => (
        <svg key={i} width={size} height={size} viewBox="0 0 24 24">
          <path d={STAR} fill={color} />
        </svg>
      ))}
    </span>
  );
}

/** Five-star rating row used for Google data (places and reviews). Partial stars are drawn by clipping a coloured row over a grey one. */
export default function Stars({ rating, size = 14, withValue = false }: { rating: number | null; size?: number; withValue?: boolean }) {
  if (rating == null) return <span className="text-xs muted">No rating</span>;
  const value = Math.max(0, Math.min(5, rating));
  const label = `${value.toFixed(1)} out of 5 stars`;
  return (
    <span className="inline-flex items-center gap-1.5" role="img" aria-label={label} title={label}>
      <span className="relative inline-flex">
        <Row size={size} color="var(--line)" />
        <span className="absolute inset-y-0 left-0 overflow-hidden" style={{ width: `${(value / 5) * 100}%` }}>
          <Row size={size} color="var(--color-mixed)" />
        </span>
      </span>
      {withValue && <span className="text-sm font-semibold">{value.toFixed(1)}</span>}
    </span>
  );
}
