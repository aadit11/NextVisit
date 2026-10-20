import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react";
import {
  ApiError,
  fetchCities,
  fetchRestaurant,
  searchRestaurants,
  type City,
  type Restaurant,
  type RestaurantHit,
} from "./api";
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
  const [matches, setMatches] = useState<RestaurantHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [highlight, setHighlight] = useState(0);

  useEffect(() => {
    fetchCities()
      .then((loaded) => {
        setCities(loaded);
        setCitiesError(null);
      })
      .catch(() => setCitiesError("Cities could not be loaded. The lookup service is unreachable."));
  }, []);

  useEffect(() => {
    const text = query.trim();
    if (/^\d+$/.test(text) || text.length < 2) {
      setMatches([]);
      setSearching(false);
      if (text.length < 2) setError(null);
      return;
    }
    let cancelled = false;
    setSearching(true);
    const handle = window.setTimeout(() => {
      searchRestaurants(cityId, text)
        .then((hits) => {
          if (cancelled) return;
          setMatches(hits);
          setHighlight(0);
          if (hits.length === 0) {
            setRestaurant(null);
            setError("No restaurants with that name in this city.");
          } else {
            setError(null);
          }
        })
        .catch((caught: unknown) => {
          if (cancelled) return;
          setMatches([]);
          setError(caught instanceof ApiError ? caught.message : "The name search could not be completed.");
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 280);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [query, cityId]);

  const selected = cities.find((city) => city.id === cityId) ?? null;

  function chooseCity(nextId: string) {
    setCityId(nextId);
    setRestaurant(null);
    setError(null);
    setActiveCode(null);
    setMatches([]);
    setHighlight(0);
  }

  async function lookup(id: string) {
    const restaurantId = id.trim();
    if (!restaurantId) {
      setError("Enter a name or id.");
      setRestaurant(null);
      return;
    }
    setLoading(true);
    setError(null);
    setActiveCode(null);
    setMatches([]);
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

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = query.trim();
    if (/^\d+$/.test(text)) {
      void lookup(text);
      return;
    }
    if (matches[highlight]) {
      void lookup(matches[highlight].restaurant_id);
    }
  }

  function onQueryKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (matches.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlight((current) => Math.min(matches.length - 1, current + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlight((current) => Math.max(0, current - 1));
    } else if (event.key === "Enter" && matches[highlight]) {
      event.preventDefault();
      void lookup(matches[highlight].restaurant_id);
    }
  }

  return (
    <main>
      <header className="mast">
        <p className="wordmark">Nextvisit</p>
        <div>
          <h1>The next inspection, read from the public record.</h1>
          <p className="lede">
            Choose a city, then a name. The score uses only inspections that city has already posted.
          </p>
        </div>
      </header>

      <div className="workspace">
        <form className="finder" onSubmit={onSubmit}>
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
          {citiesError ? <p className="notice problem">{citiesError}</p> : null}
          {selected ? <p className="city-label">{selected.label}</p> : null}
          <label className="query">
            <span>Name or id</span>
            <input
              value={query}
              placeholder={selected?.id === "new_york" ? "Name or CAMIS" : "Name or restaurant id"}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={onQueryKeyDown}
              autoComplete="off"
              spellCheck={false}
              aria-autocomplete="list"
              aria-controls="matches"
              aria-activedescendant={matches[highlight] ? `match-${matches[highlight].restaurant_id}` : undefined}
            />
          </label>
          <div className="actions">
            <button className="submit" type="submit" disabled={loading || searching || cities.length === 0}>
              {loading ? "Reading the record" : searching ? "Searching this city" : "Open"}
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
          {matches.length > 0 ? (
            <ul className="matches" id="matches" role="listbox" aria-label="Matching restaurants">
              {matches.map((hit, index) => (
                <li key={hit.restaurant_id} style={{ animationDelay: `${index * 35}ms` }}>
                  <button
                    id={`match-${hit.restaurant_id}`}
                    type="button"
                    role="option"
                    aria-selected={index === highlight}
                    className={index === highlight ? "match selected" : "match"}
                    onMouseEnter={() => setHighlight(index)}
                    onClick={() => void lookup(hit.restaurant_id)}
                  >
                    <strong>{hit.name}</strong>
                    {hit.address ? <em className="street">{hit.address}</em> : null}
                    <span>
                      {hit.address ? "" : hit.area ? `${hit.area} · ` : ""}
                      {hit.restaurant_id}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          {matches.length > 0 ? <p className="hint">Arrow keys move. Enter opens the highlighted row.</p> : null}
        </form>

        <section className="stage" aria-busy={loading}>
          {loading ? <p className="notice">Reading this restaurant's earlier inspections.</p> : null}
          {!loading && error && matches.length === 0 ? <p className="notice problem">{error}</p> : null}
          {!loading && restaurant ? (
            <ResultCard
              key={`${restaurant.city}-${restaurant.restaurant_id}`}
              restaurant={restaurant}
              hasWorkOrder={selected?.has_work_order ?? restaurant.work_order.length > 0}
              activeCode={activeCode}
              onToggleCode={(code) => setActiveCode((current) => (current === code ? null : code))}
            />
          ) : null}
          {!loading && !restaurant && selected && !selected.has_work_order && matches.length === 0 ? (
            <WorkOrder items={[]} hasWorkOrder={false} reason={null} activeCode={null} />
          ) : null}
          {!loading && !restaurant && !error && matches.length === 0 && selected?.has_work_order ? (
            <div className="idle-stage">
              <span className="idle-ring" aria-hidden="true" />
              <p className="idle">The gauge appears after a restaurant is chosen.</p>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}
