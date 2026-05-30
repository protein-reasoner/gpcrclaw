# GPCRclaw Docs

This folder turns the pasted GPCRclaw brief into an implementation-ready project map.

GPCRclaw is an agentic scientific workflow for ECL2-focused GPCR nanobody design campaigns. The product should take a target design brief, compile it into a structured in-silico campaign, evaluate demo or precomputed VHH candidates, and return a ranked report for experimental validation planning.

The core product sentence:

> GPCRclaw turns GPCR ECL2 nanobody design briefs into ranked, inspectable in-silico binder campaigns with target templates, hotspot sets, candidate sequences, specificity screens, developability filters, and validation-ready reports.

## Docs Map

- [Project Understanding](./project-understanding.md): what the project is, what it is not, and the core product model.
- [Scientific Workflow](./scientific-workflow.md): target biology, ECL2 rationale, target configs, and scientific assumptions.
- [Agent Pipeline](./agent-pipeline.md): module-by-module contracts for the campaign runner.
- [Data And Scoring](./data-and-scoring.md): schemas, mock data requirements, scoring formula, and developability checks.
- [Implementation Plan](./implementation-plan.md): phased build order, repo structure, APIs, and engineering milestones.
- [Workstream Buckets](./workstream-buckets.md): the major build buckets for agent orchestration, model containers, Google GPU execution, artifacts, ranking, UI, and safety.
- [UI And Demo Runbook](./ui-and-demo-runbook.md): screens, user flow, demo script, and visual priorities.
- [Claim Boundaries](./claim-boundaries.md): wording rules, limitation handling, and scientific safety constraints.
- [Biomni Replay Analysis](./biomni-replay-analysis.md): extracted lessons from the shared Biomni MOR nanobody design run and how they should change GPCRclaw.

## Source Status

The current repository is empty except for Git metadata. These docs are therefore based on the provided pasted brief plus lightweight verification of the named UniProt and RCSB PDB records.

Verified reference anchors:

- [UniProt `Q92633`](https://www.uniprot.org/uniprotkb/Q92633/entry) maps to human LPAR1.
- [UniProt `Q96LB1`](https://www.uniprot.org/uniprotkb/Q96LB1/entry) maps to human MRGPRX2.
- [RCSB `7TD0`](https://www.rcsb.org/structure/7TD0) is an LPAR1-Gi complex bound to LPA.
- [RCSB `7S8L`](https://www.rcsb.org/structure/7S8L) is a Gq-coupled MRGPRX2 structure with cortistatin-14.

## Build Principle

The first build should optimize for a coherent, inspectable scientific workflow rather than biological perfection. It can use mocked or precomputed candidates and scores, but every mocked part must be labeled honestly.

Do not build a generic AI chat interface. Build a campaign compiler:

```text
Input:  LPAR1 or MRGPRX2 ECL2 nanobody design brief
Output: Ranked nanobody candidate campaign report
```
