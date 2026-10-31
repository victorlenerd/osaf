export type Category =
  | "restaurant" | "street_food" | "cafe" | "bar_lounge" | "hotel" | "salon_barber"
  | "spa_wellness" | "retail" | "supermarket" | "fashion" | "electronics" | "auto"
  | "health_clinic" | "pharmacy" | "education" | "events_venue" | "transport"
  | "real_estate" | "services" | "other";

export type Sentiment = "positive" | "mixed" | "negative";
export type Recommend = "yes" | "no" | "maybe";

export interface LatLng {
  lat: number;
  lng: number;
}

export interface SearchResult {
  business_id: string;
  name: string;
  formatted_address: string;
  city: string | null;
  country: string;
  category: Category | string;
  review_count: number;
  recommend_rate: number;
  overall_sentiment: Sentiment | null;
  summary_headline: string | null;
  location: LatLng | null;
}

export interface SearchResponse {
  results: SearchResult[];
}

export interface Business extends SearchResult {
  source: "google" | "user";
  google_primary_type: string | null;
  recommend_counts: { yes: number; no: number; maybe: number };
  keywords: string[];
  created_at: string;
  updated_at: string;
}

export interface Summary {
  overall_sentiment: Sentiment;
  headline: string;
  recurring_praise: string[];
  recurring_complaints: string[];
  standout_items: string[];
  recommendation_rate: number;
  review_count: number;
  last_review_at: string;
  last_updated: string;
  model_version: string;
}

export interface Extraction {
  business_name_as_said: string;
  visit: { when_text: string | null; when_iso: string | null; where_text: string | null };
  good: string[];
  improve: string[];
  recommend: Recommend;
  category: Category | string;
  keywords: string[];
  overall_sentiment: Sentiment;
  language: string;
  one_line_summary: string;
}

export type ReviewSource = "reel" | "voice";

export interface Review {
  review_id: string;
  created_at: string;
  /** "reel": public Instagram reel. "voice": WhatsApp voice note, no video and no face check. */
  source: ReviewSource;
  /** null for voice reviews */
  reel_url: string | null;
  /** null for voice reviews */
  reel_shortcode: string | null;
  /** Absolute URL that redirects to the audio file (m4a). null for reel reviews or when audio is unavailable. */
  audio_url: string | null;
  reviewer_display_name: string | null;
  extraction: Extraction;
}

export interface BusinessResponse {
  business: Business;
  summary: Summary | null;
  reviews: Review[];
}

/* ---- Google Places (live lookups, see GET /api/places/*) ---- */

export type BusinessStatus = "OPERATIONAL" | "CLOSED_TEMPORARILY" | "CLOSED_PERMANENTLY" | string;

export interface PlaceCandidate {
  place_id: string;
  name: string;
  formatted_address: string;
  lat: number | null;
  lng: number | null;
  country: string | null;
  city: string | null;
  primary_type: string | null;
  business_status: BusinessStatus | null;
}

export interface LookupResponse {
  candidates: PlaceCandidate[];
}

export interface GooglePlace {
  place_id: string;
  name: string;
  formatted_address: string;
  city: string | null;
  country: string | null;
  lat: number | null;
  lng: number | null;
  primary_type: string | null;
  rating: number | null;
  user_rating_count: number;
  google_maps_uri: string | null;
  business_status: BusinessStatus | null;
}

export interface GoogleSummary {
  overall_sentiment: Sentiment;
  /** "" when Google had no textual reviews; show the star rating alone. */
  headline: string;
  recurring_praise: string[];
  recurring_complaints: string[];
  standout_items: string[];
  rating: number | null;
  user_rating_count: number;
  reviews_considered: number;
  generated_at: string;
  model_version: string;
}

export interface GoogleReview {
  author_name: string;
  author_uri: string | null;
  author_photo_uri: string | null;
  rating: number | null;
  /** Verbatim from Google; "" for rating-only reviews. Never edited or truncated. */
  text: string;
  language: string | null;
  relative_time: string;
  publish_time: string | null;
  google_maps_uri: string | null;
}

export interface GooglePlaceResponse {
  place: GooglePlace;
  summary: GoogleSummary;
  reviews: GoogleReview[];
  attribution: string;
}
