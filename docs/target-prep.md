# Target Preparation Layer

Target prep owns the scientific inputs that must be clean before model workers run. It is intentionally separate from worker internals: workers still consume normal manifests, while `gpcrclaw.target_prep` produces and validates the target/candidate blocks inside those manifests.

## Scope

The current layer covers:

- static LPAR1 and MRGPRX2 target metadata
- canonical receptor sequences from UniProt
- primary structure-template selection
- receptor-only clean-structure placeholders
- ECL2 sequence residue mapping
- hotspot records with residue-label normalization
- worker target payloads for Boltz-2, RFAntibody, ThermoMPNN, and future workers
- candidate validation for sequence, target, epitope, and CDR3 consistency

It does not yet parse mmCIF/PDB files. Template residue numbering is recorded as an assumption until structure parsing is implemented.

## Artifacts

`write_target_prep_artifacts(target_id, output_dir)` writes the pre-model artifact bundle:

```text
target_metadata.json
template_selection.json
target_preparation.json
clean_target.pdb
hotspot_set.json
structure_warnings.json
worker_target.json
<TARGET>.fasta
```

Checked-in examples live under:

```text
examples/target_prep/lpar1_target_prep_manifest.json
examples/target_prep/mrgprx2_target_prep_manifest.json
examples/target_prep/structures/
```

The placeholder PDBs are contract fixtures, not atomically valid receptor coordinates.

## Residue Normalization

The docs use demo hotspot labels such as `R190` for LPAR1. When checked against the canonical UniProt LPAR1 sequence, residue 190 is `C`, so the clean worker payload uses `C190` and preserves `R190` as `configured_residue` with a warning.

This keeps the product story traceable while preventing downstream model workers from receiving residue labels that contradict the receptor sequence.

Current normalized hotspot sets:

```json
{
  "LPAR1": ["C190", "N194", "M198", "L201", "S205"],
  "MRGPRX2": ["K166", "F170", "D174", "G178"]
}
```

## Validation Gates

Use these utilities before submitting model jobs:

- `validate_target_definition(target_id)` checks static target records.
- `validate_worker_target_payload(target)` checks sequence, ECL2 range, hotspot labels, and structure path presence.
- `validate_candidate_input(candidate, target_id=...)` checks candidate target/epitope/sequence/CDR3 consistency.
- `validate_worker_input_manifest(manifest)` wraps the shared worker manifest contract and target/candidate gates.

For generation workers, the candidate can be a generation-batch placeholder. For scoring workers such as Boltz-2 and ThermoMPNN, the candidate sequence and CDR3 must be present and internally consistent.

## Sources

- LPAR1 canonical sequence: <https://rest.uniprot.org/uniprotkb/Q92633.fasta>
- MRGPRX2 canonical sequence: <https://rest.uniprot.org/uniprotkb/Q96LB1.fasta>
- LPAR1 template: <https://www.rcsb.org/structure/7TD0>
- MRGPRX2 template: <https://www.rcsb.org/structure/7S8L>
