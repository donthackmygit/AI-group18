export function formatMoney(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "Chưa có";
  }
  return `${Number(value).toLocaleString("vi-VN")} VND`;
}
