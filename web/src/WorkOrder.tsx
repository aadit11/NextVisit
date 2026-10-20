import type { WorkOrderItem } from "./api";

const STATIONS: Record<string, string> = {
  cold_holding: "Cold holding",
  hot_holding: "Hot holding",
  handwashing: "Handwashing",
  food_contact: "Food contact",
  pests: "Pests",
  plumbing: "Plumbing",
  supervision: "Supervision",
  other: "Other",
};

type WorkOrderProps = {
  items: WorkOrderItem[];
  hasWorkOrder: boolean;
  reason: string | null;
  activeCode: string | null;
};

export function WorkOrder({ items, hasWorkOrder, reason, activeCode }: WorkOrderProps) {
  return (
    <section className="work-order" aria-label="Closing list">
      <header>
        <h2>Closing list</h2>
        <p>
          {items.length > 0
            ? "One step for each code, quoting the official text."
            : hasWorkOrder
              ? "The score stands without a closing list."
              : "Scores only."}
        </p>
      </header>
      {items.length > 0 ? (
        <ol>
          {items.map((item) => (
            <li
              id={`step-${item.violation_code}`}
              key={item.violation_code}
              className={
                activeCode === item.violation_code ? "lit" : activeCode ? "dimmed" : undefined
              }
            >
              <div className="step-meta">
                <span>{STATIONS[item.station] ?? item.station}</span>
                <code>{item.violation_code}</code>
              </div>
              <StepText step={item.step} span={item.source_span} />
            </li>
          ))}
        </ol>
      ) : (
        <EmptyOrder hasWorkOrder={hasWorkOrder} reason={reason} />
      )}
    </section>
  );
}

function EmptyOrder({ hasWorkOrder, reason }: { hasWorkOrder: boolean; reason: string | null }) {
  if (!hasWorkOrder) {
    return (
      <p className="empty-order">
        This city publishes a score only. The closing list stays empty, and that is a finished result.
      </p>
    );
  }
  if (reason) {
    return <p className="empty-order">{reason}</p>;
  }
  return <p className="empty-order">No closing steps were returned for this restaurant.</p>;
}

function StepText({ step, span }: { step: string; span: string }) {
  const index = span ? step.indexOf(span) : -1;
  if (index < 0) {
    return <p>{step}</p>;
  }
  return (
    <p>
      {step.slice(0, index)}
      <mark>{span}</mark>
      {step.slice(index + span.length)}
    </p>
  );
}
