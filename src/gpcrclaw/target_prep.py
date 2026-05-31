from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from gpcrclaw.worker_contract import WorkerContractError, validate_manifest


AMINO_ACIDS = set("ACDEFGHIKLMNPQRSTVWY")

THREE_LETTER = {
    "A": "ALA",
    "C": "CYS",
    "D": "ASP",
    "E": "GLU",
    "F": "PHE",
    "G": "GLY",
    "H": "HIS",
    "I": "ILE",
    "K": "LYS",
    "L": "LEU",
    "M": "MET",
    "N": "ASN",
    "P": "PRO",
    "Q": "GLN",
    "R": "ARG",
    "S": "SER",
    "T": "THR",
    "V": "VAL",
    "W": "TRP",
    "Y": "TYR",
}


class TargetPrepError(ValueError):
    pass


@dataclass(frozen=True)
class TemplateRecord:
    pdb_id: str
    state: str
    receptor_chain_id: str
    notes: str
    source_url: str
    structure_format: str = "pdb"
    clean_structure_path: str | None = None


@dataclass(frozen=True)
class HotspotSeed:
    residue: str
    exposure: float
    role: str
    evidence: str = "demo-derived"


@dataclass(frozen=True)
class TargetDefinition:
    target_id: str
    name: str
    gene: str
    uniprot_id: str
    protein_class: str
    length_aa: int
    sequence: str
    target_region: str
    ecl2_range: tuple[int, int]
    primary_template: TemplateRecord
    counter_screen_targets: tuple[str, ...]
    hotspot_seeds: tuple[HotspotSeed, ...]
    alias: str | None = None
    native_ligand: str | None = None
    source_urls: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class HotspotRecord:
    residue: str
    position: int
    amino_acid: str
    region: str
    exposure: float
    role: str
    evidence: str
    configured_residue: str
    mapping_status: str
    warnings: tuple[str, ...] = field(default_factory=tuple)


LPAR1_SEQUENCE = (
    "MAAISTSIPVISQPQFTAMNEPQCFYNESIAFFYNRSGKHLATEWNTVSKLVMGLGITVC"
    "IFIMLANLLVMVAIYVNRRFHFPIYYLMANLAAADFFAGLAYFYLMFNTGPNTRRLTVST"
    "WLLRQGLIDTSLTASVANLLAIAIERHITVFRMQLHTRMSNRRVVVVIVVIWTMAIVMGA"
    "IPSVGWNCICDIENCSNMAPLYSDSYLVFWAIFNLVTFVVMVVLYAHIFGYVRQRTMRMS"
    "RHSSGPRRNRDTMMSLLKTVVIVLGAFIICWTPGLVLLLLDVCCPQCDVLAYEKFFLLLA"
    "EFNSAMNPIIYSYRDKEMSATFRQILCCQRSENPTGPTEGSDRSASSLNHTILAGVHSND"
    "HSVV"
)

MRGPRX2_SEQUENCE = (
    "MDPTTPAWGTESTTVNGNDQALLLLCGKETLIPVFLILFIALVGLVGNGFVLWLLGFRMR"
    "RNAFSVYVLSLAGADFLFLCFQIINCLVYLSNFFCSISINFPSFFTTVMTCAYLAGLSML"
    "STVSTERCLSVLWPIWYRCRRPRHLSAVVCVLLWALSLLLSILEGKFCGFLFSDGDSGWC"
    "QTFDFITAAWLIFLFMVLCGSSLALLVRILCGSRGLPLTRLYLTILLTVLVFLLCGLPFG"
    "IQWFLILWIWKDSDVLFCHIHPVSVVLSSLNSSANPIIYFFVGSFRKQWRLQQPILKLAL"
    "QRALQDIAEVDHSEGCFRQGTPEMSRSSLV"
)

