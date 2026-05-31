# Implementation Plan

## Recommended Stack

Fastest coherent build:

```text
Next.js + React + TypeScript + Tailwind
Next.js API routes for campaign endpoints
Local JSON files for targets, candidates, templates, and scores
Optional 3Dmol.js or NGL viewer after the core workflow works
```

Avoid splitting into a Python backend until there is a real computational reason. A pure Next.js app keeps the hackathon build smaller and easier to demo.

## Repo Structure

Recommended structure:

```text
gpcrclaw/
  app/
    page.tsx
    targets/page.tsx
    campaign/[id]/page.tsx
    report/[id]/page.tsx
    api/
      targets/route.ts
      campaign/start/route.ts
      campaign/run/route.ts
      campaign/[id]/report/route.ts
  components/
    TargetCard.tsx
    PipelineStepper.tsx
    AgentOutputCard.tsx
    StructureViewer.tsx
    CandidateTable.tsx
    CandidateDetail.tsx
    ReportView.tsx
    ScoreBadge.tsx
    RiskBadge.tsx
  lib/
    targets.ts
    candidates.ts
    pipeline.ts
    scoring.ts
    developability.ts
    specificity.ts
    report.ts
    types.ts
  data/
    targets.json
    candidates/
      lpar1_candidates.json
      mrgprx2_candidates.json
    templates/
      lpar1_templates.json
      mrgprx2_templates.json
    mock_scores/
      lpar1_scores.json
      mrgprx2_scores.json
  public/
    structures/
      7TD0.pdb
      7S8L.pdb
      predicted_complexes/
```

## API Endpoints

### `GET /api/targets`

Returns target metadata for target selection.

### `POST /api/campaign/start`

Request:

```json
{
  "target_id": "LPAR1"
}
```

Response:

```json
{
  "campaign_id": "LPAR1_ECL2_CAMPAIGN_001",
  "target": {},
  "pipeline_status": "initialized"
}
```

### `POST /api/campaign/run`

Request:

```json
{
  "campaign_id": "LPAR1_ECL2_CAMPAIGN_001"
}
```

Response:

```json
{
  "campaign_id": "LPAR1_ECL2_CAMPAIGN_001",
  "target": {},
  "stages": [],
  "ranked_candidates": [],
  "report": {}
}
```

### `GET /api/campaign/:id/report`

Returns the final campaign report JSON.

For the MVP, campaign state can be deterministic and reconstructed from `target_id`. Persistent storage is not required.

## Phase 1: Data And Schemas

Goal: make the campaign objects real before building UI polish.

Tasks:

- Create `lib/types.ts`.
- Create `data/targets.json`.
- Create candidate JSONs.
- Create mock score JSONs.
- Encode hotspot metadata in target config or separate files.
- Add type-safe loaders in `lib/targets.ts` and `lib/candidates.ts`.

Done when:

- A Node/TypeScript function can load LPAR1 target config and candidates.
- Candidate data includes mixed pass, warning, and fail examples.

## Phase 2: Pipeline Backend

Goal: implement deterministic campaign runner.

Tasks:

- Create `lib/pipeline.ts`.
- Create stage functions for each agent.
- Implement `lib/specificity.ts`.
- Implement `lib/developability.ts`.
- Implement `lib/scoring.ts`.
- Implement `lib/report.ts`.
- Add API routes.

Done when:

- `POST /api/campaign/run` returns full LPAR1 campaign JSON.
- Ranking is deterministic.
- Final report JSON includes limitations.

## Phase 3: Frontend

Goal: make the workflow inspectable.

Tasks:

- Landing/project overview screen.
- Target selection screen.
- Campaign pipeline screen.
- Candidate table.
- Candidate detail panel.
- Final report view.
- Status badges and risk badges.

Done when:

- User can run LPAR1 campaign from UI.
- Pipeline stages render with status and JSON previews.
- Candidate table sorts by final rank.
- Final report is readable.

