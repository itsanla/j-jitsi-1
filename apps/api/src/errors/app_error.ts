import type { Context } from "hono";
import type { ContentfulStatusCode } from "hono/utils/http-status";

export class AppError extends Error {
  public errors?: unknown[];
  public statusCode: ContentfulStatusCode;

  constructor(message: string, statusCode: ContentfulStatusCode = 400, errors?: unknown[]) {
    super(message);
    this.statusCode = statusCode;
    this.errors = errors;
    Object.setPrototypeOf(this, AppError.prototype);
  }
}

export const handleAnyError = (c: Context, error: unknown) => {
  if (error instanceof AppError) {
    return c.json(
      { success: false, message: error.message, errors: error.errors },
      error.statusCode,
    );
  }
  console.error(error);
  return c.json({ success: false, message: "Internal server error" }, 500);
};
