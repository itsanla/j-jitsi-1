#!/usr/bin/env python3
"""
SSR Benchmark — compare two identical Next.js servers
Usage:
  python benchmark.py                        # default 20 requests per server
  python benchmark.py --n 50                 # custom request count
  python benchmark.py --a http://localhost:3000 --b http://localhost:4000
"""

import argparse
import re
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

import requests
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich import box

console = Console()


@dataclass
class Sample:
    seq: int
    req_id: str
    status: int
    ttfb_ms: float        # time to first byte (socket connect + server processing)
    total_ms: float       # full response received
    compute_ms: Optional[int] = None   # parsed from HTML
    render_ts: Optional[str] = None    # parsed from HTML
    error: Optional[str] = None


def parse_html(html: str) -> tuple[Optional[int], Optional[str]]:
    """Extract compute_ms and render_timestamp from the benchmark page HTML."""
    compute_ms = None
    render_ts = None

    # Match the compute time value: looks like "12 ms" inside the Compute Time row
    m = re.search(r'Compute Time[\s\S]{0,200}?(\d+)\s*ms', html)
    if m:
        compute_ms = int(m.group(1))

    # Match ISO timestamp inside Render Timestamp row
    m = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)', html)
    if m:
        render_ts = m.group(1)

    return compute_ms, render_ts


def fetch(seq: int, base_url: str, timeout: float = 10.0) -> Sample:
    req_id = uuid.uuid4().hex[:12]
    url = f"{base_url.rstrip('/')}/?req_id={req_id}"

    try:
        t0 = time.perf_counter()
        resp = requests.get(url, timeout=timeout, stream=True)
        ttfb = (time.perf_counter() - t0) * 1000

        body = resp.content.decode("utf-8", errors="replace")
        total = (time.perf_counter() - t0) * 1000

        compute_ms, render_ts = parse_html(body)

        return Sample(
            seq=seq,
            req_id=req_id,
            status=resp.status_code,
            ttfb_ms=round(ttfb, 2),
            total_ms=round(total, 2),
            compute_ms=compute_ms,
            render_ts=render_ts,
        )
    except Exception as exc:
        total = (time.perf_counter() - t0) * 1000
        return Sample(
            seq=seq,
            req_id=req_id,
            status=0,
            ttfb_ms=0,
            total_ms=round(total, 2),
            error=str(exc),
        )


def run_series(label: str, base_url: str, n: int, workers: int) -> list[Sample]:
    samples: list[Sample] = []
    progress = Progress(
        SpinnerColumn(),
        TextColumn(f"[bold cyan]{label}[/] [dim]{base_url}[/]"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TimeElapsedColumn(),
        console=console,
    )
    with progress:
        task = progress.add_task("fetching", total=n)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(fetch, i, base_url): i for i in range(1, n + 1)}
            for fut in as_completed(futures):
                samples.append(fut.result())
                progress.advance(task)

    samples.sort(key=lambda s: s.seq)
    return samples


def stats(values: list[float]) -> dict:
    if not values:
        return {}
    return {
        "min":  round(min(values), 2),
        "max":  round(max(values), 2),
        "mean": round(statistics.mean(values), 2),
        "p50":  round(statistics.median(values), 2),
        "p95":  round(sorted(values)[int(len(values) * 0.95)], 2),
        "stdev": round(statistics.stdev(values), 2) if len(values) > 1 else 0,
    }


def build_stats_table(
    label_a: str, samples_a: list[Sample],
    label_b: str, samples_b: list[Sample],
) -> Table:
    ok_a = [s for s in samples_a if not s.error]
    ok_b = [s for s in samples_b if not s.error]

    t = Table(title="Response Time Comparison (ms)", box=box.ROUNDED, show_lines=True)
    t.add_column("Metric", style="bold white", no_wrap=True)
    t.add_column(f"[green]{label_a}[/]", justify="right")
    t.add_column(f"[blue]{label_b}[/]", justify="right")
    t.add_column("Delta (B − A)", justify="right")

    def delta(a_val, b_val):
        if a_val is None or b_val is None:
            return "—"
        d = round(b_val - a_val, 2)
        color = "red" if d > 0 else "green"
        sign = "+" if d > 0 else ""
        return f"[{color}]{sign}{d}[/]"

    def row(name, key, values_a, values_b):
        sa = stats(values_a)
        sb = stats(values_b)
        va = sa.get(key)
        vb = sb.get(key)
        t.add_row(
            name,
            str(va) if va is not None else "—",
            str(vb) if vb is not None else "—",
            delta(va, vb),
        )

    total_a = [s.total_ms for s in ok_a]
    total_b = [s.total_ms for s in ok_b]

    for metric, key in [
        ("Total — min",   "min"),
        ("Total — mean",  "mean"),
        ("Total — p50",   "p50"),
        ("Total — p95",   "p95"),
        ("Total — max",   "max"),
        ("Total — stdev", "stdev"),
    ]:
        row(metric, key, total_a, total_b)

    # server-side compute time parsed from HTML
    comp_a = [s.compute_ms for s in ok_a if s.compute_ms is not None]
    comp_b = [s.compute_ms for s in ok_b if s.compute_ms is not None]
    if comp_a or comp_b:
        t.add_section()
        for metric, key in [
            ("Compute (server) — mean", "mean"),
            ("Compute (server) — p95",  "p95"),
        ]:
            row(metric, key,
                [float(v) for v in comp_a],
                [float(v) for v in comp_b])

    return t


