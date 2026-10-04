#!/usr/bin/env python3
"""Krypta agent-efficiency benchmark.

Each run copies one version ("arm") of the codebase into a fresh directory,
gives Claude Code one task in headless mode, then grades the result:
build gate, blind review by a separate session, hidden unit tests.

  bench.py run ARM TASK REP [--keep]   one run, end to end
  bench.py schedule [--reps N]          every run, interleaved, resumable
  bench.py summarize                    results/summary.csv
"""
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

B = Path('/tmp/krypta-bench')
ARMS, RUNS, RESULTS = B / 'arms', B / 'runs', B / 'results'
TASKS, HIDDEN = B / 'tasks', B / 'hidden'
CLAUDE = shutil.which('claude') or str(Path.home() / '.local/bin/claude')

MODEL = 'claude-opus-5-5[1m]'
AGENT_EFFORT = 'xhigh'
REVIEW_EFFORT = 'high'
AGENT_TOOLS = 'Task,Bash,Read,Edit,Write,NotebookEdit,Monitor,TaskStop,ToolSearch'
REVIEW_TOOLS = 'Read,Bash(git diff:*),Bash(git status:*),Bash(git show:*),Bash(git log:*),Bash(ls:*),Bash(cat:*),Bash(grep:*),Bash(find:*)'
AGENT_TIMEOUT_S = 90 * 60
GRADLE_TIMEOUT_S = 25 * 60
REVIEW_TIMEOUT_S = 25 * 60
LIMIT_SLEEP_S = 20 * 60
SEED = 2026


def log(msg):
    line = time.strftime('%Y-%m-%d %H:%M:%S ') + msg
    print(line, flush=True)
    with open(RESULTS / 'progress.log', 'a') as f:
        f.write(line + '\n')


def clean_env():
    env = {k: os.environ[k] for k in ('HOME', 'USER', 'PATH', 'TMPDIR', 'JAVA_HOME') if k in os.environ}
    env.update({
        'LOGNAME': os.environ.get('USER', ''),
        'SHELL': '/bin/zsh',
        'LANG': 'en_US.UTF-8',
        'TERM': 'xterm-256color',
        'CLAUDE_CODE_DISABLE_AUTO_MEMORY': '1',
        'DISABLE_AUTOUPDATER': '1',
    })
    return env


def sh(cmd, cwd, timeout=None, out=None):
    """Runs a shell command; returns (exit code, combined output)."""
    try:
        p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True,
                           timeout=timeout, env=clean_env(), stdin=subprocess.DEVNULL)
        text, code = p.stdout + p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        text, code = f'TIMEOUT after {timeout}s\n{e.stdout or ""}', 124
    if out:
        Path(out).write_text(text)
    return code, text


def claude(prompt, cwd, effort, tools, stream_path, err_path, timeout, output_format):
    args = [CLAUDE, '-p', prompt, '--model', MODEL, '--effort', effort,
            '--output-format', output_format, '--strict-mcp-config', '--no-session-persistence',
            '--disable-slash-commands', '--setting-sources', 'project,local',
            '--permission-mode', 'dontAsk', '--allowedTools', tools]
    if output_format == 'stream-json':
        args += ['--verbose', '--tools', tools]
    with open(stream_path, 'w') as out, open(err_path, 'w') as err:
        p = subprocess.Popen(args, cwd=cwd, env=clean_env(), stdout=out, stderr=err,
                             stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            return p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, 9)
            p.wait()
            return 'timeout'


