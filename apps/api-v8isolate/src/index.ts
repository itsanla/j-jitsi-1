import { Hono } from "hono";
import { benchmarkApp } from "./routes/benchmark";

const app = new Hono();

const api = new Hono();

api.route("/benchmark", benchmarkApp);

app.get("/", (c) => c.text("jirokit api"));
app.route("/api", api);

export default app;
