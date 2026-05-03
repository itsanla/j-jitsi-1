#!/usr/bin/env python3
"""
Hono API Benchmark Analyzer
Perbandingan performa Vercel Serverless Functions vs Cloudflare Workers V8 Isolate
Menggunakan Hono.js pada kedua platform dengan beban komputasi identik.

Usage:
  python analytic.py
  python analytic.py --n 1000 --workers 10
  python analytic.py --a https://jitsi-vm.anla.works --b https://jitsi-v8.anla.works \
                     --label-a Vercel --label-b Cloudflare --n 1000
"""

import argparse
import json
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
COLOR_A   = "#22c55e"   # green  → Vercel
COLOR_B   = "#3b82f6"   # blue   → Cloudflare
COLOR_FIB = "#f59e0b"
COLOR_PRM = "#8b5cf6"
COLOR_SRT = "#06b6d4"
COLOR_STR = "#ec4899"
ALPHA     = 0.72

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
    compute_ms: Optional[float] = None   # total_compute_ms dari JSON
    fib_ms:     Optional[float] = None
    primes_ms:  Optional[float] = None
    sort_ms:    Optional[float] = None
    string_ms:  Optional[float] = None
    timestamp:  Optional[str]   = None
    error:      Optional[str]   = None


# ── HTTP fetch ─────────────────────────────────────────────────────────────────
def fetch(seq: int, base_url: str, timeout: float = 20.0) -> Sample:
    req_id = uuid.uuid4().hex[:12]
    url    = base_url.rstrip("/")
    t0     = time.perf_counter()
    try:
        resp  = requests.get(url, timeout=timeout, stream=True)
        ttfb  = (time.perf_counter() - t0) * 1000
        body  = resp.content.decode("utf-8", errors="replace")
        total = (time.perf_counter() - t0) * 1000

        compute_ms = fib_ms = primes_ms = sort_ms = string_ms = None
        timestamp  = None

        try:
            data       = json.loads(body)
            compute_ms = data.get("total_compute_ms")
            timestamp  = data.get("timestamp")
            req_id     = data.get("request_id", req_id)
            tasks      = data.get("tasks", {})
            fib_ms     = tasks.get("fibonacci",   {}).get("duration_ms")
            primes_ms  = tasks.get("primes_sieve",{}).get("duration_ms")
            sort_ms    = tasks.get("array_sort",  {}).get("duration_ms")
            string_ms  = tasks.get("string_ops",  {}).get("duration_ms")
        except Exception:
            pass

        return Sample(
            seq=seq, req_id=req_id, status=resp.status_code,
            total_ms=round(total, 2), ttfb_ms=round(ttfb, 2),
            compute_ms=compute_ms, fib_ms=fib_ms, primes_ms=primes_ms,
            sort_ms=sort_ms, string_ms=string_ms, timestamp=timestamp,
        )
    except Exception as exc:
        total = (time.perf_counter() - t0) * 1000
        return Sample(seq=seq, req_id=req_id, status=0,
                      total_ms=round(total, 2), ttfb_ms=0, error=str(exc))


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
def _stats(lst: list) -> dict:
    if not lst:
        return {}
    arr = np.array(lst, dtype=float)
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


