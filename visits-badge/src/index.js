/**
 * Serves a shields.io endpoint badge showing real Cloudflare traffic for a
 * zone, so the README can display a measured number rather than a hit counter
 * that anyone could inflate by loading the image.
 *
 * GET /            -> portfolio views button (SVG)
 * GET /github      -> GitHub profile views button (SVG)
 * GET /?debug=1    -> non-sensitive diagnostics (JSON)
 *
 * Reads `httpRequests1dGroups`, the zone-level daily rollup behind the
 * dashboard's Traffic page. An earlier version used Web Analytics
 * (rumPageloadEventsAdaptiveGroups) and was badly wrong: that dataset is a
 * sampled JS beacon which, on this zone, reported traffic on 3 days out of 30
 * and quantised every count to a multiple of the sample interval. The zone
 * rollup is unsampled, matches the dashboard, and answers a whole year in one
 * request.
 *
 * Token needs: Zone -> Analytics -> Read, with Zone Resources actually set.
 */

import { button } from "./button.mjs";

const GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql";

/** Upstream for the GitHub profile counter; it has no API, only this SVG. */
const GHPVC_URL = "https://komarev.com/ghpvc/?username=andrey-rublev&label=v&color=blue";

/** Overridable so the flow can be exercised against a mock in tests. */
const gqlUrl = (env) => env.GRAPHQL_URL || GRAPHQL_URL;

/** How long a fetched figure is served before a background refresh starts. */
const FRESH_SECONDS = 600;

/** How long the last good figure is retained as a fallback. */
const STATE_TTL_SECONDS = 30 * 24 * 3600;

/** "all" resolves to this many days back - beyond retention is simply empty. */
const ALL_TIME_DAYS = 365;

const DEFAULT_DAYS = 30;

const STATE_KEY = "https://nk-visits-badge.internal/state";

const METRICS = {
  pageviews: (t) => t.pageViews,
  uniques: (t) => t.uniques,
  requests: (t) => t.requests,
};

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const debug = url.searchParams.get("debug") === "1";

    if (url.pathname.replace(/\.svg$/, "") === "/github") {
      let value;
      try {
        value = await githubViews();
      } catch {
        value = null;
      }
      return svg(
        button({
          icon: "github",
          label: "github views",
          value: value === null ? "—" : fmt(value),
          variant: "ghost",
          title: `GitHub profile views: ${value === null ? "unavailable" : fmt(value)}`,
        })
      );
    }

    let payload;
    try {
      // ?days= is honoured only under debug, for probing retention.
      const override = debug ? url.searchParams.get("days") : null;
      if (override) {
        return json({ ok: true, ...(await collect(env, override)) });
      }

      const spec = env.DAYS || String(DEFAULT_DAYS);
      const { stats, servedStale } = await statsWithFallback(env, ctx, spec);

      if (!debug) {
        return svg(
          button({
            icon: "vercel",
            label: env.BADGE_LABEL || "portfolio views",
            value: fmt(stats.value),
            variant: "ghost",
            title: `Portfolio views: ${fmt(stats.value)}`,
          })
        );
      }
      payload = json({ ok: true, servedStale, ...stats });
    } catch (err) {
      // A broken badge is worse than an honest one - render the failure.
      if (!debug) {
        return svg(button({ icon: "vercel", label: label(env), value: "—", variant: "ghost", title: "unavailable" }));
      }
      payload = json({ ok: false, error: String(err && err.message ? err.message : err) }, 500);
    }

    return payload;
  },
};

/** `spec` is either a day count or "all". */
async function collect(env, spec) {
  requireEnv(env, ["CF_API_TOKEN", "ZONE_TAG"]);

  const isAll = String(spec).toLowerCase() === "all";
  const days = isAll ? ALL_TIME_DAYS : Number(spec) || DEFAULT_DAYS;
  const end = today();
  const start = shiftDays(end, -(days - 1));

  const totals = await queryZone(env, iso(start), iso(end));
  const name = (env.METRIC || "pageviews").toLowerCase();
  const pick = METRICS[name];
  if (!pick) throw new Error(`METRIC must be one of: ${Object.keys(METRICS).join(", ")}`);

  return {
    metric: name,
    value: pick(totals) || 0,
    totals,
    window: isAll ? "all" : `${days}d`,
    since: iso(start),
  };
}

