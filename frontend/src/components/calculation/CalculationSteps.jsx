export default function CalculationSteps({ steps }) {
  if (!steps.length) {
    return null;
  }

  return (
    <ol className="calculation-steps">
      {steps.map((step, index) => (
        <li key={`${step}-${index}`}>{step}</li>
      ))}
    </ol>
  );
}
