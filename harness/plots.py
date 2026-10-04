#!/usr/bin/env python3
"""Charts for the article (PNG sized for Medium's ~700 px column). Run with /tmp/krypta-bench/venv/bin/python.

Usage: plots.py [results dir] [output dir] [en|it]
Needs stats.json (analyze.py) and decomposition.json (decompose.py) in the results dir.
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
LANG = sys.argv[3] if len(sys.argv) > 3 else 'en'
SUFFIX = '' if LANG == 'en' else f'_{LANG}'
TEXT = {
    'en': {
        'tick': {'A': 'A\nas-is', 'B': 'B\ncontext', 'C': 'C\nlean'},
        'task': {'T1': 'T1 Sort order', 'T2': 'T2 Pinned entries', 'T3': 'T3 Password generator'},
        'cost_title': 'Better context cut cost on every task; lean code only on T2',
        'effects_title': 'What each change did to the median cost, with 95% intervals',
        'effects_panels': ['Better context (B vs A)', 'Lean code (C vs B)'],
        'no_change': 'no change',
        'parts_title': 'Most of the bill is context, not output (mean per run)',
        'parts': ['Writing new context to the cache', 'Re-reading the context', 'Model output'],
    },
    'it': {
        'tick': {'A': "A\ncom'\u00e8", 'B': 'B\ncontesto', 'C': 'C\nsnello'},
        'task': {'T1': 'T1 Ordinamento', 'T2': 'T2 Voci fissate', 'T3': 'T3 Generatore di password'},
        'cost_title': 'Il contesto taglia il costo su ogni task, il codice snello solo su T2',
        'effects_title': 'Effetto di ogni modifica sul costo mediano, con intervalli al 95%',
        'effects_panels': ['Contesto migliore (B rispetto ad A)', 'Codice snello (C rispetto a B)'],
        'no_change': 'nessun cambiamento',
        'parts_title': "Il conto \u00e8 soprattutto contesto, non output (media per run)",
        'parts': ['Scrittura del nuovo contesto in cache', 'Rilettura del contesto', 'Output del modello'],
    },
}[LANG]


def money(v):
    text = f'${v:,.2f}'
    return text.replace('.', ',') if LANG == 'it' else text


def number(v, decimals=1):
    text = f'{v:.{decimals}f}'
    return text.replace('.', ',') if LANG == 'it' else text

SURFACE, INK, INK2, MUTED, GRID, AXIS = '#fcfcfb', '#0b0b0b', '#52514e', '#898781', '#e1e0d9', '#c3c2b7'
ARMS = ['A', 'B', 'C']
COLOR = {'A': '#2a78d6', 'B': '#eb6834', 'C': '#1baf7a'}
TASKS = ['T1', 'T2', 'T3']
# Parts of the bill, darkest first: one hue family so they never read as versions.
PARTS = [('writes', '#3b3a37'), ('reads', '#8f8d86'), ('output', '#cfcdc4')]

plt.rcParams.update({
    'font.family': ['Helvetica Neue', 'Helvetica', 'Arial', 'DejaVu Sans'],
    'font.size': 16, 'axes.edgecolor': AXIS, 'axes.labelcolor': INK2, 'xtick.color': INK,
    'ytick.color': MUTED, 'xtick.labelsize': 16, 'ytick.labelsize': 15, 'axes.titlecolor': INK,
    'figure.facecolor': SURFACE, 'axes.facecolor': SURFACE, 'savefig.facecolor': SURFACE,
    'axes.spines.top': False, 'axes.spines.right': False, 'axes.spines.left': False,
    'axes.grid': True, 'axes.grid.axis': 'y', 'grid.color': GRID, 'grid.linewidth': 1.0,
    'xtick.major.size': 0, 'ytick.major.size': 0,
})


def title(fig, text):
    fig.text(0.015, 0.975, text, fontsize=24, fontweight='bold', color=INK, va='top')


def load_runs():
    runs = []
    for path in sorted(RESULTS.glob('*/meta.json')):
        m = json.loads(path.read_text())
        if m.get('status') == 'done' and m.get('rep', 0) >= 1:
            runs.append(m)
    return runs


def cost_per_task(runs):
    fig, axes = plt.subplots(1, 3, figsize=(12, 6.4), dpi=200, sharey=True)
    fig.subplots_adjust(left=0.07, right=0.995, top=0.80, bottom=0.17, wspace=0.10)
    rng = np.random.default_rng(7)
    for ax, task in zip(axes, TASKS):
        for i, arm in enumerate(ARMS):
            costs = np.array([r['total_cost_usd'] for r in runs if r['task'] == task and r['arm'] == arm])
            if not len(costs):
                continue
            x = i * 1.5
            ax.scatter(x + rng.uniform(-0.12, 0.12, len(costs)), costs, s=95, color=COLOR[arm], alpha=0.85,
                       linewidths=0, zorder=3)
            med = float(np.median(costs))
            ax.hlines(med, x - 0.28, x + 0.28, color=INK, lw=2.5, zorder=4)
            ax.text(x + 0.33, med, money(med), ha='left', va='center', fontsize=15, color=INK, zorder=5)
        ax.set_xticks([0, 1.5, 3.0], [TEXT['tick'][a] for a in ARMS])
        ax.set_xlim(-0.55, 3.95)
        ax.set_title(TEXT['task'][task], loc='left', fontsize=18, fontweight='bold', pad=12)
    axes[0].set_ylim(0, 3.0)
    axes[0].yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(0.5))
    axes[0].yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: money(v)))
    title(fig, TEXT['cost_title'])
    fig.savefig(OUT / f'cost_per_task{SUFFIX}.png')
    plt.close(fig)


def effects(stats):
    pairs = [('A->B', 'B', TEXT['effects_panels'][0]), ('B->C', 'C', TEXT['effects_panels'][1])]
    fig, axes = plt.subplots(1, 2, figsize=(12, 6.2), dpi=200, sharey=True)
    fig.subplots_adjust(left=0.09, right=0.995, top=0.80, bottom=0.12, wspace=0.10)
    for ax, (key, arm, label) in zip(axes, pairs):
        ax.axhline(1.0, color=INK2, lw=1.5, zorder=2)
        ax.text(0.4, 1.015, TEXT['no_change'], ha='left', va='bottom', fontsize=14, color=INK2)
        for i, task in enumerate(TASKS):
            eff = (stats['effects'].get(f'{key} {task}') or {}).get('cost')
            if not eff:
                continue
            lo, hi = eff['ci95']
            ax.errorbar(i, eff['ratio'], yerr=[[eff['ratio'] - lo], [hi - eff['ratio']]], fmt='o', ms=9,
                        color=COLOR[arm], ecolor=COLOR[arm], elinewidth=2.5, capsize=7, capthick=2.5, zorder=3)
            change = (eff['ratio'] - 1) * 100
            ax.text(i + 0.12, eff['ratio'], f'{change:+.0f}%', ha='left', va='center', fontsize=16, color=INK)
        ax.set_xticks(range(3), TASKS)
        ax.set_xlim(-0.5, 2.5)
        ax.set_title(label, loc='left', fontsize=18, fontweight='bold', pad=12)
    axes[0].set_ylim(0.4, 1.3)
    axes[0].yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: number(v) + '×'))
    title(fig, TEXT['effects_title'])
    fig.savefig(OUT / f'effects{SUFFIX}.png')
    plt.close(fig)


def cost_components(rows):
    fig, axes = plt.subplots(1, 3, figsize=(12, 6.6), dpi=200, sharey=True)
    fig.subplots_adjust(left=0.07, right=0.995, top=0.72, bottom=0.17, wspace=0.10)
    for ax, task in zip(axes, TASKS):
        for i, arm in enumerate(ARMS):
            sel = [r for r in rows if r['task'] == task and r['arm'] == arm]
            if not sel:
                continue
            values = {
                'writes': np.mean([r['usd_cache_writes'] for r in sel]),
                'reads': np.mean([r['usd_prefix_reads'] + r['usd_history_reads'] for r in sel]),
                'output': np.mean([r['usd_output'] + r['usd_input'] for r in sel]),
            }
            bottom = 0.0
            for key, color in PARTS:
                ax.bar(i, values[key], bottom=bottom, width=0.5, color=color, edgecolor=SURFACE, linewidth=2,
                       zorder=3)
                bottom += values[key]
            ax.text(i, bottom + 0.05, money(bottom), ha='center', va='bottom', fontsize=16, color=INK)
        ax.set_xticks(range(3), [TEXT['tick'][a] for a in ARMS])
        ax.set_xlim(-0.6, 2.6)
        ax.set_title(TEXT['task'][task], loc='left', fontsize=18, fontweight='bold', pad=12)
    axes[0].set_ylim(0, 2.6)
    axes[0].yaxis.set_major_locator(matplotlib.ticker.MultipleLocator(0.5))
    axes[0].yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: money(v)))
    title(fig, TEXT['parts_title'])
    handles = [matplotlib.patches.Patch(color=color, label=label) for (_, color), label in zip(PARTS, TEXT['parts'])]
    fig.legend(handles=handles, loc='upper left', bbox_to_anchor=(0.01, 0.885), ncol=3, frameon=False, fontsize=15,
               handlelength=1.2, columnspacing=1.6)
    fig.savefig(OUT / f'cost_components{SUFFIX}.png')
    plt.close(fig)


if __name__ == '__main__':
    runs = load_runs()
    cost_per_task(runs)
    effects(json.loads((RESULTS / 'stats.json').read_text()))
    cost_components(json.loads((RESULTS / 'decomposition.json').read_text()))
    print(f'{len(runs)} runs -> {OUT}')
