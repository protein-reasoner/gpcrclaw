"use client";
import { useEffect, useRef } from 'react';

interface PDBViewerProps {
  pdbFile: string; // relative path under /public, e.g., 'structures/7S8L.pdb'
}

const PDBViewer: React.FC<PDBViewerProps> = ({ pdbFile }) => {
  const viewerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Ensure code runs only in the browser
    if (typeof window === 'undefined' || !viewerRef.current) return;

    let viewer: any;
    // Dynamically import 3Dmol on the client side
    import('3dmol').then((module) => {
      const $3Dmol = module.default || module;
      viewer = $3Dmol.createViewer(viewerRef.current, { backgroundColor: '0x000000' });
      // Load the PDB file from the public structures folder
      fetch(`/structures/${pdbFile}`)
        .then((res) => res.text())
        .then((pdbData) => {
          viewer.addModel(pdbData, 'pdb');
          viewer.setStyle({}, { cartoon: { color: 'spectrum' } });
          viewer.zoomTo();
          viewer.render();
        })
        .catch((err) => console.error('Failed to load PDB:', err));
    });

    return () => {
      if (viewer) viewer.clear();
    };
  }, [pdbFile]);

  return (
    <div
      ref={viewerRef}
      style={{ width: '100%', height: '600px', border: '1px solid #444' }}
    />
  );
};

export default PDBViewer;
