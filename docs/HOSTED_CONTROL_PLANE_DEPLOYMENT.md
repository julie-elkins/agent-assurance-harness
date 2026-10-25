# Hosted control-plane deployment readiness

This runbook describes how a second person can prepare and deploy the hosted
control plane from a fresh checkout. It does not authorise deployment by itself.

The control plane is the remote service that evaluates and records whether agent
evidence remains valid. The first deployment must use synthetic metadata only.

## Required decisions before deployment

Complete these fields in the change record or deployment ticket; do not commit account
identifiers or credentials to this repository.

- AWS account: `NOT SELECTED`
- AWS region: `NOT SELECTED`
- Environment name: `NOT SELECTED`
- Deployment owner: `NOT ASSIGNED`
- Security reviewer: `NOT ASSIGNED`
- Rollback owner: `NOT ASSIGNED`
- Team notification destination: `NOT ASSIGNED`
- Approved retention period: `NOT ESTABLISHED`

Deployment is blocked while any required field remains unresolved. The thirty-day
retention value in `control_plane.py` is a modelling assumption for the demonstration,
not an approved production policy.

## Fresh-checkout preflight

Run from the repository root:

```bash
git status --short --branch
uv sync --locked --extra dev
uv run pytest
uv run python tools/check_repository_boundaries.py
uv run python tools/audit_dependencies.py
sam validate --lint --template-file template.yaml
sam build --template-file template.yaml --build-dir /tmp/agent-assurance-sam-build
uv run python tools/hosted_control_plane_smoke_test.py
```

The smoke test is a synthetic local check. It proves current evidence, stale evidence,
unauthorised access, audit lookup, expiry metadata, and the absence of content fields.
It does not prove IAM request signing or AWS service availability.

The SAM build currently relies on the `boto3` package supplied by the AWS Lambda
runtime; it intentionally has no deployment `requirements.txt`. Before production use,
the security and delivery review must either accept that platform dependency or add a
deployment-specific pinned dependency file and audit it separately.

## Identity and environment preflight

The deployment owner must verify the selected AWS account and region from the active
identity before creating resources:

```bash
aws sts get-caller-identity
aws configure list
```

The account returned by `aws sts get-caller-identity` must match the approved change
record. A shell profile name or environment label is not sufficient evidence of account
identity.

## Deployment

Deployment requires an approved non-production account, a reviewed change, and an
authenticated AWS identity with the minimum permissions needed to create the stack.
The exact stack name and region come from the approved change record.

```bash
sam deploy --template-file .aws-sam/build/template.yaml --stack-name <approved-stack-name> --region <approved-region> --capabilities CAPABILITY_IAM --resolve-s3
```

Keep change-set confirmation enabled for the first deployment. Review the generated
resources before accepting them.

## Live smoke test

After deployment, run the synthetic cases through the deployed API using an approved
IAM identity:

1. submit the checked-in current manifest and current revisions;
2. confirm `reauthorized`;
3. submit the checked-in manifest with changed revisions;
4. confirm `reauthorization_required`;
5. request the run state and confirm the audit record contains metadata only;
6. repeat without AWS authentication and confirm rejection; and
7. verify the DynamoDB TTL setting from the table, not from the deployment command's
   success output.

Do not send provider credentials, prompts, tool arguments, model output, private paths,
or other private material.

## Local hosted client

The local hosted client is the first reusable caller for the deployed service. It uses
an AWS CLI profile to obtain temporary credentials and signs the two metadata-only
routes; it does not store provider credentials in AWS and does not contact OpenAI or
Anthropic:

```bash
uv run python tools/hosted_control_plane_client.py \
  --endpoint https://<api-id>.execute-api.<region>.amazonaws.com/v1 \
  --profile <aws-profile> \
  --region <region> \
  --manifest examples/run-manifest/manifest.json \
  --current-revisions examples/run-manifest/current-revisions.json \
  --provider all \
  --fail-on-non-reauthorized
```

The provider option uses synthetic OpenAI-shaped and Anthropic-shaped identifiers
through the same run-manifest contract. It is a contract demonstration, not evidence of
live provider quality or production readiness.

## Rollback

Rollback means returning the stack to a known-good template and code revision. For the
first non-production rehearsal:

1. record the deployed stack revision and outputs;
2. deploy the previous known-good template;
3. verify the API routes and IAM policy;
4. run the synthetic smoke test again; and
5. record the result and the rollback owner.

The DynamoDB table uses `DeletionPolicy: Retain`; deleting the stack is not the rollback
procedure and must not be used as a substitute for a rehearsed update rollback.

## Release gate

No production or private-data deployment is approved by this repository. A security
review, an explicit environment decision, a named owner, a tested rollback, and a team
notification path must exist before the service is used beyond synthetic testing.
