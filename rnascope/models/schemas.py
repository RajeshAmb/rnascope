from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PipelineStep(str, Enum):
    INGESTION = "ingestion"
    QC = "qc"
    RRNA_DEPLETION = "rrna_depletion"
    ALIGNMENT = "alignment"
    QUANTIFICATION = "quantification"
    TRANSCRIPT_QUANT = "transcript_quant"
    DEG = "deg"
    ANNOTATION = "annotation"
    PATHWAY = "pathway"
    BIOTYPE = "biotype"
    WGCNA = "wgcna"
    DECONVOLUTION = "deconvolution"
    INTERPRETATION = "interpretation"
    REPORT = "report"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SampleFlag(str, Enum):
    LOW_Q30 = "low_q30"
    LOW_MAPPING = "low_mapping"
    HIGH_DUPLICATION = "high_duplication"
    HIGH_RRNA = "high_rrna"
    CORRUPT_FASTQ = "corrupt_fastq"


class ComputeTier(str, Enum):
    SMALL = "r6i.xlarge"       # <10 GB
    MEDIUM = "r6i.8xlarge"     # 10-100 GB
    LARGE = "batch_array"      # >100 GB


class ReadLayout(str, Enum):
    PAIRED = "paired"
    SINGLE = "single"


# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------

class Sample(BaseModel):
    sample_id: str
    fastq_r1: str
    fastq_r2: str | None = None
    layout: ReadLayout = ReadLayout.PAIRED
    condition: str = ""
    flags: list[SampleFlag] = Field(default_factory=list)
    qc_metrics: dict[str, Any] = Field(default_factory=dict)
    alignment_metrics: dict[str, Any] = Field(default_factory=dict)
    bam_path: str | None = None


class JobMetadata(BaseModel):
    researcher_email: str = ""
    slack_channel: str = ""
    tissue_type: str = ""
    disease_context: str = ""
    domain: str = "biomedical"  # biomedical, plant_biology, soil_microbiome, food_science, agriculture, ecology
    covariates: list[str] = Field(default_factory=list)


GENOME_REFERENCES: dict[str, dict[str, str]] = {
    # Animals
    "human":       {"genome": "GRCh38",        "gtf": "Ensembl_110",    "org_db": "org.Hs.eg.db",  "kegg": "hsa"},
    "mouse":       {"genome": "mm39",          "gtf": "Ensembl_110",    "org_db": "org.Mm.eg.db",  "kegg": "mmu"},
    "rat":         {"genome": "mRatBN7.2",     "gtf": "Ensembl_110",    "org_db": "org.Rn.eg.db",  "kegg": "rno"},
    "zebrafish":   {"genome": "GRCz11",        "gtf": "Ensembl_110",    "org_db": "org.Dr.eg.db",  "kegg": "dre"},
    "drosophila":  {"genome": "dm6",           "gtf": "Ensembl_110",    "org_db": "org.Dm.eg.db",  "kegg": "dme"},
    "c_elegans":   {"genome": "WBcel235",      "gtf": "Ensembl_110",    "org_db": "org.Ce.eg.db",  "kegg": "cel"},
    "chicken":     {"genome": "GRCg7b",        "gtf": "Ensembl_110",    "org_db": "org.Gg.eg.db",  "kegg": "gga"},
    "pig":         {"genome": "Sscrofa11.1",   "gtf": "Ensembl_110",    "org_db": "org.Ss.eg.db",  "kegg": "ssc"},
    "cow":         {"genome": "ARS-UCD1.3",    "gtf": "Ensembl_110",    "org_db": "org.Bt.eg.db",  "kegg": "bta"},
    # Plants
    "arabidopsis": {"genome": "TAIR10",        "gtf": "Araport11",      "org_db": "org.At.tair.db", "kegg": "ath"},
    "rice":        {"genome": "IRGSP-1.0",     "gtf": "RAP-DB",         "org_db": "org.Os.eg.db",  "kegg": "osa"},
    "maize":       {"genome": "Zm-B73-v5",     "gtf": "Zm00001eb.1",   "org_db": "org.Zm.eg.db",  "kegg": "zma"},
    "wheat":       {"genome": "IWGSC_v2.1",    "gtf": "IWGSC_v2.1",    "org_db": "org.Ta.eg.db",  "kegg": "tae"},
    "tomato":      {"genome": "SL4.0",         "gtf": "ITAG4.0",       "org_db": "org.Sl.eg.db",  "kegg": "sly"},
    "soybean":     {"genome": "Wm82.a4.v1",   "gtf": "Gmax_508",      "org_db": "org.Gm.eg.db",  "kegg": "gmx"},
    "potato":      {"genome": "DM_v6.1",       "gtf": "PGSC_DM_v6.1",  "org_db": "",               "kegg": "stu"},
    "grape":       {"genome": "12X.v2",        "gtf": "VCost.v3",      "org_db": "",               "kegg": "vvi"},
    "cotton":      {"genome": "UTX-TM1_v2.1", "gtf": "HAU_v1",        "org_db": "",               "kegg": "ghir"},
    "cotton_arboreum": {"genome": "CRI_v1.0",  "gtf": "CRI_v1.0",     "org_db": "",               "kegg": "garb"},
    # Microbiome / Soil / Food
    "ecoli":       {"genome": "K-12_MG1655",   "gtf": "NCBI_ASM584",   "org_db": "org.EcK12.eg.db", "kegg": "eco"},
    "yeast":       {"genome": "R64-1-1",       "gtf": "Ensembl_110",    "org_db": "org.Sc.sgd.db", "kegg": "sce"},
    "aspergillus": {"genome": "CBS_513.88",    "gtf": "AspGD",          "org_db": "",               "kegg": "ang"},
    "lactobacillus": {"genome": "custom",      "gtf": "custom",         "org_db": "",               "kegg": ""},
    "metatranscriptome": {"genome": "meta",    "gtf": "meta",           "org_db": "",               "kegg": ""},
    "custom":      {"genome": "custom",        "gtf": "custom",         "org_db": "",               "kegg": ""},
}


