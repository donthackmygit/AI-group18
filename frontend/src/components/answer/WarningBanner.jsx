export default function WarningBanner({ warning, tone = "warning" }) {
  if (!warning) {
    return null;
  }

  return <div className={`warning-banner warning-banner--${tone}`}>{warning}</div>;
}
