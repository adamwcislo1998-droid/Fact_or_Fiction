// Node's built-in test runner verifies Reddit parsing without browser APIs or
// third-party npm packages. Fixtures imitate the relevant Reddit JSON shape.

import test from "node:test";
import assert from "node:assert/strict";

import { buildJsonUrl, parseRedditThread } from "../common/redditClient.js";


// Query/tracking parameters should be discarded while the thread path becomes
// a .json endpoint with the configured comment limit.
test("buildJsonUrl converts a Reddit permalink into a JSON request", () => {
  const output = buildJsonUrl(
    "https://www.reddit.com/r/example/comments/abc123/example_title/?utm_source=test"
  );
  assert.match(output, /comments\/abc123\/example_title\.json/);
  assert.match(output, /limit=75/);
});


// The recursive parser must retain a nested reply and ignore a deleted body.
test("parseRedditThread recursively captures nested comments", () => {
  const payload = [
    {
      data: {
        children: [
          {
            kind: "t3",
            data: {
              title: "Example title",
              selftext: "Example body",
              permalink: "/r/example/comments/abc123/example_title/",
              num_comments: 3,
            },
          },
        ],
      },
    },
    {
      data: {
        children: [
          {
            kind: "t1",
            data: {
              body: "Top-level comment",
              author: "one",
              score: 10,
              depth: 0,
              replies: {
                data: {
                  children: [
                    {
                      kind: "t1",
                      data: {
                        body: "Nested reply",
                        author: "two",
                        score: 4,
                        depth: 1,
                        replies: "",
                      },
                    },
                  ],
                },
              },
            },
          },
          {
            kind: "t1",
            data: {
              body: "[deleted]",
              author: null,
              replies: "",
            },
          },
        ],
      },
    },
  ];

  const result = parseRedditThread(
    payload,
    "https://www.reddit.com/r/example/comments/abc123/example_title/"
  );

  assert.equal(result.title, "Example title");
  assert.deepEqual(
    result.comments.map((comment) => comment.text),
    ["Top-level comment", "Nested reply"]
  );
  assert.equal(result.comments[1].depth, 1);
  assert.equal(result.extraction.method, "reddit_json");
  assert.equal(result.extraction.commentsCaptured, 2);
});
