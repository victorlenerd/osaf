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

export interface Review {
  review_id: string;
  created_at: string;
  reel_url: string;
  reel_shortcode: string;
  reviewer_display_name: string | null;
  extraction: Extraction;
}

export interface BusinessResponse {
  business: Business;
  summary: Summary | null;
  reviews: Review[];
}
