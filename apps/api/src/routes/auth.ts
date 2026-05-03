import { Hono } from "hono";
import { eq } from "drizzle-orm";
import type { Env, Variables, ResponseApi } from "../types";
import { getDb } from "../db";
import { usersTable } from "../db/schema";
import { AppError, handleAnyError } from "../errors/app_error";
import { Validator } from "../utils/validation";
import { verifyPassword } from "../utils/password";
import { signToken } from "../utils/jwt";

export const authApp = new Hono<{ Bindings: Env; Variables: Variables }>();

interface LoginBody {
  username?: string;
  password?: string;
}

interface LoginResponse {
  token: string;
  user: { id: number; username: string; role: string };
}

authApp.post("/login", async (c) => {
  try {
    const body = (await c.req.json().catch(() => ({}))) as LoginBody;
    const username = (body.username ?? "").trim();
    const password = body.password ?? "";

    const v = new Validator()
      .required(username, "username", "Username wajib diisi.")
      .required(password, "password", "Password wajib diisi.");
    if (v.hasErrors()) throw new AppError("Validasi gagal", 422, v.getErrors());

    if (!c.env.JWT_SECRET) {
      throw new AppError("JWT_SECRET belum dikonfigurasi.", 500);
    }

    const db = getDb(c.env);
    const [user] = await db
      .select()
      .from(usersTable)
      .where(eq(usersTable.username, username))
      .limit(1);

    if (!user) throw new AppError("Username atau password salah.", 401);

    const ok = await verifyPassword(password, user.password);
    if (!ok) throw new AppError("Username atau password salah.", 401);

    const token = await signToken(
      { sub: user.id, username: user.username, role: user.role },
      c.env.JWT_SECRET,
    );

    const res: ResponseApi<LoginResponse> = {
      success: true,
      message: "Login berhasil.",
      data: {
        token,
        user: { id: user.id, username: user.username, role: user.role },
      },
    };
    return c.json(res);
  } catch (e) {
    return handleAnyError(c, e);
  }
});
