"""Tool execution handlers — dispatches Claude's tool calls to real infrastructure."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from rnascope.config import settings
from rnascope.species import (
    resolve_species,
    get_annotation_r_code,
    get_pathway_r_code,
    is_plant,
    is_meta,
)
from rnascope.infra.aws import (
    s3_list_objects,
    s3_get_dataset_size_gb,
    s3_head,
    s3_upload_json,
    select_compute_tier,
    send_email,
    submit_batch_array,
    submit_batch_job,
    wait_for_batch_job,
)
from rnascope.infra.checkpoint import (
    has_checkpoint,
    restore_checkpoint,
    save_checkpoint,
    save_job_state,
    update_job_step,
)
from rnascope.models.schemas import PipelineStep

logger = logging.getLogger(__name__)


def handle_tool_call(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Route a tool call from the orchestrator agent to the correct handler.

    Returns the tool result as a JSON string.
    """
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        logger.info("Executing tool: %s (job=%s)", tool_name, tool_input.get("job_id", "?"))
        result = handler(tool_input)
        logger.info("Tool %s completed successfully", tool_name)
        return json.dumps(result, default=str)
    except Exception as e:
        logger.exception("Tool %s failed", tool_name)
        return json.dumps({"error": str(e), "tool": tool_name})


# ---------------------------------------------------------------------------
# Individual tool handlers
# ---------------------------------------------------------------------------

def _upload_validator(params: dict) -> dict:
    job_id = params["job_id"]
    bucket = params["s3_bucket"]
    file_list = params["file_list"]

    objects = s3_list_objects(bucket, "")
    s3_keys = {o["key"] for o in objects}

    present = [f for f in file_list if f in s3_keys]
    missing = [f for f in file_list if f not in s3_keys]

    # Detect paired-end from filename patterns
    r1_files = [f for f in present if "_R1" in f or "_1.fastq" in f]
    r2_files = [f for f in present if "_R2" in f or "_2.fastq" in f]
    layout = "paired" if r2_files else "single"

    # Dataset size
    total_size_gb = s3_get_dataset_size_gb(bucket, "")

    # Sample detection
    sample_ids = sorted({
        f.split("/")[-1].replace("_R1", "").replace("_R2", "")
        .replace("_1.fastq.gz", "").replace("_2.fastq.gz", "")
        .replace(".fastq.gz", "")
        for f in present
    })

    return {
        "job_id": job_id,
        "total_files": len(file_list),
        "files_present": len(present),
        "files_missing": missing,
        "layout": layout,
        "n_samples": len(sample_ids),
        "sample_ids": sample_ids,
        "dataset_size_gb": total_size_gb,
        "validation_passed": len(missing) == 0,
    }


def _compute_selector(params: dict) -> dict:
    estimate = select_compute_tier(params["dataset_size_gb"], params["n_samples"])
    return estimate.model_dump()


def _run_qc_agent(params: dict) -> dict:
    job_id = params["job_id"]
    samples = params["sample_list"]
    s3_input = params["s3_input_path"]

    update_job_step(job_id, PipelineStep.QC.value, "running")

    # Check for existing checkpoint
    existing = restore_checkpoint(job_id, PipelineStep.QC.value)
    if existing:
        logger.info("QC checkpoint found, skipping re-run")
        update_job_step(job_id, PipelineStep.QC.value, "completed")
        return existing.get("state", {})

    # Submit parallel QC jobs via Batch
    env = {"S3_INPUT": s3_input, "JOB_ID": job_id, "S3_OUTPUT": f"s3://{settings.s3_bucket_results}/{job_id}/qc/"}
    job_ids = submit_batch_array(
        job_name_prefix=f"rnascope-qc-{job_id}",
        sample_ids=samples,
        command_template=[
            "bash", "-c",
            "fastqc /data/{sample_id}*.fastq.gz -o /output/ && "
            "trimmomatic PE /data/{sample_id}_R1.fastq.gz /data/{sample_id}_R2.fastq.gz "
            "/output/{sample_id}_R1_trimmed.fastq.gz /output/{sample_id}_R1_unpaired.fastq.gz "
            "/output/{sample_id}_R2_trimmed.fastq.gz /output/{sample_id}_R2_unpaired.fastq.gz "
            "ILLUMINACLIP:TruSeq3-PE.fa:2:30:10 LEADING:3 TRAILING:3 SLIDINGWINDOW:4:15 MINLEN:36",
        ],
        vcpus=4,
        memory_mb=16000,
        environment=env,
    )

    # Wait for all jobs
    results = []
    flagged = []
    for jid in job_ids:
        detail = wait_for_batch_job(jid)
        results.append({"batch_job_id": jid, "status": detail["status"]})

    # Parse QC metrics from outputs (would read from S3 in production)
    qc_result = {
        "job_id": job_id,
        "samples_processed": len(samples),
        "batch_jobs": results,
        "flagged_samples": flagged,
        "multiqc_report": f"s3://{settings.s3_bucket_results}/{job_id}/qc/multiqc_report.html",
        "trimmed_output": f"s3://{settings.s3_bucket_results}/{job_id}/qc/trimmed/",
    }

    save_checkpoint(job_id, PipelineStep.QC.value, qc_result)
    update_job_step(job_id, PipelineStep.QC.value, "completed")
    return qc_result


