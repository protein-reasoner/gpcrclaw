"use client"
import React, { useState } from 'react';
import PDBViewer from '@/app/components/PDBViewer';

// List of available pdb files in the public/structures folder
const pdbFiles = [
  '7S8L.pdb',
  '7TD0.pdb',
];

export default function ViewerPage() {
  const [selected, setSelected] = useState(pdbFiles[0]);

  return (
    <div style={{ padding: '2rem', color: '#fff', background: '#111' }}>
      <h1 style={{ marginBottom: '1rem' }}>Protein Structure Viewer</h1>
      <select
        value={selected}
        onChange={(e) => setSelected(e.target.value)}
        style={{ marginBottom: '1rem', padding: '0.5rem' }}
      >
        {pdbFiles.map((file) => (
          <option key={file} value={file}>
            {file}
          </option>
        ))}
      </select>
      <PDBViewer pdbFile={selected} />
    </div>
  );
}
