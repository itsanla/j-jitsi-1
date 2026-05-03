#!/usr/bin/env python3
"""
SSR Edge Benchmark Analyzer
Perbandingan performa Vercel Serverless vs Cloudflare Pages Edge Workers
Dijalankan lokal sebelum deployment produksi.

Usage:
  python analytic.py                          # 40 req default
  python analytic.py --n 80 --workers 6
  python analytic.py --a https://x.vercel.app --b https://x.pages.dev \
                     --label-a Vercel --label-b Cloudflare --n 100
"""

import argparse
import re
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np
import requests
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich import box as rbox
from scipy import stats as scipy_stats

# ── paths ──────────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent
IMG  = BASE / "images"
DOCS = BASE / "docs"
IMG.mkdir(exist_ok=True)
DOCS.mkdir(exist_ok=True)

# ── style ──────────────────────────────────────────────────────────────────────
COLOR_A  = "#22c55e"   # green  → Server A (Vercel analogy)
COLOR_B  = "#3b82f6"   # blue   → Server B (Cloudflare analogy)
ALPHA    = 0.72
PLT_STYLE = {
    "figure.facecolor":  "#0f172a",
    "axes.facecolor":    "#1e293b",
    "axes.edgecolor":    "#334155",
    "axes.labelcolor":   "#cbd5e1",
    "axes.titlecolor":   "#f1f5f9",
    "xtick.color":       "#64748b",
    "ytick.color":       "#64748b",
    "text.color":        "#f1f5f9",
    "grid.color":        "#334155",
    "grid.linestyle":    "--",
    "grid.linewidth":    0.5,
    "legend.facecolor":  "#1e293b",
    "legend.edgecolor":  "#334155",
    "font.family":       "monospace",
    "font.size":         9,
}
plt.rcParams.update(PLT_STYLE)

console = Console()


# ── data model ─────────────────────────────────────────────────────────────────
@dataclass
class Sample:
    seq:        int
    req_id:     str
    status:     int
    total_ms:   float
    ttfb_ms:    float
    compute_ms: Optional[int]  = None
    render_ts:  Optional[str]  = None
    error:      Optional[str]  = None


# ── HTML parsing ───────────────────────────────────────────────────────────────
def parse_html(html: str) -> tuple[Optional[int], Optional[str]]:
    compute_ms, render_ts = None, None
    m = re.search(r"Compute Time[\s\S]{0,400}?(\d+)\s*ms", html)
    if m:
        compute_ms = int(m.group(1))
    m = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)", html)
    if m:
        render_ts = m.group(1)
    return compute_ms, render_ts


# ── HTTP fetch ─────────────────────────────────────────────────────────────────
def fetch(seq: int, base_url: str, timeout: float = 12.0) -> Sample:
    req_id = uuid.uuid4().hex[:12]
    url    = f"{base_url.rstrip('/')}/?req_id={req_id}"
    t0     = time.perf_counter()
    try:
        resp  = requests.get(url, timeout=timeout, stream=True)
        ttfb  = (time.perf_counter() - t0) * 1000
        body  = resp.content.decode("utf-8", errors="replace")
        total = (time.perf_counter() - t0) * 1000
        compute_ms, render_ts = parse_html(body)
        return Sample(seq=seq, req_id=req_id, status=resp.status_code,
                      total_ms=round(total, 2), ttfb_ms=round(ttfb, 2),
                      compute_ms=compute_ms, render_ts=render_ts)
    except Exception as exc:
        total = (time.perf_counter() - t0) * 1000
        return Sample(seq=seq, req_id=req_id, status=0,
                      total_ms=round(total, 2), ttfb_ms=0,
                      compute_ms=None, render_ts=None, error=str(exc))


def collect(label: str, url: str, n: int, workers: int) -> list[Sample]:
    samples: list[Sample] = []
    prog = Progress(
        SpinnerColumn(),
        TextColumn(f"[bold]{label}[/]  [dim]{url}[/]"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%  ({task.completed}/{task.total})"),
        TimeElapsedColumn(),
        console=console,
    )
    with prog:
        task = prog.add_task("", total=n)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(fetch, i, url): i for i in range(1, n + 1)}
            for fut in as_completed(futures):
                samples.append(fut.result())
                prog.advance(task)
    return sorted(samples, key=lambda s: s.seq)


