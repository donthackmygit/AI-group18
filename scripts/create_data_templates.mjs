import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, "..");

function colName(n) {
  let s = "";
  while (n > 0) {
    const m = (n - 1) % 26;
    s = String.fromCharCode(65 + m) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

async function ensureDir(filePath) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
}

function setColumnWidths(sheet, headers) {
  const widthByHeader = new Map([
    ["document_id", 170],
    ["file_name", 220],
    ["title", 320],
    ["document_number", 160],
    ["document_type", 130],
    ["issuing_authority", 170],
    ["issue_date", 120],
    ["effective_date", 120],
    ["expiry_date", 120],
    ["status", 150],
    ["source_type", 130],
    ["source_url", 320],
    ["local_path", 280],
    ["download_date", 120],
    ["topics", 220],
    ["version", 90],
    ["notes", 280],
    ["question_id", 130],
    ["question", 420],
    ["topic", 220],
    ["difficulty", 120],
    ["source_document_id", 180],
    ["article", 110],
    ["clause", 110],
    ["expected_answer_id", 170],
    ["answer_id", 130],
    ["expected_answer", 480],
    ["legal_basis", 320],
    ["point", 110],
  ]);

  headers.forEach((header, index) => {
    const col = colName(index + 1);
    sheet.getRange(`${col}:${col}`).format.columnWidthPx =
      widthByHeader.get(header) ?? 180;
  });
}

function styleTemplateSheet(sheet, headers, dateHeaders = []) {
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
  sheet.getRange(`A2:${endCol}101`).values = Array.from({ length: 100 }, () =>
    headers.map(() => "")
  );
  sheet.freezePanes.freezeRows(1);
  setColumnWidths(sheet, headers);

  for (const header of dateHeaders) {
    const idx = headers.indexOf(header);
    if (idx >= 0) {
      const col = colName(idx + 1);
      sheet.getRange(`${col}2:${col}101`).setNumberFormat("yyyy-mm-dd");
    }
  }
}

function addSchemaSheet(workbook, rows) {
  const sheet = workbook.worksheets.add("schema");

  sheet.getRange("A1:C1").values = [["column", "required", "description"]];
  sheet.getRange("A1:C1").format = {
    fill: "#334155",
    font: { bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "middle",
  };
  sheet.getRangeByIndexes(1, 0, rows.length, 3).values = rows;
  sheet.freezePanes.freezeRows(1);
  sheet.getRange("A:A").format.columnWidthPx = 190;
  sheet.getRange("B:B").format.columnWidthPx = 90;
  sheet.getRange("C:C").format.columnWidthPx = 520;
  sheet.getRange(`A2:C${rows.length + 1}`).format = {
    verticalAlignment: "top",
  };
}

async function saveWorkbook(filePath, mainSheetName, headers, schemaRows, dateHeaders = []) {
  await ensureDir(filePath);

  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add(mainSheetName);
  styleTemplateSheet(sheet, headers, dateHeaders);
  addSchemaSheet(workbook, schemaRows);

  await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 50 },
    summary: `${mainSheetName} formula error scan`,
  });
  await workbook.inspect({
    kind: "table",
    range: `${mainSheetName}!A1:${colName(headers.length)}4`,
    include: "values,formulas",
    tableMaxRows: 4,
    tableMaxCols: headers.length,
  });
  await workbook.render({
    sheetName: mainSheetName,
    autoCrop: "all",
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
  await output.save(filePath);
  return filePath;
}

const registryHeaders = [
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

const registrySchema = [
  ["document_id", "yes", "Ma tai lieu duy nhat, vi du LAW_04_2007_QH12 hoac TT_111_2013_BTC."],
  ["file_name", "yes", "Ten file goc dat trong data/raw theo nhom van ban."],
  ["title", "yes", "Ten day du cua van ban phap luat hoac tai lieu huong dan."],
  ["document_number", "yes", "So hieu van ban, vi du 111/2013/TT-BTC."],
  ["document_type", "yes", "Luat, Nghi dinh, Thong tu, Van ban hop nhat, Cong van, Huong dan."],
  ["issuing_authority", "yes", "Co quan ban hanh, vi du Quoc hoi, Chinh phu, Bo Tai chinh, Tong cuc Thue."],
  ["issue_date", "yes", "Ngay ban hanh theo dinh dang yyyy-mm-dd."],
  ["effective_date", "yes", "Ngay co hieu luc theo dinh dang yyyy-mm-dd."],
  ["expiry_date", "no", "Ngay het hieu luc neu co; de trong neu chua xac dinh."],
  ["status", "yes", "Trang thai: effective, expired, not_yet_effective, partially_effective, replaced."],
  ["source_type", "yes", "Loai nguon: official, trusted_secondary, internal. Uu tien official."],
  ["source_url", "yes", "URL nguon tai hoac trang cong bo chinh thuc."],
  ["local_path", "yes", "Duong dan tuong doi trong du an, vi du data/raw/circulars/111_2013_TT_BTC.pdf."],
  ["download_date", "yes", "Ngay tai ve theo dinh dang yyyy-mm-dd."],
  ["topics", "no", "Danh sach chu de ngan cach bang dau cham phay, vi du thue thu nhap ca nhan; quyet toan thue."],
  ["version", "yes", "So phien ban registry cua tai lieu, bat dau tu 1."],
  ["notes", "no", "Ghi chu ve pham vi, thay the, hop nhat, dieu khoan can chu y."],
];

const questionHeaders = [
  "question_id",
  "question",
  "topic",
  "difficulty",
  "source_document_id",
  "article",
  "clause",
  "expected_answer_id",
  "notes",
];

const questionSchema = [
  ["question_id", "yes", "Ma cau hoi duy nhat, vi du Q_TNCN_0001."],
  ["question", "yes", "Cau hoi dung de danh gia retrieval/generation."],
  ["topic", "yes", "Chu de chinh cua cau hoi, vi du giam tru gia canh, cu tru, quyet toan."],
  ["difficulty", "no", "Muc do: easy, medium, hard."],
  ["source_document_id", "no", "Ma tai lieu ky vong he thong can truy xuat."],
  ["article", "no", "Dieu luat lien quan neu biet."],
  ["clause", "no", "Khoan lien quan neu biet."],
  ["expected_answer_id", "no", "Khoa lien ket sang expected_answers.xlsx."],
  ["notes", "no", "Ghi chu ve bien the cau hoi, gia dinh, hoac pham vi danh gia."],
];

const answerHeaders = [
  "answer_id",
  "question_id",
  "expected_answer",
  "legal_basis",
  "document_id",
  "article",
  "clause",
  "point",
  "effective_date",
  "status",
  "notes",
];

const answerSchema = [
  ["answer_id", "yes", "Ma dap an ky vong duy nhat, vi du A_TNCN_0001."],
  ["question_id", "yes", "Ma cau hoi tuong ung trong questions.xlsx."],
  ["expected_answer", "yes", "Dap an chuan de so sanh voi cau tra loi cua chatbot."],
  ["legal_basis", "yes", "Can cu phap ly ngan gon: ten van ban, dieu, khoan, diem."],
  ["document_id", "yes", "Ma tai lieu trong document_registry.xlsx."],
  ["article", "no", "Dieu lien quan."],
  ["clause", "no", "Khoan lien quan."],
  ["point", "no", "Diem lien quan neu co."],
  ["effective_date", "no", "Ngay hieu luc ap dung cho dap an theo dinh dang yyyy-mm-dd."],
  ["status", "no", "Trang thai hieu luc cua can cu tai thoi diem danh gia."],
  ["notes", "no", "Ghi chu ve ngoai le, pham vi hoac cach cham diem."],
];

const created = [];
created.push(
  await saveWorkbook(
    path.join(projectRoot, "data", "metadata", "document_registry.xlsx"),
    "document_registry",
    registryHeaders,
    registrySchema,
    ["issue_date", "effective_date", "expiry_date", "download_date"]
  )
);
created.push(
  await saveWorkbook(
    path.join(projectRoot, "data", "evaluation", "questions.xlsx"),
    "questions",
    questionHeaders,
    questionSchema
  )
);
created.push(
  await saveWorkbook(
    path.join(projectRoot, "data", "evaluation", "expected_answers.xlsx"),
    "expected_answers",
    answerHeaders,
    answerSchema,
    ["effective_date"]
  )
);

console.log(`Created ${created.length} workbook template(s):`);
for (const filePath of created) {
  console.log(`- ${path.relative(projectRoot, filePath)}`);
}
