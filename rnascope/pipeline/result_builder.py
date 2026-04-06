"""Convert real pipeline outputs to the JSON format expected by the frontend.

Maps pyDESeq2 results, Salmon quantification, and enrichment data to the
exact 22+ key structure that ResultsPage.jsx renders.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.decomposition import PCA


def build_results(
    deseq_results: dict,
    qc_data: dict,
    mapping_rates: dict,
    enrichment: dict,
    biomarkers: dict,
    species: str,
    condition_a: str,
    condition_b: str,
    n_a: int,
    n_b: int,
) -> dict:
    """Build the complete results dict matching the frontend contract."""

    results_df = deseq_results["results_df"]
    vst_counts = deseq_results["vst_counts"]
    metadata = deseq_results["metadata"]
    n_samples = n_a + n_b
    sample_names = list(metadata.index)

    # ----- Volcano data -----
    volcano = []
    for gene, row in results_df.iterrows():
        lfc = float(row.get("log2FoldChange", 0))
        pval = float(row.get("pvalue", 1))
        fdr = float(row.get("padj", 1))
        if np.isnan(lfc) or np.isnan(pval):
            continue
        neg_log10 = -np.log10(max(pval, 1e-300))
        sig = fdr < 0.05 and abs(lfc) > 1
        direction = "up" if sig and lfc > 0 else ("down" if sig and lfc < 0 else "ns")
        volcano.append({
            "gene": str(gene),
            "log2fc": round(lfc, 3),
            "pvalue": float(pval),
            "fdr": float(fdr),
            "neg_log10_pvalue": round(neg_log10, 2),
            "significant": sig,
            "direction": direction,
        })

    # ----- PCA -----
    pca_model = PCA(n_components=2)
    pca_coords = pca_model.fit_transform(vst_counts.values)
    pca_data = []
    for i, sample in enumerate(sample_names):
        pca_data.append({
            "sample": sample,
            "condition": metadata.loc[sample, "condition"],
            "pc1": round(float(pca_coords[i, 0]), 2),
            "pc2": round(float(pca_coords[i, 1]), 2),
        })

    # ----- Heatmap (top 30 DEGs) -----
    sig_genes_sorted = results_df[
        (results_df["padj"] < 0.05) & (results_df["log2FoldChange"].abs() > 1)
    ].sort_values("padj").head(30)

    heatmap_genes = [g for g in sig_genes_sorted.index if g in vst_counts.columns][:30]
    if heatmap_genes:
        heatmap_vals = vst_counts[heatmap_genes].values.T  # genes x samples
        # Z-score normalize per gene
        heatmap_z = ((heatmap_vals.T - heatmap_vals.mean(axis=1)) / (heatmap_vals.std(axis=1) + 1e-8)).T
        heatmap = {
            "genes": [str(g) for g in heatmap_genes],
            "samples": sample_names,
            "matrix": heatmap_z.round(2).tolist(),
        }
    else:
        heatmap = {"genes": [], "samples": sample_names, "matrix": []}

    # ----- DEG summary -----
    n_sig = sum(1 for v in volcano if v["significant"])
    n_up = sum(1 for v in volcano if v["direction"] == "up")
    n_down = sum(1 for v in volcano if v["direction"] == "down")
    deg_summary = {
        "total_tested": len(volcano),
        "significant": n_sig,
        "upregulated": n_up,
        "downregulated": n_down,
        "fdr_threshold": 0.05,
        "fc_threshold": 1.0,
    }

    # ----- QC summary -----
    qc_samples = qc_data.get("samples", [])
    avg_q30 = np.mean([s["q30_pct"] for s in qc_samples]) if qc_samples else 0
    avg_mapping = np.mean(list(mapping_rates.values())) if mapping_rates else 0
    avg_dup = np.mean([s["duplication_pct"] for s in qc_samples]) if qc_samples else 0

    qc_summary = {
        "total_samples": n_samples,
        "total_reads_m": round(sum(s["total_reads_m"] for s in qc_samples), 1),
        "avg_q30": round(avg_q30, 1),
        "avg_mapping_rate": round(avg_mapping, 1),
        "avg_duplication": round(avg_dup, 1),
        "avg_rrna_pct": 0,
        "flagged_samples": 0,
        "samples": [
            {
                "sample": s["sample"],
                "condition": condition_a if i < n_a else condition_b,
                "total_reads_m": s["total_reads_m"],
                "q30_pct": s["q30_pct"],
                "mapping_rate": round(mapping_rates.get(s["sample"], 0), 1),
                "duplication_pct": s["duplication_pct"],
                "rrna_pct": 0,
                "passed": s["q30_pct"] > 85 and mapping_rates.get(s["sample"], 0) > 70,
            }
            for i, s in enumerate(qc_samples)
        ],
    }

    # ----- MA plot -----
    ma_data = []
    for gene, row in results_df.iterrows():
        bm = float(row.get("baseMean", 0))
        lfc = float(row.get("log2FoldChange", 0))
        fdr = float(row.get("padj", 1))
        if np.isnan(bm) or np.isnan(lfc):
            continue
        ma_data.append({
            "gene": str(gene),
            "mean_expression": round(np.log2(bm + 1), 2),
            "log2fc": round(lfc, 3),
            "significant": fdr < 0.05 and abs(lfc) > 1,
        })

    # ----- Correlation matrix -----
    corr_matrix = np.corrcoef(vst_counts.values)
    correlation = {
        "samples": sample_names,
        "matrix": corr_matrix.round(3).tolist(),
    }

    # ----- Expression distribution -----
    expression_dist = {
        "samples": sample_names,
        "distributions": [
            {
                "sample": s,
                "values": np.log2(vst_counts.loc[s].values + 1).round(2).tolist()[:200],
            }
            for s in sample_names[:6]  # limit for payload size
        ],
    }

    # ----- Annotations -----
    annotations = []
    for v in volcano:
        if v["significant"]:
            annotations.append({
                "gene": v["gene"],
                "biotype": "protein_coding",
                "go_bp": "",  # would need BioMart query
                "disease": None,
                "drug": None,
            })

    # ----- Methods text -----
    methods_text = {
        "text": (
            f"RNA-seq analysis was performed on {n_samples} samples ({n_a} {condition_a}, "
            f"{n_b} {condition_b}) of {species}. Raw reads were quality-trimmed using fastp v0.23.4. "
            f"Transcript quantification was performed with Salmon v1.10.2 using the {species} "
            f"reference transcriptome. Gene-level counts were analyzed for differential expression "
            f"using pyDESeq2 with a design formula of ~condition. Genes with |log2FC| > 1 and "
            f"FDR < 0.05 were considered significant. {n_sig} DEGs were identified "
            f"({n_up} up, {n_down} down). GO and KEGG enrichment was performed using gseapy. "
            f"ML biomarker selection used Random Forest, SVM, and LASSO with 5-fold cross-validation."
        ),
        "tools": [
            {"name": "fastp", "version": "0.23.4", "purpose": "QC and adapter trimming"},
            {"name": "Salmon", "version": "1.10.2", "purpose": "Transcript quantification"},
            {"name": "pyDESeq2", "version": "0.4+", "purpose": "Differential expression"},
            {"name": "gseapy", "version": "1.1+", "purpose": "GO/KEGG enrichment"},
            {"name": "scikit-learn", "version": "1.4+", "purpose": "ML biomarker selection"},
        ],
    }

    return {
        "domain": "plant",
        "species": species,
        "volcano": volcano,
        "pca": pca_data,
        "heatmap": heatmap,
        "go_enrichment": enrichment.get("go_enrichment", []),
        "kegg_pathways": enrichment.get("kegg_pathways", []),
        "qc_summary": qc_summary,
        "deg_summary": deg_summary,
        "biotypes": [],  # would need GTF parsing
        "interpretation": {},
        "transcripts": None,
        "wgcna": None,
        "deconvolution": None,
        "venn": None,
        "treatment_heatmap": None,
        "fastqc": None,
        "alignment": None,
        "expression_dist": expression_dist,
        "correlation": correlation,
        "ma_plot": ma_data,
        "dispersion": None,
        "time_series": None,
        "annotations": annotations,
        "biomarkers": biomarkers,
        "methods_text": methods_text,
    }
