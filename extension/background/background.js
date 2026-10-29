// Manifest V3 background service worker.
// It coordinates the popup, active Reddit tab, primary/fallback extraction,
// backend analysis and storage of the latest result.

import { analyse, healthCheck } from "../common/apiClient.js";
import { fetchRedditThread } from "../common/redditClient.js";
import { CONFIG } from "../common/config.js";

// Request the selected tab in the current browser window.
async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url) {
    throw new Error("No active browser tab is available.");
  }
  return tab;
}

// Fail early with a clear message unless an individual reddit.com thread is open.
function assertSupportedRedditUrl(url) {
  const parsed = new URL(url);
  const supportedHost = /^(www\.|old\.)?reddit\.com$/i.test(parsed.hostname);
  if (!supportedHost || !/\/comments\//i.test(parsed.pathname)) {
    throw new Error("Open an individual Reddit post before running the analysis.");
  }
}

// Ask the content script to inspect rendered HTML. Promise.race supplies a
// timeout because a missing/unresponsive content script would otherwise hang.
async function getDomFallback(tabId) {
  const timeout = new Promise((_, reject) => {
    setTimeout(
      () => reject(new Error("The Reddit page did not respond in time.")),
      CONFIG.CONTENT_SCRIPT_TIMEOUT_MS
    );
  });

  const response = await Promise.race([
    chrome.tabs.sendMessage(tabId, { type: "GET_REDDIT_PAGE_DATA" }),
    timeout,
  ]);

  if (!response?.ok) {
    throw new Error(response?.error || "The content script could not read the Reddit page.");
  }
  return response.data;
}

// Prefer structured Reddit JSON. If it fails, retain the reason in extraction
// metadata and use the DOM fallback rather than failing the whole operation.
async function collectRedditData(tab) {
  let jsonError = null;
  try {
    return await fetchRedditThread(tab.url);
  } catch (error) {
    jsonError = String(error?.message || error);
  }

  const domData = await getDomFallback(tab.id);
  return {
    ...domData,
    extraction: {
      ...(domData.extraction || {}),
      primaryMethodFailed: "reddit_json",
      primaryMethodError: jsonError,
    },
  };
}

// Complete one user operation: locate tab, capture data, call Flask and save a
// lightweight record of the latest analysis in extension-local storage.
async function analyseCurrentPage() {
  const tab = await getActiveTab();
  assertSupportedRedditUrl(tab.url);

  const pageData = await collectRedditData(tab);
  const result = await analyse(pageData);

  await chrome.storage.local.set({
    lastAnalysis: {
      url: tab.url,
      analysedAt: new Date().toISOString(),
      result,
      extraction: pageData.extraction,
    },
  });

  return { result, pageData };
}

// Central message router used by popup.js. The async IIFE allows await inside
// the callback. Returning true keeps Chrome's response channel open.
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    try {
      // Optional chaining tolerates a malformed/missing message object.
      switch (message?.type) {
        case "PING_BACKEND":
          sendResponse({ ok: true, data: await healthCheck() });
          break;
        case "ANALYSE_CURRENT_PAGE":
          sendResponse({ ok: true, ...(await analyseCurrentPage()) });
          break;
        // Braces create a local block for the ``stored`` constant.
        case "GET_LAST_ANALYSIS": {
          const stored = await chrome.storage.local.get("lastAnalysis");
          sendResponse({ ok: true, data: stored.lastAnalysis || null });
          break;
        }
        default:
          sendResponse({ ok: false, error: "Unknown extension message type." });
      }
    } catch (error) {
      sendResponse({ ok: false, error: String(error?.message || error) });
    }
  })();

  return true;
});
