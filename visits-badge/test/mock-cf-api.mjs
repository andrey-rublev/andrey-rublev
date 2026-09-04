/**
 * Stands in for the Cloudflare API so the Worker's full path can be exercised
 * without a real token: site-tag discovery, the GraphQL query, and the
 * visits -> pageviews fallback when the schema rejects `sum { visits }`.
 *
 *   node test/mock-cf-api.mjs [port] [--no-visits]
 */
import { createServer } from "node:http";

const port = Number(process.argv[2]) || 8788;
const supportsVisits = !process.argv.includes("--no-visits");

const SITE_TAG = "abcd1234abcd1234abcd1234abcd1234";

const server = createServer((req, res) => {
  let body = "";
  req.on("data", (c) => (body += c));
  req.on("end", () => {
    const send = (obj, status = 200) => {
      res.writeHead(status, { "Content-Type": "application/json" });
      res.end(JSON.stringify(obj));
    };

    if (req.url.includes("/rum/site_info/list")) {
      return send({
        success: true,
        errors: [],
        result: [
          { site_tag: "0000", host: "someoneelse.com" },
          { site_tag: SITE_TAG, host: "nikhilkolli.com" },
        ],
      });
    }

    if (req.url.includes("/graphql")) {
      const { query, variables } = JSON.parse(body || "{}");
      const wantsVisits = query.includes("sum { visits }");

      if (wantsVisits && !supportsVisits) {
        return send({
          errors: [{ message: 'Unknown field "visits" on type "RumPageloadEventsAdaptiveGroupsSum"' }],
        });
      }
      if (variables.siteTag !== SITE_TAG) {
        return send({ errors: [{ message: `unexpected siteTag ${variables.siteTag}` }] });
      }

      const group = wantsVisits ? { count: 4821, sum: { visits: 1337 } } : { count: 4821 };
      return send({
        data: { viewer: { accounts: [{ rumPageloadEventsAdaptiveGroups: [group] }] } },
      });
    }

    send({ success: false, errors: [{ message: "not found" }] }, 404);
  });
});

server.listen(port, "127.0.0.1", () => {
  console.log(`mock CF API on :${port} (visits ${supportsVisits ? "supported" : "unsupported"})`);
});
