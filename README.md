# Prof Tools Toolkit 1.2.1

One opt-in performance-engineering skill with Python/CPU, NVIDIA CUDA and AMD ROCm references. Invoking `prof-tools` explicitly authorizes Labcoat for that campaign; Labcoat is otherwise opt-in. One small CLI around stateless profilers, verification algorithms and experimental evidence. **Labcoat** owns experiment history, preregistration, lineage and KEEP/REVERT decisions.

The toolkit is for agents tasked with making **representative full applications** faster while preserving semantics and leaving a small, coherent final implementation. It is not a standalone GPU profiler, a second experiment database, or a general stochastic optimizer.

## Install

```bash
python -m pip install -e /path/to/prof_tools
python /path/to/prof_tools/tools/install_skills.py --project /path/to/target --client codex
# or: --client claude [--with-agents]
```

The installer copies the `/optimize` skill and its references; five specialist agent templates are optional. The distributed Python package exposes only the `prof-tools` command.

## Start from an ordinary request (no JSON to prepare)

With the `/optimize` skill installed, ask your coding agent, for example:

> Optimize representative training-step throughput in this repository, preserving numerical, gradient and distributed semantics. Treat memory as a secondary metric unless capacity is binding. Use Labcoat for experiments and deliver one clean, independently validated final diff.

**You do not create any JSON, performance scripts, or experiment worktrees.** The agent first clones the source into a separate, independently owned preparation repository with no push remote. It inspects the code and tests, establishes correctness requirements, and authors and commits `perf/workload.json` and minimal benchmark adapters **in that isolated repository**, not in your source repository. The agent then freezes the prepared base commit. It gathers profiling evidence, derives an opportunity map outside the source checkout, and uses the CLI operations below to conduct the campaign. The agent—not the CLI—performs this reasoning and file authoring. Labcoat owns notes and history. Invoking `prof-tools` is the opt-in for Labcoat in this campaign: the agent reads Labcoat's protocol and uses its scripts automatically, without asking the user again. If the agent runtime cannot invoke `/labcoat` to enable its skill-scoped hooks, it must check annotations and validate Labcoat notes explicitly at experiment boundaries and before finalization; simply reading its instructions does not register hooks.

If the agent cannot establish a required scientific tolerance, trusted oracle, production workload distribution, or operational requirement from the repository, it must disclose the uncertainty and ask for that missing decision, rather than silently guessing. A provisional suite can support exploration, but cannot be presented as validated production coverage.

See [`skills/optimize/references/contract-authoring.md`](skills/optimize/references/contract-authoring.md) for the agent's exact authoring/validation procedure and protocol examples.

## Commands

| Agent-facing command | Owns |
|---|---|
| `prof-tools diagnose` | Machine-readable CPU/GPU activity, counter, PyTorch and distributed trace diagnosis |
| `prof-tools campaign start` | Opportunity screening, independent campaign Git repository, Labcoat notes repository and worktree preparation |
| `prof-tools campaign run` | Bounded, foreground, resumable campaign with one Codex worker at a time |
| `prof-tools evaluate` | Independent correctness, weighted unprofiled A/B benchmarking, resource guardrails and assessment |
| `prof-tools finalize` | Original-base-to-final semantic review and exact-commit verification |
| `prof-tools inspect` | Advanced read-only schema, events, SKU and environment information |

No `bench`, `verify`, `suite`, `assess`, `campaign-plan`, `campaign-prepare`, `campaign-status`, `integration-review`, `cpu-pstats` or `counter-report` commands are exposed. Their analysis and measurement mechanisms remain importable (e.g. `prof_tools.benchmark.run_trials`, `prof_tools.verify.run_verification`, `prof_tools.trace_diagnostics.diagnose`, `prof_tools.counters.counter_summary`, `prof_tools.distributed.analyze_ranks`). Those are implementation functions, not parallel workflow APIs.

### Diagnose

```bash
prof-tools diagnose --trace perf/trace.sqlite --marker train_step --out perf/diagnosis.json --markdown perf/diagnosis.md
prof-tools diagnose --cpu-profile perf/profile.pstats --cpu-format pstats --out perf/diagnosis.json
prof-tools inspect --kind trace-schema --file perf/trace.sqlite
prof-tools inspect --kind trace-events --file perf/trace.sqlite --out perf/events.jsonl
prof-tools inspect --kind hardware --sku mi300a --dtype bf16
```

