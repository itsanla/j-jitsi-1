import { Hono } from "hono";
import type { Env, Variables } from "../types";

import vercelPayload     from "../../data/vercel.json";
import cloudflarePayload from "../../data/cloudflare.json";

export const benchmarkApp = new Hono<{ Bindings: Env; Variables: Variables }>();

benchmarkApp.get("/", (c) => {
  // c.env → Cloudflare Workers binding
  // process.env → Vercel / Node.js serverless
  const deployment = c.env?.DEPLOYMENT ?? process.env.DEPLOYMENT ?? "unknown";
  const timestamp  = new Date().toISOString();

  if (deployment === "vercel") {
    return c.json({ ...vercelPayload, timestamp });
  }

  if (deployment === "cloudflare") {
    return c.json({ ...cloudflarePayload, timestamp });
  }

  return c.json(
    { error: "DEPLOYMENT env not configured", deployment, timestamp },
    500,
  );
});
