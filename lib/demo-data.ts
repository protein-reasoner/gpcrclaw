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

export const scoreWeights = {
  interfaceConfidence: 0.35,
  epitopeContacts: 0.25,
  poseConsistency: 0.15,
  specificity: 0.15,
  developability: 0.1
} as const;

function interfaceConfidence(ipSAE: number, ipTM: number) {
  return round4(0.6 * ipSAE + 0.4 * ipTM);
}

function rankScore(candidate: {
  ipSAE: number;
  ipTM: number;
  epitopeContactScore: number;
  poseConsistencyScore: number;
  specificityScore: number;
  developabilityScore: number;
}) {
  const interfaceScore = interfaceConfidence(candidate.ipSAE, candidate.ipTM);
  return round4(
    scoreWeights.interfaceConfidence * interfaceScore +
      scoreWeights.epitopeContacts * candidate.epitopeContactScore +
      scoreWeights.poseConsistency * candidate.poseConsistencyScore +
      scoreWeights.specificity * candidate.specificityScore +
      scoreWeights.developability * candidate.developabilityScore
  );
}

function round4(value: number) {
  return Math.round(value * 10000) / 10000;
}

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
    ipSAE: 0.82,
    ipTM: 0.76,
    interfaceConfidence: interfaceConfidence(0.82, 0.76),
    epitopeContactScore: 0.8,
    poseConsistencyScore: 0.78,
    specificityScore: 0.7,
    developabilityScore: 0.842,
    rankScore: rankScore({
      ipSAE: 0.82,
      ipTM: 0.76,
      epitopeContactScore: 0.8,
      poseConsistencyScore: 0.78,
      specificityScore: 0.7,
      developabilityScore: 0.842
    }),
    artifactPath: ".gpcrclaw/examples/rfantibody/output/structures/LPAR1_RFNB_001_binder.pdb"
  },
  {
    rank: 2,
    id: "LPAR1_RFNB_004",
    cdr3: "LSADRKQVDKMIT",
    cdr3Length: 13,
    ipSAE: 0.76,
    ipTM: 0.72,
    interfaceConfidence: interfaceConfidence(0.76, 0.72),
    epitopeContactScore: 0.6,
    poseConsistencyScore: 0.72,
    specificityScore: 0.66,
    developabilityScore: 0.767,
    rankScore: rankScore({
      ipSAE: 0.76,
      ipTM: 0.72,
      epitopeContactScore: 0.6,
      poseConsistencyScore: 0.72,
      specificityScore: 0.66,
      developabilityScore: 0.767
    }),
    artifactPath: ".gpcrclaw/examples/rfantibody/output/structures/LPAR1_RFNB_004_binder.pdb"
  },
  {
    rank: 3,
    id: "LPAR1_RFNB_002",
    cdr3: "YPRYGYATDC",
    cdr3Length: 10,
    ipSAE: 0.71,
    ipTM: 0.68,
    interfaceConfidence: interfaceConfidence(0.71, 0.68),
    epitopeContactScore: 0.6,
    poseConsistencyScore: 0.67,
    specificityScore: 0.61,
    developabilityScore: 0.751,
    rankScore: rankScore({
      ipSAE: 0.71,
      ipTM: 0.68,
      epitopeContactScore: 0.6,
      poseConsistencyScore: 0.67,
      specificityScore: 0.61,
      developabilityScore: 0.751
    }),
    artifactPath: ".gpcrclaw/examples/rfantibody/output/structures/LPAR1_RFNB_002_binder.pdb"
  }
] as const;