/**
 * One request covers the whole range: the daily rollup has no 93-day ceiling,
 * and asking for the range as a single group lets Cloudflare deduplicate
 * `uniques` across it. Summing per-day uniques would double-count anyone who
 * visited on more than one day.
 */
async function queryZone(env, start, end) {
  const query = `
    query Traffic($zoneTag: string!, $start: Date!, $end: Date!) {
      viewer {
        zones(filter: { zoneTag: $zoneTag }) {
          httpRequests1dGroups(
            filter: { date_geq: $start, date_leq: $end }
            limit: 1
          ) { sum { requests pageViews } uniq { uniques } }
        }
      }
    }`;

  const res = await fetch(gqlUrl(env), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify({ query, variables: { zoneTag: env.ZONE_TAG, start, end } }),
  });

  const body = await readJson(res, "graphql");
  if (body.errors && body.errors.length) throw new Error(`GraphQL: ${summarize(body.errors)}`);
  if (!res.ok) throw new Error(`GraphQL HTTP ${res.status}`);

  const zones = body.data && body.data.viewer && body.data.viewer.zones;
  if (!zones || !zones.length) {
    throw new Error("ZONE_TAG not visible - token needs Zone > Analytics > Read with Zone Resources set");
  }

  const row = (zones[0].httpRequests1dGroups || [])[0];
  return {
    requests: (row && row.sum && row.sum.requests) || 0,
    pageViews: (row && row.sum && row.sum.pageViews) || 0,
    uniques: (row && row.uniq && row.uniq.uniques) || 0,
  };
}

/**
 * Serves the last good figure when a refresh fails, and refreshes in the
 * background once it goes stale, so shields.io never waits on the API.
 */
async function statsWithFallback(env, ctx, spec) {
  const cached = await readState();
  const age = cached ? (Date.now() - cached.fetchedAt) / 1000 : Infinity;

  if (cached && age < FRESH_SECONDS) return { stats: cached.stats, servedStale: false };

  if (cached) {
    ctx.waitUntil(refresh(env, spec).catch(() => {}));
    return { stats: cached.stats, servedStale: true };
  }

  return { stats: await refresh(env, spec), servedStale: false };
}

async function refresh(env, spec) {
  const stats = await collect(env, spec);
  await writeState(stats);
  return stats;
}

async function readState() {
  const hit = await caches.default.match(new Request(STATE_KEY));
  if (!hit) return null;
  try {
    return await hit.json();
  } catch {
    return null;
  }
}

async function writeState(stats) {
  await caches.default.put(
    new Request(STATE_KEY),
    new Response(JSON.stringify({ stats, fetchedAt: Date.now() }), {
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": `public, max-age=${STATE_TTL_SECONDS}`,
      },
    })
  );
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
    label: label(env),
    message: new Intl.NumberFormat("en-US").format(stats.value),
    color: env.BADGE_COLOR || "818CF8",
  };
}

function label(env) {
  return env.BADGE_LABEL || "portfolio views";
}

function requireEnv(env, keys) {
  const missing = keys.filter((k) => !env[k]);
  if (missing.length) throw new Error(`Missing config: ${missing.join(", ")}`);
}

function summarize(errors) {
  if (!errors || !errors.length) return "";
  return errors.map((e) => e.message).join("; ").slice(0, 200);
}

/**
 * The profile counter has no API - only an SVG whose number is baked in - so
 * the count is read back out of it and redrawn in this button set. Fetched
 * fresh every time: it increments per render, which is the behaviour to keep.
 */
async function githubViews() {
  const res = await fetch(GHPVC_URL, { headers: { Accept: "image/svg+xml" } });
  const body = await res.text();
  const texts = [...body.matchAll(/>([\d,]+)<\/text>/g)].map((m) => m[1]);
  const n = texts.length ? Number(texts[texts.length - 1].replace(/,/g, "")) : NaN;
  if (!Number.isFinite(n)) throw new Error("could not read count from upstream");
  return n;
}

const fmt = (n) => new Intl.NumberFormat("en-US").format(n);

/** No-store so each render re-counts and the number never sticks. */
function svg(markup) {
  return new Response(markup, {
    headers: {
      "Content-Type": "image/svg+xml; charset=utf-8",
      "Cache-Control": "max-age=0, no-cache, no-store, must-revalidate",
      "Access-Control-Allow-Origin": "*",
    },
  });
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
