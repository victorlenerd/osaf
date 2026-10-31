import Link from "next/link";
import type { PlaceCandidate } from "@/lib/types";
import { placeTypeLabel } from "@/lib/constants";
import { Tag } from "./Badges";

export function GoogleVerifiedPill() {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold"
      style={{ background: "color-mix(in oklab, var(--color-good) 14%, transparent)", color: "var(--color-good)" }}
    >
      <svg aria-hidden width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="m5 12 5 5L20 7" />
      </svg>
      Verified on Google
    </span>
  );
}

export function ClosedPill() {
  return (
    <span
      className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold"
      style={{ background: "color-mix(in oklab, var(--color-bad) 14%, transparent)", color: "var(--color-bad)" }}
    >
      Permanently closed
    </span>
  );
}

export default function PlaceCandidateCard({ candidate }: { candidate: PlaceCandidate }) {
  const href = `/business?id=${encodeURIComponent(candidate.place_id)}`;
  const closed = candidate.business_status === "CLOSED_PERMANENTLY";
  const type = placeTypeLabel(candidate.primary_type);
  return (
    <li>
      <Link href={href} className="card group block p-4 transition-transform hover:-translate-y-0.5 focus-visible:-translate-y-0.5 sm:p-5">
        <div className="flex flex-wrap items-center gap-2">
          <GoogleVerifiedPill />
          {closed && <ClosedPill />}
          {type && <Tag>{type}</Tag>}
        </div>
        <h3 className="font-display mt-2 text-lg font-semibold leading-snug group-hover:underline" style={{ color: "var(--brand)" }}>
          {candidate.name}
        </h3>
        <p className="mt-0.5 text-sm muted">{candidate.formatted_address}</p>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm">
          <span className="muted">{[candidate.city, candidate.country].filter(Boolean).join(", ")}</span>
          <span className="inline-flex items-center gap-1 font-medium" style={{ color: "var(--accent-ink)" }}>
            See Google reviews
            <svg aria-hidden width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12h14M13 6l6 6-6 6" />
            </svg>
          </span>
        </div>
      </Link>
    </li>
  );
}
