"""Run the public assurance contract from the reusable GitHub Action."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from agent_reliability_lab.pack_provenance import pack_manifest, pack_set_sha256
from agent_reliability_lab.consumer_contract import (
    ConsumerContractReport,
    evaluate_consumer_contract,
    load_consumer_policy_manifest,
)
from agent_reliability_lab.run_manifest import (
    evaluate_reauthorization,
    load_current_revisions,
    load_manifest,
)
from agent_reliability_lab.packs import (
    load_builtin_packs,
    load_pack_directory,
)
from agent_reliability_lab.runner import (
    failed_checks,
    run_adapter_comparison,
    run_pack_comparison,
)
from agent_reliability_lab.external import (
    DEFAULT_ADAPTER_TIMEOUT_SECONDS,
    DEFAULT_MAX_MEMORY_BYTES,
    DEFAULT_MAX_RESPONSE_BYTES,
    DEFAULT_MAX_STDERR_BYTES,
    SubprocessAdapter,
)


ACTION_REPORT_VERSION = 1


def _bool(value: str, field: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{field} must be true or false.")
    return normalized == "true"


def _command(value: str) -> tuple[str, ...]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("adapter-command-json must be valid JSON.") from error
    if (
        not isinstance(parsed, list)
        or not parsed
        or not all(isinstance(item, str) and item for item in parsed)
    ):
        raise ValueError(
            "adapter-command-json must be a non-empty JSON array of strings."
        )
    if len(parsed) > 64 or any(len(item) > 4096 for item in parsed):
        raise ValueError("adapter-command-json exceeds the argument-vector limits.")
    return tuple(parsed)


def _load_packs(directory: Path | None):
    if directory is None:
        return load_builtin_packs()
    results = load_pack_directory(directory)
    refusals = [result.refusal for result in results if result.refusal is not None]
    packs = tuple(result.pack for result in results if result.pack is not None)
    if refusals or not packs:
        raise ValueError("scenario-pack-directory did not produce valid scenario packs.")
    return packs


def _metadata_report(
    *,
    report: Any,
    packs: tuple[Any, ...],
    custom_packs: bool,
    consumer_contract: ConsumerContractReport | None = None,
    run_manifest: dict[str, object] | None = None,
) -> dict[str, object]:
    agent_report = (
        report.reports[0] if hasattr(report, "reports") else report
    )
    assurance_failed = (
        failed_checks(report)
        if hasattr(report, "reports")
        else not agent_report.passed
    )
    consumer_failed = (
        consumer_contract is not None and not consumer_contract.passed
    )
    manifest_failed = (
        run_manifest is not None
        and run_manifest.get("supports_decision") is not True
    )
    failed = bool(assurance_failed or consumer_failed or manifest_failed)
    data: dict[str, object] = {
        "reusable_action_version": ACTION_REPORT_VERSION,
        "decision": "blocked" if failed else "pass",
        "passed": not failed,
        "agent_id": agent_report.agent_id,
        "scenario_count": len(packs),
        "custom_packs": custom_packs,
        "scenario_pack_sha256": pack_set_sha256(packs),
        "scenario_packs": [
            pack_manifest(pack).to_dict()
            for pack in sorted(packs, key=lambda item: item.scenario_id)
        ],
        "assurance": (
            report.to_dict()
            if hasattr(report, "reports")
            else {"report": agent_report.to_dict()}
        ),
        "diagnostics": {
            "warnings": [
                "The action runs the caller's adapter as a bounded subprocess "
                "with shell execution disabled.",
                "The report contains identifiers, findings, counts, and hashes "
                "only; adapter payloads and credentials are not exported.",
            ],
            "what_it_does_not_show": (
                "It does not show prompts, raw tool payloads, provider output, "
                "credentials, causality, or a production sandbox."
            ),
        },
    }
    if consumer_contract is not None:
        data["consumer_contract"] = consumer_contract.to_dict()
    if run_manifest is not None:
        data["run_manifest"] = run_manifest
    return data


def _refusal(error: Exception) -> dict[str, object]:
    return {
        "reusable_action_version": ACTION_REPORT_VERSION,
        "decision": "blocked",
        "passed": False,
        "refusal": {
            "error": "reusable_assurance_refused",
            "message": "The reusable assurance action could not establish a result.",
            "guidance": "Repair the action inputs or scenario packs before retrying.",
            "source": type(error).__name__,
        },
        "diagnostics": {
            "warnings": [
                "A refusal is a blocked result, not a passing empty result."
            ],
            "what_it_does_not_show": (
                "It does not show adapter arguments, paths, prompts, credentials, "
                "or provider output."
            ),
        },
    }


def _write_output(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with Path(github_output).open("a", encoding="utf-8") as stream:
            stream.write(f"decision={data.get('decision', 'blocked')}\n")
            stream.write(f"passed={str(data.get('passed', False)).lower()}\n")


def _write_summary(data: dict[str, object]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    assurance = data.get("assurance")
    agent = assurance.get("report") if isinstance(assurance, dict) else None
    if isinstance(agent, dict):
        status = "PASS" if data.get("passed") is True else "BLOCKED"
        lines = [
            "# Reusable Agent Assurance",
            "",
            f"- **Decision:** {status}",
            f"- **Agent:** `{data.get('agent_id', 'unknown')}`",
            f"- **Scenarios:** {data.get('scenario_count', 0)}",
            f"- **Scenario-pack SHA-256:** `{data.get('scenario_pack_sha256', 'unknown')}`",
            "",
            "The report contains metadata only; prompts, payloads, provider output, "
            "and credentials are not exported.",
            "",
        ]
        contract = data.get("consumer_contract")
        if isinstance(contract, dict):
            contract_status = "PASS" if contract.get("passed") is True else "BLOCKED"
            reasons = contract.get("failure_reasons", [])
            lines.extend(
                [
                    f"- **Consumer policy contract:** {contract_status}",
                    f"- **Consumer contract failure reasons:** `{reasons}`",
                    "",
                ]
            )
        manifest = data.get("run_manifest")
        if isinstance(manifest, dict):
            lines.extend(
                [
                    f"- **Run-manifest decision:** `{manifest.get('status', 'blocked')}`",
                    f"- **Run-manifest dependencies changed:** "
                    f"`{manifest.get('changed_dependencies', [])}`",
                    "",
                ]
            )
    else:
        lines = [
            "# Reusable Agent Assurance",
            "",
            "- **Decision:** BLOCKED",
            "- **Reason:** the action refused to establish a result.",
            "",
        ]
    with Path(summary_path).open("a", encoding="utf-8") as stream:
        stream.write("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run metadata-only assurance from the reusable GitHub Action."
    )
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--adapter-command-json", required=True)
    parser.add_argument("--adapter-working-directory", type=Path, required=True)
    parser.add_argument("--scenario-pack-directory", default="")
    parser.add_argument("--consumer-policy-manifest", default="")
    parser.add_argument(
        "--run-manifest",
        default="",
        help="Optional metadata-only run manifest, resolved from the adapter workdir.",
    )
    parser.add_argument(
        "--current-revisions",
        default="",
        help="Optional current revision map paired with --run-manifest.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mutations", default="true")
    parser.add_argument("--fail-on-findings", default="true")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_ADAPTER_TIMEOUT_SECONDS,
    )
    parser.add_argument(
        "--max-response-bytes",
        type=int,
        default=DEFAULT_MAX_RESPONSE_BYTES,
    )
    parser.add_argument(
        "--max-stderr-bytes",
        type=int,
        default=DEFAULT_MAX_STDERR_BYTES,
    )
    parser.add_argument(
        "--max-memory-bytes",
        type=int,
        default=DEFAULT_MAX_MEMORY_BYTES,
    )
    args = parser.parse_args(argv)

    fail_on_findings = True
    refused = False
    try:
        command = _command(args.adapter_command_json)
        mutations = _bool(args.mutations, "mutations")
        fail_on_findings = _bool(args.fail_on_findings, "fail-on-findings")
        if not args.adapter_working_directory.is_dir():
            raise ValueError("adapter-working-directory must be an existing directory.")
        pack_directory = (
            Path(args.scenario_pack_directory)
            if args.scenario_pack_directory
            else None
        )
        packs = _load_packs(pack_directory)
        adapter = SubprocessAdapter(
            agent_id=args.agent_id,
            command=command,
            timeout_seconds=args.timeout_seconds,
            max_response_bytes=args.max_response_bytes,
            max_stderr_bytes=args.max_stderr_bytes,
            max_memory_bytes=args.max_memory_bytes,
            working_directory=args.adapter_working_directory,
        )
        if pack_directory is None:
            report = run_adapter_comparison(adapter, include_mutations=mutations)
        else:
            if mutations:
                raise ValueError(
                    "mutations must be false when scenario-pack-directory is supplied."
                )
            report = run_pack_comparison(adapter, packs)
        consumer_contract = None
        if args.consumer_policy_manifest:
            manifest_path = Path(args.consumer_policy_manifest)
            if not manifest_path.is_absolute():
                manifest_path = args.adapter_working_directory / manifest_path
            manifest = load_consumer_policy_manifest(manifest_path)
            agent_report = (
                report.reports[0] if hasattr(report, "reports") else report
            )
            consumer_contract = evaluate_consumer_contract(
                agent_report.trace_metadata,
                manifest,
                tuple(pack.scenario_id for pack in packs),
            )
        run_manifest = None
        if bool(args.run_manifest) != bool(args.current_revisions):
            raise ValueError(
                "--run-manifest and --current-revisions must be supplied together."
            )
        if args.run_manifest:
            run_manifest_path = Path(args.run_manifest)
            current_revisions_path = Path(args.current_revisions)
            if not run_manifest_path.is_absolute():
                run_manifest_path = args.adapter_working_directory / run_manifest_path
            if not current_revisions_path.is_absolute():
                current_revisions_path = (
                    args.adapter_working_directory / current_revisions_path
                )
            run_manifest = evaluate_reauthorization(
                load_manifest(str(run_manifest_path)),
                load_current_revisions(str(current_revisions_path)),
            ).to_dict()
        data = _metadata_report(
            report=report,
            packs=packs,
            custom_packs=pack_directory is not None,
            consumer_contract=consumer_contract,
            run_manifest=run_manifest,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        data = _refusal(error)
        refused = True

    _write_output(args.output, data)
    _write_summary(data)
    return int(refused or (fail_on_findings and data.get("passed") is not True))


if __name__ == "__main__":
    raise SystemExit(main())
