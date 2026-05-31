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
    name: "Boot GPU VM",
    description: "Start the A100 worker VM, attach the LPAR1 campaign inputs, and keep the run record tied to the cloud job.",
    state: "running"
  },
  {
    name: "Run drug design model",
    description: "Execute RFantibody/RFdiffusion on the GPU VM to generate ECL2-focused VHH candidates and output artifacts.",
    state: "running"
  },
  {
    name: "Run evaluation model",
    description: "Filter and gate generated candidates with Boltz-2 ipSAE, epitope contacts, ipTM, pTM, VHH developability checks, and structure artifacts before ranking returned results.",
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
