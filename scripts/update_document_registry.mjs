import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, "..");
const candidatesPath = path.join(projectRoot, "data", "metadata", "registry_candidates.json");
const registryPath = path.join(projectRoot, "data", "metadata", "document_registry.xlsx");

const headers = [
  "document_id",
  "file_name",
  "title",
  "document_number",
  "document_type",
  "issuing_authority",
  "issue_date",
  "effective_date",
  "expiry_date",
  "status",
  "source_type",
  "source_url",
  "local_path",
  "download_date",
  "topics",
  "version",
  "notes",
];

const schemaRows = [
  ["document_id", "yes", "Ma tai lieu duy nhat, vi du LAW_04_2007_QH12 hoac TT_111_2013_BTC."],
  ["file_name", "yes", "Ten file goc dat trong data/raw theo nhom van ban."],
  ["title", "yes", "Ten day du cua van ban phap luat hoac tai lieu huong dan."],
  ["document_number", "yes", "So hieu van ban, vi du 111/2013/TT-BTC."],
  ["document_type", "yes", "Luat, Nghi dinh, Thong tu, Thong tu lien tich, Nghi quyet, Cong van, Chi thi."],
  ["issuing_authority", "yes", "Co quan ban hanh, vi du Quoc hoi, Chinh phu, Bo Tai chinh, Tong cuc Thue."],
  ["issue_date", "yes", "Ngay ban hanh theo dinh dang yyyy-mm-dd."],
  ["effective_date", "yes", "Ngay co hieu luc theo dinh dang yyyy-mm-dd; voi cong van dung ngay ban hanh lam moc tham chieu neu co."],
  ["expiry_date", "no", "Ngay het hieu luc neu co; de trong neu chua xac dinh."],
  ["status", "yes", "Trang thai: effective, expired, not_yet_effective, partially_effective, replaced."],
  ["source_type", "yes", "Loai nguon: official, trusted_secondary, internal. Uu tien official."],
  ["source_url", "no", "URL nguon tai hoac trang cong bo chinh thuc. De trong neu chua xac dinh URL tai ve ban dau."],
  ["local_path", "yes", "Duong dan tuong doi trong du an, vi du data/raw/circulars/111-2013-TT-BTC.pdf."],
  ["download_date", "yes", "Ngay tai ve theo dinh dang yyyy-mm-dd."],
  ["topics", "no", "Danh sach chu de ngan cach bang dau cham phay, vi du thue thu nhap ca nhan; quyet toan thue."],
  ["version", "yes", "So phien ban registry cua tai lieu, bat dau tu 1."],
  ["notes", "no", "Ghi chu ve pham vi, thay the, hop nhat, dieu khoan can chu y."],
];

const authoritativeUrls = {
  "109-2025-QH15-Luat-TNCN.pdf": "https://congbao.chinhphu.vn/van-ban/luat-so-109-2025-qh15-468671.htm",
  "111-2013-TT-BTC.pdf": "https://congbao.chinhphu.vn/tai-ve-van-ban-so-111-2013-tt-btc-7822-4293?format=pdf",
  "119-2014-TT-BTC.pdf": "https://congbao.chinhphu.vn/so-do-van-ban-so-119-2014-tt-btc-8161",
  "151-2014-TT-BTC.pdf": "https://congbao.chinhphu.vn/van-ban/thong-tu-so-151-2014-tt-btc-8162.htm",
  "20-1010-TT-BTC.pdf": "https://vbpl.vn/TW/Pages/vbpq-thuoctinh.aspx?ItemID=25012",
  "206-2013-TTLT-BTC-BCA.pdf": "https://chinhphu.vn/default.aspx?docid=171804&pageid=27160",
  "92-2015-TT-BTC.pdf": "https://congbao.chinhphu.vn/van-ban/92-2015-tt-btc-15620.htm",
  "65-2013-ND-CP.pdf": "https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-65-2013-nd-cp-4403.htm",
  "91-2014-ND-CP.pdf": "https://congbao.chinhphu.vn/van-ban/nghi-dinh-so-91-2014-nd-cp-6679.htm",
  "12-2015-ND-CP.pdf": "https://congbao.chinhphu.vn/so-do-van-ban-so-12-2015-nd-cp-6680",
};

