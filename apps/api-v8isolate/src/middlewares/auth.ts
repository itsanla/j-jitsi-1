import type { Context, Next } from "hono";
import type { Env, Variables } from "../types";
import { verifyToken, type JwtPayload } from "../utils/jwt";

type AppContext = Context<{ Bindings: Env; Variables: Variables }>;

export const jwtCheckToken = async (c: AppContext, next: Next) => {
  const auth = c.req.header("Authorization");
  const token = auth?.startsWith("Bearer ") ? auth.slice(7) : undefined;

  if (!token) {
    return c.json({ success: false, message: "Token dibutuhkan." }, 401);
  }

  const payload = await verifyToken(token, c.env.JWT_SECRET);
  if (!payload) {
    return c.json(
      { success: false, message: "Token invalid atau sudah kadaluarsa." },
      401,
    );
  }

  c.set("user", payload);
  await next();
};

export type AuthUser = JwtPayload;
