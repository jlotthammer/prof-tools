"""A small workflow CLI; specialized profilers stay available as Python modules."""
import argparse
import json
from pathlib import Path
import sys

from .auto_diagnosis import auto_diagnose, finding
from .campaign import start_campaign
from .orchestration import reserve_evaluation, run_campaign
from .cpu import cpu_inventory, cprofile_summary, collapsed_stacks_summary
from .environment import inventory
from .hardware import DEVICES, ridge, gemm_ai, wave_efficiency
from .reporting import diagnosis_markdown
from .trace_diagnostics import inspect_schema, export_events
from .workflow import evaluate, finalize


def _path_json(path):
    return json.loads(Path(path).read_text()) if path else None


def _diagnose(args):
    if not any((args.trace, args.counter_file, args.torch_trace, args.ranks_manifest,
                args.dependency_graph, args.cpu_profile)):
        raise ValueError("diagnose requires at least one trace, CPU profile, or other evidence source")
    report = (auto_diagnose(
        trace=args.trace, counter_file=args.counter_file, counter_manifest=args.counter_manifest,
        counter_table=args.counter_table, counter_columns=_path_json(args.counter_column_map),
        torch_trace=args.torch_trace, ranks_manifest=args.ranks_manifest,
        dependency_graph=args.dependency_graph, marker=args.marker, top=args.top)
        if any((args.trace, args.counter_file, args.torch_trace, args.ranks_manifest,
                args.dependency_graph))
        else {"schema_version": 1, "sources": {}, "findings": [], "limitations": []})
    if args.cpu_profile:
        data = (cprofile_summary(args.cpu_profile, args.top)
                if args.cpu_format == "pstats" else collapsed_stacks_summary(args.cpu_profile, args.top))
        report["sources"]["cpu_profile"] = data
        report["findings"].append(finding("CPU_PROFILE_HOTSPOTS", "observe",
            "CPU profile samples or calls ranked; the profile does not establish exposed application cost",
            "Correlate hotspots with representative unprofiled application timing before implementation.",
            {"format": args.cpu_format, "profile": args.cpu_profile}, "low"))
        report["limitations"].append("CPU sampling or deterministic profiling introduces measurement overhead.")
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))
    if args.markdown:
        Path(args.markdown).write_text(diagnosis_markdown(report))
    return report


def _inspect(args):
    if args.kind == "environment":
        return inventory()
    if args.kind == "cpu-environment":
        return cpu_inventory()
    if args.kind == "hardware":
        if not args.sku:
            raise ValueError("inspect --kind hardware requires --sku")
        result = {"sku": args.sku, "facts": DEVICES[args.sku], "dtype": args.dtype,
                  "peak_ridge_flop_per_byte": ridge(args.sku, args.dtype),
                  "provenance": "vendor peak / derived, not measured"}
        if args.gemm:
            result["gemm_ideal_ai_flop_per_byte"] = gemm_ai(*args.gemm)
        if args.tiles:
            result["wave_quantization"] = wave_efficiency(args.tiles, DEVICES[args.sku]["units"])
        return result
    if args.kind == "trace-schema":
        if not args.file:
            raise ValueError("inspect --kind trace-schema requires --file")
        return inspect_schema(args.file)
    if args.kind == "trace-events":
        if not args.file or not args.out:
            raise ValueError("inspect --kind trace-events requires --file and --out")
        return export_events(args.file, args.out, args.event_kind, args.start_ns, args.end_ns)
    raise ValueError(f"unknown inspection mode {args.kind}")


