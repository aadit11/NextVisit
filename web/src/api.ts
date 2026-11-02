const base = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
const TOKEN_KEY = "nextvisit-token";

export type City = {
  id: string;
  name: string;
  label: string;
};

export type HistoryCode = {
  code: string;
  description: string | null;
};

export type InspectionVisit = {
  date: string;
  grade: string | null;
  score: number | null;
  codes: HistoryCode[];
};

export type Restaurant = {
  city: string;
  restaurant_id: string;
  name: string | null;
  address: string | null;
  cuisine: string | null;
  area: string | null;
  hours: string | null;
  grade: string | null;
  score: number | null;
  last_inspection_date: string | null;
  serious: boolean | null;
  latitude: number | null;
  longitude: number | null;
  average_stars: number | null;
  review_count: number;
  abstained: boolean;
  probability: number | null;
  label: string;
  trend: "cleaner" | "steady" | "worse" | null;
  recent_visit_count: number;
  recent_serious_count: number;
  peer_count: number;
  peer_graded_count: number;
  peer_standing: "better" | "typical" | "worse" | null;
  score_trend: "falling" | "rising" | "steady" | null;
  codes: HistoryCode[];
  visits: InspectionVisit[];
  earlier_inspections: number;
  history: string;
  history_reason: string | null;
  code_summary?: string;
};

export type MapPlace = {
  restaurant_id: string;
  name: string;
  address: string | null;
  latitude: number;
  longitude: number;
};

export type RestaurantHit = {
  restaurant_id: string;
  name: string;
  area: string | null;
  address: string | null;
  cuisine: string | null;
  grade: string | null;
  last_inspection_date: string | null;
  serious: boolean | null;
  latitude: number | null;
  longitude: number | null;
  average_stars: number | null;
  review_count: number;
};

export type Facets = {
  areas: string[];
  cuisines: string[];
  grades: string[];
};

export type Account = {
  token: string;
  name: string;
  email: string;
};

export type Review = {
  author: string;
  stars: number;
  comment: string;
  created_at: string;
};

export type ReviewList = {
  average_stars: number | null;
  review_count: number;
  mine: { stars: number; comment: string } | null;
  reviews: Review[];
};

export type Filters = {
  area: string;
  cuisine: string;
  grade: string;
  clean: boolean;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export function readToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function storeToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

export async function fetchCities(): Promise<City[]> {
  return readJson<City[]>(await request("/cities"));
}

export async function fetchMap(cityId: string): Promise<MapPlace[]> {
  const rows = await readJson<Array<{ i: string; n: string; y: number; x: number }>>(
    await request(`/cities/${encodeURIComponent(cityId)}/map`),
  );
  return rows.map((row) => ({
    restaurant_id: row.i,
    name: row.n,
    address: null,
    latitude: row.y,
    longitude: row.x,
  }));
}

export async function fetchFacets(cityId: string): Promise<Facets> {
  return readJson<Facets>(await request(`/cities/${encodeURIComponent(cityId)}/facets`));
}

export async function fetchRestaurant(cityId: string, restaurantId: string): Promise<Restaurant> {
  const path = `/cities/${encodeURIComponent(cityId)}/restaurants/${encodeURIComponent(restaurantId)}`;
  return readJson<Restaurant>(await request(path));
}

export async function searchRestaurants(cityId: string, query: string, filters: Filters): Promise<RestaurantHit[]> {
  const params = new URLSearchParams();
  if (query.trim()) params.set("q", query.trim());
  if (filters.area) params.set("area", filters.area);
  if (filters.cuisine) params.set("cuisine", filters.cuisine);
  if (filters.grade) params.set("grade", filters.grade);
  if (filters.clean) params.set("clean", "true");
  const path = `/cities/${encodeURIComponent(cityId)}/restaurants?${params.toString()}`;
  return readJson<RestaurantHit[]>(await request(path));
}

export async function registerAccount(name: string, email: string, password: string): Promise<Account> {
  return readJson<Account>(await send("/account/register", { name, email, password }));
}

export async function loginAccount(email: string, password: string): Promise<Account> {
  return readJson<Account>(await send("/account/login", { email, password }));
}

export async function fetchMe(): Promise<Account> {
  const token = readToken();
  return readJson<Account>(await request("/account/me", token));
}

export async function fetchReviews(cityId: string, restaurantId: string): Promise<ReviewList> {
  const path = `/cities/${encodeURIComponent(cityId)}/restaurants/${encodeURIComponent(restaurantId)}/reviews`;
  return readJson<ReviewList>(await request(path, readToken()));
}

export async function saveReview(cityId: string, restaurantId: string, stars: number, comment: string): Promise<ReviewList> {
  const path = `/cities/${encodeURIComponent(cityId)}/restaurants/${encodeURIComponent(restaurantId)}/reviews`;
  return readJson<ReviewList>(await send(path, { stars, comment }, readToken()));
}

async function request(path: string, token: string | null = null): Promise<Response> {
  return call(path, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
}

async function send(path: string, body: unknown, token: string | null = null): Promise<Response> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  return call(path, { method: "POST", headers, body: JSON.stringify(body) });
}

async function call(path: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, init);
  } catch {
    throw new ApiError("The lookup service is unreachable.", 0);
  }
  if (!response.ok) {
    throw new ApiError(await errorMessage(response), response.status);
  }
  return response;
}

async function readJson<T>(response: Response): Promise<T> {
  return response.json() as Promise<T>;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail) {
      return body.detail;
    }
  } catch {
    // The body was not JSON.
  }
  if (response.status === 404) {
    return "No restaurant with that id was found in this city.";
  }
  return "The lookup could not be completed.";
}
