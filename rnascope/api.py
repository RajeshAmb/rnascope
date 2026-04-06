"""FastAPI application — REST API for upload, pipeline, chat, graphs, WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from rnascope.agents.chat import ChatAgent
from rnascope.config import settings
from rnascope.infra.checkpoint import get_job_state, save_job_state

logger = logging.getLogger(__name__)

api_app = FastAPI(title="RNAscope", version="1.0.0")

api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory stores
_chat_sessions: dict[str, ChatAgent] = {}
_active_websockets: dict[str, list[WebSocket]] = {}

# Upload temp dir
UPLOAD_DIR = Path(os.environ.get("RNASCOPE_UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Persistent job store — survives server restarts
_JOBS_DIR = UPLOAD_DIR / ".jobs"
_JOBS_DIR.mkdir(parents=True, exist_ok=True)


class _PersistentJobStore:
    """Dict-like store that persists each job as a JSON file on disk."""

    def __init__(self, directory: Path):
        self._dir = directory

    def _path(self, job_id: str) -> Path:
        return self._dir / f"{job_id}.json"

    def __contains__(self, job_id: str) -> bool:
        return self._path(job_id).exists()

    def get(self, job_id: str, default=None):
        try:
            return self[job_id]
        except KeyError:
            # Fallback to Redis for recovery
            try:
                from rnascope.infra.checkpoint import get_job_state
                state = get_job_state(job_id)
                if state:
                    self[job_id] = state # Restore to local disk
                    return state
            except Exception:
                pass
            return default

    def __getitem__(self, job_id: str) -> dict:
        p = self._path(job_id)
        if not p.exists():
            # Check Redis before failing
            try:
                from rnascope.infra.checkpoint import get_job_state
                state = get_job_state(job_id)
                if state:
                    self[job_id] = state # Restore to local disk
                    return state
            except Exception:
                pass
            raise KeyError(job_id)
        return json.loads(p.read_text(encoding="utf-8"))

    def __setitem__(self, job_id: str, state: dict):
        self._path(job_id).write_text(json.dumps(state), encoding="utf-8")
        # Sync to Redis for persistence across restarts/workers
        try:
            from rnascope.infra.checkpoint import save_job_state
            save_job_state(job_id, state)
        except Exception as e:
            logger.warning("Failed to sync job %s to Redis: %s", job_id, e)

    def __contains__(self, job_id: str) -> bool:
        if self._path(job_id).exists():
            return True
        # Check Redis
        try:
            from rnascope.infra.checkpoint import get_job_state
            return get_job_state(job_id) is not None
        except Exception:
            return False

    def items(self):
        for p in self._dir.glob("*.json"):
            job_id = p.stem
            try:
                yield job_id, json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue


_jobs_store = _PersistentJobStore(_JOBS_DIR)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    job_id: str
    question: str


class ChatResponse(BaseModel):
    job_id: str
    answer: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    project_name: str = ""
    species: str = ""
    condition_a: str = ""
    condition_b: str = ""
    n_samples: int = 0
    dataset_size_gb: float = 0.0
    current_step: str | None = None
    steps_completed: list[str] = []
    total_steps: int = 11
    pct_complete: float = 0.0
    cost_so_far_usd: float = 0.0
    created_at: str = ""
    eta_minutes: float = 0.0


class JobCreateRequest(BaseModel):
    project_name: str
    species: str = "human"
    condition_a: str
    condition_b: str
    n_a: int
    n_b: int
    tissue_type: str = ""
    disease_context: str = ""
    email: str = ""
    slack_channel: str = ""


# ---------------------------------------------------------------------------
# Species-specific gene/pathway banks for dynamic demo data
# ---------------------------------------------------------------------------

_SPECIES_GENES = {
    "human": [
        "IL1B", "TNF", "CXCL8", "MMP9", "DEFB4A", "CCL2", "IL6", "CLDN8",
        "MUC2", "TFF3", "AQP8", "SLC26A3", "DUOX2", "LCN2", "S100A8",
        "S100A9", "CXCL1", "IFNG", "NOS2", "IDO1", "GBP1", "HLA-DRA",
        "CD74", "FCGR3A", "MMP3", "SERPINB3", "KRT16", "FABP4", "PPARG",
        "FASN", "HMGCR", "PCK1", "APOA1", "CYP3A4", "ALB", "CRP", "SAA1",
        "COL1A1", "FN1", "ACTA2", "TGFB1", "VEGFA", "PDGFRA", "PECAM1",
        "CDH5", "VWF", "ICAM1", "CD4", "CD8A", "FOXP3", "GZMB", "PDCD1",
    ],
    "mouse": [
        "Il1b", "Tnf", "Cxcl2", "Mmp9", "Ccl2", "Il6", "Cldn8", "Muc2",
        "Tff3", "Duox2", "Lcn2", "S100a8", "S100a9", "Ifng", "Nos2",
        "Gbp1", "H2-Aa", "Cd74", "Mmp3", "Krt16", "Fabp4", "Pparg",
        "Fasn", "Hmgcr", "Pck1", "Alb", "Crp", "Col1a1", "Fn1", "Acta2",
        "Tgfb1", "Vegfa", "Pecam1", "Cdh5", "Icam1", "Cd4", "Cd8a",
        "Foxp3", "Gzmb", "Pdcd1", "Ctla4", "Lag3", "Arg1", "Chil3",
        "Retnla", "Clec4e", "Irf7", "Isg15", "Mx1", "Oas2", "Stat1",
    ],
    "arabidopsis": [
        "AT1G01010", "RD29A", "COR15A", "DREB2A", "CBF1", "CBF2", "CBF3",
        "LEA14", "RAB18", "PR1", "PR2", "PR5", "PDF1.2", "ERF1", "PAD4",
        "EDS1", "NPR1", "WRKY33", "WRKY40", "MYB51", "CYP79B2", "CYP71A13",
        "AOS", "LOX2", "JAZ1", "JAZ10", "COI1", "MYC2", "ABI1", "ABI5",
        "NCED3", "AAO3", "PYR1", "PYL4", "SnRK2.6", "RbohD", "SLAC1",
        "KAT1", "NHX1", "SOS1", "HKT1", "RD22", "COR47", "KIN1", "LTI78",
        "CAB1", "RBCS1A", "PSBA", "LHCB1", "RCA", "SUS1", "INV1",
    ],
    "rice": [
        "LOC_Os01g01010", "OsDREB1A", "OsDREB2A", "OsNAC9", "OsWRKY45",
        "OsWRKY71", "OsMYB4", "OsLEA3", "OsP5CS", "OsNHX1", "OsSOS1",
        "OsHKT1", "OsCIPK15", "OsSAPK2", "OsPR1a", "OsPR10", "OsNPR1",
        "OsWRKY13", "OsCHS", "OsPAL", "Os4CL", "OsF3H", "OsDFR",
        "OsGSTU4", "OsCAT", "OsSOD", "OsAPX2", "OsRbohB", "OsSWEET11",
        "OsSWEET14", "OsXa21", "OsXa13", "OsPi9", "OsPi21", "OsPi54",
        "OsSPL14", "OsGW2", "OsGS3", "OsGn1a", "OsDEP1", "OsSd1",
        "OsWaxy", "OsSSI", "OsSSIIa", "OsAGPL2", "OsPHO1", "OsPT2",
        "OsAMT1", "OsNRT2.1", "OsNiR", "OsGS1", "OsFd-GOGAT",
    ],
    "tomato": [
        "Solyc01g005000", "SlPR1", "SlPR2", "SlPR5", "SlNPR1", "SlWRKY33",
        "SlERF1", "SlJAZ1", "SlMYC2", "SlAOS", "SlLOX2", "SlPIN2",
        "SlDEF2", "SlPAL5", "SlCHS2", "SlF3H", "SlDFR", "SlANS",
        "SlPSY1", "SlPDS", "SlZDS", "SlLCYB", "SlCRTISO", "SlCYP97A29",
        "SlRIN", "SlCNR", "SlNOR", "SlACS2", "SlACS4", "SlACO1",
        "SlETR3", "SlPG2A", "SlEXP1", "SlCEL2", "SlTBG4", "SlPME",
        "SlSWEET1a", "SlHT1", "SlLIN5", "SlSUS1", "SlFRK1", "SlSPS",
        "SlFW2.2", "SlSP", "SlSP5G", "SlSFT", "SlS", "SlLC", "SlFAS",
        "SlENO", "SlClV", "SlGLK2",
    ],
    "maize": [
        "Zm00001eb000010", "ZmVP14", "ZmNCED", "ZmDREB2A", "ZmNAC111",
        "ZmWRKY33", "ZmMYB31", "ZmLEA3", "ZmP5CS", "ZmNHX1", "ZmSOS1",
        "ZmHKT1", "ZmPR1", "ZmPR10", "ZmCHS", "ZmPAL", "ZmBx1",
        "ZmBx2", "ZmF3H", "ZmDFR", "ZmGSTU", "ZmCAT", "ZmSOD",
        "ZmSWEET13a", "ZmSUT1", "ZmINCW2", "ZmSh2", "ZmBt2", "ZmWaxy",
        "ZmSU1", "ZmAE1", "ZmO2", "ZmFL2", "ZmZein", "ZmSSIII",
        "ZmTb1", "ZmGt1", "ZmVgt1", "ZmRA1", "ZmTS1", "ZmSK1",
        "ZmCCT9", "ZmLG1", "ZmBA1", "ZmKN1", "ZmYAB", "ZmAN1",
        "ZmBIF2", "ZmFEA2", "ZmCLE7", "ZmWUS", "ZmID1",
    ],
    "ecoli": [
        "dnaA", "gyrB", "thrA", "thrB", "thrC", "lacZ", "lacY", "lacA",
        "rpoB", "rpoC", "rpoA", "rpoD", "ftsZ", "murA", "murB",
        "recA", "lexA", "uvrA", "uvrB", "polA", "ompA", "ompC", "ompF",
        "sodA", "sodB", "katG", "katE", "oxyR", "soxS", "arcA", "fnr",
        "crp", "ihfA", "hns", "fis", "rpoS", "cspA", "groEL", "dnaK",
        "clpB", "lon", "rpoH", "flhD", "fliC", "motA", "cheA", "cheY",
        "acs", "aceA", "aceB", "icd", "sdhA", "sucA",
    ],
    "yeast": [
        "ACT1", "TDH3", "ENO2", "PGK1", "ADH1", "ADH2", "PDC1",
        "HXK2", "GLK1", "PFK1", "PFK2", "FBP1", "PYK1", "PYK2",
        "CIT1", "ACO1", "IDH1", "KGD1", "SDH1", "FUM1", "MDH1",
        "GDH1", "GLN1", "ASN1", "MET6", "SAM1", "LEU2", "HIS3",
        "TRP1", "URA3", "LYS2", "ADE2", "CDC28", "CLN1", "CLN2",
        "CLB1", "CLB2", "SIC1", "SWI4", "SWI6", "MBP1", "SSN6",
        "TUP1", "GAL4", "GCN4", "HAP4", "MSN2", "MSN4", "HSF1",
        "YAP1", "SKN7", "SOD1",
    ],
    "cotton": [
        "GhPR1", "GhPR5", "GhNPR1", "GhWRKY40", "GhWRKY70", "GhERF1",
        "GhMYB36", "GhJAZ1", "GhPAL", "GhCHS", "GhF3H", "GhDFR",
        "GhCAD", "GhCCoAOMT", "GhCOMT", "GhLAC", "GhPOD", "GhSOD",
        "GhCAT", "GhAPX", "GhGST", "GhHSP70", "GhHSP90", "GhLEA",
        "GhRD22", "GhNAC", "GhDREB", "GhP5CS", "GhNHX1", "GhSOS1",
        "GhSWEET", "GhSUT", "GhINV", "GhSUS", "GhCesA", "GhExpA",
        "GhXTH", "GhPME", "GhPG", "GhGhPEL", "GhMYB109", "GhMYB25",
        "GhHD1", "GhACO", "GhACS", "GhETR", "GhEIN2", "GhCTR1",
        "GhGID1", "GhDELLA", "GhARF", "GhAux/IAA",
    ],
    "cotton_arboreum": [
        "GaPR1", "GaPR5", "GaNPR1", "GaWRKY40", "GaWRKY70", "GaERF1",
        "GaMYB36", "GaJAZ1", "GaPAL", "GaCHS", "GaF3H", "GaDFR",
        "GaCAD", "GaCCoAOMT", "GaCOMT", "GaLAC", "GaPOD", "GaSOD",
        "GaCAT", "GaAPX", "GaGST", "GaHSP70", "GaHSP90", "GaLEA",
        "GaRD22", "GaNAC", "GaDREB", "GaP5CS", "GaNHX1", "GaSOS1",
        "GaSWEET", "GaSUT", "GaINV", "GaSUS", "GaCesA", "GaExpA",
        "GaXTH", "GaPME", "GaPG", "GaPEL", "GaMYB109", "GaMYB25",
        "GaHD1", "GaACO", "GaACS", "GaETR", "GaEIN2", "GaCTR1",
        "GaGID1", "GaDELLA", "GaARF", "GaAux/IAA",
    ],
}

_SPECIES_GO_TERMS = {
    "plant": [
        {"term": "response to water deprivation", "source": "GO_BP", "count": 18, "gene_ratio": 0.14},
        {"term": "response to abscisic acid", "source": "GO_BP", "count": 22, "gene_ratio": 0.17},
        {"term": "defense response to bacterium", "source": "GO_BP", "count": 15, "gene_ratio": 0.12},
        {"term": "jasmonic acid mediated signaling", "source": "GO_BP", "count": 12, "gene_ratio": 0.09},
        {"term": "salicylic acid mediated signaling", "source": "GO_BP", "count": 10, "gene_ratio": 0.08},
        {"term": "flavonoid biosynthetic process", "source": "GO_BP", "count": 8, "gene_ratio": 0.06},
        {"term": "photosynthesis", "source": "GO_BP", "count": 14, "gene_ratio": 0.11},
        {"term": "cell wall organization", "source": "GO_BP", "count": 16, "gene_ratio": 0.12},
        {"term": "response to cold", "source": "GO_BP", "count": 11, "gene_ratio": 0.09},
        {"term": "chloroplast", "source": "GO_CC", "count": 28, "gene_ratio": 0.22},
        {"term": "apoplast", "source": "GO_CC", "count": 14, "gene_ratio": 0.11},
        {"term": "transcription factor activity", "source": "GO_MF", "count": 20, "gene_ratio": 0.15},
        {"term": "kinase activity", "source": "GO_MF", "count": 13, "gene_ratio": 0.10},
    ],
    "animal": [
        {"term": "inflammatory response", "source": "GO_BP", "count": 24, "gene_ratio": 0.18},
        {"term": "immune system process", "source": "GO_BP", "count": 31, "gene_ratio": 0.24},
        {"term": "cytokine-mediated signaling", "source": "GO_BP", "count": 18, "gene_ratio": 0.14},
        {"term": "defense response to bacterium", "source": "GO_BP", "count": 12, "gene_ratio": 0.09},
        {"term": "leukocyte migration", "source": "GO_BP", "count": 14, "gene_ratio": 0.11},
        {"term": "extracellular matrix organization", "source": "GO_BP", "count": 16, "gene_ratio": 0.12},
        {"term": "cell adhesion", "source": "GO_BP", "count": 20, "gene_ratio": 0.15},
        {"term": "response to lipopolysaccharide", "source": "GO_BP", "count": 9, "gene_ratio": 0.07},
        {"term": "positive regulation of NF-kB", "source": "GO_BP", "count": 11, "gene_ratio": 0.08},
        {"term": "receptor binding", "source": "GO_MF", "count": 22, "gene_ratio": 0.17},
        {"term": "cytokine activity", "source": "GO_MF", "count": 13, "gene_ratio": 0.10},
        {"term": "extracellular region", "source": "GO_CC", "count": 28, "gene_ratio": 0.22},
        {"term": "plasma membrane", "source": "GO_CC", "count": 35, "gene_ratio": 0.27},
    ],
    "microbe": [
        {"term": "metabolic process", "source": "GO_BP", "count": 30, "gene_ratio": 0.23},
        {"term": "oxidation-reduction process", "source": "GO_BP", "count": 18, "gene_ratio": 0.14},
        {"term": "transmembrane transport", "source": "GO_BP", "count": 15, "gene_ratio": 0.12},
        {"term": "DNA repair", "source": "GO_BP", "count": 8, "gene_ratio": 0.06},
        {"term": "response to stress", "source": "GO_BP", "count": 12, "gene_ratio": 0.09},
        {"term": "cell division", "source": "GO_BP", "count": 10, "gene_ratio": 0.08},
        {"term": "translation", "source": "GO_BP", "count": 20, "gene_ratio": 0.15},
        {"term": "catalytic activity", "source": "GO_MF", "count": 25, "gene_ratio": 0.19},
        {"term": "ATP binding", "source": "GO_MF", "count": 22, "gene_ratio": 0.17},
        {"term": "cytoplasm", "source": "GO_CC", "count": 35, "gene_ratio": 0.27},
        {"term": "ribosome", "source": "GO_CC", "count": 16, "gene_ratio": 0.12},
        {"term": "membrane", "source": "GO_CC", "count": 28, "gene_ratio": 0.22},
        {"term": "periplasmic space", "source": "GO_CC", "count": 10, "gene_ratio": 0.08},
    ],
}

_SPECIES_KEGG = {
    "plant": [
        {"pathway": "Plant hormone signal transduction", "direction": "up"},
        {"pathway": "MAPK signaling — plant", "direction": "up"},
        {"pathway": "Phenylpropanoid biosynthesis", "direction": "up"},
        {"pathway": "Flavonoid biosynthesis", "direction": "up"},
        {"pathway": "Plant-pathogen interaction", "direction": "up"},
        {"pathway": "Photosynthesis", "direction": "down"},
        {"pathway": "Carbon fixation in photosynthetic organisms", "direction": "down"},
        {"pathway": "Starch and sucrose metabolism", "direction": "down"},
        {"pathway": "Nitrogen metabolism", "direction": "down"},
        {"pathway": "Carotenoid biosynthesis", "direction": "down"},
    ],
    "animal": [
        {"pathway": "Cytokine-cytokine receptor interaction", "direction": "up"},
        {"pathway": "TNF signaling pathway", "direction": "up"},
        {"pathway": "NF-kappa B signaling pathway", "direction": "up"},
        {"pathway": "IL-17 signaling pathway", "direction": "up"},
        {"pathway": "JAK-STAT signaling pathway", "direction": "up"},
        {"pathway": "NOD-like receptor signaling", "direction": "up"},
        {"pathway": "Tight junction", "direction": "down"},
        {"pathway": "Metabolic pathways", "direction": "down"},
        {"pathway": "Drug metabolism", "direction": "down"},
        {"pathway": "Fat digestion and absorption", "direction": "down"},
    ],
    "microbe": [
        {"pathway": "TCA cycle", "direction": "up"},
        {"pathway": "Oxidative phosphorylation", "direction": "up"},
        {"pathway": "Amino acid biosynthesis", "direction": "up"},
        {"pathway": "Ribosome", "direction": "up"},
        {"pathway": "ABC transporters", "direction": "up"},
        {"pathway": "Glycolysis / Gluconeogenesis", "direction": "down"},
        {"pathway": "Fatty acid biosynthesis", "direction": "down"},
        {"pathway": "Peptidoglycan biosynthesis", "direction": "down"},
        {"pathway": "Flagellar assembly", "direction": "down"},
        {"pathway": "Two-component system", "direction": "down"},
    ],
}


def _get_domain(species: str) -> str:
    """Get domain category for a species."""
    plants = {"arabidopsis", "rice", "maize", "wheat", "tomato", "soybean", "potato", "grape", "cotton", "cotton_arboreum"}
    microbes = {"ecoli", "yeast", "aspergillus", "lactobacillus", "metatranscriptome"}
    if species in plants:
        return "plant"
    if species in microbes:
        return "microbe"
    return "animal"


# ---------------------------------------------------------------------------
# Dynamic demo data generator — species-aware
# ---------------------------------------------------------------------------

def _generate_demo_results(job_id: str, species: str = "human",
                           condition_a: str = "Treatment", condition_b: str = "Control",
                           n_a: int = 3, n_b: int = 3) -> dict:
    """Generate realistic demo RNA-seq results dynamically based on species."""
    import math
    import random

    random.seed(hash(job_id) % 2**32)

    domain = _get_domain(species)
    n_samples = n_a + n_b

    # Get species-specific gene names (or fallback to human)
    gene_names = _SPECIES_GENES.get(species, _SPECIES_GENES["human"])[:100]

    volcano_data = []
    for gene in gene_names:
        fc = random.gauss(0, 2.5)
        pval = 10 ** (-random.expovariate(0.3))
        pval = min(pval, 1.0)
        neg_log10p = -math.log10(max(pval, 1e-300))
        sig = abs(fc) > 1 and pval < 0.05
        volcano_data.append({
            "gene": gene,
            "log2fc": round(fc, 3),
            "neg_log10_pvalue": round(neg_log10p, 2),
            "pvalue": pval,
            "fdr": round(min(pval * len(gene_names) / 10, 1.0), 6),
            "significant": sig,
            "direction": "up" if fc > 1 and sig else ("down" if fc < -1 and sig else "ns"),
        })

    # PCA data — dynamic sample count and conditions
    pca_data = []
    for i in range(n_samples):
        cond = condition_a if i < n_a else condition_b
        cx = random.gauss(20 if i < n_a else -20, 8)
        cy = random.gauss(5, 10)
        pca_data.append({
            "sample": f"S{i+1:02d}",
            "condition": cond,
            "pc1": round(cx, 2),
            "pc2": round(cy, 2),
        })

    # Heatmap: top 30 DE genes x samples, z-score normalized
    top_genes = sorted(volcano_data, key=lambda g: -abs(g["log2fc"]))[:30]
    heatmap_data = {
        "genes": [g["gene"] for g in top_genes],
        "samples": [p["sample"] for p in pca_data],
        "conditions": [p["condition"] for p in pca_data],
        "matrix": [
            [round(random.gauss(1.5 if j < n_a else -1.5, 0.8) * (1 if g["log2fc"] > 0 else -1), 2)
             for j in range(n_samples)]
            for g in top_genes
        ],
    }

    # GO enrichment — species-domain specific
    go_template = _SPECIES_GO_TERMS.get(domain, _SPECIES_GO_TERMS["animal"])
    go_terms = []
    for t in go_template:
        pval = 10 ** (-random.uniform(3, 12))
        go_terms.append({
            **t,
            "pvalue": pval,
            "neg_log10_pvalue": round(-math.log10(pval), 2),
        })

    # KEGG pathways — species-domain specific
    kegg_template = _SPECIES_KEGG.get(domain, _SPECIES_KEGG["animal"])
    kegg_pathways = []
    for p in kegg_template:
        pval = 10 ** (-random.uniform(2, 9))
        kegg_pathways.append({
            "pathway": p["pathway"],
            "count": random.randint(5, 22),
            "pvalue": pval,
            "neg_log10_pvalue": round(-math.log10(pval), 2),
            "direction": p["direction"],
        })

    # QC summary
    qc_summary = {
        "total_samples": n_samples,
        "total_reads_m": round(random.uniform(180, 250), 1),
        "avg_q30": round(random.uniform(92, 97), 1),
        "avg_mapping_rate": round(random.uniform(85, 95), 1),
        "avg_duplication": round(random.uniform(15, 30), 1),
        "avg_rrna_pct": round(random.uniform(2, 8), 1),
        "flagged_samples": 0,
        "samples": [
            {
                "sample": f"S{i+1:02d}",
                "condition": condition_a if i < n_a else condition_b,
                "total_reads_m": round(random.uniform(28, 45), 1),
                "q30_pct": round(random.uniform(91, 98), 1),
                "mapping_rate": round(random.uniform(84, 96), 1),
                "duplication_pct": round(random.uniform(12, 35), 1),
                "rrna_pct": round(random.uniform(1.5, 10), 1),
                "passed": True,
            }
            for i in range(n_samples)
        ],
    }

    # DEG summary
    n_up = sum(1 for g in volcano_data if g["direction"] == "up")
    n_down = sum(1 for g in volcano_data if g["direction"] == "down")
    deg_summary = {
        "total_tested": len(volcano_data),
        "significant": n_up + n_down,
        "upregulated": n_up,
        "downregulated": n_down,
        "fdr_threshold": 0.05,
        "fc_threshold": 1.0,
    }

    # Biotype distribution
    biotypes = [
        {"biotype": "protein_coding", "count": 14832, "pct": 62.3},
        {"biotype": "lncRNA", "count": 5621, "pct": 23.6},
        {"biotype": "processed_pseudogene", "count": 1543, "pct": 6.5},
        {"biotype": "snRNA", "count": 834, "pct": 3.5},
        {"biotype": "miRNA", "count": 421, "pct": 1.8},
        {"biotype": "snoRNA", "count": 312, "pct": 1.3},
        {"biotype": "misc_RNA", "count": 238, "pct": 1.0},
    ]

    # AI interpretation — dynamic based on actual genes and species
    top3_up = [g["gene"] for g in sorted(volcano_data, key=lambda x: -x["log2fc"]) if g["significant"]][:3]
    top3_down = [g["gene"] for g in sorted(volcano_data, key=lambda x: x["log2fc"]) if g["significant"]][:3]
    top_pathway = kegg_pathways[0]["pathway"] if kegg_pathways else "unknown"

    interpretation = {
        "executive_summary": (
            f"Comparison of {condition_a} vs {condition_b} in {species} reveals {n_up + n_down} "
            f"differentially expressed genes (FDR < 0.05, |log2FC| > 1), with {n_up} upregulated "
            f"and {n_down} downregulated. The dominant biological theme is {top_pathway}. "
            f"Top upregulated genes include {', '.join(top3_up) if top3_up else 'N/A'}, "
            f"while top downregulated include {', '.join(top3_down) if top3_down else 'N/A'}."
        ),
        "top_hypotheses": [
            {
                "id": "H1",
                "hypothesis": f"The {top_pathway} pathway is the primary transcriptional response in {condition_a}.",
                "rationale": f"{top3_up[0] if top3_up else 'Top gene'} and related genes are enriched in this pathway.",
                "test": f"Validate {top3_up[0] if top3_up else 'top gene'} expression by qRT-PCR in independent samples.",
            },
            {
                "id": "H2",
                "hypothesis": f"Downregulation of {top3_down[0] if top3_down else 'key genes'} contributes to the {condition_a} phenotype.",
                "rationale": f"{top3_down[0] if top3_down else 'Key gene'} shows strong downregulation and maps to a repressed pathway.",
                "test": f"Overexpression rescue experiment for {top3_down[0] if top3_down else 'target gene'}.",
            },
            {
                "id": "H3",
                "hypothesis": f"The observed expression changes are driven by upstream regulatory changes in {go_terms[0]['term'] if go_terms else 'a key process'}.",
                "rationale": f"GO enrichment shows {go_terms[0]['term'] if go_terms else 'top process'} as the most significant biological process.",
                "test": "Perform time-course RNA-seq to identify early vs late response genes.",
            },
        ],
    }

    # ---- Transcript-level quantification (Salmon) — dynamic ----
    tx_prefix = "ENST" if domain == "animal" else ("AT" if species == "arabidopsis" else "TX")
    top_by_fc = sorted(volcano_data, key=lambda x: -abs(x["log2fc"]))
    transcript_data = {
        "top_isoforms": [
            {"gene_symbol": g["gene"], "transcript_id": f"{tx_prefix}{random.randint(10000,99999)}", "tpm": round(random.expovariate(0.005), 1), "is_primary": random.random() > 0.3}
            for g in top_by_fc[:20]
        ],
        "isoform_switch": [
            {"gene": g["gene"], "isoform_a": f"{tx_prefix}{random.randint(10000,99999)}", "isoform_b": f"{tx_prefix}{random.randint(10000,99999)}", "dIF": round(random.uniform(-0.5, 0.5), 3), "fdr": round(10 ** (-random.uniform(1, 5)), 6)}
            for g in top_by_fc[:5] if g["significant"]
        ],
        "total_transcripts_detected": random.randint(35000, 55000),
        "total_genes_detected": random.randint(18000, 25000),
    }

    # ---- WGCNA co-expression modules ----
    wgcna_colors = ["turquoise", "blue", "brown", "yellow", "green", "red", "black", "pink", "magenta", "purple"]
    wgcna_go_bank = {
        "animal": ["inflammatory response", "immune signaling", "extracellular matrix", "cell cycle",
                   "lipid metabolism", "apoptosis", "RNA processing", "cytokine production",
                   "tight junction", "oxidative phosphorylation"],
        "plant": ["photosynthesis", "defense response", "hormone signaling", "cell wall biogenesis",
                  "flavonoid biosynthesis", "phenylpropanoid pathway", "stress response", "auxin transport",
                  "chloroplast organization", "secondary metabolism"],
        "microbe": ["central metabolism", "amino acid biosynthesis", "cell division", "DNA repair",
                    "ribosome biogenesis", "membrane transport", "stress response", "motility",
                    "biofilm formation", "oxidative phosphorylation"],
    }
    wgcna_go = wgcna_go_bank.get(domain, wgcna_go_bank["animal"])
    wgcna_modules = []
    for i, color in enumerate(wgcna_colors):
        n = random.randint(80, 600)
        cor_val = random.uniform(-0.9, 0.9)
        pval = 10 ** (-abs(cor_val) * random.uniform(2, 8))
        hub_pool = [g["gene"] for g in volcano_data]
        random.shuffle(hub_pool)
        wgcna_modules.append({
            "color": color,
            "n_genes": n,
            "hub_genes": hub_pool[:random.randint(5, 8)],
            "cor_trait": round(cor_val, 3),
            "pvalue": round(pval, 8),
            "top_go_term": wgcna_go[i],
        })

    wgcna_edges = []
    for _ in range(200):
        mod = random.choice(wgcna_modules)
        if len(mod["hub_genes"]) >= 2:
            src, tgt = random.sample(mod["hub_genes"], 2)
            wgcna_edges.append({"source": src, "target": tgt, "weight": round(random.uniform(0.1, 0.95), 3), "module": mod["color"]})

    wgcna_data = {"modules": wgcna_modules, "network_edges": wgcna_edges}

    # ---- Cell type deconvolution ----
    cell_type_bank = {
        "animal": ["Epithelial", "T cells CD4+", "T cells CD8+", "Macrophages M1", "Macrophages M2", "B cells", "Neutrophils", "Fibroblasts", "Endothelial", "NK cells"],
        "plant": ["Mesophyll", "Epidermis", "Guard cells", "Phloem", "Xylem", "Root cortex", "Root endodermis", "Meristem", "Trichomes", "Palisade"],
        "microbe": ["Exponential phase", "Stationary phase", "Biofilm", "Planktonic", "Persister", "Competent", "Sporulating", "Vegetative", "Motile", "Sessile"],
    }
    cell_types = cell_type_bank.get(domain, cell_type_bank["animal"])
    sample_names = [f"S{i+1:02d}" for i in range(n_samples)]
    conditions_list = [condition_a] * n_a + [condition_b] * n_b

    fractions_list = []
    comparison_list = []
    for j, (sname, cond) in enumerate(zip(sample_names, conditions_list)):
        row = {}
        vals = [random.uniform(0.02, 0.3) for _ in cell_types]
        total = sum(vals)
        for ct, v in zip(cell_types, vals):
            frac = v / total
            row[ct] = round(frac, 4)
            comparison_list.append({"cell_type": ct, "condition": "A" if j < n_a else "B", "fraction": round(frac, 4), "sample": sname})
        fractions_list.append(row)

    cell_type_stats = []
    for ct in cell_types:
        a_vals = [f[ct] for f in fractions_list[:n_a]]
        b_vals = [f[ct] for f in fractions_list[n_a:]]
        mean_a = sum(a_vals) / max(len(a_vals), 1)
        mean_b = sum(b_vals) / max(len(b_vals), 1)
        cell_type_stats.append({
            "cell_type": ct,
            "mean_a": round(mean_a, 4),
            "mean_b": round(mean_b, 4),
            "diff": round(mean_a - mean_b, 4),
            "pvalue": round(random.uniform(0.001, 0.5), 4),
        })
    cell_type_stats.sort(key=lambda x: x["pvalue"])

    deconv_data = {
        "fractions": fractions_list,
        "cell_types": cell_types,
        "samples": sample_names,
        "conditions": conditions_list,
        "comparison": comparison_list,
        "cell_type_stats": cell_type_stats,
        "method": "xCell",
    }

    # --------------- FastQC data ---------------
    read_len = 150
    positions = list(range(1, read_len + 1))
    fastqc_data = {
        "base_quality": {
            "positions": positions,
            "mean_quality": [round(random.gauss(36 if p < 130 else 33, 1.2), 1) for p in positions],
            "q1": [round(random.gauss(32 if p < 130 else 28, 1.5), 1) for p in positions],
            "q3": [round(random.gauss(38 if p < 130 else 35, 0.8), 1) for p in positions],
            "lower_whisker": [round(random.gauss(28 if p < 130 else 22, 2), 1) for p in positions],
            "upper_whisker": [round(random.gauss(40, 0.5), 1) for p in positions],
        },
        "gc_content": {
            "gc_pct": list(range(0, 101)),
            "count": [round(max(0, 5000 * math.exp(-0.5 * ((x - 42) / 10) ** 2) + random.gauss(0, 100))) for x in range(101)],
            "theoretical": [round(5000 * math.exp(-0.5 * ((x - 42) / 10) ** 2)) for x in range(101)],
        },
        "adapter_content": {
            "positions": positions,
            "illumina_universal": [round(max(0, 0.002 * p + random.gauss(0, 0.1)), 2) for p in positions],
            "illumina_small_rna": [round(max(0, 0.001 * p + random.gauss(0, 0.05)), 2) for p in positions],
            "nextera": [round(max(0, 0.0005 * p + random.gauss(0, 0.03)), 2) for p in positions],
        },
    }

    # --------------- Alignment/Mapping data ---------------
    sample_names_full = [f"{condition_a}_rep{i+1}" for i in range(n_a)] + [f"{condition_b}_rep{i+1}" for i in range(n_b)]
    alignment_data = {
        "mapping_rate": {
            "samples": sample_names_full,
            "mapped": [round(random.uniform(28, 42), 1) for _ in range(n_samples)],
            "unmapped": [round(random.uniform(2, 6), 1) for _ in range(n_samples)],
        },
        "read_distribution": {
            "samples": sample_names_full,
            "exonic": [round(random.uniform(55, 75), 1) for _ in range(n_samples)],
            "intronic": [round(random.uniform(15, 30), 1) for _ in range(n_samples)],
            "intergenic": [round(random.uniform(5, 15), 1) for _ in range(n_samples)],
        },
        "gene_body_coverage": {
            "percentile": list(range(0, 101, 5)),
            "samples": [
                {"name": s, "coverage": [round(random.gauss(0.8 + 0.2 * math.sin(math.pi * p / 100), 0.08), 3) for p in range(0, 101, 5)]}
                for s in sample_names_full
            ],
        },
    }

    # --------------- Expression distribution data ---------------
    expression_dist = {
        "samples": [
            {"name": s, "values": [round(random.gauss(4.5, 2.5), 2) for _ in range(200)]}
            for s in sample_names_full
        ],
    }

    # --------------- Correlation heatmap ---------------
    corr_matrix = []
    for i in range(n_samples):
        row = []
        for j in range(n_samples):
            if i == j:
                row.append(1.0)
            else:
                # Same condition = higher correlation
                same_cond = (i < n_a and j < n_a) or (i >= n_a and j >= n_a)
                r = round(random.uniform(0.92, 0.98) if same_cond else random.uniform(0.78, 0.88), 3)
                row.append(r)
        corr_matrix.append(row)
    # Make symmetric
    for i in range(n_samples):
        for j in range(i + 1, n_samples):
            corr_matrix[j][i] = corr_matrix[i][j]
    correlation_data = {
        "samples": sample_names_full,
        "matrix": corr_matrix,
        "min": 0.75,
    }

    # --------------- MA Plot data ---------------
    ma_data = []
    for g in volcano_data:
        mean_expr = round(10 ** random.uniform(0.5, 4.5), 1)
        ma_data.append({
            "gene": g["gene"],
            "mean_expression": mean_expr,
            "log2fc": g["log2fc"],
            "significant": g["significant"],
        })

    # --------------- Dispersion data ---------------
    n_disp = 200
    mean_counts_disp = [round(10 ** random.uniform(0.5, 4.5), 1) for _ in range(n_disp)]
    mean_counts_disp.sort()
    dispersion_data = {
        "mean_counts": mean_counts_disp,
        "gene_est": [round(10 ** random.gauss(-1.5, 0.8), 4) for _ in range(n_disp)],
        "fitted": [round(0.5 / (mc ** 0.5) + 0.01, 4) for mc in mean_counts_disp],
        "final_est": [round(max(0.001, 0.5 / (mc ** 0.5) + 0.01 + random.gauss(0, 0.02)), 4) for mc in mean_counts_disp],
    }

    # --------------- Time-series data (for DPI experiments) ---------------
    time_points = [0, 7, 14, 21, 28]
    top_time_genes = [g["gene"] for g in sorted(volcano_data, key=lambda x: -abs(x["log2fc"])) if g["significant"]][:8]
    time_series_data = {
        "time_points": time_points,
        "x_label": "Days Post Inoculation (DPI)",
        "title": "Gene Expression Over Time (Top DEGs)",
        "genes": [
            {
                "gene": gene,
                "values": [round(random.gauss(2 + idx * 0.3, 0.5) + t * random.uniform(-0.05, 0.15), 2) for t in time_points],
                "se": [round(random.uniform(0.2, 0.6), 2) for _ in time_points],
            }
            for idx, gene in enumerate(top_time_genes)
        ],
    }

    # Venn diagram data — up-regulated DEGs split into condition-specific sets
    up_genes = [g["gene"] for g in volcano_data if g["direction"] == "up"]
    down_genes = [g["gene"] for g in volcano_data if g["direction"] == "down"]
    # Simulate two overlapping sets (e.g., two time points or sub-conditions)
    mid = len(up_genes) // 2
    overlap = max(1, len(up_genes) // 4)
    venn_data = {
        "set_a": up_genes[:mid + overlap],
        "set_b": up_genes[mid - overlap:] if mid > overlap else up_genes,
        "label_a": condition_a,
        "label_b": condition_b,
    }

    # Treatment-wise expression heatmap — annotated genes grouped by treatment
    treatment_genes = sorted(volcano_data, key=lambda g: -abs(g["log2fc"]))[:25]
    treatments = []
    for i in range(n_a):
        treatments.append(f"{condition_a}_rep{i+1}")
    for i in range(n_b):
        treatments.append(f"{condition_b}_rep{i+1}")
    treatment_heatmap = {
        "genes": [g["gene"] for g in treatment_genes],
        "treatments": treatments,
        "matrix": [
            [round(random.gauss(2.0 if j < n_a else 0.5, 0.6) * (1 if g["log2fc"] > 0 else -1), 2)
             for j in range(n_samples)]
            for g in treatment_genes
        ],
        "annotation_categories": [
            ("Defense/Stress" if abs(g["log2fc"]) > 2 else "Metabolism" if g["log2fc"] > 0 else "Signaling")
            for g in treatment_genes
        ],
    }

    # Gene annotations for the annotation table
    _biotype_pool = ["protein_coding", "lncRNA", "protein_coding", "protein_coding",
                     "processed_pseudogene", "snRNA", "protein_coding", "miRNA"]
    _go_bp_pool = {
        "plant": [
            "defense response", "response to water deprivation", "jasmonic acid signaling",
            "salicylic acid signaling", "cell wall organization", "phenylpropanoid biosynthesis",
            "flavonoid biosynthesis", "photosynthesis", "response to cold", "response to ABA",
            "lignin biosynthesis", "oxidative stress response", "kinase signaling",
        ],
        "animal": [
            "inflammatory response", "immune system process", "cytokine signaling",
            "leukocyte migration", "ECM organization", "cell adhesion", "apoptosis",
            "NF-kB signaling", "antigen presentation", "T cell activation",
            "wound healing", "angiogenesis", "lipid metabolism",
        ],
        "microbe": [
            "metabolic process", "oxidation-reduction", "transmembrane transport",
            "DNA repair", "stress response", "cell division", "translation",
            "biofilm formation", "quorum sensing", "amino acid biosynthesis",
            "carbohydrate metabolism", "protein folding", "chemotaxis",
        ],
    }
    _disease_pool = {
        "plant": ["Fusarium wilt resistance", "drought tolerance", "salt stress", "pathogen defense",
                  "herbivore resistance", "heat tolerance", "cold acclimation", None, None],
        "animal": ["IBD", "colorectal cancer", "rheumatoid arthritis", "fibrosis",
                   "atherosclerosis", "diabetes", "autoimmune", None, None],
        "microbe": ["antibiotic resistance", "virulence", "biofilm", "pathogenesis", None, None, None],
    }
    _drug_pool = {
        "plant": [None, None, None, "Fungicide target", "Herbicide target", None],
        "animal": ["Infliximab", "Adalimumab", None, "Tocilizumab", None, None, "Pembrolizumab", None],
        "microbe": ["Ciprofloxacin", "Rifampicin", None, None, "Ampicillin", None, None],
    }

    go_bp_list = _go_bp_pool.get(domain, _go_bp_pool["animal"])
    disease_list = _disease_pool.get(domain, _disease_pool["animal"])
    drug_list = _drug_pool.get(domain, _drug_pool["animal"])

    annotations = []
    for g in volcano_data:
        if g.get("significant"):
            annotations.append({
                "gene": g["gene"],
                "biotype": random.choice(_biotype_pool),
                "go_bp": random.choice(go_bp_list),
                "disease": random.choice(disease_list),
                "drug": random.choice(drug_list),
            })

    return {
        "domain": domain,
        "species": species,
        "volcano": volcano_data,
        "pca": pca_data,
        "heatmap": heatmap_data,
        "go_enrichment": go_terms,
        "kegg_pathways": kegg_pathways,
        "qc_summary": qc_summary,
        "deg_summary": deg_summary,
        "biotypes": biotypes,
        "interpretation": interpretation,
        "transcripts": transcript_data,
        "wgcna": wgcna_data,
        "deconvolution": domain == "animal" and deconv_data or None,
        "venn": venn_data,
        "treatment_heatmap": treatment_heatmap,
        "fastqc": fastqc_data,
        "alignment": alignment_data,
        "expression_dist": expression_dist,
        "correlation": correlation_data,
        "ma_plot": ma_data,
        "dispersion": dispersion_data,
        "time_series": time_series_data,
        "annotations": annotations,
        "biomarkers": _generate_biomarker_results(volcano_data, condition_a, condition_b, domain),
    }


def _generate_biomarker_results(volcano_data: list, condition_a: str, condition_b: str, domain: str) -> dict:
    """Generate ML-based biomarker selection results (RF, SVM, LASSO)."""
    import random as _rnd

    # Get significant genes sorted by absolute log2FC
    sig_genes = sorted(
        [g for g in volcano_data if g.get("significant")],
        key=lambda g: abs(g["log2fc"]),
        reverse=True,
    )
    if not sig_genes:
        return {}

    # Top candidate genes for biomarker analysis
    candidates = sig_genes[:min(50, len(sig_genes))]

    # --- Random Forest feature importance ---
    rf_importance = []
    for i, g in enumerate(candidates):
        imp = max(0.01, 1.0 / (1 + i * 0.3) + _rnd.gauss(0, 0.05))
        rf_importance.append({"gene": g["gene"], "importance": round(imp, 4), "rank": i + 1})
    rf_importance.sort(key=lambda x: x["importance"], reverse=True)
    for i, item in enumerate(rf_importance):
        item["rank"] = i + 1

    # --- SVM (RFE) ranking ---
    svm_ranking = []
    shuffled = list(range(len(candidates)))
    _rnd.shuffle(shuffled)
    # Bias toward top DEGs being ranked higher
    for i, g in enumerate(candidates):
        rfe_rank = max(1, i + 1 + _rnd.randint(-3, 3))
        svm_ranking.append({"gene": g["gene"], "rfe_rank": rfe_rank, "support_vector": _rnd.random() < 0.6})
    svm_ranking.sort(key=lambda x: x["rfe_rank"])
    for i, item in enumerate(svm_ranking):
        item["rfe_rank"] = i + 1

    # --- LASSO coefficients ---
    lasso_coefs = []
    for g in candidates:
        coef = g["log2fc"] * _rnd.uniform(0.1, 0.5) * (1 if abs(g["log2fc"]) > 1.5 else _rnd.uniform(0, 0.3))
        if abs(coef) > 0.01:  # LASSO zeroes out weak features
            lasso_coefs.append({"gene": g["gene"], "coefficient": round(coef, 4), "selected": True})
        else:
            lasso_coefs.append({"gene": g["gene"], "coefficient": 0.0, "selected": False})
    lasso_selected = [c for c in lasso_coefs if c["selected"]]

    # --- Consensus biomarkers (genes selected by all 3 methods) ---
    rf_top = {x["gene"] for x in rf_importance[:20]}
    svm_top = {x["gene"] for x in svm_ranking[:20]}
    lasso_top = {x["gene"] for x in lasso_selected[:20]}
    consensus_genes = rf_top & svm_top & lasso_top

    # Build consensus list with per-method scores
    rf_map = {x["gene"]: x for x in rf_importance}
    svm_map = {x["gene"]: x for x in svm_ranking}
    lasso_map = {x["gene"]: x for x in lasso_coefs}

    consensus = []
    for gene in sorted(consensus_genes, key=lambda g: rf_map[g]["importance"], reverse=True):
        vol = next((v for v in volcano_data if v["gene"] == gene), {})
        consensus.append({
            "gene": gene,
            "log2fc": vol.get("log2fc", 0),
            "fdr": vol.get("fdr", 1),
            "rf_importance": rf_map[gene]["importance"],
            "rf_rank": rf_map[gene]["rank"],
            "svm_rank": svm_map[gene]["rfe_rank"],
            "lasso_coef": lasso_map[gene]["coefficient"],
        })

    # --- Model performance metrics ---
    models = {
        "random_forest": {
            "accuracy": round(_rnd.uniform(0.88, 0.96), 3),
            "auc": round(_rnd.uniform(0.90, 0.98), 3),
            "precision": round(_rnd.uniform(0.85, 0.95), 3),
            "recall": round(_rnd.uniform(0.82, 0.94), 3),
            "f1": round(_rnd.uniform(0.85, 0.94), 3),
            "cv_folds": 5,
            "n_features_used": len(rf_top),
        },
        "svm": {
            "accuracy": round(_rnd.uniform(0.85, 0.94), 3),
            "auc": round(_rnd.uniform(0.88, 0.96), 3),
            "precision": round(_rnd.uniform(0.83, 0.93), 3),
            "recall": round(_rnd.uniform(0.80, 0.92), 3),
            "f1": round(_rnd.uniform(0.82, 0.92), 3),
            "cv_folds": 5,
            "n_features_used": len(svm_top),
        },
        "lasso": {
            "accuracy": round(_rnd.uniform(0.82, 0.92), 3),
            "auc": round(_rnd.uniform(0.85, 0.95), 3),
            "precision": round(_rnd.uniform(0.80, 0.91), 3),
            "recall": round(_rnd.uniform(0.78, 0.90), 3),
            "f1": round(_rnd.uniform(0.79, 0.90), 3),
            "cv_folds": 5,
            "n_features_used": len(lasso_selected),
            "lambda": round(_rnd.uniform(0.001, 0.1), 4),
        },
    }

    # --- ROC curve data per model ---
    roc_curves = {}
    for model_name in ["random_forest", "svm", "lasso"]:
        auc = models[model_name]["auc"]
        fpr = [0.0]
        tpr = [0.0]
        for t in range(1, 20):
            f = t / 20.0
            # Simulate a curve that bows toward top-left based on AUC
            tp = min(1.0, f ** (1 / max(auc * 2, 1.01)))
            fpr.append(round(f, 3))
            tpr.append(round(tp, 3))
        fpr.append(1.0)
        tpr.append(1.0)
        roc_curves[model_name] = {"fpr": fpr, "tpr": tpr, "auc": auc}

    # --- Confusion matrix for best model ---
    n_test = _rnd.randint(8, 15)
    tp = int(n_test * models["random_forest"]["recall"])
    fn = n_test - tp
    fp = max(0, int(n_test * (1 - models["random_forest"]["precision"])))
    tn = n_test - fp
    confusion = {"tp": tp, "fn": fn, "fp": fp, "tn": tn, "labels": [condition_a, condition_b]}

    return {
        "comparisons": [
            {"label": f"{condition_a} vs {condition_b}", "type": "primary"},
        ],
        "random_forest": rf_importance[:20],
        "svm_ranking": svm_ranking[:20],
        "lasso_coefficients": lasso_coefs,
        "consensus_biomarkers": consensus,
        "model_performance": models,
        "roc_curves": roc_curves,
        "confusion_matrix": confusion,
        "summary": {
            "total_deg_input": len(sig_genes),
            "rf_top_features": len(rf_top),
            "svm_top_features": len(svm_top),
            "lasso_selected": len(lasso_selected),
            "consensus_count": len(consensus),
            "best_model": "random_forest",
            "best_auc": models["random_forest"]["auc"],
        },
    }


# ---------------------------------------------------------------------------
# Upload & Job creation
# ---------------------------------------------------------------------------

@api_app.post("/api/jobs/init")
async def init_job(
    project_name: str = Form(...),
    species: str = Form("human"),
    domain: str = Form("biomedical"),
    condition_a: str = Form(...),
    condition_b: str = Form(...),
    n_a: int = Form(...),
    n_b: int = Form(...),
    tissue_type: str = Form(""),
    disease_context: str = Form(""),
    email: str = Form(""),
):
    """Create a job record with metadata only (no files yet)."""
    job_id = str(uuid.uuid4())[:12]
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    job_state = {
        "job_id": job_id,
        "project_name": project_name,
        "species": species,
        "domain": domain,
        "condition_a": condition_a,
        "condition_b": condition_b,
        "n_a": n_a,
        "n_b": n_b,
        "n_samples": n_a + n_b,
        "tissue_type": tissue_type,
        "disease_context": disease_context,
        "email": email,
        "dataset_size_gb": 0,
        "files": [],
        "status": "uploading",
        "current_step": "uploading",
        "steps_completed": [],
        "total_steps": 11,
        "pct_complete": 0,
        "cost_so_far_usd": 0.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    _jobs_store[job_id] = job_state
    return {"job_id": job_id, "status": "uploading"}


STREAM_CHUNK = 1024 * 1024  # 1 MB disk-write buffer
_METADATA_EXTS = {".csv", ".tsv", ".txt"}
_assembly_locks: dict[str, asyncio.Lock] = {}  # per-file locks to prevent concurrent reassembly
_upload_semaphore = asyncio.Semaphore(4)  # max 4 concurrent upload requests to prevent OOM on small instances


def _is_metadata_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in _METADATA_EXTS


def _register_file(job_id: str, filename: str, size_bytes: int):
    """Register an uploaded file as metadata or data in the job store."""
    job = _jobs_store[job_id]
    if _is_metadata_file(filename):
        job["metadata_file"] = filename
    else:
        if filename not in job["files"]:
            job["files"].append(filename)
        job["dataset_size_gb"] = round(job["dataset_size_gb"] + size_bytes / (1024**3), 2)
    _jobs_store[job_id] = job


# ---------------------------------------------------------------------------
# S3 presigned upload (browser → S3 directly, bypasses server)
# ---------------------------------------------------------------------------

S3_UPLOAD_ENABLED = bool(settings.aws_access_key_id and settings.s3_bucket_raw)


class PresignedUrlRequest(BaseModel):
    filename: str
    content_type: str = "application/gzip"
    part_count: int = 1


@api_app.get("/api/upload-mode")
async def get_upload_mode():
    """Tell the frontend whether S3 direct upload is available."""
    return {"s3_enabled": S3_UPLOAD_ENABLED, "max_chunk_mb": 10}


@api_app.post("/api/jobs/{job_id}/presign")
async def get_presigned_url(job_id: str, req: PresignedUrlRequest):
    """Generate S3 presigned URL(s) for direct browser-to-S3 upload."""
    if job_id not in _jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")
    if not S3_UPLOAD_ENABLED:
        raise HTTPException(status_code=501, detail="S3 upload not configured")

    from rnascope.infra.aws import _get_s3
    s3 = _get_s3()
    bucket = settings.s3_bucket_raw
    s3_key = f"{job_id}/{req.filename}"

    if req.part_count <= 1:
        url = s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": s3_key, "ContentType": req.content_type},
            ExpiresIn=86400, # 24 hours for large uploads
        )
        return {"method": "PUT", "url": url, "s3_key": s3_key}

    # Multipart upload for large files
    mpu = s3.create_multipart_upload(Bucket=bucket, Key=s3_key, ContentType=req.content_type)
    upload_id = mpu["UploadId"]

    part_urls = []
    for part_num in range(1, req.part_count + 1):
        url = s3.generate_presigned_url(
            "upload_part",
            Params={"Bucket": bucket, "Key": s3_key, "UploadId": upload_id, "PartNumber": part_num},
            ExpiresIn=86400, # 24 hours
        )
        part_urls.append({"part_number": part_num, "url": url})

    return {"method": "MULTIPART", "upload_id": upload_id, "s3_key": s3_key, "parts": part_urls}


@api_app.post("/api/jobs/{job_id}/proxy-upload")
async def proxy_upload_part(
    job_id: str,
    s3_key: str = Query(...),
    upload_id: str = Query(...),
    part_number: int = Query(...),
    file: UploadFile = File(...),
):
    """Proxy an S3 multipart upload part through the server to avoid CORS/connection issues."""
    if job_id not in _jobs_store:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    from rnascope.infra.aws import _get_s3
    s3 = _get_s3()
    bucket = settings.s3_bucket_raw

    try:
        # Read the chunk from the request
        chunk = await file.read()
        
        # Upload directly to S3
        resp = s3.upload_part(
            Bucket=bucket,
            Key=s3_key,
            PartNumber=part_number,
            UploadId=upload_id,
            Body=chunk,
        )
        return {"etag": resp["ETag"]}
    except Exception as e:
        logger.exception("Proxy upload failed for job %s part %d", job_id, part_number)
        raise HTTPException(status_code=500, detail=str(e))


class CompleteMultipartRequest(BaseModel):
    s3_key: str
    upload_id: str
    parts: list[dict]


@api_app.post("/api/jobs/{job_id}/presign/complete")
async def complete_multipart(job_id: str, req: CompleteMultipartRequest):
    """Complete an S3 multipart upload after all parts are uploaded."""
    if job_id not in _jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")

    from rnascope.infra.aws import _get_s3
    s3 = _get_s3()
    bucket = settings.s3_bucket_raw

    s3.complete_multipart_upload(
        Bucket=bucket,
        Key=req.s3_key,
        UploadId=req.upload_id,
        MultipartUpload={"Parts": [{"PartNumber": p["part_number"], "ETag": p["etag"]} for p in req.parts]},
    )

    filename = req.s3_key.split("/", 1)[-1]
    head = s3.head_object(Bucket=bucket, Key=req.s3_key)
    _register_file(job_id, filename, head["ContentLength"])

    return {"status": "complete", "s3_key": req.s3_key}


@api_app.post("/api/jobs/{job_id}/presign/register")
async def register_s3_file(job_id: str, filename: str = Form(...), size_bytes: int = Form(0)):
    """Register a file after single PUT presigned upload completes."""
    if job_id not in _jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")

    _register_file(job_id, filename, size_bytes)
    return {"status": "registered", "filename": filename}


# ---------------------------------------------------------------------------
# Fallback chunked upload (browser → server → disk/S3)
# ---------------------------------------------------------------------------

@api_app.post("/api/jobs/{job_id}/upload")
async def upload_file(
    job_id: str,
    file: UploadFile = File(...),
    chunk_index: int = Form(0),
    total_chunks: int = Form(1),
    filename: str = Form(""),
):
    """Upload a file chunk. Chunks are written to disk and assembled on final chunk."""
    async with _upload_semaphore:
        return await _upload_file_inner(job_id, file, chunk_index, total_chunks, filename)


async def _upload_file_inner(
    job_id: str,
    file: UploadFile,
    chunk_index: int,
    total_chunks: int,
    filename: str,
):
    if job_id not in _jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")

    real_name = filename or file.filename
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    if total_chunks == 1:
        # Single-chunk file
        dest = job_dir / real_name
        file_size = 0
        with open(dest, "wb") as f:
            while buf := await file.read(STREAM_CHUNK):
                f.write(buf)
                file_size += len(buf)

        # Upload to S3 and clean up local file
        await _upload_to_s3_and_cleanup(job_id, real_name, dest, file_size)
        return {"filename": real_name, "chunk": 0, "total_chunks": 1, "status": "complete",
                "size_mb": round(file_size / (1024**2), 2)}

    # Multi-chunk: write chunk to a temp part file
    chunk_dir = job_dir / f".chunks_{real_name}"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = chunk_dir / f"part_{chunk_index:05d}"

    chunk_size = 0
    with open(chunk_path, "wb") as f:
        while buf := await file.read(STREAM_CHUNK):
            f.write(buf)
            chunk_size += len(buf)

    # Check if all chunks have arrived — use a lock to prevent concurrent reassembly
    lock_key = f"{job_id}/{real_name}"
    if lock_key not in _assembly_locks:
        _assembly_locks[lock_key] = asyncio.Lock()

    async with _assembly_locks[lock_key]:
        received = len(list(chunk_dir.glob("part_*")))

        if received >= total_chunks:
            # Reassemble the full file
            dest = job_dir / real_name
            total_size = 0
            with open(dest, "wb") as out:
                for i in range(total_chunks):
                    part = chunk_dir / f"part_{i:05d}"
                    total_size += part.stat().st_size
                    with open(part, "rb") as inp:
                        shutil.copyfileobj(inp, out)

            # Clean up chunk dir and lock
            shutil.rmtree(chunk_dir, ignore_errors=True)
            _assembly_locks.pop(lock_key, None)

            # Upload to S3 and clean up local file
            await _upload_to_s3_and_cleanup(job_id, real_name, dest, total_size)
            return {"filename": real_name, "chunk": chunk_index, "total_chunks": total_chunks,
                    "status": "complete", "size_mb": round(total_size / (1024**2), 2)}

    return {"filename": real_name, "chunk": chunk_index, "total_chunks": total_chunks,
            "status": "uploading", "received": received}


async def _upload_to_s3_and_cleanup(job_id: str, filename: str, local_path: Path, file_size: int):
    """Upload a completed file to S3, register it, and remove from local disk."""
    from rnascope.config import settings as _settings

    s3_key = f"{job_id}/{filename}"

    try:
        from rnascope.infra.aws import s3_multipart_upload
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            s3_multipart_upload,
            _settings.s3_bucket_raw,
            s3_key,
            str(local_path),
            50,  # 50 MB chunks for S3 multipart
        )
        logger.info("Uploaded %s to s3://%s/%s", filename, _settings.s3_bucket_raw, s3_key)
    except Exception as exc:
        logger.error("S3 upload failed for %s: %s — keeping local copy", filename, exc)
        _register_file(job_id, filename, file_size)
        return

    # S3 upload succeeded — remove local file to free disk
    try:
        local_path.unlink()
    except OSError:
        pass

    _register_file(job_id, filename, file_size)


@api_app.post("/api/jobs/{job_id}/sync-s3")
async def sync_s3_files(job_id: str):
    """Scan S3 for files under this job_id and register them.

    Use this after uploading files via AWS CLI:
        aws s3 sync ./fastq_folder s3://rnascope-raw-data/<job_id>/
    """
    if job_id not in _jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")
    if not S3_UPLOAD_ENABLED:
        raise HTTPException(status_code=501, detail="S3 not configured")

    from rnascope.infra.aws import s3_list_objects
    bucket = settings.s3_bucket_raw
    objects = s3_list_objects(bucket, f"{job_id}/")

    registered = 0
    for obj in objects:
        filename = obj["key"].split("/", 1)[-1]
        if filename:
            _register_file(job_id, filename, obj["size"])
            registered += 1

    job = _jobs_store[job_id]
    return {
        "job_id": job_id,
        "files_registered": registered,
        "total_files": len(job["files"]),
        "dataset_size_gb": job["dataset_size_gb"],
    }


@api_app.post("/api/jobs/{job_id}/rerun")
async def rerun_job(job_id: str):
    """Re-run pipeline using files already in S3 (no re-upload needed).

    Creates a new job that references the same S3 files as the original.
    Files are kept for 60 days after the original upload.
    """
    if job_id not in _jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")

    old_job = _jobs_store[job_id]

    # Check if files still exist
    expire_at = old_job.get("files_expire_at")
    if expire_at:
        from datetime import datetime as _dt
        if _dt.fromisoformat(expire_at) < _dt.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Files have expired. Please re-upload.")

    # Create new job with same metadata but fresh state
    new_job_id = str(uuid.uuid4())[:12]
    new_job = {
        **old_job,
        "job_id": new_job_id,
        "status": "uploading",
        "current_step": "uploading",
        "steps_completed": [],
        "pct_complete": 0,
        "cost_so_far_usd": 0.0,
        "results": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_job_id": job_id,
    }
    _jobs_store[new_job_id] = new_job

    # Copy S3 file references (files are still in S3 under original job_id)
    if S3_UPLOAD_ENABLED:
        from rnascope.infra.aws import s3_list_objects
        bucket = settings.s3_bucket_raw
        objects = s3_list_objects(bucket, f"{job_id}/")
        for obj in objects:
            filename = obj["key"].split("/", 1)[-1]
            if filename:
                _register_file(new_job_id, filename, obj["size"])

    return {"new_job_id": new_job_id, "files_reused": len(new_job.get("files", [])), "source_job_id": job_id}


def _detect_samples(files: list[str]) -> list[dict]:
    """Detect paired-end samples from filenames.

    Handles patterns like:
      sample_1.fq.gz / sample_2.fq.gz
      sample_R1.fq.gz / sample_R2.fq.gz
      sample_R1_001.fastq.gz / sample_R2_001.fastq.gz
    """
    import re
    # Strip to base name (remove path prefix if any)
    basenames = [f.split("/")[-1] for f in files]

    # Group by sample: remove _1/_2, _R1/_R2 suffixes
    sample_map: dict[str, list[str]] = {}
    for fname in basenames:
        # Skip metadata files
        if Path(fname).suffix.lower() in _METADATA_EXTS:
            continue
        # Extract sample ID by removing read pair indicator
        sample_id = re.sub(r'[._](?:R?[12])(?:[._]001)?\.(?:fq|fastq)\.gz$', '', fname, flags=re.IGNORECASE)
        if sample_id not in sample_map:
            sample_map[sample_id] = []
        sample_map[sample_id].append(fname)

    samples = []
    for sid, fnames in sorted(sample_map.items()):
        samples.append({
            "sample_id": sid,
            "files": sorted(fnames),
            "paired": len(fnames) >= 2,
        })
    return samples


@api_app.post("/api/jobs/{job_id}/start")
async def start_job(job_id: str):
    """Start the pipeline after all files have been uploaded."""
    if job_id not in _jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _jobs_store[job_id]
    if not job["files"]:
        raise HTTPException(status_code=400, detail="No files uploaded yet")

    # Auto-detect samples from uploaded filenames
    detected = _detect_samples(job["files"])
    n_detected = len(detected)
    if n_detected > 0:
        job["detected_samples"] = detected
        job["n_samples"] = n_detected
        # Split evenly between conditions if user didn't specify correctly
        if job.get("n_a", 0) + job.get("n_b", 0) != n_detected:
            job["n_a"] = n_detected // 2
            job["n_b"] = n_detected - n_detected // 2
            logger.info("Auto-detected %d samples from %d files for job %s", n_detected, len(job["files"]), job_id)

    job["status"] = "running"
    job["current_step"] = "ingestion"
    _jobs_store[job_id] = job

    asyncio.get_event_loop().run_in_executor(None, _simulate_pipeline, job_id)

    return {"job_id": job_id, "status": "started", "files_uploaded": len(job["files"]), "size_gb": job["dataset_size_gb"]}


def _simulate_pipeline(job_id: str):
    """Simulate pipeline progress for demo (replace with real orchestrator call)."""
    import time

    steps = [
        ("ingestion", "Validating uploads..."),
        ("qc", "Running FastQC + Trimmomatic..."),
        ("rrna_depletion", "Removing rRNA reads..."),
        ("alignment", "STAR alignment running..."),
        ("quantification", "featureCounts quantification..."),
        ("transcript_quant", "Salmon transcript quantification..."),
        ("deg", "DESeq2 differential expression..."),
        ("biomarker", "ML biomarker selection (RF + SVM + LASSO)..."),
        ("annotation", "Gene annotation..."),
        ("pathway", "Pathway enrichment analysis..."),
        ("biotype", "RNA biotype classification..."),
        ("wgcna", "WGCNA co-expression network..."),
        ("deconvolution", "Cell type deconvolution..."),
        ("interpretation", "AI biological interpretation..."),
        ("report", "Generating PDF report..."),
    ]

    for i, (step, msg) in enumerate(steps):
        time.sleep(3)  # simulate work
        job = _jobs_store.get(job_id)
        if not job:
            return
        job["current_step"] = step
        job["steps_completed"] = [s[0] for s in steps[:i]]
        job["pct_complete"] = round((i / len(steps)) * 100, 1)
        job["cost_so_far_usd"] = round(0.12 * (i + 1), 2)
        _jobs_store[job_id] = job

        # Notify websockets
        _broadcast_sync(job_id, {
            "type": "step_update",
            "step": step,
            "message": msg,
            "pct_complete": job["pct_complete"],
            "steps_completed": job["steps_completed"],
        })

    # Mark completed + generate results
    job = _jobs_store.get(job_id)
    if job:
        job["status"] = "completed"
        job["current_step"] = None
        job["steps_completed"] = [s[0] for s in steps]
        job["pct_complete"] = 100.0
        job["results"] = _generate_demo_results(
            job_id,
            species=job.get("species", "human"),
            condition_a=job.get("condition_a", "Treatment"),
            condition_b=job.get("condition_b", "Control"),
            n_a=job.get("n_a", 3),
            n_b=job.get("n_b", 3),
        )
        _jobs_store[job_id] = job

        _broadcast_sync(job_id, {
            "type": "pipeline_complete",
            "pct_complete": 100.0,
            "message": "Pipeline complete! Results are ready.",
        })

        # Keep raw files for 60 days so users can re-run without re-uploading.
        # S3 lifecycle policy handles deletion after 60 days.
        job["files_expire_at"] = (datetime.now(timezone.utc) + __import__("datetime").timedelta(days=60)).isoformat()
        _jobs_store[job_id] = job
        logger.info("Raw files for job %s retained until %s", job_id, job["files_expire_at"])


def _broadcast_sync(job_id: str, message: dict):
    """Send WebSocket message from a sync thread."""
    sockets = _active_websockets.get(job_id, [])
    for ws in sockets:
        try:
            asyncio.run_coroutine_threadsafe(
                ws.send_json(message),
                asyncio.get_event_loop(),
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Job status & list
# ---------------------------------------------------------------------------

@api_app.get("/api/jobs")
async def list_jobs():
    """List all jobs."""
    jobs = []
    for jid, state in _jobs_store.items():
        jobs.append({
            "job_id": jid,
            "project_name": state.get("project_name", ""),
            "status": state.get("status", "unknown"),
            "pct_complete": state.get("pct_complete", 0),
            "n_samples": state.get("n_samples", 0),
            "created_at": state.get("created_at", ""),
        })
    return {"jobs": sorted(jobs, key=lambda j: j["created_at"], reverse=True)}


@api_app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    """Get the current status of a pipeline job."""
    state = _jobs_store.get(job_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return state


# ---------------------------------------------------------------------------
# Results / Graph data endpoints
# ---------------------------------------------------------------------------

@api_app.get("/api/jobs/{job_id}/results")
async def job_results(job_id: str):
    """Get all analysis results (graph data) for a completed job."""
    state = _jobs_store.get(job_id)
    if not state:
        raise HTTPException(status_code=404, detail="Job not found")
    results = state.get("results")
    if not results:
        raise HTTPException(status_code=202, detail="Results not ready yet")
    return results


@api_app.get("/api/jobs/{job_id}/volcano")
async def volcano_data(job_id: str):
    state = _jobs_store.get(job_id)
    if not state or not state.get("results"):
        raise HTTPException(status_code=404)
    return state["results"]["volcano"]


@api_app.get("/api/jobs/{job_id}/pca")
async def pca_data(job_id: str):
    state = _jobs_store.get(job_id)
    if not state or not state.get("results"):
        raise HTTPException(status_code=404)
    return state["results"]["pca"]


@api_app.get("/api/jobs/{job_id}/heatmap")
async def heatmap_data(job_id: str):
    state = _jobs_store.get(job_id)
    if not state or not state.get("results"):
        raise HTTPException(status_code=404)
    return state["results"]["heatmap"]


@api_app.get("/api/jobs/{job_id}/go")
async def go_data(job_id: str):
    state = _jobs_store.get(job_id)
    if not state or not state.get("results"):
        raise HTTPException(status_code=404)
    return state["results"]["go_enrichment"]


@api_app.get("/api/jobs/{job_id}/kegg")
async def kegg_data(job_id: str):
    state = _jobs_store.get(job_id)
    if not state or not state.get("results"):
        raise HTTPException(status_code=404)
    return state["results"]["kegg_pathways"]


@api_app.get("/api/jobs/{job_id}/qc")
async def qc_data(job_id: str):
    state = _jobs_store.get(job_id)
    if not state or not state.get("results"):
        raise HTTPException(status_code=404)
    return state["results"]["qc_summary"]


@api_app.get("/api/jobs/{job_id}/deg")
async def deg_data(job_id: str):
    state = _jobs_store.get(job_id)
    if not state or not state.get("results"):
        raise HTTPException(status_code=404)
    return state["results"]["deg_summary"]


@api_app.get("/api/jobs/{job_id}/biotypes")
async def biotype_data(job_id: str):
    state = _jobs_store.get(job_id)
    if not state or not state.get("results"):
        raise HTTPException(status_code=404)
    return state["results"]["biotypes"]


@api_app.get("/api/jobs/{job_id}/interpretation")
async def interpretation_data(job_id: str):
    state = _jobs_store.get(job_id)
    if not state or not state.get("results"):
        raise HTTPException(status_code=404)
    return state["results"]["interpretation"]


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@api_app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    if req.job_id not in _chat_sessions:
        _chat_sessions[req.job_id] = ChatAgent(req.job_id)
    agent = _chat_sessions[req.job_id]
    answer = agent.ask(req.question)
    return ChatResponse(job_id=req.job_id, answer=answer)


# ---------------------------------------------------------------------------
# WebSocket for live pipeline progress
# ---------------------------------------------------------------------------

@api_app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    await websocket.accept()
    _active_websockets.setdefault(job_id, []).append(websocket)
    try:
        # Send current state immediately
        state = _jobs_store.get(job_id)
        if state:
            await websocket.send_json({
                "type": "current_state",
                "status": state.get("status"),
                "current_step": state.get("current_step"),
                "pct_complete": state.get("pct_complete", 0),
                "steps_completed": state.get("steps_completed", []),
            })
        # Keep alive until client disconnects
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _active_websockets[job_id].remove(websocket)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@api_app.get("/health")
async def health():
    return {"status": "ok", "service": "rnascope"}


# ---------------------------------------------------------------------------
# Serve frontend static files (production: built React app)
# ---------------------------------------------------------------------------

import os as _os
from pathlib import Path as _Path
from fastapi.responses import FileResponse

# Check multiple possible locations for the static dir
_static_candidates = [
    _Path("/app/static"),                          # Docker: COPY --from=frontend
    _Path(__file__).parent.parent / "static",      # Local dev: project root
    _Path.cwd() / "static",                        # CWD fallback
]
_static_dir = None
for _candidate in _static_candidates:
    if _candidate.is_dir() and (_candidate / "index.html").is_file():
        _static_dir = _candidate
        break

if _static_dir:
    logger.info("Serving frontend from: %s", _static_dir)

    # Serve static assets (js, css, etc.) with correct MIME types
    api_app.mount("/assets", StaticFiles(directory=str(_static_dir / "assets")), name="static-assets")

    @api_app.get("/{path:path}")
    async def serve_spa(path: str):
        if path.startswith("api/") or path.startswith("ws/") or path == "health":
            raise HTTPException(status_code=404)
        file_path = _static_dir / path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_static_dir / "index.html")
else:
    logger.warning("No static frontend found. Serving API only.")

    @api_app.get("/")
    async def root():
        return {"status": "ok", "service": "rnascope", "frontend": "not built", "docs": "/docs"}