TARGETS: dict[str, TargetDefinition] = {
    "LPAR1": TargetDefinition(
        target_id="LPAR1",
        name="Lysophosphatidic acid receptor 1",
        gene="LPAR1",
        alias="EDG2",
        uniprot_id="Q92633",
        protein_class="Class A GPCR, lysophospholipid receptor family",
        length_aa=364,
        sequence=LPAR1_SEQUENCE,
        native_ligand="lysophosphatidic acid (LPA)",
        target_region="ECL2",
        ecl2_range=(188, 211),
        primary_template=TemplateRecord(
            pdb_id="7TD0",
            state="active",
            receptor_chain_id="R",
            notes="LPAR1 + LPA + Gi heterotrimer; receptor-only clean target is prepared for model inputs.",
            source_url="https://www.rcsb.org/structure/7TD0",
            clean_structure_path="/mnt/disks/input/targets/LPAR1_7TD0_clean_target.pdb",
        ),
        counter_screen_targets=("LPAR2", "LPAR3", "LPAR4", "LPAR5", "LPAR6"),
        hotspot_seeds=(
            HotspotSeed("R190", 0.82, "surface exposed ECL2 contact"),
            HotspotSeed("Y194", 0.77, "hydrophobic/aromatic surface"),
            HotspotSeed("D198", 0.69, "polar/charged contact"),
            HotspotSeed("K201", 0.74, "charged surface contact"),
            HotspotSeed("F205", 0.63, "surface aromatic contact"),
        ),
        source_urls=(
            "https://rest.uniprot.org/uniprotkb/Q92633.fasta",
            "https://www.rcsb.org/structure/7TD0",
        ),
    ),
    "MRGPRX2": TargetDefinition(
        target_id="MRGPRX2",
        name="Mas-related G protein-coupled receptor X2",
        gene="MRGPRX2",
        uniprot_id="Q96LB1",
        protein_class="Class A GPCR, Mas-related family",
        length_aa=330,
        sequence=MRGPRX2_SEQUENCE,
        target_region="ECL2",
        ecl2_range=(165, 185),
        primary_template=TemplateRecord(
            pdb_id="7S8L",
            state="active",
            receptor_chain_id="R",
            notes="MRGPRX2 + cortistatin-14 + Gq; receptor-only clean target is prepared for model inputs.",
            source_url="https://www.rcsb.org/structure/7S8L",
            clean_structure_path="/mnt/disks/input/targets/MRGPRX2_7S8L_clean_target.pdb",
        ),
        counter_screen_targets=("MRGPRX1", "MRGPRX3", "MRGPRX4"),
        hotspot_seeds=(
            HotspotSeed("K166", 0.78, "charged exposed contact"),
            HotspotSeed("F170", 0.65, "hydrophobic contact"),
            HotspotSeed("D174", 0.71, "polar/charged contact"),
            HotspotSeed("Y178", 0.68, "aromatic contact"),
        ),
        source_urls=(
            "https://rest.uniprot.org/uniprotkb/Q96LB1.fasta",
            "https://www.rcsb.org/structure/7S8L",
        ),
    ),
}


def available_targets() -> list[str]:
    return sorted(TARGETS)


def get_target_definition(target_id: str) -> TargetDefinition:
    key = target_id.upper()
    try:
        return TARGETS[key]
    except KeyError as exc:
        raise TargetPrepError(f"unknown target_id: {target_id}") from exc


def target_metadata(target_id: str) -> dict[str, Any]:
    target = get_target_definition(target_id)
    metadata = {
        "target_id": target.target_id,
        "name": target.name,
        "gene": target.gene,
        "alias": target.alias,
        "uniprot_id": target.uniprot_id,
        "protein_class": target.protein_class,
        "length_aa": target.length_aa,
        "native_ligand": target.native_ligand,
        "target_region": target.target_region,
        "approx_ecl2_range": list(target.ecl2_range),
        "counter_screen_targets": list(target.counter_screen_targets),
        "source_urls": list(target.source_urls),
    }
    return {key: value for key, value in metadata.items() if value is not None}


def sequence_input(target_id: str) -> dict[str, Any]:
    target = get_target_definition(target_id)
    return {
        "target_id": target.target_id,
        "uniprot_id": target.uniprot_id,
        "sequence": target.sequence,
        "length_aa": len(target.sequence),
        "fasta_header": f">sp|{target.uniprot_id}|{target.target_id}_HUMAN {target.name}",
        "source": "UniProt canonical FASTA",
    }


