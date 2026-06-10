export function confidenceLabel(value) {
  if (value === null || value === undefined) {
    return "Chưa có độ tin cậy";
  }
  if (value >= 0.85) {
    return "Độ tin cậy cao";
  }
  if (value >= 0.65) {
    return "Độ tin cậy khá";
  }
  if (value >= 0.35) {
    return "Cần kiểm tra thêm";
  }
  return "Độ tin cậy thấp";
}

export function confidencePercent(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return `${Math.round(Number(value) * 100)}%`;
}

export function confidenceTone(value) {
  if (value === null || value === undefined) {
    return "neutral";
  }
  if (value >= 0.85) {
    return "good";
  }
  if (value >= 0.65) {
    return "medium";
  }
  return "low";
}
