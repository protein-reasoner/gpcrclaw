# Scientific Workflow

## Domain Frame

GPCRs are seven-transmembrane receptors with extracellular loops, transmembrane helices, and intracellular loops. GPCRclaw targets extracellular loop 2, or ECL2, because it is accessible from outside the cell and can offer subtype-specific surface features.

For this demo, the product should focus on ECL2 binders rather than deep-pocket binders. That keeps the story clean:

- The intended epitope is extracellular.
- Candidate binders are VHH/nanobody format.
- Binding is constrained to ECL2 and immediate TM4/TM5 flanks.
- Orthosteric pocket and intracellular contacts are forbidden.
- The product prioritizes a small candidate set over broad recall.

## Targets

### LPAR1

LPAR1 is the primary demo target.

```json
{
  "target_id": "LPAR1",
  "name": "Lysophosphatidic acid receptor 1",
  "gene": "LPAR1",
  "alias": "EDG2",
  "uniprot_id": "Q92633",
  "protein_class": "Class A GPCR, lysophospholipid receptor family",
  "length_aa": 364,
  "native_ligand": "lysophosphatidic acid (LPA)",
  "target_region": "ECL2",
  "approx_ecl2_range": [188, 211],
  "recommended_primary_template": {
    "pdb_id": "7TD0",
    "state": "active",
    "notes": "LPAR1 + LPA + Gi heterotrimer"
  },
  "counter_screen_targets": ["LPAR2", "LPAR3", "LPAR4", "LPAR5", "LPAR6"]
}
```

Primary demo story:

- Use active template `7TD0`.
- Highlight ECL2 residues `188-211`.
- Use 5 demo-derived hotspot residues.
- Rank about 10 demo/precomputed candidates.

### MRGPRX2

MRGPRX2 is the second target or stretch target.

```json
{
  "target_id": "MRGPRX2",
  "name": "Mas-related G protein-coupled receptor X2",
  "gene": "MRGPRX2",
  "uniprot_id": "Q96LB1",
  "protein_class": "Class A GPCR, Mas-related family",
  "length_aa": 330,
  "target_region": "ECL2",
  "approx_ecl2_range": [165, 185],
  "recommended_primary_template": {
    "pdb_id": "7S8L",
    "state": "active",
    "notes": "MRGPRX2 + cortistatin-14 + Gq"
  },
  "counter_screen_targets": ["MRGPRX1", "MRGPRX3", "MRGPRX4"]
}
```

Secondary demo story:

- Use active template `7S8L`.
- Highlight ECL2 residues `165-185`.
- Use a compact hotspot set.
- Rank about 8 demo/precomputed candidates.

## ECL2 Design Rationale

ECL2 is useful in the demo because:

- It is accessible to extracellular binders.
- It is easier to explain visually than a deep orthosteric pocket.
- It can vary across related GPCRs, supporting a specificity narrative.
- It supports a compact VHH design story with CDR3 lengths around `10-18`.
- It creates a clear constraint system: bind ECL2, avoid unrelated receptor regions.

## Binder Constraints

Canonical demo constraints:

```json
{
  "binder_format": "VHH / nanobody",
  "scaffold": "camelid_nanobody",
  "cdr3_length_range": [10, 18],
  "target_epitope": "ECL2",
  "allowed_contacts": ["ECL2", "immediate TM4 flank", "immediate TM5 flank"],
  "forbidden_contacts": ["orthosteric pocket", "intracellular face", "unrelated receptor surface"],
  "candidate_count_goal": "single digits after filtering",
  "design_priority": "precision over recall"
}
```

## Hotspot Strategy

Gold-standard hotspot derivation would:

1. Load the receptor structure.
2. Map the ECL2 residue range onto the receptor chain.
3. Estimate solvent exposure.
4. Select surface-exposed ECL2 residues.
5. Optionally include immediate TM4/TM5 flanking residues.
6. Exclude buried residues and unrelated receptor surfaces.

MVP hotspot derivation should:

- Use precomputed demo hotspot residues.
- Label them as `demo-derived` or `precomputed`.
- Include exposure and role metadata.
- Keep the set small enough for candidate explanations.

Example LPAR1 demo hotspots:

```json
[
  {"residue": "R190", "exposure": 0.82, "role": "surface exposed ECL2 contact"},
  {"residue": "Y194", "exposure": 0.77, "role": "hydrophobic/aromatic surface"},
  {"residue": "D198", "exposure": 0.69, "role": "polar/charged contact"},
  {"residue": "K201", "exposure": 0.74, "role": "charged surface contact"},
  {"residue": "F205", "exposure": 0.63, "role": "surface aromatic contact"}
]
```

Example MRGPRX2 demo hotspots:

```json
[
  {"residue": "K166", "exposure": 0.78, "role": "charged exposed contact"},
  {"residue": "F170", "exposure": 0.65, "role": "hydrophobic contact"},
  {"residue": "D174", "exposure": 0.71, "role": "polar/charged contact"},
  {"residue": "Y178", "exposure": 0.68, "role": "aromatic contact"}
]
```

## Scientific Assumptions To Keep Visible

- ECL2 ranges are approximate until verified against sequence/structure alignment.
- Demo hotspot residues are not calculated unless a real structure parser is implemented.
- Candidate structures and interface scores can be mocked or precomputed for hackathon speed.
- The app should consistently say `predicted`, `demo-derived`, `precomputed`, or `computational`.
- The final output requires wet-lab validation.

## Replay-Derived Caveat

The shared Biomni replay used MOR antagonist design where CDR3 was allowed to engage the orthosteric pocket plus the ECL2 lid. That is a different biological objective from the current GPCRclaw brief.

For LPAR1/MRGPRX2, keep the default scope ECL2-focused unless the user explicitly changes the target epitope. Do not import MOR-specific assumptions such as pocket penetration, MOR hotspot residues, or DP motif preference into the GPCRclaw target configs.
