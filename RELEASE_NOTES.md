# v1.3.0 — Read-only performance analysis skill

- Add explicit `/analyze` for source-level performance recommendations with optional traces, benchmark summaries, or CSV evidence.
- Keep recommendations separate from code changes and campaign execution; `/optimize` remains the implementation and verification workflow.
- Installer and bundle validation now include both skills.

# v1.2.1 — Explicit-only Labcoat activation and bounded research loop

- `prof-tools` remains explicit-only, and its invocation explicitly opts in to Labcoat for that campaign. It does not require a second user confirmation.
- Agent loads the Labcoat protocol and executes annotation/validation scripts at experiment transitions if runtime-specific skill hooks are not active.
- Codex `agents/openai.yaml` marks `prof-tools` explicit-only; Claude Code already uses `disable-model-invocation`.
- Coordinator now describes a bounded, iterative falsification/evaluation/recording cycle, rather than another `autoresearch` daemon. This guidance is not a fully unattended process scheduler.
- No profiling algorithms, benchmark contracts, Git isolation or CLI API changed in this patch release.

# v1.2.0 — External experimental Git and Labcoat isolation

- `campaign start` clones a fully independent bare Git repository; experiment worktrees, refs, and commits no longer share the source repository object database.
- Notes live in a separate persistent Labcoat Git repository, optionally selected with `--labcoat-repo`. Workers receive Git-excluded `notes` symlinks. The campaign clone has no origin remote to prevent accidental pushes.
- The agent first prepares an independent source clone, and creates/commits the workload contract there rather than in the original source repository. Final integration also takes place outside source; only a validated consolidated patch may land in source.
- One new regression test commits both a failed optimization and a Labcoat note and verifies the source HEAD, refs, commit history and files are unchanged.
- The campaign Git repository must be retained while Labcoat notes reference experimental commit IDs. No replacement experiment tracker is introduced.

# v1.1.0 — Agent-owned contracts and frozen evaluation criteria

- Plain-language user goal is sufficient: the agent discovers, authors, validates and commits the canonical `perf/workload.json` and benchmark/oracle adapters; it derives its own opportunity map from evidence. Neither JSON file is a user setup requirement.
- One new focused reference (`references/contract-authoring.md`) gives the discovery and correctness protocol, exact schemas, validation procedure, freeze sequence and uncertainty escalation rules. No extra public command or separate state system.
- `prof-tools evaluate` defaults to the canonical `perf/workload.json` while retaining `--spec` for a deliberately nonstandard committed contract.
- Evaluation records a SHA-256 digest of the executed workload contract. When the baseline contains the canonical file, `finalize` blocks changes to that contract and rejects reports from a different version.
- Labcoat remains the sole experiment history. The package cannot itself infer scientific semantics or construct an oracle; the invoking coding agent must perform that work.

# v1.0.0 — Workflow and skill-interface simplification

- One `prof-tools` skill entrypoint, not 16 competing skills; all specialized backend and hardware material remains under references.
- Five CLI root operations: `diagnose`, `campaign start`, `evaluate`, `finalize`, `inspect`; superseded root commands are deleted rather than aliased.
- `campaign start` composes opportunity screening, diverse branch selection and Git worktree creation without a persisted intermediate plan or Labcoat status mirror.
- `evaluate` combines independently verified outputs, weighted unprofiled measurements, memory guardrails and acceptance evidence into one top-level `evaluation.json`.
- `finalize` accepts that evaluation artifact plus independent design review, rechecks correctness/performance decision and final source revision.
- Specialist trace, counter, distributed, CPU and kernel algorithms remain importable, stateless Python modules.
- No embedded experiment tracker. Labcoat continues to own hypotheses, preregistration, notes, lineage and final integration decisions.
- Public masked-window benchmark and private holdout remain separate packages.

**Hardware:** profiler adapters require real-device regression fixtures before claiming live H100/MI300A acceptance. Verification is bounded by the reference oracles and project-supplied tests.
