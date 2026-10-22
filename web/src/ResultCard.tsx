import { useState } from "react";
import type { Restaurant } from "./api";
import { codeIntro, decisionSentence, inspectionAge, peerSentence, readCode, recordGuide, scoreTrendSentence, statusSentence, trendSentence } from "./reading";
import { Reviews } from "./Reviews";

const CODE_PREVIEW = 6;

type ResultCardProps = {
  restaurant: Restaurant;
  signedIn: boolean;
  onReviews: () => void;
  onLogin: () => void;
};

export function ResultCard({ restaurant, signedIn, onReviews, onLogin }: ResultCardProps) {
  const [codesOpen, setCodesOpen] = useState(false);
  const facts = [
    restaurant.grade,
    restaurant.last_inspection_date,
    restaurant.score != null ? `Score ${restaurant.score}` : null,
  ].filter(Boolean);
  const status = statusSentence(restaurant.city, restaurant.serious);
  const age = inspectionAge(restaurant.last_inspection_date);
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
  const decision = decisionSentence(restaurant);
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
  return (
    <article className="result" aria-live="polite">
      {restaurant.cuisine ? <p className="eyebrow">{restaurant.cuisine}</p> : null}
      <h2>{restaurant.name ?? restaurant.restaurant_id}</h2>
      {restaurant.address ? <p className="street">{restaurant.address}</p> : null}
      {restaurant.hours ? <p className="hours">Hours {restaurant.hours}</p> : null}
      {facts.length > 0 ? <p className="meta">{facts.join(" · ")}</p> : null}
      {status ? <p className={restaurant.serious ? "serious" : "clean-line"}>{status}</p> : null}
      <section className="reading" aria-label="How to read this record">
        <h3>Last inspection</h3>
        {age ? <p className="inspection-age">{age}</p> : null}
        {trend ? <p className={`inspection-trend ${trendClass}`}>{trend}</p> : null}
        {peers ? (
          <>
            <h3>Nearby</h3>
            <p className={`inspection-peer standing-${restaurant.peer_standing ?? "count"}`}>{peers}</p>
          </>
        ) : null}
        <p>{recordGuide(restaurant.city)}</p>
        {decision ? (
          <>
            <h3>Next inspection</h3>
            <p className={restaurant.probability != null && restaurant.probability >= 0.5 ? "serious" : "clean-line"}>{decision}</p>
          </>
        ) : null}
      </section>
      {restaurant.brief ? (
        <section className="brief" aria-label="Hygiene brief">
          <h3>Hygiene brief</h3>
          <p>{restaurant.brief}</p>
        </section>
      ) : null}
      <p className="osm-note">OpenStreetMap supplies hours, and cuisine when the city file has none.</p>
      <section className="codes" aria-label="Violation codes">
        <header>
          <h3>Violation codes</h3>
        </header>
        <p className="code-intro">{codeIntro(restaurant.city)}</p>
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
                    {item.description ? (
                      <p className="code-official">
                        <span>Department wording</span>
                        {item.description}
                      </p>
                    ) : null}
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
