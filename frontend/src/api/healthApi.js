import { requestJson } from "./http.js";

export function getHealth(options = {}) {
  return requestJson("/health", {
    method: "GET",
    signal: options.signal,
  });
}
