import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

export type MapPoint = {
  id: string;
  name: string;
  address: string | null;
  latitude: number;
  longitude: number;
};

type CityView = {
  latitude: number;
  longitude: number;
  zoom: number;
};

const CITY_VIEWS: Record<string, CityView> = {
  new_york: { latitude: 40.73, longitude: -73.99, zoom: 11 },
  chicago: { latitude: 41.8781, longitude: -87.6298, zoom: 11 },
  king_county: { latitude: 47.548, longitude: -121.983, zoom: 9 },
  los_angeles: { latitude: 34.05, longitude: -118.25, zoom: 9 },
  boston: { latitude: 42.3601, longitude: -71.0589, zoom: 12 },
  san_francisco: { latitude: 37.7749, longitude: -122.4194, zoom: 12 },
  austin: { latitude: 30.2672, longitude: -97.7431, zoom: 11 },
};

const PLACE_STYLE: L.CircleMarkerOptions = {
  radius: 4,
  color: "#0f6b50",
  weight: 1,
  fillColor: "#0f6b50",
  fillOpacity: 0.7,
};

const FOCUS_STYLE: L.CircleMarkerOptions = {
  radius: 11,
  color: "#8d3418",
  weight: 2,
  fillColor: "#b8612e",
  fillOpacity: 0.95,
};

type MapPanelProps = {
  cityId: string;
  cityName: string;
  places: MapPoint[];
  placesLoading: boolean;
  placesUnavailable: boolean;
  focus: MapPoint | null;
  focusName: string | null;
  locating: boolean;
  onSelect: (id: string) => void;
};

export function MapPanel({
  cityId,
  cityName,
  places,
  placesLoading,
  placesUnavailable,
  focus,
  focusName,
  locating,
  onSelect,
}: MapPanelProps) {
  const node = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const placesLayerRef = useRef<L.LayerGroup | null>(null);
  const focusLayerRef = useRef<L.LayerGroup | null>(null);
  const placesRef = useRef(places);
  const focusRef = useRef(focus);
  const onSelectRef = useRef(onSelect);
  placesRef.current = places;
  focusRef.current = focus;
  onSelectRef.current = onSelect;

  const placesKey = `${cityId}:${places.length}:${places[0]?.id ?? ""}`;
  const focusKey = focus ? `${focus.id}:${focus.latitude.toFixed(5)}:${focus.longitude.toFixed(5)}` : "";

  useEffect(() => {
    const host = node.current;
    if (!host) return;
    const view = CITY_VIEWS[cityId] ?? CITY_VIEWS.new_york;
    const map = L.map(host, { preferCanvas: true, scrollWheelZoom: false }).setView(
      [view.latitude, view.longitude],
      view.zoom,
    );
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap",
      maxZoom: 19,
    }).addTo(map);
    placesLayerRef.current = L.layerGroup().addTo(map);
    focusLayerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;
    let fitted = "";
    const fitToHost = () => {
      const size = `${host.clientWidth}x${host.clientHeight}`;
      map.invalidateSize();
      if (size === fitted || focusRef.current) return;
      fitted = size;
      const current = placesRef.current;
      if (current.length > 0) {
        map.fitBounds(boundsOf(current), { padding: [24, 24], maxZoom: 13, animate: false });
      }
    };
    const observer = new ResizeObserver(fitToHost);
    observer.observe(host);
    return () => {
      observer.disconnect();
      map.remove();
      mapRef.current = null;
      placesLayerRef.current = null;
      focusLayerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const layer = placesLayerRef.current;
    if (!layer) return;
    layer.clearLayers();
    for (const place of placesRef.current) {
      const marker = L.circleMarker([place.latitude, place.longitude], PLACE_STYLE);
      marker.on("click", () => {
        onSelectRef.current(place.id);
        marker.bindPopup(popupNode(place), { className: "place-popup", closeButton: false }).openPopup();
      });
      marker.addTo(layer);
    }
  }, [placesKey]);

  useEffect(() => {
    const map = mapRef.current;
    const layer = focusLayerRef.current;
    if (!map || !layer) return;
    layer.clearLayers();
    const selected = focusRef.current;
    const current = placesRef.current;
    if (selected) {
      const marker = L.circleMarker([selected.latitude, selected.longitude], FOCUS_STYLE);
      marker.bindPopup(popupNode(selected), { className: "place-popup", closeButton: false });
      marker.on("click", () => onSelectRef.current(selected.id));
      marker.addTo(layer);
      marker.openPopup();
      map.flyTo([selected.latitude, selected.longitude], 16, { duration: 0.6 });
    } else if (current.length > 0) {
      map.fitBounds(boundsOf(current), { padding: [24, 24], maxZoom: 13 });
    } else if (!placesLoading) {
      const view = CITY_VIEWS[cityId] ?? CITY_VIEWS.new_york;
      map.flyTo([view.latitude, view.longitude], view.zoom, { duration: 0.6 });
    }
    const frame = window.setTimeout(() => map.invalidateSize(), 80);
    return () => window.clearTimeout(frame);
  }, [placesKey, focusKey, cityId, placesLoading]);

  const caption = mapCaption({
    cityName,
    places: places.length,
    placesLoading,
    placesUnavailable,
    focus,
    focusName,
    locating,
  });

  return (
    <div className="map-wrap">
      <div ref={node} className="map" role="region" aria-label={caption} />
      <p className="map-caption">{caption}</p>
    </div>
  );
}

function boundsOf(places: MapPoint[]): L.LatLngBounds {
  let south = 90;
  let north = -90;
  let west = 180;
  let east = -180;
  for (const place of places) {
    if (place.latitude < south) south = place.latitude;
    if (place.latitude > north) north = place.latitude;
    if (place.longitude < west) west = place.longitude;
    if (place.longitude > east) east = place.longitude;
  }
  return L.latLngBounds([south, west], [north, east]);
}

function mapCaption({
  cityName,
  places,
  placesLoading,
  placesUnavailable,
  focus,
  focusName,
  locating,
}: {
  cityName: string;
  places: number;
  placesLoading: boolean;
  placesUnavailable: boolean;
  focus: MapPoint | null;
  focusName: string | null;
  locating: boolean;
}): string {
  if (focus) return `${focus.name}, pinned on the map. ${places.toLocaleString()} places in ${cityName}.`;
  if (focusName && locating) return `Finding ${focusName} in ${cityName}.`;
  if (focusName) return `${focusName} has no published map point. ${placeCount(places, cityName)}`;
  if (placesLoading) return `Loading restaurants in ${cityName}.`;
  if (placesUnavailable) return `Restaurant locations for ${cityName} could not be loaded.`;
  if (places === 0) {
    return `${cityName} does not publish coordinates for these restaurants, so they cannot be pinned.`;
  }
  return placeCount(places, cityName);
}

function placeCount(places: number, cityName: string): string {
  if (places === 0) return `No places are pinned in ${cityName}.`;
  return places === 1 ? `1 place in ${cityName}.` : `${places.toLocaleString()} places in ${cityName}.`;
}

function popupNode(point: MapPoint): HTMLElement {
  const root = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = point.name;
  root.append(title);
  if (point.address) {
    const line = document.createElement("span");
    line.textContent = point.address;
    root.append(line);
  }
  return root;
}