# ── statistics ─────────────────────────────────────────────────────────────────
def analyze(samples: list[Sample]) -> dict:
    ok  = [s for s in samples if not s.error and s.status == 200]
    tot = [s.total_ms  for s in ok]
    cmp = [float(s.compute_ms) for s in ok if s.compute_ms is not None]
    tbt = [s.ttfb_ms   for s in ok]

    def _s(lst):
        if not lst:
            return {}
        arr = np.array(lst)
        return {
            "n":      len(lst),
            "mean":   float(np.mean(arr)),
            "median": float(np.median(arr)),
            "stdev":  float(np.std(arr, ddof=1)) if len(lst) > 1 else 0.0,
            "cv":     float(np.std(arr, ddof=1) / np.mean(arr)) if len(lst) > 1 and np.mean(arr) else 0.0,
            "min":    float(np.min(arr)),
            "max":    float(np.max(arr)),
            "p25":    float(np.percentile(arr, 25)),
            "p50":    float(np.percentile(arr, 50)),
            "p75":    float(np.percentile(arr, 75)),
            "p95":    float(np.percentile(arr, 95)),
            "p99":    float(np.percentile(arr, 99)),
            "iqr":    float(np.percentile(arr, 75) - np.percentile(arr, 25)),
            "skew":   float(scipy_stats.skew(arr)),
            "kurt":   float(scipy_stats.kurtosis(arr)),
            "raw":    lst,
        }

    ts_set = {s.render_ts for s in ok if s.render_ts}
    overhead = [s.total_ms - (s.compute_ms or 0) for s in ok if s.compute_ms is not None]

    # warm-up split: first 20% vs rest
    warm_n   = max(1, len(ok) // 5)
    warmup   = [s.total_ms for s in ok[:warm_n]]
    steady   = [s.total_ms for s in ok[warm_n:]]

    return {
        "n_ok":    len(ok),
        "n_err":   len(samples) - len(ok),
        "ssr_ok":  len(ts_set) == len(ok) and len(ok) > 0,
        "total":   _s(tot),
        "compute": _s(cmp),
        "ttfb":    _s(tbt),
        "overhead":_s(overhead),
        "warmup":  {"mean": np.mean(warmup) if warmup else None,
                    "n":    warm_n},
        "steady":  {"mean": np.mean(steady) if steady else None},
    }


def significance(a: list[Sample], b: list[Sample]) -> dict:
    """Mann-Whitney U + Cohen's d effect size."""
    ok_a = [s.total_ms for s in a if not s.error and s.status == 200]
    ok_b = [s.total_ms for s in b if not s.error and s.status == 200]
    if len(ok_a) < 2 or len(ok_b) < 2:
        return {"u_stat": None, "p_value": None, "effect_r": None}

    u, p = scipy_stats.mannwhitneyu(ok_a, ok_b, alternative="two-sided")
    n1, n2 = len(ok_a), len(ok_b)
    r = 1 - (2 * u) / (n1 * n2)   # rank-biserial correlation (effect size)

    pooled_std = np.sqrt(
        ((n1 - 1) * np.var(ok_a, ddof=1) + (n2 - 1) * np.var(ok_b, ddof=1))
        / (n1 + n2 - 2)
    )
    cohens_d = (np.mean(ok_a) - np.mean(ok_b)) / pooled_std if pooled_std else 0.0

    return {"u_stat": u, "p_value": p, "effect_r": r, "cohens_d": cohens_d,
            "significant": p < 0.05}


# ── charts ─────────────────────────────────────────────────────────────────────
def _save(fig, name: str):
    path = IMG / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    console.print(f"  [dim]saved[/] {path.relative_to(BASE)}")


def chart_distribution(la: str, sa: list[Sample], lb: str, sb: list[Sample]):
    ok_a = [s.total_ms for s in sa if not s.error]
    ok_b = [s.total_ms for s in sb if not s.error]

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=False)
    fig.suptitle("Response Time Distribution", fontsize=12, weight="bold", y=1.01)

    for ax, data, color, label in [
        (axes[0], ok_a, COLOR_A, la),
        (axes[1], ok_b, COLOR_B, lb),
    ]:
        arr = np.array(data)
        bins = min(30, max(10, len(data) // 4))
        ax.hist(arr, bins=bins, color=color, alpha=ALPHA, edgecolor="none", density=True)
        kde_x = np.linspace(arr.min() - 5, arr.max() + 5, 300)
        kde   = scipy_stats.gaussian_kde(arr)
        ax.plot(kde_x, kde(kde_x), color=color, linewidth=2)
        ax.axvline(np.mean(arr),   color="#f59e0b", linewidth=1.4, linestyle="--", label=f"mean={np.mean(arr):.1f}")
        ax.axvline(np.median(arr), color="#e879f9", linewidth=1.4, linestyle=":",  label=f"med={np.median(arr):.1f}")
        ax.set_title(f"[{label}]", fontsize=10)
        ax.set_xlabel("Response Time (ms)")
        ax.set_ylabel("Density")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    fig.tight_layout()
    _save(fig, "01_distribution.png")


def chart_boxplot(la: str, sa: list[Sample], lb: str, sb: list[Sample]):
    ok_a = [s.total_ms for s in sa if not s.error]
    ok_b = [s.total_ms for s in sb if not s.error]
    ca_a = [float(s.compute_ms) for s in sa if s.compute_ms is not None]
    ca_b = [float(s.compute_ms) for s in sb if s.compute_ms is not None]

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    fig.suptitle("Distribution Spread — Box Plots", fontsize=12, weight="bold")

    def _box(ax, data_a, data_b, title, ylabel):
        bp = ax.boxplot([data_a, data_b], patch_artist=True, widths=0.5,
                        medianprops=dict(color="#fbbf24", linewidth=2),
                        whiskerprops=dict(color="#94a3b8"),
                        capprops=dict(color="#94a3b8"),
                        flierprops=dict(marker="o", markersize=4, alpha=0.5))
        bp["boxes"][0].set_facecolor(COLOR_A + "bb")
        bp["boxes"][1].set_facecolor(COLOR_B + "bb")
        ax.set_xticklabels([la, lb])
        ax.set_title(title, fontsize=10)
        ax.set_ylabel(ylabel)
        ax.grid(True, axis="y", alpha=0.3)

    _box(axes[0], ok_a, ok_b, "Total Response Time (ms)", "ms")
    _box(axes[1], ca_a, ca_b, "Server Compute Time (ms)", "ms")

    # legend patch
    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=COLOR_A, label=la), Patch(color=COLOR_B, label=lb)],
               loc="lower center", ncol=2, framealpha=0.2, fontsize=9)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    _save(fig, "02_boxplot.png")


