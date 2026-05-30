# Project Understanding

## What Is Happening Here

GPCRclaw is a hackathon-oriented scientific workflow product. It takes a GPCR nanobody design goal and turns it into a structured in-silico campaign:

```text
Design brief
-> target and template selection
-> ECL2 localization
-> hotspot derivation
-> nanobody design specification
-> candidate loading or generation
-> interface scoring
-> specificity counter-screening
-> developability filtering
-> final ranking
-> campaign report
```

The user should feel like they are operating a research workbench, not chatting with an assistant. The app should expose structured artifacts at each stage: JSON outputs, brief explanations, candidate tables, scoring evidence, and a final report.

## Product Thesis

The hard demo problem is not "invent a real therapeutic." The hard demo problem is "make a credible campaign compiler." GPCRclaw should show that a messy biological design intent can become an ordered, auditable workflow with explicit constraints and outputs.

The strongest framing:

- The product is a design-brief-to-campaign compiler.
- The domain is ECL2-focused GPCR nanobody/VHH design.
- The output is a small, high-confidence candidate set for wet-lab validation.
- The scope is computational prioritization, not clinical validation.

## Primary Demo Scope

The MVP should focus on one reliable path:

1. User selects `LPAR1`.
2. App initializes an `LPAR1_ECL2_CAMPAIGN`.
3. Pipeline selects template `7TD0`.
4. Pipeline localizes ECL2 to approximate residues `188-211`.
5. Pipeline uses demo-derived hotspot residues.
6. Pipeline compiles a VHH design spec.
7. Pipeline loads about 10 candidate nanobody records.
8. Pipeline scores interface, specificity, and developability.
9. Pipeline ranks candidates.
10. App renders the final campaign report.

`MRGPRX2` should be the second target and strong-demo path if time allows.

## What This Is Not

GPCRclaw should not be presented as:

- A clinical therapeutic discovery platform.
- A wet-lab validated nanobody generator.
- A direct disease treatment claim.
- A generic GPCR chatbot.
- A broad library generation tool.

It is a research support and demo workflow that produces computationally prioritized candidates for expert review and experimental validation.

## User Mental Model

The intended user is a scientist or builder who wants to inspect the campaign. They need to see:

- Which target was selected.
- Which structure template was used.
- Which epitope and hotspot residues define the design problem.
- What constraints were applied to candidate generation.
- Why a candidate ranked above another candidate.
- Which candidates have specificity or developability warnings.
- What should happen next in the lab.

## Product Object Model

The central object is a `Campaign`.

A campaign contains:

- Target metadata.
- Template selection.
- ECL2 localization result.
- Hotspot set.
- Design specification.
- Candidate list.
- Candidate scoring outputs.
- Ranked candidates.
- Final campaign report.

Every UI screen and API endpoint should either create, inspect, advance, or render this campaign object.

## Success Criteria

MVP success means:

- LPAR1 campaign runs end to end.
- Candidate ranking is deterministic and explainable.
- Specificity warnings are visible.
- Developability filtering catches obvious liabilities.
- Final report renders with limitations.
- The UI looks like a serious scientific workflow.

Strong success means:

- MRGPRX2 also runs.
- Structure or schematic visualization clearly highlights ECL2.
- Report can be copied or exported.
- At least one real PDB file or real structure metadata is used.

Stretch success means:

- User can paste a natural-language brief.
- Metadata can be fetched live.
- Hotspots can be derived from coordinates instead of mocked.
- Candidate generation can call a real model or external service.
