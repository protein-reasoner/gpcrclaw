export const demoCampaign = {
  id: "LPAR1_ECL2_DEMO",
  name: "LPAR1 ECL2 Campaign",
  target: "LPAR1",
  template: "7TD0",
  ecl2Range: "188-211",
  hotspots: ["R190", "Y194", "D198", "K201", "F205"],
  candidateCount: 4,
  evidenceMode: "local demo",
  artifactRoot: ".gpcrclaw/examples/rfantibody/output"
} as const;

export const pipelineStages = [
  {
    name: "Compile target brief",
    description: "Load LPAR1, 7TD0, ECL2 residues 188-211, and hotspot constraints into one design job.",
    state: "done"
  },
  {
    name: "Generate VHH candidates",
    description: "Emit local RFantibody-interface demo candidates with sequences, CDRs, FASTA files, binder PDBs, and downstream manifests.",
    state: "done"
  },
  {
    name: "Validate and rank",
    description: "Run the local loop through validation, retry one failed candidate, and return ranked research-support dossiers.",
    state: "demo-ready"
  }
] as const;

export const rankedCandidates = [
  {
    rank: 1,
    id: "LPAR1_RFNB_001",
    cdr3: "VRRTWHGTSYGERLFDV",
    cdr3Length: 17,
    interfaceScore: 0.863,
    specificityMargin: 0.4,
    developabilityScore: 0.842,
    rankScore: 0.7017,
    artifactPath: ".gpcrclaw/examples/rfantibody/output/structures/LPAR1_RFNB_001_binder.pdb"
  },
  {
    rank: 2,
    id: "LPAR1_RFNB_004",
    cdr3: "LSADRKQVDKMIT",
    cdr3Length: 13,
    interfaceScore: 0.817,
    specificityMargin: 0.363,
    developabilityScore: 0.767,
    rankScore: 0.649,
    artifactPath: ".gpcrclaw/examples/rfantibody/output/structures/LPAR1_RFNB_004_binder.pdb"
  },
  {
    rank: 3,
    id: "LPAR1_RFNB_002",
    cdr3: "YPRYGYATDC",
    cdr3Length: 10,
    interfaceScore: 0.792,
    specificityMargin: 0.311,
    developabilityScore: 0.751,
    rankScore: 0.618,
    artifactPath: ".gpcrclaw/examples/rfantibody/output/structures/LPAR1_RFNB_002_binder.pdb"
  }
] as const;
