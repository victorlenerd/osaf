import Link from "next/link";
import type { ReactNode } from "react";
import { formatDate } from "@/lib/format";

export interface LegalSection {
  id: string;
  title: string;
  body: ReactNode;
}

interface Props {
  kicker: string;
  title: string;
  effective: string;
  intro: ReactNode;
  /** Plain-language bullets shown before the full text. Not a substitute for it. */
  summary: string[];
  sections: LegalSection[];
  related: { href: string; label: string };
}

export default function LegalPage({ kicker, title, effective, intro, summary, sections, related }: Props) {
  return (
    <div className="max-w-3xl pt-8 sm:pt-14">
      <p className="text-xs font-semibold uppercase tracking-[0.2em]" style={{ color: "var(--accent-ink)" }}>
        {kicker}
      </p>
      <h1 className="font-display mt-3 text-4xl font-semibold leading-tight tracking-tight sm:text-5xl" style={{ color: "var(--brand)" }}>
        {title}
      </h1>
      <p className="mt-3 text-sm muted">
        Effective {formatDate(effective)} · See also our <Link href={related.href} className="underline">{related.label}</Link>
      </p>
      <div className="mt-5 text-base leading-relaxed">{intro}</div>

      <section className="card mt-8 p-5 sm:p-6" aria-labelledby="summary-heading">
        <h2 id="summary-heading" className="text-xs font-semibold uppercase tracking-wide muted">In short</h2>
        <ul className="mt-3 space-y-2 text-sm leading-relaxed">
          {summary.map((s) => (
            <li key={s} className="flex gap-2">
              <span aria-hidden className="w-3 shrink-0 font-bold" style={{ color: "var(--accent-ink)" }}>–</span>
              <span>{s}</span>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-xs muted">This summary is for convenience only. The full text below is what applies.</p>
      </section>

      <nav aria-label="Contents" className="mt-8">
        <h2 className="text-xs font-semibold uppercase tracking-wide muted">Contents</h2>
        <ol className="mt-2 columns-1 gap-6 text-sm sm:columns-2">
          {sections.map((s, i) => (
            <li key={s.id} className="py-0.5">
              <a href={`#${s.id}`} className="hover:underline">
                <span className="muted">{i + 1}.</span> {s.title}
              </a>
            </li>
          ))}
        </ol>
      </nav>

      <article className="card mt-8 divide-y line px-5 sm:px-8">
        {sections.map((s, i) => (
          <section key={s.id} id={s.id} className="legal-section scroll-mt-20 py-6 sm:py-8" aria-labelledby={`${s.id}-h`}>
            <h2 id={`${s.id}-h`} className="font-display text-xl font-semibold sm:text-2xl" style={{ color: "var(--brand)" }}>
              <span className="muted">{i + 1}.</span> {s.title}
            </h2>
            <div className="mt-3 space-y-3 text-[15px] leading-relaxed">{s.body}</div>
          </section>
        ))}
      </article>
    </div>
  );
}