class Job(BaseModel):
    job_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    project_name: str = ""
    species: str = "human"
    genome: str = "GRCh38"
    gtf: str = "Ensembl_110"
    samples: list[Sample] = Field(default_factory=list)
    condition_a: str = ""
    condition_b: str = ""
    n_a: int = 0
    n_b: int = 0
    genotypes: list[str] = Field(default_factory=list)
    time_points: list[str] = Field(default_factory=list)
    dataset_size_gb: float = 0.0
    s3_input_path: str = ""
    metadata_path: str = ""
    metadata: JobMetadata = Field(default_factory=JobMetadata)
    status: JobStatus = JobStatus.PENDING
    current_step: PipelineStep | None = None
    steps_completed: list[PipelineStep] = Field(default_factory=list)
    compute_tier: ComputeTier = ComputeTier.SMALL
    estimated_cost_usd: float = 0.0
    cost_so_far_usd: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    error_log: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline step results
# ---------------------------------------------------------------------------

class QCReport(BaseModel):
    sample_id: str
    total_reads: int = 0
    q30_pct: float = 0.0
    gc_pct: float = 0.0
    duplication_pct: float = 0.0
    adapter_pct: float = 0.0
    passed: bool = True
    flags: list[SampleFlag] = Field(default_factory=list)


class AlignmentStats(BaseModel):
    sample_id: str
    total_reads: int = 0
    mapped_reads: int = 0
    mapping_rate: float = 0.0
    unique_mapped: int = 0
    multi_mapped: int = 0
    unmapped: int = 0
    bam_path: str = ""


class DEGResult(BaseModel):
    gene_id: str
    gene_symbol: str = ""
    biotype: str = ""
    chromosome: str = ""
    log2fc: float = 0.0
    pvalue: float = 1.0
    fdr: float = 1.0
    mean_counts_a: float = 0.0
    mean_counts_b: float = 0.0
    significant: bool = False


class PathwayResult(BaseModel):
    term_id: str
    term_name: str = ""
    source: str = ""  # GO_BP, GO_MF, GO_CC, KEGG, GSEA
    gene_count: int = 0
    gene_ratio: str = ""
    bg_ratio: str = ""
    pvalue: float = 1.0
    p_adjusted: float = 1.0
    genes: list[str] = Field(default_factory=list)
    direction: str = ""  # up, down, mixed


class AnnotatedGene(BaseModel):
    gene_id: str
    gene_symbol: str = ""
    biotype: str = ""
    chromosome: str = ""
    start: int = 0
    end: int = 0
    description: str = ""
    go_bp: list[str] = Field(default_factory=list)
    go_mf: list[str] = Field(default_factory=list)
    go_cc: list[str] = Field(default_factory=list)
    kegg_pathways: list[str] = Field(default_factory=list)
    subcellular_localization: str = ""
    disease_associations: list[str] = Field(default_factory=list)
    drug_targets: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Agent message format
# ---------------------------------------------------------------------------

class AgentMessage(BaseModel):
    type: str = "status_update"  # status_update | step_complete | error | result | question
    step: str = ""
    job_id: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    summary: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    next_action: str = ""
    requires_attention: bool = False
    s3_outputs: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------

class Checkpoint(BaseModel):
    job_id: str
    step: PipelineStep
    sample_id: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    output_s3_path: str = ""
    metrics: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Compute selection
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Transcript-level quantification (Salmon)
# ---------------------------------------------------------------------------

class TranscriptQuantResult(BaseModel):
    transcript_id: str
    gene_id: str = ""
    gene_symbol: str = ""
    tpm: float = 0.0
    num_reads: float = 0.0
    effective_length: float = 0.0


# ---------------------------------------------------------------------------
# WGCNA co-expression modules
# ---------------------------------------------------------------------------

class WGCNAModule(BaseModel):
    module_id: str  # e.g. "ME_turquoise"
    color: str = ""
    n_genes: int = 0
    hub_genes: list[str] = Field(default_factory=list)
    eigengene_cor_trait: float = 0.0  # correlation with trait
    eigengene_pvalue: float = 1.0
    top_go_term: str = ""
    top_kegg_pathway: str = ""
    genes: list[str] = Field(default_factory=list)


class WGCNAEdge(BaseModel):
    source: str
    target: str
    weight: float = 0.0
    module: str = ""


# ---------------------------------------------------------------------------
# Cell type deconvolution
# ---------------------------------------------------------------------------

class CellTypeEstimate(BaseModel):
    sample_id: str
    condition: str = ""
    cell_type: str = ""
    fraction: float = 0.0
    pvalue: float = 1.0


# ---------------------------------------------------------------------------
# Compute selection
# ---------------------------------------------------------------------------

class ComputeEstimate(BaseModel):
    instance_type: str
    n_instances: int = 1
    vcpu_total: int = 0
    ram_gb_total: int = 0
    estimated_runtime_hours: float = 0.0
    estimated_cost_usd: float = 0.0
    use_spot: bool = True
    use_batch_array: bool = False
