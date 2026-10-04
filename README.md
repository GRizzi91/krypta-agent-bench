# Do AI coding agents need clean architecture? — benchmark harness

The scripts, prompts and hidden tests behind the article *Do AI coding agents need clean architecture?*
They measure what Claude Code spends to implement the same feature on three versions of the same Android app:

| Version | Code | Context given to the agent |
| --- | --- | --- |
| A, as-is | 10 Gradle modules, use cases and repositories behind interfaces, 5 files per screen | the workspace CLAUDE.md (589 lines) |
| B, better context | same code as A | a 37-line project CLAUDE.md with a feature-to-files map, a generated design-system index, a quiet `./check` script |
| C, lean code | 3 Gradle modules, no pass-through layers, no generated DI bindings, 2 files per screen | the same context as B, map updated |

The app itself (Krypta, a password vault) is not part of this repository. The harness works with any project:
put one directory per version under `arms/`, write your tasks and hidden tests, and run it.

## Layout

```
harness/bench.py          one run end to end; the interleaved, resumable schedule; CSV summary
harness/analyze.py        medians, IQR, cost per success, bootstrap ratios, Mann-Whitney, pooled comparison
harness/decompose.py      splits each run's cost: cache writes, re-reads of the prefix and of the history, output
harness/plots.py          the article's charts
harness/design_index.py   generates DESIGN_INDEX.md (catalog) and DESIGN_API.md (signatures) from Kotlin sources
harness/watch.sh          waits for progress while the detached schedule runs
prompts/tasks/T*.md       the three task specifications, identical for every version
prompts/review_prompt.md  the blind reviewer's instructions
prompts/rewrite_prompt.md the instructions that produced version C (the rewriting session never saw the tasks)
hidden-tests/             acceptance tests copied in after each run; C/ holds the variants for version C
results/runs.json         per-run metrics: cost, tokens by model, API and tool calls, files touched, checks
results/summary.csv       one row per run
results/stats.json        aggregated statistics; results/decomposition.json: per-run cost split
charts/                   the article's charts
```

## What one run does

1. Clones `arms/<version>` into a fresh directory (APFS copy-on-write), commits it as the baseline, stops all Gradle and Kotlin daemons.
2. Runs Claude Code headless with an empty environment and fixed flags:

   ```
   claude -p "<task>" --model 'claude-opus-5-5[1m]' --effort xhigh \
     --output-format stream-json --verbose --strict-mcp-config --no-session-persistence \
     --disable-slash-commands --setting-sources project,local --permission-mode dontAsk \
     --tools Task,Bash,Read,Edit,Write,NotebookEdit,Monitor,TaskStop,ToolSearch \
     --allowedTools Task,Bash,Read,Edit,Write,NotebookEdit,Monitor,TaskStop,ToolSearch
   ```

   with `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` and `DISABLE_AUTOUPDATER=1`.
3. Stages the change and records files touched and lines changed.
4. Build gate: `./gradlew assembleDevDebug`.
5. Blind review: a second headless session gets only the task and the diff (every CLAUDE.md removed) and judges each numbered requirement.
6. Hidden tests: copies the task's acceptance test in and runs it with Gradle.

A run succeeds when the build passes, the hidden tests pass and the reviewer finds every requirement met.

## Running it

```
python3 harness/bench.py run A T1 1        # one run
python3 harness/bench.py schedule --reps 5  # every version x task x rep, interleaved, resumable
python3 harness/bench.py summarize          # results/summary.csv
venv/bin/python harness/analyze.py          # statistics (needs numpy, scipy)
venv/bin/python harness/plots.py            # charts (needs matplotlib)
```

`bench.py` uses `/tmp/krypta-bench` as its root; change `B` at the top to move it. Cost is the `total_cost_usd` Claude Code reports (a client-side estimate at list prices). With a subscription the runs consume plan usage instead; the scheduler waits and retries when it hits a usage limit.

## Results (45 runs, all passed every check)

Median cost per run at list price (Claude Opus 5.5, xhigh effort, Claude Code 2.1.289):

| Task | A as-is | B better context | C lean code |
| --- | --- | --- | --- |
| T1 sort order | $1.83 | $1.14 | $1.11 |
| T2 pinned entries (crosses layers) | $1.89 | $1.57 | $1.25 |
| T3 password generator | $2.20 | $1.27 | $1.32 |

- A to B (context only): cheaper on every task, all five runs below all five on A (Mann-Whitney p = 0.008 per task); pooled ratio 0.63 (95% CI 0.59-0.72).
- B to C (structure): 20% cheaper on T2 (p = 0.008), no difference on T1 and T3; pooled ratio 0.96 (0.86-1.05).
- The gap comes from reading: on A the context reached a median 129k tokens against 74-75k on B and C, and tool output entering it was 46k tokens against 25k and 23k. More than half of that extra tool output is design-system source code the agent opened (a median 14k tokens per run on A, 1.7k on B, 0.7k on C).

The source code of the app is not published; `results/` holds numbers only (no transcripts, diffs or file paths).
