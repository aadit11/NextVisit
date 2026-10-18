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
  if (restaurant.abstained || restaurant.probability === null) {
    return (
      <article className="result abstained" aria-live="polite">
        <p className="eyebrow">No score</p>
        <h2>{restaurant.name ?? "This restaurant"}</h2>
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
              ? "Select a code to find its closing step."
              : "Taken from inspections already on the record."}
          </p>
        </header>
        <div className="code-row">
          {restaurant.codes.map((code) => (
            <button
              key={code}
              type="button"
              className={activeCode === code ? "code active" : "code"}
              aria-pressed={activeCode === code}
              onClick={() => onToggleCode(code)}
            >
              {code}
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
  const [offset, setOffset] = useState(circumference);
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      setOffset(circumference * (1 - clamp(probability)));
    });
    return () => cancelAnimationFrame(frame);
  }, [circumference, probability]);
  const tone = probability >= 0.75 ? "high" : probability >= 0.45 ? "mid" : "low";
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
          strokeDashoffset={offset}
        />
      </svg>
      <strong>{formatPercent(probability)}</strong>
    </div>
  );
}

function formatPercent(probability: number): string {
  return `${(Math.round(probability * 1000) / 10).toFixed(1)}%`;
}

function clamp(value: number): number {
  return Math.min(1, Math.max(0, value));
}
