import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(scriptDir, "..");
const registryPath = path.join(projectRoot, "data", "metadata", "document_registry.xlsx");
const rawDir = path.join(projectRoot, "data", "raw");

function toPosix(value) {
  return value.replaceAll(path.sep, "/");
}

async function listFiles(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await listFiles(fullPath)));
    } else if (entry.name !== ".gitkeep") {
      files.push(toPosix(path.relative(projectRoot, fullPath)));
    }
  }
  return files.sort((a, b) => a.localeCompare(b, "vi"));
}

function fileExists(relativePath, rawFiles) {
  return rawFiles.has(relativePath);
}

function stemOf(relativePath) {
  return path.posix.basename(relativePath, path.posix.extname(relativePath));
}

function dirOf(relativePath) {
  return path.posix.dirname(relativePath);
}

function normalizeVietnameseCode(value) {
  return String(value ?? "")
    .replaceAll("Đ", "D")
    .replaceAll("đ", "d")
    .replaceAll("/", "-")
    .replaceAll(" ", "")
    .toUpperCase();
}

function candidatesFor(row, oldPath, rawFiles, referencedOrAssigned) {
  const oldDir = dirOf(oldPath);
  const oldStem = stemOf(oldPath);
  const rawList = [...rawFiles].filter((file) => dirOf(file) === oldDir);

  const sameStem = rawList.filter((file) => stemOf(file) === oldStem);
  if (sameStem.length === 1) return sameStem;

  const documentNumber = normalizeVietnameseCode(row.document_number);
  const numberPrefix = documentNumber.split("-").slice(0, 3).join("-");
  if (numberPrefix) {
    const byDocumentNumber = rawList.filter((file) =>
      normalizeVietnameseCode(stemOf(file)).startsWith(numberPrefix)
    );
    if (byDocumentNumber.length === 1) return byDocumentNumber;
  }

  const documentIdParts = String(row.document_id ?? "").split("_");
  const leadingNumber = documentIdParts.find((part) => /^\d+$/.test(part));
  if (leadingNumber) {
    const byLeadingNumber = rawList.filter((file) =>
      stemOf(file).startsWith(`${leadingNumber}-`)
    );
    if (byLeadingNumber.length === 1) return byLeadingNumber;
  }

  const remainingInDir = rawList.filter((file) => !referencedOrAssigned.has(file));
  if (remainingInDir.length === 1) return remainingInDir;

  return [];
}

const rawFilesList = await listFiles(rawDir);
const rawFiles = new Set(rawFilesList);

const input = await FileBlob.load(registryPath);
const workbook = await SpreadsheetFile.importXlsx(input);
const sheet = workbook.worksheets.getItem("document_registry");
const used = sheet.getUsedRange();
const values = used.values;
const headers = values[0];
const indexes = Object.fromEntries(headers.map((header, index) => [header, index]));

for (const required of ["document_id", "document_number", "local_path"]) {
  if (!(required in indexes)) {
    throw new Error(`Missing required registry column: ${required}`);
  }
}

const currentRows = values.slice(1).filter((row) => row.some((cell) => String(cell ?? "").trim()));
const referencedExisting = new Set(
  currentRows
    .map((row) => String(row[indexes.local_path] ?? "").trim())
    .filter((localPath) => localPath && fileExists(localPath, rawFiles))
);
const referencedOrAssigned = new Set(referencedExisting);
const updates = [];
const unresolved = [];

for (let rowIndex = 0; rowIndex < currentRows.length; rowIndex += 1) {
  const rowValues = currentRows[rowIndex];
  const excelRow = rowIndex + 2;
  const row = Object.fromEntries(headers.map((header, index) => [header, rowValues[index]]));
  const oldPath = String(row.local_path ?? "").trim();

  if (!oldPath || fileExists(oldPath, rawFiles)) {
    continue;
  }

  const candidates = candidatesFor(row, oldPath, rawFiles, referencedOrAssigned);
  if (candidates.length === 1) {
    const newPath = candidates[0];
    sheet.getRange(`M${excelRow}`).values = [[newPath]];
    referencedOrAssigned.add(newPath);
    updates.push({
      row: excelRow,
      document_id: row.document_id,
      old_path: oldPath,
      new_path: newPath,
    });
  } else {
    unresolved.push({
      row: excelRow,
      document_id: row.document_id,
      old_path: oldPath,
      candidates,
    });
  }
}

if (unresolved.length) {
  console.error(JSON.stringify({ updates, unresolved }, null, 2));
  throw new Error(`Could not resolve ${unresolved.length} local_path value(s).`);
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(registryPath);

console.log(JSON.stringify({ updated: updates.length, updates }, null, 2));
