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

const CACHE_SECONDS = 600;
const DEFAULT_DAYS = 30;

/**
 * Cloudflare refuses any single query wider than 13w2d (93 days), so an
 * all-time total is assembled from consecutive chunks walked backwards.
 * 90 keeps a safe margin under the cap.
 */
const CHUNK_DAYS = 90;

/** Bounds the walk so a cache miss can never fan out indefinitely. */
const MAX_CHUNKS = 16;

/** Stop after this many consecutive empty chunks, to tolerate quiet gaps. */
const EMPTY_CHUNKS_BEFORE_STOP = 2;

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
      // Debug-only: per-day rows, to check whether sampleInterval varies.
      if (debug && url.searchParams.get("breakdown") === "1") {
        const days = Number(url.searchParams.get("days")) || 30;
        const end = today();
        const start = shiftDays(end, -(days - 1));
        const rows = await graphql(
          env,
          `query B($accountTag: string!, $start: Date!, $end: Date!) {
             viewer { accounts(filter: { accountTag: $accountTag }) {
               rumPageloadEventsAdaptiveGroups(
                 filter: { date_geq: $start, date_leq: $end }
                 limit: 5000
                 orderBy: [date_ASC]
               ) { count sum { visits } avg { sampleInterval } dimensions { date siteTag } }
             } } }`,
          { accountTag: env.CF_ACCOUNT_ID, start: iso(start), end: iso(end) }
        );
        const rawSum = rows.reduce((a, r) => a + (r.count || 0), 0);
        const scaledSum = rows.reduce(
          (a, r) => a + (r.count || 0) * ((r.avg && Number(r.avg.sampleInterval)) || 1),
          0
        );
        const visitsSum = rows.reduce((a, r) => a + ((r.sum && r.sum.visits) || 0), 0);
        const intervals = [...new Set(rows.map((r) => r.avg && r.avg.sampleInterval))];
        return json({
          ok: true,
          days,
          rows: rows.length,
          rawSum,
          scaledSum,
          visitsSum,
          distinctSampleIntervals: intervals,
          sample: rows.slice(0, 5),
        });
      }

      // ?days= is honoured only under debug, for probing retention limits.
      const override = debug ? url.searchParams.get("days") : null;
      const spec = override || env.DAYS || String(DEFAULT_DAYS);
      const stats = await collect(env, spec);
      payload = debug
        ? json({
            ok: true,
            siteTag: mask(stats.siteTag),
            metric: stats.metric,
            value: stats.value,
            raw: stats.raw,
            sampleInterval: stats.sampleInterval,
            window: stats.window,
            chunks: stats.chunks,
            oldestDay: stats.oldestDay,
          })
        : json(badge(env, stats));
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

/** `spec` is either a day count or "all". */
async function collect(env, spec) {
  requireEnv(env, ["CF_API_TOKEN", "CF_ACCOUNT_ID"]);
  return String(spec).toLowerCase() === "all"
    ? collectAllTime(env)
    : collectWindow(env, Number(spec) || DEFAULT_DAYS);
}

async function collectWindow(env, days) {
  const end = today();
  const start = shiftDays(end, -(days - 1));
  const r = await queryTraffic(env, env.SITE_TAG || null, iso(start), iso(end));
  return { ...r, window: `${days}d`, chunks: 1, oldestDay: iso(start) };
}

/**
 * Walks backwards in chunks and sums them. Stops on a run of empty chunks, or
 * when Cloudflare refuses the range because it has aged out of retention -
 * either way, that is as far back as the data goes.
 */