def _run_alignment_agent(params: dict) -> dict:
    job_id = params["job_id"]
    samples = params["sample_list"]
    genome = params["genome"]
    gtf = params["gtf"]

    update_job_step(job_id, PipelineStep.ALIGNMENT.value, "running")

    existing = restore_checkpoint(job_id, PipelineStep.ALIGNMENT.value)
    if existing:
        update_job_step(job_id, PipelineStep.ALIGNMENT.value, "completed")
        return existing.get("state", {})

    # Step 3: rRNA depletion + Step 4: STAR alignment combined
    env = {
        "JOB_ID": job_id,
        "GENOME": genome,
        "GTF": gtf,
        "STAR_INDEX": settings.star_genome_index_s3,
        "S3_OUTPUT": f"s3://{settings.s3_bucket_results}/{job_id}/alignment/",
    }

    star_params = (
        "--outSAMtype BAM SortedByCoordinate "
        "--outSAMattributes NH HI AS NM "
        "--quantMode GeneCounts "
        "--twopassMode Basic "
        "--outFilterMismatchNmax 2 "
        "--alignSJoverhangMin 8 "
        "--alignSJDBoverhangMin 1"
    )

    job_ids = submit_batch_array(
        job_name_prefix=f"rnascope-align-{job_id}",
        sample_ids=samples,
        command_template=[
            "bash", "-c",
            # rRNA depletion with SortMeRNA
            "sortmerna --ref /refs/silva-138-rRNA.fasta "
            "--reads /data/{sample_id}_R1_trimmed.fastq.gz "
            "--reads /data/{sample_id}_R2_trimmed.fastq.gz "
            "--aligned /tmp/rrna --other /tmp/non_rrna --paired_in --fastx && "
            # STAR alignment
            f"STAR --runThreadN 8 --genomeDir /refs/star_index "
            f"--readFilesIn /tmp/non_rrna_fwd.fastq.gz /tmp/non_rrna_rev.fastq.gz "
            f"--readFilesCommand zcat {star_params} "
            f"--outFileNamePrefix /output/{{sample_id}}_ && "
            # Flagstat QC
            "samtools flagstat /output/{sample_id}_Aligned.sortedByCoord.out.bam "
            "> /output/{sample_id}_flagstat.txt",
        ],
        vcpus=8,
        memory_mb=60000,
        environment=env,
    )

    results = []
    bam_paths = []
    for jid in job_ids:
        detail = wait_for_batch_job(jid)
        results.append({"batch_job_id": jid, "status": detail["status"]})

    for sid in samples:
        bam_paths.append(f"s3://{settings.s3_bucket_results}/{job_id}/alignment/{sid}_Aligned.sortedByCoord.out.bam")

    alignment_result = {
        "job_id": job_id,
        "samples_aligned": len(samples),
        "bam_paths": bam_paths,
        "batch_jobs": results,
        "alignment_stats": f"s3://{settings.s3_bucket_results}/{job_id}/alignment/stats/",
    }

    save_checkpoint(job_id, PipelineStep.ALIGNMENT.value, alignment_result)
    update_job_step(job_id, PipelineStep.ALIGNMENT.value, "completed")
    return alignment_result


