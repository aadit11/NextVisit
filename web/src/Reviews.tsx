import { useEffect, useState, type FormEvent } from "react";
import { ApiError, fetchReviews, saveReview, type ReviewList } from "./api";

type ReviewsProps = {
  cityId: string;
  restaurantId: string;
  signedIn: boolean;
  onChange: () => void;
  onLogin: () => void;
};

export function Reviews({ cityId, restaurantId, signedIn, onChange, onLogin }: ReviewsProps) {
  const [list, setList] = useState<ReviewList | null>(null);
  const [stars, setStars] = useState(0);
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchReviews(cityId, restaurantId)
      .then((loaded) => {
        if (cancelled) return;
        setList(loaded);
        setStars((current) => loaded.mine?.stars ?? (current > 0 ? current : 0));
        setComment((current) => loaded.mine?.comment || current);
      })
      .catch((caught: unknown) => {
        if (!cancelled) setError(caught instanceof ApiError ? caught.message : "Reviews could not be loaded.");
      });
    return () => {
      cancelled = true;
    };
  }, [cityId, restaurantId, signedIn]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!signedIn) {
      onLogin();
      return;
    }
    if (stars < 1) {
      setError("Choose a star rating.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await saveReview(cityId, restaurantId, stars, comment);
      setList(saved);
      onChange();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The review could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="reviews" aria-label="Reviews">
      <header>
        <h3>Reviews</h3>
        <p>{list && list.review_count > 0 ? `${list.average_stars?.toFixed(1)} from ${list.review_count}` : "No reviews yet."}</p>
      </header>
      <form onSubmit={onSubmit}>
        <div className="stars" role="radiogroup" aria-label="Star rating">
          {[1, 2, 3, 4, 5].map((value) => (
            <button
              key={value}
              type="button"
              className={value <= stars ? "star on" : "star"}
              aria-checked={stars === value}
              role="radio"
              onClick={() => setStars(value)}
            >
              {value}
            </button>
          ))}
        </div>
        <textarea
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          maxLength={800}
          rows={3}
          placeholder="What should the next diner know?"
        />
        {error ? <p className="notice problem">{error}</p> : null}
        <button className="submit" type="submit" disabled={saving}>
          {saving ? "Saving" : signedIn ? (list?.mine ? "Update your review" : "Publish review") : "Log in to review"}
        </button>
      </form>
      {list && list.reviews.length > 0 ? (
        <ul className="review-list">
          {list.reviews.map((review) => (
            <li key={`${review.author}-${review.created_at}`}>
              <strong>
                {review.author} · {review.stars} star{review.stars === 1 ? "" : "s"}
              </strong>
              {review.comment ? <p>{review.comment}</p> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
