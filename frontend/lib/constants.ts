import type { Category } from "./types";

export const COUNTRIES: { code: string; name: string }[] = [
  { code: "NG", name: "Nigeria" },
  { code: "GH", name: "Ghana" },
  { code: "KE", name: "Kenya" },
  { code: "ZA", name: "South Africa" },
  { code: "RW", name: "Rwanda" },
  { code: "UG", name: "Uganda" },
  { code: "TZ", name: "Tanzania" },
  { code: "SN", name: "Senegal" },
  { code: "CI", name: "Côte d'Ivoire" },
  { code: "CM", name: "Cameroon" },
  { code: "ET", name: "Ethiopia" },
  { code: "EG", name: "Egypt" },
  { code: "MA", name: "Morocco" },
];

export const CATEGORIES: { value: Category; label: string }[] = [
  { value: "restaurant", label: "Restaurant" },
  { value: "street_food", label: "Street food" },
  { value: "cafe", label: "Café" },
  { value: "bar_lounge", label: "Bar & lounge" },
  { value: "hotel", label: "Hotel" },
  { value: "salon_barber", label: "Salon & barber" },
  { value: "spa_wellness", label: "Spa & wellness" },
  { value: "retail", label: "Retail" },
  { value: "supermarket", label: "Supermarket" },
  { value: "fashion", label: "Fashion" },
  { value: "electronics", label: "Electronics" },
  { value: "auto", label: "Auto" },
  { value: "health_clinic", label: "Health clinic" },
  { value: "pharmacy", label: "Pharmacy" },
  { value: "education", label: "Education" },
  { value: "events_venue", label: "Events venue" },
  { value: "transport", label: "Transport" },
  { value: "real_estate", label: "Real estate" },
  { value: "services", label: "Services" },
  { value: "other", label: "Other" },
];

const CATEGORY_LABELS = new Map<string, string>(CATEGORIES.map((c) => [c.value, c.label]));
export function categoryLabel(value: string): string {
  return CATEGORY_LABELS.get(value) ?? value.replace(/_/g, " ");
}

/** Humanise a Google Places primary type such as "nigerian_restaurant" → "Nigerian restaurant". */
export function placeTypeLabel(value: string | null | undefined): string {
  if (!value) return "";
  const words = value.replace(/_/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

const COUNTRY_NAMES = new Map<string, string>(COUNTRIES.map((c) => [c.code, c.name]));
/** Human name for an ISO alpha-2 code: our curated list first, then the runtime's region names
 *  (reviewer dialing codes can come from anywhere), then the code itself. */
export function countryName(code: string): string {
  const known = COUNTRY_NAMES.get(code);
  if (known) return known;
  try {
    return new Intl.DisplayNames(["en"], { type: "region" }).of(code.toUpperCase()) ?? code;
  } catch {
    return code;
  }
}

const LANGUAGE_NAMES: Record<string, string> = {
  en: "English", fr: "French", pt: "Portuguese", ar: "Arabic", sw: "Swahili", ha: "Hausa",
  yo: "Yoruba", ig: "Igbo", pcm: "Nigerian Pidgin", tw: "Twi", am: "Amharic", zu: "Zulu",
  xh: "Xhosa", af: "Afrikaans", rw: "Kinyarwanda", wo: "Wolof", lg: "Luganda", so: "Somali",
};
export function languageName(code: string): string {
  const base = code.toLowerCase().split("-")[0];
  return LANGUAGE_NAMES[base] ?? code.toUpperCase();
}

/** Shown on the site and used for the wa.me link. Override with NEXT_PUBLIC_WHATSAPP_NUMBER. */
export const WHATSAPP_NUMBER = process.env.NEXT_PUBLIC_WHATSAPP_NUMBER || "+1 (555) 137-0042";
export const REPO_URL = process.env.NEXT_PUBLIC_REPO_URL || "";

/** Reviewer rewards. Mirrors backend `points_per_review`; the gift card itself is handed out manually for now. */
export const POINTS_PER_REVIEW = 10;
export const WEEKLY_REVIEW_LIMIT = 3;
export const REWARD_POINTS = 100;
export const REWARD_LABEL = "$10 Amazon gift card";
