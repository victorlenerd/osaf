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

const COUNTRY_NAMES = new Map<string, string>(COUNTRIES.map((c) => [c.code, c.name]));
export function countryName(code: string): string {
  return COUNTRY_NAMES.get(code) ?? code;
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

export const WHATSAPP_NUMBER = process.env.NEXT_PUBLIC_WHATSAPP_NUMBER || "";
export const REPO_URL = process.env.NEXT_PUBLIC_REPO_URL || "";
