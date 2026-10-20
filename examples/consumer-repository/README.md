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
