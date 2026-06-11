import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const registryPath = "data/metadata/document_registry.xlsx";

const urlColumns = {
  sourceType: 10,
  sourceUrl: 11,
  notes: 16,
};

const urlOverrides = {
  DISPATCH_12764_CTHN_TTHT:
    "https://thuvienphapluat.vn/cong-van/Thue-Phi-Le-Phi/Cong-van-12764-CTHN-TTHT-2023-xac-dinh-thu-nhap-chiu-thue-thu-nhap-ca-nhan-Cuc-Thue-Ha-Noi-560345.aspx",
};

const trustedSecondaryDomains = [
  "thuvienphapluat.vn",
  "luatvietnam.vn",
  "vbpl.ts24.com.vn",
  "dulieuphapluat.vn",
  "luatminhkhue.vn",
  "baocaotaichinh.vn",
  "nhansu.vn",
];

const searchPriorityDomains = [
  "thuvienphapluat.vn",
  "luatvietnam.vn",
  "vbpl.ts24.com.vn",
  "dulieuphapluat.vn",
  "luatminhkhue.vn",
  "baocaotaichinh.vn",
  "nhansu.vn",
];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function decodeHtml(value) {
  return value
    .replaceAll("&quot;", "\"")
    .replaceAll("&amp;", "&")
    .replaceAll("&#x2F;", "/")
    .replaceAll("&#39;", "'")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">");
}

function cleanTitle(value) {
  return decodeHtml(value.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim());
}

function cleanDuckDuckGoUrl(value) {
  let href = decodeHtml(value);
  if (href.startsWith("//duckduckgo.com/l/?")) {
    href = `https:${href}`;
  }

  try {
    const url = new URL(href);
    const target = url.searchParams.get("uddg");
    if (target) {
      return decodeURIComponent(target);
    }
  } catch {
    return href;
  }

  return href;
}

