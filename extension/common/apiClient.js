// HTTP client for the local Flask backend.
// Keeping fetch/error handling here avoids duplicating network logic in the
// popup and background service worker.

import { CONFIG } from "./config.js";

// Perform a request, distinguish network/JSON/API errors and return parsed data.
async function requestJson(url, options = {}) {
  let response;
  try {
    // A rejected fetch means the backend could not be reached at all.
    response = await fetch(url, options);
  } catch (error) {
    throw new Error(
      "Could not reach the local backend. Start backend/app.py and try again."
    );
  }

  // A reachable server can still return HTML or malformed JSON; handle that as
  // a separate, clearer error for the user.
  let data;
  try {
    data = await response.json();
  } catch (_error) {
    throw new Error(`The backend returned an invalid response (${response.status}).`);
  }

  // Respect both HTTP status and the project's explicit ``ok`` field.
  if (!response.ok || data?.ok === false) {
    const message = data?.error?.message || data?.error || `Request failed (${response.status}).`;
    throw new Error(message);
  }
  return data;
}

// GET has no request body and disables cache so status is current.
export function healthCheck() {
  return requestJson(`${CONFIG.BACKEND_BASE_URL}/health`, {
    method: "GET",
    cache: "no-store",
  });
}

// POST serialises the captured Reddit object and declares JSON content.
export function analyse(payload) {
  return requestJson(`${CONFIG.BACKEND_BASE_URL}/analyse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