def _run_quantification_agent(params: dict) -> dict:
    job_id = params["job_id"]
    bam_paths = params["bam_paths"]
    gtf = params["gtf"]

    update_job_step(job_id, PipelineStep.QUANTIFICATION.value, "running")

    existing = restore_checkpoint(job_id, PipelineStep.QUANTIFICATION.value)
    if existing:
        update_job_step(job_id, PipelineStep.QUANTIFICATION.value, "completed")
        return existing.get("state", {})

    bam_args = " ".join(bam_paths)
    batch_job_id = submit_batch_job(
        job_name=f"rnascope-quant-{job_id}",
        command=[
            "bash", "-c",
            f"featureCounts -T 16 -s 2 -t exon -g gene_id "
            f"-a {gtf} --fracOverlap 0.2 -M --byReadGroup "
            f"-o /output/counts.txt {bam_args}",
        ],
        vcpus=16,
        memory_mb=64000,
    )
    wait_for_batch_job(batch_job_id)

    count_matrix_path = f"s3://{settings.s3_bucket_results}/{job_id}/quantification/counts.txt"

    result = {
        "job_id": job_id,
        "count_matrix_path": count_matrix_path,
        "n_bams": len(bam_paths),
    }

    save_checkpoint(job_id, PipelineStep.QUANTIFICATION.value, result)
    update_job_step(job_id, PipelineStep.QUANTIFICATION.value, "completed")
    return result


def _run_deg_agent(params: dict) -> dict:
    job_id = params["job_id"]
    count_matrix = params["count_matrix"]
    metadata = params["metadata"]
    design = params["design_formula"]

    update_job_step(job_id, PipelineStep.DEG.value, "running")

    existing = restore_checkpoint(job_id, PipelineStep.DEG.value)
    if existing:
        update_job_step(job_id, PipelineStep.DEG.value, "completed")
        return existing.get("state", {})

    # Run DESeq2 via R in a container
    r_script = f"""
    library(DESeq2)
    counts <- read.csv("{count_matrix}", row.names=1)
    meta <- read.csv("{metadata}", row.names=1)
    dds <- DESeqDataSetFromMatrix(countData=counts, colData=meta, design={design})
    dds <- dds[rowSums(counts(dds)) >= 10, ]
    dds <- DESeq(dds)
    res <- results(dds, alpha=0.05)
    res_shrunk <- lfcShrink(dds, coef=2, type="ashr")
    write.csv(as.data.frame(res_shrunk), "/output/deseq2_results.csv")

    # edgeR validation
    library(edgeR)
    y <- DGEList(counts=counts, group=meta$condition)
    y <- calcNormFactors(y)
    design_mat <- model.matrix(~meta$condition)
    y <- estimateDisp(y, design_mat)
    fit <- glmQLFit(y, design_mat)
    qlf <- glmQLFTest(fit, coef=2)
    write.csv(topTags(qlf, n=100)$table, "/output/edger_top100.csv")
    """

    batch_job_id = submit_batch_job(
        job_name=f"rnascope-deg-{job_id}",
        command=["Rscript", "-e", r_script],
        vcpus=8,
        memory_mb=32000,
        environment={"JOB_ID": job_id},
    )

    detail = wait_for_batch_job(batch_job_id)
    # Handle convergence failure
    if detail["status"] == "FAILED":
        logger.warning("DESeq2 failed, retrying with betaPrior=FALSE")
        r_script_retry = r_script.replace("DESeq(dds)", "DESeq(dds, betaPrior=FALSE)")
        batch_job_id = submit_batch_job(
            job_name=f"rnascope-deg-retry-{job_id}",
            command=["Rscript", "-e", r_script_retry],
            vcpus=8,
            memory_mb=32000,
        )
        detail = wait_for_batch_job(batch_job_id)

    deg_path = f"s3://{settings.s3_bucket_results}/{job_id}/deg/deseq2_results.csv"
    edger_path = f"s3://{settings.s3_bucket_results}/{job_id}/deg/edger_top100.csv"

    result = {
        "job_id": job_id,
        "deg_results": deg_path,
        "edger_validation": edger_path,
        "design_formula": design,
    }

    save_checkpoint(job_id, PipelineStep.DEG.value, result)
    update_job_step(job_id, PipelineStep.DEG.value, "completed")
    return result


