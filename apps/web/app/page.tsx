export const dynamic = 'force-dynamic'
export const runtime = 'edge'

type SearchParams = Promise<{ req_id?: string }>

function computeLoad(): number {
  const start = Date.now()
  Array.from({ length: 10_000 }, () => Math.random()).sort((a, b) => a - b)
  return Date.now() - start
}

export default async function Page({
  searchParams,
}: {
  searchParams: SearchParams
}) {
  const { req_id } = await searchParams
  const renderTimestamp = new Date().toISOString()
  const computeMs = computeLoad()
  const serverTitle =
    process.env.NEXT_PUBLIC_SERVER_TITLE ?? 'SSR Edge Benchmark'

  return (
    <div className="relative min-h-screen bg-[#030712] text-white overflow-hidden">

      {/* ── ambient gradient blobs ── */}
      <div className="pointer-events-none fixed inset-0">
        <div className="absolute -top-40 -left-40 h-[600px] w-[600px] rounded-full bg-emerald-500/10 blur-[140px]" />
        <div className="absolute -bottom-40 -right-40 h-[600px] w-[600px] rounded-full bg-blue-600/10 blur-[140px]" />
        <div className="absolute top-1/2 left-1/2 h-[300px] w-[300px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-violet-600/5 blur-[100px]" />
      </div>

      {/* ── content ── */}
      <div className="relative z-10 flex min-h-screen flex-col items-center justify-center px-6 py-20">

        {/* badge */}
        <div className="mb-8 flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-1.5 backdrop-blur-xl">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
          <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-400">
            SSR Active · Edge Runtime
          </span>
        </div>

        {/* hero title */}
        <h1 className="mb-3 max-w-2xl text-center text-4xl font-bold tracking-tight text-white sm:text-5xl">
          {serverTitle}
        </h1>
        <p className="mb-14 text-center text-sm text-white/35">
          Server-Side Rendered · V8 Isolate · force-dynamic
        </p>

        {/* metric cards */}
        <div className="w-full max-w-md space-y-2.5">
          <GlassCard
            label="Status"
            value="SSR Active"
            dotClass="bg-emerald-400"
          />
          <GlassCard
            label="Compute Time"
            value={`${computeMs} ms`}
            dotClass="bg-sky-400"
          />
          <GlassCard
            label="Render Timestamp"
            value={renderTimestamp}
            dotClass="bg-violet-400"
            mono
          />
          <GlassCard
            label="Request ID"
            value={req_id ?? '—'}
            dotClass="bg-amber-400"
            mono
          />
        </div>

        {/* footer */}
        <p className="mt-10 font-mono text-[11px] text-white/20">
          force-dynamic · no-cache · {renderTimestamp}
        </p>
      </div>
    </div>
  )
}

function GlassCard({
  label,
  value,
  dotClass,
  mono = false,
}: {
  label: string
  value: string
  dotClass: string
  mono?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-6 rounded-2xl border border-white/[0.07] bg-white/[0.04] px-5 py-4 backdrop-blur-2xl">
      <span className="flex shrink-0 items-center gap-2.5 text-sm text-white/45">
        <span className={`h-1.5 w-1.5 rounded-full ${dotClass}`} />
        {label}
      </span>
      <span
        className={`truncate text-right text-sm font-medium text-white/90 ${
          mono ? 'font-mono' : ''
        }`}
      >
        {value}
      </span>
    </div>
  )
}
