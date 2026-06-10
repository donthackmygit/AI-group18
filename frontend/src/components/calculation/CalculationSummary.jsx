import { formatMoney } from "../../utils/formatMoney.js";
import CalculationSteps from "./CalculationSteps.jsx";

export default function CalculationSummary({ calculation }) {
  if (!calculation) {
    return null;
  }

  const metrics = [
    ["Thu nhập tính thuế", calculation.taxable_income],
    ["Giảm trừ bản thân", calculation.personal_deduction],
    ["Giảm trừ người phụ thuộc", calculation.dependent_deduction],
    ["Số thuế phải nộp", calculation.tax_amount],
  ];

  return (
    <section className="calculation-section">
      <div className="section-heading">
        <h3>Kết quả tính thuế</h3>
        {calculation.missing_fields?.length ? (
          <span>Thiếu {calculation.missing_fields.length} trường</span>
        ) : null}
      </div>

      <div className="calculation-grid">
        {metrics.map(([label, value]) => (
          <div key={label} className="calculation-metric">
            <span>{label}</span>
            <strong>{formatMoney(value)}</strong>
          </div>
        ))}
      </div>

      <CalculationSteps steps={calculation.calculation_steps || []} />

      {calculation.missing_fields?.length ? (
        <div className="missing-fields">
          Cần bổ sung: {calculation.missing_fields.join(", ")}
        </div>
      ) : null}
    </section>
  );
}
