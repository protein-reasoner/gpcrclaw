export const demoCampaign = {
  id: "LPAR1_ECL2_DEMO",
  name: "LPAR1 ECL2 Campaign",
  target: "LPAR1",
  template: "7TD0",
  ecl2Range: "188-211",
  hotspots: ["R190", "Y194", "D198", "K201", "F205"],
  candidateCount: 10
} as const;

export const pipelineStages = [
  {
    name: "Target and template",
    description: "Resolve the selected GPCR, UniProt record, structure template, and ECL2 design scope.",
    state: "ready"
  },
  {
    name: "Hotspot set",
    description: "Keep the epitope definition inspectable through configured residues and counter-screen targets.",
    state: "ready"
  },
  {
    name: "Worker batch",
    description: "Submit RFantibody and ESMFold2 work units through the manifest, GCS artifact, and Google Batch contract.",
    state: "cloud"
  },
  {
    name: "Ranking report",
    description: "Combine interface, specificity, and developability metrics into a limitations-aware report.",
    state: "ready"
  }
] as const;

export const rankedCandidates = [
  {
    rank: 1,
    id: "LPAR1_NB_002",
    interfaceScore: 0.863,
    specificityMargin: 0.4,
    developabilityScore: 0.842,
    rankScore: 0.7017
  },
  {
    rank: 2,
    id: "LPAR1_NB_001",
    interfaceScore: 0.817,
    specificityMargin: 0.363,
    developabilityScore: 0.767,
    rankScore: 0.649
  },
  {
    rank: 3,
    id: "LPAR1_NB_003",
    interfaceScore: 0.792,
    specificityMargin: 0.311,
    developabilityScore: 0.751,
    rankScore: 0.618
  }
] as const;
