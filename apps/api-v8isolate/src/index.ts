import { Hono } from "hono";

const app = new Hono();

const payload = {
  deployment: "cloudflare",
  platform: "Cloudflare Workers",
  runtime: "V8 Isolate",
  architecture: "Edge Worker",
  execution_model: "v8-isolate",
  cold_start_estimate: "<5ms",
  isolation: "v8-isolate-namespace",
};

app.get("/", (c) => c.json({ ...payload, timestamp: new Date().toISOString() }));

export default app;