GPU traces can be `nsys` SQLite or native ROCm `rocpd`; unknown schema versions must be inspected rather than guessed. Counter files require explicit capture manifests; rank skew requires calibrated clocks and stable collective IDs. Directly observed intervals are not automatically causal dependencies. Unprofiled measurements remain the sole performance acceptance basis.

### Start a campaign

The agent writes the opportunity spec *itself* as an evidence artifact outside the clean repository (see `examples/opportunities.sample.json`); the user does not provide it. **Never author benchmark contracts or experimental commits in the original source repository.** The agent first inspects the source working-tree status, documents any uncommitted changes (a clone does not include them), and creates an independent preparation clone. Relevant pre-existing changes must be applied to the preparation clone as an explicit, preserved patch, without altering the source. It removes the clone's push remote and commits the frozen workload contract there:

```bash
git clone --no-local --no-hardlinks /path/to/source /path/to/isolated-preparation
git -C /path/to/isolated-preparation remote remove origin
# Agent authors, verifies, and commits perf/workload.json in isolated-preparation.
prof-tools campaign start \
  --repo /path/to/isolated-preparation \
  --base <prepared-base-commit> \
  --opportunities /absolute/path/opportunities.json \
  --worktrees /path/to/new/campaign-directory \
  --labcoat-repo /path/to/persistent/project-labcoat \
  --out /path/outside/project/campaign.json
```

`--labcoat-repo` is optional; the default is an external sibling named `<preparation-name>-labcoat`. Reuse one persistent external Labcoat repository across campaigns when possible. The campaign directory contains its own independent bare Git repository and linked experiment worktrees. Workers have `notes` symlinks into the Labcoat repository; the links are Git-excluded in the campaign and never added to the original source repository.

After `campaign start`, use `prof-tools campaign run --campaign campaign.json --objective "..." --time-budget-minutes 120 --max-evaluations 8`. One evaluation is reserved for final integration; `--reserve-minutes` defaults to 15. The run stays in the foreground, writes resumable state into the campaign directory, and can be continued with `--resume`. `prof-tools evaluate` consumes candidate slots during exploration. Use `--phase final` only after the run reports `ready_for_final_review`; the controller does not perform final integration or design review.

`campaign start` requires a clean **preparation** Git repository. It prepares candidate hypotheses, stable experiment IDs and isolated worktrees; `campaign run` then dispatches one Codex worker at a time. Workers follow Labcoat preregistration, and Labcoat retains the experiment history. Campaign state and evaluation reservations live beside the isolated campaign Git repository. **Retain both the campaign Git directory and external Labcoat notes repository:** Labcoat snapshots reference experimental commit hashes that become unrecoverable if the campaign object store is deleted.

### Evaluate a candidate

The agent prepares and commits one canonical project contract at `perf/workload.json` **in its isolated preparation clone** before the prepared base is frozen. The public case includes a ready-made alternative contract at `examples/sequence-window-case/suite.json`. Its schema specifies independent complete-output verification, weighted representative cases, regression tolerance, and optional binding memory constraints.

```bash
prof-tools evaluate --outdir /tmp/evaluation-001
# Existing projects with another committed contract may explicitly pass --spec <path>.
```

`evaluation.json` is the canonical machine-readable decision artifact and includes the underlying verification report, performance results, assessment and code revision. Logs and per-case measurement files remain supporting artifacts. If correctness fails, benchmark acceptance is blocked; if performance is inconclusive, no speedup is claimed. The contract itself must include any additional gradient, safety, numerical or distributed checks appropriate to the application; automatic output comparison is not a proof of program equivalence. See `skills/optimize/references/verification.md`.

An exploratory microbenchmark may call `prof_tools.benchmark.run_trials` directly; it is not an application-level `evaluate` result and cannot pass `finalize`.

### Finalize from the frozen prepared base

In a fresh integration worktree **within the isolated campaign repository** (for example, `git --git-dir /path/to/campaign/campaign.git worktree add -b prof-tools/integration /path/to/campaign/integration <prepared-base-commit>`), the agent reconstructs a coherent final implementation (not a merge of messy exploratory branches), commits it, and reruns `evaluate` on that exact commit. An independent, read-only reviewer then produces the design-review JSON (`examples/design-review.sample.json`).

