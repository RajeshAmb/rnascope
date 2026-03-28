"""All 14 Anthropic API tool definitions for the RNAscope orchestrator."""

TOOL_DEFINITIONS: list[dict] = [
    # 1. Upload Validator
    {
        "name": "upload_validator",
        "description": (
            "Validate uploaded FASTQ files in S3: check checksums, detect "
            "paired-end vs single-end layout, estimate dataset size, and "
            "detect species from filenames or a kraken2 subsample."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Unique identifier for this analysis job.",
                },
                "s3_bucket": {
                    "type": "string",
                    "description": "S3 bucket containing the raw FASTQ files.",
                },
                "file_list": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of S3 keys for all FASTQ files to validate.",
                },
            },
            "required": ["job_id", "s3_bucket", "file_list"],
        },
    },
    # 2. Compute Selector
    {
        "name": "compute_selector",
        "description": (
            "Select the optimal AWS compute tier based on dataset size and "
            "sample count. Returns instance type, cost estimate, and whether "
            "to use Spot or Batch array jobs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dataset_size_gb": {
                    "type": "number",
                    "description": "Total dataset size in gigabytes.",
                },
                "n_samples": {
                    "type": "integer",
                    "description": "Number of samples in the dataset.",
                },
            },
            "required": ["dataset_size_gb", "n_samples"],
        },
    },
    # 3. QC Agent
    {
        "name": "run_qc_agent",
        "description": (
            "Run the quality control pipeline: FastQC on all samples in "
            "parallel, MultiQC aggregation, Trimmomatic adapter/quality "
            "trimming. Returns per-sample QC metrics and flagged samples."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "sample_list": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of sample IDs to process.",
                },
                "s3_input_path": {
                    "type": "string",
                    "description": "S3 prefix containing the FASTQ files.",
                },
            },
            "required": ["job_id", "sample_list", "s3_input_path"],
        },
    },
    # 4. Alignment Agent
    {
        "name": "run_alignment_agent",
        "description": (
            "Run STAR alignment on all samples. Includes rRNA depletion via "
            "SortMeRNA, STAR 2-pass alignment, BAM sorting, and samtools "
            "flagstat QC. Supports parallel processing via AWS Batch."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "sample_list": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "genome": {
                    "type": "string",
                    "description": "Reference genome identifier (e.g. GRCh38, mm39).",
                },
                "gtf": {
                    "type": "string",
                    "description": "S3 path to the GTF annotation file.",
                },
            },
            "required": ["job_id", "sample_list", "genome", "gtf"],
        },
    },
    # 5. Quantification Agent
    {
        "name": "run_quantification_agent",
        "description": (
            "Run featureCounts on aligned BAM files to produce a raw gene "
            "count matrix (genes x samples). Supports multi-mapped reads "
            "and all Ensembl biotypes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "bam_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "S3 paths to sorted BAM files.",
                },
                "gtf": {
                    "type": "string",
                    "description": "S3 path to the GTF annotation file.",
                },
            },
            "required": ["job_id", "bam_paths", "gtf"],
        },
    },
    # 6. DEG Agent
    {
        "name": "run_deg_agent",
        "description": (
            "Run differential gene expression analysis using DESeq2 (primary) "
            "and edgeR (validation). Returns full DE results table with gene "
            "symbols, biotypes, fold changes, p-values, and FDR."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "count_matrix": {
                    "type": "string",
                    "description": "S3 path to the raw count matrix CSV.",
                },
                "metadata": {
                    "type": "string",
                    "description": "S3 path to the sample metadata CSV.",
                },
                "design_formula": {
                    "type": "string",
                    "description": "R-style design formula (e.g. '~ condition' or '~ condition + batch').",
                },
            },
            "required": ["job_id", "count_matrix", "metadata", "design_formula"],
        },
    },
    # 7. Annotation Agent
    {
        "name": "run_annotation_agent",
        "description": (
            "Annotate DE genes with biotype, chromosomal location, GO terms, "
            "KEGG pathways, subcellular localization, disease associations "
            "(DisGeNET), and drug target status (DGIdb)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "gene_list": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of Ensembl gene IDs to annotate.",
                },
                "species": {
                    "type": "string",
                    "description": "Species (human, mouse, rat, etc.).",
                },
            },
            "required": ["job_id", "gene_list", "species"],
        },
    },
    # 8. Pathway Agent
    {
        "name": "run_pathway_agent",
        "description": (
            "Run pathway enrichment analysis: GO over-representation (BP, MF, CC), "
            "KEGG enrichment (up/down separate), and GSEA. Uses clusterProfiler."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "deg_results": {
                    "type": "string",
                    "description": "S3 path to the DEG results JSON.",
                },
                "species": {"type": "string"},
                "ontologies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Which analyses to run: GO_BP, GO_MF, GO_CC, KEGG, GSEA.",
                },
            },
            "required": ["job_id", "deg_results", "species", "ontologies"],
        },
    },
    # 9. Interpretation Agent
    {
        "name": "run_interpretation_agent",
        "description": (
            "Generate AI biological interpretation of the RNA-seq results. "
            "Produces: executive summary, mechanistic narrative, hypotheses, "
            "recommended experiments, therapeutic relevance, literature context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "deg_results": {
                    "type": "string",
                    "description": "S3 path to the DEG results JSON.",
                },
                "pathway_results": {
                    "type": "string",
                    "description": "S3 path to the pathway enrichment results JSON.",
                },
                "metadata": {
                    "type": "object",
                    "description": "Sample metadata including tissue type and disease context.",
                },
            },
            "required": ["job_id", "deg_results", "pathway_results", "metadata"],
        },
    },
    # 10. Report Agent
    {
        "name": "run_report_agent",
        "description": (
            "Generate a publication-ready PDF report containing all analysis "
            "results: QC summary, volcano plot, PCA plot, heatmap, pathway "
            "charts, DEG tables, and AI interpretation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "all_results": {
                    "type": "object",
                    "description": (
                        "Dictionary containing S3 paths to all pipeline outputs: "
                        "qc_report, alignment_stats, count_matrix, deg_results, "
                        "annotation, pathway_results, interpretation."
                    ),
                },
            },
            "required": ["job_id", "all_results"],
        },
    },
    # 11. Slack Notification
    {
        "name": "notify_slack",
        "description": "Send a notification message to a Slack channel with optional file attachments.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "channel": {
                    "type": "string",
                    "description": "Slack channel name or ID.",
                },
                "message": {"type": "string"},
                "attachments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "S3 paths to files to attach.",
                },
            },
            "required": ["job_id", "channel", "message"],
        },
    },
    # 12. Email Notification
    {
        "name": "notify_email",
        "description": "Send an email notification to the researcher with optional attachments.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "recipient": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "attachments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "S3 paths to files to attach.",
                },
            },
            "required": ["job_id", "recipient", "subject", "body"],
        },
    },
    # 13. Get Job Status
    {
        "name": "get_job_status",
        "description": (
            "Retrieve the current status of a pipeline job including current "
            "step, completion percentage, cost, and any errors."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
            },
            "required": ["job_id"],
        },
    },
    # 14. Checkpoint Save
    {
        "name": "checkpoint_save",
        "description": (
            "Save a pipeline checkpoint to Redis and S3 for recovery. "
            "Stores step name, sample ID, output paths, and metrics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "step": {
                    "type": "string",
                    "description": "Pipeline step name.",
                },
                "state_dict": {
                    "type": "object",
                    "description": "Arbitrary state to checkpoint.",
                },
            },
            "required": ["job_id", "step", "state_dict"],
        },
    },
    # 15. Checkpoint Restore
    {
        "name": "checkpoint_restore",
        "description": "Restore a pipeline checkpoint from Redis/S3. Returns null if no checkpoint exists.",
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "step": {"type": "string"},
            },
            "required": ["job_id", "step"],
        },
    },
    # 16. Transcript Quantification (Salmon)
    {
        "name": "run_transcript_quant_agent",
        "description": (
            "Run Salmon for transcript-level quantification. Produces TPM and "
            "read counts per transcript and per gene, enabling isoform-level "
            "analysis and differential transcript usage."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "sample_list": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "s3_input_path": {
                    "type": "string",
                    "description": "S3 prefix with trimmed FASTQ files.",
                },
                "species": {"type": "string"},
                "transcriptome_index": {
                    "type": "string",
                    "description": "S3 path to Salmon index. Built automatically if not provided.",
                },
            },
            "required": ["job_id", "sample_list", "s3_input_path", "species"],
        },
    },
    # 17. WGCNA Co-expression Network
    {
        "name": "run_wgcna_agent",
        "description": (
            "Run Weighted Gene Co-expression Network Analysis (WGCNA). "
            "Identifies co-expression modules, hub genes, module-trait "
            "correlations, and enriched pathways per module. Also outputs "
            "network edges for visualization."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "count_matrix": {
                    "type": "string",
                    "description": "S3 path to normalized count matrix.",
                },
                "metadata": {
                    "type": "string",
                    "description": "S3 path to sample metadata CSV.",
                },
                "species": {"type": "string"},
                "min_module_size": {
                    "type": "integer",
                    "description": "Minimum genes per module (default 30).",
                },
                "soft_power": {
                    "type": "integer",
                    "description": "Soft thresholding power. Auto-detected if 0.",
                },
            },
            "required": ["job_id", "count_matrix", "metadata", "species"],
        },
    },
    # 18. Cell Type Deconvolution
    {
        "name": "run_deconvolution_agent",
        "description": (
            "Run cell type deconvolution on bulk RNA-seq data using "
            "CIBERSORTx or MuSiC. Estimates the proportion of each cell "
            "type in every sample. For non-human species or plants, uses "
            "custom signature matrices if available."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"},
                "count_matrix": {
                    "type": "string",
                    "description": "S3 path to normalized count matrix.",
                },
                "species": {"type": "string"},
                "tissue_type": {
                    "type": "string",
                    "description": "Tissue type to select signature matrix.",
                },
                "method": {
                    "type": "string",
                    "description": "Deconvolution method: cibersortx, music, xcell, immuneceliai.",
                },
                "signature_matrix": {
                    "type": "string",
                    "description": "S3 path to custom signature matrix (optional).",
                },
            },
            "required": ["job_id", "count_matrix", "species"],
        },
    },
]
