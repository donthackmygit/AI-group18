import path from "node:path";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, "..");
const registryPath = path.join(projectRoot, "data", "metadata", "document_registry.xlsx");

const columns = {
  document_id: "A",
  file_name: "B",
  title: "C",
  document_number: "D",
  document_type: "E",
  issuing_authority: "F",
  issue_date: "G",
  effective_date: "H",
  expiry_date: "I",
  status: "J",
  source_type: "K",
  source_url: "L",
  local_path: "M",
  download_date: "N",
  topics: "O",
  version: "P",
  notes: "Q",
};

const updates = {
  CIRCULAR_111_2013_TT_BTC: {
    file_name: "111-2013-TT-BTC.doc",
    local_path: "data/raw/circulars/111-2013-TT-BTC.doc",
  },
  CIRCULAR_20_2010_TT_BTC: {
    file_name: "20-2010-TT-BTC.doc",
    local_path: "data/raw/circulars/20-2010-TT-BTC.doc",
    notes: "",
  },
  JOINT_CIRCULAR_206_2013_TTLT_BTC_BCA: {
    file_name: "206-2013-TTLT-BTC-BCA.doc",
    local_path: "data/raw/circulars/206-2013-TTLT-BTC-BCA.doc",
  },
  JOINT_CIRCULAR_212_2013_TTLT_BTC_BQP: {
    file_name: "212-2013-TTLT-BTC-BQP.doc",
    local_path: "data/raw/circulars/212-2013-TTLT-BTC-BQP.doc",
  },
  CIRCULAR_92_2015_TT_BTC: {
    file_name: "92-2015-TT-BTC.doc",
    local_path: "data/raw/circulars/92-2015-TT-BTC.doc",
  },
  DECREE_12_2015_ND_CP: {
    file_name: "12-2015-ND-CP.doc",
    local_path: "data/raw/decrees/12-2015-ND-CP.doc",
  },
  DECREE_65_2013_ND_CP: {
    file_name: "65-2013-ND-CP.doc",
    local_path: "data/raw/decrees/65-2013-ND-CP.doc",
  },
  DECREE_91_2014_ND_CP: {
    file_name: "91-2014-ND-CP.doc",
    local_path: "data/raw/decrees/91-2014-ND-CP.doc",
  },
  LAW_109_2025_QH15: {
    file_name: "109-2025-QH15.doc",
    local_path: "data/raw/laws/109-2025-QH15.doc",
  },
  DISPATCH_13510_CTHN_TTHT: {
    file_name: "13510-CTHN-TTHT.doc",
    local_path: "data/raw/official_dispatches/13510-CTHN-TTHT.doc",
  },
  DISPATCH_13762_CTHN_HCDKN: {
    document_id: "DISPATCH_13762_CTHN_HKDCN",
    file_name: "13762-CTHN-HKDCN.doc",
    title: "Công văn 13762/CTHN-HKDCN về quyết toán thuế TNCN năm 2022",
    document_number: "13762/CTHN-HKDCN",
    issuing_authority: "Cục Thuế Thành phố Hà Nội",
    issue_date: "2023-03-22",
    effective_date: "2023-03-22",
    status: "effective",
    local_path: "data/raw/official_dispatches/13762-CTHN-HKDCN.doc",
    topics: "thuế thu nhập cá nhân; quyết toán thuế",
    notes: "",
  },
  DISPATCH_24601_CTHN_TTHT: {
    file_name: "24601-CTHN-TTHT.doc",
    local_path: "data/raw/official_dispatches/24601-CTHN-TTHT.doc",
  },
  DISPATCH_26215_CTHN_TTHT: {
    file_name: "26215-CTHN-TTHT.doc",
    local_path: "data/raw/official_dispatches/26215-CTHN-TTHT.doc",
  },
  DISPATCH_33037_CTHN_TTHT: {
    file_name: "33037-CTHN-TTHT.doc",
    local_path: "data/raw/official_dispatches/33037-CTHN-TTHT.doc",
  },
  DISPATCH_3469_CTHN_TTHT: {
    file_name: "3469-CTHN-TTHT.doc",
    local_path: "data/raw/official_dispatches/3469-CTHN-TTHT.doc",
  },
  DISPATCH_388_CTHN_TTHT: {
    file_name: "388-CTHN-TTHT.doc",
    local_path: "data/raw/official_dispatches/388-CTHN-TTHT.doc",
  },
  DISPATCH_41573_CTHN_TTHT: {
    file_name: "41573-CTHN-TTHT.doc",
    local_path: "data/raw/official_dispatches/41573-CTHN-TTHT.doc",
  },
  DISPATCH_4172_TCT_DNNCN: {
    file_name: "4172-TCT-DNNCN.doc",
    local_path: "data/raw/official_dispatches/4172-TCT-DNNCN.doc",
  },
  DISPATCH_4418_CTHN_TTHT: {
    file_name: "4418-CTHN-TTHT.doc",
    local_path: "data/raw/official_dispatches/4418-CTHN-TTHT.doc",
  },
  DISPATCH_45194_CTHN_TTHT: {
    file_name: "45194-CTHN-TTHT.doc",
    local_path: "data/raw/official_dispatches/45194-CTHN-TTHT.doc",
  },
  DISPATCH_6097_CTHN_TTHT: {
    file_name: "6097-CTHN-TTHT.doc",
    local_path: "data/raw/official_dispatches/6097-CTHN-TTHT.doc",
  },
  DISPATCH_9298_CTHN_TTHT: {
    document_id: "DISPATCH_9208_CT_TTHT",
    file_name: "9208-CT-TTHT.doc",
    title: "Công văn 9208/CT-TTHT về hóa đơn, chứng từ",
    document_number: "9208/CT-TTHT",
    document_type: "Công văn",
    issuing_authority: "Cục Thuế Thành phố Hồ Chí Minh",
    issue_date: "2017-09-22",
    effective_date: "2017-09-22",
    expiry_date: "",
    status: "effective",
    source_type: "official",
    source_url: "",
    local_path: "data/raw/official_dispatches/9208-CT-TTHT.doc",
    topics: "hóa đơn, chứng từ",
    version: 1,
    notes: "",
  },
  RESOLUTION_954_2020_UBTVQH14: {
    file_name: "954-2020-UBTVQH14.doc",
    local_path: "data/raw/resolutions/954-2020-UBTVQH14.doc",
  },
};

const input = await FileBlob.load(registryPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem("document_registry");
const values = sheet.getUsedRange().values;
const headers = values[0];
const documentIdIndex = headers.indexOf("document_id");

if (documentIdIndex < 0) {
  throw new Error("Missing document_id column.");
}

const applied = [];
for (let rowIndex = 1; rowIndex < values.length; rowIndex += 1) {
  const row = values[rowIndex];
  const documentId = row[documentIdIndex];
  const update = updates[documentId];
  if (!update) continue;

  const excelRow = rowIndex + 1;
  for (const [field, value] of Object.entries(update)) {
    const col = columns[field];
    if (!col) throw new Error(`No column mapping for field: ${field}`);
    sheet.getRange(`${col}${excelRow}`).values = [[value]];
  }
  applied.push({ row: excelRow, from: documentId, to: update.document_id ?? documentId });
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(registryPath);

console.log(JSON.stringify({ updatedRows: applied.length, applied }, null, 2));
