import {
  confidenceLabel,
  confidencePercent,
  confidenceTone,
} from "../../utils/confidence.js";

export default function ConfidenceBadge({ value }) {
  const tone = confidenceTone(value);

  return (
    <span className={`confidence-badge confidence-badge--${tone}`}>
      {confidenceLabel(value)}
      {value !== null && value !== undefined ? ` (${confidencePercent(value)})` : ""}
    </span>
  );
}
