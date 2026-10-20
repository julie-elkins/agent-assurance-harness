# Security policy

## Scope

Agent Reliability Lab is a public, synthetic demonstration. The repository must not
contain unpublished exam material, candidate data, private prompts, raw provider output,
credentials, customer data, or copied internal logs.

The default pull-request CI job is offline with respect to model providers. It has
read-only repository permissions, receives no provider credentials, and must not enable
the live provider flag. A separate push-only job has the minimum GitHub permissions
needed to create release provenance attestations; it runs only after the read-only job
passes and does not receive provider credentials.

## Live-provider boundary

The optional live command is a local-only integration boundary for one built-in synthetic
scenario. It accepts no caller-supplied task content, arbitrary endpoint, credential
argument, retry policy, persistent trace, or background job.

When `--allow-network` is used, the process reads the fixed provider environment variable
and sends a synthetic request to the selected official HTTPS endpoint. This is external
transmission by design. The credential is not written to the repository, report, replay,
exception, or log, but the provider necessarily receives it as an authentication header.

Do not use the live boundary with private input until an application security review and
delivery-path review have approved that change.

## Reporting a vulnerability

Please do not publish a suspected credential or private-data exposure in a public issue.
Remove the secret from active use, preserve only the minimum synthetic reproduction, and
contact the repository owner through GitHub's private vulnerability reporting mechanism
when it is available. If private reporting is unavailable, open an issue that contains
only a high-level description and no secret, private input, raw provider response, or
exploit payload.

## Verification

Run the repository boundary check, dependency audit, and test suite locally:

```bash
uv run python tools/check_repository_boundaries.py
uv run python tools/audit_dependencies.py
uv run pytest
```

The boundary check is a high-signal guard, not proof that the repository contains no
possible secret. Reviewers must still inspect unexpected files and diffs.
