#!/usr/bin/env python3
"""Statistics over finished runs: per version x task, effects between versions, pooled effects.

Usage: analyze.py [results dir]   (run with /tmp/krypta-bench/venv/bin/python)
Writes <results>/stats.json and prints a readable report.
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import mannwhitneyu

RESULTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/tmp/krypta-bench/results')
ARMS, TASKS = ['A', 'B', 'C'], ['T1', 'T2', 'T3']
METRICS = ['cost', 'api_calls', 'cache_read', 'cache_write', 'output', 'wall_s', 'files', 'reads', 'gradle']
RNG = np.random.default_rng(2026)


def main_usage(m):
    """Session totals of the main model (the result's `usage` can miss segments before a background wait)."""
    for model, v in (m.get('modelUsage') or {}).items():
        if 'opus' in model:
            return {'input_tokens': v.get('inputTokens'), 'output_tokens': v.get('outputTokens'),
                    'cache_read_input_tokens': v.get('cacheReadInputTokens'),
                    'cache_creation_input_tokens': v.get('cacheCreationInputTokens')}
    return m.get('usage') or {}


def load():
    runs = []
    for path in sorted(RESULTS.glob('*/meta.json')):
        m = json.loads(path.read_text())
        if m.get('status') != 'done' or m.get('rep', 0) < 1:
            continue
        u = main_usage(m)
        tools = m.get('tool_calls') or {}
        runs.append({
            'id': m['id'], 'arm': m['arm'], 'task': m['task'], 'rep': m['rep'],
            'success': bool(m.get('success')), 'build_ok': bool(m.get('build_ok')),
            'tests_ok': bool(m.get('tests_ok')),
            'review_ok': bool(m.get('review') and m['review'].get('all_met')),
            'cost': m.get('total_cost_usd') or 0.0,
            'api_calls': (m.get('api_calls_main') or 0) + (m.get('api_calls_sub') or 0),
            'cache_read': u.get('cache_read_input_tokens') or 0,
            'cache_write': u.get('cache_creation_input_tokens') or 0,
            'output': u.get('output_tokens') or 0,
            'wall_s': m.get('wall_s') or 0,
            'files': m.get('files_changed') or 0,
            'reads': sum(v for k, v in tools.items() if k.startswith('Read')),
            'gradle': m.get('gradle_calls') or 0,
        })
    return runs


def boot_ratio(x, y, n=10000):
    """95% bootstrap interval of median(y) / median(x)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    xs = RNG.choice(x, (n, len(x))).astype(float)
    ys = RNG.choice(y, (n, len(y))).astype(float)
    ratios = np.median(ys, axis=1) / np.median(xs, axis=1)
    return float(np.percentile(ratios, 2.5)), float(np.percentile(ratios, 97.5))


def describe(values):
    v = np.asarray(values, float)
    return {'n': len(v), 'median': float(np.median(v)), 'p25': float(np.percentile(v, 25)),
            'p75': float(np.percentile(v, 75)), 'mean': float(v.mean())}


def compare(x, y):
    if len(x) < 2 or len(y) < 2:
        return None
    lo, hi = boot_ratio(x, y)
    p = mannwhitneyu(x, y, alternative='two-sided').pvalue
    return {'ratio': float(np.median(y) / np.median(x)), 'ci95': [lo, hi], 'p': float(p)}


def main():
    runs = load()
    out = {'cells': {}, 'effects': {}, 'pooled': {}}
    for task in TASKS:
        for arm in ARMS:
            cell = [r for r in runs if r['arm'] == arm and r['task'] == task]
            if not cell:
                continue
            ok = [r for r in cell if r['success']]
            out['cells'][f'{arm}-{task}'] = {
                'runs': len(cell), 'successes': len(ok),
                'build_ok': sum(r['build_ok'] for r in cell), 'tests_ok': sum(r['tests_ok'] for r in cell),
                'review_ok': sum(r['review_ok'] for r in cell),
                'cost_per_success': (sum(r['cost'] for r in cell) / len(ok)) if ok else None,
                **{m: describe([r[m] for r in cell]) for m in METRICS},
            }
        for a, b in (('A', 'B'), ('B', 'C'), ('A', 'C')):
            xa = [r for r in runs if r['arm'] == a and r['task'] == task]
            xb = [r for r in runs if r['arm'] == b and r['task'] == task]
            out['effects'][f'{a}->{b} {task}'] = {m: compare([r[m] for r in xa], [r[m] for r in xb])
                                                  for m in ('cost', 'api_calls', 'wall_s', 'files')}
    # Pooled: every run divided by the median of version A on the same task.
    for m in ('cost', 'api_calls', 'cache_read', 'output', 'wall_s'):
        norm = {arm: [] for arm in ARMS}
        for task in TASKS:
            base = [r[m] for r in runs if r['arm'] == 'A' and r['task'] == task]
            if not base:
                continue
            ref = float(np.median(base)) or 1.0
            for r in runs:
                if r['task'] == task:
                    norm[r['arm']].append(r[m] / ref)
        out['pooled'][m] = {arm: describe(v) for arm, v in norm.items() if v}
        for a, b in (('A', 'B'), ('B', 'C'), ('A', 'C')):
            if len(norm[a]) > 1 and len(norm[b]) > 1:
                out['pooled'][m][f'{a}->{b}'] = compare(norm[a], norm[b])
    (RESULTS / 'stats.json').write_text(json.dumps(out, indent=1))

    print(f'{len(runs)} runs')
    print(f'{"cell":8} {"ok":>5} {"cost med":>9} {"IQR":>15} {"$/success":>10} {"calls":>6} {"files":>6} {"wall s":>7}')
    for key, c in out['cells'].items():
        cps = f'{c["cost_per_success"]:.2f}' if c['cost_per_success'] else '-'
        print(f'{key:8} {c["successes"]}/{c["runs"]:<3} {c["cost"]["median"]:9.2f} '
              f'{c["cost"]["p25"]:7.2f}-{c["cost"]["p75"]:<7.2f} {cps:>10} {c["api_calls"]["median"]:6.0f} '
              f'{c["files"]["median"]:6.0f} {c["wall_s"]["median"]:7.0f}')
    print('effects (ratio of medians, 95% bootstrap CI, Mann-Whitney p):')
    for key, e in out['effects'].items():
        c = e.get('cost')
        if c:
            print(f'  {key:10} cost x{c["ratio"]:.2f} [{c["ci95"][0]:.2f}, {c["ci95"][1]:.2f}] p={c["p"]:.3f}'
                  f'   calls x{e["api_calls"]["ratio"]:.2f} p={e["api_calls"]["p"]:.3f}')
    print('pooled cost (relative to A median per task):')
    for key, v in out['pooled'].get('cost', {}).items():
        if 'median' in v:
            print(f'  {key}: median {v["median"]:.2f} (IQR {v["p25"]:.2f}-{v["p75"]:.2f}, n={v["n"]})')
        else:
            print(f'  {key}: x{v["ratio"]:.2f} [{v["ci95"][0]:.2f}, {v["ci95"][1]:.2f}] p={v["p"]:.3f}')


if __name__ == '__main__':
    main()
