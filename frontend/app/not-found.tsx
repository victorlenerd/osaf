import Link from "next/link";

export default function NotFound() {
  return (
    <div className="card mx-auto mt-16 max-w-lg p-8 text-center">
      <p className="font-display text-6xl font-bold" style={{ color: "var(--accent-ink)" }}>404</p>
      <h1 className="font-display mt-2 text-2xl font-semibold" style={{ color: "var(--brand)" }}>Page not found</h1>
      <p className="mt-2 text-sm muted">That page doesn&apos;t exist. The search is a good place to start.</p>
      <Link href="/" className="mt-5 inline-block rounded-full px-5 py-2 text-sm font-semibold" style={{ background: "var(--accent)", color: "var(--accent-fg)" }}>
        Back to search
      </Link>
    </div>
  );
}