async function collectAllTime(env) {
  let total = 0;
  let chunks = 0;
  let empties = 0;
  let rawTotal = 0;
  let siteTag = env.SITE_TAG || null;
  let metric = null;
  let sampleInterval = 1;
  let oldestDay = null;

  let end = today();

  for (let i = 0; i < MAX_CHUNKS; i++) {
    const start = shiftDays(end, -(CHUNK_DAYS - 1));

    let r;
    try {
      r = await queryTraffic(env, siteTag, iso(start), iso(end));
    } catch (err) {
      // Out of retention, or the range was refused - nothing older to read.
      if (chunks === 0) throw err;
      break;
    }

    chunks++;
    total += r.value;
    rawTotal += r.raw || 0;
    if (r.siteTag) siteTag = r.siteTag;
    if (r.metric) metric = r.metric;
    if (r.raw > 0 && r.sampleInterval) sampleInterval = r.sampleInterval;
    if (r.value > 0) oldestDay = iso(start);

    empties = r.value === 0 ? empties + 1 : 0;
    if (empties >= EMPTY_CHUNKS_BEFORE_STOP) break;

    end = shiftDays(start, -1);
  }

  return {
    siteTag,
    metric: metric || "visits",
    value: total,
    raw: rawTotal,
    sampleInterval,
    window: "all",
    chunks,
    oldestDay,
  };
}

/**
 * Pull traffic grouped by site tag. Grouping rather than filtering means the
 * tag never has to be configured for a single-site account, and a multi-site
 * account gets a clear error naming its options instead of a silent wrong sum.
 *
 * Which number is reported follows METRIC; if the schema rejects
 * `sum { visits }` it falls back to the pageview `count` and says so.
 */
async function queryTraffic(env, siteTag, start, end) {
  const wantPageviews = (env.METRIC || "visits").toLowerCase() === "pageviews";

  const build = (metricFields) => `
    query Traffic($accountTag: string!, $start: Date!, $end: Date!) {
      viewer {
        accounts(filter: { accountTag: $accountTag }) {
          rumPageloadEventsAdaptiveGroups(
            filter: { date_geq: $start, date_leq: $end }
            limit: 100
          ) { ${metricFields} avg { sampleInterval } dimensions { siteTag } }
        }
      }
    }`;

  const vars = { accountTag: env.CF_ACCOUNT_ID, start, end };

  let rows;
  let metric;

  if (wantPageviews) {
    rows = await graphql(env, build("count"), vars);
    metric = "pageviews";
  } else {
    // Keep the first failure: if both attempts fail the cause is usually auth
    // or permissions, and that error is more useful than the fallback's.
    let firstError = null;
    rows = await graphql(env, build("count sum { visits }"), vars).catch((e) => {
      firstError = e;
      return null;
    });
    metric = "visits";
    if (!rows) {
      rows = await graphql(env, build("count"), vars).catch((e) => {
        throw firstError || e;
      });
      metric = "pageviews";
    }
  }

  const row = pickSite(rows, siteTag);
  if (!row) return { siteTag, metric, value: 0, raw: 0, sampleInterval: 1 };

  const visits = row.sum && typeof row.sum.visits === "number" ? row.sum.visits : null;
  if (metric === "visits" && visits === null) metric = "pageviews";

  const raw = metric === "visits" ? visits : row.count || 0;
  const sampleInterval = (row.avg && Number(row.avg.sampleInterval)) || 1;

  return {
    siteTag: (row.dimensions && row.dimensions.siteTag) || siteTag,
    metric,
    raw,
    sampleInterval,
    // Adaptive datasets return sampled rows; the true total is the sampled
    // count scaled by the interval. Without this the badge reads N times low.
    value: Math.round(raw * sampleInterval),
  };
}

function pickSite(rows, siteTag) {
  if (!rows.length) return null;

  if (siteTag) {
    // A chunk with no traffic for this site is a legitimate zero, not an error.
    return rows.find((r) => r.dimensions && r.dimensions.siteTag === siteTag) || null;
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

const DAY_MS = 86400000;
const today = () => new Date();
const shiftDays = (d, n) => new Date(d.getTime() + n * DAY_MS);
const iso = (d) => d.toISOString().slice(0, 10);

function badge(env, stats) {
  return {
    schemaVersion: 1,
    label: label(env, stats.window),
    message: new Intl.NumberFormat("en-US").format(stats.value),
    color: env.BADGE_COLOR || "818CF8",
  };
}

function label(env, window) {
  if (env.BADGE_LABEL) return env.BADGE_LABEL;
  if (!window || window === "all") return "site visits";
  return `site visits · ${window}`;
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
