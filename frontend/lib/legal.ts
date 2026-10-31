/**
 * Facts referenced by the Terms of Service and Privacy Policy. Keep them in one place so a
 * change of entity, address or contact updates both documents. Review these before launch.
 */
export const LEGAL = {
  /** Trading name used throughout both documents. */
  brand: "Afefehub",
  /** Registered legal entity that operates the service: 1CTECH, a Canadian company (https://1ctech.ca). */
  operator: "1CTECH",
  operatorUrl: "https://1ctech.ca",
  /** Postal address for legal notices. Add the street address before launch; the country must stay Canada. */
  address: "Ontario, Canada",
  /** 1CTECH is registered in Ontario: Ontario law governs the Terms and Ontario courts hear disputes. */
  governingLaw: "the Province of Ontario and the federal laws of Canada applicable therein",
  governingLawAdjective: "Ontario",
  courts: "the courts of Ontario, Canada",
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
