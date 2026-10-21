# Reusable-action consumer fixture

This directory is a synthetic consumer repository fixture. It has no provider
credentials, network client, private content, or dependency on the harness package.

The adapter uses only the standard library and implements the identifier-only
JSONL protocol expected by the reusable Agent Assurance Action. The workflow
demonstrates both paths:

- a guarded adapter that should pass; and
- a deliberately degraded adapter that should be blocked.

The workflow pins the action to the reviewed Phase 17 commit. A consumer should
update that reference only through a reviewed dependency change, because a moving
branch can change the assurance code without changing the consumer workflow.

`policy-manifest.json` adds a metadata-only consumer contract. It binds adapter
traces to a reviewed policy version and SHA-256 digest, requires the protected
write scenario to report `orders:write`, and requires the unsupported-request
scenario to report an escalation. The degraded adapter violates these controls
as well as the evidence contract, so the action blocks it.

`policy-manifest-drifted.json` is a valid but different policy declaration. The
local consumer validation runs the same guarded adapter against the approved
manifest, the drifted manifest, and the approved manifest again. The drifted
state must block, and the restored approved state must pass.

This fixture does not provide live credentials, IAM enforcement, a vault,
an egress gateway, or a human escalation queue. It proves that those expectations
are represented and enforced at the pre-merge boundary.
