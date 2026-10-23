# Advanced production operations

This lesson adds the organizational layer to AI incident response. It is for learners
who can already trace an AI workflow through data, retrieval, model execution, tools,
authorization, evidence, containment, and recovery.

It is a learning guide, not an organization's incident runbook, legal process, security
approval, or production-readiness assessment.

Use the [Production AI Agent Readiness Checklist](PRODUCTION_AI_AGENT_READINESS_CHECKLIST.md)
as the capstone crosswalk after this lesson. It points back to the evidence required
across the technical, organizational, and delivery-path controls instead of asking the
learner to treat this document as a complete readiness decision.

## Why ownership is a technical control

An incident can have a technically correct mitigation and still get worse when nobody
has the authority to apply it, communicate it, or verify that it worked. AI systems
make this harder because the change surface is wider than application code. A model,
prompt, retrieval index, tool permission, policy, evaluator, dependency, or deployment
configuration can change behavior.

**Incident ownership** means assigning a person or team authority for the next decision,
not merely naming someone who receives an alert. The owner must know:

- what decision is needed;
- what evidence is required;
- which action is allowed now;
- which action needs approval;
- who must be informed;
- when the decision will be revisited; and
- what would make the current plan unsafe.

If those questions have no named owner, the workflow may remain active while people
debate responsibility. That delay is itself a production risk.

## A small-team ownership model

**RACI** means Responsible, Accountable, Consulted, and Informed. It is a compact way to
show who performs a task, who owns the decision, who must advise, and who needs an
update. One person can hold more than one role in a small team, but high-risk changes
should not be approved only by the person who made the change.

| Decision or activity | Responsible | Accountable | Consulted | Informed |
| --- | --- | --- | --- | --- |
| Pause the affected workflow or tool | Technical lead | Incident commander | Security/privacy lead | Product owner |
| Preserve bounded evidence and timeline | Scribe or technical lead | Incident commander | Security/privacy lead | Product owner |
| Decide whether data exposure is possible | Security/privacy lead | Incident commander | Product owner | Communications lead |
| Describe user or business impact | Product owner | Incident commander | Technical lead | Communications lead |
| Send an internal status update | Communications lead | Incident commander | Security/privacy lead | Affected stakeholders |
| Approve an emergency mitigation | Technical lead | Change approver | Security/privacy and product leads | Incident team |
| Restore broader capability | Technical lead | Change approver | Incident commander and security/privacy lead | Affected stakeholders |

The **incident commander** is the person accountable for coordinating the response and
making the next operational decision. The commander does not need to diagnose every
technical detail. Their job is to establish priority, assign work, stop unsafe activity,
resolve conflicts, and declare when the response can move to recovery.

The **change approver** is the person accountable for accepting the risk of a production
change. For a high-risk AI change, approval should consider the affected model,
prompt, retrieval, tool, policy, permissions, evaluator, and rollback path together.

## Communications that help the response

Communication is part of containment. A vague update can cause a second incident when
another team resumes the workflow, retries an external action, or changes the same
configuration without knowing what is already happening.

A useful first update states:

1. **Status:** what is known and what remains uncertain.
2. **Scope:** the workflow, capability, or audience affected.
3. **Current control:** what has been paused, narrowed, or placed behind approval.
4. **Owner:** who is coordinating the response.
5. **User impact:** the observable effect, without exposing protected data.
6. **Next decision:** what must happen next and who owns it.
7. **Next update:** when the audience should expect another update.

Use audience-specific detail. The incident team may need revision identifiers and
authorization evidence. A product or support team may need a service-impact statement
and a safe workaround. An external status update may need only the affected capability,
current mitigation, and next update time. None of these audiences needs raw prompts,
customer content, secrets, credentials, or model output in a public channel.

The communication record should preserve decisions and times, not become a second copy of
the sensitive investigation. If a recipient cannot act on a detail, that detail probably
belongs in the bounded evidence system rather than the broad status channel.

## Production change management

**Production change management** is the controlled process for deciding whether a change
may reach a live system, how it is limited, and how its effect is verified.