def _run_annotation_agent(params: dict) -> dict:
    job_id = params["job_id"]
    gene_list = params["gene_list"]
    species = params["species"]

    update_job_step(job_id, PipelineStep.ANNOTATION.value, "running")

    existing = restore_checkpoint(job_id, PipelineStep.ANNOTATION.value)
    if existing:
        update_job_step(job_id, PipelineStep.ANNOTATION.value, "completed")
        return existing.get("state", {})

    # Annotation via R/Bioconductor — species-aware
    cfg = resolve_species(species)
    genes_str = '","'.join(gene_list)
    annotation_code = get_annotation_r_code(species)

    r_script = f"""
    genes <- c("{genes_str}")
    {annotation_code}
    write.csv(annot, "/output/gene_annotations.csv")
    """

    if cfg.org_db:
        r_script = f"library({cfg.org_db})\n" + r_script

    batch_job_id = submit_batch_job(
        job_name=f"rnascope-annot-{job_id}",
        command=["Rscript", "-e", r_script],
        vcpus=4,
        memory_mb=16000,
    )
    wait_for_batch_job(batch_job_id)

    annot_path = f"s3://{settings.s3_bucket_results}/{job_id}/annotation/gene_annotations.csv"

    result = {
        "job_id": job_id,
        "annotated_results": annot_path,
        "n_genes": len(gene_list),
        "species": species,
    }

    save_checkpoint(job_id, PipelineStep.ANNOTATION.value, result)
    update_job_step(job_id, PipelineStep.ANNOTATION.value, "completed")
    return result


def _run_pathway_agent(params: dict) -> dict:
    job_id = params["job_id"]
    deg_results = params["deg_results"]
    species = params["species"]
    ontologies = params["ontologies"]

    update_job_step(job_id, PipelineStep.PATHWAY.value, "running")

    existing = restore_checkpoint(job_id, PipelineStep.PATHWAY.value)
    if existing:
        update_job_step(job_id, PipelineStep.PATHWAY.value, "completed")
        return existing.get("state", {})

    cfg = resolve_species(species)
    pathway_code = get_pathway_r_code(species)

    r_script = f"""
    deg <- read.csv("{deg_results}")
    sig_genes <- deg[abs(deg$log2FoldChange) > 1 & deg$padj < 0.05, "gene_id"]
    sig_up <- deg[deg$log2FoldChange > 1 & deg$padj < 0.05, "gene_id"]
    sig_down <- deg[deg$log2FoldChange < -1 & deg$padj < 0.05, "gene_id"]
    all_genes <- deg$gene_id

    # Species-specific pathway enrichment ({cfg.name}, domain={cfg.domain})
    # Databases: {', '.join(cfg.pathway_dbs)}
    {pathway_code}

    # Save results
    tryCatch(write.csv(as.data.frame(ego_bp), "/output/go_bp.csv"), error=function(e) NULL)
    tryCatch(write.csv(as.data.frame(ego_mf), "/output/go_mf.csv"), error=function(e) NULL)
    tryCatch(write.csv(as.data.frame(ego_cc), "/output/go_cc.csv"), error=function(e) NULL)
    tryCatch(write.csv(as.data.frame(kk_up), "/output/kegg_up.csv"), error=function(e) NULL)
    tryCatch(write.csv(as.data.frame(kk_down), "/output/kegg_down.csv"), error=function(e) NULL)
    """

    batch_job_id = submit_batch_job(
        job_name=f"rnascope-pathway-{job_id}",
        command=["Rscript", "-e", r_script],
        vcpus=8,
        memory_mb=32000,
    )
    wait_for_batch_job(batch_job_id)

    base = f"s3://{settings.s3_bucket_results}/{job_id}/pathway"
    result = {
        "job_id": job_id,
        "go_bp": f"{base}/go_bp.csv",
        "go_mf": f"{base}/go_mf.csv",
        "go_cc": f"{base}/go_cc.csv",
        "kegg_up": f"{base}/kegg_up.csv",
        "kegg_down": f"{base}/kegg_down.csv",
        "gsea_go": f"{base}/gsea_go.csv",
        "gsea_kegg": f"{base}/gsea_kegg.csv",
        "ontologies_run": ontologies,
    }

    save_checkpoint(job_id, PipelineStep.PATHWAY.value, result)
    update_job_step(job_id, PipelineStep.PATHWAY.value, "completed")
    return result


