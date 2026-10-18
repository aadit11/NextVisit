import { useEffect, useState } from "react";
import { fetchCities, type City } from "./api";

export function App() {
  const [cities, setCities] = useState<City[]>([]);
  const [cityId, setCityId] = useState("new_york");
  const [query, setQuery] = useState("");

  useEffect(() => {
    fetchCities()
      .then(setCities)
      .catch(() => setCities([]));
  }, []);

  const selected = cities.find((city) => city.id === cityId);

  return (
    <main>
      <h1>Nextvisit</h1>
      <p>Chance the next posted inspection goes badly, from that city's public history.</p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
        }}
      >
        <label>
          City
          <select value={cityId} onChange={(event) => setCityId(event.target.value)}>
            {cities.map((city) => (
              <option key={city.id} value={city.id}>
                {city.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Name or id
          <input value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <button type="submit">Look up</button>
      </form>
      {selected ? <p>{selected.label}</p> : null}
    </main>
  );
}
