import { NextResponse } from "next/server";
import { demoCampaign, pipelineStages, rankedCandidates } from "@/lib/demo-data";

export function GET() {
  return NextResponse.json({
    campaign: demoCampaign,
    stages: pipelineStages,
    rankedCandidates,
    limitations: [
      "Computational research-support output only.",
      "Mock and precomputed evidence must not be interpreted as live model validation.",
      "No clinical or therapeutic conclusion is implied."
    ]
  });
}
