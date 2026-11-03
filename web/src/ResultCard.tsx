import { useState } from "react";
import type { CleanerPeer, Restaurant } from "./api";
import { codeIntro, distanceLabel, inspectionAge, inspectionDateLabel, peerSentence, readCode, scaleCaption, scoreTrendSentence, statusSentence, trendSentence } from "./reading";
import { Reviews } from "./Reviews";

const CODE_PREVIEW = 6;

type ResultCardProps = {
  restaurant: Restaurant;
  signedIn: boolean;
  onReviews: () => void;
  onLogin: () => void;
  onOpen?: (peer: CleanerPeer) => void;
};

export function ResultCard({ restaurant, signedIn, onReviews, onLogin, onOpen }: ResultCardProps) {
  const [codesOpen, setCodesOpen] = useState(false);
  const status = statusSentence(restaurant.city, restaurant.serious);
  const age = inspectionAge(restaurant.last_inspection_date);
  const inspectedOn = inspectionDateLabel(restaurant.last_inspection_date);
  const trend = restaurant.city === "austin"
    ? scoreTrendSentence(restaurant.score_trend)
    : trendSentence(restaurant.trend, restaurant.recent_visit_count, restaurant.recent_serious_count);
  const trendClass = restaurant.city === "austin"
    ? restaurant.score_trend === "falling"
      ? "trend-worse"
      : restaurant.score_trend === "rising"
        ? "trend-cleaner"
        : "trend-steady"
    : `trend-${restaurant.trend}`;
  const cleaner = restaurant.cleaner_peers ?? [];
  const peers = peerSentence(
    restaurant.cuisine,
    restaurant.area,
    restaurant.grade,
    restaurant.peer_count,
    restaurant.peer_graded_count,
    restaurant.peer_standing,
  );
  const visibleCodes = codesOpen ? restaurant.codes : restaurant.codes.slice(0, CODE_PREVIEW);
  const hiddenCodes = restaurant.codes.length - visibleCodes.length;
  const intro = codeIntro(restaurant.city);
  const scale = restaurant.grade || restaurant.score != null ? scaleCaption(restaurant.city) : null;
  const rows: { label: string; value: string; className?: string }[] = [
    restaurant.grade ? { label: "Grade", value: restaurant.grade } : null,
    restaurant.score != null ? { label: "Score", value: String(restaurant.score) } : null,
    inspectedOn ? { label: "Date", value: inspectedOn } : null,
    age ? { label: "Age", value: age } : null,
    status ? { label: "Result", value: status, className: restaurant.serious ? "serious" : "clean-line" } : null,
    trend ? { label: "Recent visits", value: trend, className: `inspection-trend ${trendClass}` } : null,
    restaurant.area ? { label: "Area", value: restaurant.area } : null,
    restaurant.hours ? { label: "Hours", value: restaurant.hours } : null,
  ].filter((row) => row != null);
  return (
    <article className="result" aria-live="polite">
      {restaurant.cuisine ? <p className="eyebrow">{restaurant.cuisine}</p> : null}
      <h2>{restaurant.name ?? restaurant.restaurant_id}</h2>
      {restaurant.address ? <p className="street">{restaurant.address}</p> : null}
      {rows.length > 0 || peers || cleaner.length > 0 ? (
        <section className="reading" aria-label="Inspection record">
          {rows.length > 0 ? (
            <>
              <h3>Last inspection</h3>
              <dl className="facts">
                {rows.map((row) => (
                  <div key={row.label}>
                    <dt>{row.label}</dt>
                    <dd className={row.className}>{row.value}</dd>
                  </div>
                ))}
              </dl>
            </>
          ) : null}
          {peers || cleaner.length > 0 ? (
            <>
              <h3>Nearby</h3>
              {peers ? (
                <p className={`inspection-peer standing-${restaurant.peer_standing ?? "count"}`}>{peers}</p>
              ) : null}
              {cleaner.length > 0 ? (
                <>
                <p className="cleaner-lead">
                  {restaurant.nearby_basis === "closest"
                    ? "The closest places with a last inspection at least as good."
                    : "The next inspection looks cleaner at these places."}
                </p>
                <ul className="cleaner-peers">
                  {cleaner.map((peer) => {
                    const distance = distanceLabel(peer.distance_miles);
                    return (
                      <li key={peer.restaurant_id}>
                        <button type="button" onClick={() => onOpen?.(peer)}>
                          <span className="peer-name">
                            <span>{peer.name}</span>
                            {peer.address ? <small>{peer.address}</small> : null}
                          </span>
                          <span className="peer-facts">
                            {peer.grade ? <strong>{peer.grade}</strong> : null}
                            {distance ? <em>{distance}</em> : null}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
                </>
              ) : null}
            </>
          ) : null}
        </section>
      ) : null}
      {scale ? <p className="scale">{scale}</p> : null}
      {restaurant.visits?.length ? (
        <section className="history" aria-label="Inspection history">
          <h3>Inspection history</h3>
          {restaurant.history ? <p>{restaurant.history}</p> : null}
          <ol>
            {restaurant.visits.map((visit, index) => (
              <li key={`${visit.date}-${index}`}>
                <span>{inspectionDateLabel(visit.date) ?? visit.date}</span>
                {visit.grade ? <strong>{visit.grade}</strong> : null}
                {visit.score != null ? <span>{Number.isInteger(visit.score) ? visit.score : visit.score.toFixed(0)}</span> : null}
                {restaurant.city !== "austin" && visit.codes.length ? (
                  <span className="history-codes">{visit.codes.map((item) => item.code).join(", ")}</span>
                ) : null}
              </li>
            ))}
          </ol>
          {restaurant.earlier_inspections > 0 ? (
            <p className="earlier">
              {restaurant.earlier_inspections === 1
                ? "1 earlier inspection on file is not listed."
                : `${restaurant.earlier_inspections} earlier inspections on file are not listed.`}
            </p>
          ) : null}
        </section>
      ) : null}
      {restaurant.city === "austin" ? null : (
      <section className="codes" aria-label="Violation codes">
        <header>
          <h3>Violation codes</h3>
        </header>
        {restaurant.code_summary ? <p className="code-summary">{restaurant.code_summary}</p> : null}
        {intro && restaurant.codes.length > 0 ? <p className="code-intro">{intro}</p> : null}
        {restaurant.codes.length > 0 ? (
          <div className="code-list">
            {visibleCodes.map((item) => {
              const reading = readCode(item.description);
              return (
                <article key={item.code} className="code-note">
                  <strong>{item.code}</strong>
                  <div>
                    <p className="topic">{reading.topic}</p>
                    <p className="code-plain">{reading.plain}</p>
                    {item.description ? <p className="code-official">{item.description}</p> : null}
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <p className="empty-order">This record has no violation codes.</p>
        )}
        {hiddenCodes > 0 ? (
          <button type="button" className="text-button more-codes" onClick={() => setCodesOpen(true)}>
            Show {hiddenCodes} more codes
          </button>
        ) : null}
      </section>
      )}
      <Reviews
        cityId={restaurant.city}
        restaurantId={restaurant.restaurant_id}
        signedIn={signedIn}
        onChange={onReviews}
        onLogin={onLogin}
      />
    </article>
  );
}
