import { Suspense } from "react";
import type { Metadata } from "next";
import BusinessView from "./BusinessView";
import { SkeletonCard } from "@/components/Skeleton";

// The interactive page (Google fallback, legacy ?id= links). The crawlable, canonical page of a
// reviewed business is /b/<slug>, rendered by the backend; this route stays out of the index.
export const metadata: Metadata = { title: "Business", robots: { index: false, follow: true } };

export default function BusinessPage() {
  return (
    <Suspense
      fallback={
        <div className="grid gap-4 pt-8">
          <SkeletonCard lines={2} />
          <SkeletonCard lines={5} />
        </div>
      }
    >
      <BusinessView />
    </Suspense>
  );
}
