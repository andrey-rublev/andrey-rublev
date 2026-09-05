/**
 * Stands in for the Cloudflare GraphQL Analytics API so the Worker's full path
 * can be exercised without a real token: site-tag discovery from the grouped
 * dimensions, and the visits -> pageviews fallback when the schema rejects
 * `sum { visits }`.
 *
 *   node test/mock-cf-api.mjs [port] [--no-visits] [--multi-site] [--history=N]
 *
 * --history=N makes data exist only within the last N days, so the all-time
 * walk runs out of history and its stop condition can be exercised.
 */
import { createServer } from "node:http";

const port = Number(process.argv[2]) || 8788;
const supportsVisits = !process.argv.includes("--no-visits");
const multiSite = process.argv.includes("--multi-site");
const historyArg = process.argv.find((a) => a.startsWith("--history="));
const historyDays = historyArg ? Number(historyArg.split("=")[1]) : Infinity;

const SITE_TAG = "abcd1234abcd1234abcd1234abcd1234";
const OTHER_TAG = "99999999999999999999999999999999";

const server = createServer((req, res) => {
  let body = "";
  req.on("data", (c) => (body += c));
  req.on("end", () => {
    const send = (obj, status = 200) => {
      res.writeHead(status, { "Content-Type": "application/json" });
      res.end(JSON.stringify(obj));
    };

    if (!req.url.includes("/graphql")) {
      return send({ success: false, errors: [{ message: "not found" }] }, 404);
    }

    const { query, variables } = JSON.parse(body || "{}");
    const wantsVisits = query.includes("sum { visits }");

    // Outside the simulated history there is simply nothing to report.
    const ageDays = (Date.now() - Date.parse(variables.end)) / 86400000;
    if (ageDays > historyDays) {
      return send({ data: { viewer: { accounts: [{ rumPageloadEventsAdaptiveGroups: [] }] } } });
    }

    if (wantsVisits && !supportsVisits) {
      return send({
        errors: [{ message: 'Unknown field "visits" on type "RumPageloadEventsAdaptiveGroupsSum"' }],
      });
    }

    const row = (tag, count, visits) =>
      wantsVisits
        ? { count, sum: { visits }, dimensions: { siteTag: tag } }
        : { count, dimensions: { siteTag: tag } };

    const groups = multiSite
      ? [row(SITE_TAG, 4821, 1337), row(OTHER_TAG, 12, 3)]
      : [row(SITE_TAG, 4821, 1337)];

    send({ data: { viewer: { accounts: [{ rumPageloadEventsAdaptiveGroups: groups }] } } });
  });
});

server.listen(port, "127.0.0.1", () => {
  console.log(
    `mock CF GraphQL on :${port} (visits ${supportsVisits ? "supported" : "unsupported"},` +
      ` ${multiSite ? "multi-site" : "single-site"})`
  );
});
