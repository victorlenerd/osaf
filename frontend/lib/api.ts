import type { BusinessResponse, Category, GooglePlaceResponse, LookupResponse, SearchResponse } from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { signal, headers: { accept: "application/json" } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail || `Request failed (${res.status})`);
  }
  return (await res.json()) as T;
}

export interface SearchParams {
  q: string;
  country?: string;
  category?: Category | "";
  limit?: number;
}

export function searchBusinesses(params: SearchParams, signal?: AbortSignal): Promise<SearchResponse> {
  const qs = new URLSearchParams();
  qs.set("q", params.q);
  if (params.country) qs.set("country", params.country);
  if (params.category) qs.set("category", params.category);
  qs.set("limit", String(params.limit ?? 20));
  return getJson<SearchResponse>(`/api/search?${qs.toString()}`, signal);
}

export function getBusiness(id: string, signal?: AbortSignal): Promise<BusinessResponse> {
  return getJson<BusinessResponse>(`/api/business/${encodeURIComponent(id)}`, signal);
}

export interface LookupParams {
  q: string;
  country?: string;
  limit?: number;
}

/** Ask Google Places (via the API) for businesses matching a name. Only called when Afefehub search is empty. */
export function lookupPlaces(params: LookupParams, signal?: AbortSignal): Promise<LookupResponse> {
  const qs = new URLSearchParams();
  qs.set("q", params.q);
  if (params.country) qs.set("country", params.country);
  qs.set("limit", String(params.limit ?? 5));
  return getJson<LookupResponse>(`/api/places/lookup?${qs.toString()}`, signal);
}

/** Live Google reviews (max 5) plus an AI summary for a place. 404 for unknown ids and any `afefe:` id. */
export function getGooglePlace(id: string, signal?: AbortSignal): Promise<GooglePlaceResponse> {
  return getJson<GooglePlaceResponse>(`/api/places/${encodeURIComponent(id)}/google`, signal);
}
