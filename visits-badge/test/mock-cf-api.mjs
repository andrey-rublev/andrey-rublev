/**
 * Stands in for the Cloudflare GraphQL Analytics API so the Worker can be
 * exercised without a token: the zone lookup, metric selection, and the
 * failure paths.
 *
 *   node test/mock-cf-api.mjs [port] [--no-zone] [--range-error]
 *
 * --no-zone     returns an empty zones list, as a token without Zone
 *               Resources does - the failure that cost the most time to
 *               diagnose, because it looks like success.
 * --range-error rejects the window the way Cloudflare does past its cap.
 */
import { createServer } from "node:http";

const port = Number(process.argv[2]) || 8788;
const noZone = process.argv.includes("--no-zone");
const rangeError = process.argv.includes("--range-error");

const ZONE_TAG = "8d60a9e02808f681461afbb0e5adbfa8";

const TOTALS = { requests: 49230, pageViews: 30877, uniques: 4632 };

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

    const { variables } = JSON.parse(body || "{}");

    if (rangeError) {
      return send({
        errors: [{ message: `zone "${ZONE_TAG}" cannot request a time range wider than 52w1d1h` }],
      });
    }

    // A token missing Zone Resources returns an empty list, not an error.
    if (noZone || variables.zoneTag !== ZONE_TAG) {
      return send({ data: { viewer: { zones: [] } } });
    }

    send({
      data: {
        viewer: {
          zones: [
            {
              httpRequests1dGroups: [
                {
                  sum: { requests: TOTALS.requests, pageViews: TOTALS.pageViews },
                  uniq: { uniques: TOTALS.uniques },
                },
              ],
            },
          ],
        },
      },
    });
  });
});

server.listen(port, "127.0.0.1", () => {
  const mode = noZone ? "no-zone" : rangeError ? "range-error" : "ok";
  console.log(`mock CF GraphQL on :${port} (${mode})`);
});
