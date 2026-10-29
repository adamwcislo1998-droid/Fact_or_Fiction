// Primary Reddit extractor.
// Reddit's structured .json representation is attempted before DOM scraping
// because it is less dependent on changing page layouts and supports replies.

import { CONFIG } from "./config.js";

// Fetch one thread with an AbortController-enforced timeout.
export async function fetchRedditThread(url) {
  const jsonUrl = buildJsonUrl(url);
  // AbortController lets the extension cancel a stalled network request instead
  // of leaving the popup waiting indefinitely.
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), CONFIG.REDDIT_JSON_TIMEOUT_MS);

  try {
    // Omit credentials and cached copies; only public thread JSON is required.
    const response = await fetch(jsonUrl, {
      method: "GET",
      headers: { Accept: "application/json" },
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`Reddit JSON request failed (${response.status}).`);
    }

    const payload = await response.json();
    return parseRedditThread(payload, url);
  } finally {
    // Always release the timer whether fetch succeeded, failed or was aborted.
    clearTimeout(timeout);
  }
}

// Validate that the active page is an individual supported Reddit thread and
// convert its clean pathname into Reddit's JSON endpoint.
export function buildJsonUrl(inputUrl) {
  const url = new URL(inputUrl);
  if (!/^(www\.|old\.)?reddit\.com$/i.test(url.hostname)) {
    throw new Error("The active page is not a supported Reddit page.");
  }
  if (!/\/comments\//i.test(url.pathname)) {
    throw new Error("Open an individual Reddit post before running the analysis.");
  }

  const cleanPath = url.pathname.replace(/\/+$/, "");
  return `https://www.reddit.com${cleanPath}.json?raw_json=1&limit=${CONFIG.MAX_COMMENTS}&sort=top`;
}

// Convert Reddit's two-listing response (post listing + comments listing) into
// the simpler shape expected by the Python backend.
export function parseRedditThread(payload, sourceUrl) {
  if (!Array.isArray(payload) || payload.length < 2) {
    throw new Error("Reddit returned an unexpected thread format.");
  }

  // The first child of the first listing is the post object.
  const post = payload[0]?.data?.children?.[0]?.data;
  if (!post) {
    throw new Error("The Reddit post could not be found in the JSON response.");
  }

  // Recursively collect t1 comment objects, including nested replies.
  const comments = [];
  walkCommentChildren(payload[1]?.data?.children || [], comments, 0);

  return {
    url: post.url_overridden_by_dest || sourceUrl,
    redditPermalink: post.permalink ? `https://www.reddit.com${post.permalink}` : sourceUrl,
    title: normaliseText(post.title),
    body: normaliseText(post.selftext),
    comments: comments.slice(0, CONFIG.MAX_COMMENTS),
    extraction: {
      method: "reddit_json",
      commentsCaptured: Math.min(comments.length, CONFIG.MAX_COMMENTS),
      totalCommentCountReported: Number.isFinite(post.num_comments) ? post.num_comments : null,
      truncated: comments.length > CONFIG.MAX_COMMENTS,
    },
  };
}

// Depth-first traversal stops at MAX_COMMENTS, ignores non-comment placeholders
// such as Reddit "more" objects, and skips deleted/removed bodies.
function walkCommentChildren(children, output, depth) {
  for (const child of children) {
    if (output.length >= CONFIG.MAX_COMMENTS) return;
    if (child?.kind !== "t1" || !child.data) continue;

    const data = child.data;
    const text = normaliseText(data.body);
    if (text && text !== "[deleted]" && text !== "[removed]") {
      output.push({
        text,
        author: normaliseText(data.author) || null,
        score: Number.isFinite(data.score) ? data.score : null,
        depth: Number.isFinite(data.depth) ? data.depth : depth,
      });
    }

    const replies = data.replies;
    if (replies && typeof replies === "object") {
      walkCommentChildren(replies?.data?.children || [], output, depth + 1);
    }
  }
}

// Convert null/undefined safely, collapse whitespace and trim page/API text.
function normaliseText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}
