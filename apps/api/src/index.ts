import { Hono } from "hono";
import { cors } from "hono/cors";
import { logger } from "hono/logger";
import type { Env, Variables } from "./types";
import { eventsApp } from "./routes/events";
import { promoApp } from "./routes/promo";
import { benchmarkApp } from "./routes/benchmark";

const app = new Hono<{ Bindings: Env; Variables: Variables }>();

app.use("*", logger());
app.use("*", async (c, next) => {
  const mw = cors({
    origin: (origin) => {
      const allowedOrigins = c.env.ALLOWED_ORIGINS
        ? c.env.ALLOWED_ORIGINS.split(",").map((o) => o.trim())
        : [c.env.FRONTEND_URL].filter(Boolean);

      return allowedOrigins.includes(origin) ? origin : allowedOrigins[0] ?? "*";
    },
    credentials: true,
  });
  return mw(c, next);
});

const api = new Hono<{ Bindings: Env; Variables: Variables }>();

api.get("/test", (c) => c.json({ message: "Test" }));
api.route("/events", eventsApp);
api.route("/promo", promoApp);
api.route("/benchmark", benchmarkApp);

app.get("/", (c) => c.text("silahkan akses https://jitsi-v8.anla.works/api/benchmark"));
app.route("/api", api);

export default app;