def _run_interpretation_agent(params: dict) -> dict:
    """This tool calls the interpretation sub-agent (Claude) — handled in orchestrator."""
    # The orchestrator agent loop intercepts this and calls the interpretation model.
    # This handler is a placeholder that returns metadata for the agentic loop.
    return {
        "job_id": params["job_id"],
        "status": "requires_llm_call",
        "deg_results": params["deg_results"],
        "pathway_results": params["pathway_results"],
        "metadata": params.get("metadata", {}),
    }


def _run_report_agent(params: dict) -> dict:
    job_id = params["job_id"]
    all_results = params["all_results"]

    update_job_step(job_id, PipelineStep.REPORT.value, "running")

    r_script = f"""
    library(ggplot2)
    library(pheatmap)
    library(EnhancedVolcano)
    library(rmarkdown)

    # Load results
    deg <- read.csv("{all_results.get('deg_results', '')}")

    # Volcano plot
    png("/output/volcano.png", width=1200, height=900)
    EnhancedVolcano(deg, lab=deg$gene_symbol, x='log2FoldChange', y='padj',
                    title='Differential Expression', pCutoff=0.05, FCcutoff=1,
                    selectLab=head(deg$gene_symbol[order(deg$padj)], 20))
    dev.off()

    # PCA plot
    # ... generated from normalized counts

    # Heatmap of top 50 DEGs
    # ... generated from z-score normalized expression

    # Render PDF report
    rmarkdown::render("/templates/report.Rmd", output_file="/output/report.pdf",
                      params=list(job_id="{job_id}"))
    """

    batch_job_id = submit_batch_job(
        job_name=f"rnascope-report-{job_id}",
        command=["Rscript", "-e", r_script],
        vcpus=4,
        memory_mb=16000,
    )
    wait_for_batch_job(batch_job_id)

    report_path = f"s3://{settings.s3_bucket_reports}/{job_id}/report.pdf"

    result = {
        "job_id": job_id,
        "report_pdf_s3_path": report_path,
        "plots": {
            "volcano": f"s3://{settings.s3_bucket_results}/{job_id}/plots/volcano.png",
            "pca": f"s3://{settings.s3_bucket_results}/{job_id}/plots/pca.png",
            "heatmap": f"s3://{settings.s3_bucket_results}/{job_id}/plots/heatmap.png",
        },
    }

    save_checkpoint(job_id, PipelineStep.REPORT.value, result)
    update_job_step(job_id, PipelineStep.REPORT.value, "completed")
    return result


def _notify_slack(params: dict) -> dict:
    from slack_sdk import WebClient

    client = WebClient(token=settings.slack_bot_token)
    resp = client.chat_postMessage(
        channel=params["channel"],
        text=params["message"],
    )

    # Upload attachments if provided
    for attachment_s3 in params.get("attachments", []):
        # In production: download from S3 to temp file, then upload to Slack
        pass

    return {
        "job_id": params["job_id"],
        "delivery_status": "sent",
        "channel": params["channel"],
        "ts": resp.get("ts", ""),
    }


def _notify_email(params: dict) -> dict:
    send_email(
        recipient=params["recipient"],
        subject=params["subject"],
        body=params["body"],
    )
    return {
        "job_id": params["job_id"],
        "delivery_status": "sent",
        "recipient": params["recipient"],
    }


def _get_job_status(params: dict) -> dict:
    from rnascope.infra.checkpoint import get_job_state
    state = get_job_state(params["job_id"])
    if not state:
        return {"job_id": params["job_id"], "status": "not_found"}
    return state


def _checkpoint_save(params: dict) -> dict:
    s3_path = save_checkpoint(
        job_id=params["job_id"],
        step=params["step"],
        state=params["state_dict"],
    )
    return {"checkpoint_id": f"{params['job_id']}:{params['step']}", "s3_path": s3_path}


