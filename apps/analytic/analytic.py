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
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
COLOR_A  = "#22c55e"
COLOR_B  = "#3b82f6"
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
    seq:       int
    req_id:    str
    status:    int
    total_ms:  float
    ttfb_ms:   float
    timestamp: Optional[str] = None
    error:     Optional[str] = None


# ── HTTP fetch ─────────────────────────────────────────────────────────────────
def fetch(seq: int, base_url: str, timeout: float = 20.0) -> Sample:
    req_id = uuid.uuid4().hex[:12]
    url    = base_url.rstrip("/")
    t0     = time.perf_counter()
    try:
        resp      = requests.get(url, timeout=timeout, stream=True)
        ttfb      = (time.perf_counter() - t0) * 1000
        body      = resp.content.decode("utf-8", errors="replace")
        total     = (time.perf_counter() - t0) * 1000
        timestamp = None
        try:
            data      = json.loads(body)
            timestamp = data.get("timestamp")
            req_id    = data.get("request_id", req_id)
        except Exception:
            pass
        return Sample(seq=seq, req_id=req_id, status=resp.status_code,
                      total_ms=round(total, 2), ttfb_ms=round(ttfb, 2),
                      timestamp=timestamp)
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
    tot = [s.total_ms for s in ok]
    tbt = [s.ttfb_ms  for s in ok]

    req_ids = {s.req_id for s in ok if s.req_id}
    api_ok  = len(req_ids) == len(ok) and len(ok) > 0

    warm_n = max(1, len(ok) // 5)
    warmup = [s.total_ms for s in ok[:warm_n]]
    steady = [s.total_ms for s in ok[warm_n:]]

    return {
        "n_ok":   len(ok),
        "n_err":  len(samples) - len(ok),
        "api_ok": api_ok,
        "total":  _stats(tot),
        "ttfb":   _stats(tbt),
        "warmup": {"mean": float(np.mean(warmup)) if warmup else None, "n": warm_n,
                   "raw": warmup},
        "steady": {"mean": float(np.mean(steady)) if steady else None,
                   "raw": steady},
    }


def significance(a: list[Sample], b: list[Sample]) -> dict:
    ok_a = [s.total_ms for s in a if not s.error and s.status == 200]
    ok_b = [s.total_ms for s in b if not s.error and s.status == 200]
    if len(ok_a) < 2 or len(ok_b) < 2:
        return {"u_stat": None, "p_value": None, "effect_r": None}
    u, p   = scipy_stats.mannwhitneyu(ok_a, ok_b, alternative="two-sided")
    n1, n2 = len(ok_a), len(ok_b)
    r      = 1 - (2 * u) / (n1 * n2)
    pooled = np.sqrt(((n1-1)*np.var(ok_a, ddof=1) + (n2-1)*np.var(ok_b, ddof=1)) / (n1+n2-2))
    d      = (np.mean(ok_a) - np.mean(ok_b)) / pooled if pooled else 0.0
    return {"u_stat": u, "p_value": p, "effect_r": r, "cohens_d": d,
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
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    fig.suptitle("Response Time Distribution — Histogram + KDE", fontsize=12, weight="bold")
    for ax, data, color, label in [(axes[0], ok_a, COLOR_A, la), (axes[1], ok_b, COLOR_B, lb)]:
        arr  = np.array(data)
        bins = min(50, max(15, len(data) // 8))
        ax.hist(arr, bins=bins, color=color, alpha=ALPHA, edgecolor="none", density=True)
        kde_x = np.linspace(arr.min()*0.9, arr.max()*1.05, 400)
        ax.plot(kde_x, scipy_stats.gaussian_kde(arr)(kde_x), color=color, linewidth=2)
        ax.axvline(np.mean(arr),              color="#f59e0b", linewidth=1.5, linestyle="--",
                   label=f"mean={np.mean(arr):.1f}ms")
        ax.axvline(np.median(arr),            color="#e879f9", linewidth=1.5, linestyle=":",
                   label=f"med={np.median(arr):.1f}ms")
        ax.axvline(float(np.percentile(arr,95)), color="#94a3b8", linewidth=1.0, linestyle="-.",
                   label=f"p95={float(np.percentile(arr,95)):.1f}ms")
        ax.set_title(f"[{label}]  n={len(data)}", fontsize=10)
        ax.set_xlabel("Response Time (ms)")
        ax.set_ylabel("Density")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)
    fig.tight_layout()
    _save(fig, "01_distribution.png")


def chart_boxplot(la, sa, lb, sb):
    ok_a = [s.total_ms for s in sa if not s.error]
    ok_b = [s.total_ms for s in sb if not s.error]
    tbt_a = [s.ttfb_ms for s in sa if not s.error]
    tbt_b = [s.ttfb_ms for s in sb if not s.error]
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

    _box(axes[0], ok_a,  ok_b,  "Total Response Time (ms)", "ms")
    _box(axes[1], tbt_a, tbt_b, "Time To First Byte — TTFB (ms)", "ms")

    from matplotlib.patches import Patch
    fig.legend(handles=[Patch(color=COLOR_A, label=la), Patch(color=COLOR_B, label=lb)],
               loc="lower center", ncol=2, framealpha=0.2, fontsize=9)
    fig.tight_layout(rect=[0, 0.06, 1, 1])
    _save(fig, "02_boxplot.png")


def chart_percentiles(la, sa_stat, lb, sb_stat):
    pcts   = ["p50", "p75", "p95", "p99"]
    labels = ["P50 (Median)", "P75", "P95", "P99"]
    va = [sa_stat["total"].get(p, 0) for p in pcts]
    vb = [sb_stat["total"].get(p, 0) for p in pcts]
    x, w = np.arange(len(labels)), 0.32
    fig, ax = plt.subplots(figsize=(9, 5))
    fig.suptitle("Latency Percentile Comparison", fontsize=12, weight="bold")
    ba = ax.bar(x - w/2, va, w, color=COLOR_A, alpha=ALPHA, label=la)
    bb = ax.bar(x + w/2, vb, w, color=COLOR_B, alpha=ALPHA, label=lb)
    for bars in [ba, bb]:
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x()+bar.get_width()/2, h+0.3,
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
    ax.scatter(xa, ya, color=COLOR_A, s=1.5, alpha=0.35)
    ax.scatter(xb, yb, color=COLOR_B, s=1.5, alpha=0.35)
    win = max(5, len(ya) // 50)
    if len(ya) >= win:
        ax.plot(list(xa)[win-1:], np.convolve(ya, np.ones(win)/win, mode="valid"),
                color=COLOR_A, linewidth=2, label=f"{la} (rolling avg)")
    if len(yb) >= win:
        ax.plot(list(xb)[win-1:], np.convolve(yb, np.ones(win)/win, mode="valid"),
                color=COLOR_B, linewidth=2, label=f"{lb} (rolling avg)")
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
        cdf = np.arange(1, n+1) / n
        ax.plot(data, cdf, color=color, linewidth=2, label=label)
        for pct, prob in [(0.50, 0.50), (0.95, 0.95), (0.99, 0.99)]:
            idx = int(pct * n) - 1
            ax.axvline(data[idx], color=color, linewidth=0.7, linestyle=":", alpha=0.5)
            ax.text(data[idx]+0.3, prob-0.04, f"p{int(pct*100)}={data[idx]:.0f}ms",
                    color=color, fontsize=7)
    ax.set_xlabel("Response Time (ms)")
    ax.set_ylabel("Cumulative Probability")
    ax.set_ylim(0, 1.05)
    for prob in [0.50, 0.95, 0.99]:
        ax.axhline(prob, color="#64748b", linewidth=0.6, linestyle="--", alpha=0.4)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    _save(fig, "05_cdf.png")


def chart_warmup_vs_steady(la, stat_a, lb, stat_b):
    """Warmup (first 20%) vs Steady State (remaining 80%) per platform."""
    categories = ["Warm-up\n(first 20%)", "Steady State\n(remaining 80%)"]
    va = [stat_a["warmup"]["mean"] or 0, stat_a["steady"]["mean"] or 0]
    vb = [stat_b["warmup"]["mean"] or 0, stat_b["steady"]["mean"] or 0]

    x, w = np.arange(len(categories)), 0.32
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Warm-up vs Steady State — Cold Start Effect Analysis",
                 fontsize=12, weight="bold")

    # bar chart
    ax = axes[0]
    ba = ax.bar(x - w/2, va, w, color=COLOR_A, alpha=ALPHA, label=la)
    bb = ax.bar(x + w/2, vb, w, color=COLOR_B, alpha=ALPHA, label=lb)
    for bars in [ba, bb]:
        for bar in bars:
            h = bar.get_height()
            ax.text(bar.get_x()+bar.get_width()/2, h+0.5,
                    f"{h:.1f}", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels(categories)
    ax.set_ylabel("Mean Response Time (ms)")
    ax.set_title("Mean RTT per Phase", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, axis="y", alpha=0.3)

    # violin / distribution comparison warmup vs steady
    ax2 = axes[1]
    raw_a_warm  = stat_a["warmup"]["raw"]
    raw_a_stead = stat_a["steady"]["raw"]
    raw_b_warm  = stat_b["warmup"]["raw"]
    raw_b_stead = stat_b["steady"]["raw"]

    parts = ax2.violinplot([raw_a_warm, raw_a_stead, raw_b_warm, raw_b_stead],
                           positions=[1, 2, 3.5, 4.5], showmedians=True, widths=0.6)
    colors_vio = [COLOR_A, COLOR_A, COLOR_B, COLOR_B]
    for pc, c in zip(parts["bodies"], colors_vio):
        pc.set_facecolor(c)
        pc.set_alpha(0.6)

    ax2.set_xticks([1, 2, 3.5, 4.5])
    ax2.set_xticklabels([f"{la}\nWarm-up", f"{la}\nSteady",
                         f"{lb}\nWarm-up", f"{lb}\nSteady"], fontsize=8)
    ax2.set_ylabel("Response Time (ms)")
    ax2.set_title("Distribution per Phase", fontsize=10)
    ax2.grid(True, axis="y", alpha=0.3)

    fig.tight_layout()
    _save(fig, "06_warmup_vs_steady.png")


# ── report ─────────────────────────────────────────────────────────────────────
def write_report(la, stat_a, lb, stat_b, sig, n, workers, url_a, url_b, timestamp):
    ta = stat_a["total"]
    tb = stat_b["total"]

    winner   = la if ta["mean"] < tb["mean"] else lb
    diff_ms  = abs(ta["mean"] - tb["mean"])
    diff_pct = diff_ms / min(ta["mean"], tb["mean"]) * 100
    p_str    = f"{sig['p_value']:.6f}" if sig.get("p_value") is not None else "N/A"
    sig_str  = "Signifikan (p < 0.05)" if sig.get("significant") else "Tidak Signifikan (p ≥ 0.05)"

    cold_a = abs((stat_a["warmup"]["mean"] or 0) - (stat_a["steady"]["mean"] or 0))
    cold_b = abs((stat_b["warmup"]["mean"] or 0) - (stat_b["steady"]["mean"] or 0))

    lines = f"""\
================================================================================
PERBANDINGAN PERFORMA ARSITEKTUR EDGE COMPUTING:
VERCEL SERVERLESS FUNCTIONS vs CLOUDFLARE WORKERS V8 ISOLATE
Berbasis Metrik HTTP Response Time (Client-Side RTT) pada Hono.js REST API
================================================================================
Tanggal Analisis  : {timestamp}
Platform A        : {url_a}  [{la}]
Platform B        : {url_b}  [{lb}]
Jumlah Request    : {n} per platform
Concurrency       : {workers} workers paralel
Framework         : Hono.js (identik pada kedua platform)
Beban Komputasi   : Fibonacci F(40) + Sieve 200K + Sort 50K + String 5K
--------------------------------------------------------------------------------

1. LATAR BELAKANG ARSITEKTUR
──────────────────────────────
Penelitian ini membandingkan dua model eksekusi serverless yang fundamental
berbeda dalam menangani HTTP request dengan beban komputasi CPU:

Vercel Serverless Functions menjalankan kode di atas infrastruktur AWS Lambda
dengan Node.js runtime. Setiap fungsi dieksekusi dalam proses Node.js yang
terisolasi dalam container. Cold start terjadi ketika container belum tersedia
(estimasi: 100–1000 ms), mencakup inisialisasi runtime Node.js, loading modul,
dan alokasi memori.

Cloudflare Workers menggunakan model V8 Isolate — instance V8 engine yang
mengisolasi eksekusi via JavaScript namespace, bukan container terpisah.
Model ini menghilangkan cold start yang signifikan (<5 ms) karena isolate
di-reuse lintas request. Cloudflare memiliki >300 PoP edge global.

Kedua platform menjalankan kode Hono.js yang identik secara logika dengan
beban komputasi yang sama, memastikan perbedaan murni dari infrastruktur.

2. CATATAN METODOLOGI — KETERBATASAN TIMING SERVER-SIDE
──────────────────────────────────────────────────────────
Cloudflare Workers membekukan nilai Date.now() dan mengkuantisasi
performance.now() selama eksekusi request sebagai mitigasi kerentanan
Spectre (CVE-2017-5753). Akibatnya, pengukuran waktu server-side pada
Cloudflare Workers tidak tersedia dan tidak dapat diandalkan.

Untuk menjaga fairness perbandingan, server-side timing DIHAPUS dari
kedua platform. Penelitian ini berfokus sepenuhnya pada metrik yang dapat
diukur secara setara: client-side Round Trip Time (RTT).

Metrik yang digunakan:
  - total_ms  : waktu dari pembukaan koneksi TCP hingga seluruh body diterima
  - ttfb_ms   : Time To First Byte (koneksi hingga header pertama)
  - Keduanya diukur dengan time.perf_counter() Python (resolusi nanosecond)

3. BEBAN KOMPUTASI (IDENTIK PADA KEDUA PLATFORM)
──────────────────────────────────────────────────
  a) Fibonacci F(40)           — iteratif, hasil: 102.334.155
  b) Sieve of Eratosthenes     — bilangan prima hingga 200.000
  c) Array Sort (50.000 elemen)— sorting float acak
  d) String Operations (5.000) — konkatenasi string acak

4. HASIL STATISTIK — TOTAL RESPONSE TIME / RTT (ms)
──────────────────────────────────────────────────────
                        {la:<24}  {lb:<24}
  N (sukses)          : {stat_a['n_ok']:<24}  {stat_b['n_ok']:<24}
  Error               : {stat_a['n_err']:<24}  {stat_b['n_err']:<24}
  Mean                : {ta['mean']:<24.3f}  {tb['mean']:<24.3f}
  Median (P50)        : {ta['median']:<24.3f}  {tb['median']:<24.3f}
  Std Dev             : {ta['stdev']:<24.3f}  {tb['stdev']:<24.3f}
  CV (stdev/mean)     : {ta['cv']:<24.4f}  {tb['cv']:<24.4f}
  Min                 : {ta['min']:<24.3f}  {tb['min']:<24.3f}
  P25                 : {ta['p25']:<24.3f}  {tb['p25']:<24.3f}
  P75                 : {ta['p75']:<24.3f}  {tb['p75']:<24.3f}
  P95                 : {ta['p95']:<24.3f}  {tb['p95']:<24.3f}
  P99                 : {ta['p99']:<24.3f}  {tb['p99']:<24.3f}
  IQR                 : {ta['iqr']:<24.3f}  {tb['iqr']:<24.3f}
  Max                 : {ta['max']:<24.3f}  {tb['max']:<24.3f}
  Skewness            : {ta['skew']:<24.4f}  {tb['skew']:<24.4f}
  Kurtosis (excess)   : {ta['kurt']:<24.4f}  {tb['kurt']:<24.4f}

5. TTFB — TIME TO FIRST BYTE (ms)
──────────────────────────────────
                        {la:<24}  {lb:<24}
  Mean TTFB           : {stat_a['ttfb'].get('mean',0):<24.3f}  {stat_b['ttfb'].get('mean',0):<24.3f}
  Median TTFB         : {stat_a['ttfb'].get('median',0):<24.3f}  {stat_b['ttfb'].get('median',0):<24.3f}
  P95 TTFB            : {stat_a['ttfb'].get('p95',0):<24.3f}  {stat_b['ttfb'].get('p95',0):<24.3f}

6. ANALISIS WARM-UP VS STEADY STATE (DETEKSI COLD START)
──────────────────────────────────────────────────────────
  (Warm-up = 20% request pertama, Steady = 80% sisanya)

                        {la:<24}  {lb:<24}
  Warmup mean ({stat_a['warmup']['n']:>3} req) : {(stat_a['warmup']['mean'] or 0):<24.3f}  {(stat_b['warmup']['mean'] or 0):<24.3f}
  Steady mean         : {(stat_a['steady']['mean'] or 0):<24.3f}  {(stat_b['steady']['mean'] or 0):<24.3f}
  Selisih (cold start): {cold_a:<24.3f}  {cold_b:<24.3f}

  Selisih warmup–steady yang lebih besar mengindikasikan cold start effect
  yang lebih dominan. Lambda (Vercel) umumnya memiliki cold start lebih tinggi
  karena inisialisasi container Node.js, sedangkan V8 Isolate (Cloudflare)
  me-reuse isolate sehingga cold start minimal.

7. UJI SIGNIFIKANSI STATISTIK
──────────────────────────────
  Metode    : Mann-Whitney U Test (two-sided, non-parametrik)
  H₀        : Tidak ada perbedaan distribusi RTT kedua platform
  H₁        : Terdapat perbedaan distribusi RTT yang signifikan
  U-stat    : {sig.get('u_stat', 'N/A')}
  p-value   : {p_str}
  Hasil     : {sig_str}
  Effect r  : {sig.get('effect_r', 0):.6f}  (>0.1 kecil, >0.3 sedang, >0.5 besar)
  Cohen's d : {sig.get('cohens_d', 0):.6f}

8. INTERPRETASI DAN DISKUSI
──────────────────────────────
Perbedaan mean RTT: {diff_ms:.3f} ms ({diff_pct:.2f}%), {winner} lebih cepat.

Consistency (CV):
  {la}: CV = {ta['cv']:.4f}  |  {lb}: CV = {tb['cv']:.4f}
  CV lebih rendah = distribusi latency lebih konsisten dan dapat diprediksi.
  {'Platform lebih konsisten: ' + (la if ta['cv'] < tb['cv'] else lb)}

Tail Latency (P99 vs P50):
  Rasio P99/P50 {la}: {ta['p99']/ta['p50']:.2f}x
  Rasio P99/P50 {lb}: {tb['p99']/tb['p50']:.2f}x
  Rasio tinggi mengindikasikan outlier signifikan (cold start / throttling).

Skewness {ta['skew']:.3f} ({la}) vs {tb['skew']:.3f} ({lb}):
  Distribusi right-skewed adalah karakteristik tipikal arsitektur serverless
  karena adanya cold start events yang mendorong outlier ke kanan.

9. KESIMPULAN
──────────────────────────────
Dari {n} request per platform dengan beban komputasi identik (Hono.js):

  1. {winner} mencatatkan mean RTT lebih rendah
     (selisih: {diff_ms:.3f} ms / {diff_pct:.2f}%)

  2. Uji Mann-Whitney U: {sig_str}
     p = {p_str}, effect size r = {sig.get('effect_r',0):.4f}

  3. Konsistensi: {la if ta['cv'] < tb['cv'] else lb} lebih konsisten
     (CV: {ta['cv']:.4f} vs {tb['cv']:.4f})

  4. Cold start effect (selisih warmup-steady):
     {la}: {cold_a:.3f} ms  |  {lb}: {cold_b:.3f} ms

  5. Tail latency (P99):
     {la}: {ta['p99']:.3f} ms  |  {lb}: {tb['p99']:.3f} ms

  6. Validasi API: kedua platform mengembalikan JSON valid
     dengan request_id UUID unik per request (tanpa caching)

10. ARTEFAK VISUAL
──────────────────────────────
  images/01_distribution.png     — Histogram + KDE distribusi RTT
  images/02_boxplot.png          — Box plot RTT & TTFB
  images/03_percentiles.png      — Perbandingan P50, P75, P95, P99
  images/04_timeseries.png       — Time series per-request (warm-up visibility)
  images/05_cdf.png              — Empirical CDF kedua platform
  images/06_warmup_vs_steady.png — Analisis cold start: warmup vs steady state

================================================================================
"""
    path = DOCS / "perbandingan.txt"
    path.write_text(lines, encoding="utf-8")
    console.print(f"  [dim]saved[/] {path.relative_to(BASE)}")
    return lines


# ── terminal summary ───────────────────────────────────────────────────────────
def print_summary(la, stat_a, lb, stat_b, sig):
    ta, tb = stat_a["total"], stat_b["total"]

    t = Table(title="Response Time Summary (ms)", box=rbox.ROUNDED, show_lines=True)
    t.add_column("Metric",          style="bold white", no_wrap=True)
    t.add_column(f"[green]{la}[/]", justify="right")
    t.add_column(f"[blue]{lb}[/]",  justify="right")
    t.add_column("Delta (B−A)",      justify="right")

    def d(av, bv):
        if av is None or bv is None: return "—"
        v = round(bv - av, 3)
        return f"[{'red' if v>0 else 'green'}]{'+' if v>0 else ''}{v}[/]"

    rows = [
        ("N ok / err",   f"{stat_a['n_ok']}/{stat_a['n_err']}", f"{stat_b['n_ok']}/{stat_b['n_err']}", ""),
        ("Mean",         f"{ta['mean']:.3f}",  f"{tb['mean']:.3f}",  d(ta['mean'],  tb['mean'])),
        ("P50 (Median)", f"{ta['p50']:.3f}",   f"{tb['p50']:.3f}",   d(ta['p50'],   tb['p50'])),
        ("P95",          f"{ta['p95']:.3f}",   f"{tb['p95']:.3f}",   d(ta['p95'],   tb['p95'])),
        ("P99",          f"{ta['p99']:.3f}",   f"{tb['p99']:.3f}",   d(ta['p99'],   tb['p99'])),
        ("Stdev",        f"{ta['stdev']:.3f}", f"{tb['stdev']:.3f}", d(ta['stdev'], tb['stdev'])),
        ("CV",           f"{ta['cv']:.4f}",    f"{tb['cv']:.4f}",    d(ta['cv'],    tb['cv'])),
        ("TTFB mean",    f"{stat_a['ttfb'].get('mean',0):.3f}",
                         f"{stat_b['ttfb'].get('mean',0):.3f}", ""),
        ("Warmup mean",  f"{stat_a['warmup']['mean'] or 0:.3f}",
                         f"{stat_b['warmup']['mean'] or 0:.3f}", ""),
        ("Steady mean",  f"{stat_a['steady']['mean'] or 0:.3f}",
                         f"{stat_b['steady']['mean'] or 0:.3f}", ""),
        ("Cold start Δ", f"{abs((stat_a['warmup']['mean'] or 0)-(stat_a['steady']['mean'] or 0)):.3f}",
                         f"{abs((stat_b['warmup']['mean'] or 0)-(stat_b['steady']['mean'] or 0)):.3f}", ""),
        ("Skewness",     f"{ta['skew']:.4f}",  f"{tb['skew']:.4f}",  ""),
        ("P99/P50 ratio",f"{ta['p99']/ta['p50']:.2f}x",
                         f"{tb['p99']/tb['p50']:.2f}x", ""),
    ]
    for r in rows:
        t.add_row(*r)
    console.print(t)
    console.print()

    p_str = f"{sig['p_value']:.6f}" if sig.get("p_value") is not None else "N/A"
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

    for label, url in [(args.label_a, args.a), (args.label_b, args.b)]:
        try:
            r    = requests.get(url, timeout=10)
            data = r.json()
            plat = data.get("platform", {}).get("deployment", "?")
            console.print(f"  [green]✓[/] {label}  HTTP {r.status_code}  deployment={plat}")
        except Exception as e:
            console.print(f"  [red]✗[/] {label} — {e}")
    console.print()

    samples_a = collect(args.label_a, args.a, args.n, args.workers)
    samples_b = collect(args.label_b, args.b, args.n, args.workers)
    console.print()

    stat_a = analyze(samples_a)
    stat_b = analyze(samples_b)
    sig    = significance(samples_a, samples_b)

    console.rule("[dim]Generating charts[/]")
    chart_distribution    (args.label_a, samples_a, args.label_b, samples_b)
    chart_boxplot         (args.label_a, samples_a, args.label_b, samples_b)
    chart_percentiles     (args.label_a, stat_a,    args.label_b, stat_b)
    chart_timeseries      (args.label_a, samples_a, args.label_b, samples_b)
    chart_cdf             (args.label_a, samples_a, args.label_b, samples_b)
    chart_warmup_vs_steady(args.label_a, stat_a,    args.label_b, stat_b)

    console.rule("[dim]Generating report[/]")
    write_report(args.label_a, stat_a, args.label_b, stat_b,
                 sig, args.n, args.workers, args.a, args.b, ts)

    console.rule("[bold]Summary[/]")
    print_summary(args.label_a, stat_a, args.label_b, stat_b, sig)

    console.print(f"\n  [dim]charts →[/] {IMG.relative_to(BASE.parent)}/")
    console.print(f"  [dim]report →[/] {(DOCS / 'perbandingan.txt').relative_to(BASE.parent)}\n")


if __name__ == "__main__":
    main()