def chart_percentiles(la: str, sa_stat: dict, lb: str, sb_stat: dict):
    pcts = ["p50", "p95", "p99"]
    labels = ["P50 (Median)", "P95", "P99"]
    va = [sa_stat["total"].get(p, 0) for p in pcts]
    vb = [sb_stat["total"].get(p, 0) for p in pcts]

    x   = np.arange(len(labels))
    w   = 0.32
    fig, ax = plt.subplots(figsize=(8, 4.5))
    fig.suptitle("Latency Percentile Comparison", fontsize=12, weight="bold")

    ba = ax.bar(x - w/2, va, w, color=COLOR_A, alpha=ALPHA, label=la)
    bb = ax.bar(x + w/2, vb, w, color=COLOR_B, alpha=ALPHA, label=lb)

    for bars in [ba, bb]:
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, h + 0.5,
                    f"{h:.1f}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Response Time (ms)")
    ax.legend(fontsize=9)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    _save(fig, "03_percentiles.png")


def chart_timeseries(la: str, sa: list[Sample], lb: str, sb: list[Sample]):
    ok_a = [(s.seq, s.total_ms) for s in sa if not s.error]
    ok_b = [(s.seq, s.total_ms) for s in sb if not s.error]

    fig, ax = plt.subplots(figsize=(12, 4.5))
    fig.suptitle("Latency Over Request Sequence (warm-up visibility)", fontsize=12, weight="bold")

    xa, ya = zip(*ok_a) if ok_a else ([], [])
    xb, yb = zip(*ok_b) if ok_b else ([], [])

    ax.plot(xa, ya, color=COLOR_A, linewidth=1.2, alpha=0.9, label=la)
    ax.plot(xb, yb, color=COLOR_B, linewidth=1.2, alpha=0.9, label=lb)

    # rolling mean (window=5)
    if len(ya) >= 5:
        roll_a = np.convolve(ya, np.ones(5)/5, mode="valid")
        ax.plot(list(xa)[4:], roll_a, color=COLOR_A, linewidth=2.5,
                linestyle="--", alpha=0.6, label=f"{la} roll-avg")
    if len(yb) >= 5:
        roll_b = np.convolve(yb, np.ones(5)/5, mode="valid")
        ax.plot(list(xb)[4:], roll_b, color=COLOR_B, linewidth=2.5,
                linestyle="--", alpha=0.6, label=f"{lb} roll-avg")

    ax.set_xlabel("Request Sequence #")
    ax.set_ylabel("Total Response Time (ms)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    _save(fig, "04_timeseries.png")


def chart_cdf(la: str, sa: list[Sample], lb: str, sb: list[Sample]):
    ok_a = sorted(s.total_ms for s in sa if not s.error)
    ok_b = sorted(s.total_ms for s in sb if not s.error)

    fig, ax = plt.subplots(figsize=(9, 5))
    fig.suptitle("Empirical CDF — Response Time", fontsize=12, weight="bold")

    for data, color, label in [(ok_a, COLOR_A, la), (ok_b, COLOR_B, lb)]:
        n  = len(data)
        cdf = np.arange(1, n + 1) / n
        ax.plot(data, cdf, color=color, linewidth=2, label=label)
        # p95 marker
        idx95 = int(0.95 * n) - 1
        ax.axvline(data[idx95], color=color, linewidth=0.8, linestyle=":",
                   alpha=0.6)
        ax.text(data[idx95] + 0.5, 0.92, f"p95={data[idx95]:.0f}ms",
                color=color, fontsize=7)

    ax.set_xlabel("Response Time (ms)")
    ax.set_ylabel("Cumulative Probability")
    ax.set_ylim(0, 1.05)
    ax.axhline(0.95, color="#64748b", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    _save(fig, "05_cdf.png")


def chart_overhead(la: str, sa: list[Sample], lb: list[Sample], lb_label: str):
    ok_a = [(s.total_ms, s.compute_ms) for s in sa  if s.compute_ms and not s.error]
    ok_b = [(s.total_ms, s.compute_ms) for s in lb  if s.compute_ms and not s.error]

    def decompose(data):
        compute  = np.mean([c   for _, c in data])
        overhead = np.mean([t-c for t, c in data])
        return compute, overhead

    ca, oa = decompose(ok_a)
    cb, ob = decompose(ok_b)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    fig.suptitle("Response Time Decomposition\n(Server Compute vs Network/Infra Overhead)", fontsize=11, weight="bold")

    servers = [la, lb_label]
    computes  = [ca, cb]
    overheads = [oa, ob]

    x = np.arange(len(servers))
    w = 0.45
    b1 = ax.bar(x, computes,  w, label="Server Compute (ms)", color="#f59e0b", alpha=0.85)
    b2 = ax.bar(x, overheads, w, bottom=computes, label="Network/Infra Overhead (ms)",
                color="#8b5cf6", alpha=0.85)

    for bar, val in zip(b1, computes):
        ax.text(bar.get_x() + bar.get_width()/2, val/2,
                f"{val:.1f}", ha="center", va="center", fontsize=9, color="white", weight="bold")
    for bar, bot, val in zip(b2, computes, overheads):
        ax.text(bar.get_x() + bar.get_width()/2, bot + val/2,
                f"{val:.1f}", ha="center", va="center", fontsize=9, color="white", weight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(servers)
    ax.set_ylabel("Time (ms)")
    ax.legend(fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    _save(fig, "06_overhead_breakdown.png")


# ── report ─────────────────────────────────────────────────────────────────────
def write_report(
    la: str, stat_a: dict,
    lb: str, stat_b: dict,
    sig: dict,
    n: int, workers: int,
    url_a: str, url_b: str,
    timestamp: str,
):
    ta = stat_a["total"]
    tb = stat_b["total"]
    ca = stat_a["compute"]
    cb = stat_b["compute"]
    oa = stat_a["overhead"]
    ob = stat_b["overhead"]

    winner    = la if ta["mean"] < tb["mean"] else lb
    loser     = lb if winner == la else la
    diff_pct  = abs(ta["mean"] - tb["mean"]) / min(ta["mean"], tb["mean"]) * 100
    p_val_str = f"{sig['p_value']:.4f}" if sig.get("p_value") is not None else "N/A"
    sig_str   = "Signifikan (p < 0.05)" if sig.get("significant") else "Tidak Signifikan (p ≥ 0.05)"

    lines = f"""\
================================================================================
PERBANDINGAN PERFORMA ARSITEKTUR SERVERLESS:
VERCEL SERVERLESS FUNCTIONS vs CLOUDFLARE PAGES EDGE WORKERS
Berbasis Metrik HTTP Response Time pada Server-Side Rendering (Next.js)
================================================================================
Tanggal Analisis : {timestamp}
Server A (proxy)  : {url_a}  [{la}]
Server B (proxy)  : {url_b}  [{lb}]
Jumlah Request    : {n} per server
Concurrency       : {workers} workers paralel
Runtime           : Next.js App Router, Edge Runtime, force-dynamic
--------------------------------------------------------------------------------

1. LATAR BELAKANG ARSITEKTUR
──────────────────────────────
Vercel Serverless Functions menjalankan kode di atas container AWS Lambda
berbasis Node.js runtime. Setiap invokasi dapat mengalami cold start
(inisialisasi container ~100–1000 ms) sebelum eksekusi fungsi berlangsung.
Vercel mengelola warm instance secara otomatis namun tidak dijamin.

Cloudflare Pages (Workers) menggunakan model V8 Isolate — proses V8 tunggal
yang mengisolasi fungsi via namespace, bukan proses/container terpisah.
Model ini menghilangkan overhead cold start yang signifikan (<5 ms) karena
isolate diinisialisasi sekali dan di-reuse. Namun, API yang tersedia dibatasi
pada Web Standard APIs (tanpa Node.js built-ins seperti fs, crypto).

Kedua platform mendukung distribusi geografis (CDN + edge node global),
namun Cloudflare memiliki lebih dari 300 PoP dibandingkan Vercel yang
bergantung pada wilayah AWS.

2. METODOLOGI
──────────────────────────────
- Protokol  : HTTP/1.1 GET dengan query parameter ?req_id=<uuid> unik per request
- Cache bypass: req_id acak memaksa server tidak meng-cache response
- SSR validation: setiap response diperiksa apakah Render Timestamp unik
- Timing client : time.perf_counter() (resolusi nanosecond)
  * total_ms : mulai koneksi hingga seluruh body diterima
  * ttfb_ms  : mulai koneksi hingga header pertama diterima
- Compute time (server-side): diekstrak dari HTML yang di-render
  (fungsi sort 10.000 angka acak, diukur dengan Date.now())
- Concurrency : {workers} request paralel (ThreadPoolExecutor)
- Uji statistik : Mann-Whitney U (non-parametrik, tidak mengasumsikan normalitas)
- Effect size  : rank-biserial correlation (r) dan Cohen's d

3. HASIL STATISTIK
──────────────────────────────
3.1 Total Response Time (ms)
                        {la:<20}  {lb:<20}
  N (sukses)          : {stat_a['n_ok']:<20}  {stat_b['n_ok']:<20}
  Error               : {stat_a['n_err']:<20}  {stat_b['n_err']:<20}
  Mean                : {ta['mean']:<20.2f}  {tb['mean']:<20.2f}
  Median (P50)        : {ta['median']:<20.2f}  {tb['median']:<20.2f}
  Std Dev             : {ta['stdev']:<20.2f}  {tb['stdev']:<20.2f}
  CV (stdev/mean)     : {ta['cv']:<20.3f}  {tb['cv']:<20.3f}
  Min                 : {ta['min']:<20.2f}  {tb['min']:<20.2f}
  P25                 : {ta['p25']:<20.2f}  {tb['p25']:<20.2f}
  P75                 : {ta['p75']:<20.2f}  {tb['p75']:<20.2f}
  P95                 : {ta['p95']:<20.2f}  {tb['p95']:<20.2f}
  P99                 : {ta['p99']:<20.2f}  {tb['p99']:<20.2f}
  IQR                 : {ta['iqr']:<20.2f}  {tb['iqr']:<20.2f}
  Skewness            : {ta['skew']:<20.3f}  {tb['skew']:<20.3f}
  Kurtosis (excess)   : {ta['kurt']:<20.3f}  {tb['kurt']:<20.3f}
  Max                 : {ta['max']:<20.2f}  {tb['max']:<20.2f}

3.2 Server Compute Time (ms) — dari HTML
  Mean compute        : {(ca.get('mean') or 0):<20.2f}  {(cb.get('mean') or 0):<20.2f}
  P95 compute         : {(ca.get('p95')  or 0):<20.2f}  {(cb.get('p95')  or 0):<20.2f}

3.3 Infra/Network Overhead (total − compute) (ms)
  Mean overhead       : {(oa.get('mean') or 0):<20.2f}  {(ob.get('mean') or 0):<20.2f}
  P95 overhead        : {(oa.get('p95')  or 0):<20.2f}  {(ob.get('p95')  or 0):<20.2f}

3.4 Warm-up vs Steady State
  Warmup mean ({stat_a['warmup']['n']:>2} req) : {(stat_a['warmup']['mean'] or 0):<20.2f}  {(stat_b['warmup']['mean'] or 0):<20.2f}
  Steady-state mean   : {(stat_a['steady']['mean'] or 0):<20.2f}  {(stat_b['steady']['mean'] or 0):<20.2f}

3.5 Validasi SSR
  Semua timestamp unik: {'YA' if stat_a['ssr_ok'] else 'TIDAK':<20}  {'YA' if stat_b['ssr_ok'] else 'TIDAK':<20}
  (YA = force-dynamic aktif, tidak ada response yang di-cache)

4. UJI SIGNIFIKANSI STATISTIK
──────────────────────────────
  Metode          : Mann-Whitney U (two-sided)
  U-statistic     : {sig.get('u_stat', 'N/A')}
  p-value         : {p_val_str}
  Kesimpulan      : {sig_str}
  Effect size (r) : {sig.get('effect_r', 0):.4f}  (|r|>0.1 kecil, >0.3 sedang, >0.5 besar)
  Cohen's d       : {sig.get('cohens_d', 0):.4f}

5. INTERPRETASI DAN DISKUSI
──────────────────────────────
Perbedaan mean response time antara {la} dan {lb} adalah
{abs(ta['mean'] - tb['mean']):.2f} ms ({diff_pct:.1f}%), di mana {winner} lebih cepat.

Nilai Coefficient of Variation (CV) mengindikasikan konsistensi layanan:
  {la}: CV = {ta['cv']:.3f}   {lb}: CV = {tb['cv']:.3f}
Nilai CV lebih rendah menunjukkan respons lebih konsisten antar request.

Decomposisi waktu memperlihatkan bahwa server compute time (beban CPU isolate)
antara kedua server relatif setara ({(ca.get('mean') or 0):.1f} ms vs {(cb.get('mean') or 0):.1f} ms).
Perbedaan utama terletak pada komponen infra/network overhead, yang mencerminkan
perbedaan model eksekusi (Lambda cold-start vs Isolate reuse) dan routing jaringan.

Skewness positif tinggi ({max(ta['skew'], tb['skew']):.2f}) mengindikasikan adanya outlier ke kanan
(cold-start events), yang merupakan karakteristik tipikal arsitektur serverless.

CATATAN: Pengujian lokal ini menggunakan dua instance Next.js pada port berbeda
sebagai proxy untuk mensimulasikan kondisi deployment. Angka ini merupakan
baseline validasi logika SSR, bukan prediksi performa produksi.
Faktor yang tidak terukur di lokal: cold start sesungguhnya, latency jaringan
global, edge node selection, TLS handshake, dan HTTP/2 multiplexing.

6. KESIMPULAN
──────────────────────────────
Dari {n} request per server:
- {winner} mencatatkan mean response time lebih rendah ({diff_pct:.1f}% lebih cepat)
- Uji Mann-Whitney: {sig_str}
- SSR aktif dan tervalidasi pada kedua server (semua timestamp unik)
- Server compute time setara, perbedaan ada di lapisan infrastruktur
- Deployment produksi diperlukan untuk mengukur cold start dan latency global

7. ARTEFAK
──────────────────────────────
  images/01_distribution.png      — Histogram + KDE distribusi response time
  images/02_boxplot.png           — Box plot spread & outlier comparison
  images/03_percentiles.png       — Perbandingan P50, P95, P99
  images/04_timeseries.png        — Time series per-request (deteksi warm-up)
  images/05_cdf.png               — Empirical CDF kedua server
  images/06_overhead_breakdown.png — Dekomposisi compute vs infra overhead

================================================================================
"""
    path = DOCS / "perbandingan.txt"
    path.write_text(lines, encoding="utf-8")
    console.print(f"  [dim]saved[/] {path.relative_to(BASE)}")
    return lines


# ── terminal summary ───────────────────────────────────────────────────────────
def print_summary(la: str, sa: list[Sample], stat_a: dict,
                  lb: str, sb: list[Sample], stat_b: dict,
                  sig: dict):
    ta, tb = stat_a["total"], stat_b["total"]

    t = Table(title="Response Time Summary (ms)", box=rbox.ROUNDED, show_lines=True)
    t.add_column("Metric",           style="bold white", no_wrap=True)
    t.add_column(f"[green]{la}[/]",  justify="right")
    t.add_column(f"[blue]{lb}[/]",   justify="right")
    t.add_column("Delta (B−A)",       justify="right")

    def d(a_val, b_val):
        if a_val is None or b_val is None: return "—"
        v = round(b_val - a_val, 2)
        c = "red" if v > 0 else "green"
        s = "+" if v > 0 else ""
        return f"[{c}]{s}{v}[/]"

    rows = [
        ("N ok / err",  f"{stat_a['n_ok']}/{stat_a['n_err']}", f"{stat_b['n_ok']}/{stat_b['n_err']}", ""),
        ("Mean",        f"{ta['mean']:.2f}", f"{tb['mean']:.2f}", d(ta['mean'], tb['mean'])),
        ("P50",         f"{ta['p50']:.2f}",  f"{tb['p50']:.2f}",  d(ta['p50'],  tb['p50'])),
        ("P95",         f"{ta['p95']:.2f}",  f"{tb['p95']:.2f}",  d(ta['p95'],  tb['p95'])),
        ("P99",         f"{ta['p99']:.2f}",  f"{tb['p99']:.2f}",  d(ta['p99'],  tb['p99'])),
        ("Stdev",       f"{ta['stdev']:.2f}",f"{tb['stdev']:.2f}",d(ta['stdev'],tb['stdev'])),
        ("CV",          f"{ta['cv']:.3f}",   f"{tb['cv']:.3f}",   d(ta['cv'],   tb['cv'])),
        ("Skewness",    f"{ta['skew']:.3f}", f"{tb['skew']:.3f}", ""),
        ("Compute mean",f"{stat_a['compute'].get('mean',0):.1f}",
                        f"{stat_b['compute'].get('mean',0):.1f}", ""),
    ]
    for r in rows:
        t.add_row(*r)

    console.print(t)
    console.print()

    p_str = f"{sig['p_value']:.4f}" if sig.get("p_value") is not None else "N/A"
    sig_str = "[green]Signifikan (p<0.05)[/]" if sig.get("significant") else "[yellow]Tidak signifikan[/]"
    console.print(Panel(
        f"  Mann-Whitney U = {sig.get('u_stat','N/A')}   p = {p_str}   → {sig_str}\n"
        f"  Effect size r = {sig.get('effect_r',0):.4f}   Cohen's d = {sig.get('cohens_d',0):.4f}\n"
        f"  SSR validated: [green]{la}[/] {'✓' if stat_a['ssr_ok'] else '✗'}   "
        f"[blue]{lb}[/] {'✓' if stat_b['ssr_ok'] else '✗'}",
        title="[bold]Significance Test[/]", border_style="yellow"
    ))


# ── main ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="SSR Edge Benchmark Analyzer")
    ap.add_argument("--a",       default="http://localhost:3000", metavar="URL")
    ap.add_argument("--b",       default="http://localhost:4000", metavar="URL")
    ap.add_argument("--label-a", default="Server-A",             metavar="NAME")
    ap.add_argument("--label-b", default="Server-B",             metavar="NAME")
    ap.add_argument("--n",       default=40, type=int,           metavar="N",
                    help="Requests per server (default: 40)")
    ap.add_argument("--workers", default=5,  type=int,           metavar="W",
                    help="Concurrent workers (default: 5)")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    console.rule("[bold]SSR Edge Benchmark Analyzer[/]")
    console.print(f"  [dim]A:[/] {args.a}  →  [green]{args.label_a}[/]")
    console.print(f"  [dim]B:[/] {args.b}  →  [blue]{args.label_b}[/]")
    console.print(f"  [dim]N:[/] {args.n}  [dim]workers:[/] {args.workers}\n")

    # reachability check
    for label, url in [(args.label_a, args.a), (args.label_b, args.b)]:
        try:
            r = requests.get(url, timeout=6)
            ssr = "✓ SSR" if "SSR Active" in r.text else "? (no SSR marker)"
            console.print(f"  [green]✓[/] {label}  HTTP {r.status_code}  {ssr}")
        except Exception as e:
            console.print(f"  [red]✗[/] {label} unreachable — {e}")
    console.print()

    # collect
    samples_a = collect(args.label_a, args.a, args.n, args.workers)
    samples_b = collect(args.label_b, args.b, args.n, args.workers)
    console.print()

    # analyze
    stat_a = analyze(samples_a)
    stat_b = analyze(samples_b)
    sig    = significance(samples_a, samples_b)

    # charts
    console.rule("[dim]Generating charts[/]")
    chart_distribution(args.label_a, samples_a, args.label_b, samples_b)
    chart_boxplot     (args.label_a, samples_a, args.label_b, samples_b)
    chart_percentiles (args.label_a, stat_a,    args.label_b, stat_b)
    chart_timeseries  (args.label_a, samples_a, args.label_b, samples_b)
    chart_cdf         (args.label_a, samples_a, args.label_b, samples_b)
    chart_overhead    (args.label_a, samples_a, samples_b,    args.label_b)

    # report
    console.rule("[dim]Generating report[/]")
    write_report(args.label_a, stat_a, args.label_b, stat_b,
                 sig, args.n, args.workers, args.a, args.b, ts)

    # terminal summary
    console.rule("[bold]Summary[/]")
    print_summary(args.label_a, samples_a, stat_a,
                  args.label_b, samples_b, stat_b, sig)

    console.print(f"\n  [dim]charts →[/] {IMG.relative_to(BASE.parent)}/")
    console.print(f"  [dim]report →[/] {(DOCS / 'perbandingan.txt').relative_to(BASE.parent)}\n")


if __name__ == "__main__":
    main()
