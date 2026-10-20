import { useEffect, useState } from "react";
import type { Restaurant } from "./api";
import { WorkOrder } from "./WorkOrder";

type ResultCardProps = {
  restaurant: Restaurant;
  hasWorkOrder: boolean;
  activeCode: string | null;
  onToggleCode: (code: string) => void;
};

export function ResultCard({ restaurant, hasWorkOrder, activeCode, onToggleCode }: ResultCardProps) {
  useEffect(() => {
    if (!activeCode) return;
    document.getElementById(`step-${activeCode}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [activeCode]);

  if (restaurant.abstained || restaurant.probability === null) {
    return (
      <article className="result abstained" aria-live="polite">
        <p className="eyebrow">No score</p>
        <h2>{restaurant.name ?? "This restaurant"}</h2>
        {restaurant.address ? <p className="street">{restaurant.address}</p> : null}
        <p className="abstain-line">No score. This restaurant has no completed inspection to learn from.</p>
        <p className="meta">{restaurant.restaurant_id}</p>
      </article>
    );
  }

  return (
    <article className="result" aria-live="polite">
      <div className="result-top">
        <Gauge probability={restaurant.probability} />
        <div>
          {restaurant.cuisine ? <p className="eyebrow">{restaurant.cuisine}</p> : null}
          <h2>{restaurant.name ?? restaurant.restaurant_id}</h2>
          {restaurant.address ? <p className="street">{restaurant.address}</p> : null}
          <p className="label-sentence">{restaurant.label}</p>
          <p className="meta">
            {restaurant.restaurant_id}
            <span>Exact probability {restaurant.probability.toFixed(4)}</span>
          </p>
        </div>
      </div>
      {restaurant.codes.length > 0 ? (
      <section className="codes" aria-label="Violation codes">
        <header>
          <h3>Codes in the history</h3>
          <p>
            {restaurant.work_order.length > 0
              ? "The city's wording. Select a code to find its closing step."
              : "The city's wording for each code already on the record."}
          </p>
        </header>
        <div className="code-list">
          {restaurant.codes.map((item) => (
            <button
              key={item.code}
              type="button"
              className={activeCode === item.code ? "code active" : "code"}
              aria-pressed={activeCode === item.code}
              onClick={() => onToggleCode(item.code)}
            >
              <strong>{item.code}</strong>
              <span>{item.description ?? "This city did not publish wording for this code."}</span>
            </button>
          ))}
        </div>
      </section>
      ) : null}
      <WorkOrder
        items={restaurant.work_order}
        hasWorkOrder={hasWorkOrder}
        reason={restaurant.work_order_reason}
        activeCode={activeCode}
      />
    </article>
  );
}

function Gauge({ probability }: { probability: number }) {
  const radius = 58;
  const circumference = 2 * Math.PI * radius;
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      setShown(clamp(probability));
      return;
    }
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const progress = Math.min(1, (now - start) / 780);
      const eased = 1 - (1 - progress) ** 3;
      setShown(clamp(probability) * eased);
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [probability]);
  const tone = probability >= 0.75 ? "high" : probability >= 0.45 ? "mid" : "low";
  const caption = tone === "high" ? "Higher on this city's scale" : tone === "mid" ? "Middle of this city's scale" : "Lower on this city's scale";
  return (
    <div className={`gauge ${tone}`}>
      <svg viewBox="0 0 140 140" aria-hidden="true">
        <circle cx="70" cy="70" r={radius} />
        <circle
          className="value"
          cx="70"
          cy="70"
          r={radius}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - shown)}
        />
      </svg>
      <strong>{formatPercent(shown)}</strong>
      <em>{caption}</em>
    </div>
  );
}

function formatPercent(probability: number): string {
  return `${(Math.round(probability * 1000) / 10).toFixed(1)}%`;
}

function clamp(value: number): number {
  return Math.min(1, Math.max(0, value));
}
