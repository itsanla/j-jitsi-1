export type ValidationError = { path: string; msg: string };

export class Validator {
  private errors: ValidationError[] = [];

  check(condition: boolean, path: string, msg: string) {
    if (!condition) this.errors.push({ path, msg });
    return this;
  }

  required(value: unknown, path: string, msg?: string) {
    const ok =
      value !== undefined &&
      value !== null &&
      !(typeof value === "string" && value.trim() === "");
    return this.check(ok, path, msg ?? `${path} harus diisi.`);
  }

  isEmail(value: unknown, path: string, msg = "Email tidak valid") {
    if (value === undefined || value === null || value === "") return this;
    const ok = typeof value === "string" && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
    return this.check(ok, path, msg);
  }

  isIn<T>(value: unknown, list: readonly T[], path: string, msg?: string) {
    const ok = list.includes(value as T);
    return this.check(ok, path, msg ?? `${path} harus salah satu dari ${list.join(", ")}`);
  }

  isIntGt(value: unknown, threshold: number, path: string, msg?: string) {
    const n = Number(value);
    const ok = Number.isInteger(n) && n > threshold;
    return this.check(ok, path, msg ?? `${path} harus berupa angka > ${threshold}`);
  }

  isIntGte(value: unknown, threshold: number, path: string, msg?: string) {
    const n = Number(value);
    const ok = Number.isInteger(n) && n >= threshold;
    return this.check(ok, path, msg ?? `${path} harus berupa angka >= ${threshold}`);
  }

  minLength(value: unknown, min: number, path: string, msg?: string) {
    if (value === undefined || value === null) return this;
    const ok = typeof value === "string" && value.length >= min;
    return this.check(ok, path, msg ?? `${path} minimal ${min} karakter`);
  }

  isISODate(value: unknown, path: string, msg = "Format tanggal harus ISO 8601.") {
    if (value === undefined || value === null || value === "") return this;
    const d = new Date(String(value));
    return this.check(!Number.isNaN(d.getTime()), path, msg);
  }

  async customAsync(fn: () => Promise<void | string>) {
    try {
      const msg = await fn();
      if (typeof msg === "string") this.errors.push({ path: "_custom", msg });
    } catch (e: any) {
      this.errors.push({ path: "_custom", msg: e?.message ?? "Validasi gagal" });
    }
    return this;
  }

  hasErrors() {
    return this.errors.length > 0;
  }

  getErrors() {
    return this.errors;
  }
}