const overrides = {
  "111-2013-TT-BTC.pdf": {
    title:
      "Thông tư 111/2013/TT-BTC hướng dẫn thực hiện Luật Thuế thu nhập cá nhân, Luật sửa đổi, bổ sung một số điều của Luật Thuế thu nhập cá nhân và Nghị định 65/2013/NĐ-CP",
    issue_date: "2013-08-15",
    effective_date: "2013-10-01",
    notes:
      "PDF dạng scan/ảnh; metadata ngày hiệu lực được đối chiếu với Công báo Chính phủ.",
  },
  "119-2014-TT-BTC.pdf": {
    title:
      "Thông tư 119/2014/TT-BTC sửa đổi, bổ sung một số thông tư để cải cách, đơn giản thủ tục hành chính về thuế",
  },
  "151-2014-TT-BTC.pdf": {
    title:
      "Thông tư 151/2014/TT-BTC hướng dẫn thi hành Nghị định 91/2014/NĐ-CP về sửa đổi, bổ sung một số điều tại các Nghị định quy định về thuế",
  },
  "20-1010-TT-BTC.pdf": {
    document_id: "CIRCULAR_20_2010_TT_BTC",
    document_number: "20/2010/TT-BTC",
    title:
      "Thông tư 20/2010/TT-BTC hướng dẫn sửa đổi, bổ sung một số thủ tục hành chính về Thuế thu nhập cá nhân",
    issue_date: "2010-02-05",
    effective_date: "2010-03-22",
    notes: "",
  },
  "206-2013-TTLT-BTC-BCA.pdf": {
    title:
      "Thông tư liên tịch 206/2013/TTLT-BTC-BCA hướng dẫn việc thu, nộp thuế thu nhập cá nhân đối với sĩ quan, hạ sĩ quan, công chức, viên chức và nhân viên hưởng lương trong Công an nhân dân",
    issue_date: "2013-12-25",
    effective_date: "2014-02-07",
    notes:
      "PDF dạng scan/ảnh; metadata được đối chiếu với Cổng Thông tin điện tử Chính phủ.",
  },
  "212-2013-TTLT-BTC-BQP.pdf": {
    title:
      "Thông tư liên tịch 212/2013/TTLT-BTC-BQP hướng dẫn việc thu, nộp thuế thu nhập cá nhân đối với sĩ quan, quân nhân chuyên nghiệp, cán bộ, công chức, viên chức và nhân viên hưởng lương thuộc Bộ Quốc phòng",
    issue_date: "2013-12-30",
    effective_date: "2014-02-12",
    notes:
      "PDF dạng scan/ảnh; source_url chính thức chưa xác định, metadata ngày/tiêu đề được đối chiếu từ nguồn văn bản công khai.",
  },
  "92-2015-TT-BTC.pdf": {
    title:
      "Thông tư 92/2015/TT-BTC hướng dẫn thuế giá trị gia tăng và thuế thu nhập cá nhân đối với cá nhân cư trú có hoạt động kinh doanh",
    issue_date: "2015-06-15",
    effective_date: "2015-07-30",
    notes:
      "PDF dạng scan/ảnh; metadata ngày hiệu lực được đối chiếu với Công báo Chính phủ.",
  },
  "12-2015-ND-CP.pdf": {
    title:
      "Nghị định 12/2015/NĐ-CP quy định chi tiết thi hành Luật sửa đổi, bổ sung một số điều của các Luật về thuế và sửa đổi, bổ sung một số điều của các Nghị định về thuế",
    issue_date: "2015-02-12",
    effective_date: "2015-02-12",
    notes:
      "PDF dạng scan/ảnh; metadata ngày hiệu lực được đối chiếu với Công báo Chính phủ.",
  },
  "65-2013-ND-CP.pdf": {
    title:
      "Nghị định 65/2013/NĐ-CP quy định chi tiết một số điều của Luật Thuế thu nhập cá nhân và Luật sửa đổi, bổ sung một số điều của Luật Thuế thu nhập cá nhân",
    issue_date: "2013-06-27",
    effective_date: "2013-07-01",
    notes:
      "PDF dạng scan/ảnh; metadata ngày hiệu lực được đối chiếu với Công báo Chính phủ.",
  },
  "91-2014-ND-CP.pdf": {
    title:
      "Nghị định 91/2014/NĐ-CP sửa đổi, bổ sung một số điều tại các Nghị định quy định về thuế",
    issue_date: "2014-10-01",
    effective_date: "2014-11-15",
    notes:
      "PDF dạng scan/ảnh; metadata ngày hiệu lực được đối chiếu với Công báo Chính phủ.",
  },
  "109-2025-QH15-Luat-TNCN.pdf": {
    document_id: "LAW_109_2025_QH15",
    document_number: "109/2025/QH15",
    title: "Luật Thuế thu nhập cá nhân",
    issue_date: "2025-12-10",
    effective_date: "2026-07-01",
    status: "not_yet_effective",
    topics: "thuế thu nhập cá nhân",
    notes:
      "PDF dạng scan/ảnh; tại ngày 2026-06-07 văn bản chưa có hiệu lực.",
  },
  "954-2020-UBTVQH14.pdf": {
    title:
      "Nghị quyết 954/2020/UBTVQH14 về điều chỉnh mức giảm trừ gia cảnh của thuế thu nhập cá nhân",
    issue_date: "2020-06-02",
    effective_date: "2020-07-01",
    topics: "thuế thu nhập cá nhân; giảm trừ gia cảnh",
    notes:
      "PDF dạng scan/ảnh; source_url chính thức chưa xác định, metadata ngày/tiêu đề được đối chiếu từ nguồn văn bản công khai.",
  },
  "12764-CTHN-TTHT.pdf": {
    title: "Công văn 12764/CTHN-TTHT về xác định thu nhập chịu thuế TNCN",
  },
  "13510-CTHN-TTHT.pdf": {
    title:
      "Công văn 13510/CTHN-TTHT về chính sách thuế TNCN đối với khoản trợ cấp mất việc",
    issue_date: "2023-03-22",
    effective_date: "2023-03-22",
  },
  "13762-CTHN-HKDCN.doc": {
    title: "Công văn 13762/CTHN-HKDCN",
    notes: "",
  },
  "19297-CTHN-TTHT.pdf": {
    title:
      "Công văn 19297/CTHN-TTHT về thuế TNCN đối với lệ phí thi chứng chỉ",
  },
  "20479-CT-TTHT.pdf": {
    issuing_authority: "Cục Thuế Thành phố Hà Nội",
    title:
      "Công văn 20479/CT-TTHT về tính thuế TNCN đối với hoạt động cho thuê lại lao động",
  },
  "24601-CTHN-TTHT.pdf": {
    title:
      "Công văn 24601/CTHN-TTHT về thuế TNCN từ trúng thưởng cho nhân viên",
    issue_date: "2023-04-19",
    effective_date: "2023-04-19",
  },
  "26215-CTHN-TTHT.pdf": {
    title: "Công văn 26215/CTHN-TTHT về chính sách thuế TNCN",
    issue_date: "2023-04-21",
    effective_date: "2023-04-21",
  },
  "3177-TCT-DNNCN.doc": {
    title:
      "Công văn 3177/TCT-DNNCN về chính sách thuế TNCN đối với tiền được hưởng từ Quỹ hưu trí bổ sung tự nguyện",
    issue_date: "2023-07-27",
    effective_date: "2023-07-27",
    notes:
      "File .doc cũ; metadata ngày/tiêu đề được đối chiếu từ nguồn văn bản công khai.",
  },
  "33037-CTHN-TTHT.pdf": {
    title:
      "Công văn 33037/CTHN-TTHT về chính sách thuế TNCN đối với quà tặng cho nhân viên khi nghỉ việc",
    issue_date: "2023-05-15",
    effective_date: "2023-05-15",
  },
  "3469-CTHN-TTHT.pdf": {
    title:
      "Công văn 3469/CTHN-TTHT về thuế TNCN đối với quà tặng và thưởng cho nhân viên",
    issue_date: "2023-02-01",
    effective_date: "2023-02-01",
  },
  "388-CTHN-TTHT.pdf": {
    title:
      "Công văn 388/CTHN-TTHT về chứng từ điện tử khấu trừ thuế TNCN",
    issue_date: "2023-01-04",
    effective_date: "2023-01-04",
  },
  "41573-CTHN-TTHT.pdf": {
    title: "Công văn 41573/CTHN-TTHT về quyết toán thuế TNCN",
    issue_date: "2023-06-14",
    effective_date: "2023-06-14",
  },
  "4172-TCT-DNNCN.pdf": {
    title: "Công văn 4172/TCT-DNNCN về đẩy mạnh xử lý hồ sơ hoàn thuế TNCN",
    issue_date: "2023-09-20",
    effective_date: "2023-09-20",
  },
  "4418-CTHN-TTHT.pdf": {
    title:
      "Công văn 4418/CTHN-TTHT về kê khai, phân bổ thuế TNCN theo Thông tư 80/2021/TT-BTC",
    issue_date: "2023-02-09",
    effective_date: "2023-02-09",
  },
  "45194-CTHN-TTHT.pdf": {
    title: "Công văn 45194/CTHN-TTHT về kê khai thuế TNCN cho người lao động",
    issue_date: "2023-06-30",
    effective_date: "2023-06-30",
  },
  "4888-TCT-DNNCN.pdf": {
    title: "Công văn 4888/TCT-DNNCN về chính sách thuế TNCN",
  },
  "5001-TCT-DNNCN.pdf": {
    title:
      "Công văn 5001/TCT-DNNCN về xác định căn cứ tính thuế TNCN đối với thu nhập từ thừa kế",
  },
  "6097-CTHN-TTHT.pdf": {
    title: "Công văn 6097/CTHN-TTHT về quyết toán thuế TNCN",
    issue_date: "2023-02-16",
    effective_date: "2023-02-16",
  },
  "61175-CTHN-TTHT.pdf": {
    title:
      "Công văn 61175/CTHN-TTHT về thuế TNCN từ việc trúng thưởng của người lao động",
  },
  "61182-CTHN-TTHT.pdf": {
    title:
      "Công văn 61182/CTHN-TTHT về thuế TNCN đối với thu nhập của lao động nước ngoài",
  },
  "63646-CTHN-TTHT.pdf": {
    title:
      "Công văn 63646/CTHN-TTHT về miễn giảm thuế TNCN theo Hiệp định vận chuyển hàng không",
    issue_date: "2023-08-30",
    effective_date: "2023-08-30",
  },
  "9208-CT-TTHT.doc": {
    title:
      "Công văn 9208/CT-TTHT về hóa đơn, chứng từ",
    issue_date: "2017-09-22",
    effective_date: "2017-09-22",
    topics: "hóa đơn, chứng từ",
  },
};

