export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="card animate-pulse p-5" aria-hidden>
      <div className="h-5 w-2/3 rounded" style={{ background: "var(--line)" }} />
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="mt-3 h-3 rounded" style={{ background: "var(--line)", width: `${90 - i * 15}%` }} />
      ))}
    </div>
  );
}
