import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import {
  ApiError,
  fetchCities,
  fetchFacets,
  fetchMap,
  fetchMe,
  fetchRestaurant,
  loginAccount,
  readToken,
  registerAccount,
  searchRestaurants,
  storeToken,
  type Account,
  type City,
  type Facets,
  type Filters,
  type MapPlace,
  type Restaurant,
  type RestaurantHit,
} from "./api";
import { MapPanel, type MapPoint } from "./MapPanel";
import { ResultCard } from "./ResultCard";

const SAMPLE_CAMIS = "30075445";
const EMPTY_FILTERS: Filters = { area: "", cuisine: "", grade: "", clean: false };
const EMPTY_FACETS: Facets = { areas: [], cuisines: [], grades: [] };

export function App() {
  const [cities, setCities] = useState<City[]>([]);
  const [cityId, setCityId] = useState("new_york");
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [facets, setFacets] = useState<Facets>(EMPTY_FACETS);
  const [restaurant, setRestaurant] = useState<Restaurant | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [citiesError, setCitiesError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [matches, setMatches] = useState<RestaurantHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [suggestionsDismissed, setSuggestionsDismissed] = useState(false);
  const queryField = useRef<HTMLDivElement>(null);
  const [account, setAccount] = useState<Account | null>(null);
  const [accountOpen, setAccountOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [accountError, setAccountError] = useState<string | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [places, setPlaces] = useState<MapPoint[]>([]);
  const [placesLoading, setPlacesLoading] = useState(false);
  const [placesUnavailable, setPlacesUnavailable] = useState(false);
  const lookupToken = useRef(0);

  useEffect(() => {
    fetchCities()
      .then((loaded) => {
        setCities(loaded);
        setCitiesError(null);
      })
      .catch(() => setCitiesError("Cities could not be loaded. The lookup service is unreachable."));
    if (readToken()) {
      fetchMe()
        .then(setAccount)
        .catch(() => {
          storeToken(null);
          setAccount(null);
        });
    }
  }, []);

  useEffect(() => {
    fetchFacets(cityId)
      .then(setFacets)
      .catch(() => setFacets(EMPTY_FACETS));
  }, [cityId]);

  useEffect(() => {
    let cancelled = false;
    setPlaces([]);
    setPlacesLoading(true);
    setPlacesUnavailable(false);
    fetchMap(cityId)
      .then((rows) => {
        if (!cancelled) setPlaces(rows.map(toMapPoint));
      })
      .catch(() => {
        if (!cancelled) {
          setPlaces([]);
          setPlacesUnavailable(true);
        }
      })
      .finally(() => {
        if (!cancelled) setPlacesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [cityId]);

  useEffect(() => {
    const text = query.trim();
    const filtering = Boolean(filters.area || filters.cuisine || filters.grade || filters.clean);
    if (/^\d+$/.test(text) || (text.length < 2 && !filtering)) {
      setMatches([]);
      setSearching(false);
      if (text.length < 2) setError(null);
      return;
    }
    let cancelled = false;
    setSearching(true);
    const handle = window.setTimeout(() => {
      searchRestaurants(cityId, text, filters)
        .then((hits) => {
          if (cancelled) return;
          setMatches(hits);
          setHighlight(0);
          setError(hits.length === 0 ? "No restaurants match this search." : null);
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
  }, [query, cityId, filters]);

  useEffect(() => {
    setSuggestionsDismissed(false);
  }, [query, cityId, filters]);

  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      if (!queryField.current?.contains(event.target as Node)) setSuggestionsDismissed(true);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, []);

  const selected = cities.find((city) => city.id === cityId) ?? null;
  const nameQuery = query.trim();
  const nameSearch = nameQuery.length >= 2 && !/^\d+$/.test(nameQuery);
  const suggestionsOpen = nameSearch && !suggestionsDismissed;
  const focus = focusPoint(focusId, places, restaurant);
  const focusName = focusedName(focusId, matches, restaurant);

  function chooseCity(nextId: string) {
    lookupToken.current += 1;
    setCityId(nextId);
    setPlaces([]);
    setPlacesLoading(true);
    setPlacesUnavailable(false);
    setRestaurant(null);
    setFocusId(null);
    setError(null);
    setMatches([]);
    setHighlight(0);
    setSuggestionsDismissed(false);
    setFilters(EMPTY_FILTERS);
    setLoading(false);
  }

  async function lookup(id: string) {
    const restaurantId = id.trim();
    if (!restaurantId) {
      setError("Enter a name or id.");
      setRestaurant(null);
      setFocusId(null);
      return;
    }
    const token = ++lookupToken.current;
    setFocusId(restaurantId);
    setLoading(true);
    setError(null);
    try {
      const next = await fetchRestaurant(cityId, restaurantId);
      if (token !== lookupToken.current) return;
      setRestaurant(next);
    } catch (caught) {
      if (token !== lookupToken.current) return;
      setRestaurant(null);
      setError(caught instanceof ApiError ? caught.message : "The lookup could not be completed.");
    } finally {
      if (token === lookupToken.current) setLoading(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = query.trim();
    if (/^\d+$/.test(text)) {
      void lookup(text);
      return;
    }
    if (matches[highlight]) void lookup(matches[highlight].restaurant_id);
  }

  function onQueryKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape") {
      setSuggestionsDismissed(true);
      return;
    }
    if (!suggestionsOpen || matches.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlight((current) => Math.min(matches.length - 1, current + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlight((current) => Math.max(0, current - 1));
    } else if (event.key === "Enter" && matches[highlight]) {
      event.preventDefault();
      setSuggestionsDismissed(true);
      void lookup(matches[highlight].restaurant_id);
    }
  }

  function chooseMatch(restaurantId: string) {
    setSuggestionsDismissed(true);
    void lookup(restaurantId);
  }

  async function onAccount(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "");
    const password = String(form.get("password") ?? "");
    const name = String(form.get("name") ?? "");
    setAccountError(null);
    try {
      const next = creating ? await registerAccount(name, email, password) : await loginAccount(email, password);
      storeToken(next.token);
      setAccount(next);
      setAccountOpen(false);
    } catch (caught) {
      setAccountError(caught instanceof ApiError ? caught.message : "The account could not be saved.");
    }
  }

  function logout() {
    storeToken(null);
    setAccount(null);
  }

  return (
    <main>
      <header className="mast">
        <div className="mast-top">
          <h1 className="wordmark">Nextvisit</h1>
          {account ? (
            <p className="session">
              {account.name}
              <button type="button" className="text-button" onClick={logout}>
                Log out
              </button>
            </p>
          ) : (
            <button type="button" className="text-button" onClick={() => setAccountOpen(true)}>
              Log in
            </button>
          )}
        </div>
        <p className="lede">The inspection record, beside the reviews.</p>
      </header>

      <div className="city-bar">
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
      </div>

      <div className="workspace">
        <form className="finder" onSubmit={onSubmit}>
          <div className="finder-row">
          <div className="query-field" ref={queryField}>
            <label className="query">
              <span>Name or id</span>
              <input
                value={query}
                placeholder={selected?.id === "new_york" ? "Name or CAMIS" : "Name or restaurant id"}
                onChange={(event) => {
                  const next = event.target.value;
                  setQuery(next);
                  const text = next.trim();
                  if (text.length >= 2 && !/^\d+$/.test(text)) setSearching(true);
                }}
                onKeyDown={onQueryKeyDown}
                onFocus={() => setSuggestionsDismissed(false)}
                autoComplete="off"
                spellCheck={false}
                role="combobox"
                aria-autocomplete="list"
                aria-expanded={suggestionsOpen}
                aria-controls="matches"
                aria-activedescendant={
                  suggestionsOpen && matches[highlight] ? `match-${matches[highlight].restaurant_id}` : undefined
                }
              />
            </label>
            {suggestionsOpen ? (
              matches.length > 0 ? (
                <MatchList
                  className="matches dropdown"
                  matches={matches}
                  query={nameQuery}
                  highlight={highlight}
                  onHover={setHighlight}
                  onPick={chooseMatch}
                />
              ) : (
                <p className="suggestion-status" role="status">
                  {searching ? "Searching this city." : "No restaurants match."}
                </p>
              )
            ) : null}
          </div>
            <FilterSelect label="Area" value={filters.area} options={facets.areas} onChange={(area) => setFilters({ ...filters, area })} />
            <FilterSelect
              label="Cuisine"
              value={filters.cuisine}
              options={facets.cuisines}
              onChange={(cuisine) => setFilters({ ...filters, cuisine })}
            />
            <FilterSelect
              label="Recent grade"
              value={filters.grade}
              options={facets.grades}
              onChange={(grade) => setFilters({ ...filters, grade })}
            />
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
          </div>
          <label className="clean-toggle">
            <input
              type="checkbox"
              checked={filters.clean}
              onChange={(event) => setFilters({ ...filters, clean: event.target.checked })}
            />
            Last inspection had no serious violation
          </label>
          {!nameSearch && matches.length > 0 ? (
            <MatchList matches={matches} query={nameQuery} highlight={highlight} onHover={setHighlight} onPick={chooseMatch} />
          ) : null}
        </form>

        <section className="stage" aria-busy={loading}>
          <MapPanel
            cityId={cityId}
            cityName={selected?.name ?? "This city"}
            places={places}
            placesLoading={placesLoading}
            placesUnavailable={placesUnavailable}
            focus={focus}
            focusName={focusName}
            locating={loading}
            onSelect={(id) => void lookup(id)}
          />
          {loading ? <p className="notice">Reading this restaurant's inspection record.</p> : null}
          {!loading && error && matches.length === 0 ? <p className="notice problem">{error}</p> : null}
          {!loading && restaurant ? (
            <ResultCard
              key={`${restaurant.city}-${restaurant.restaurant_id}`}
              restaurant={restaurant}
              signedIn={account !== null}
              onReviews={() => setFilters((current) => ({ ...current }))}
              onLogin={() => setAccountOpen(true)}
            />
          ) : null}
          {!loading && !restaurant && !error && matches.length === 0 ? (
            <div className="idle-stage">
              <p className="idle">Choose a restaurant to see its last inspection and reviews.</p>
            </div>
          ) : null}
        </section>
      </div>

      {accountOpen ? (
        <div className="scrim" role="presentation" onClick={() => setAccountOpen(false)}>
          <form
            className="account-card"
            role="dialog"
            aria-label={creating ? "Create an account" : "Log in"}
            onClick={(event) => event.stopPropagation()}
            onSubmit={onAccount}
          >
            <h2>{creating ? "Create an account" : "Log in"}</h2>
            {creating ? (
              <label>
                Name
                <input name="name" autoComplete="name" required />
              </label>
            ) : null}
            <label>
              Email
              <input name="email" type="email" autoComplete="email" required />
            </label>
            <label>
              Password
              <input name="password" type="password" autoComplete={creating ? "new-password" : "current-password"} required minLength={8} />
            </label>
            {accountError ? <p className="notice problem">{accountError}</p> : null}
            <div className="actions">
              <button className="submit" type="submit">
                {creating ? "Create account" : "Log in"}
              </button>
              <button className="sample" type="button" onClick={() => setCreating((value) => !value)}>
                {creating ? "I already have an account" : "Create an account"}
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </main>
  );
}

function MatchList({
  matches,
  query,
  highlight,
  onHover,
  onPick,
  className = "matches",
}: {
  matches: RestaurantHit[];
  query: string;
  highlight: number;
  onHover: (index: number) => void;
  onPick: (restaurantId: string) => void;
  className?: string;
}) {
  return (
    <ul className={className} id="matches" role="listbox" aria-label="Matching restaurants">
      {matches.map((hit, index) => (
        <li key={hit.restaurant_id}>
          <button
            id={`match-${hit.restaurant_id}`}
            type="button"
            role="option"
            aria-selected={index === highlight}
            className={index === highlight ? "match selected" : "match"}
            onMouseDown={(event) => event.preventDefault()}
            onMouseEnter={() => onHover(index)}
            onClick={() => onPick(hit.restaurant_id)}
          >
            <strong>{highlightMatch(hit.name, query)}</strong>
            {hit.address ? <em className="street">{hit.address}</em> : null}
            <span>
              {[hit.grade, hit.area, hit.review_count ? `${hit.average_stars?.toFixed(1)} · ${hit.review_count} reviews` : null]
                .filter(Boolean)
                .join(" · ")}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function highlightMatch(name: string, query: string) {
  const needle = query.trim();
  const at = name.toLocaleLowerCase().indexOf(needle.toLocaleLowerCase());
  if (at < 0 || needle.length < 2) return name;
  return (
    <>
      {name.slice(0, at)}
      <mark>{name.slice(at, at + needle.length)}</mark>
      {name.slice(at + needle.length)}
    </>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="filter">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">Any</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </label>
  );
}

function toMapPoint(place: MapPlace): MapPoint {
  return {
    id: place.restaurant_id,
    name: place.name,
    address: place.address,
    latitude: place.latitude,
    longitude: place.longitude,
  };
}

function focusPoint(focusId: string | null, places: MapPoint[], restaurant: Restaurant | null): MapPoint | null {
  if (!focusId) return null;
  if (restaurant?.restaurant_id === focusId && restaurant.latitude != null && restaurant.longitude != null) {
    return {
      id: restaurant.restaurant_id,
      name: restaurant.name ?? restaurant.restaurant_id,
      address: restaurant.address,
      latitude: restaurant.latitude,
      longitude: restaurant.longitude,
    };
  }
  return places.find((place) => place.id === focusId) ?? null;
}

function focusedName(focusId: string | null, matches: RestaurantHit[], restaurant: Restaurant | null): string | null {
  if (!focusId) return null;
  if (restaurant?.restaurant_id === focusId) return restaurant.name ?? restaurant.restaurant_id;
  return matches.find((hit) => hit.restaurant_id === focusId)?.name ?? focusId;
}