```bash
prof-tools finalize \
  --repo /path/to/project \
  --base <original-commit> \
  --evaluation /path/outside/project/final-evaluation/evaluation.json \
  --design-review /path/outside/project/design-review.json \
  --out /path/outside/project/final.json
```

When the baseline includes `perf/workload.json`, it also enforces byte-for-byte preservation of that contract and verifies the final evaluation's SHA-256 digest. The gate checks a clean final Git tree; source provenance; correctness/benchmark evidence from the final commit; ten substantive architectural dimensions with source locations; a justified account of every changed file; public API before/after; and simpler alternatives. It cannot mechanically prove elegance. Labcoat is the final repository-decision authority. After `finalize` passes, the agent can export a single clean diff from the prepared base or original source commit, inspect it, and apply only the selected implementation to the real source repository. **Never merge or push exploratory branches into source.** Keep the isolated campaign Git repository as long as Labcoat notes reference its historical code commits.

## Source layout

```text
skills/optimize/SKILL.md             One explicit agent entrypoint
skills/optimize/references/          CPU/CUDA/ROCm, diagnosis, verification, search, hardware, specialist details
agents-optional/                 Independent profiler, implementer, validator, architecture reviewer, coordinator
src/prof_tools/                     Stateless analysis + small workflow composition
examples/sequence-window-case/   Public real-world synthetic CPU optimization challenge
```

The accompanying **private holdout** is distributed **separately**, never inside this repository or skill bundle. Do not mount it into the optimization-agent workspace. The private evaluator is an independence boundary only if the evaluation is administered separately; a same-user untrusted test runner is not a security sandbox.

## Reproducibility and limitations

- Run `python -m unittest discover -s tests -v`, `python tools/validate_bundle.py`, and `python tools/generate_full_reference.py`.
- Synthetic tests cover trace schema adapters, opportunity screening, weighted correctness/benchmark integration, and campaign worktrees. Actual H100/MI300A profiling still requires captures on those GPUs and matching profiler versions.
- Critical path conclusions require actual dependencies; GPU activity, overlap and queue timing alone cannot prove exposed application latency.
- A project's independent oracle, workload distribution, numerical tolerances and safety requirements are supplied by the project; no generic verifier can infer all of them.

### Isolated Git history: what remains where

```text
project/                      Original source Git: unchanged throughout exploration
project-preparation/          Independent clone: frozen workload contract + adapters
project-labcoat/              Separate persistent Git repo: notes, provenance, lineage
campaign/
  campaign.git/               Independent bare Git: experimental and final commits
  worktrees/<experiment-id>/  Experimental code; notes -> project-labcoat/notes
  integration/                Final consolidated branch created from frozen base
```

No experiment branches, reflogs, or object files are added to the source Git database.
Experimental commits are intentionally retained in `campaign.git` for Labcoat replay.
After final approval, export a reviewed diff with `git diff --binary <original-source-sha> <final-commit>`
from the isolated integration repository and apply it to a **new clean source branch**
(after `git apply --check`), then commit the final change once. The diff may include
the benchmark contract if that was added during preparation; the reviewer must
decide whether this test infrastructure belongs in the deliverable. Do not push or
merge experimental refs. This delivery step is performed by the agent/runtime,
not an additional `prof-tools` CLI command.

## Opt-in and autonomous search boundary

`/optimize` and `labcoat` are explicit-only agent skills. In Claude Code, each uses `disable-model-invocation: true`; in Codex each provides an `agents/openai.yaml` policy with `allow_implicit_invocation: false`. A request to invoke `/optimize` opts into Labcoat **for that campaign only**; other tasks do not. The agent loads Labcoat and uses its scripts automatically. The skill-scoped Labcoat hooks become active only after invoking the actual `/labcoat` skill in Claude Code; reading `SKILL.md` is not equivalent. The coordinator must run annotation checks and note validation at experiment boundaries when native skill invocation is unavailable.

The coordinator uses an **AutoResearch-style iterative search policy** (falsify → evaluate → record → choose next, within a budget). `prof-tools campaign run` adds a foreground, resumable controller with a hard deadline, a shared evaluation cap, and one Codex worker at a time. It does not run unattended after the invoking process exits, select a winning candidate, or integrate/review the final patch. Labcoat retains provenance; `prof-tools` retains evaluation and profiling semantics.