def template_selection(target_id: str) -> dict[str, Any]:
    target = get_target_definition(target_id)
    template = target.primary_template
    return {
        "target_id": target.target_id,
        "selected_template": template.pdb_id,
        "state": template.state,
        "receptor_chain_id": template.receptor_chain_id,
        "structure_format": template.structure_format,
        "structure_file_url": template.source_url,
        "clean_structure_path": template.clean_structure_path,
        "rationale": template.notes,
    }


def ecl2_mapping(target_id: str) -> dict[str, Any]:
    target = get_target_definition(target_id)
    start, end = target.ecl2_range
    labels = residue_labels(target.sequence, start, end)
    return {
        "target_id": target.target_id,
        "template": target.primary_template.pdb_id,
        "epitope": target.target_region,
        "sequence_residue_range": [start, end],
        "structure_chain_id": target.primary_template.receptor_chain_id,
        "structure_residue_range": [start, end],
        "residue_labels": labels,
        "visualization_selection": f"chain {target.primary_template.receptor_chain_id} and resi {start}-{end}",
        "method": "configured ECL2 range checked against canonical UniProt sequence",
        "mapping_status": "sequence_verified_structure_placeholder",
        "warnings": [
            "Structure residue numbering is assumed to match canonical sequence numbering until mmCIF parsing is implemented."
        ],
    }


def hotspot_records(target_id: str) -> list[dict[str, Any]]:
    target = get_target_definition(target_id)
    start, end = target.ecl2_range
    records = []
    for seed in target.hotspot_seeds:
        configured_aa, position = parse_residue_label(seed.residue)
        if position < start or position > end:
            raise TargetPrepError(f"configured hotspot {seed.residue} is outside {target.target_id} ECL2 range {start}-{end}")
        actual_aa = target.sequence[position - 1]
        actual_residue = f"{actual_aa}{position}"
        warnings: list[str] = []
        mapping_status = "sequence_verified"
        if actual_aa != configured_aa:
            mapping_status = "normalized_from_configured_label"
            warnings.append(
                f"Configured hotspot {seed.residue} maps to {actual_residue} in UniProt {target.uniprot_id}."
            )
        records.append(
            asdict(
                HotspotRecord(
                    residue=actual_residue,
                    position=position,
                    amino_acid=actual_aa,
                    region=target.target_region,
                    exposure=seed.exposure,
                    role=seed.role,
                    evidence=seed.evidence,
                    configured_residue=seed.residue,
                    mapping_status=mapping_status,
                    warnings=tuple(warnings),
                )
            )
        )
    return records


def hotspot_set(target_id: str) -> dict[str, Any]:
    target = get_target_definition(target_id)
    records = hotspot_records(target_id)
    return {
        "target_id": target.target_id,
        "epitope": target.target_region,
        "method": "demo-derived hotspot positions normalized against canonical UniProt sequence",
        "hotspot_residues": [record["residue"] for record in records],
        "records": records,
        "rationale": "Small ECL2 contact set for constrained extracellular nanobody design.",
    }


def target_preparation(target_id: str) -> dict[str, Any]:
    target = get_target_definition(target_id)
    template = target.primary_template
    return {
        "target_id": target.target_id,
        "template_id": template.pdb_id,
        "input_structure": {
            "pdb_id": template.pdb_id,
            "source_url": template.source_url,
            "receptor_chain_id": template.receptor_chain_id,
            "format": template.structure_format,
        },
        "clean_target": {
            "path": template.clean_structure_path,
            "chain_id": template.receptor_chain_id,
            "placeholder": True,
            "contains": ["receptor_chain_only", "ECL2_residue_numbering_reference"],
        },
        "strip_policy": {
            "strip_non_target_chains": True,
            "strip_g_proteins": True,
            "strip_antibodies": True,
            "strip_waters": True,
            "strip_ions": True,
            "native_ligands_as_metadata_only": True,
        },
        "retained_metadata": {
            "native_ligand": target.native_ligand,
            "template_state": template.state,
        },
        "assumptions": [
            "Placeholder clean structures carry residue-numbering references, not atomically valid receptor coordinates.",
            "Native ligands and signaling partners are retained as metadata rather than physical constraints.",
        ],
    }