function colName(n) {
  let s = "";
  while (n > 0) {
    const m = (n - 1) % 26;
    s = String.fromCharCode(65 + m) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

function normalizeRow(raw) {
  const row = {};
  for (const header of headers) {
    row[header] = raw[header] ?? "";
  }

  const override = overrides[row.file_name] ?? {};
  Object.assign(row, override);
  row.source_url = row.source_url || authoritativeUrls[row.file_name] || "";
  row.source_type = row.source_type || "official";
  row.download_date = row.download_date || "2026-06-07";
  row.version = row.version || 1;
  row.status = row.status || "effective";

  if (row.document_type === "Công văn" && row.issue_date && !row.effective_date) {
    row.effective_date = row.issue_date;
  }

  if (!row.topics) {
    row.topics = inferTopics(row.title);
  }

  return row;
}

function inferTopics(title) {
  const lower = title.toLowerCase();
  const topics = [];
  if (lower.includes("tncn") || lower.includes("thu nhập cá nhân")) {
    topics.push("thuế thu nhập cá nhân");
  }
  if (lower.includes("quyết toán")) topics.push("quyết toán thuế");
  if (lower.includes("giảm trừ gia cảnh")) topics.push("giảm trừ gia cảnh");
  if (lower.includes("khấu trừ")) topics.push("khấu trừ thuế");
  if (lower.includes("người phụ thuộc")) topics.push("người phụ thuộc");
  if (lower.includes("trúng thưởng")) topics.push("trúng thưởng");
  if (lower.includes("hoàn thuế")) topics.push("hoàn thuế");
  if (lower.includes("thu nhập từ thừa kế")) topics.push("thu nhập từ thừa kế");
  if (lower.includes("thuế gtgt")) topics.push("thuế giá trị gia tăng");
  return topics.length ? [...new Set(topics)].join("; ") : "thuế thu nhập cá nhân";
}

function setColumnWidths(sheet) {
  const widthByHeader = new Map([
    ["document_id", 190],
    ["file_name", 230],
    ["title", 520],
    ["document_number", 180],
    ["document_type", 150],
    ["issuing_authority", 210],
    ["issue_date", 120],
    ["effective_date", 120],
    ["expiry_date", 120],
    ["status", 150],
    ["source_type", 130],
    ["source_url", 360],
    ["local_path", 320],
    ["download_date", 120],
    ["topics", 260],
    ["version", 90],
    ["notes", 420],
  ]);
  headers.forEach((header, index) => {
    const col = colName(index + 1);
    sheet.getRange(`${col}:${col}`).format.columnWidthPx = widthByHeader.get(header) ?? 180;
  });
}

function styleRegistrySheet(sheet, rows) {
  const endCol = colName(headers.length);
  sheet.showGridLines = true;
  sheet.getRange(`A1:${endCol}1`).values = [headers];
  sheet.getRange(`A1:${endCol}1`).format = {
    fill: "#0F766E",
    font: { bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "middle",
  };
  sheet.getRange(`A1:${endCol}1`).format.rowHeightPx = 30;
  sheet.getRangeByIndexes(1, 0, rows.length, headers.length).values = rows.map((row) =>
    headers.map((header) => row[header] ?? "")
  );
  sheet.getRange(`A2:${endCol}${rows.length + 1}`).format = {
    verticalAlignment: "top",
    wrapText: true,
  };
  sheet.freezePanes.freezeRows(1);
  setColumnWidths(sheet);

  for (const header of ["issue_date", "effective_date", "expiry_date", "download_date"]) {
    const idx = headers.indexOf(header);
    if (idx >= 0) {
      const col = colName(idx + 1);
      sheet.getRange(`${col}2:${col}${rows.length + 1}`).setNumberFormat("yyyy-mm-dd");
    }
  }
}

function addSchemaSheet(workbook) {
  const sheet = workbook.worksheets.add("schema");
  sheet.getRange("A1:C1").values = [["column", "required", "description"]];
  sheet.getRange("A1:C1").format = {
    fill: "#334155",
    font: { bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "middle",
  };
  sheet.getRangeByIndexes(1, 0, schemaRows.length, 3).values = schemaRows;
  sheet.freezePanes.freezeRows(1);
  sheet.getRange("A:A").format.columnWidthPx = 190;
  sheet.getRange("B:B").format.columnWidthPx = 90;
  sheet.getRange("C:C").format.columnWidthPx = 560;
  sheet.getRange(`A2:C${schemaRows.length + 1}`).format = {
    verticalAlignment: "top",
    wrapText: true,
  };
}

const payload = JSON.parse(await fs.readFile(candidatesPath, "utf8"));
const rows = payload.rows
  .map(normalizeRow)
  .sort((a, b) => a.local_path.localeCompare(b.local_path, "vi"));

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("document_registry");
styleRegistrySheet(sheet, rows);
addSchemaSheet(workbook);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 50 },
  summary: "document_registry formula error scan",
});
const preview = await workbook.inspect({
  kind: "table",
  range: `document_registry!A1:${colName(headers.length)}6`,
  include: "values,formulas",
  tableMaxRows: 6,
  tableMaxCols: headers.length,
});
await workbook.render({
  sheetName: "document_registry",
  range: "A1:Q12",
  scale: 1,
  format: "png",
});
await workbook.render({
  sheetName: "schema",
  autoCrop: "all",
  scale: 1,
  format: "png",
});

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(registryPath);

console.log(JSON.stringify({
  registryPath,
  rowCount: rows.length,
  formulaErrors: errors.ndjson,
  preview: preview.ndjson.split("\n").slice(0, 8),
}, null, 2));
