# Troubleshooting

## The command reports a failed guarded path

Inspect the guarded result's `missing_evidence` list. The usual causes are:

- semantic outcome was not recorded;
- retry or cost ceiling was omitted;
- the workflow identifier changed;
- escalation was not recorded; or
- the independent breaker was weakened.

The correct repair is to restore the evidence contract, not to remove the failing
control.

## The command reports success for both paths

The negative control is no longer proving anything. Check that the naive path still
has an empty semantic outcome and exceeds the declared retry and cost ceilings.

## The output contains raw content

Stop. The public lab is metadata-only. Do not add prompts, tool arguments, provider
responses, customer data, or private source text to make the example easier to read.
