import { Hono } from "hono";

const app = new Hono();

function fibonacci(n: number): number {
  let a = 0, b = 1;
  for (let i = 2; i <= n; i++) [a, b] = [b, a + b];
  return b;
}

function sievePrimes(limit: number): number {
  const sieve = new Uint8Array(limit + 1).fill(1);
  sieve[0] = sieve[1] = 0;
  for (let i = 2; i * i <= limit; i++) {
    if (sieve[i]) for (let j = i * i; j <= limit; j += i) sieve[j] = 0;
  }
  let count = 0;
  for (let i = 0; i <= limit; i++) if (sieve[i]) count++;
  return count;
}

function sortArray(n: number): { min: number; max: number; median: number } {
  const arr = Array.from({ length: n }, () => Math.random()).sort((a, b) => a - b);
  return { min: arr[0], max: arr[n - 1], median: arr[Math.floor(n / 2)] };
}

function stringOps(iterations: number): number {
  const parts: string[] = [];
  for (let i = 0; i < iterations; i++) parts.push(Math.random().toString(36).slice(2));
  return parts.join("").length;
}

function time<T>(fn: () => T): { result: T; ms: number } {
  const t = Date.now();
  const result = fn();
  return { result, ms: Date.now() - t };
}

app.get("/", (c) => {
  const fib    = time(() => fibonacci(40));
  const primes = time(() => sievePrimes(200_000));
  const sort   = time(() => sortArray(50_000));
  const str    = time(() => stringOps(5_000));

  const totalMs = Math.round((fib.ms + primes.ms + sort.ms + str.ms) * 100) / 100;

  return c.json({
    platform: {
      deployment: "cloudflare",
      runtime: "V8 Isolate",
      architecture: "Edge Worker",
      execution_model: "v8-isolate",
      cold_start_estimate: "<5ms",
      isolation: "v8-isolate-namespace",
    },
    tasks: {
      fibonacci: {
        n: 40,
        result: fib.result,
        duration_ms: fib.ms,
      },
      primes_sieve: {
        limit: 200_000,
        count: primes.result,
        duration_ms: primes.ms,
      },
      array_sort: {
        size: 50_000,
        ...sort.result,
        duration_ms: sort.ms,
      },
      string_ops: {
        iterations: 5_000,
        output_length: str.result,
        duration_ms: str.ms,
      },
    },
    total_compute_ms: totalMs,
    timestamp: new Date().toISOString(),
    request_id: crypto.randomUUID(),
  });
});

export default app;
