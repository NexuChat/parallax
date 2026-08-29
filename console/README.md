# Parallax live console

Open `index.html` directly in a browser for the dependable offline demo. It immediately renders a built-in copy of the sample run, so browsers that block `fetch()` from `file://` still show a complete operations wall. For a real feed, serve this directory with any static web server and use `?feed=URL`.

Examples:

```text
index.html
index.html?feed=fixtures/feed.jsonl
index.html?feed=http://localhost:8080/feed
```

The feed is newline-delimited JSON (`.jsonl`). Each line is one frozen `FeedEvent`:

```json
{"kind":"mosaic","at":"2026-08-29T16:04:01Z","payload":{"seq":42,"image":"https://…/mosaic.jpg","tiles":[{"context":"owner-en-light-desktop","x":0,"y":0,"w":350,"h":400}]}}
{"kind":"finding","at":"2026-08-29T16:04:03Z","payload":{"id":"drift-locale-…","kind":"drift","severity":"high","axis":"locale","surface":"/billing","surface_id":"…","summary":"Arabic witness was redirected from billing.","evidence":"owner-en-light-desktop=reached · owner-ar-light-desktop=blocked","witnesses":["owner-en-light-desktop","owner-ar-light-desktop"]}}
{"kind":"status","at":"2026-08-29T16:04:04Z","payload":{"state":"running","message":"Seven witnesses settled"}}
```

`mosaic.image` may be an HTTP(S), relative, `data:` image URL, or a file-relative image URL. Tile coordinates are source-image pixels; the console measures the displayed image and scales every overlay from its natural dimensions. Findings are appended without re-rendering the existing list, newest first, and their `witnesses` activate the corresponding mosaic tiles.

For a static URL the console polls with byte ranges where the server supports them, otherwise it only processes appended lines. It also attempts SSE at the same `?feed` URL shape; malformed events/lines are ignored and leave the current display intact.