During an incident, separate two paths:

- A **standard change** follows the normal review, testing, approval, deployment, and
  verification path.
- An **emergency change** is a time-sensitive change made to reduce immediate risk. It
  still needs an owner, a reason, a defined success condition, a defined failure
  condition, a rollback or containment plan, and a later review.

An incident does not automatically authorize every urgent change. The change must answer:

1. What risk does this change reduce?
2. What new risk could it introduce?
3. What is the narrowest scope that can test the mitigation?
4. Which evidence allows the change to proceed?
5. Who can stop or reverse it?
6. What result means the change failed?
7. When will the team decide whether to expand, hold, or reverse it?

For an AI workflow, the change record should identify the affected control boundary:

- model or model-routing revision;
- prompt or policy revision;
- retrieval source, index, or ranking change;
- tool contract or execution permission;
- evaluator or threshold;
- dependency or deployment configuration; or
- retry, timeout, cost, or approval behavior.

Prefer a **canary**, which is a limited rollout to a bounded audience or synthetic
traffic, before restoring broad capability. A canary is useful only if the team defines
the evidence it will inspect and the condition that stops expansion.

**Rollback** means returning to a known-good version or narrowing capability after a
change fails. Rollback may not undo an external action that already committed, so the
change plan must also name reconciliation work for effects that cannot be reversed
automatically.

## Recovery decision record

Before restoring broader capability, record:

- the incident and workflow identifiers;
- the owner and approver;
- the evidence preserved and any evidence gap;
- the containment action and what it did not undo;
- the change identifier and affected control boundary;
- the canary scope and observed result;
- the rollback or reconciliation path;
- the regression case that covers the failure;
- the residual risk accepted; and
- the next review time.

**Residual risk** is the risk that remains after the mitigation. Saying that it exists is
not the same as accepting it. A named decision owner must choose whether the remaining
risk is acceptable, whether capability stays narrowed, or whether more work is required.

## Tabletop exercise

Use the companion [AI Incident Response Tabletop Lab](../examples/ai-incident-response-lab/README.md)
after reading this lesson. For the synthetic scenario, assign the roles above and answer:

1. Who is the incident commander, and what decision are they accountable for in the
   next fifteen minutes?
2. Who can pause the workflow and external tool, and what evidence must they preserve?
3. Which audience receives the first update, and what detail must be withheld?
4. Is the proposed recovery a standard change or an emergency change? Why?
5. What is the narrowest canary scope?
6. What observation stops the canary or triggers rollback?
7. Who approves broader restoration, and what residual risk are they accepting?
8. What change should be made after the incident so the same failure is detected earlier?

A strong answer names one owner for every decision, distinguishes responsibility from
approval authority, gives communications an update time, and refuses to call the
workflow recovered merely because the service returns a successful response.

## Learner checkpoint

Explain these four statements in your own words:

1. An alert is not ownership.
2. Containment is not rollback.
3. An emergency change is still a controlled change.
4. A successful deployment is not evidence that the incident is resolved.

Then write a five-line recovery record containing the owner, change, canary, stop
condition, and verification evidence.

## What this lesson does not prove

- It does not establish that a real organization has the roles or authority described.
- It does not replace an incident plan, security review, privacy review, legal process, or
  change-management policy.
- It does not prove live monitoring, model quality, rollback capability, or business
  continuity.
- It does not authorize access to private data or external systems.
- It uses no provider credentials, live traffic, customer content, or real incident
  telemetry.

## First-party and public references

- [NIST SP 800-61 Revision 3: Incident Response Recommendations and Considerations for Cybersecurity Risk Management](https://csrc.nist.gov/pubs/sp/800/61/r3/final)
- [Google SRE: Managing Incidents](https://sre.google/sre-book/managing-incidents/)
- [Google SRE: Postmortem Culture](https://sre.google/sre-book/postmortem-culture/)
- [OpenAI Agent Builder safety](https://developers.openai.com/api/docs/guides/agent-builder-safety)
- [Anthropic: Trustworthy agents](https://www.anthropic.com/research/trustworthy-agents)