def parse_stream(path):
    """Metrics from a stream-json transcript (assistant messages deduplicated by id)."""
    msgs, order, tool_names, tool_inputs = {}, [], {}, {}
    result, tool_calls, result_chars = None, {}, {}
    gradle_calls = 0
    for line in open(path, errors='ignore'):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        t = o.get('type')
        if t == 'result':
            result = o
        elif t == 'assistant':
            m = o.get('message') or {}
            mid, u = m.get('id'), m.get('usage') or {}
            sub = o.get('parent_tool_use_id') is not None
            if mid not in msgs:
                order.append(mid)
                msgs[mid] = {'u': u, 'sub': sub}
            elif (u.get('output_tokens') or 0) >= (msgs[mid]['u'].get('output_tokens') or 0):
                msgs[mid]['u'] = u
            for b in m.get('content') or []:
                if b.get('type') == 'tool_use':
                    name = b.get('name')
                    tool_names[b['id']] = name
                    tool_inputs[b['id']] = b.get('input') or {}
                    key = name + ('@sub' if sub else '')
                    tool_calls[key] = tool_calls.get(key, 0) + 1
                    if name == 'Bash' and 'gradlew' in str(b.get('input', {}).get('command', '')):
                        gradle_calls += 1
        elif t == 'user':
            content = (o.get('message') or {}).get('content')
            if isinstance(content, list):
                for b in content:
                    if b.get('type') == 'tool_result':
                        c = b.get('content')
                        size = len(c if isinstance(c, str) else json.dumps(c))
                        name = tool_names.get(b.get('tool_use_id'), '?')
                        result_chars[name] = result_chars.get(name, 0) + size
    main = [msgs[i]['u'] for i in order if not msgs[i]['sub']]
    ctx = lambda u: sum((u.get(k) or 0) for k in ('input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'))
    return {
        'result': result,
        'api_calls_main': len(main),
        'api_calls_sub': len(order) - len(main),
        'context_first': ctx(main[0]) if main else None,
        'context_last': ctx(main[-1]) if main else None,
        'tool_calls': tool_calls,
        'tool_result_chars': result_chars,
        'gradle_calls': gradle_calls,
    }


def limit_hit(stream_path, err_path):
    text = Path(err_path).read_text(errors='ignore')[-4000:]
    try:
        for line in open(stream_path, errors='ignore'):
            if '"type":"result"' in line or 'usage limit' in line.lower() or 'rate_limit' in line:
                text += line[-4000:]
    except FileNotFoundError:
        pass
    return bool(re.search(r'usage limit|limit reached|rate.?limit|overloaded|resets? (at|in)', text, re.I))


def git(cmd, cwd):
    return sh(f'git -c user.email=bench@local -c user.name=bench {cmd}', cwd)


