#!/usr/bin/env python3
"""Charts for the article (PNG, for Medium). Run with /tmp/krypta-bench/venv/bin/python.

Usage: plots.py [results dir] [output dir]
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

RESULTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/tmp/krypta-bench/results')
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else RESULTS / 'charts'
OUT.mkdir(parents=True, exist_ok=True)

SURFACE, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7'
ARMS = ['A', 'B', 'C']
COLOR = {'A': '#2a78d6', 'B': '#eb6834', 'C': '#1baf7a'}
ARM_LABEL = {'A': 'A  as-is', 'B': 'B  better context', 'C': 'C  lean code'}
TASKS = ['T1', 'T2', 'T3']
TASK_LABEL = {'T1': 'T1  Sort order', 'T2': 'T2  Pinned entries', 'T3': 'T3  Password generator'}
FOOTNOTE = 'Claude Opus 5.5 (xhigh effort), Claude Code 2.1.289 headless. Cost at list price as reported by Claude Code.'

plt.rcParams.update({
    'font.family': ['Helvetica Neue', 'Helvetica', 'Arial', 'DejaVu Sans'],
    'font.size': 11, 'axes.edgecolor': AXIS, 'axes.labelcolor': INK2, 'xtick.color': INK2,
    'ytick.color': MUTED, 'axes.titlecolor': INK, 'figure.facecolor': SURFACE, 'axes.facecolor': SURFACE,
    'savefig.facecolor': SURFACE, 'axes.spines.top': False, 'axes.spines.right': False,
    'axes.spines.left': False, 'axes.grid': True, 'axes.grid.axis': 'y', 'grid.color': GRID,
    'grid.linewidth': 0.8, 'grid.linestyle': '-', 'xtick.major.size': 0, 'ytick.major.size': 0,
})


def load():
    runs = []
    for path in sorted(RESULTS.glob('*/meta.json')):
        m = json.loads(path.read_text())
        if m.get('status') == 'done' and m.get('rep', 0) >= 1:
            runs.append(m)
    return runs


def header(fig, title, subtitle):
    fig.text(0.02, 0.965, title, fontsize=16, fontweight='bold', color=INK, va='top')
    fig.text(0.02, 0.905, subtitle, fontsize=11.5, color=INK2, va='top')
    fig.text(0.02, 0.02, FOOTNOTE, fontsize=9, color=MUTED, va='bottom')


def cost_per_task(runs):
    fig, axes = plt.subplots(1, 3, figsize=(12, 5.2), dpi=200)
    fig.subplots_adjust(left=0.06, right=0.99, top=0.70, bottom=0.14, wspace=0.28)
    rng = np.random.default_rng(7)
    for ax, task in zip(axes, TASKS):
        top = max([r['total_cost_usd'] for r in runs if r['task'] == task] or [1]) * 1.18
        for i, arm in enumerate(ARMS):
            cell = [r for r in runs if r['task'] == task and r['arm'] == arm]
            if not cell:
                continue
            costs = np.array([r['total_cost_usd'] for r in cell])
            xs = i + rng.uniform(-0.11, 0.11, len(cell))
            for x, r in zip(xs, cell):
                ok = r.get('success')
                ax.plot(x, r['total_cost_usd'], 'o', ms=8.5, mfc=COLOR[arm] if ok else SURFACE,
                        mec=COLOR[arm] if not ok else SURFACE, mew=2 if not ok else 1.5, zorder=3)
            med = float(np.median(costs))
            ax.hlines(med, i - 0.27, i + 0.27, color=INK, lw=2, zorder=4, capstyle='round')
            ax.text(i + 0.31, med, f'${med:.2f}', va='center', ha='left', fontsize=10.5, color=INK, zorder=5)
        ax.set_xlim(-0.5, 2.85)
        ax.set_ylim(0, top)
        ax.set_xticks(range(3), ARMS, fontsize=12, fontweight='bold')
        for tick, arm in zip(ax.get_xticklabels(), ARMS):
            tick.set_color(INK)
        ax.yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(1.0 if top > 4 else 0.5))
        ax.yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter('${x:,.2f}'))
        ax.set_title(TASK_LABEL[task], loc='left', fontsize=12, fontweight='bold', pad=10)
    failed = sum(1 for r in runs if not r.get('success'))
    note = (f'Each dot is one run; all {len(runs)} passed every check.' if not failed
            else 'Each dot is one run (filled = all checks passed, hollow = failed).')
    header(fig, 'Cost per run, by task and version', note + ' The line and label mark the median.')
    keys = '   '.join(f'{arm} = {ARM_LABEL[arm].split("  ")[1]}' for arm in ARMS)
    fig.text(0.02, 0.85, keys, fontsize=11.5, color=INK2, va='top')
    fig.savefig(OUT / 'cost_per_task.png')
    plt.close(fig)


def relative(stats):
    pooled = stats.get('pooled', {})
    measures = [('cost', 'Cost'), ('api_calls', 'API calls'), ('cache_read', 'Tokens read from cache')]
    fig, axes = plt.subplots(1, len(measures), figsize=(12, 4.8), dpi=200, sharey=True)
    fig.subplots_adjust(left=0.07, right=0.99, top=0.74, bottom=0.17, wspace=0.12)
    for ax, (key, label) in zip(axes, measures):
        data = pooled.get(key, {})
        ax.axhline(1.0, color=COLOR['A'], lw=2, zorder=2)
        ax.text(-0.42, 1.0, 'A = 1.0', va='bottom', ha='left', fontsize=10, color=INK2)
        for i, arm in enumerate(['B', 'C'], start=1):
            eff = data.get(f'A->{arm}')
            if not eff:
                continue
            lo, hi = eff['ci95']
            ax.vlines(i - 0.5, lo, hi, color=COLOR[arm], lw=2, zorder=3)
            ax.plot(i - 0.5, eff['ratio'], 'o', ms=10, mfc=COLOR[arm], mec=SURFACE, mew=1.5, zorder=4)
            ax.text(i - 0.5 + 0.09, eff['ratio'], f'{eff["ratio"]:.2f}', va='center', ha='left',
                    fontsize=10.5, color=INK)
        ax.set_xlim(-0.5, 2.15)
        ax.set_xticks([0.5, 1.5], ['B', 'C'], fontsize=12, fontweight='bold')
        ax.set_title(label, loc='left', fontsize=12, fontweight='bold', pad=10)
    axes[0].set_ylim(0, 1.6)
    axes[0].yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter('{x:.1f}'))
    header(fig, 'Relative to the as-is version, all tasks pooled',
           'Each run divided by version A’s median on the same task, then compared by median; bars are 95% bootstrap intervals.')
    fig.savefig(OUT / 'relative_pooled.png')
    plt.close(fig)


def cost_components(rows):
    parts = [('usd_cache_writes', 'Writing new context to cache'), ('usd_output', 'Model output'),
             ('usd_history_reads', 'Re-reading the conversation'), ('usd_prefix_reads', 'Re-reading the fixed prefix')]
    fig, axes = plt.subplots(1, len(parts), figsize=(12, 4.6), dpi=200, sharey=True)
    fig.subplots_adjust(left=0.06, right=0.99, top=0.72, bottom=0.16, wspace=0.14)
    top = max(np.median([r[k] for r in rows if r['arm'] == arm]) for k, _ in parts for arm in ARMS) * 1.25
    for ax, (key, label) in zip(axes, parts):
        for i, arm in enumerate(ARMS):
            sel = [r[key] for r in rows if r['arm'] == arm]
            if not sel:
                continue
            med = float(np.median(sel))
            ax.bar(i, med, width=0.42, color=COLOR[arm], zorder=3)
            ax.text(i, med + top * 0.02, f'${med:.2f}', ha='center', va='bottom', fontsize=10.5, color=INK)
        ax.set_xticks(range(3), ARMS, fontsize=12)
        for tick in ax.get_xticklabels():
            tick.set_color(INK)
        ax.set_title(label, loc='left', fontsize=11.5, fontweight='bold', pad=10)
        ax.set_xlim(-0.6, 2.6)
    axes[0].set_ylim(0, top)
    axes[0].yaxis.set_major_formatter(matplotlib.ticker.StrMethodFormatter('${x:,.2f}'))
    header(fig, 'Where the money goes, median per run',
           'All tasks pooled. Every token that enters the context is written to the cache once, then re-read on every later call.')
    fig.savefig(OUT / 'cost_components.png')
    plt.close(fig)


if __name__ == '__main__':
    runs = load()
    cost_per_task(runs)
    stats_path = RESULTS / 'stats.json'
    if stats_path.exists():
        relative(json.loads(stats_path.read_text()))
    decomposition = RESULTS / 'decomposition.json'
    if decomposition.exists():
        cost_components(json.loads(decomposition.read_text()))
    print(f'{len(runs)} runs -> {OUT}')