def structure_warnings(target_id: str) -> dict[str, Any]:
    records = hotspot_records(target_id)
    hotspot_warnings = [warning for record in records for warning in record["warnings"]]
    return {
        "target_id": get_target_definition(target_id).target_id,
        "warnings": [
            "ECL2 sequence positions are verified against canonical sequence, but template residue numbering is not parsed yet.",
            "Clean target PDB files are placeholders until receptor-only mmCIF/PDB extraction is implemented.",
            *hotspot_warnings,
        ],
        "blocking": False,
    }


def worker_target_payload(target_id: str, *, clean_structure_path: str | None = None) -> dict[str, Any]:
    target = get_target_definition(target_id)
    template = target.primary_template
    mapping = ecl2_mapping(target_id)
    hotspots = hotspot_set(target_id)
    structure_path = clean_structure_path or template.clean_structure_path
    return {
        "target_id": target.target_id,
        "gene": target.gene,
        "uniprot_id": target.uniprot_id,
        "epitope": target.target_region,
        "sequence": target.sequence,
        "receptor_sequence": target.sequence,
        "chain_id": template.receptor_chain_id,
        "template_id": template.pdb_id,
        "structure_path": structure_path,
        "receptor_structure_path": structure_path,
        "ecl2_range": mapping["sequence_residue_range"],
        "ecl2_residue_labels": mapping["residue_labels"],
        "hotspot_residues": hotspots["hotspot_residues"],
        "hotspot_records": hotspots["records"],
        "counter_screen_targets": list(target.counter_screen_targets),
        "target_preparation": {
            "clean_target_path": structure_path,
            "strip_policy": target_preparation(target_id)["strip_policy"],
            "warnings": structure_warnings(target_id)["warnings"],
        },
    }


def design_spec(target_id: str, *, num_candidates_to_generate: int | None = None) -> dict[str, Any]:
    target = get_target_definition(target_id)
    default_count = 20 if target.target_id == "LPAR1" else 8
    return {
        "design_job_id": f"{target.target_id}_ECL2_DESIGN_001",
        "target": target.target_id,
        "template": target.primary_template.pdb_id,
        "binder_format": "VHH",
        "scaffold": "camelid_nanobody",
        "cdr3_length_range": [10, 18],
        "hotspot_residues": hotspot_set(target_id)["hotspot_residues"],
        "allowed_contact_regions": ["ECL2", "TM4 flank", "TM5 flank"],
        "forbidden_contact_regions": ["orthosteric pocket", "intracellular face"],
        "num_candidates_to_generate": num_candidates_to_generate or default_count,
        "ranking_objective": "maximize ECL2-specific binding while minimizing cross-reactivity and developability risks",
    }


def target_prep_manifest(target_id: str, *, campaign_id: str | None = None) -> dict[str, Any]:
    target = get_target_definition(target_id)
    return {
        "campaign_id": campaign_id or f"{target.target_id}_TARGET_PREP_EXAMPLE",
        "stage": "target_preparation",
        "evidence_mode": "precomputed",
        "target_metadata": target_metadata(target_id),
        "sequence_input": sequence_input(target_id),
        "template_selection": template_selection(target_id),
        "target_preparation": target_preparation(target_id),
        "ecl2_mapping": ecl2_mapping(target_id),
        "hotspot_set": hotspot_set(target_id),
        "design_spec": design_spec(target_id),
        "worker_target": worker_target_payload(target_id),
        "structure_warnings": structure_warnings(target_id),
    }


def validate_target_definition(target_id: str) -> list[str]:
    target = get_target_definition(target_id)
    warnings = []
    validate_sequence(target.sequence, label=f"{target.target_id} sequence")
    if len(target.sequence) != target.length_aa:
        raise TargetPrepError(f"{target.target_id} length_aa does not match sequence length")
    start, end = target.ecl2_range
    if start < 1 or end > len(target.sequence) or start >= end:
        raise TargetPrepError(f"{target.target_id} ECL2 range is outside sequence bounds")
    for record in hotspot_records(target_id):
        warnings.extend(record["warnings"])
    return warnings


