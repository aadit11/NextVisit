export type City = {
  id: string;
  name: string;
  label: string;
  has_work_order: boolean;
};

export async function fetchCities(): Promise<City[]> {
  const response = await fetch("/cities");
  if (!response.ok) {
    throw new Error("Could not load cities.");
  }
  return response.json();
}