def run(arm, task, rep, keep=False):
    rid = f'{arm}-{task}-r{rep}'
    run_dir, out = RUNS / rid, RESULTS / rid
    shutil.rmtree(run_dir, ignore_errors=True)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    subprocess.run(['cp', '-cR', str(ARMS / arm), str(run_dir)], check=True)
    git('init -q', run_dir)
    git('add -A', run_dir)
    git('commit -qm base', run_dir)
    git('tag bench-base', run_dir)
    krypta = run_dir / 'Krypta'
    # Every run starts with no Gradle or Kotlin daemon alive, whatever the previous run left behind.
    sh('./gradlew --stop -q', krypta, 120)
    sh('pkill -f KotlinCompileDaemon', krypta, 30)
    prompt = (TASKS / f'{task}.md').read_text()
    meta = {'id': rid, 'arm': arm, 'task': task, 'rep': rep, 'model': MODEL, 'effort': AGENT_EFFORT,
            'started': time.strftime('%Y-%m-%dT%H:%M:%S')}

    log(f'{rid}: agent start')
    t0 = time.time()
    code = claude(prompt, krypta, AGENT_EFFORT, AGENT_TOOLS, out / 'stream.jsonl', out / 'stderr.txt',
                  AGENT_TIMEOUT_S, 'stream-json')
    meta['wall_s'] = round(time.time() - t0, 1)
    meta['exit'] = code
    metrics = parse_stream(out / 'stream.jsonl')
    res = metrics.pop('result')
    if res is None or res.get('is_error'):
        if limit_hit(out / 'stream.jsonl', out / 'stderr.txt'):
            meta['status'] = 'limited'
            (out / 'meta.json').write_text(json.dumps(meta, indent=1))
            shutil.rmtree(run_dir, ignore_errors=True)
            log(f'{rid}: usage or rate limit, will retry')
            return meta
    meta.update(metrics)
    if res:
        for k in ('subtype', 'is_error', 'num_turns', 'duration_ms', 'duration_api_ms', 'total_cost_usd',
                  'usage', 'modelUsage'):
            meta[k] = res.get(k)
    log(f'{rid}: agent done in {meta["wall_s"]}s, cost {meta.get("total_cost_usd")}, turns {meta.get("num_turns")}')

    # The change, as the reviewer and the stats see it.
    git('add -A', run_dir)
    _, numstat = git('diff --cached bench-base --numstat', run_dir)
    files = [l.split('\t') for l in numstat.strip().splitlines() if '\t' in l]
    meta['files_changed'] = len(files)
    meta['lines_added'] = sum(int(a) for a, _, _ in files if a.isdigit())
    meta['lines_deleted'] = sum(int(d) for _, d, _ in files if d.isdigit())
    meta['changed_paths'] = [p for _, _, p in files]
    _, patch = git('diff --cached bench-base', run_dir)
    (out / 'diff.patch').write_text(patch)

    log(f'{rid}: build gate')
    code, _ = sh('./gradlew assembleDevDebug --console=plain', krypta, GRADLE_TIMEOUT_S, out / 'build.log')
    meta['build_ok'] = code == 0

    log(f'{rid}: blind review')
    # The reviewer must judge spec + diff only, not the version's own instructions.
    for context_file in (run_dir / 'CLAUDE.md', krypta / 'CLAUDE.md'):
        context_file.unlink(missing_ok=True)
    review_prompt = (B / 'scripts' / 'review_prompt.md').read_text().replace('{{TASK}}', prompt)
    claude(review_prompt, krypta, REVIEW_EFFORT, REVIEW_TOOLS, out / 'review_raw.json', out / 'review_err.txt',
           REVIEW_TIMEOUT_S, 'json')
    meta['review'] = parse_review(out / 'review_raw.json')

    log(f'{rid}: hidden tests')
    cfg = json.loads((HIDDEN / 'config.json').read_text())[arm][task]
    dest = krypta / cfg['dest']
    dest.parent.mkdir(parents=True, exist_ok=True)
    name = Path(cfg['dest']).name
    source = HIDDEN / arm / task / name
    shutil.copy(source if source.exists() else HIDDEN / task / name, dest)
    code, _ = sh(f'./gradlew {cfg["gradle"]} --tests {cfg["test"]} --console=plain', krypta,
                 GRADLE_TIMEOUT_S, out / 'tests.log')
    meta['tests_ok'] = code == 0
    meta['tests'] = parse_junit(krypta, cfg['test'])

    review_ok = bool(meta['review'] and meta['review'].get('all_met'))
    meta['success'] = bool(meta['build_ok'] and meta['tests_ok'] and review_ok)
    meta['status'] = 'done'
    meta['finished'] = time.strftime('%Y-%m-%dT%H:%M:%S')
    (out / 'meta.json').write_text(json.dumps(meta, indent=1))
    log(f'{rid}: build={meta["build_ok"]} tests={meta["tests_ok"]} review={review_ok} -> success={meta["success"]}')
    if not keep:
        shutil.rmtree(run_dir, ignore_errors=True)
    return meta


def parse_review(path):
    try:
        raw = json.loads(Path(path).read_text())
    except ValueError:
        return None
    text = raw.get('result') or ''
    m = re.search(r'\{.*\}', text, re.S)
    if not m:
        return {'unparsed': text[:2000], 'cost': raw.get('total_cost_usd')}
    try:
        review = json.loads(m.group(0))
    except ValueError:
        return {'unparsed': text[:2000], 'cost': raw.get('total_cost_usd')}
    review['cost'] = raw.get('total_cost_usd')
    return review


