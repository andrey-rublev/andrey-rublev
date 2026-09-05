# visits-badge

A Cloudflare Worker that serves a [shields.io endpoint](https://shields.io/badges/endpoint-badge)
badge showing **real** Cloudflare Web Analytics traffic for `nikhilkolli.com`.

The point is that the number is measured. A plain hit-counter badge counts loads of
the badge image, so anyone can inflate it by refreshing — and it never sees the
website at all. This reads the actual analytics instead.

## How it works

```
shields.io  ->  this Worker  ->  Cloudflare GraphQL Analytics API
                     |
                     +-- site tag read from grouped dimensions (cached 10 min)
```

Everything goes through the GraphQL Analytics API. The site tag comes back as a
grouped dimension, so nothing needs configuring for a single-site account — and
the REST management endpoint (`/rum/site_info`) is deliberately avoided, since it
needs a second, broader token permission that the badge has no use for.

(The `site_token` in your page source is a different value from the `site_tag`
the analytics dataset uses — worth knowing if you ever query this by hand.)

If the schema rejects `sum { visits }`, it retries with the pageview `count` and
relabels the metric, so the badge still shows something true rather than breaking.
If anything else fails it renders a grey `unavailable` badge — never a broken image.

## Setup

**1. Create an API token.** Cloudflare dashboard → My Profile → API Tokens →
Create Token → Custom token. It needs exactly one permission:

| Scope | Resource | Level |
| :--- | :--- | :--- |
| Account | Account Analytics | Read |

**2. Set your account id** in `wrangler.jsonc` → `vars.CF_ACCOUNT_ID`. It is not a
secret; find it in the dashboard sidebar of any domain, or run `wrangler whoami`.

**3. Deploy.**

```bash
npx wrangler login
npx wrangler secret put CF_API_TOKEN
npx wrangler deploy
```

`secret put` prompts for the token and stores it encrypted — it never goes in the
repo. Do not put it in `wrangler.jsonc`.

**4. Add the badge**, using the `workers.dev` URL from the deploy output:

```markdown
![Site visits](https://img.shields.io/endpoint?url=https://nk-visits-badge.<subdomain>.workers.dev&style=for-the-badge)
```

## Checking it

```bash
curl 'https://nk-visits-badge.<subdomain>.workers.dev/?debug=1'
```

Returns the resolved metric and value, with the site tag masked:

```json
{ "ok": true, "siteTag": "abcd…1234", "metric": "visits", "value": 1337, "days": 30 }
```

On failure it returns `{ "ok": false, "error": "..." }` with the reason.

## Local test, no token needed

`test/mock-cf-api.mjs` stands in for the Cloudflare GraphQL API so the whole path
can be exercised offline — site-tag discovery, the query, and the visits →
pageviews fallback.

```bash
cp .dev.vars.example .dev.vars     # then uncomment GRAPHQL_URL
node test/mock-cf-api.mjs 8788     # --no-visits or --multi-site to vary it
npx wrangler dev --port 8791 --local
curl 'http://127.0.0.1:8791/?debug=1'
```

## Config

| Var | Required | Notes |
| :--- | :--- | :--- |
| `CF_API_TOKEN` | yes | **Secret.** Account Analytics → Read. |
| `CF_ACCOUNT_ID` | yes | Not secret. |
| `SITE_TAG` | no | Only needed if more than one site has data. |
| `DAYS` | no | Day count, or `all`. Default `30`. |
| `METRIC` | no | `pageviews` or `visits` (sessions). Default `visits`. |
| `BADGE_LABEL` | no | Default `site visits · <days>d`. |
| `BADGE_COLOR` | no | Default `818CF8`. |

## All-time totals

Cloudflare refuses any single query wider than **13w2d** (93 days), so `DAYS=all`
walks backwards in 90-day chunks and sums them, stopping after two consecutive
empty chunks or when a range is refused for having aged out of retention.

That makes the total complete for any site whose history is still within
retention. For an older site it becomes "as far back as Cloudflare still has",
which is the most that can honestly be claimed — `/?debug=1` reports `chunks`
and `oldestDay` so you can see how far it actually reached.

Each cache miss costs one API call per chunk, bounded at 16.
