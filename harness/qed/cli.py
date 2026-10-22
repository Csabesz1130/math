"""Command-line interface: ``qed <command>``.

Exit status: 0 on success; 1 on a usage or input error; 2 when an app's
conclusions fall below ``--require``, or a verification fails; 3 when a solve
run ends unsolved or a verification could not run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import industry, kits
from .apps import APPS
from .apps.base import AppResult
from .catalog import Catalog, plain
from .evidence import Tier, claims_markdown
from .repo import RepoNotFound


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        parser.print_help()
        return 1
    try:
        return args.handler(args)
    except (RepoNotFound, ValueError, KeyError, FileNotFoundError, RuntimeError) as error:
        message = error.args[0] if isinstance(error, KeyError) and error.args else error
        print(f"qed: {message}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qed", description="From mathematical results to verified industrial tools.")
    parser.add_argument("--repo", help="the manuscript collection (default: found from the current directory)")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("catalog", help="list result families")
    p.add_argument("--subject", help="only families filed under this subject (substring match)")
    p.add_argument("--formalized", action="store_true", help="only families with a Lean formalization")
    p.add_argument("--json", action="store_true")
    p.set_defaults(handler=cmd_catalog)

    p = sub.add_parser("show", help="show one family: manuscripts, sources and Comparator challenges")
    p.add_argument("family")
    p.add_argument("--json", action="store_true")
    p.set_defaults(handler=cmd_show)

    p = sub.add_parser("search", help="search the collection")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=8)
    p.set_defaults(handler=cmd_search)

    p = sub.add_parser("map", help="triage every family by industrial readiness")
    p.add_argument("--readiness", choices=sorted(industry.READINESS), help="only this readiness level")
    p.add_argument("--markdown", action="store_true", help="print the full industrial map as Markdown")
    p.add_argument("--json", action="store_true")
    p.set_defaults(handler=cmd_map)

    app = sub.add_parser("app", help="run an application").add_subparsers(dest="app")
    app.add_parser("list", help="list applications").set_defaults(handler=cmd_app_list)

    p = app.add_parser("pulse-code", help=APPS["pulse-code"][1])
    p.add_argument("--length", type=int, required=True)
    p.add_argument("--objective", choices=("psl", "merit"), default="psl")
    p.add_argument("--seconds", type=float, default=10.0, help="heuristic search budget")
    p.add_argument("--exhaustive-seconds", type=float, default=20.0, help="budget for exact lower-bound search")
    p.add_argument("--seed", type=int, default=0)
    _app_options(p)
    p.set_defaults(handler=cmd_pulse_code)

    p = app.add_parser("crossbar", help=APPS["crossbar"][1])
    p.add_argument("--m", type=int, required=True, help="number of sources")
    p.add_argument("--n", type=int, required=True, help="number of sinks")
    p.add_argument("--seed", type=int, default=0)
    _app_options(p)
    p.set_defaults(handler=cmd_crossbar)

    p = app.add_parser("null-model", help=APPS["null-model"][1])
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--edges", help="edge list file: 'u v' per line")
    source.add_argument("--demo", action="store_true", help="a generated network with a planted dense ring")
    p.add_argument("--chain", choices=("edge", "theorem"), default="edge")
    p.add_argument("--samples", type=int, default=200)
    p.add_argument("--chains", type=int, default=4)
    p.add_argument("--swaps-per-edge", type=float, default=20.0, help="burn-in, in proposed swaps per edge")
    p.add_argument("--certify-tv", type=float, help="with --chain theorem: run each sample long enough for this total variation")
    p.add_argument("--max-steps", type=int, default=50_000_000)
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--seed", type=int, default=0)
    _app_options(p)
    p.set_defaults(handler=cmd_null_model)

    p = app.add_parser("maxcut", help=APPS["maxcut"][1])
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--edges", help="weighted edge list file: 'u v [w]' per line")
    source.add_argument("--demo", action="store_true", help="a generated weighted graph")
    p.add_argument("--roundings", type=int, default=400)
    p.add_argument("--no-exact", action="store_true", help="skip exhaustive optimum on small graphs")
    p.add_argument("--seed", type=int, default=0)
    _app_options(p)
    p.set_defaults(handler=cmd_maxcut)

    p = sub.add_parser("solve", help="run the generate-verify-refine loop on a problem file")
    p.add_argument("problem", help="problem TOML file")
    p.add_argument("--provider", default="anthropic", help="solver model: anthropic[:model[@effort]], openai-compat:URL#model, scripted:FILE")
    p.add_argument("--critic", help="referee model for proofs (same spec forms); off by default")
    p.add_argument("--samples", type=int, default=4, help="parallel attempts per round")
    p.add_argument("--rounds", type=int, default=3)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--exec", action="store_true", dest="allow_exec", help="allow running model-written code and Lean")
    p.add_argument("--related", type=int, default=5, help="related results from the collection to include")
    p.add_argument("--max-context-chars", type=int, default=400_000)
    p.add_argument("--runs-dir", help="where run records go (default: harness/runs in the collection, else ./runs)")
    p.set_defaults(handler=cmd_solve)

    kit = sub.add_parser("kit", help="paper-to-code verification kits").add_subparsers(dest="kit")
    kit.add_parser("list", help="list kits").set_defaults(handler=cmd_kit_list)
    p = kit.add_parser("check", help="check the kit's classical baseline against its exact oracle")
    p.add_argument("name")
    p.add_argument("--count", type=int, default=40)
    p.add_argument("--seed", type=int, default=0)
    p.set_defaults(handler=cmd_kit_check)

    p = sub.add_parser("verify", help="run Comparator on a family's Lean challenges")
    p.add_argument("family")
    p.add_argument("--challenge", help="only this challenge")
    p.set_defaults(handler=cmd_verify)
    return parser


def _app_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--out", help="directory for report.md, report.json and any drawings")
    p.add_argument("--json", action="store_true", help="print the full result as JSON")
    p.add_argument("--require", type=Tier.parse, metavar="TIER",
                   help="exit 2 unless every conclusion reaches this tier (verified, formalized, published, empirical)")


def _catalog(args) -> Catalog:
    return Catalog.load(args.repo)


def _catalog_or_none(args) -> Catalog | None:
    try:
        return Catalog.load(args.repo)
    except RepoNotFound:
        return None


# -- catalogue ------------------------------------------------------------------------


def cmd_catalog(args) -> int:
    catalog = _catalog(args)
    families = [
        f for f in catalog
        if (not args.subject or args.subject.lower() in f.subject.lower()) and (not args.formalized or f.challenges)
    ]
    if args.json:
        print(json.dumps([f.to_dict() for f in families], indent=2))
        return 0
    for f in families:
        print(f"{f.id}  {f.formal_tier.label:<10}  {f.subject:<38}  {plain(f.title)}")
    print(f"\n{len(families)} of {len(catalog)} families; {catalog.manuscript_count} manuscripts in the collection")
    return 0


def cmd_show(args) -> int:
    catalog = _catalog(args)
    family = catalog.get(args.family)
    if args.json:
        print(json.dumps(family.to_dict(abstracts=True), indent=2))
        return 0
    print(f"{family.id}. {plain(family.title)}  [{family.subject}; {family.formal_tier.label}]\n")
    print(plain(family.summary) + "\n")
    for m in family.manuscripts:
        sources = catalog.paper_sources(m)
        print(f"- {plain(m.title)}\n  {m.path}  ({len(sources)} LaTeX source file(s))")
    if family.challenges:
        print(f"\nComparator challenges (review status: {catalog.review_status}):")
        for c in family.challenges:
            print(f"- {c.name}: {', '.join(c.theorem_names)}  [lean/{c.config}]")
    return 0


def cmd_search(args) -> int:
    from .search import Index

    catalog = _catalog(args)
    for hit in Index(catalog).search(args.query, args.limit):
        f = hit.family
        print(f"{f.id}  {hit.score:6.1f}  {f.formal_tier.label:<10}  {plain(f.title)}")
    return 0


def cmd_map(args) -> int:
    catalog = _catalog(args)
    rows = industry.triage(catalog)
    if args.markdown:
        print(industry.markdown(rows, catalog))
        return 0
    if args.readiness:
        rows = [r for r in rows if r.readiness == args.readiness]
    elif not args.json:
        rows = [r for r in rows if r.application]
    if args.json:
        print(json.dumps([r.to_dict() for r in rows], indent=2))
        return 0
    for r in rows:
        tool = f"  [{r.application.tool}]" if r.application and r.application.tool else ""
        print(f"{r.readiness}  {r.family.id}  {r.family.formal_tier.label:<10}  {plain(r.family.title)}{tool}")
    return 0


# -- applications ---------------------------------------------------------------------


def cmd_app_list(args) -> int:
    for name, (families, description) in APPS.items():
        print(f"{name:<12} families {families:<9} {description}")
    return 0


def _finish(result: AppResult, args) -> int:
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text(result.to_markdown(), encoding="utf-8")
        (out / "report.json").write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        for name, content in result.files.items():
            (out / name).write_text(content, encoding="utf-8")
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.title)
        for line in result.headline:
            print(f"  {line}")
        print()
        for conclusion in result.conclusions:
            print(f"  [{conclusion.tier.label}] {conclusion.statement}")
        if args.out:
            print(f"\nReport written to {args.out}/")
    if args.require is not None:
        weak = [c for c in result.conclusions if c.tier > args.require]
        if weak:
            print(f"\nqed: {len(weak)} conclusion(s) below the required tier {args.require.label}", file=sys.stderr)
            return 2
    return 0


def cmd_pulse_code(args) -> int:
    from .apps import pulse_codes

    result = pulse_codes.run(
        args.length, objective=args.objective, seconds=args.seconds,
        exhaustive_seconds=args.exhaustive_seconds, seed=args.seed, catalog=_catalog_or_none(args),
    )
    return _finish(result, args)


def cmd_crossbar(args) -> int:
    from .apps import crossbar

    return _finish(crossbar.run(args.m, args.n, seed=args.seed, catalog=_catalog_or_none(args)), args)


def cmd_null_model(args) -> int:
    from .apps import null_model

    graph = null_model.demo_graph() if args.demo else null_model.read_edge_list(args.edges)
    result = null_model.run(
        graph, chain=args.chain, samples=args.samples, chains=args.chains, swaps_per_edge=args.swaps_per_edge,
        certify_tv=args.certify_tv, max_steps=args.max_steps, seed=args.seed, top=args.top,
        catalog=_catalog_or_none(args),
    )
    return _finish(result, args)


def cmd_maxcut(args) -> int:
    from .apps import maxcut

    labels, edges = maxcut.demo_graph() if args.demo else maxcut.read_weighted_edges(args.edges)
    result = maxcut.run(labels, edges, seed=args.seed, roundings=args.roundings, exact=not args.no_exact,
                        catalog=_catalog_or_none(args))
    return _finish(result, args)


# -- solving --------------------------------------------------------------------------


def cmd_solve(args) -> int:
    from .llm import make_provider
    from .solve import Engine, Problem
    from .solve.report import markdown

    problem = Problem.load(args.problem)
    catalog = _catalog_or_none(args)
    if args.runs_dir:
        runs_dir = Path(args.runs_dir)
    elif catalog is not None and (catalog.root / "harness").is_dir():
        runs_dir = catalog.root / "harness" / "runs"  # ignored by harness/.gitignore
    else:
        runs_dir = Path("runs")
    engine = Engine(
        make_provider(args.provider),
        critic=make_provider(args.critic) if args.critic else None,
        catalog=catalog,
        samples=args.samples, rounds=args.rounds, workers=args.workers, allow_exec=args.allow_exec,
        related=args.related, max_context_chars=args.max_context_chars, runs_dir=runs_dir,
    )
    run = engine.solve(problem)
    claims, conclusions = run.claims()
    best = run.best
    print(f"{problem.id}: {'solved' if run.solved else 'not solved'} "
          f"(best tier {best.tier.label if best else 'none'}, target {problem.target.label}; {len(run.attempts)} attempts)")
    print(claims_markdown(claims, conclusions))
    if run.directory:
        print(f"Run record: {run.directory}/ (report.md, attempts.jsonl, training.jsonl)")
    else:
        print(markdown(run))
    return 0 if run.solved else 3


def cmd_kit_list(args) -> int:
    for name in kits.names():
        kit = kits.get(name)
        summary = " ".join(kit.__doc__.strip().split("\n\n")[0].split())
        print(f"{name:<14} family {kit.FAMILY}  entrypoint {kit.ENTRYPOINT}()\n  {summary}")
    return 0


def cmd_kit_check(args) -> int:
    kit = kits.get(args.name)
    cases = kit.instances(args.seed, args.count)
    failures = []
    for number, instance in enumerate(cases, 1):
        ok, why = kit.check(instance, kit.baseline(instance), kit.oracle(instance))
        if not ok:
            failures.append((number, why))
    doc = (kit.baseline.__doc__ or "").strip().splitlines()[0]
    print(f"{kit.NAME}: baseline ({doc}) passes {len(cases) - len(failures)} of {len(cases)} instances")
    for number, why in failures[:5]:
        print(f"  instance {number}: {why}")
    return 0


def cmd_verify(args) -> int:
    from .solve.lean import run_comparator

    catalog = _catalog(args)
    family = catalog.get(args.family)
    challenges = [c for c in family.challenges if not args.challenge or c.name == args.challenge]
    if not challenges:
        print(f"qed: family {family.id} has no matching Comparator challenge", file=sys.stderr)
        return 1
    statuses = []
    for challenge in challenges:
        verdict = run_comparator(catalog.root / "lean", challenge.config)
        statuses.append(verdict.status)
        print(f"{challenge.name}: {verdict.status} — {verdict.message}")
    if any(s in ("fail", "error") for s in statuses):
        return 2
    return 0 if all(s == "pass" for s in statuses) else 3


if __name__ == "__main__":
    sys.exit(main())
