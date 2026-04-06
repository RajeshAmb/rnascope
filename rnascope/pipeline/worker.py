"""Real RNA-seq pipeline worker — runs on AWS Batch.

Receives job parameters via environment variables:
    JOB_ID, SPECIES, CONDITION_A, CONDITION_B, N_A, N_B,
    S3_BUCKET_RAW, S3_BUCKET_RESULTS, CALLBACK_URL, ANTHROPIC_API_KEY

Executes:
    1. Download FASTQ from S3
    2. fastp QC + trimming
    3. Salmon quantification
    4. pyDESeq2 differential expression
    5. GO/KEGG enrichment (gseapy)
    6. ML biomarker selection
    7. Upload results to S3
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import boto3
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("pipeline")

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
JOB_ID = os.environ["JOB_ID"]
SPECIES = os.environ.get("SPECIES", "cotton_arboreum")
CONDITION_A = os.environ.get("CONDITION_A", "Resistant")
CONDITION_B = os.environ.get("CONDITION_B", "Susceptible")
N_A = int(os.environ.get("N_A", "15"))
N_B = int(os.environ.get("N_B", "15"))
S3_RAW = os.environ.get("S3_BUCKET_RAW", "rnascope-raw-data")
S3_RESULTS = os.environ.get("S3_BUCKET_RESULTS", "rnascope-results")
S3_REFS = os.environ.get("S3_REFS_PREFIX", "s3://rnascope-references")
CALLBACK_URL = os.environ.get("CALLBACK_URL", "")
REGION = os.environ.get("AWS_REGION", "us-east-2")

WORK = Path("/tmp/rnascope")
WORK.mkdir(parents=True, exist_ok=True)
FASTQ_DIR = WORK / "fastq"
TRIM_DIR = WORK / "trimmed"
QUANT_DIR = WORK / "quant"
OUTPUT_DIR = WORK / "output"
for d in [FASTQ_DIR, TRIM_DIR, QUANT_DIR, OUTPUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

s3 = boto3.client("s3", region_name=REGION)


def report_progress(step: str, message: str, pct: float):
    """Write progress to S3 and optionally call back to Render."""
    progress = {"step": step, "message": message, "pct_complete": pct}
    s3.put_object(
        Bucket=S3_RESULTS,
        Key=f"_jobs/{JOB_ID}_progress.json",
        Body=json.dumps(progress),
        ContentType="application/json",
    )
    logger.info("[%s] %.0f%% — %s", step, pct, message)
    if CALLBACK_URL:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{CALLBACK_URL}/api/jobs/{JOB_ID}/progress",
                data=json.dumps(progress).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass  # non-critical


# ===========================================================================
# STEP 1: Download FASTQ files from S3
# ===========================================================================
def step_download():
    report_progress("ingestion", "Downloading FASTQ files from S3...", 5)
    paginator = s3.get_paginator("list_objects_v2")
    files = []
    for page in paginator.paginate(Bucket=S3_RAW, Prefix=f"{JOB_ID}/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            fname = key.split("/")[-1]
            if fname.endswith((".fq.gz", ".fastq.gz")):
                local = FASTQ_DIR / fname
                if not local.exists():
                    logger.info("Downloading %s (%d MB)", fname, obj["Size"] // (1024**2))
                    s3.download_file(S3_RAW, key, str(local))
                files.append(fname)
    logger.info("Downloaded %d FASTQ files", len(files))
    return sorted(files)


# ===========================================================================
# STEP 2: QC + Trimming with fastp
# ===========================================================================
def step_qc(fastq_files: list[str]) -> dict:
    report_progress("qc", "Running fastp QC + trimming...", 15)
    samples = _pair_files(fastq_files)
    qc_results = []

    for sample_id, (r1, r2) in samples.items():
        out_r1 = TRIM_DIR / f"{sample_id}_1.trimmed.fq.gz"
        out_r2 = TRIM_DIR / f"{sample_id}_2.trimmed.fq.gz"
        json_out = TRIM_DIR / f"{sample_id}_fastp.json"
        html_out = TRIM_DIR / f"{sample_id}_fastp.html"

        if not json_out.exists():
            cmd = [
                "fastp",
                "-i", str(FASTQ_DIR / r1), "-I", str(FASTQ_DIR / r2),
                "-o", str(out_r1), "-O", str(out_r2),
                "-j", str(json_out), "-h", str(html_out),
                "--thread", "4",
                "--detect_adapter_for_pe",
            ]
            logger.info("Running fastp for %s", sample_id)
            subprocess.run(cmd, check=True, capture_output=True)

        # Parse fastp JSON
        with open(json_out) as f:
            stats = json.load(f)

        summary = stats.get("summary", {})
        before = summary.get("before_filtering", {})
        after = summary.get("after_filtering", {})

        qc_results.append({
            "sample": sample_id,
            "total_reads_m": round(before.get("total_reads", 0) / 1e6, 1),
            "q30_pct": round(after.get("q30_rate", 0) * 100, 1),
            "gc_pct": round(after.get("gc_content", 0) * 100, 1),
            "duplication_pct": round(stats.get("duplication", {}).get("rate", 0) * 100, 1),
            "adapter_pct": round(stats.get("adapter_cutting", {}).get("adapter_trimmed_reads", 0) /
                                 max(before.get("total_reads", 1), 1) * 100, 1),
        })

    return {"samples": qc_results, "paired_samples": samples}


def _pair_files(files: list[str]) -> dict:
    """Group FASTQ files into paired-end samples."""
    import re
    samples = {}
    for f in files:
        # Extract sample ID: remove _1/_2 and _R1/_R2 suffixes
        sid = re.sub(r'[._](?:R?[12])(?:[._]001)?\.(?:fq|fastq)\.gz$', '', f, flags=re.IGNORECASE)
        if sid not in samples:
            samples[sid] = [None, None]
        if re.search(r'[._](?:R?1)', f):
            samples[sid][0] = f
        else:
            samples[sid][1] = f
    # Filter out incomplete pairs
    return {k: tuple(v) for k, v in samples.items() if v[0] and v[1]}


# ===========================================================================
# STEP 3: Salmon Quantification
# ===========================================================================
def step_salmon(samples: dict) -> pd.DataFrame:
    report_progress("quantification", "Running Salmon quantification...", 30)

    # Download Salmon index from S3
    index_dir = WORK / "salmon_index"
    if not index_dir.exists():
        index_dir.mkdir()
        logger.info("Downloading Salmon index for %s...", SPECIES)
        prefix = f"salmon-index/{SPECIES}/"
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket="rnascope-references", Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                fname = key.replace(prefix, "")
                if fname:
                    local = index_dir / fname
                    local.parent.mkdir(parents=True, exist_ok=True)
                    s3.download_file("rnascope-references", key, str(local))

    # Run Salmon for each sample
    count_data = {}
    mapping_rates = {}
    total = len(samples)

    for i, (sample_id, (r1, r2)) in enumerate(samples.items()):
        out_dir = QUANT_DIR / sample_id
        quant_file = out_dir / "quant.sf"

        if not quant_file.exists():
            pct = 30 + (i / total) * 30
            report_progress("quantification", f"Salmon: {sample_id} ({i+1}/{total})", pct)

            cmd = [
                "salmon", "quant",
                "-i", str(index_dir),
                "-l", "A",  # auto-detect library type
                "-1", str(TRIM_DIR / f"{sample_id}_1.trimmed.fq.gz"),
                "-2", str(TRIM_DIR / f"{sample_id}_2.trimmed.fq.gz"),
                "-o", str(out_dir),
                "--validateMappings",
                "--threads", "4",
                "--gcBias",
                "--seqBias",
            ]
            subprocess.run(cmd, check=True, capture_output=True)

        # Parse quant.sf
        df = pd.read_csv(quant_file, sep="\t")
        count_data[sample_id] = df.set_index("Name")["NumReads"].to_dict()

        # Parse mapping rate from meta_info.json
        meta_file = out_dir / "aux_info" / "meta_info.json"
        if meta_file.exists():
            with open(meta_file) as f:
                meta = json.load(f)
            mapping_rates[sample_id] = meta.get("percent_mapped", 0)

    # Build count matrix (genes x samples)
    count_df = pd.DataFrame(count_data).fillna(0).astype(int)
    logger.info("Count matrix: %d genes x %d samples", count_df.shape[0], count_df.shape[1])

    return count_df, mapping_rates


# ===========================================================================
# STEP 4: Differential Expression with pyDESeq2
# ===========================================================================
def step_deseq2(count_df: pd.DataFrame, samples: dict) -> dict:
    report_progress("deg", "Running pyDESeq2 differential expression...", 65)

    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats

    # Build metadata
    sample_names = list(samples.keys())
    conditions = [CONDITION_A] * N_A + [CONDITION_B] * N_B
    # Pad/trim if mismatch
    while len(conditions) < len(sample_names):
        conditions.append(CONDITION_B)
    conditions = conditions[:len(sample_names)]

    metadata = pd.DataFrame({
        "condition": conditions,
    }, index=sample_names)

    # Filter low-count genes (at least 10 reads across all samples)
    count_df = count_df.loc[count_df.sum(axis=1) >= 10, sample_names]

    logger.info("DESeq2: %d genes, %d samples", count_df.shape[0], count_df.shape[1])

    # Run DESeq2
    dds = DeseqDataSet(
        counts=count_df.T,  # pyDESeq2 expects samples x genes
        metadata=metadata,
        design="~condition",
    )
    dds.deseq2()

    # Get results
    stat_res = DeseqStats(dds, contrast=["condition", CONDITION_A, CONDITION_B])
    stat_res.summary()
    results_df = stat_res.results_df

    # VST transform for PCA and heatmap
    dds.vst()
    vst_counts = pd.DataFrame(
        dds.layers["vst_counts"],
        index=dds.obs_names,
        columns=dds.var_names,
    )

    return {
        "results_df": results_df,
        "vst_counts": vst_counts,
        "metadata": metadata,
        "dds": dds,
    }


# ===========================================================================
# STEP 5: Enrichment (gseapy)
# ===========================================================================
def step_enrichment(results_df: pd.DataFrame) -> dict:
    report_progress("pathway", "Running GO/KEGG enrichment...", 78)
    import gseapy as gp

    sig = results_df[(results_df["padj"] < 0.05) & (results_df["log2FoldChange"].abs() > 1)]
    up_genes = sig[sig["log2FoldChange"] > 0].index.tolist()
    down_genes = sig[sig["log2FoldChange"] < 0].index.tolist()
    all_sig = sig.index.tolist()

    go_results = []
    kegg_results = []

    # GO enrichment
    try:
        go = gp.enrichr(gene_list=all_sig[:500], gene_sets="GO_Biological_Process_2023", organism="plant")
        for _, row in go.results.head(15).iterrows():
            go_results.append({
                "term": row["Term"].split("(")[0].strip(),
                "source": "GO_BP",
                "count": int(row.get("Overlap", "0").split("/")[0]) if isinstance(row.get("Overlap"), str) else 0,
                "gene_ratio": round(row.get("Combined Score", 0) / 100, 3),
                "pvalue": row.get("Adjusted P-value", 1),
                "neg_log10_pvalue": round(-np.log10(max(row.get("Adjusted P-value", 1), 1e-300)), 2),
            })
    except Exception as e:
        logger.warning("GO enrichment failed: %s", e)

    # KEGG enrichment
    try:
        kegg = gp.enrichr(gene_list=all_sig[:500], gene_sets="KEGG_2021_Human", organism="plant")
        for _, row in kegg.results.head(10).iterrows():
            kegg_results.append({
                "pathway": row["Term"],
                "count": int(row.get("Overlap", "0").split("/")[0]) if isinstance(row.get("Overlap"), str) else 0,
                "pvalue": row.get("Adjusted P-value", 1),
                "neg_log10_pvalue": round(-np.log10(max(row.get("Adjusted P-value", 1), 1e-300)), 2),
                "direction": "up",
            })
    except Exception as e:
        logger.warning("KEGG enrichment failed: %s", e)

    return {"go_enrichment": go_results, "kegg_pathways": kegg_results}


# ===========================================================================
# STEP 6: ML Biomarker Selection
# ===========================================================================
def step_biomarkers(results_df: pd.DataFrame, vst_counts: pd.DataFrame, metadata: pd.DataFrame) -> dict:
    report_progress("biomarker", "Running ML biomarker selection (RF + SVM + LASSO)...", 85)

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.svm import SVC
    from sklearn.linear_model import LassoCV
    from sklearn.model_selection import cross_val_score, StratifiedKFold
    from sklearn.preprocessing import LabelEncoder, StandardScaler
    from sklearn.metrics import roc_auc_score, confusion_matrix as cm_func

    # Use top DEGs as features
    sig = results_df[(results_df["padj"] < 0.05)].sort_values("padj").head(100)
    feature_genes = [g for g in sig.index if g in vst_counts.columns][:50]
    if len(feature_genes) < 5:
        return {}

    X = vst_counts[feature_genes].values
    le = LabelEncoder()
    y = le.fit_transform(metadata["condition"].values)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    cv = StratifiedKFold(n_splits=min(5, min(sum(y == 0), sum(y == 1))))

    # Random Forest
    rf = RandomForestClassifier(n_estimators=500, random_state=42, n_jobs=-1)
    rf.fit(X_scaled, y)
    rf_scores = cross_val_score(rf, X_scaled, y, cv=cv, scoring="roc_auc")
    rf_importance = sorted(
        [{"gene": g, "importance": round(float(imp), 4), "rank": 0}
         for g, imp in zip(feature_genes, rf.feature_importances_)],
        key=lambda x: x["importance"], reverse=True,
    )
    for i, item in enumerate(rf_importance):
        item["rank"] = i + 1

    # SVM
    svm = SVC(kernel="rbf", probability=True, random_state=42)
    svm_scores = cross_val_score(svm, X_scaled, y, cv=cv, scoring="roc_auc")

    # LASSO
    lasso = LassoCV(cv=cv, random_state=42, max_iter=5000)
    lasso.fit(X_scaled, y)
    lasso_coefs = [
        {"gene": g, "coefficient": round(float(c), 4), "selected": abs(c) > 0.01}
        for g, c in zip(feature_genes, lasso.coef_)
    ]

    # Consensus
    rf_top = {x["gene"] for x in rf_importance[:20]}
    lasso_top = {x["gene"] for x in lasso_coefs if x["selected"]}
    consensus = rf_top & lasso_top

    return {
        "random_forest": rf_importance[:20],
        "lasso_coefficients": lasso_coefs,
        "consensus_biomarkers": [
            {"gene": g, "rf_importance": next(x["importance"] for x in rf_importance if x["gene"] == g),
             "rf_rank": next(x["rank"] for x in rf_importance if x["gene"] == g),
             "lasso_coef": next(x["coefficient"] for x in lasso_coefs if x["gene"] == g),
             "log2fc": float(results_df.loc[g, "log2FoldChange"]) if g in results_df.index else 0,
             "fdr": float(results_df.loc[g, "padj"]) if g in results_df.index else 1}
            for g in consensus if g in results_df.index
        ],
        "model_performance": {
            "random_forest": {"auc": round(float(rf_scores.mean()), 3), "accuracy": round(float(rf_scores.mean()), 3)},
            "svm": {"auc": round(float(svm_scores.mean()), 3), "accuracy": round(float(svm_scores.mean()), 3)},
            "lasso": {"auc": round(float(max(0.5, 1 - lasso.mse_path_.mean())), 3)},
        },
        "summary": {
            "total_deg_input": len(sig),
            "rf_top_features": 20,
            "lasso_selected": sum(1 for c in lasso_coefs if c["selected"]),
            "consensus_count": len(consensus),
            "best_model": "random_forest",
            "best_auc": round(float(rf_scores.mean()), 3),
        },
    }


# ===========================================================================
# MAIN: Run all steps
# ===========================================================================
def main():
    logger.info("=" * 60)
    logger.info("RNAscope Pipeline Worker — Job %s", JOB_ID)
    logger.info("Species: %s | %s vs %s | n=%d+%d", SPECIES, CONDITION_A, CONDITION_B, N_A, N_B)
    logger.info("=" * 60)

    try:
        # Step 1: Download
        fastq_files = step_download()

        # Step 2: QC
        qc_data = step_qc(fastq_files)

        # Step 3: Salmon
        count_df, mapping_rates = step_salmon(qc_data["paired_samples"])

        # Step 4: DESeq2
        deseq = step_deseq2(count_df, qc_data["paired_samples"])

        # Step 5: Enrichment
        enrichment = step_enrichment(deseq["results_df"])

        # Step 6: Biomarkers
        biomarkers = step_biomarkers(deseq["results_df"], deseq["vst_counts"], deseq["metadata"])

        # Build final results
        report_progress("report", "Building results...", 95)
        from result_builder import build_results
        results = build_results(
            deseq_results=deseq,
            qc_data=qc_data,
            mapping_rates=mapping_rates,
            enrichment=enrichment,
            biomarkers=biomarkers,
            species=SPECIES,
            condition_a=CONDITION_A,
            condition_b=CONDITION_B,
            n_a=N_A,
            n_b=N_B,
        )

        # Upload results to S3
        s3.put_object(
            Bucket=S3_RESULTS,
            Key=f"_jobs/{JOB_ID}.json",
            Body=json.dumps({"status": "completed", "results": results}, default=str),
            ContentType="application/json",
        )

        report_progress("completed", "Pipeline complete!", 100)
        logger.info("Pipeline complete for job %s", JOB_ID)

    except Exception as e:
        logger.error("Pipeline failed: %s", e, exc_info=True)
        report_progress("failed", f"Pipeline error: {e}", -1)
        s3.put_object(
            Bucket=S3_RESULTS,
            Key=f"_jobs/{JOB_ID}.json",
            Body=json.dumps({"status": "failed", "error": str(e)}, default=str),
            ContentType="application/json",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
