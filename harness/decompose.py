#!/usr/bin/env python3
"""Where each run's money went, from its stream-json transcript.

For every main-thread API call: cached tokens re-read are split into the fixed prefix (the context of the
first call: system prompt, tools, CLAUDE.md, task) and the conversation history accumulated since.
Also measures how much tool output the agent pulled in, and how much of it came from ../tools (the design system).

Usage: decompose.py [results dir]   (run with /tmp/krypta-bench/venv/bin/python)
Writes <results>/decomposition.json and prints medians per version.
"""
import json
import sys
from pathlib import Path

import numpy as np

RESULTS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/tmp/krypta-bench/results')
# Claude Opus 5.5 list prices, $ per million tokens.
PRICE = {'input': 4.0, 'cache_read': 0.20, 'write_5m': 5.0, 'write_1h': 8.0, 'output': 20.0}


def decompose(stream, result_usage, reported_usd):
    msgs, order, tool_meta = {}, [], {}
    tools_chars = total_chars = 0
    for line in open(stream, errors='ignore'):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get('type') == 'assistant':
            m = o.get('message') or {}
            mid, u = m.get('id'), m.get('usage') or {}
            if o.get('parent_tool_use_id') is None:
                if mid not in msgs:
                    order.append(mid)
                    msgs[mid] = u
                elif (u.get('output_tokens') or 0) >= (msgs[mid].get('output_tokens') or 0):
                    msgs[mid] = u
            for b in m.get('content') or []:
                if b.get('type') == 'tool_use':
                    inp = b.get('input') or {}
                    target = str(inp.get('file_path') or inp.get('command') or '')
                    tool_meta[b['id']] = ('/tools/' in target or '../tools' in target or 'tools/design' in target)
        elif o.get('type') == 'user':
            content = (o.get('message') or {}).get('content')
            if isinstance(content, list):
                for b in content:
                    if b.get('type') == 'tool_result':
                        c = b.get('content')
                        size = len(c if isinstance(c, str) else json.dumps(c))
                        total_chars += size
                        if tool_meta.get(b.get('tool_use_id')):
                            tools_chars += size
    if not order:
        return None
    usages = [msgs[i] for i in order]
    ctx = lambda u: sum((u.get(k) or 0) for k in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'))
    prefix = ctx(usages[0])
    prefix_reads = history_reads = 0
    for u in usages:
        cr = u.get('cache_read_input_tokens') or 0
        p = min(cr, prefix)
        prefix_reads += p
        history_reads += cr - p
    # Totals come from modelUsage (the result's `usage` can cover only the last segment of a session that
    # waited on a background task); the per-call split only apportions the cache reads.
    reads = result_usage.get('cache_read_input_tokens') or 0
    split = prefix_reads / (prefix_reads + history_reads) if prefix_reads + history_reads else 0
    w1, w5 = result_usage.get('cache_creation_input_tokens') or 0, 0
    usd = lambda tokens, key: tokens * PRICE[key] / 1e6
    parts = {
        'usd_prefix_reads': usd(reads * split, 'cache_read'),
        'usd_history_reads': usd(reads * (1 - split), 'cache_read'),
        'usd_cache_writes': usd(w5, 'write_5m') + usd(w1, 'write_1h'),
        'usd_output': usd(result_usage.get('output_tokens') or 0, 'output'),
        'usd_input': usd(result_usage.get('input_tokens') or 0, 'input'),
    }
    parts['usd_other'] = (reported_usd or 0) - sum(parts.values())
    return {
        'calls': len(usages), 'prefix_tokens': prefix, 'context_last': ctx(usages[-1]),
        'written_tokens': w1 + w5, 'output_tokens': result_usage.get('output_tokens') or 0,
        **parts, 'tool_output_tokens': total_chars // 4, 'tools_dir_tokens': tools_chars // 4,
    }


def main_usage(m):
    """Session totals of the main model, in the result-usage key names."""
    for model, v in (m.get('modelUsage') or {}).items():
        if 'opus' in model:
            return {'input_tokens': v.get('inputTokens'), 'output_tokens': v.get('outputTokens'),
                    'cache_read_input_tokens': v.get('cacheReadInputTokens'),
                    'cache_creation_input_tokens': v.get('cacheCreationInputTokens')}
    return m.get('usage') or {}


def main():
    rows = []
    for meta_path in sorted(RESULTS.glob('*/meta.json')):
        m = json.loads(meta_path.read_text())
        if m.get('status') != 'done' or m.get('rep', 0) < 1:
            continue
        d = decompose(meta_path.parent / 'stream.jsonl', main_usage(m), m.get('total_cost_usd'))
        if d:
            d.update({'id': m['id'], 'arm': m['arm'], 'task': m['task'], 'reported_usd': m.get('total_cost_usd')})
            rows.append(d)
    (RESULTS / 'decomposition.json').write_text(json.dumps(rows, indent=1))
    keys = ['prefix_tokens', 'context_last', 'written_tokens', 'output_tokens', 'usd_prefix_reads', 'usd_history_reads',
            'usd_cache_writes', 'usd_output', 'usd_other', 'tool_output_tokens', 'tools_dir_tokens']
    print(f'{len(rows)} runs; medians per version (all tasks)')
    print(f'{"arm":4}' + ''.join(f'{k[-16:]:>17}' for k in keys))
    for arm in 'ABC':
        sel = [r for r in rows if r['arm'] == arm]
        if sel:
            print(f'{arm:4}' + ''.join(f'{np.median([r[k] for r in sel]):17.2f}' for k in keys))
    print('other (subagents, Haiku side calls, rounding): max', round(max(r['usd_other'] for r in rows), 3),
          'min', round(min(r['usd_other'] for r in rows), 3))


if __name__ == '__main__':
    main()
