/**
 * Serves a shields.io endpoint badge showing real Cloudflare Web Analytics
 * traffic for a site, so the README can display an actual measured number
 * rather than a hit counter that anyone could inflate by loading the image.
 *
 * GET /            -> shields endpoint JSON
 * GET /?debug=1    -> non-sensitive diagnostics (no token, no account id)
 *
 * Everything runs through the GraphQL Analytics API, which needs exactly one
 * token permission: Account -> Account Analytics -> Read. The REST management
 * endpoint (/rum/site_info) is deliberately not used - it requires a separate
 * permission and is not needed, since the site tag is available as a GraphQL
 * dimension.
 */

const GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql";

/** Overridable so the flow can be exercised against a mock in tests. */
const gqlUrl = (env) => env.GRAPHQL_URL || GRAPHQL_URL;

/** How long to hold a result before asking Cloudflare again. */
const CACHE_SECONDS = 600;

/**
 * Web Analytics retention is finite, so an "all time" total isn't available.
 * The badge reports a rolling window and says so in the label.
 */
const DEFAULT_DAYS = 30;

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const debug = url.searchParams.get("debug") === "1";

    const cache = caches.default;
    const cacheKey = new Request(new URL(url.pathname + url.search, url.origin), { method: "GET" });

    if (!debug) {
      const hit = await cache.match(cacheKey);
      if (hit) return hit;
    }

    let payload;
    try {
      const days = Number(env.DAYS) || DEFAULT_DAYS;
      const stats = await collect(env, days);
      payload = debug
        ? json({ ok: true, siteTag: mask(stats.siteTag), metric: stats.metric, value: stats.value, days })
        : json(badge(env, stats.value, days));
    } catch (err) {
      // A broken badge is worse than an honest one - render the failure.
      payload = debug
        ? json({ ok: false, error: String(err && err.message ? err.message : err) }, 500)
        : json({ schemaVersion: 1, label: label(env), message: "unavailable", color: "inactive" });
    }

    if (!debug && payload.status === 200) {
      payload.headers.set("Cache-Control", `public, max-age=${CACHE_SECONDS}`);
      ctx.waitUntil(cache.put(cacheKey, payload.clone()));
    }
    return payload;
  },
};

async function collect(env, days) {
  requireEnv(env, ["CF_API_TOKEN", "CF_ACCOUNT_ID"]);
  const { start, end } = window(days);
  return queryTraffic(env, env.SITE_TAG || null, start, end);
}

/**
 * Pull traffic grouped by site tag. Grouping rather than filtering means the
 * tag never has to be configured for a single-site account, and a multi-site
 * account gets a clear error naming its options instead of a silent wrong sum.
 *
 * Falls back from `sum { visits }` to the pageview `count` if the schema
 * rejects the field, so the badge still shows something true.
 */
async function queryTraffic(env, siteTag, start, end) {
  const build = (metricFields) => `
    query Visits($accountTag: string!, $start: Date!, $end: Date!) {
      viewer {
        accounts(filter: { accountTag: $accountTag }) {
          rumPageloadEventsAdaptiveGroups(
            filter: { date_geq: $start, date_leq: $end }
            limit: 100
          ) { ${metricFields} dimensions { siteTag } }
        }
      }
    }`;

  const vars = { accountTag: env.CF_ACCOUNT_ID, start, end };

  // Keep the first failure: if both attempts fail the cause is usually auth or
  // permissions, and that error is far more useful than the fallback's.
  let firstError = null;
  let rows = await graphql(env, build("count sum { visits }"), vars).catch((e) => {
    firstError = e;
    return null;
  });
  let metric = "visits";

  if (!rows) {
    rows = await graphql(env, build("count"), vars).catch((e) => {
      throw firstError || e;
    });
    metric = "pageviews";
  }

  const row = pickSite(rows, siteTag);
  if (!row) return { siteTag, metric, value: 0 };

  const visits = row.sum && typeof row.sum.visits === "number" ? row.sum.visits : null;
  if (metric === "visits" && visits === null) metric = "pageviews";

  return {
    siteTag: (row.dimensions && row.dimensions.siteTag) || siteTag,
    metric,
    value: metric === "visits" ? visits : row.count || 0,
  };
}

function pickSite(rows, siteTag) {
  if (!rows.length) return null;

  if (siteTag) {
    const match = rows.find((r) => r.dimensions && r.dimensions.siteTag === siteTag);
    if (!match) throw new Error(`SITE_TAG not found in analytics for this window`);
    return match;
  }

  if (rows.length === 1) return rows[0];

  const tags = rows.map((r) => (r.dimensions && r.dimensions.siteTag) || "?");
  throw new Error(`${rows.length} sites have data - set SITE_TAG to one of: ${tags.join(", ")}`);
}

async function graphql(env, query, variables) {
  const res = await fetch(gqlUrl(env), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ query, variables }),
  });

  const body = await readJson(res, "graphql");
  if (body.errors && body.errors.length) throw new Error(`GraphQL: ${summarize(body.errors)}`);
  if (!res.ok) throw new Error(`GraphQL HTTP ${res.status}`);

  const accounts = body.data && body.data.viewer && body.data.viewer.accounts;
  if (!accounts || !accounts.length) throw new Error("No account matched CF_ACCOUNT_ID");
  return accounts[0].rumPageloadEventsAdaptiveGroups || [];
}

/**
 * Cloudflare can answer with an empty body or an HTML error page. Parsing that
 * blind yields "Unexpected end of JSON input", which says nothing useful - so
 * surface the status and a snippet of what actually came back.
 */
async function readJson(res, what) {
  const text = await res.text();
  if (!text.trim()) {
    const ct = res.headers.get("content-type") || "none";
    throw new Error(`${what}: HTTP ${res.status} empty body (content-type: ${ct})`);
  }
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`${what}: HTTP ${res.status} non-JSON: ${text.slice(0, 140)}`);
  }
}

/** Inclusive date window ending today, in the YYYY-MM-DD the API expects. */
function window(days) {
  const end = new Date();
  const start = new Date(end.getTime() - (days - 1) * 86400000);
  const iso = (d) => d.toISOString().slice(0, 10);
  return { start: iso(start), end: iso(end) };
}

function badge(env, value, days) {
  return {
    schemaVersion: 1,
    label: label(env, days),
    message: new Intl.NumberFormat("en-US").format(value),
    color: env.BADGE_COLOR || "818CF8",
  };
}

function label(env, days) {
  if (env.BADGE_LABEL) return env.BADGE_LABEL;
  return days ? `site visits · ${days}d` : "site visits";
}

function requireEnv(env, keys) {
  const missing = keys.filter((k) => !env[k]);
  if (missing.length) throw new Error(`Missing config: ${missing.join(", ")}`);
}

function summarize(errors) {
  if (!errors || !errors.length) return "";
  return errors.map((e) => e.message).join("; ").slice(0, 200);
}

/** Never echo identifiers back in full from a public endpoint. */
function mask(tag) {
  return tag ? `${tag.slice(0, 4)}…${tag.slice(-4)}` : null;
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Access-Control-Allow-Origin": "*",
    },
  });
}
