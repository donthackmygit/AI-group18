const TECHNICAL_REPLACEMENTS = {
  gross_income: "thu nhập chịu thuế",
  tax_exempt_income: "thu nhập được miễn thuế",
  mandatory_insurance: "bảo hiểm bắt buộc",
  personal_deduction: "giảm trừ bản thân",
  dependent_deduction: "giảm trừ người phụ thuộc",
  charity_contributions: "khoản đóng góp từ thiện",
  other_deductions: "khoản giảm trừ khác",
  taxable_income: "thu nhập tính thuế",
  tax_amount: "số thuế phải nộp",
};

function naturalizeStep(step) {
  let text = String(step || "").trim();

  for (const [technicalName, vietnameseName] of Object.entries(TECHNICAL_REPLACEMENTS)) {
    text = text.replaceAll(technicalName, vietnameseName);
  }

  text = text.replaceAll(
    "Gross taxable salary/wage income",
    "Thu nhập tiền lương, tiền công chịu thuế"
  );
  text = text.replaceAll(
    "Taxable income after deductions",
    "Thu nhập tính thuế sau khi trừ các khoản giảm trừ"
  );
  text = text.replaceAll(
    "Personal income tax by progressive brackets",
    "Số thuế TNCN phải nộp theo biểu thuế lũy tiến từng phần"
  );
  text = text.replaceAll(
    "Non-resident salary/wage taxable income",
    "Thu nhập chịu thuế của cá nhân không cư trú"
  );
  text = text.replaceAll(
    "Flat-rate tax for non-resident salary/wage income",
    "Số thuế TNCN phải nộp theo thuế suất toàn phần"
  );
  text = text.replaceAll(
    "Short-term/no-contract taxable payment",
    "Thu nhập chịu khấu trừ đối với hợp đồng ngắn hạn hoặc không có hợp đồng"
  );
  text = text.replaceAll(
    "Withholding tax for short-term/no-contract resident income",
    "Số thuế tạm khấu trừ"
  );

  return text;
}

export default function CalculationSteps({ steps }) {
  if (!steps.length) {
    return null;
  }

  return (
    <ol className="calculation-steps">
      {steps.map((step, index) => (
        <li key={`${step}-${index}`}>{naturalizeStep(step)}</li>
      ))}
    </ol>
  );
}