def validate_worker_target_payload(payload: dict[str, Any], *, require_structure_path: bool = True) -> list[str]:
    required = ["target_id", "epitope", "sequence", "ecl2_range", "hotspot_residues"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise TargetPrepError(f"worker target payload missing required keys: {', '.join(missing)}")
    sequence = validate_sequence(str(payload["sequence"]), label="worker target sequence")
    ecl2_range = payload["ecl2_range"]
    if not isinstance(ecl2_range, list) or len(ecl2_range) != 2:
        raise TargetPrepError("worker target ecl2_range must be [start, end]")
    start, end = int(ecl2_range[0]), int(ecl2_range[1])
    if start < 1 or end > len(sequence) or start >= end:
        raise TargetPrepError("worker target ecl2_range is outside sequence bounds")
    expected_ecl2 = set(residue_labels(sequence, start, end))
    labels = payload.get("ecl2_residue_labels")
    if labels is not None and list(labels) != residue_labels(sequence, start, end):
        raise TargetPrepError("worker target ecl2_residue_labels do not match sequence and ecl2_range")
    hotspots = payload["hotspot_residues"]
    if not isinstance(hotspots, list) or not hotspots:
        raise TargetPrepError("worker target hotspot_residues must be a non-empty list")
    for residue in hotspots:
        aa, position = parse_residue_label(str(residue))
        if position < 1 or position > len(sequence) or sequence[position - 1] != aa:
            raise TargetPrepError(f"worker target hotspot {residue} does not match target sequence")
        if str(residue) not in expected_ecl2:
            raise TargetPrepError(f"worker target hotspot {residue} is outside ECL2 range")
    if require_structure_path and not (payload.get("structure_path") or payload.get("receptor_structure_path")):
        raise TargetPrepError("worker target payload requires structure_path or receptor_structure_path")
    warnings = payload.get("target_preparation", {}).get("warnings", [])
    return [str(warning) for warning in warnings]


def validate_candidate_input(
    candidate: dict[str, Any],
    *,
    target_id: str,
    epitope: str = "ECL2",
    sequence_required: bool = True,
    cdr3_length_range: tuple[int, int] = (10, 18),
) -> list[str]:
    if not isinstance(candidate, dict):
        raise TargetPrepError("candidate input must be an object")
    if not candidate.get("candidate_id"):
        raise TargetPrepError("candidate input requires candidate_id")
    candidate_target = candidate.get("target_id") or candidate.get("target")
    if candidate_target is not None and str(candidate_target) != target_id:
        raise TargetPrepError(f"candidate target {candidate_target} does not match manifest target {target_id}")
    candidate_epitope = candidate.get("target_epitope")
    if candidate_epitope is not None and str(candidate_epitope) != epitope:
        raise TargetPrepError(f"candidate epitope {candidate_epitope} does not match target epitope {epitope}")
    sequence = candidate.get("sequence") or candidate.get("binder_sequence") or candidate.get("nanobody_sequence")
    if sequence is None:
        if sequence_required:
            raise TargetPrepError("candidate input requires sequence")
        return []
    sequence_text = validate_sequence(str(sequence), label="candidate sequence")
    cdr3 = candidate.get("cdr3")
    if cdr3 is None:
        if sequence_required:
            raise TargetPrepError("candidate input requires cdr3")
        return []
    cdr3_text = validate_sequence(str(cdr3), label="candidate cdr3")
    low, high = cdr3_length_range
    if len(cdr3_text) < low or len(cdr3_text) > high:
        raise TargetPrepError(f"candidate cdr3 length must be between {low} and {high}")
    if cdr3_text not in sequence_text:
        raise TargetPrepError("candidate cdr3 must be present in candidate sequence")
    return []


def validate_worker_input_manifest(manifest: dict[str, Any]) -> list[str]:
    try:
        validate_manifest(manifest)
    except WorkerContractError as exc:
        raise TargetPrepError(str(exc)) from exc
    target = manifest.get("target")
    if not isinstance(target, dict):
        raise TargetPrepError("manifest target must be an object")
    warnings = validate_worker_target_payload(target)
    candidate = manifest.get("candidate")
    if not isinstance(candidate, dict):
        raise TargetPrepError("manifest candidate must be an object")
    worker_name = str(manifest.get("worker_name", ""))
    sequence_required = worker_name in {"boltz2", "thermompnn"}
    warnings.extend(
        validate_candidate_input(
            candidate,
            target_id=str(target["target_id"]),
            epitope=str(target.get("epitope", "ECL2")),
            sequence_required=sequence_required,
        )
    )
    return warnings


def write_target_prep_artifacts(target_id: str, output_dir: Path) -> dict[str, Path]:
    target = get_target_definition(target_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "target_metadata": output_dir / "target_metadata.json",
        "template_selection": output_dir / "template_selection.json",
        "target_preparation": output_dir / "target_preparation.json",
        "clean_target": output_dir / f"{target.target_id}_{target.primary_template.pdb_id}_clean_target.pdb",
        "hotspot_set": output_dir / "hotspot_set.json",
        "structure_warnings": output_dir / "structure_warnings.json",
        "worker_target": output_dir / "worker_target.json",
        "sequence_fasta": output_dir / f"{target.target_id}.fasta",
    }
    write_json(paths["target_metadata"], target_metadata(target_id))
    write_json(paths["template_selection"], template_selection(target_id))
    write_json(paths["target_preparation"], target_preparation(target_id))
    write_json(paths["hotspot_set"], hotspot_set(target_id))
    write_json(paths["structure_warnings"], structure_warnings(target_id))
    write_json(paths["worker_target"], worker_target_payload(target_id, clean_structure_path=str(paths["clean_target"])))
    paths["sequence_fasta"].write_text(format_fasta(target), encoding="utf-8")
    paths["clean_target"].write_text(render_placeholder_pdb(target_id), encoding="utf-8")
    return paths


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_placeholder_pdb(target_id: str) -> str:
    target = get_target_definition(target_id)
    records = hotspot_records(target_id)
    lines = [
        f"HEADER    GPCRCLAW CLEAN TARGET PLACEHOLDER        {target.target_id}",
        f"REMARK 900 TEMPLATE {target.primary_template.pdb_id} CHAIN {target.primary_template.receptor_chain_id}",
        "REMARK 900 PLACEHOLDER FOR TARGET-PREP CONTRACT TESTING; NOT ATOMIC COORDINATES",
    ]
    for index, record in enumerate(records, start=1):
        residue_name = THREE_LETTER[record["amino_acid"]]
        position = int(record["position"])
        x = 10.0 + index
        y = 2.5 * index
        z = -1.5 * index
        lines.append(
            f"ATOM  {index:5d}  CA  {residue_name} {target.primary_template.receptor_chain_id}{position:4d}"
            f"    {x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00           C"
        )
    lines.extend(["TER", "END"])
    return "\n".join(lines) + "\n"


def format_fasta(target: TargetDefinition) -> str:
    header = f">sp|{target.uniprot_id}|{target.target_id}_HUMAN {target.name}"
    chunks = [target.sequence[index : index + 60] for index in range(0, len(target.sequence), 60)]
    return header + "\n" + "\n".join(chunks) + "\n"


def residue_labels(sequence: str, start: int, end: int) -> list[str]:
    return [f"{sequence[position - 1]}{position}" for position in range(start, end + 1)]


def parse_residue_label(label: str) -> tuple[str, int]:
    text = label.strip().upper()
    if len(text) < 2 or text[0] not in AMINO_ACIDS or not text[1:].isdigit():
        raise TargetPrepError(f"invalid residue label: {label}")
    return text[0], int(text[1:])


def validate_sequence(sequence: str, *, label: str) -> str:
    cleaned = "".join(sequence.split()).upper()
    if not cleaned:
        raise TargetPrepError(f"{label} must not be empty")
    invalid = sorted(set(cleaned) - AMINO_ACIDS)
    if invalid:
        raise TargetPrepError(f"{label} contains invalid amino acid symbols: {', '.join(invalid)}")
    return cleaned
