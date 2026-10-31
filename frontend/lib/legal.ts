/**
 * Facts referenced by the Terms of Service and Privacy Policy. Keep them in one place so a
 * change of entity, address or contact updates both documents. Review these before launch.
 */
export const LEGAL = {
  /** Trading name used throughout both documents. */
  brand: "Afefehub",
  /** Registered legal entity that operates the service. Replace with the company name once incorporated. */
  operator: "Afefehub",
  /** Postal address for legal notices. Set before launch. */
  address: "Lagos, Nigeria",
  /** Country whose law governs the Terms and whose courts hear disputes. */
  governingLaw: "the Federal Republic of Nigeria",
  courts: "the courts of Lagos State, Nigeria",
  /** Contact mailboxes. Make sure these are delivered before publishing. */
  legalEmail: "legal@afefehub.com",
  privacyEmail: "privacy@afefehub.com",
  /** Minimum age to submit a review or otherwise use the service. */
  minimumAge: 18,
  /** Dates shown at the top of each document (ISO). Bump when the text changes. */
  termsEffective: "2026-10-31",
  privacyEffective: "2026-10-31",
  siteUrl: "https://afefehub.com",
} as const;
