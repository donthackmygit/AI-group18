import { DEFAULT_CHAT_OPTIONS } from "../config/env.js";
import { requestJson } from "./http.js";

export function sendChatMessage(payload, options = {}) {
  const body = {
    ...DEFAULT_CHAT_OPTIONS,
    ...payload,
  };

  return requestJson("/api/v1/chat", {
    method: "POST",
    headers: options.accessToken
      ? {
          Authorization: `Bearer ${options.accessToken}`,
        }
      : undefined,
    body: JSON.stringify(body),
    signal: options.signal,
  });
}
