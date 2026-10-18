const base = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export type City = {
  id: string;
  name: string;
  label: string;
  has_work_order: boolean;
};

export type WorkOrderItem = {
  station: string;
  violation_code: string;
  source_span: string;
  step: string;
};

export type Restaurant = {
  city: string;
  restaurant_id: string;
  name: string | null;
  cuisine: string | null;
  abstained: boolean;
  probability: number | null;
  label: string;
  codes: string[];
  work_order: WorkOrderItem[];
  work_order_reason: string | null;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function fetchCities(): Promise<City[]> {
  return readJson<City[]>(await request("/cities"));
}

export async function fetchRestaurant(cityId: string, restaurantId: string): Promise<Restaurant> {
  const path = `/cities/${encodeURIComponent(cityId)}/restaurants/${encodeURIComponent(restaurantId)}`;
  return readJson<Restaurant>(await request(path));
}

async function request(path: string): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${base}${path}`);
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
