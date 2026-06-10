import { API_BASE_URL } from "../config/env.js";

export class HttpError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = "HttpError";
    this.status = status;
    this.payload = payload;
  }
}

export async function requestJson(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  const text = await response.text();
  const payload = text ? safeParseJson(text) : null;

  if (!response.ok) {
    throw new HttpError(
      resolveErrorMessage(payload, response.statusText),
      response.status,
      payload,
    );
  }

  return payload;
}

function safeParseJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

function resolveErrorMessage(payload, fallback) {
  if (!payload) {
    return fallback || "Không nhận được phản hồi từ máy chủ.";
  }

  if (typeof payload.detail === "string") {
    return payload.detail;
  }

  if (Array.isArray(payload.detail)) {
    return payload.detail
      .map((item) => item.msg || item.message || String(item))
      .join("; ");
  }

  if (payload.message) {
    return payload.message;
  }

  return fallback || "Yêu cầu không thành công.";
}