def parse_junit(krypta, test_class):
    tests = failures = 0
    for xml in krypta.rglob(f'TEST-{test_class}.xml'):
        s = xml.read_text(errors='ignore')
        m = re.search(r'tests="(\d+)".*?failures="(\d+)".*?errors="(\d+)"', s, re.S)
        if m:
            tests += int(m.group(1))
            failures += int(m.group(2)) + int(m.group(3))
    return {'tests': tests, 'failed': failures}


def schedule_order(reps):
    rng = random.Random(SEED)
    order = []
    for rep in range(1, reps + 1):
        tasks = ['T1', 'T2', 'T3']
        rng.shuffle(tasks)
        for task in tasks:
            arms = ['A', 'B', 'C']
            rng.shuffle(arms)
            order += [(arm, task, rep) for arm in arms]
    return order


def schedule(reps):
    (B / 'schedule.pid').write_text(str(os.getpid()))
    for arm, task, rep in schedule_order(reps):
        meta_path = RESULTS / f'{arm}-{task}-r{rep}' / 'meta.json'
        while True:
            if meta_path.exists() and json.loads(meta_path.read_text()).get('status') == 'done':
                break
            if (B / 'STOP').exists():
                log('STOP file found, exiting')
                return
            meta = run(arm, task, rep)
            if meta.get('status') == 'limited':
                time.sleep(LIMIT_SLEEP_S)
                continue
            break
    log('schedule complete')
    (B / 'schedule.done').write_text(time.strftime('%Y-%m-%dT%H:%M:%S'))


def summarize():
    rows = []
    for meta_path in sorted(RESULTS.glob('*/meta.json')):
        m = json.loads(meta_path.read_text())
        if m.get('status') != 'done':
            continue
        u = next(({'input_tokens': v.get('inputTokens'), 'output_tokens': v.get('outputTokens'),
                   'cache_read_input_tokens': v.get('cacheReadInputTokens'),
                   'cache_creation_input_tokens': v.get('cacheCreationInputTokens')}
                  for model, v in (m.get('modelUsage') or {}).items() if 'opus' in model), m.get('usage') or {})
        rows.append({
            'id': m['id'], 'arm': m['arm'], 'task': m['task'], 'rep': m['rep'],
            'success': m['success'], 'build_ok': m['build_ok'], 'tests_ok': m['tests_ok'],
            'review_ok': bool(m.get('review') and m['review'].get('all_met')),
            'cost_usd': m.get('total_cost_usd'), 'turns': m.get('num_turns'),
            'api_calls_main': m.get('api_calls_main'), 'api_calls_sub': m.get('api_calls_sub'),
            'duration_s': round((m.get('duration_ms') or 0) / 1000), 'wall_s': m.get('wall_s'),
            'input': u.get('input_tokens'), 'cache_write': u.get('cache_creation_input_tokens'),
            'cache_read': u.get('cache_read_input_tokens'), 'output': u.get('output_tokens'),
            'context_first': m.get('context_first'), 'context_last': m.get('context_last'),
            'files_changed': m.get('files_changed'), 'lines_added': m.get('lines_added'),
            'lines_deleted': m.get('lines_deleted'), 'gradle_calls': m.get('gradle_calls'),
            'reads': sum(v for k, v in (m.get('tool_calls') or {}).items() if k.startswith('Read')),
            'bash': sum(v for k, v in (m.get('tool_calls') or {}).items() if k.startswith('Bash')),
            'subagents': sum(v for k, v in (m.get('tool_calls') or {}).items() if k == 'Task'),
        })
    if not rows:
        print('no finished runs')
        return
    import csv
    with open(RESULTS / 'summary.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f'{len(rows)} runs -> {RESULTS / "summary.csv"}')


if __name__ == '__main__':
    RESULTS.mkdir(parents=True, exist_ok=True)
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'run':
        print(json.dumps(run(sys.argv[2], sys.argv[3], int(sys.argv[4]), keep='--keep' in sys.argv), indent=1))
    elif cmd == 'schedule':
        reps = int(sys.argv[sys.argv.index('--reps') + 1]) if '--reps' in sys.argv else 5
        schedule(reps)
    elif cmd == 'summarize':
        summarize()
    else:
        print(__doc__)
