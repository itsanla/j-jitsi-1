const TIMESTAMP_FIELDS = new Set(["createdAt", "updatedAt", "tanggal"]);

export function unixToISO(timestamp: number | null | undefined): string | null {
  if (timestamp === null || timestamp === undefined) return null;
  return new Date(timestamp * 1000).toISOString();
}

function convertValue(value: unknown): unknown {
  if (value === null || value === undefined) return value;
  if (Array.isArray(value)) return value.map(convertValue);
  if (typeof value === "object") return convertObject(value as Record<string, unknown>);
  return value;
}

function convertObject<T extends Record<string, unknown>>(obj: T): T {
  const result: Record<string, unknown> = {};
  for (const key of Object.keys(obj)) {
    const val = obj[key];
    if (TIMESTAMP_FIELDS.has(key) && typeof val === "number") {
      result[key] = unixToISO(val);
    } else {
      result[key] = convertValue(val);
    }
  }
  return result as T;
}

export function convertTimestamps<T>(obj: T): T {
  return convertValue(obj) as T;
}

export function convertTimestampsArray<T>(arr: T[]): T[] {
  return arr.map(convertTimestamps);
}
