import { Suspense } from "react";
import type { Metadata } from "next";
import BusinessView from "./BusinessView";
import { SkeletonCard } from "@/components/Skeleton";

export const metadata: Metadata = { title: "Business" };

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
