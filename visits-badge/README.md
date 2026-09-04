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
                     +-- resolves site_tag from SITE_HOST (cached 10 min)
```

The beacon's `site_token` (public, in your page source) is **not** the `site_tag`
the analytics dataset filters on, so the Worker looks the tag up by hostname via
`/rum/site_info/list` rather than making you find it by hand.

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
secret; find it in the dashboard sidebar of any domain.

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

`test/mock-cf-api.mjs` stands in for the Cloudflare API so the whole path can be
exercised offline — site-tag discovery, the GraphQL query, and the visits →
pageviews fallback.

```bash
cp .dev.vars.example .dev.vars     # then uncomment API_BASE and GRAPHQL_URL
node test/mock-cf-api.mjs 8788     # add --no-visits to exercise the fallback
npx wrangler dev --port 8791 --local
curl 'http://127.0.0.1:8791/?debug=1'
```

## Config

| Var | Required | Notes |
| :--- | :--- | :--- |
| `CF_API_TOKEN` | yes | **Secret.** Account Analytics → Read. |
| `CF_ACCOUNT_ID` | yes | Not secret. |
| `SITE_HOST` | yes* | Hostname in Web Analytics. \*Unless `SITE_TAG` is set. |
| `SITE_TAG` | no | Skips the lookup. |
| `DAYS` | no | Rolling window, default `30`. |
| `BADGE_LABEL` | no | Default `site visits · <days>d`. |
| `BADGE_COLOR` | no | Default `818CF8`. |

## Why a rolling window

Cloudflare Web Analytics retention is finite, so there is no meaningful all-time
total to report. The badge shows a window and says so in its label.
