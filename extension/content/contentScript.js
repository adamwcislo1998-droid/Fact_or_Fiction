// DOM fallback extractor injected into Reddit pages.
// It supports current Reddit web components, the previous redesign and old
// Reddit. It is used only when the cleaner Reddit JSON request fails.

// Keep capture bounded and allow a brief wait for Reddit's dynamic rendering.
const MAX_COMMENTS = 75;
const COMMENT_WAIT_MS = 2200;

// Shared text cleanup prevents whitespace-only values and unstable formatting.
function normaliseText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

// Prefer innerText (visible rendered text), falling back to textContent.
function textOf(element) {
  return normaliseText(element?.innerText || element?.textContent || "");
}

// Try selectors in priority order and remember which one succeeded for
// diagnostic extraction metadata.
function firstText(selectors, root = document) {
  for (const selector of selectors) {
    const text = textOf(root.querySelector(selector));
    if (text) return { text, selector };
  }
  return { text: "", selector: null };
}

// Try title/body selectors from multiple Reddit generations.
function extractPost() {
  const titleResult = firstText([
    'shreddit-post h1[slot="title"]',
    'h1[slot="title"]',
    'shreddit-post [slot="title"]',
    'a[id^="post-title"]',
    '.thing.link .top-matter a.title',
    'main h1',
  ]);

  const bodyResult = firstText([
    'shreddit-post-text-body [id$="-post-rtjson-content"]',
    'shreddit-post-text-body .md',
    'shreddit-post [slot="text-body"]',
    '[data-testid="post-content"]',
    'article [data-click-id="text"]',
    '.thing.link .usertext-body .md',
  ]);

  return {
    title: titleResult.text,
    body: bodyResult.text,
    titleSelector: titleResult.selector,
    bodySelector: bodyResult.selector,
  };
}

// Current Reddit uses <shreddit-comment> custom elements with useful metadata
// stored in attributes.
function extractCurrentRedditComments() {
  const comments = [];
  const nodes = document.querySelectorAll("shreddit-comment");

  for (const node of nodes) {
    const body = firstText(
      [
        'div[slot="comment"]',
        '.md[slot="comment"]',
        'div[id$="-comment-rtjson-content"]',
        '[shreddit-comment-content]',
        '[slot="comment-body"]',
      ],
      node
    );
    if (!body.text) continue;

    comments.push({
      text: body.text,
      author: normaliseText(node.getAttribute("author")) || null,
      score: parseOptionalInteger(node.getAttribute("score")),
      depth: parseOptionalInteger(node.getAttribute("depth")),
      sourceSelector: body.selector,
    });
  }

  return comments;
}

// Previous redesign fallback; text is more reliable than author/score metadata.
function extractRedesignComments() {
  const comments = [];
  const nodes = document.querySelectorAll('[data-testid="comment"]');

  for (const node of nodes) {
    const body = firstText(
      [
        '[data-click-id="text"]',
        '.RichTextJSON-root',
        '.md',
        '[data-testid="comment-content"]',
      ],
      node
    );
    if (!body.text) continue;
    comments.push({ text: body.text, sourceSelector: body.selector });
  }

  return comments;
}

// Old Reddit uses conventional .thing/.usertext CSS structures.
function extractOldRedditComments() {
  const comments = [];
  const nodes = document.querySelectorAll('.thing.comment, .commentarea .comment');

  for (const node of nodes) {
    const body = firstText(['.usertext-body .md', '.entry .usertext-body'], node);
    if (!body.text) continue;
    comments.push({
      text: body.text,
      author: textOf(node.querySelector('.author')) || null,
      score: parseScoreText(textOf(node.querySelector('.score.unvoted, .score'))),
      depth: null,
      sourceSelector: body.selector,
    });
  }

  return comments;
}

// Merge every layout-specific result, deduplicate exact normalised text and stop
// at the configured maximum.
function extractComments() {
  const candidates = [
    ...extractCurrentRedditComments(),
    ...extractRedesignComments(),
    ...extractOldRedditComments(),
  ];

  const seen = new Set();
  const deduplicated = [];
  for (const comment of candidates) {
    const key = normaliseText(comment.text).toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    deduplicated.push(comment);
    if (deduplicated.length >= MAX_COMMENTS) break;
  }
  return deduplicated;
}

// Reddit renders asynchronously. Poll for up to 2.2 seconds and stop early once
// post text and at least one comment are available.
async function waitForRedditContent() {
  const deadline = Date.now() + COMMENT_WAIT_MS;
  let post = extractPost();
  let comments = extractComments();

  while (Date.now() < deadline) {
    if ((post.title || post.body) && comments.length > 0) break;
    await new Promise((resolve) => setTimeout(resolve, 200));
    post = extractPost();
    comments = extractComments();
  }

  return { post, comments };
}

// Build the backend payload and strip the internal sourceSelector field from
// individual comments before returning it.
async function getRedditPageData() {
  const { post, comments } = await waitForRedditContent();
  if (!post.title && !post.body) {
    throw new Error("Could not capture the Reddit post title or body from this page.");
  }

  return {
    url: location.href,
    title: post.title,
    body: post.body,
    comments: comments.map(({ sourceSelector: _sourceSelector, ...comment }) => comment),
    extraction: {
      method: "dom_fallback",
      commentsCaptured: comments.length,
      titleSelector: post.titleSelector,
      bodySelector: post.bodySelector,
      commentSelectors: [...new Set(comments.map((comment) => comment.sourceSelector).filter(Boolean))],
      redditLayout: detectLayout(),
    },
  };
}

// Report which selector family appears to match the page for debugging/evaluation.
function detectLayout() {
  if (document.querySelector("shreddit-app, shreddit-post")) return "current_reddit";
  if (document.querySelector("#siteTable, .thing.link")) return "old_reddit";
  return "reddit_redesign_or_unknown";
}

// Convert attribute text into an integer or null. Metadata is optional and does
// not currently influence scoring.
function parseOptionalInteger(value) {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number.parseInt(String(value).replace(/[^\d-]/g, ""), 10);
  return Number.isFinite(parsed) ? parsed : null;
}

// Old Reddit score text can include words; select its first signed integer.
function parseScoreText(value) {
  const match = String(value || "").match(/-?\d+/);
  return match ? Number.parseInt(match[0], 10) : null;
}

// Respond only to the extraction request. Returning true is required because
// getRedditPageData resolves asynchronously after the listener returns.
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "GET_REDDIT_PAGE_DATA") return false;

  getRedditPageData()
    .then((data) => sendResponse({ ok: true, data }))
    .catch((error) => sendResponse({ ok: false, error: String(error?.message || error) }));

  return true;
});
