/**
 * Serves a shields.io endpoint badge showing real Cloudflare Web Analytics
 * traffic for a site, so the README can display an actual measured number
 * rather than a hit counter that anyone could inflate by loading the image.
 *
 * GET /            -> shields endpoint JSON
 * GET /?debug=1    -> non-sensitive diagnostics (no token, no account id)
 */

const GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql";
const API_BASE = "https://api.cloudflare.com/client/v4";

/** Overridable so the flow can be exercised against a mock in tests. */
const gqlUrl = (env) => env.GRAPHQL_URL || GRAPHQL_URL;
const apiBase = (env) => env.API_BASE || API_BASE;

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

/** Resolve the site tag, then pull the traffic number for the window. */
async function collect(env, days) {
  requireEnv(env, ["CF_API_TOKEN", "CF_ACCOUNT_ID"]);

  const siteTag = env.SITE_TAG || (await discoverSiteTag(env));
  const { start, end } = window(days);
  const { metric, value } = await queryTraffic(env, siteTag, start, end);
  return { siteTag, metric, value };
}

/**
 * The beacon's site_token is not the site_tag the analytics dataset filters
 * on, so look the tag up by hostname instead of asking the user for it.
 */
async function discoverSiteTag(env) {
  const host = env.SITE_HOST;
  if (!host) throw new Error("Set SITE_HOST (or SITE_TAG) in wrangler.jsonc");

  const res = await fetch(`${apiBase(env)}/accounts/${env.CF_ACCOUNT_ID}/rum/site_info/list`, {
    headers: { Authorization: `Bearer ${env.CF_API_TOKEN}` },
  });
  const body = await res.json();
  if (!res.ok || !body.success) {
    throw new Error(`site_info/list failed: ${summarize(body.errors) || res.status}`);
  }

  const sites = body.result || [];
  const match = sites.find((s) => hostOf(s) === host) || sites.find((s) => (hostOf(s) || "").endsWith(host));
  if (!match) {
    throw new Error(`No Web Analytics site matching "${host}" (found: ${sites.map(hostOf).join(", ") || "none"})`);
  }
  return match.site_tag;
}

function hostOf(site) {
  return site.host || (site.ruleset && site.ruleset.zone_name) || "";
}

/**
 * Ask for visits and pageviews together; if the schema rejects `sum { visits }`
 * fall back to the pageview count so the badge still renders something true.
 */
async function queryTraffic(env, siteTag, start, end) {
  const full = `
    query Visits($accountTag: string!, $siteTag: string!, $start: Date!, $end: Date!) {
      viewer {
        accounts(filter: { accountTag: $accountTag }) {
          rumPageloadEventsAdaptiveGroups(
            filter: { siteTag: $siteTag, date_geq: $start, date_leq: $end }
            limit: 1
          ) { count sum { visits } }
        }
      }
    }`;

  const countOnly = full.replace("{ count sum { visits } }", "{ count }");
  const vars = { accountTag: env.CF_ACCOUNT_ID, siteTag, start, end };

  let groups = await graphql(env, full, vars).catch(() => null);
  let metric = "visits";

  if (!groups) {
    groups = await graphql(env, countOnly, vars);
    metric = "pageviews";
  }

  const row = groups[0];
  if (!row) return { metric, value: 0 };

  const visits = row.sum && typeof row.sum.visits === "number" ? row.sum.visits : null;
  if (metric === "visits" && visits === null) metric = "pageviews";
  return { metric, value: metric === "visits" ? visits : row.count || 0 };
}

async function graphql(env, query, variables) {
  const res = await fetch(gqlUrl(env), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query, variables }),
  });

  const body = await res.json();
  if (body.errors && body.errors.length) throw new Error(summarize(body.errors));
  if (!res.ok) throw new Error(`GraphQL HTTP ${res.status}`);

  const accounts = body.data && body.data.viewer && body.data.viewer.accounts;
  if (!accounts || !accounts.length) throw new Error("No account matched CF_ACCOUNT_ID");
  return accounts[0].rumPageloadEventsAdaptiveGroups || [];
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
