# Claim Boundaries

## Core Rule

GPCRclaw produces computational campaign artifacts. It does not produce validated therapeutics.

Use these words consistently:

- `candidate`
- `predicted`
- `computational`
- `in-silico`
- `demo-derived`
- `precomputed`
- `requires wet-lab validation`
- `for research support`

## Do Not Say

Do not say:

```text
We discovered a therapeutic.
We created a validated nanobody.
This will bind in real life.
This treats disease.
This is ready for clinical use.
```

## Say Instead

Say:

```text
We generated an in-silico candidate campaign.
These are computationally prioritized candidates.
The output requires wet-lab binding validation.
This is for research and design support.
The score is demo-derived or precomputed.
```

## UI Labels

When a value is mocked or precomputed, label it directly:

- `demo-derived hotspot`
- `precomputed candidate`
- `demo oracle interface score`
- `placeholder predicted complex`
- `computational-only recommendation`

The final report should include a visible limitations section.

## Required Report Limitations

Every final report should state:

- The campaign is computational only.
- No wet-lab validation has been performed.
- Candidate structures and scores may be mocked, demo-derived, or precomputed.
- Binding, specificity, and developability require experimental confirmation.
- The output is not a clinical or therapeutic claim.

## Recommendation Language

Use:

```text
advance_to_experimental_validation
hold_for_review
reject
```

Avoid:

```text
approved
validated
therapeutic
clinical candidate
safe
effective
```

## Scientific Risk Notes

These points should remain visible in docs and report logic:

- ECL2 ranges are approximate until sequence/structure mapping is verified.
- Static hotspot sets are not substitutes for structural exposure calculations.
- Specificity scoring is only a proxy unless real structural or experimental evidence is used.
- Developability regex checks catch simple sequence liabilities, not full manufacturability.
- Candidate ranking is a triage aid, not proof of binding.
