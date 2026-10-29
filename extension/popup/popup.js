// Controller for the extension popup.
// It checks backend availability, starts analysis and safely constructs the
// visible result without injecting untrusted Reddit text as HTML.

// Cache frequently accessed DOM nodes once when the module loads.
const analyseBtn = document.getElementById("analyseBtn");
const statusEl = document.getElementById("status");
const backendStatusEl = document.getElementById("backendStatus");
const backendDotEl = document.getElementById("backendDot");
const resultPanel = document.getElementById("resultPanel");

// Update operation feedback and toggle the error visual state.
function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("status-text--error", isError);
}

// Update both status wording and the dot colour class.
function setBackendStatus(message, state) {
  backendStatusEl.textContent = message;
  backendDotEl.className = `status-dot status-dot--${state}`;
}

// Ask the background worker to call Flask's health endpoint.
async function checkBackend() {
  setBackendStatus("Checking local backend", "pending");
  const response = await chrome.runtime.sendMessage({ type: "PING_BACKEND" });
  if (!response?.ok) {
    setBackendStatus("Backend unavailable", "error");
    return false;
  }
  setBackendStatus(
    response.data.transformer_enabled
      ? "Backend ready; transformer enabled"
      : "Backend ready; standard analysis mode",
    "ok"
  );
  return true;
}

// Populate every result field. textContent/createElement are used instead of
// innerHTML so captured user content cannot become executable markup.
function renderResult(result, pageData) {
  resultPanel.hidden = false;
  document.getElementById("scoreValue").textContent = `${result.score_percent}/100`;
  document.getElementById("scoreLabel").textContent = result.label;
  document.getElementById("confidenceLabel").textContent = `${result.assessment_confidence} assessment confidence`;
  document.getElementById("summary").textContent = result.summary;
  document.getElementById("commentCount").textContent = result.comment_analysis.captured_count;
  document.getElementById("linkCount").textContent = result.post_analysis.link_count;
  document.getElementById("extractionMethod").textContent = friendlyMethod(
    pageData?.extraction?.method || result.input_summary?.extraction?.method
  );

  // Clamp marker position even if a malformed response leaves the expected range.
  const marker = document.getElementById("scoreMarker");
  marker.style.left = `${Math.max(0, Math.min(100, result.score_percent))}%`;

  // Backend already orders indicators by absolute influence. Display the first
  // six non-neutral items to keep the compact popup readable.
  const indicatorList = document.getElementById("indicatorList");
  indicatorList.replaceChildren();
  for (const indicator of result.indicators.filter((item) => item.contribution !== 0).slice(0, 6)) {
    const card = document.createElement("article");
    card.className = `indicator indicator--${indicator.direction}`;

    const top = document.createElement("div");
    top.className = "indicator__top";

    const name = document.createElement("span");
    name.className = "indicator__name";
    name.textContent = titleCase(indicator.id);

    const weight = document.createElement("span");
    weight.className = "indicator__weight";
    // The backend's -1..+1 contribution scale maps to +/-50 display points.
    const points = Math.round(indicator.contribution * 50);
    weight.textContent = `${points >= 0 ? "+" : ""}${points} points`;

    const explanation = document.createElement("p");
    explanation.textContent = indicator.explanation;

    top.append(name, weight);
    card.append(top, explanation);
    indicatorList.append(card);
  }

  const limitationsList = document.getElementById("limitationsList");
  limitationsList.replaceChildren();
  for (const limitation of result.limitations) {
    const item = document.createElement("li");
    item.textContent = limitation;
    limitationsList.append(item);
  }
}

// Translate internal extraction identifiers into user-facing labels.
function friendlyMethod(method) {
  if (method === "reddit_json") return "Reddit JSON";
  if (method === "dom_fallback") return "page DOM";
  return "unknown";
}

// Convert snake_case indicator IDs into readable headings.
function titleCase(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

// Disable the button for the whole asynchronous operation to prevent duplicate
// requests. ``finally`` restores it after either success or failure.
analyseBtn.addEventListener("click", async () => {
  analyseBtn.disabled = true;
  setStatus("Capturing the post and comments, then running the analysis.");

  try {
    const response = await chrome.runtime.sendMessage({ type: "ANALYSE_CURRENT_PAGE" });
    if (!response?.ok) throw new Error(response?.error || "Analysis failed.");
    renderResult(response.result, response.pageData);
    setStatus("Analysis complete.");
  } catch (error) {
    setStatus(String(error?.message || error), true);
  } finally {
    analyseBtn.disabled = false;
  }
});

// Check backend status as soon as the popup document is ready.
document.addEventListener("DOMContentLoaded", () => {
  checkBackend().catch((error) => {
    setBackendStatus(String(error?.message || error), "error");
  });
});
