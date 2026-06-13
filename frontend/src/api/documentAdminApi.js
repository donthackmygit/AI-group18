import { requestJson } from "./http.js";

export function listDocuments(accessToken, options = {}) {
  return requestJson("/api/v1/admin/documents", {
    method: "GET",
    headers: authHeaders(accessToken),
    signal: options.signal,
  });
}

export function getDocument(documentId, accessToken, options = {}) {
  return requestJson(`/api/v1/admin/documents/${encodeURIComponent(documentId)}`, {
    method: "GET",
    headers: authHeaders(accessToken),
    signal: options.signal,
  });
}

export function uploadDocument(payload, accessToken, options = {}) {
  return requestJson("/api/v1/admin/documents/upload", {
    method: "POST",
    headers: authHeaders(accessToken),
    body: JSON.stringify(payload),
    signal: options.signal,
  });
}

export function updateDocument(documentId, payload, accessToken, options = {}) {
  return requestJson(`/api/v1/admin/documents/${encodeURIComponent(documentId)}`, {
    method: "PATCH",
    headers: authHeaders(accessToken),
    body: JSON.stringify(payload),
    signal: options.signal,
  });
}

export function ingestDocument(documentId, accessToken, options = {}) {
  return requestJson(`/api/v1/admin/documents/${encodeURIComponent(documentId)}/ingest`, {
    method: "POST",
    headers: authHeaders(accessToken),
    body: JSON.stringify({}),
    signal: options.signal,
  });
}

export function rerunDocumentEmbedding(documentId, accessToken, options = {}) {
  return requestJson(
    `/api/v1/admin/documents/${encodeURIComponent(documentId)}/rerun-embedding`,
    {
      method: "POST",
      headers: authHeaders(accessToken),
      body: JSON.stringify({}),
      signal: options.signal,
    },
  );
}

export function expireDocument(documentId, accessToken, options = {}) {
  return requestJson(`/api/v1/admin/documents/${encodeURIComponent(documentId)}/expire`, {
    method: "POST",
    headers: authHeaders(accessToken),
    body: JSON.stringify({}),
    signal: options.signal,
  });
}

export function removeDocumentFromSearch(documentId, accessToken, options = {}) {
  return requestJson(
    `/api/v1/admin/documents/${encodeURIComponent(documentId)}/search-index`,
    {
      method: "DELETE",
      headers: authHeaders(accessToken),
      signal: options.signal,
    },
  );
}

export function listDocumentChunks(documentId, accessToken, options = {}) {
  const params = new URLSearchParams();
  if (options.limit) {
    params.set("limit", String(options.limit));
  }
  if (options.offset) {
    params.set("offset", String(options.offset));
  }
  const query = params.toString();

  return requestJson(
    `/api/v1/admin/documents/${encodeURIComponent(documentId)}/chunks${query ? `?${query}` : ""}`,
    {
      method: "GET",
      headers: authHeaders(accessToken),
      signal: options.signal,
    },
  );
}

export async function listAllDocumentChunks(documentId, accessToken, options = {}) {
  const limit = options.limit || 200;
  const items = [];
  let offset = 0;
  let lastResponse = null;

  while (true) {
    lastResponse = await listDocumentChunks(documentId, accessToken, {
      ...options,
      limit,
      offset,
    });
    const batch = lastResponse.items || [];
    items.push(...batch);

    if (batch.length < limit) {
      return {
        ...lastResponse,
        items,
        offset: 0,
        limit,
      };
    }

    offset += limit;
  }
}

function authHeaders(accessToken) {
  return accessToken
    ? {
        Authorization: `Bearer ${accessToken}`,
      }
    : undefined;
}