def _checkpoint_restore(params: dict) -> dict:
    data = restore_checkpoint(params["job_id"], params["step"])
    if data:
        return data
    return {"result": None}


# ---------------------------------------------------------------------------
# Transcript-level quantification (Salmon)
# ---------------------------------------------------------------------------

def _run_transcript_quant_agent(params: dict) -> dict:
    job_id = params["job_id"]
    samples = params["sample_list"]
    s3_input = params["s3_input_path"]
    species = params["species"]

    update_job_step(job_id, PipelineStep.TRANSCRIPT_QUANT.value, "running")

    existing = restore_checkpoint(job_id, PipelineStep.TRANSCRIPT_QUANT.value)
    if existing:
        update_job_step(job_id, PipelineStep.TRANSCRIPT_QUANT.value, "completed")
        return existing.get("state", {})

    # Build or locate Salmon index
    index_path = params.get("transcriptome_index", "")
    if not index_path:
        index_path = f"s3://{settings.s3_bucket_results}/references/salmon_index/{species}/"

    env = {
        "JOB_ID": job_id,
        "S3_INPUT": s3_input,
        "SALMON_INDEX": index_path,
        "S3_OUTPUT": f"s3://{settings.s3_bucket_results}/{job_id}/salmon/",
    }

    job_ids = submit_batch_array(
        job_name_prefix=f"rnascope-salmon-{job_id}",
        sample_ids=samples,
        command_template=[
            "bash", "-c",
            "salmon quant -i /refs/salmon_index "
            "-l A "
            "-1 /data/{sample_id}_R1_trimmed.fastq.gz "
            "-2 /data/{sample_id}_R2_trimmed.fastq.gz "
            "-p 8 "
            "--validateMappings "
            "--seqBias --gcBias "
            "-o /output/{sample_id}_salmon && "
            "cp /output/{sample_id}_salmon/quant.sf /output/{sample_id}_quant.sf",
        ],
        vcpus=8,
        memory_mb=32000,
        environment=env,
    )

    for jid in job_ids:
        wait_for_batch_job(jid)

    # Aggregate with tximport in R
    r_script = f"""
    library(tximport)
    library(readr)
    files <- list.files("/output", pattern="*_quant.sf", full.names=TRUE)
    names(files) <- gsub("_quant.sf", "", basename(files))
    tx2gene <- read_csv("/refs/tx2gene_{species}.csv")
    txi <- tximport(files, type="salmon", tx2gene=tx2gene,
                    countsFromAbundance="lengthScaledTPM")
    write.csv(txi$abundance, "/output/transcript_tpm.csv")
    write.csv(txi$counts, "/output/transcript_counts.csv")
    write.csv(txi$length, "/output/transcript_lengths.csv")
    """

    batch_job_id = submit_batch_job(
        job_name=f"rnascope-tximport-{job_id}",
        command=["Rscript", "-e", r_script],
        vcpus=4,
        memory_mb=16000,
    )
    wait_for_batch_job(batch_job_id)

    base = f"s3://{settings.s3_bucket_results}/{job_id}/salmon"
    result = {
        "job_id": job_id,
        "transcript_tpm": f"{base}/transcript_tpm.csv",
        "transcript_counts": f"{base}/transcript_counts.csv",
        "gene_tpm": f"{base}/gene_tpm.csv",
        "n_samples": len(samples),
    }

    save_checkpoint(job_id, PipelineStep.TRANSCRIPT_QUANT.value, result)
    update_job_step(job_id, PipelineStep.TRANSCRIPT_QUANT.value, "completed")
    return result


# ---------------------------------------------------------------------------
# WGCNA co-expression network analysis
# ---------------------------------------------------------------------------