## Phase 4: Visualization

Goal: make ECL2 visibly understandable.

Start with a schematic:

- Seven transmembrane receptor cartoon.
- ECL2 loop highlighted.
- Hotspot residue chips.
- Candidate nanobody docked as a simple visual element.

Then add optional 3D:

- Use 3Dmol.js or NGL.
- Load local `7TD0.pdb`.
- Highlight configured residue range.
- Add candidate complex if available.

Done when:

- The user can visually identify target, ECL2, hotspots, and candidate binder.

## Phase 5: Polish

Goal: turn the core workflow into a demo-worthy product.

Tasks:

- Add stage animation.
- Add concise scientific explanations.
- Add report copy/export.
- Add MRGPRX2 support.
- Add honest labels for mocked or precomputed data.
- Add empty/loading/error states.

Done when:

- The demo script can be run smoothly end to end.
- The UI avoids looking like a generic AI dashboard.

## Engineering Priorities

1. Deterministic end-to-end campaign first.
2. Clear evidence artifacts second.
3. Visual polish third.
4. Real structure parsing fourth.
5. Dynamic brief parsing last.

This order avoids spending time on 3D or LLM behavior before the product has a coherent core.

## Biomni Replay Addendum

The shared Biomni replay shows a more realistic end-state pipeline than the first GPCRclaw MVP:

```text
RFAntibody / RFdiffusion + ProteinMPNN generation
-> Boltz-2 complex scoring
-> ThermoMPNN stability scoring
-> ImmuneBuilder CDR loop quality
-> integrated ranking
-> report plus artifacts
```

Use this as a long-term architecture target, not as the first implementation requirement.

Recommended product modes:

- `mock`: local JSON candidates and deterministic scoring.
- `precomputed`: load completed CSV/JSON/PDB artifacts from a prior run and render a real campaign report.
- `live`: submit generation/scoring jobs, track batches, retry failures, and stream progress.

For the hackathon build, implement `mock` first and design the data model so `precomputed` can be added without rewriting the UI.

Operational lessons to encode in the model:

- Real generation must be batched; avoid monolithic jobs.
- Campaigns can be partial and still useful.
- Store job IDs, batch IDs, output artifact IDs, and retry notes.
- Structure scoring and report generation should work even when only top candidates have expensive metrics.

## GPU Agent Runtime Update

The first implementation now uses a Python package for the campaign agent runtime before a frontend or Cloud Run API is added.

Implemented first:

- Local campaign state under `.gpcrclaw/state`.
- Local artifacts under `.gpcrclaw/artifacts`.
- File-based worker contract for `manifest.json`, `metrics.json`, `artifacts.json`, and `logs.txt`.
- `fake_worker` for local smoke runs and future Batch smoke jobs.
- Google Batch dry-run payload generation for `us-central1` L4 and A100 jobs.
- Boltz-2 placeholder that validates the same manifest contract and returns a not-yet-configured worker error.

Next after the fake-worker cloud smoke passes:

1. Publish the fake-worker image to Artifact Registry.
2. Run one L4 Google Batch smoke job and verify Cloud Storage outputs.
3. Run one standard A100 Google Batch smoke job and verify Cloud Storage outputs.
4. Run a bounded parallel fake-worker A100 batch below the configured concurrency limit.
5. Replace only the worker internals with a Boltz-2 scoring container while keeping campaign orchestration and artifact provenance unchanged.
- Tool-derived scores must be labeled with tool name and provenance.

## Workstream Bucket Reference

The full build is split into ownership-sized buckets in [Workstream Buckets](./workstream-buckets.md). Use that document as the operating map when turning this plan into tasks.

The concrete agent/GPU execution decision is in [Agent GPU Architecture](./agent-gpu-architecture.md). Use that document for backend adapter contracts, model-worker output contracts, and `alankrit/` naming.
