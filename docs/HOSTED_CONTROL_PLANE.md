# Hosted control plane

The hosted control plane is an AWS-deployable service boundary around the existing
provider-neutral run-manifest evaluator.

It accepts:

- one versioned run manifest;
- one complete current-revision map; and
- the authenticated API caller supplied by API Gateway.

It returns whether the evidence is `reauthorized`, requires
`reauthorization_required`, or is `blocked`. It stores only decision metadata,
revision digests, identifiers, and an append-only audit record with enforced
time-to-live (TTL). TTL is the database mechanism that removes records after their
configured retention window.

It does not accept or store prompts, tool arguments, provider output, credentials,
private paths, or CERTI material. OpenAI and Anthropic adapters remain client-side:
they produce the shared metadata contract, while the hosted service evaluates it.

## Local verification

The service logic can be exercised without AWS credentials:

```bash
uv run pytest tests/unit/test_control_plane.py
```

The tests use an in-memory audit store. That proves the evaluator and metadata boundary;
it does not prove AWS deployment, IAM configuration, API Gateway signing, or DynamoDB
availability.

## AWS deployment boundary

`template.yaml` defines:

- an IAM-authenticated API Gateway REST API;
- a Python Lambda handler that reuses `run_manifest.evaluate_reauthorization`;
- a DynamoDB table with server-side encryption, point-in-time recovery, and TTL; and
- Lambda permissions limited to `PutItem`, `GetItem`, and `Query`.

The table's `DeletionPolicy` is `Retain` because deleting an audit table is not a
rollback operation. Retention and account selection must be reviewed before deployment.
The hosted service is not approved for private or production data by this repository.

Before deployment, complete:

1. security review for the AWS account, authentication, retention, and audit boundary;
2. delivery-path review for CI, protected main, deploy ownership, and rollback;
3. a synthetic smoke test against a non-production account; and
4. a deliberately unauthorised request test that observes a rejection.

No deployment command is part of the public CI workflow.
