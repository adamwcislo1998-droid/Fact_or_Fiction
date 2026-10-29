// Shared extension configuration.
// Object.freeze prevents accidental runtime mutation of addresses or limits.
// These limits mirror backend defaults so capture and validation agree.

export const CONFIG = Object.freeze({
  BACKEND_BASE_URL: "http://127.0.0.1:5000/api/v1",
  MAX_COMMENTS: 75,
  REDDIT_JSON_TIMEOUT_MS: 5000,
  CONTENT_SCRIPT_TIMEOUT_MS: 5000,
});
