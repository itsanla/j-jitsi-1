import type { JwtPayload } from "./utils/jwt";

export interface Env {
  DB: D1Database;
  DEPLOYMENT?: string;
  JWT_SECRET?: string;
  CLOUDINARY_CLOUD_NAME?: string;
  CLOUDINARY_API_KEY?: string;
  CLOUDINARY_API_SECRET?: string;
  FRONTEND_URL?: string;
  ALLOWED_ORIGINS?: string;
}

export interface Variables {
  user?: JwtPayload;
}

export interface ResponseApi<T = unknown> {
  success: boolean;
  message: string;
  data?: T;
  errors?: unknown;
}