def build_raw_table(label: str, samples: list[Sample], color: str) -> Table:
    t = Table(title=f"[{color}]{label}[/] — per-request detail", box=box.SIMPLE_HEAD)
    t.add_column("#",          justify="right", style="dim")
    t.add_column("req_id",     style="dim")
    t.add_column("HTTP",       justify="center")
    t.add_column("Total ms",   justify="right")
    t.add_column("Compute ms", justify="right")
    t.add_column("Render TS",  style="dim")

    for s in samples:
        status_style = "green" if s.status == 200 else "red"
        t.add_row(
            str(s.seq),
            s.req_id,
            f"[{status_style}]{s.status or 'ERR'}[/]",
            f"{s.total_ms:.1f}",
            str(s.compute_ms) if s.compute_ms is not None else "—",
            s.render_ts or (f"[red]{s.error[:40]}[/]" if s.error else "—"),
        )
    return t


def build_verdict(
    label_a: str, samples_a: list[Sample],
    label_b: str, samples_b: list[Sample],
) -> Panel:
    ok_a = [s for s in samples_a if not s.error and s.status == 200]
    ok_b = [s for s in samples_b if not s.error and s.status == 200]

    err_a = len(samples_a) - len(ok_a)
    err_b = len(samples_b) - len(ok_b)

    mean_a = statistics.mean([s.total_ms for s in ok_a]) if ok_a else float("inf")
    mean_b = statistics.mean([s.total_ms for s in ok_b]) if ok_b else float("inf")

    lines = []
    lines.append(f"  Requests   : {len(samples_a)} per server")
    lines.append(f"  Errors     : {label_a}={err_a}  {label_b}={err_b}")

    if mean_a < mean_b:
        diff_pct = round((mean_b - mean_a) / mean_a * 100, 1)
        lines.append(
            f"\n  [bold green]{label_a}[/] is faster by [bold]{diff_pct}%[/] on mean total time"
            f"  ({mean_a:.1f} ms vs {mean_b:.1f} ms)"
        )
    elif mean_b < mean_a:
        diff_pct = round((mean_a - mean_b) / mean_b * 100, 1)
        lines.append(
            f"\n  [bold blue]{label_b}[/] is faster by [bold]{diff_pct}%[/] on mean total time"
            f"  ({mean_b:.1f} ms vs {mean_a:.1f} ms)"
        )
    else:
        lines.append("\n  Both servers performed equally.")

    # SSR validation: check every response has a unique render_ts
    ts_a = {s.render_ts for s in ok_a if s.render_ts}
    ts_b = {s.render_ts for s in ok_b if s.render_ts}
    ssr_ok_a = len(ts_a) == len(ok_a) if ok_a else False
    ssr_ok_b = len(ts_b) == len(ok_b) if ok_b else False

    lines.append("")
    lines.append(f"  SSR validated ({label_a}): {'[green]YES — all timestamps unique[/]' if ssr_ok_a else '[red]NO — possible caching detected[/]'}")
    lines.append(f"  SSR validated ({label_b}): {'[green]YES — all timestamps unique[/]' if ssr_ok_b else '[red]NO — possible caching detected[/]'}")

    return Panel("\n".join(lines), title="[bold]Verdict[/]", border_style="yellow")


def main():
    parser = argparse.ArgumentParser(description="SSR benchmark: compare two local servers")
    parser.add_argument("--a",       default="http://localhost:3000", metavar="URL", help="Server A URL (default: localhost:3000)")
    parser.add_argument("--b",       default="http://localhost:4000", metavar="URL", help="Server B URL (default: localhost:4000)")
    parser.add_argument("--label-a", default="localhost:3000",        metavar="NAME")
    parser.add_argument("--label-b", default="localhost:4000",        metavar="NAME")
    parser.add_argument("--n",       default=20, type=int,            metavar="N",   help="Requests per server (default: 20)")
    parser.add_argument("--workers", default=4,  type=int,            metavar="W",   help="Concurrent workers per server (default: 4)")
    parser.add_argument("--raw",     action="store_true",             help="Show per-request raw tables")
    args = parser.parse_args()

    console.rule("[bold]SSR Benchmark — Local Pre-Deploy Test[/]")
    console.print(f"  [dim]Server A:[/] {args.a}  →  [green]{args.label_a}[/]")
    console.print(f"  [dim]Server B:[/] {args.b}  →  [blue]{args.label_b}[/]")
    console.print(f"  [dim]Requests per server:[/] {args.n}   [dim]Workers:[/] {args.workers}")
    console.print()

    # Check servers are reachable before starting
    for label, url in [(args.label_a, args.a), (args.label_b, args.b)]:
        try:
            r = requests.get(url, timeout=5)
            console.print(f"  [green]✓[/] {label} reachable — HTTP {r.status_code}")
        except Exception as e:
            console.print(f"  [red]✗[/] {label} unreachable — {e}")
            console.print(f"    Make sure the server is running at [bold]{url}[/]")
    console.print()

    samples_a = run_series(args.label_a, args.a, args.n, args.workers)
    samples_b = run_series(args.label_b, args.b, args.n, args.workers)

    console.print()

    if args.raw:
        console.print(build_raw_table(args.label_a, samples_a, "green"))
        console.print()
        console.print(build_raw_table(args.label_b, samples_b, "blue"))
        console.print()

    console.print(build_stats_table(args.label_a, samples_a, args.label_b, samples_b))
    console.print()
    console.print(build_verdict(args.label_a, samples_a, args.label_b, samples_b))


if __name__ == "__main__":
    main()
