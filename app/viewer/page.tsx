"use client";

import React, { useState, useEffect, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft, HelpCircle } from "lucide-react";
import PDBViewer from "@/app/components/PDBViewer";

// Available PDB structures (public/structures)
const pdbFiles = [
  { id: "7TD0.pdb", label: "LPAR1 Active State (7TD0) - Iteration 1 Model", key: "LPAR1" },
  { id: "7S8L.pdb", label: "MRGPRX2 Active State (7S8L) - Iteration 1 Model", key: "MRGPRX2" }
];

function ViewerContent() {
  const searchParams = useSearchParams();
  const [selected, setSelected] = useState(pdbFiles[0].id);

  useEffect(() => {
    const proteinParam = searchParams.get("protein")?.toUpperCase();
    if (proteinParam) {
      const match = pdbFiles.find(f => f.key === proteinParam || f.id.toUpperCase().startsWith(proteinParam));
      if (match) {
        setSelected(match.id);
      }
    }
  }, [searchParams]);

  return (
    <div style={{
      background: "#090d16",
      color: "#f8fafc",
      minHeight: "100vh",
      display: "flex",
      flexDirection: "column",
      fontFamily: "Inter, sans-serif"
    }}>
      <header style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "1.25rem 2rem",
        borderBottom: "1px solid #1e293b",
        background: "#0f172a"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "1.5rem" }}>
          <Link href="/" style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            color: "#94a3b8",
            textDecoration: "none",
            fontSize: "0.9rem",
            fontWeight: 600,
            transition: "color 0.2s"
          }}
          >
            <ArrowLeft size={16} /> Back to Dashboard
          </Link>
          <span style={{ color: "#334155" }}>|</span>
          <h1 style={{ fontSize: "1.2rem", fontWeight: 700, margin: 0, letterSpacing: "-0.02em" }}>
            GPCRclaw Structure Viewer
          </h1>
        </div>
        <div style={{
          fontSize: "0.85rem",
          color: "#94a3b8",
          background: "#1e293b",
          padding: "0.5rem 1rem",
          borderRadius: "9999px",
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          border: "1px solid #334155"
        }}>
          <HelpCircle size={14} color="#38bdf8" />
          <span>Protein structure is from our <strong>1st iteration of drug discovery model</strong>.</span>
        </div>
      </header>

      <main style={{
        flex: 1,
        display: "grid",
        gridTemplateColumns: "320px 1fr",
        overflow: "hidden"
      }}>
        {/* Sidebar Controls */}
        <div style={{
          background: "#0f172a",
          padding: "2rem",
          borderRight: "1px solid #1e293b",
          display: "flex",
          flexDirection: "column",
          gap: "2rem"
        }}>
          <div>
            <h2 style={{ fontSize: "0.85rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "#64748b", margin: "0 0 0.75rem 0" }}>
              Active Structure Template
            </h2>
            <div style={{ position: "relative" }}>
              <select
                id="pdb-select"
                value={selected}
                onChange={(e) => setSelected(e.target.value)}
                style={{
                  width: "100%",
                  background: "#1e293b",
                  color: "#f8fafc",
                  padding: "0.75rem 1rem",
                  borderRadius: "8px",
                  border: "1px solid #334155",
                  fontSize: "0.9rem",
                  fontWeight: 500,
                  cursor: "pointer",
                  appearance: "none",
                  outline: "none"
                }}
              >
                {pdbFiles.map((file) => (
                  <option key={file.id} value={file.id}>
                    {file.label}
                  </option>
                ))}
              </select>
              <div style={{
                position: "absolute",
                right: "1rem",
                top: "50%",
                transform: "translateY(-50%)",
                pointerEvents: "none",
                color: "#64748b"
              }}>
                ▼
              </div>
            </div>
          </div>

          <div style={{
            background: "rgba(30, 41, 59, 0.5)",
            border: "1px solid #1e293b",
            borderRadius: "8px",
            padding: "1.25rem",
            fontSize: "0.85rem",
            lineHeight: 1.6,
            color: "#94a3b8"
          }}>
            <strong style={{ color: "#f8fafc", display: "block", marginBottom: "0.5rem" }}>Viewer Information</strong>
            This interactive 3D viewer displays isolated GPCR receptors generated during model execution. You can click and drag to rotate, and scroll to zoom.
          </div>
        </div>

        {/* Clean 3D view container */}
        <div style={{
          background: "#090d16",
          padding: "2rem",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center"
        }}>
          <div style={{
            width: "100%",
            height: "100%",
            background: "#0f172a",
            borderRadius: "16px",
            boxShadow: "0 20px 25px -5px rgb(0 0 0 / 0.5), 0 8px 10px -6px rgb(0 0 0 / 0.5)",
            position: "relative",
            overflow: "hidden",
            display: "flex",
            flexDirection: "column"
          }}>
            <div style={{
              position: "absolute",
              top: "1.25rem",
              left: "1.25rem",
              zIndex: 10,
              background: "rgba(15, 23, 42, 0.8)",
              backdropFilter: "blur(4px)",
              padding: "0.5rem 1rem",
              borderRadius: "6px",
              border: "1px solid #1e293b",
              fontSize: "0.8rem",
              fontWeight: 600,
              color: "#38bdf8"
            }}>
              Active ID: {selected}
            </div>
            <div style={{ flex: 1, minHeight: "550px" }}>
              <PDBViewer pdbFile={selected} />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default function ViewerPage() {
  return (
    <Suspense fallback={<div style={{ padding: "2rem", color: "#fff", background: "#090d16" }}>Loading viewer...</div>}>
      <ViewerContent />
    </Suspense>
  );
}
