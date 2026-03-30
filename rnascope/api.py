"""FastAPI application — REST API for upload, pipeline, chat, graphs, WebSocket."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
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
_jobs_store: dict[str, dict] = {}

# Upload temp dir
UPLOAD_DIR = Path(os.environ.get("RNASCOPE_UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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
    genotypes: list[str] = []
    time_points: list[str] = []
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
    plants = {"arabidopsis", "rice", "maize", "wheat", "tomato", "soybean", "potato", "grape"}
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
        "total_samples": 6,
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

    return {
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
        "deconvolution": deconv_data,
    }


# ---------------------------------------------------------------------------
# Upload & Job creation
# ---------------------------------------------------------------------------

@api_app.post("/api/jobs")
async def create_job(
    project_name: str = Form(...),
    species: str = Form("human"),
    condition_a: str = Form(...),
    condition_b: str = Form(...),
    n_a: int = Form(...),
    n_b: int = Form(...),
    genotypes: str = Form(""),
    time_points: str = Form(""),
    tissue_type: str = Form(""),
    disease_context: str = Form(""),
    email: str = Form(""),
    files: list[UploadFile] = File(...),
):
    """Upload FASTQ files and start a new pipeline job."""
    job_id = str(uuid.uuid4())[:12]
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    uploaded_files = []
    total_size = 0
    for f in files:
        dest = job_dir / f.filename
        content = await f.read()
        dest.write_bytes(content)
        total_size += len(content)
        uploaded_files.append(f.filename)

    size_gb = round(total_size / (1024**3), 2)

    job_state = {
        "job_id": job_id,
        "project_name": project_name,
        "species": species,
        "condition_a": condition_a,
        "condition_b": condition_b,
        "n_a": n_a,
        "n_b": n_b,
        "n_samples": n_a + n_b,
        "genotypes": [g.strip() for g in genotypes.split(",") if g.strip()] if genotypes else [],
        "time_points": [t.strip() for t in time_points.split(",") if t.strip()] if time_points else [],
        "tissue_type": tissue_type,
        "disease_context": disease_context,
        "email": email,
        "dataset_size_gb": size_gb,
        "files": uploaded_files,
        "status": "running",
        "current_step": "ingestion",
        "steps_completed": [],
        "total_steps": 11,
        "pct_complete": 0,
        "cost_so_far_usd": 0.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    _jobs_store[job_id] = job_state

    # Start simulated pipeline progress in background
    asyncio.get_event_loop().run_in_executor(None, _simulate_pipeline, job_id)

    return {"job_id": job_id, "status": "started", "files_uploaded": len(uploaded_files), "size_gb": size_gb}


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

        _broadcast_sync(job_id, {
            "type": "pipeline_complete",
            "pct_complete": 100.0,
            "message": "Pipeline complete! Results are ready.",
        })


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