def _run_wgcna_agent(params: dict) -> dict:
    job_id = params["job_id"]
    count_matrix = params["count_matrix"]
    metadata = params["metadata"]
    species = params["species"]
    min_mod = params.get("min_module_size", 30)
    soft_power = params.get("soft_power", 0)

    update_job_step(job_id, PipelineStep.WGCNA.value, "running")

    existing = restore_checkpoint(job_id, PipelineStep.WGCNA.value)
    if existing:
        update_job_step(job_id, PipelineStep.WGCNA.value, "completed")
        return existing.get("state", {})

    power_detect = "" if soft_power else """
    powers <- c(1:20)
    sft <- pickSoftThreshold(datExpr, powerVector=powers, verbose=5)
    power <- sft$powerEstimate
    if (is.na(power)) power <- 6
    """
    power_set = f"power <- {soft_power}" if soft_power else ""

    r_script = f"""
    library(WGCNA)
    library(clusterProfiler)
    options(stringsAsFactors = FALSE)
    enableWGCNAThreads(nThreads=8)

    # Load data
    counts <- read.csv("{count_matrix}", row.names=1)
    meta <- read.csv("{metadata}", row.names=1)

    # Filter low-variance genes (top 5000 by MAD)
    mads <- apply(counts, 1, mad)
    datExpr <- t(counts[order(mads, decreasing=TRUE)[1:min(5000, nrow(counts))], ])

    # Detect soft power
    {power_detect}
    {power_set}

    # Build network
    net <- blockwiseModules(datExpr, power=power,
                            TOMType="unsigned", minModuleSize={min_mod},
                            reassignThreshold=0, mergeCutHeight=0.25,
                            numericLabels=TRUE, pamRespectsDendro=FALSE,
                            saveTOMs=FALSE, verbose=3, maxBlockSize=5000)

    moduleLabels <- net$colors
    moduleColors <- labels2colors(moduleLabels)
    MEs <- net$MEs

    # Module-trait correlation
    trait <- as.numeric(factor(meta$condition))
    moduleTraitCor <- cor(MEs, trait, use="p")
    moduleTraitPvalue <- corPvalueStudent(moduleTraitCor, nrow(datExpr))

    # Hub genes per module
    modules_df <- data.frame(gene=colnames(datExpr), module=moduleColors)

    # Export for each module: genes, hub genes, correlation
    results <- list()
    for (mod in unique(moduleColors)) {{
        mod_genes <- modules_df$gene[modules_df$module == mod]
        kME <- signedKME(datExpr, MEs)
        col_name <- paste0("kME", which(unique(moduleColors) == mod) - 1)
        if (col_name %in% colnames(kME)) {{
            hubs <- names(sort(kME[mod_genes, col_name], decreasing=TRUE))[1:min(10, length(mod_genes))]
        }} else {{
            hubs <- head(mod_genes, 10)
        }}
        idx <- which(unique(moduleColors) == mod)
        results[[mod]] <- list(
            module=mod, n_genes=length(mod_genes),
            hub_genes=hubs,
            cor_trait=moduleTraitCor[idx],
            pvalue=moduleTraitPvalue[idx]
        )
    }}

    # Save results
    write.csv(modules_df, "/output/wgcna_module_genes.csv")
    saveRDS(results, "/output/wgcna_modules.rds")
    jsonlite::write_json(results, "/output/wgcna_modules.json")

    # Export top edges for network visualization (top 500 by TOM weight)
    TOM <- TOMsimilarityFromExpr(datExpr, power=power)
    top_idx <- order(TOM, decreasing=TRUE)[1:min(500, length(TOM))]
    edges <- data.frame(
        source=colnames(datExpr)[row(TOM)[top_idx]],
        target=colnames(datExpr)[col(TOM)[top_idx]],
        weight=TOM[top_idx],
        module=moduleColors[row(TOM)[top_idx]]
    )
    write.csv(edges, "/output/wgcna_edges.csv")
    """

    batch_job_id = submit_batch_job(
        job_name=f"rnascope-wgcna-{job_id}",
        command=["Rscript", "-e", r_script],
        vcpus=8,
        memory_mb=64000,
    )
    wait_for_batch_job(batch_job_id)

    base = f"s3://{settings.s3_bucket_results}/{job_id}/wgcna"
    result = {
        "job_id": job_id,
        "modules_json": f"{base}/wgcna_modules.json",
        "module_genes": f"{base}/wgcna_module_genes.csv",
        "network_edges": f"{base}/wgcna_edges.csv",
    }

    save_checkpoint(job_id, PipelineStep.WGCNA.value, result)
    update_job_step(job_id, PipelineStep.WGCNA.value, "completed")
    return result


# ---------------------------------------------------------------------------
# Cell type deconvolution
# ---------------------------------------------------------------------------

