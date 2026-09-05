# visits-badge

A Cloudflare Worker serving a [shields.io endpoint](https://shields.io/badges/endpoint-badge)
badge with **real** traffic figures for `nikhilkolli.com`.

The point is that the number is measured. A plain hit-counter badge counts loads
of the badge image, so anyone can inflate it by refreshing — and it never sees
the website at all.

## Which dataset, and why not Web Analytics

Reads `httpRequests1dGroups` — the zone-level daily rollup behind the dashboard's
**Traffic** page.

The obvious choice was Web Analytics (`rumPageloadEventsAdaptiveGroups`), and it
was wrong. That dataset is a sampled JS beacon, and on this zone it:

- reported traffic on **3 days out of 30**, against ~40–95 real visitors *daily*;
- returned every count as a multiple of its sample interval, so any faithful
  total was a multiple of 100 — a number that cannot help but look invented;
- needed `count × avg(sampleInterval)` scaling that is easy to miss, and reads
  10× low if you do (the undercount still looks plausible, which is the trap).

The zone rollup is unsampled, matches the dashboard, and answers a whole year in
a single request.

| Window | Requests | Page views | Uniques |
| :--- | ---: | ---: | ---: |
| 30 days | 20,541 | 11,299 | 1,497 |
| All time | 49,230 | 30,877 | 4,632 |

Dashboard for the same 30 days: 20.76k requests, 1.53k unique visitors.

## Setup

**1. Create an API token.** Cloudflare → My Profile → API Tokens → Create Token →
Custom token:

| Section | Value |
| :--- | :--- |
| Permissions | `Zone` · `Analytics` · `Read` |
| **Zone Resources** | `Include` · `All zones` (or just this zone) |

**Zone Resources is a separate section, and skipping it is the failure mode to
watch for.** A token with the permission but no resource is *valid and active* —
`/user/tokens/verify` returns 200 — yet every zone query comes back as an empty
list with no error. It looks like "no data", not like "no access".

**2. Set `ZONE_TAG`** in `wrangler.jsonc`. Not a secret; dashboard sidebar, or
`GET /client/v4/zones`.

**3. Deploy.**

```bash
npx wrangler login
npx wrangler secret put CF_API_TOKEN
npx wrangler deploy
```

`secret put` prompts for the token and stores it encrypted. Note the prompt hides
input, and on Windows terminals a paste into it can silently register only a
single character — if the badge then fails, check `/?debug=1` before assuming the
token is wrong.

**4. Add the badge:**

```markdown
![Portfolio views](https://img.shields.io/endpoint?url=https%3A%2F%2Fnk-visits-badge.<subdomain>.workers.dev&style=for-the-badge)
```

## Checking it

```bash
curl 'https://nk-visits-badge.<subdomain>.workers.dev/?debug=1'
```

```json
{ "ok": true, "metric": "pageviews", "value": 30877,
  "totals": { "requests": 49230, "pageViews": 30877, "uniques": 4632 },
  "window": "all", "since": "2025-09-06" }
```

All three metrics come back every time, so the badge can be reconciled against
the dashboard without redeploying. `?days=N` overrides the window under debug.

## Reliability

Answering from the API on every cache miss made the badge intermittently render
`unavailable`. The last good figure is now kept for 30 days and served
immediately; once older than 10 minutes a refresh runs in the background behind
the response, and a failed refresh falls back to that figure rather than an
error. After the first success the badge goes stale, never broken.

## Local test, no token needed

```bash
cp .dev.vars.example .dev.vars     # uncomment GRAPHQL_URL
node test/mock-cf-api.mjs 8788     # --no-zone or --range-error
npx wrangler dev --port 8791 --local
curl 'http://127.0.0.1:8791/?debug=1'
```

`--no-zone` reproduces the empty-zone-list failure above, which is worth keeping
precisely because it is indistinguishable from success at the HTTP layer.

## Config

| Var | Required | Notes |
| :--- | :--- | :--- |
| `CF_API_TOKEN` | yes | **Secret.** Zone → Analytics → Read. |
| `ZONE_TAG` | yes | Not secret. |
| `DAYS` | no | Day count, or `all`. Default `30`. |
| `METRIC` | no | `pageviews`, `uniques`, or `requests`. Default `pageviews`. |
| `BADGE_LABEL` | no | Default `portfolio views`. |
| `BADGE_COLOR` | no | Default `818CF8`. |

## Known limit

`httpRequests1dGroups` refuses ranges wider than **52w1d**, so `all` looks back
365 days. Every figure above is well inside that. Once the site is more than a
year old, `all` will quietly mean "the last year" — at which point this needs
chunked queries plus a stored running total.
