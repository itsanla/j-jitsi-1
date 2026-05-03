import { Hono } from "hono";

const cloudflarePayload = {
  deployment: "cloudflare",
  platform: "Cloudflare Workers",
  runtime: "V8 Isolate",
  architecture: "Edge Worker",
  execution_model: "v8-isolate",
  cold_start_estimate: "<5ms",
  isolation: "v8-isolate-namespace",
};

export const benchmarkApp = new Hono();

benchmarkApp.get("/", (c) => {
  return c.json({ ...cloudflarePayload, timestamp: new Date().toISOString() });
});
