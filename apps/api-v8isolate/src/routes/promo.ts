import { Hono } from "hono";
import { eq, and } from "drizzle-orm";
import type { Env, Variables, ResponseApi } from "../types";
import { getDb } from "../db";
import { eventsTable, promoCodesTable } from "../db/schema";
import { AppError, handleAnyError } from "../errors/app_error";
import { Validator } from "../utils/validation";

export const promoApp = new Hono<{ Bindings: Env; Variables: Variables }>();

type ValidatePromoBody = {
  code?: string;
  event_slug?: string;
};

type ValidatePromoResponse = {
  valid: boolean;
  code: string;
  event_slug: string;
  discount_type: string;
  discount_value: number;
  remaining_uses: number | null;
};

promoApp.post("/validate", async (c) => {
  try {
    const body = (await c.req.json().catch(() => ({}))) as ValidatePromoBody;
    const code = (body.code ?? "").trim().toUpperCase();
    const eventSlug = (body.event_slug ?? "").trim();

    const v = new Validator()
      .required(code, "code", "Kode promo wajib diisi.")
      .required(eventSlug, "event_slug", "Event wajib dipilih.");

    if (v.hasErrors()) {
      throw new AppError("Validasi gagal", 422, v.getErrors());
    }

    const db = getDb(c.env);

    const [event] = await db
      .select()
      .from(eventsTable)
      .where(and(eq(eventsTable.slug, eventSlug), eq(eventsTable.is_active, 1)))
      .limit(1);

    if (!event) throw new AppError("Event tidak ditemukan.", 404);

    const [promo] = await db
      .select()
      .from(promoCodesTable)
      .where(
        and(
          eq(promoCodesTable.code, code),
          eq(promoCodesTable.is_active, 1),
        ),
      )
      .limit(1);

    if (!promo) throw new AppError("Kode promo tidak valid.", 404);

    if (promo.event_id != null && promo.event_id !== event.id) {
      throw new AppError("Kode promo tidak berlaku untuk event ini.", 400);
    }

    if (promo.valid_until != null) {
      const nowSec = Math.floor(Date.now() / 1000);
      if (nowSec > promo.valid_until) {
        throw new AppError("Kode promo sudah kadaluarsa.", 400);
      }
    }

    if (promo.max_uses != null && promo.current_uses >= promo.max_uses) {
      throw new AppError("Kuota kode promo sudah habis.", 400);
    }

    const data: ValidatePromoResponse = {
      valid: true,
      code: promo.code,
      event_slug: event.slug,
      discount_type: promo.discount_type,
      discount_value: promo.discount_value,
      remaining_uses:
        promo.max_uses == null ? null : promo.max_uses - promo.current_uses,
    };

    const res: ResponseApi<ValidatePromoResponse> = {
      success: true,
      message: "Kode promo valid.",
      data,
    };
    return c.json(res);
  } catch (e) {
    return handleAnyError(c, e);
  }
});