function compact(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

function sourceTypeForUrl(url) {
  if (!url) {
    return null;
  }

  const officialDomains = [
    "congbao.chinhphu.vn",
    "vbpl.vn",
    "chinhphu.vn",
    "mof.gov.vn",
    "gdt.gov.vn",
  ];

  if (officialDomains.some((domain) => url.includes(domain))) {
    return "official";
  }

  if (trustedSecondaryDomains.some((domain) => url.includes(domain))) {
    return "trusted_secondary";
  }

  return "trusted_secondary";
}

function noteForUrl(url) {
  if (!url || sourceTypeForUrl(url) === "official") {
    return null;
  }

  let sourceName = "nguồn văn bản công khai";
  if (url.includes("thuvienphapluat.vn")) sourceName = "Thư viện Pháp luật";
  if (url.includes("luatvietnam.vn")) sourceName = "LuatVietnam";
  if (url.includes("vbpl.ts24.com.vn")) sourceName = "VBPL TS24";
  if (url.includes("dulieuphapluat.vn")) sourceName = "Dữ liệu Pháp luật";
  if (url.includes("luatminhkhue.vn")) sourceName = "Luật Minh Khuê";
  if (url.includes("baocaotaichinh.vn")) sourceName = "Báo cáo Tài chính";
  if (url.includes("nhansu.vn")) sourceName = "Nhân Sự";

  return `source_url dùng ${sourceName} vì chưa xác định được URL công bố chính thức riêng cho văn bản này.`;
}

function appendNote(existing, addition) {
  if (!addition) {
    return existing || null;
  }

  const text = String(existing || "").trim();
  if (!text) {
    return addition;
  }
  if (text.includes(addition)) {
    return text;
  }
  return `${text} ${addition}`;
}

function queryFromRow(row, documentNumber, titleIndex) {
  const title = String(row[titleIndex] || "")
    .replace(/[^\p{L}\p{N}\s/.-]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
  const titleTerms = title
    .split(/\s+/)
    .filter((word) => word.length >= 4)
    .slice(0, 8)
    .join(" ");
  return `"${documentNumber}" ${titleTerms}`.trim();
}

async function searchSourceUrl(queryText, documentNumber) {
  const query = encodeURIComponent(queryText);
  const response = await fetch(`https://duckduckgo.com/html/?q=${query}`, {
    headers: {
      "user-agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
    },
  });
  const html = await response.text();
  let matches = parseDuckDuckGoHtml(html);

  if (!matches.length || html.includes("Unfortunately, bots use DuckDuckGo too.")) {
    const markdown = await fetchDuckDuckGoMarkdown(query);
    matches = parseDuckDuckGoMarkdown(markdown);
  }

  const normalizedNumber = compact(documentNumber);
  const dashNumber = documentNumber.toLowerCase().replaceAll("/", "-");
  const noSlashNumber = documentNumber.replaceAll("/", " ");

  const relevant = matches.filter((item) => {
    const haystack = `${item.url} ${item.title}`.toLowerCase();
    return (
      haystack.includes(dashNumber)
      || haystack.includes(noSlashNumber.toLowerCase())
      || compact(haystack).includes(normalizedNumber)
    );
  });

  relevant.sort((left, right) => {
    const leftIndex = searchPriorityDomains.findIndex((domain) => left.url.includes(domain));
    const rightIndex = searchPriorityDomains.findIndex((domain) => right.url.includes(domain));
    return (leftIndex === -1 ? 99 : leftIndex) - (rightIndex === -1 ? 99 : rightIndex);
  });

  return relevant[0] || matches[0] || null;
}

async function fetchDuckDuckGoMarkdown(encodedQuery) {
  const response = await fetch(
    `https://r.jina.ai/http://r.jina.ai/http://https://duckduckgo.com/html/?q=${encodedQuery}`,
    {
      headers: {
        "user-agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
      },
    },
  );
  return response.text();
}

function parseDuckDuckGoHtml(html) {
  return [...html.matchAll(/<a rel="nofollow" class="result__a" href="([^"]+)">([\s\S]*?)<\/a>/g)]
    .map((match) => ({
      url: cleanDuckDuckGoUrl(match[1]),
      title: cleanTitle(match[2]),
    }))
    .filter((item) => item.url.startsWith("http"));
}

function parseDuckDuckGoMarkdown(markdown) {
  return [...markdown.matchAll(/## \[([^\]]+)\]\((https:\/\/duckduckgo\.com\/l\/\?[^)]+)\)/g)]
    .map((match) => ({
      url: cleanDuckDuckGoUrl(match[2]),
      title: cleanTitle(match[1]),
    }))
    .filter((item) => item.url.startsWith("http"));
}

async function main() {
  const input = await FileBlob.load(registryPath);
  const workbook = await SpreadsheetFile.importXlsx(input);
  const sheet = workbook.worksheets.getItem("document_registry");
  const usedRange = sheet.getUsedRange();
  const rows = usedRange.values;
  const headers = rows[0];

  const documentIdIndex = headers.indexOf("document_id");
  const documentNumberIndex = headers.indexOf("document_number");
  const titleIndex = headers.indexOf("title");
  const sourceUrlIndex = headers.indexOf("source_url");

  if (documentIdIndex === -1 || documentNumberIndex === -1 || sourceUrlIndex === -1) {
    throw new Error("document_registry sheet is missing required URL columns.");
  }

  const updated = [];
  for (let rowIndex = 1; rowIndex < rows.length; rowIndex += 1) {
    const row = rows[rowIndex];
    const documentId = String(row[documentIdIndex] || "").trim();
    const documentNumber = String(row[documentNumberIndex] || "").trim();
    const existingUrl = String(row[sourceUrlIndex] || "").trim();

    if (!documentId || !documentNumber) {
      continue;
    }

    let sourceUrl = urlOverrides[documentId] || existingUrl;
    let picked = null;

    if (!sourceUrl) {
      picked = await searchSourceUrl(queryFromRow(row, documentNumber, titleIndex), documentNumber);
      if (!picked) {
        picked = await searchSourceUrl(documentNumber.replaceAll("/", " "), documentNumber);
      }
      sourceUrl = picked?.url || "";
      await sleep(500);
    }

    if (!sourceUrl) {
      updated.push({ documentId, documentNumber, status: "missing" });
      continue;
    }

    const sourceType = sourceTypeForUrl(sourceUrl);
    const sourceNote = noteForUrl(sourceUrl);
    row[urlColumns.sourceType] = sourceType || row[urlColumns.sourceType] || null;
    row[urlColumns.sourceUrl] = sourceUrl;
    row[urlColumns.notes] = appendNote(row[urlColumns.notes], sourceNote);

    updated.push({
      documentId,
      documentNumber,
      status: existingUrl === sourceUrl ? "kept" : "updated",
      sourceType: row[urlColumns.sourceType],
      sourceUrl,
      pickedTitle: picked?.title || null,
    });
  }

  usedRange.values = rows;

  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(registryPath);

  console.log(JSON.stringify(updated, null, 2));
}

await main();