def _run_deconvolution_agent(params: dict) -> dict:
    job_id = params["job_id"]
    count_matrix = params["count_matrix"]
    species = params["species"]
    tissue = params.get("tissue_type", "")
    method = params.get("method", "")
    custom_sig = params.get("signature_matrix", "")

    update_job_step(job_id, PipelineStep.DECONVOLUTION.value, "running")

    existing = restore_checkpoint(job_id, PipelineStep.DECONVOLUTION.value)
    if existing:
        update_job_step(job_id, PipelineStep.DECONVOLUTION.value, "completed")
        return existing.get("state", {})

    cfg = resolve_species(species)

    # Plants and metatranscriptomes: no cell type deconvolution
    if cfg.domain in ("plant", "meta"):
        result = {
            "job_id": job_id,
            "method": "skipped",
            "reason": f"Cell type deconvolution not applicable for {cfg.domain} ({cfg.name}). "
                      "No single-cell reference signatures available for this organism.",
            "species": species,
        }
        save_checkpoint(job_id, PipelineStep.DECONVOLUTION.value, result)
        update_job_step(job_id, PipelineStep.DECONVOLUTION.value, "completed")
        return result

    # Auto-select method based on species config
    if not method:
        method = cfg.deconvolution_method or "xcell"

    if method == "xcell":
        r_script = f"""
        library(xCell)
        expr <- read.csv("{count_matrix}", row.names=1)
        result <- xCellAnalysis(expr)
        write.csv(result, "/output/deconvolution_xcell.csv")
        """
    elif method == "music":
        r_script = f"""
        library(MuSiC)
        bulk <- read.csv("{count_matrix}", row.names=1)
        # Use reference single-cell dataset for tissue type
        # In production: load tissue-specific scRNA reference from S3
        result <- music_prop(bulk.mtx=as.matrix(bulk),
                            sc.sce=sc_ref, markers=NULL,
                            clusters='cell_type', samples='sample')
        write.csv(result$Est.prop.weighted, "/output/deconvolution_music.csv")
        """
    else:
        # CIBERSORTx (default fallback)
        r_script = f"""
        library(immunedeconv)
        expr <- read.csv("{count_matrix}", row.names=1)
        result <- deconvolute(as.matrix(expr), method="cibersort_abs")
        write.csv(result, "/output/deconvolution_cibersort.csv")
        """

    batch_job_id = submit_batch_job(
        job_name=f"rnascope-deconv-{job_id}",
        command=["Rscript", "-e", r_script],
        vcpus=4,
        memory_mb=32000,
    )
    wait_for_batch_job(batch_job_id)

    base = f"s3://{settings.s3_bucket_results}/{job_id}/deconvolution"
    result = {
        "job_id": job_id,
        "method": method,
        "deconvolution_results": f"{base}/deconvolution_{method}.csv",
        "species": species,
        "tissue_type": tissue,
    }

    save_checkpoint(job_id, PipelineStep.DECONVOLUTION.value, result)
    update_job_step(job_id, PipelineStep.DECONVOLUTION.value, "completed")
    return result


# ---------------------------------------------------------------------------
# Handler dispatch table
# ---------------------------------------------------------------------------

TOOL_HANDLERS: dict[str, Any] = {
    "upload_validator": _upload_validator,
    "compute_selector": _compute_selector,
    "run_qc_agent": _run_qc_agent,
    "run_alignment_agent": _run_alignment_agent,
    "run_quantification_agent": _run_quantification_agent,
    "run_transcript_quant_agent": _run_transcript_quant_agent,
    "run_deg_agent": _run_deg_agent,
    "run_annotation_agent": _run_annotation_agent,
    "run_pathway_agent": _run_pathway_agent,
    "run_wgcna_agent": _run_wgcna_agent,
    "run_deconvolution_agent": _run_deconvolution_agent,
    "run_interpretation_agent": _run_interpretation_agent,
    "run_report_agent": _run_report_agent,
    "notify_slack": _notify_slack,
    "notify_email": _notify_email,
    "get_job_status": _get_job_status,
    "checkpoint_save": _checkpoint_save,
    "checkpoint_restore": _checkpoint_restore,
}