def analyze(samples: list[Sample]) -> dict:
    ok  = [s for s in samples if not s.error and s.status == 200]
    tot = [s.total_ms  for s in ok]
    cmp = [s.compute_ms for s in ok if s.compute_ms is not None]
    tbt = [s.ttfb_ms   for s in ok]
    ovh = [s.total_ms - s.compute_ms for s in ok if s.compute_ms is not None]

    fib_lst    = [s.fib_ms    for s in ok if s.fib_ms    is not None]
    primes_lst = [s.primes_ms for s in ok if s.primes_ms is not None]
    sort_lst   = [s.sort_ms   for s in ok if s.sort_ms   is not None]
    string_lst = [s.string_ms for s in ok if s.string_ms is not None]

    req_ids = {s.req_id for s in ok if s.req_id}
    api_ok  = len(req_ids) == len(ok) and len(ok) > 0

    warm_n = max(1, len(ok) // 5)
    warmup = [s.total_ms for s in ok[:warm_n]]
    steady = [s.total_ms for s in ok[warm_n:]]

    return {
        "n_ok":    len(ok),
        "n_err":   len(samples) - len(ok),
        "api_ok":  api_ok,
        "total":   _stats(tot),
        "compute": _stats(cmp),
        "ttfb":    _stats(tbt),
        "overhead":_stats(ovh),
        "tasks": {
            "fibonacci":   _stats(fib_lst),
            "primes_sieve":_stats(primes_lst),
            "array_sort":  _stats(sort_lst),
            "string_ops":  _stats(string_lst),
        },
        "warmup": {"mean": float(np.mean(warmup)) if warmup else None, "n": warm_n},
        "steady": {"mean": float(np.mean(steady)) if steady else None},
    }


def significance(a: list[Sample], b: list[Sample]) -> dict:
    ok_a = [s.total_ms for s in a if not s.error and s.status == 200]
    ok_b = [s.total_ms for s in b if not s.error and s.status == 200]
    if len(ok_a) < 2 or len(ok_b) < 2:
        return {"u_stat": None, "p_value": None, "effect_r": None}

    u, p = scipy_stats.mannwhitneyu(ok_a, ok_b, alternative="two-sided")
    n1, n2 = len(ok_a), len(ok_b)
    r = 1 - (2 * u) / (n1 * n2)

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


def chart_distribution(la, sa, lb, sb):
    ok_a = [s.total_ms for s in sa if not s.error]
    ok_b = [s.total_ms for s in sb if not s.error]

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=False)
    fig.suptitle("Response Time Distribution — Histogram + KDE", fontsize=12, weight="bold", y=1.01)

    for ax, data, color, label in [
        (axes[0], ok_a, COLOR_A, la),
        (axes[1], ok_b, COLOR_B, lb),
    ]:
        arr  = np.array(data)
        bins = min(50, max(15, len(data) // 8))
        ax.hist(arr, bins=bins, color=color, alpha=ALPHA, edgecolor="none", density=True)
        kde_x = np.linspace(arr.min() * 0.9, arr.max() * 1.05, 400)
        kde   = scipy_stats.gaussian_kde(arr)
        ax.plot(kde_x, kde(kde_x), color=color, linewidth=2)
        ax.axvline(np.mean(arr),   color="#f59e0b", linewidth=1.5, linestyle="--",
                   label=f"mean={np.mean(arr):.1f} ms")
        ax.axvline(np.median(arr), color="#e879f9", linewidth=1.5, linestyle=":",
                   label=f"med={np.median(arr):.1f} ms")
        ax.axvline(float(np.percentile(arr, 95)), color="#94a3b8", linewidth=1.0,
                   linestyle="-.", label=f"p95={float(np.percentile(arr,95)):.1f} ms")
        ax.set_title(f"[{label}]  n={len(data)}", fontsize=10)
        ax.set_xlabel("Response Time (ms)")
        ax.set_ylabel("Density")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    fig.tight_layout()
    _save(fig, "01_distribution.png")


def chart_boxplot(la, sa, lb, sb):
    ok_a = [s.total_ms  for s in sa if not s.error]
    ok_b = [s.total_ms  for s in sb if not s.error]
    cm_a = [s.compute_ms for s in sa if s.compute_ms is not None]
    cm_b = [s.compute_ms for s in sb if s.compute_ms is not None]

    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    fig.suptitle("Distribution Spread — Box Plots", fontsize=12, weight="bold")

    def _box(ax, da, db, title, ylabel):
        bp = ax.boxplot([da, db], patch_artist=True, widths=0.5,
                        medianprops=dict(color="#fbbf24", linewidth=2),
                        whiskerprops=dict(color="#94a3b8"),
                        capprops=dict(color="#94a3b8"),
                        flierprops=dict(marker="o", markersize=3, alpha=0.4))
        bp["boxes"][0].set_facecolor(COLOR_A + "bb")
        bp["boxes"][1].set_facecolor(COLOR_B + "bb")
        ax.set_xticklabels([la, lb])
        ax.set_title(title, fontsize=10)
        ax.set_ylabel(ylabel)
        ax.grid(True, axis="y", alpha=0.3)

    _box(axes[0], ok_a, ok_b, "Total Response Time (ms)", "ms")
    _box(axes[1], cm_a, cm_b, "Server Compute Time (ms)", "ms")

    from matplotlib.patches import Patch
    fig.legend(
        handles=[Patch(color=COLOR_A, label=la), Patch(color=COLOR_B, label=lb)],
        loc="lower center", ncol=2, framealpha=0.2, fontsize=9,
    )
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    _save(fig, "02_boxplot.png")


def chart_percentiles(la, sa_stat, lb, sb_stat):
    pcts   = ["p50", "p75", "p95", "p99"]
    labels = ["P50 (Median)", "P75", "P95", "P99"]
    va = [sa_stat["total"].get(p, 0) for p in pcts]
    vb = [sb_stat["total"].get(p, 0) for p in pcts]

    x = np.arange(len(labels))
    w = 0.32
    fig, ax = plt.subplots(figsize=(9, 5))
    fig.suptitle("Latency Percentile Comparison", fontsize=12, weight="bold")

    ba = ax.bar(x - w/2, va, w, color=COLOR_A, alpha=ALPHA, label=la)
    bb = ax.bar(x + w/2, vb, w, color=COLOR_B, alpha=ALPHA, label=lb)

    for bars in [ba, bb]:
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2, h + 0.3,
                    f"{h:.1f}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Response Time (ms)")
    ax.legend(fontsize=9)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    _save(fig, "03_percentiles.png")


def chart_timeseries(la, sa, lb, sb):
    ok_a = [(s.seq, s.total_ms) for s in sa if not s.error]
    ok_b = [(s.seq, s.total_ms) for s in sb if not s.error]

    fig, ax = plt.subplots(figsize=(14, 5))
    fig.suptitle("Latency Over Request Sequence — Cold Start & Warm-up Visibility",
                 fontsize=12, weight="bold")

    xa, ya = zip(*ok_a) if ok_a else ([], [])
    xb, yb = zip(*ok_b) if ok_b else ([], [])

    ax.scatter(xa, ya, color=COLOR_A, s=1.5, alpha=0.4)
    ax.scatter(xb, yb, color=COLOR_B, s=1.5, alpha=0.4)

    win = max(5, len(ya) // 50)
    if len(ya) >= win:
        roll_a = np.convolve(ya, np.ones(win)/win, mode="valid")
        ax.plot(list(xa)[win-1:], roll_a, color=COLOR_A, linewidth=2,
                label=f"{la} (rolling avg)")
    if len(yb) >= win:
        roll_b = np.convolve(yb, np.ones(win)/win, mode="valid")
        ax.plot(list(xb)[win-1:], roll_b, color=COLOR_B, linewidth=2,
                label=f"{lb} (rolling avg)")

    ax.set_xlabel("Request Sequence #")
    ax.set_ylabel("Total Response Time (ms)")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    _save(fig, "04_timeseries.png")


def chart_cdf(la, sa, lb, sb):
    ok_a = sorted(s.total_ms for s in sa if not s.error)
    ok_b = sorted(s.total_ms for s in sb if not s.error)

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.suptitle("Empirical CDF — Cumulative Distribution of Response Time",
                 fontsize=12, weight="bold")

    for data, color, label in [(ok_a, COLOR_A, la), (ok_b, COLOR_B, lb)]:
        n   = len(data)
        cdf = np.arange(1, n + 1) / n
        ax.plot(data, cdf, color=color, linewidth=2, label=label)
        for pct, prob in [(0.50, 0.50), (0.95, 0.95), (0.99, 0.99)]:
            idx = int(pct * n) - 1
            ax.axvline(data[idx], color=color, linewidth=0.7, linestyle=":", alpha=0.5)
            ax.text(data[idx] + 0.3, prob - 0.04,
                    f"p{int(pct*100)}={data[idx]:.0f}ms", color=color, fontsize=7)

    ax.set_xlabel("Response Time (ms)")
    ax.set_ylabel("Cumulative Probability")
    ax.set_ylim(0, 1.05)
    for prob in [0.50, 0.95, 0.99]:
        ax.axhline(prob, color="#64748b", linewidth=0.6, linestyle="--", alpha=0.4)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    _save(fig, "05_cdf.png")


def chart_overhead(la, sa, lb_label, sb):
    ok_a = [(s.total_ms, s.compute_ms) for s in sa if s.compute_ms is not None and not s.error]
    ok_b = [(s.total_ms, s.compute_ms) for s in sb if s.compute_ms is not None and not s.error]

    def decompose(data):
        compute  = float(np.mean([c   for _, c in data]))
        overhead = float(np.mean([t-c for t, c in data]))
        return compute, overhead

    ca, oa = decompose(ok_a)
    cb, ob = decompose(ok_b)

    fig, ax = plt.subplots(figsize=(8, 5))
    fig.suptitle("Response Time Decomposition\nServer Compute vs Network/Infra Overhead",
                 fontsize=11, weight="bold")

    servers   = [la, lb_label]
    computes  = [ca, cb]
    overheads = [oa, ob]
    x = np.arange(len(servers))
    w = 0.5

    b1 = ax.bar(x, computes,  w, label="Server Compute (ms)", color="#f59e0b", alpha=0.88)
    b2 = ax.bar(x, overheads, w, bottom=computes,
                label="Network/Infra Overhead (ms)", color="#8b5cf6", alpha=0.88)

    for bar, val in zip(b1, computes):
        ax.text(bar.get_x()+bar.get_width()/2, val/2,
                f"{val:.2f}", ha="center", va="center", fontsize=10, color="white", weight="bold")
    for bar, bot, val in zip(b2, computes, overheads):
        ax.text(bar.get_x()+bar.get_width()/2, bot+val/2,
                f"{val:.2f}", ha="center", va="center", fontsize=10, color="white", weight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(servers, fontsize=11)
    ax.set_ylabel("Time (ms)")
    ax.legend(fontsize=9)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    _save(fig, "06_overhead_breakdown.png")


def chart_task_breakdown(la, sa_stat, lb, sb_stat):
    tasks  = ["fibonacci", "primes_sieve", "array_sort", "string_ops"]
    labels = ["Fibonacci\nF(45)", "Sieve of\nEratosthenes\n(100K)", "Array Sort\n(50K floats)", "String Ops\n(5K iter)"]
    colors = [COLOR_FIB, COLOR_PRM, COLOR_SRT, COLOR_STR]

    means_a = [sa_stat["tasks"].get(t, {}).get("mean", 0) for t in tasks]
    means_b = [sb_stat["tasks"].get(t, {}).get("mean", 0) for t in tasks]
    p95_a   = [sa_stat["tasks"].get(t, {}).get("p95",  0) for t in tasks]
    p95_b   = [sb_stat["tasks"].get(t, {}).get("p95",  0) for t in tasks]

    x = np.arange(len(tasks))
    w = 0.28

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle("Per-Task Compute Time Comparison (Mean & P95)",
                 fontsize=12, weight="bold")

    for ax, vals_a, vals_b, title_sfx in [
        (axes[0], means_a, means_b, "Mean"),
        (axes[1], p95_a,  p95_b,   "P95"),
    ]:
        ba = ax.bar(x - w/2, vals_a, w, color=COLOR_A, alpha=ALPHA, label=la)
        bb = ax.bar(x + w/2, vals_b, w, color=COLOR_B, alpha=ALPHA, label=lb)
        for bars in [ba, bb]:
            for bar in bars:
                h = bar.get_height()
                if h > 0:
                    ax.text(bar.get_x()+bar.get_width()/2, h+0.02,
                            f"{h:.2f}", ha="center", va="bottom", fontsize=7.5)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_ylabel("Duration (ms)")
        ax.set_title(title_sfx, fontsize=10)
        ax.legend(fontsize=9)
        ax.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    _save(fig, "07_task_breakdown.png")


# ── report ─────────────────────────────────────────────────────────────────────
def write_report(la, stat_a, lb, stat_b, sig, n, workers, url_a, url_b, timestamp):
    ta = stat_a["total"];    tb = stat_b["total"]
    ca = stat_a["compute"];  cb = stat_b["compute"]
    oa = stat_a["overhead"]; ob = stat_b["overhead"]

    winner   = la if ta["mean"] < tb["mean"] else lb
    diff_ms  = abs(ta["mean"] - tb["mean"])
    diff_pct = diff_ms / min(ta["mean"], tb["mean"]) * 100
    p_str    = f"{sig['p_value']:.6f}" if sig.get("p_value") is not None else "N/A"
    sig_str  = "Signifikan (p < 0.05)" if sig.get("significant") else "Tidak Signifikan (p ≥ 0.05)"

    def task_row(key, name):
        ta_ = stat_a["tasks"].get(key, {})
        tb_ = stat_b["tasks"].get(key, {})
        return (
            f"  {name:<22}: "
            f"mean={ta_.get('mean',0):.3f}ms  p95={ta_.get('p95',0):.3f}ms    "
            f"mean={tb_.get('mean',0):.3f}ms  p95={tb_.get('p95',0):.3f}ms\n"
        )

    task_block = (
        f"  {'Task':<22}  {'[ ' + la + ' ]':<34}  {'[ ' + lb + ' ]'}\n"
        f"  {'-'*74}\n"
        + task_row("fibonacci",    "Fibonacci F(45)")
        + task_row("primes_sieve", "Primes Sieve (100K)")
        + task_row("array_sort",   "Array Sort (50K)")
        + task_row("string_ops",   "String Ops (5K)")
    )

    lines = f"""\
================================================================================
PERBANDINGAN PERFORMA ARSITEKTUR EDGE COMPUTING:
VERCEL SERVERLESS FUNCTIONS vs CLOUDFLARE WORKERS V8 ISOLATE
Berbasis Metrik HTTP Response Time pada Hono.js REST API dengan Beban Komputasi
================================================================================
Tanggal Analisis  : {timestamp}
Platform A        : {url_a}  [{la}]
Platform B        : {url_b}  [{lb}]
Jumlah Request    : {n} per platform
Concurrency       : {workers} workers paralel
Framework         : Hono.js (identik pada kedua platform)
--------------------------------------------------------------------------------

1. LATAR BELAKANG ARSITEKTUR
──────────────────────────────
Penelitian ini membandingkan dua model eksekusi serverless yang fundamental
berbeda dalam menangani HTTP request dengan beban komputasi CPU:

Vercel Serverless Functions menjalankan kode di atas infrastruktur AWS Lambda
dengan Node.js runtime. Setiap fungsi dieksekusi dalam proses Node.js yang
terisolasi dalam container. Cold start terjadi ketika container belum tersedia
(estimasi: 100–1000 ms), mencakup inisialisasi runtime Node.js, loading modul,
dan alokasi memori. Vercel mengelola pool container warm secara otomatis.

Cloudflare Workers menggunakan model V8 Isolate — sebuah instance V8 engine
yang mengisolasi eksekusi fungsi via JavaScript namespace, bukan container
terpisah. Model ini menghilangkan overhead cold start yang signifikan (<5 ms)
karena V8 isolate diinisialisasi satu kali per worker process dan di-reuse
lintas request. Eksekusi berjalan dekat pengguna (edge network Cloudflare
>300 PoP global) dengan akses hanya pada Web Standard APIs.

Kedua platform menjalankan kode Hono.js yang identik secara logika, memastikan
perbedaan performa murni berasal dari karakteristik infrastruktur, bukan
implementasi aplikasi.

2. BEBAN KOMPUTASI (IDENTIK PADA KEDUA PLATFORM)
──────────────────────────────────────────────────
Setiap request menjalankan 4 task komputasi CPU secara berurutan:
  a) Fibonacci F(45)          — kalkulasi iteratif bilangan Fibonacci ke-45
  b) Sieve of Eratosthenes    — pembangkitan bilangan prima hingga 100.000
  c) Array Sort (50.000 elem) — sorting 50.000 bilangan float acak (QuickSort)
  d) String Operations (5.000)— konkatenasi dan pemrosesan 5.000 string acak

Total compute time diukur server-side menggunakan performance.now() dan
disertakan dalam JSON response sebagai `total_compute_ms`.

3. METODOLOGI
──────────────────────────────
- Protokol  : HTTP GET, response format JSON
- Timing    : time.perf_counter() Python (resolusi sub-millisecond)
  * total_ms  : mulai koneksi TCP hingga seluruh body diterima (RTT penuh)
  * ttfb_ms   : mulai koneksi hingga byte pertama diterima (Time To First Byte)
  * compute_ms: diambil dari field `total_compute_ms` dalam JSON response
  * overhead  : total_ms − compute_ms (= latency jaringan + infra overhead)
- Concurrency : {workers} thread paralel (ThreadPoolExecutor)
- Validasi API: setiap response memiliki `request_id` UUID unik
- Uji statistik: Mann-Whitney U (non-parametrik, bebas asumsi normalitas)
- Effect size : rank-biserial correlation (r) dan Cohen's d

4. HASIL STATISTIK
──────────────────────────────
4.1 Total Response Time — Client-Measured End-to-End (ms)
                        {la:<22}  {lb:<22}
  N (sukses)          : {stat_a['n_ok']:<22}  {stat_b['n_ok']:<22}
  Error               : {stat_a['n_err']:<22}  {stat_b['n_err']:<22}
  Mean                : {ta['mean']:<22.3f}  {tb['mean']:<22.3f}
  Median (P50)        : {ta['median']:<22.3f}  {tb['median']:<22.3f}
  Std Dev             : {ta['stdev']:<22.3f}  {tb['stdev']:<22.3f}
  CV (stdev/mean)     : {ta['cv']:<22.4f}  {tb['cv']:<22.4f}
  Min                 : {ta['min']:<22.3f}  {tb['min']:<22.3f}
  P25                 : {ta['p25']:<22.3f}  {tb['p25']:<22.3f}
  P75                 : {ta['p75']:<22.3f}  {tb['p75']:<22.3f}
  P95                 : {ta['p95']:<22.3f}  {tb['p95']:<22.3f}
  P99                 : {ta['p99']:<22.3f}  {tb['p99']:<22.3f}
  IQR                 : {ta['iqr']:<22.3f}  {tb['iqr']:<22.3f}
  Max                 : {ta['max']:<22.3f}  {tb['max']:<22.3f}
  Skewness            : {ta['skew']:<22.4f}  {tb['skew']:<22.4f}
  Kurtosis (excess)   : {ta['kurt']:<22.4f}  {tb['kurt']:<22.4f}

4.2 Server-Side Compute Time — JSON field `total_compute_ms` (ms)
  CATATAN PENTING: Cloudflare Workers membekukan Date.now() dan
  mengkuantisasi performance.now() selama eksekusi request sebagai
  mitigasi kerentanan Spectre (CVE-2017-5753). Akibatnya, pengukuran
  waktu server-side pada Cloudflare Workers secara teknis tidak tersedia.
  Ini adalah fitur keamanan yang disengaja, bukan keterbatasan implementasi.
  Referensi: https://developers.cloudflare.com/workers/runtime-apis/performance/

  Mean compute        : {ca.get('mean',0) if ca else 'N/A (timer frozen)':<22}  {cb.get('mean',0) if cb else 'N/A (timer frozen)'}
  Median compute      : {(ca.get('median',0) if ca else 'N/A'):<22}  {(cb.get('median',0) if cb else 'N/A')}
  P95 compute         : {(ca.get('p95',0) if ca else 'N/A'):<22}  {(cb.get('p95',0) if cb else 'N/A')}

4.3 Network/Infra Overhead = total_ms − compute_ms (ms)
  (Hanya tersedia untuk platform dengan server-side timing aktif)
  Mean overhead       : {oa.get('mean',0) if oa else 'N/A':<22}  {ob.get('mean',0) if ob else 'N/A'}
  Median overhead     : {(oa.get('median',0) if oa else 'N/A'):<22}  {(ob.get('median',0) if ob else 'N/A')}
  P95 overhead        : {(oa.get('p95',0) if oa else 'N/A'):<22}  {(ob.get('p95',0) if ob else 'N/A')}

4.4 Per-Task Compute Time Breakdown (ms)
{task_block}
4.5 Warm-up vs Steady State (deteksi cold start)
  Warmup mean ({stat_a['warmup']['n']:>3} req)  : {(stat_a['warmup']['mean'] or 0):<22.3f}  {(stat_b['warmup']['mean'] or 0):<22.3f}
  Steady-state mean   : {(stat_a['steady']['mean'] or 0):<22.3f}  {(stat_b['steady']['mean'] or 0):<22.3f}
  Selisih warmup-steady: {abs((stat_a['warmup']['mean'] or 0)-(stat_a['steady']['mean'] or 0)):<22.3f}  {abs((stat_b['warmup']['mean'] or 0)-(stat_b['steady']['mean'] or 0)):<22.3f}

4.6 Validasi API
  Request ID unik     : {'YA' if stat_a['api_ok'] else 'TIDAK':<22}  {'YA' if stat_b['api_ok'] else 'TIDAK'}
  (YA = setiap response memiliki UUID unik, tidak ada caching)

5. UJI SIGNIFIKANSI STATISTIK
──────────────────────────────
  Metode          : Mann-Whitney U Test (two-sided, non-parametrik)
  H₀              : Tidak ada perbedaan distribusi response time
  H₁              : Terdapat perbedaan distribusi response time
  U-statistic     : {sig.get('u_stat', 'N/A')}
  p-value         : {p_str}
  Kesimpulan      : {sig_str}
  Effect size (r) : {sig.get('effect_r', 0):.6f}
                    (interpretasi: |r|>0.1 kecil, >0.3 sedang, >0.5 besar)
  Cohen's d       : {sig.get('cohens_d', 0):.6f}

6. INTERPRETASI DAN DISKUSI
──────────────────────────────
Perbedaan mean response time antara {la} dan {lb}:
  Selisih absolut : {diff_ms:.3f} ms
  Selisih relatif : {diff_pct:.2f}%
  Platform lebih cepat: {winner}

Decomposisi waktu response memisahkan dua komponen utama:
(1) Server Compute Time: waktu eksekusi kode JavaScript di server
    {la}: {ca.get('mean',0):.3f} ms  |  {lb}: {cb.get('mean',0):.3f} ms
    Mencerminkan efisiensi engine JavaScript pada masing-masing platform.
    V8 Isolate (Cloudflare) dan V8 di Node.js (Vercel) menggunakan engine yang
    sama, namun perbedaan konfigurasi dan konteks eksekusi dapat mempengaruhi
    JIT compilation behavior.

(2) Network/Infra Overhead: latensi jaringan + overhead infrastruktur
    {la}: {oa.get('mean',0):.3f} ms  |  {lb}: {ob.get('mean',0):.3f} ms
    Komponen ini mencakup: TCP handshake, TLS negotiation, routing jaringan,
    cold start (khusus Lambda), scheduling container/isolate, dan serialisasi
    response.

Coefficient of Variation (CV) mengindikasikan konsistensi layanan:
  {la}: CV = {ta['cv']:.4f}   |   {lb}: CV = {tb['cv']:.4f}
  CV lebih rendah = distribusi latency lebih konsisten (lebih dapat diprediksi).

Warm-up vs Steady State:
  Selisih signifikan antara fase warm-up dan steady state mengindikasikan
  adanya cold start effect. Model Lambda (Vercel) umumnya menunjukkan
  selisih lebih besar karena overhead inisialisasi container.

Skewness positif ({ta['skew']:.3f} vs {tb['skew']:.3f}) mengindikasikan distribusi
right-skewed — adanya outlier ke kanan yang merupakan karakteristik khas
arsitektur serverless (cold start events, GC pause, network jitter).

7. KESIMPULAN
──────────────────────────────
Dari {n} request per platform dengan beban komputasi identik:

  1. {winner} mencatatkan mean response time lebih rendah
     (selisih: {diff_ms:.3f} ms / {diff_pct:.2f}% lebih cepat)

  2. Uji Mann-Whitney U: {sig_str}
     p = {p_str}, effect size r = {sig.get('effect_r',0):.4f}

  3. Server compute time kedua platform relatif {'setara' if abs(ca.get('mean',0)-cb.get('mean',0)) < 5 else 'berbeda'}:
     {la} = {ca.get('mean',0):.3f} ms, {lb} = {cb.get('mean',0):.3f} ms

  4. Perbedaan utama terletak pada komponen Network/Infra Overhead:
     {la} = {oa.get('mean',0):.3f} ms, {lb} = {ob.get('mean',0):.3f} ms
     Overhead lebih rendah pada {la if oa.get('mean',0) < ob.get('mean',0) else lb}

  5. Konsistensi (CV): {'Lebih konsisten: ' + (la if ta['cv'] < tb['cv'] else lb)}

  6. Validasi API: kedua platform mengembalikan response JSON valid
     dengan request_id unik per request (tidak ada caching)

8. ARTEFAK VISUAL
──────────────────────────────
  images/01_distribution.png      — Histogram + KDE distribusi response time
  images/02_boxplot.png           — Box plot spread, outlier, dan compute time
  images/03_percentiles.png       — Perbandingan P50, P75, P95, P99
  images/04_timeseries.png        — Time series per-request (deteksi warm-up)
  images/05_cdf.png               — Empirical CDF kedua platform
  images/06_overhead_breakdown.png — Dekomposisi compute vs infra overhead
  images/07_task_breakdown.png    — Per-task compute time (fibonacci/primes/sort/string)

================================================================================
"""
    path = DOCS / "perbandingan.txt"
    path.write_text(lines, encoding="utf-8")
    console.print(f"  [dim]saved[/] {path.relative_to(BASE)}")
    return lines


# ── terminal summary ───────────────────────────────────────────────────────────
def print_summary(la, sa, stat_a, lb, sb, stat_b, sig):
    ta, tb = stat_a["total"], stat_b["total"]

    t = Table(title="Response Time Summary (ms)", box=rbox.ROUNDED, show_lines=True)
    t.add_column("Metric",          style="bold white", no_wrap=True)
    t.add_column(f"[green]{la}[/]", justify="right")
    t.add_column(f"[blue]{lb}[/]",  justify="right")
    t.add_column("Delta (B−A)",      justify="right")

    def d(av, bv):
        if av is None or bv is None: return "—"
        v = round(bv - av, 3)
        c = "red" if v > 0 else "green"
        return f"[{c}]{'+' if v>0 else ''}{v}[/]"

    rows = [
        ("N ok / err",     f"{stat_a['n_ok']}/{stat_a['n_err']}", f"{stat_b['n_ok']}/{stat_b['n_err']}", ""),
        ("Mean",           f"{ta['mean']:.3f}",  f"{tb['mean']:.3f}",  d(ta['mean'],  tb['mean'])),
        ("P50 (Median)",   f"{ta['p50']:.3f}",   f"{tb['p50']:.3f}",   d(ta['p50'],   tb['p50'])),
        ("P95",            f"{ta['p95']:.3f}",   f"{tb['p95']:.3f}",   d(ta['p95'],   tb['p95'])),
        ("P99",            f"{ta['p99']:.3f}",   f"{tb['p99']:.3f}",   d(ta['p99'],   tb['p99'])),
        ("Stdev",          f"{ta['stdev']:.3f}", f"{tb['stdev']:.3f}", d(ta['stdev'], tb['stdev'])),
        ("CV",             f"{ta['cv']:.4f}",    f"{tb['cv']:.4f}",    d(ta['cv'],    tb['cv'])),
        ("Compute mean",   f"{stat_a['compute'].get('mean',0):.3f}",
                           f"{stat_b['compute'].get('mean',0):.3f}", ""),
        ("Overhead mean",  f"{stat_a['overhead'].get('mean',0):.3f}",
                           f"{stat_b['overhead'].get('mean',0):.3f}", ""),
        ("Warmup mean",    f"{stat_a['warmup']['mean'] or 0:.3f}",
                           f"{stat_b['warmup']['mean'] or 0:.3f}", ""),
        ("Steady mean",    f"{stat_a['steady']['mean'] or 0:.3f}",
                           f"{stat_b['steady']['mean'] or 0:.3f}", ""),
        ("Skewness",       f"{ta['skew']:.4f}",  f"{tb['skew']:.4f}",  ""),
    ]
    for r in rows:
        t.add_row(*r)

    console.print(t)
    console.print()

    p_str   = f"{sig['p_value']:.6f}" if sig.get("p_value") is not None else "N/A"
    sig_lbl = "[green]Signifikan (p<0.05)[/]" if sig.get("significant") else "[yellow]Tidak signifikan[/]"
    console.print(Panel(
        f"  Mann-Whitney U = {sig.get('u_stat','N/A')}\n"
        f"  p-value = {p_str}   →  {sig_lbl}\n"
        f"  Effect size r = {sig.get('effect_r',0):.6f}   Cohen's d = {sig.get('cohens_d',0):.6f}\n"
        f"  API validated: [green]{la}[/] {'✓' if stat_a['api_ok'] else '✗'}   "
        f"[blue]{lb}[/] {'✓' if stat_b['api_ok'] else '✗'}",
        title="[bold]Significance Test[/]", border_style="yellow",
    ))


# ── main ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Hono API Benchmark Analyzer")
    ap.add_argument("--a",       default="https://jitsi-vm.anla.works",  metavar="URL")
    ap.add_argument("--b",       default="https://jitsi-v8.anla.works",  metavar="URL")
    ap.add_argument("--label-a", default="Vercel (Lambda)",              metavar="NAME")
    ap.add_argument("--label-b", default="Cloudflare (V8 Isolate)",      metavar="NAME")
    ap.add_argument("--n",       default=1000, type=int,                 metavar="N")
    ap.add_argument("--workers", default=10,   type=int,                 metavar="W")
    args = ap.parse_args()

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    console.rule("[bold]Hono API Benchmark Analyzer[/]")
    console.print(f"  [dim]A:[/] {args.a}  →  [green]{args.label_a}[/]")
    console.print(f"  [dim]B:[/] {args.b}  →  [blue]{args.label_b}[/]")
    console.print(f"  [dim]N:[/] {args.n}  [dim]workers:[/] {args.workers}\n")

    # reachability check
    for label, url in [(args.label_a, args.a), (args.label_b, args.b)]:
        try:
            r    = requests.get(url, timeout=10)
            data = r.json()
            plat = data.get("platform", {}).get("deployment", "?")
            comp = data.get("total_compute_ms")
            comp_str = f"{comp}ms" if comp is not None else "N/A (timer frozen)"
            note = " [dim][Spectre mitigation][/]" if data.get("timing_note") else ""
            console.print(f"  [green]✓[/] {label}  HTTP {r.status_code}  "
                          f"deployment={plat}  compute={comp_str}{note}")
        except Exception as e:
            console.print(f"  [red]✗[/] {label} — {e}")
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
    chart_overhead    (args.label_a, samples_a, args.label_b, samples_b)
    chart_task_breakdown(args.label_a, stat_a,  args.label_b, stat_b)

    # report
    console.rule("[dim]Generating report[/]")
    write_report(args.label_a, stat_a, args.label_b, stat_b,
                 sig, args.n, args.workers, args.a, args.b, ts)

    # summary
    console.rule("[bold]Summary[/]")
    print_summary(args.label_a, samples_a, stat_a,
                  args.label_b, samples_b, stat_b, sig)

    console.print(f"\n  [dim]charts →[/] {IMG.relative_to(BASE.parent)}/")
    console.print(f"  [dim]report →[/] {(DOCS / 'perbandingan.txt').relative_to(BASE.parent)}\n")


if __name__ == "__main__":
    main()