def _parser():
    p = argparse.ArgumentParser(prog="prof-tools", description="Measure, explore, verify and finalize application performance improvements")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("diagnose", help="analyze CPU/GPU evidence without opening trace viewers")
    d.add_argument("--trace", help="Nsight Systems / ROCm SQLite trace")
    d.add_argument("--cpu-profile", help="cProfile .pstats or folded stacks")
    d.add_argument("--cpu-format", choices=["pstats", "folded"], default="pstats")
    d.add_argument("--counter-file")
    d.add_argument("--counter-manifest")
    d.add_argument("--counter-table")
    d.add_argument("--counter-column-map")
    d.add_argument("--torch-trace")
    d.add_argument("--ranks-manifest")
    d.add_argument("--dependency-graph")
    d.add_argument("--marker")
    d.add_argument("--top", type=int, default=20)
    d.add_argument("--out")
    d.add_argument("--markdown")

    c = sub.add_parser("campaign", help="create experiment branches, never experiment history")
    csub = c.add_subparsers(dest="campaign_command", required=True)
    start = csub.add_parser("start", help="screen opportunities and prepare independent worktrees")
    start.add_argument("--repo", required=True)
    start.add_argument("--base", required=True)
    start.add_argument("--opportunities", required=True, help="seven-family opportunity specification")
    start.add_argument("--worktrees", required=True, help="new isolated campaign directory (outside source)")
    start.add_argument("--labcoat-repo", help="existing or new independent Labcoat repository (default: sibling <project>-labcoat)")
    start.add_argument("--out", help="single branch-brief artifact outside the repository")

    run = csub.add_parser("run", help="run or resume a bounded, single-worker optimization campaign")
    run.add_argument("--campaign", required=True, help="campaign.json produced by campaign start")
    run.add_argument("--objective", help="optimization objective (required for a new run)")
    run.add_argument("--time-budget-minutes", type=float, help="total foreground campaign budget")
    run.add_argument("--max-evaluations", type=int, help="candidate evaluations plus one reserved final evaluation")
    run.add_argument("--reserve-minutes", type=float, default=15, help="time kept for integration and final validation")
    run.add_argument("--resume", action="store_true", help="continue the existing campaign state")
    run.add_argument("--dry-run", action="store_true", help="show campaign limits without starting Codex")

    e = sub.add_parser("evaluate", help="verify correctness, run weighted unprofiled benchmarks and assess")
    e.add_argument("--spec", default="perf/workload.json", help="project-owned workload contract (default: perf/workload.json)")
    e.add_argument("--outdir", required=True)
    e.add_argument("--phase", choices=["candidate", "final"], default="candidate",
                   help="campaign budget pool to consume (default: candidate)")

    f = sub.add_parser("finalize", help="validate exact final commit and independent semantic architecture review")
    f.add_argument("--repo", required=True)
    f.add_argument("--base", required=True)
    f.add_argument("--evaluation", required=True)
    f.add_argument("--design-review", required=True)
    f.add_argument("--out")

    i = sub.add_parser("inspect", help="advanced read-only inspection of raw evidence and hardware")
    i.add_argument("--kind", choices=["environment", "cpu-environment", "hardware", "trace-schema", "trace-events"], required=True)
    i.add_argument("--file")
    i.add_argument("--out")
    i.add_argument("--sku", choices=sorted(DEVICES))
    i.add_argument("--dtype", default="bf16")
    i.add_argument("--gemm", nargs=3, type=int, metavar=("M", "N", "K"))
    i.add_argument("--tiles", type=int)
    i.add_argument("--event-kind", choices=["all", "kernel", "copy", "api", "memset"], default="all")
    i.add_argument("--start-ns", type=int)
    i.add_argument("--end-ns", type=int)
    return p


def main(argv=None):
    p = _parser()
    args = p.parse_args(argv)
    try:
        if args.command == "diagnose":
            result = _diagnose(args)
        elif args.command == "campaign":
            if args.campaign_command == "run":
                result = run_campaign(args.campaign, objective=args.objective,
                                      time_budget_minutes=args.time_budget_minutes,
                                      max_evaluations=args.max_evaluations,
                                      reserve_minutes=args.reserve_minutes,
                                      resume=args.resume, dry_run=args.dry_run)
            else:
                if args.out:
                    output = Path(args.out).resolve()
                    repo = Path(args.repo).resolve()
                    worktrees = Path(args.worktrees).resolve()
                    if output == repo or repo in output.parents or output == worktrees or worktrees in output.parents:
                        raise ValueError("campaign report must be outside both the source repository and worktree directory")
                    if output.exists():
                        raise FileExistsError(f"campaign output already exists: {output}")
                    output.parent.mkdir(parents=True, exist_ok=True)
                result = start_campaign(args.opportunities, args.repo, args.base, args.worktrees, args.labcoat_repo)
                if args.out:
                    Path(args.out).write_text(json.dumps(result, indent=2))
        elif args.command == "evaluate":
            if not Path(args.spec).is_file():
                raise ValueError(f"workload contract not found: {args.spec}; the invoking agent must author and commit the project benchmark/verification contract first")
            reserve_evaluation(args.phase)
            result = evaluate(args.spec, args.outdir)
        elif args.command == "finalize":
            result = finalize(args.repo, args.base, args.evaluation, args.design_review)
            if args.out:
                Path(args.out).write_text(json.dumps(result, indent=2))
        else:
            result = _inspect(args)
            if args.out and args.kind != "trace-events":
                Path(args.out).write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
        if args.command in {"evaluate", "finalize"} and result["status"] in {"BLOCKED", "FAIL"}:
            return 1
        return 0
    except (ValueError, FileExistsError, OSError, RuntimeError, KeyError, TypeError) as exc:
        print(f"prof-tools: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
