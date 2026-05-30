# UI And Demo Runbook

## UI Tone

The app should feel polished, scientific, and serious. It can be futuristic, but it should not become gimmicky.

Good visual language:

- Clean lab/workbench interface.
- Clear status colors.
- Structured JSON previews.
- Scientific tables.
- One strong epitope visualization.
- Concise evidence summaries.

Avoid:

- Generic chatbot layouts.
- Excessive marketing hero copy.
- Overloaded cards with no workflow hierarchy.
- Claims that candidates are validated binders.
- Visuals that do not explain ECL2, hotspots, or ranking.

## Screen 1: Landing / Project Overview

Primary text:

```text
GPCRclaw
Agentic ECL2 Nanobody Design Campaigns for GPCRs
```

Supporting copy:

```text
Turn GPCR nanobody design briefs into structured in-silico campaigns:
target selection, ECL2 hotspot derivation, candidate generation, scoring,
specificity filtering, developability checks, and final design reports.
```

Primary action:

```text
Start ECL2 Campaign
```

## Screen 2: Target Selection

Target cards:

```text
LPAR1
Lysophosphatidic acid receptor 1
UniProt: Q92633
ECL2: approx. 188-211
Primary template: 7TD0
Counter-screen: LPAR2-LPAR6
```

```text
MRGPRX2
Mas-related GPCR X2
UniProt: Q96LB1
ECL2: approx. 165-185
Primary template: 7S8L
Counter-screen: MRGPRX1, MRGPRX3, MRGPRX4
```

LPAR1 should be visually marked as the primary demo target.

## Screen 3: Campaign Pipeline

Pipeline stages:

```text
1. Parse Brief
2. Select Template
3. Locate ECL2
4. Derive Hotspots
5. Compile Design Spec
6. Generate Candidates
7. Score Interface
8. Counter-Screen Specificity
9. Filter Developability
10. Rank Candidates
11. Generate Report
```

Each stage should show:

- Status: pending, running, done, warning, failed.
- Short explanation.
- Expandable JSON output.
- Any warnings.

For the hackathon demo, stages can animate quickly while returning deterministic results.

## Screen 4: Structure / Epitope View

The important visual moment:

```text
Target receptor -> ECL2 highlighted -> hotspot residues -> candidate nanobody interface
```

MVP schematic:

- GPCR 7TM schematic.
- ECL2 loop highlighted.
- Hotspot residue chips attached to the loop.
- Nanobody shape positioned near ECL2.
- Template and residue range displayed nearby.

3D stretch:

- Load local PDB.
- Style receptor cartoon.
- Highlight ECL2 residue range.
- Show candidate complex in a different color if available.

## Screen 5: Candidate Table

Columns:

```text
Rank
Candidate ID
CDR3
CDR3 Length
Interface Score
Hotspot Contacts
Specificity Margin
Developability
Final Score
Recommendation
```

Example:

```text
1 | LPAR1_NB_001 | ARGTYWDSRGLFDY | 14 | 0.86 | 4/5 | 0.51 | Pass | 0.84 | Advance
```

Interaction:

- Clicking a row opens candidate detail.
- Status badges should make warnings obvious.
- Rejected candidates should remain visible so the filtering story is clear.

## Screen 6: Candidate Detail

Show:

- Full sequence.
- CDR1/CDR2/CDR3.
- Interface score.
- Hotspot contacts.
- Counter-screen scores.
- Developability flags.
- Why selected or why held/rejected.
- Validation recommendation.

Example explanation:

```text
Why selected:
- Strong predicted ECL2 interface
- Contacts 4/5 hotspot residues
- Low cross-reactivity vs LPAR2-LPAR6
- Passes developability filters

Warnings:
- Contains W in CDR3; monitor oxidation risk
```

## Screen 7: Final Report

Sections:

```text
Campaign Summary
Target Information
Template Selection
ECL2 Hotspot Set
Design Specification
Top Candidates
Specificity Counter-Screen
Developability Review
Recommended Validation
Limitations
```

Include a copy/export button if time allows.

## Demo Script

The app should support this path:

1. Open GPCRclaw.
2. Select `LPAR1 ECL2 Campaign`.
3. Show the target card:
   - LPAR1.
   - UniProt `Q92633`.
   - Active template `7TD0`.
   - ECL2 range `188-211`.
   - Counter-screen `LPAR2-LPAR6`.
4. Click `Run Campaign`.
5. Pipeline animates:
   - Parse Brief: done.
   - Select Template: `7TD0`.
   - Locate ECL2: residues `188-211`.
   - Derive Hotspots: 5 exposed demo-derived residues.
   - Compile Design Spec: VHH, CDR3 `10-18`, ECL2-only contacts.
   - Generate Candidates: 10 candidates.
   - Score Interface: assigns interface and contact scores.
   - Counter-Screen: flags cross-reactive candidates.
   - Developability: filters liability motifs.
   - Rank: top 3 candidates.
6. Show structure or schematic view.
7. Show ranked candidate table.
8. Open top candidate.
9. Explain why top candidate advances.
10. Open final report.
11. Report ends with validation next steps and computational-only limitations.

## Demo Narrative

Use this concise spoken story:

```text
GPCRclaw takes a GPCR nanobody design brief and compiles it into a structured in-silico campaign. For LPAR1, it selects an active receptor template, localizes ECL2, derives a constrained hotspot set, evaluates demo-generated VHH candidates, filters them for specificity and developability, and returns a small set of computationally prioritized candidates for experimental validation.
```
