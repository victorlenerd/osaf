import type { Metadata } from "next";
import LegalPage from "@/components/LegalPage";
import { LEGAL } from "@/lib/legal";
import { PAYOUTS_ENABLED } from "@/lib/constants";
import { CURRENT_SECTIONS, CURRENT_SUMMARY } from "./current-terms";
import { PAYOUT_SECTIONS, PAYOUT_SUMMARY } from "./payout-terms";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: `The terms that govern use of ${LEGAL.brand}, including how video reviews are submitted, verified, published and removed.`,
};

const B = LEGAL.brand;

// Until the payout launch the Terms in force stay up; the payout version replaces them when
// NEXT_PUBLIC_PAYOUTS_ENABLED is "true" (set together with the backend's PAYOUTS_ENABLED).
const sections = PAYOUTS_ENABLED ? PAYOUT_SECTIONS : CURRENT_SECTIONS;
const summary = PAYOUTS_ENABLED ? PAYOUT_SUMMARY : CURRENT_SUMMARY;

export default function TermsPage() {
  return (
    <LegalPage
      kicker="Legal"
      title="Terms of Service"
      effective={LEGAL.termsEffective}
      related={{ href: "/privacy", label: "Privacy Policy" }}
      intro={
        <p>
          These Terms explain the rules for using {B}: how video reviews are submitted and verified, what you promise when you submit one,
          how businesses can raise concerns, and the limits of what we are responsible for. Please read them; they affect your rights.
        </p>
      }
      summary={summary}
      sections={sections}
    />
  );
}
