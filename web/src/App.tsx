import { useEffect, useState } from "react";
import { ApiError, fetchCities, fetchRestaurant, type City, type Restaurant } from "./api";
import { ResultCard } from "./ResultCard";
import { WorkOrder } from "./WorkOrder";

const SAMPLE_CAMIS = "30075445";

export function App() {
  const [cities, setCities] = useState<City[]>([]);
  const [cityId, setCityId] = useState("new_york");
  const [query, setQuery] = useState("");
  const [restaurant, setRestaurant] = useState<Restaurant | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [citiesError, setCitiesError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeCode, setActiveCode] = useState<string | null>(null);

  useEffect(() => {
    fetchCities()
      .then((loaded) => {
        setCities(loaded);
        setCitiesError(null);
      })
      .catch(() => setCitiesError("Cities could not be loaded. The lookup service is unreachable."));
  }, []);

  const selected = cities.find((city) => city.id === cityId) ?? null;

  function chooseCity(nextId: string) {
    setCityId(nextId);
    setRestaurant(null);
    setError(null);
    setActiveCode(null);
  }

  async function lookup(id: string) {
    const restaurantId = id.trim();
    if (!restaurantId) {
      setError("Enter a restaurant id.");
      setRestaurant(null);
      return;
    }
    setLoading(true);
    setError(null);
    setActiveCode(null);
    try {
      const body = await fetchRestaurant(cityId, restaurantId);
      setRestaurant(body);
    } catch (caught) {
      setRestaurant(null);
      setError(caught instanceof ApiError ? caught.message : "The lookup could not be completed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main>
      <header className="mast">
        <p className="wordmark">Nextvisit</p>
        <h1>The next inspection, read from the public record.</h1>
        <p className="lede">
          Pick a city, then look up a restaurant by its own id. The score uses only inspections that city has already posted.
        </p>
      </header>

      <form
        className="finder"
        onSubmit={(event) => {
          event.preventDefault();
          void lookup(query);
        }}
      >
        <div className="cities" role="radiogroup" aria-label="City">
          {cities.map((city) => (
            <button
              key={city.id}
              type="button"
              role="radio"
              aria-checked={city.id === cityId}
              className={city.id === cityId ? "city selected" : "city"}
              onClick={() => chooseCity(city.id)}
            >
              {city.name}
            </button>
          ))}
        </div>
        {citiesError ? <p className="notice">{citiesError}</p> : null}
        <label className="query">
          <span>{selected?.id === "new_york" ? "CAMIS" : "Restaurant id"}</span>
          <input
            value={query}
            placeholder={selected?.id === "new_york" ? "Such as 30075445" : "City restaurant id"}
            onChange={(event) => setQuery(event.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
        </label>
        <div className="actions">
          <button className="submit" type="submit" disabled={loading || cities.length === 0}>
            {loading ? "Checking the record" : "Look up"}
          </button>
          {cityId === "new_york" ? (
            <button
              className="sample"
              type="button"
              onClick={() => {
                setQuery(SAMPLE_CAMIS);
                void lookup(SAMPLE_CAMIS);
              }}
            >
              Try {SAMPLE_CAMIS}
            </button>
          ) : null}
        </div>
        {selected ? <p className="city-label">{selected.label}</p> : null}
      </form>

      <section className="stage" aria-busy={loading}>
        {loading ? <p className="notice">Reading this restaurant's earlier inspections.</p> : null}
        {!loading && error ? <p className="notice problem">{error}</p> : null}
        {!loading && restaurant ? (
          <ResultCard
            key={restaurant.restaurant_id}
            restaurant={restaurant}
            hasWorkOrder={selected?.has_work_order ?? restaurant.work_order.length > 0}
            activeCode={activeCode}
            onToggleCode={(code) => setActiveCode((current) => (current === code ? null : code))}
          />
        ) : null}
        {!loading && !restaurant && selected && !selected.has_work_order ? (
          <WorkOrder items={[]} hasWorkOrder={false} reason={null} activeCode={null} />
        ) : null}
        {!loading && !restaurant && !error && selected?.has_work_order ? (
          <p className="idle">The gauge appears after an id is found.</p>
        ) : null}
      </section>
    </main>
  );
}
