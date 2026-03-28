# RNAscope Agent Workflow — Complete Technical Guide

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [User Upload Flow](#2-user-upload-flow)
3. [Orchestrator Agent Loop — The Brain](#3-orchestrator-agent-loop--the-brain)
4. [Pipeline Steps (1–14) In Detail](#4-pipeline-steps-114-in-detail)
5. [Sub-Agent Communication](#5-sub-agent-communication)
6. [Species Routing — How It Decides What to Search](#6-species-routing--how-it-decides-what-to-search)
7. [Frontend — How Graphs Are Generated](#7-frontend--how-graphs-are-generated)
8. [Chat Agent — Researcher Q&A](#8-chat-agent--researcher-qa)
9. [Error Handling & Recovery](#9-error-handling--recovery)
10. [Data Flow Diagram](#10-data-flow-diagram)

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER (Browser)                           │
│  Upload FASTQ → Configure Experiment → View Graphs → Chat      │
└──────────────┬──────────────────────────────────┬───────────────┘
               │ HTTP / WebSocket                 │
               ▼                                  ▼
┌──────────────────────────┐    ┌──────────────────────────────┐
│     FastAPI Backend       │    │     React Frontend (Vite)    │
│  ─────────────────────    │    │  ────────────────────────    │
│  POST /api/jobs (upload)  │    │  UploadPage.jsx              │
│  GET  /api/jobs/:id       │    │  DashboardPage.jsx           │
│  GET  /api/jobs/:id/results│   │  ResultsPage.jsx (9 tabs)    │
│  POST /api/chat           │    │  ChartCard + Plotly.js       │
│  WS   /ws/:id (live)      │    │  ChatPanel.jsx               │
└──────────┬───────────────┘    └──────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR AGENT                          │
│  Claude API (claude-sonnet-4-6) + System Prompt               │
│  ─────────────────────────────────────────────────────────   │
│  Receives: job config (species, conditions, FASTQ paths)     │
│  Decides:  which tool to call next                           │
│  Calls:    18 tools via Anthropic tool_use                   │
│  Loop:     call tool → get result → decide next → repeat     │
└──────────┬───────────────────────────────────────────────────┘
           │ Tool Calls
           ▼
┌──────────────────────────────────────────────────────────────┐
│                    TOOL HANDLERS                              │
│  handlers.py → dispatches to real infrastructure             │
│  ─────────────────────────────────────────────────────────   │
│  upload_validator     → S3 file verification                 │
│  compute_selector     → pick EC2/Batch tier                  │
│  run_qc_agent         → FastQC + Trimmomatic (AWS Batch)     │
│  run_alignment_agent  → SortMeRNA + STAR (AWS Batch)         │
│  run_quantification   → featureCounts (AWS Batch)            │
│  run_transcript_quant → Salmon (AWS Batch)                   │
│  run_deg_agent        → DESeq2 + edgeR (AWS Batch)           │
│  run_annotation_agent → biomaRt + clusterProfiler            │
│  run_pathway_agent    → GO/KEGG/MapMan/PlantCyc              │
│  run_wgcna_agent      → WGCNA network (AWS Batch)            │
│  run_deconvolution    → xCell/CIBERSORTx (AWS Batch)         │
│  run_interpretation   → calls Interpretation Sub-Agent        │
│  run_report_agent     → PDF generation (AWS Batch)            │
│  notify_slack/email   → Slack SDK / AWS SES                  │
│  checkpoint_save      → Redis + S3                           │
│  checkpoint_restore   → Redis (fast) → S3 (fallback)         │
└──────────┬───────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────┐
│                    AWS INFRASTRUCTURE                         │
│  S3 (raw data, results, reports)                             │
│  AWS Batch (parallel compute per sample)                     │
│  Redis (checkpoints, job state)                              │
│  SES (email notifications)                                   │
│  EFS (shared STAR genome index)                              │
└──────────────────────────────────────────────────────────────┘
```

### Three Claude-Powered Agents

| Agent | Model | Temp | Purpose |
|-------|-------|------|---------|
| **Orchestrator** | claude-sonnet-4-6 | 0.1 | Decides what to do next, calls tools, drives the pipeline |
| **Interpretation** | claude-sonnet-4-6 | 0.3 | Reads DE + pathway results, writes biological narrative |
| **Chat** | claude-sonnet-4-6 | 0.2 | Answers researcher questions about their specific results |

---

## 2. User Upload Flow

### Step-by-step: What happens when the user clicks "Start Analysis"

```
1. USER fills form in UploadPage.jsx:
   - Selects FASTQ files (drag & drop)
   - Sets: project name, species (e.g. "arabidopsis"), conditions, sample counts
   - Sets: tissue type, biological context, email

2. BROWSER sends POST /api/jobs (multipart form data)
   - Files uploaded as multipart chunks
   - Form fields sent alongside

3. FASTAPI (api.py) receives the request:
   a. Generates job_id (UUID, first 12 chars)
   b. Saves files to uploads/{job_id}/
   c. Creates job_state dict:
      {
        job_id, project_name, species, condition_a, condition_b,
        n_a, n_b, files, status: "running", current_step: "ingestion"
      }
   d. Stores in _jobs_store[job_id]
   e. Starts pipeline in background thread: _simulate_pipeline(job_id)
   f. Returns: { job_id, status: "started", files_uploaded, size_gb }

4. BROWSER receives job_id → navigates to /results/{job_id}

5. BROWSER opens WebSocket: ws://host/ws/{job_id}
   - Server sends current_state immediately
   - Server pushes step_update messages as pipeline progresses
   - Browser updates ProgressTracker in real-time

6. PIPELINE completes → server pushes pipeline_complete
   - Browser fetches GET /api/jobs/{job_id}/results
   - Results rendered as interactive charts
```

### File flow:
```
User's computer                          Server
─────────────                            ──────
sample1_R1.fastq.gz  ──POST /api/jobs──▶  uploads/{job_id}/sample1_R1.fastq.gz
sample1_R2.fastq.gz  ──────────────────▶  uploads/{job_id}/sample1_R2.fastq.gz
sample2_R1.fastq.gz  ──────────────────▶  uploads/{job_id}/sample2_R1.fastq.gz
...                                        │
                                           ▼ (production: upload to S3)
                                        s3://rnascope-raw-data/{job_id}/
```

---

## 3. Orchestrator Agent Loop — The Brain

This is the core of the system. File: `rnascope/agents/orchestrator.py`

### How the agentic loop works:

```python
def run_pipeline(job: Job) -> dict:
    # 1. Initialize Claude client
    client = anthropic.Anthropic(api_key=...)

    # 2. Build the initial message describing the job
    messages = [{"role": "user", "content": _build_job_message(job)}]
    #    This message contains: job_id, species, samples, conditions, S3 paths

    # 3. AGENTIC LOOP (max 50 turns)
    for turn in range(MAX_TURNS):

        # 4. Call Claude with system prompt + tools
        response = client.messages.create(
            model="claude-sonnet-4-6",
            system=ORCHESTRATOR_SYSTEM_PROMPT,  # 400-line prompt
            messages=messages,
            tools=TOOL_DEFINITIONS,             # 18 tool schemas
        )

        # 5. Parse response — Claude returns text + tool_use blocks
        for block in response.content:
            if block.type == "text":
                # Claude explains what it's doing (logged)
            if block.type == "tool_use":
                # Claude wants to call a tool
                tool_calls.append(block)

        # 6. If no tool calls → pipeline is done
        if not tool_calls:
            break

        # 7. Execute each tool call
        for tc in tool_calls:
            if tc.name == "run_interpretation_agent":
                # Special: calls Interpretation sub-agent (separate Claude call)
                result = _handle_interpretation(client, tc.input)
            else:
                # Normal: dispatch to handler function
                result = handle_tool_call(tc.name, tc.input)

        # 8. Feed tool results back to Claude
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        # 9. Claude sees the results → decides what to call next
        # (loop continues)
```

### What Claude "thinks" during the loop:

```
Turn 1: "New job received. 6 samples, arabidopsis, drought vs control.
         First I need to validate the uploads."
         → calls: upload_validator(job_id, bucket, file_list)

Turn 2: "All 12 files present, paired-end, 8.5 GB total.
         Need to select compute tier."
         → calls: compute_selector(dataset_size_gb=8.5, n_samples=6)

Turn 3: "Small dataset, r6i.xlarge is fine. Now run QC."
         → calls: run_qc_agent(job_id, sample_list, s3_input_path)

Turn 4: "QC complete. 2 samples flagged for Q30 < 85% but still usable.
         Proceeding to alignment."
         → calls: run_alignment_agent(job_id, samples, "TAIR10", araport11_gtf)

Turn 5: "Alignment done. 89% average mapping rate. Good.
         Now quantify gene expression."
         → calls: run_quantification_agent(job_id, bam_paths, gtf)

... (continues through all 14 steps)

Turn 14: "All analyses complete. Sending notifications."
          → calls: notify_slack(job_id, channel, "Analysis complete! ...")
          → calls: notify_email(job_id, email, "Results ready", ...)
          (no more tool calls → loop exits)
```

### Key design decisions:
- Claude decides the order, not hardcoded logic
- Claude can skip steps if not applicable (e.g., skip deconvolution for plants)
- Claude can retry failed steps (up to 3 times)
- Claude checkpoints after every step
- If Claude hits an error, it reads the error message and adapts

---

## 4. Pipeline Steps (1–14) In Detail

### STEP 1: INGESTION & VALIDATION

```
Input:  S3 bucket + file list
Tool:   upload_validator(job_id, s3_bucket, file_list)

What happens:
  1. List all objects in S3 bucket
  2. Check every expected file exists
  3. Detect paired-end (_R1/_R2) vs single-end
  4. Calculate total dataset size in GB
  5. Extract sample IDs from filenames

Output: {
  files_present: 12, files_missing: [],
  layout: "paired", n_samples: 6,
  dataset_size_gb: 8.5, sample_ids: [...]
}
```

### STEP 2: COMPUTE SELECTION

```
Input:  dataset_size_gb, n_samples
Tool:   compute_selector(8.5, 6)

Logic:
  < 10 GB  → EC2 r6i.xlarge   (4 vCPU, 32 GB)    ~$0.25/hr
  10-100 GB → EC2 r6i.8xlarge  (32 vCPU, 256 GB)   ~$2.00/hr
  > 100 GB  → AWS Batch array  (auto-scale)         ~$0.05/vCPU-hr Spot

Output: {
  instance_type: "r6i.xlarge", estimated_cost_usd: 1.26,
  use_spot: true, estimated_runtime_hours: 2.5
}
```

### STEP 3: QUALITY CONTROL

```
Input:  sample list + S3 input path
Tool:   run_qc_agent(job_id, samples, s3_path)

What happens:
  1. Check for existing checkpoint → skip if already done
  2. Submit one AWS Batch job per sample (parallel):
     - FastQC: read quality, GC content, adapter contamination
     - Trimmomatic: remove adapters (TruSeq3-PE), trim low-quality bases
       LEADING:3 TRAILING:3 SLIDINGWINDOW:4:15 MINLEN:36
  3. Wait for all Batch jobs to complete
  4. Aggregate with MultiQC
  5. Flag samples: Q30 < 85%, mapping < 70%, duplication > 60%
  6. Save checkpoint to Redis + S3

Output: {
  samples_processed: 6, flagged_samples: ["S03"],
  multiqc_report: "s3://results/job123/qc/multiqc.html",
  trimmed_output: "s3://results/job123/qc/trimmed/"
}

NOTE: Flagged samples are NOT removed. They continue through
the pipeline but are annotated in the final report.
```

### STEP 4: rRNA DEPLETION

```
Runs inside the alignment agent (combined step).

What happens:
  1. SortMeRNA aligns reads against SILVA 138 rRNA database
  2. Separates: rRNA reads (discarded) vs non-rRNA reads (kept)
  3. For human: additionally removes host DNA via Bowtie2 --very-fast
  4. For plants: no host removal needed
  5. Logs rRNA percentage per sample

Flag if: rRNA > 60% (suggests poor library prep)
```

### STEP 5: READ ALIGNMENT (STAR)

```
Input:  samples, genome (e.g. "TAIR10"), GTF
Tool:   run_alignment_agent(job_id, samples, genome, gtf)

What happens:
  1. Check checkpoint → skip if done
  2. Submit Batch array (one job per sample):
     a. SortMeRNA rRNA depletion
     b. STAR 2-pass alignment:
        --outSAMtype BAM SortedByCoordinate
        --quantMode GeneCounts
        --twopassMode Basic
        --outFilterMismatchNmax 2
     c. samtools flagstat for alignment QC
  3. Wait for all jobs
  4. Collect BAM paths from S3

Output: {
  bam_paths: ["s3://results/job123/alignment/S01_Aligned.bam", ...],
  alignment_stats: "s3://results/job123/alignment/stats/"
}
```

### STEP 6: GENE QUANTIFICATION (featureCounts)

```
Input:  BAM paths + GTF
Tool:   run_quantification_agent(job_id, bam_paths, gtf)

What happens:
  1. Run featureCounts on ALL BAMs simultaneously:
     -T 16 (16 threads)
     -s 2  (reverse stranded — standard for Total RNA-seq)
     -t exon -g gene_id
     --fracOverlap 0.2
     -M (count multi-mapped reads fractionally)
  2. Output: raw count matrix (genes × samples)

Output: {
  count_matrix_path: "s3://results/job123/quantification/counts.txt"
}
```

### STEP 7: TRANSCRIPT QUANTIFICATION (Salmon)

```
Input:  trimmed FASTQs + species
Tool:   run_transcript_quant_agent(job_id, samples, s3_input, species)

What happens:
  1. Per sample: Salmon quant in mapping-based mode
     --validateMappings --seqBias --gcBias -l A
  2. Aggregate with tximport (R):
     - Transcript-to-gene mapping via tx2gene file
     - Produces: TPM matrix, scaled counts, effective lengths
  3. Detect isoform switching events

Output: {
  transcript_tpm: "s3://results/job123/salmon/transcript_tpm.csv",
  gene_tpm: "s3://results/job123/salmon/gene_tpm.csv"
}
```

### STEP 8: DIFFERENTIAL EXPRESSION (DESeq2 + edgeR)

```
Input:  count matrix + metadata + design formula
Tool:   run_deg_agent(job_id, counts, metadata, "~ condition")

What happens:
  1. Run DESeq2 in R:
     a. Filter: keep genes with rowSums >= 10
     b. Fit model: ~ condition (or ~ condition + batch if covariates exist)
     c. Run DESeq() for dispersion estimation + Wald test
     d. Shrink fold changes: lfcShrink(type="ashr")
     e. Apply Benjamini-Hochberg FDR correction
     f. Threshold: FDR < 0.05, |log2FC| > 1
  2. Run edgeR on top 100 genes as validation
  3. If DESeq2 fails to converge:
     → Retry with betaPrior=FALSE
     → If still fails: fall back to edgeR as primary

Output: {
  deg_results: "s3://results/job123/deg/deseq2_results.csv",
  edger_validation: "s3://results/job123/deg/edger_top100.csv"
}
```

### STEP 9: FUNCTIONAL ANNOTATION

```
Input:  gene list + species
Tool:   run_annotation_agent(job_id, genes, species)

What happens (SPECIES-SPECIFIC):

  For ANIMALS (human, mouse, etc.):
    → biomaRt: Ensembl (hsapiens_gene_ensembl)
    → Fetches: symbol, biotype, chr, start, end, description
    → GO terms, KEGG, DisGeNET, DGIdb

  For PLANTS (arabidopsis, rice, etc.):
    → biomaRt: Ensembl Plants (athaliana_eg_gene)
    → Fetches: gene ID, symbol, biotype, chr, description
    → TAIR, Phytozome, PlantRegMap annotations

  For MICROBES (E. coli, yeast):
    → NCBI-based annotation or species-specific DB
    → EcoCyc, SGD, AspGD

Output: {
  annotated_results: "s3://results/job123/annotation/gene_annotations.csv"
}
```

### STEP 10: PATHWAY ENRICHMENT

```
Input:  DEG results + species
Tool:   run_pathway_agent(job_id, deg_results, species, ontologies)

What happens (SPECIES-SPECIFIC):

  For ANIMALS:
    → GO enrichment: BP, MF, CC (clusterProfiler + org.Hs.eg.db)
    → KEGG: enrichKEGG(organism="hsa")
    → GSEA: gene-set enrichment on ranked gene list

  For PLANTS:
    → GO enrichment: via org.At.tair.db or Ensembl Plants biomaRt
    → KEGG: enrichKEGG(organism="ath")
    → MapMan: plant-specific metabolic pathway bins
    → PlantCyc: AraCyc/RiceCyc/CornCyc metabolic pathways
    → PlantReactome (if available)

  For MICROBES:
    → GO enrichment: via species OrgDb
    → KEGG: species-specific code
    → EcoCyc/MetaCyc for metabolic pathways

  For METATRANSCRIPTOME:
    → HUMAnN3 for community-level pathway abundance
    → eggNOG-mapper for KO assignment
    → Skip standard GO/KEGG (not applicable to mixed communities)

Output: {
  go_bp, go_mf, go_cc, kegg_up, kegg_down, gsea_go, gsea_kegg,
  mapman_enrichment (plants only), plantcyc_enrichment (plants only)
}
```

### STEP 11: RNA BIOTYPE ANALYSIS

```
Classifies all expressed genes by Ensembl biotype:
  protein_coding, lncRNA, snRNA, snoRNA, miRNA, pseudogene, misc_RNA

Calculates: proportion of reads per biotype
Runs: separate DE analysis for mRNA vs lncRNA
```

### STEP 12: WGCNA CO-EXPRESSION NETWORK

```
Input:  normalized count matrix + metadata
Tool:   run_wgcna_agent(job_id, counts, metadata, species)

What happens:
  1. Filter to top 5000 most variable genes (by MAD)
  2. Auto-detect soft thresholding power (pickSoftThreshold)
  3. Build weighted co-expression network (blockwiseModules):
     - TOM (Topological Overlap Matrix) computation
     - Hierarchical clustering
     - Dynamic tree cutting → module assignment
     - Module merging (cutHeight=0.25)
  4. Compute module eigengenes
  5. Correlate eigengenes with trait (condition_a vs condition_b)
  6. Identify hub genes per module (top 10 by kME)
  7. Run GO enrichment per significant module
  8. Export top 500 edges for network visualization

Output: {
  modules_json, module_genes, network_edges
}
```

### STEP 13: CELL TYPE DECONVOLUTION

```
Input:  count matrix + species + tissue type
Tool:   run_deconvolution_agent(job_id, counts, species)

Species-aware logic:
  ANIMALS → xCell, CIBERSORTx, or MuSiC (auto-selected)
  PLANTS  → SKIPPED (no single-cell references available)
  MICROBES → SKIPPED
  META    → SKIPPED (use community composition instead)

What happens (for animals):
  1. Select method based on species config
  2. Run deconvolution in R container
  3. Get per-sample cell type fractions
  4. Compare fractions between conditions (Wilcoxon test)
  5. Flag significantly different cell types (p < 0.05)

Output: {
  method: "xcell",
  deconvolution_results: "s3://results/job123/deconvolution/xcell.csv"
}
  OR
{
  method: "skipped",
  reason: "Cell type deconvolution not applicable for plant (Arabidopsis)"
}
```

### STEP 14: AI BIOLOGICAL INTERPRETATION

```
This step calls a SEPARATE Claude model (the Interpretation Sub-Agent).

Input:  DEG results + pathway results + metadata
Tool:   run_interpretation_agent(job_id, deg, pathways, metadata)

What happens:
  1. Orchestrator calls the tool
  2. Handler detects this needs an LLM call (not a Batch job)
  3. Calls interpretation.py → run_interpretation():
     - Creates a NEW Claude API call with INTERPRETATION_SYSTEM_PROMPT
     - Passes: top 50 DEGs, pathway results, tissue type, disease context
     - Temperature: 0.3 (slightly creative but grounded)
  4. Claude generates 6 sections:
     - Executive summary (3-5 sentences, PI-friendly)
     - Mechanistic narrative (signaling axis, upstream→downstream)
     - Top 3 testable hypotheses
     - 5 recommended experiments
     - Therapeutic relevance (drug targets)
     - Literature context (relevant prior studies)

Output: full interpretation text (returned to orchestrator)
```

### STEP 14b: REPORT GENERATION

```
Final step. Generates publication-ready PDF containing:
  - Auto-generated Methods section with software versions
  - Sample summary table
  - All plots (volcano, PCA, heatmap, GO, KEGG)
  - Top DEG table
  - AI interpretation
  - Auto-cited bibliography
```

---

## 5. Sub-Agent Communication

### How the three agents talk:

```
┌─────────────────────────────────────────────────┐
│              ORCHESTRATOR AGENT                   │
│  (drives the pipeline, calls tools)              │
│                                                   │
│  Turn 12: "Analysis complete. Need interpretation"│
│  → calls tool: run_interpretation_agent(...)      │
│                                                   │
│     ┌─────────────────────────────────────────┐  │
│     │      INTERPRETATION SUB-AGENT            │  │
│     │  (separate Claude API call)              │  │
│     │                                          │  │
│     │  Input: top DEGs + pathways + metadata   │  │
│     │  Output: 6-section biological narrative  │  │
│     │  Model: claude-sonnet-4-6, temp=0.3      │  │
│     └──────────────────┬──────────────────────┘  │
│                        │ returns interpretation   │
│                        ▼                          │
│  Turn 13: "Interpretation done. Now generate      │
│            report and notify researcher."          │
│  → calls: run_report_agent(...)                   │
│  → calls: notify_slack(...), notify_email(...)    │
└───────────────────────────────────────────────────┘

                    SEPARATELY:

┌─────────────────────────────────────────────────┐
│                CHAT AGENT                        │
│  (independent, stateful, per-job)                │
│                                                   │
│  Activated when: researcher asks a question       │
│  Input: question + full job context (injected)    │
│  Output: answer referencing their specific data   │
│  Model: claude-sonnet-4-6, temp=0.2              │
│                                                   │
│  Example:                                         │
│  User: "What should I validate first?"            │
│  Chat: "I recommend validating CBF1 (log2FC=4.2, │
│         FDR=1.3e-8) by qRT-PCR — it's the top   │
│         upregulated gene and a known cold-stress  │
│         transcription factor in Arabidopsis."     │
└───────────────────────────────────────────────────┘
```

---

## 6. Species Routing — How It Decides What to Search

File: `rnascope/species.py`

### The species resolver

When the user selects "Arabidopsis" in the upload form, the entire pipeline adapts:

```python
cfg = resolve_species("arabidopsis")

cfg.key           = "arabidopsis"
cfg.name          = "Arabidopsis thaliana"
cfg.domain        = "plant"                    # ← THIS drives all routing
cfg.genome        = "TAIR10"
cfg.gtf           = "Araport11"
cfg.org_db        = "org.At.tair.db"           # ← Bioconductor annotation DB
cfg.kegg_code     = "ath"                      # ← KEGG organism code
cfg.ensembl_dataset = "athaliana_eg_gene"      # ← Ensembl Plants mart
cfg.pathway_dbs   = ["GO", "KEGG", "MapMan", "PlantCyc", "PlantReactome"]
cfg.annotation_dbs = ["TAIR", "Ensembl_Plants", "UniProt", "Phytozome", "PlantRegMap"]
cfg.mapman_bin    = "Ath_AGI_LOCUS_TAIR10_Aug2012.txt"
cfg.plantcyc_db   = "AraCyc"
cfg.has_deconvolution = False                  # ← No cell type deconv for plants
```

### How each handler uses it:

```
ANNOTATION HANDLER:
  if domain == "plant":
      → uses Ensembl Plants mart (plants.ensembl.org)
      → queries athaliana_eg_gene dataset
  if domain == "animal":
      → uses standard Ensembl mart
      → queries hsapiens_gene_ensembl

PATHWAY HANDLER:
  if domain == "plant":
      → GO via org.At.tair.db
      → KEGG with organism="ath"
      → MapMan bin mapping (plant metabolic pathways)
      → PlantCyc (AraCyc) metabolic pathways
  if domain == "animal":
      → GO via org.Hs.eg.db
      → KEGG with organism="hsa"
      → Reactome, MSigDB

DECONVOLUTION HANDLER:
  if domain == "plant":
      → SKIPPED with message explaining why
  if domain == "animal":
      → runs xCell/CIBERSORTx based on species config

DEMO DATA GENERATOR:
  if species == "arabidopsis":
      → gene names: RD29A, CBF1, PR1, DREB2A, ...
      → GO terms: "response to water deprivation", "ABA signaling", ...
      → KEGG: "Plant hormone signal transduction", "Phenylpropanoid biosynthesis"
      → Cell types: Mesophyll, Epidermis, Guard cells, ... (if applicable)
```

### Complete routing table:

```
User selects    │ Genome   │ Annotation DB     │ KEGG │ GO DB            │ Extra pathways
────────────────┼──────────┼───────────────────┼──────┼──────────────────┼─────────────────
Human           │ GRCh38   │ Ensembl           │ hsa  │ org.Hs.eg.db     │ Reactome, MSigDB
Mouse           │ mm39     │ Ensembl           │ mmu  │ org.Mm.eg.db     │ Reactome
Arabidopsis     │ TAIR10   │ Ensembl Plants    │ ath  │ org.At.tair.db   │ MapMan, AraCyc
Rice            │ IRGSP-1  │ Ensembl Plants    │ osa  │ org.Os.eg.db     │ MapMan, RiceCyc
Maize           │ Zm-B73   │ Ensembl Plants    │ zma  │ org.Zm.eg.db     │ MapMan, CornCyc
Tomato          │ SL4.0    │ Ensembl Plants    │ sly  │ —                │ MapMan, TomatoCyc
E. coli         │ K-12     │ NCBI              │ eco  │ org.EcK12.eg.db  │ EcoCyc
Yeast           │ R64      │ Ensembl           │ sce  │ org.Sc.sgd.db    │ SGD
Metatranscript  │ meta     │ NCBI_NR/UniRef90  │ —    │ —                │ HUMAnN3, eggNOG
```

---

## 7. Frontend — How Graphs Are Generated

### Data flow: Backend → Frontend → Chart

```
Backend (api.py)                    Frontend (ResultsPage.jsx)
────────────────                    ────────────────────────
GET /api/jobs/{id}/results    →     results = { volcano, pca, heatmap,
returns JSON with all data          go_enrichment, kegg_pathways, ... }
                                         │
                                         ▼
                                    TABS route to chart components:
                                    ┌─────────────┬──────────────────────────────┐
                                    │ Tab         │ Component → Plotly trace     │
                                    ├─────────────┼──────────────────────────────┤
                                    │ Overview    │ VolcanoPlot (scatter)        │
                                    │             │ PCAPlot (scatter)            │
                                    │             │ DEGTable (table)             │
                                    │             │ BiotypePie (pie)             │
                                    │ QC          │ QCSummary (stats + table)    │
                                    │ DEG         │ VolcanoPlot + HeatmapPlot   │
                                    │             │ DEGTable                     │
                                    │ Transcripts │ TranscriptPlot (bar + table) │
                                    │ Annotation  │ AnnotationTable (table)      │
                                    │ Pathways    │ GOBubble (scatter) +         │
                                    │             │ KEGGBar (horizontal bar)     │
                                    │ Network     │ WGCNAPlot (bar + network +   │
                                    │             │ module cards)                │
                                    │ Cell Types  │ DeconvolutionPlot (stacked   │
                                    │             │ bar + comparison table)      │
                                    │ AI          │ Interpretation text +        │
                                    │             │ hypothesis cards             │
                                    └─────────────┴──────────────────────────────┘
```

### Download system:

```
ChartCard wrapper (ChartCard.jsx)
  │
  ├── plotRef → Plotly.toImage(el, {format: "png"})  → download PNG
  ├── plotRef → Plotly.toImage(el, {format: "svg"})  → download SVG
  └── csvData → build CSV string → Blob → download
                {filename, headers, rows}

"Download All CSV" button → exports 8 CSV files at once:
  volcano_data.csv, pca_data.csv, heatmap_data.csv,
  go_enrichment.csv, kegg_pathways.csv, biotype_distribution.csv,
  qc_metrics.csv, deg_significant.csv
```

---

## 8. Chat Agent — Researcher Q&A

File: `rnascope/agents/chat.py`

### How it works:

```
1. User types question in ChatPanel.jsx
2. POST /api/chat { job_id, question }
3. Backend creates/reuses ChatAgent(job_id)
4. ChatAgent builds system prompt:
   CHAT_SYSTEM_PROMPT + runtime job context:
   - Current step, % complete, ETA
   - Top DEGs, pathway summary, QC metrics
   - Flagged samples, cost so far
5. Sends to Claude API (temp=0.2, max_tokens=1024)
6. Returns answer to frontend

The chat agent is STATEFUL — it remembers the conversation history.
Each job gets its own ChatAgent instance with its own message list.
```

### Example conversation:

```
Researcher: "Is my data good quality?"
Chat Agent: "Your data quality is strong overall. Average Q30 is 94.2%
             (threshold: 85%), mapping rate is 91.3%, and duplication
             is 22.4%. Sample S03 was flagged with Q30 at 83.7% but
             was kept in the analysis. No samples were excluded."

Researcher: "What's the most interesting finding?"
Chat Agent: "The standout finding is the convergence of 8 top DE genes
             on the ABA signaling pathway — RD29A (log2FC=4.2),
             DREB2A (log2FC=3.8), and NCED3 (log2FC=3.1) all point
             to a drought-responsive transcriptional program. This is
             consistent with your drought stress vs control design."
```

---

## 9. Error Handling & Recovery

### Checkpoint system:

```
After EVERY step completion:
  1. Save to Redis (fast, 7-day TTL):
     key: rnascope:checkpoint:{job_id}:{step}
     value: JSON {state, metrics, output_s3_path, timestamp}

  2. Save to S3 (permanent):
     s3://rnascope-results/{job_id}/checkpoints/{step}.json

Before EVERY step start:
  1. Check Redis for existing checkpoint
  2. If found → SKIP the step (return cached results)
  3. If not in Redis → check S3
  4. If nowhere → run the step fresh
```

### Error recovery matrix:

```
Error                    │ What the agent does
─────────────────────────┼──────────────────────────────────────
FASTQ file corrupt       │ Request re-upload of specific file
Q30 < 75%                │ Flag sample, continue analysis, note in report
rRNA > 70%               │ Re-run depletion with aggressive params
                         │ If still >70%, exclude from DE only
Spot instance killed     │ Checkpoint → graceful shutdown → auto-relaunch
DESeq2 won't converge    │ Retry with betaPrior=FALSE → fallback to edgeR
n < 3 per group          │ Continue but warn: "exploratory results"
Out of memory            │ Bump instance one tier → retry from checkpoint
No enriched pathways     │ Relax thresholds: FDR<0.2, then <0.5
API rate limit           │ Exponential backoff: 2s, 4s, 8s → max 3 retries
```

### Retry logic (in orchestrator.py):

```python
def _call_orchestrator(client, messages, retry=0):
    try:
        return client.messages.create(...)
    except anthropic.APIError as e:
        if retry < 3:
            time.sleep(2 ** retry)  # 1s, 2s, 4s
            return _call_orchestrator(client, messages, retry + 1)
        raise
```

---

## 10. Data Flow Diagram

### End-to-end: from FASTQ to graphs

```
FASTQ files (user upload)
    │
    ▼
┌─ STEP 1: Validate ─────────────────────────────────┐
│  S3 check → detect layout → count samples           │
└──────────────────────────────────────────────────────┘
    │
    ▼
┌─ STEP 2: Select compute ───────────────────────────┐
│  Dataset size → EC2 tier or Batch array              │
└──────────────────────────────────────────────────────┘
    │
    ▼
┌─ STEP 3: QC ───────────────────────────────────────┐
│  FastQC → MultiQC → Trimmomatic                     │
│  Output: trimmed FASTQs + QC metrics                 │──→ QC Tab (graphs)
└──────────────────────────────────────────────────────┘
    │
    ▼
┌─ STEP 4-5: Align + Quantify ──────────────────────┐
│  SortMeRNA → STAR → featureCounts                    │
│  Output: BAM files + raw count matrix                │
└──────────────────────────────────────────────────────┘
    │                           │
    ▼                           ▼
┌─ STEP 6: Salmon ───┐  ┌─ STEP 7: DESeq2 ─────────┐
│  Transcript TPM     │  │  DE genes + fold changes   │
│  Isoform switching  │  │  FDR correction             │
│  Output: TPM matrix │  │  Output: DEG table          │──→ DEG Tab (volcano,
└─────────────────────┘  └───────────────────────────┘      heatmap, table)
    │                           │
    ▼                           ▼
 Transcripts Tab         ┌─ STEP 8: Annotate ────────┐
 (bar chart,             │  Species-specific DBs       │
  isoform table)         │  GO, KEGG, disease, drugs   │──→ Annotation Tab
                         └───────────────────────────┘
                                │
                                ▼
                         ┌─ STEP 9: Pathways ────────┐
                         │  GO (BP/MF/CC)              │
                         │  KEGG (up/down)             │
                         │  MapMan (plants)            │──→ Pathways Tab
                         │  PlantCyc (plants)          │    (bubble + bar)
                         └───────────────────────────┘
                                │
                         ┌──────┴──────┐
                         ▼             ▼
                  ┌─ STEP 10 ─┐ ┌─ STEP 11 ──────┐
                  │  WGCNA     │ │ Deconvolution   │
                  │  Network   │ │ Cell types      │
                  │  Modules   │ │ (animals only)  │
                  └─────┬──────┘ └──────┬──────────┘
                        │               │
                        ▼               ▼
                   Network Tab    Cell Types Tab
                        │               │
                        └───────┬───────┘
                                ▼
                         ┌─ STEP 12: AI ─────────────┐
                         │  Interpretation Sub-Agent   │
                         │  Claude reads ALL results   │
                         │  Generates 6-section report │──→ AI Tab
                         └───────────────────────────┘
                                │
                                ▼
                         ┌─ STEP 13: Report ─────────┐
                         │  PDF with all plots         │
                         │  Methods + bibliography     │
                         └───────────────────────────┘
                                │
                                ▼
                         ┌─ STEP 14: Notify ─────────┐
                         │  Slack message              │
                         │  Email with report link     │
                         └───────────────────────────┘
                                │
                                ▼
                          DONE. Researcher notified.
                          All results in S3 + web app.
```

---

## File Map

```
rnascope/
├── pyproject.toml                 # Python dependencies
├── .env.example                   # Environment variables template
├── .gitignore
├── AGENT_WORKFLOW.md              # This file
│
├── rnascope/                      # Python backend
│   ├── main.py                    # CLI entry point (typer)
│   ├── api.py                     # FastAPI server + demo data generator
│   ├── config.py                  # Pydantic settings from .env
│   ├── species.py                 # Species resolver (25 organisms)
│   ├── notifications.py           # Slack + email
│   │
│   ├── agents/
│   │   ├── orchestrator.py        # Main agentic loop
│   │   ├── interpretation.py      # Biological narrative sub-agent
│   │   └── chat.py                # Researcher Q&A agent
│   │
│   ├── prompts/
│   │   ├── orchestrator.py        # 400-line system prompt
│   │   ├── interpretation.py      # Interpretation prompt
│   │   └── chat.py                # Chat prompt + context builder
│   │
│   ├── tools/
│   │   ├── definitions.py         # 18 Anthropic API tool schemas
│   │   └── handlers.py            # Tool execution → AWS Batch
│   │
│   ├── infra/
│   │   ├── aws.py                 # S3, Batch, SES, compute selection
│   │   └── checkpoint.py          # Redis + S3 checkpoint/recovery
│   │
│   └── models/
│       └── schemas.py             # Pydantic models + GENOME_REFERENCES
│
└── web/                           # React frontend
    ├── package.json
    ├── vite.config.js
    ├── tailwind.config.js
    ├── index.html
    │
    └── src/
        ├── main.jsx
        ├── App.jsx                # Router + nav
        ├── api.js                 # API client + WebSocket
        │
        ├── pages/
        │   ├── UploadPage.jsx     # Drag-drop + config form
        │   ├── DashboardPage.jsx  # Job list
        │   └── ResultsPage.jsx    # 9-tab results view
        │
        └── components/
            ├── ChartCard.jsx      # Download wrapper (PNG/SVG/CSV)
            ├── ChatPanel.jsx      # Floating chat window
            ├── ProgressTracker.jsx # Pipeline step progress
            │
            └── charts/
                ├── VolcanoPlot.jsx
                ├── PCAPlot.jsx
                ├── HeatmapPlot.jsx
                ├── GOBubble.jsx
                ├── KEGGBar.jsx
                ├── BiotypePie.jsx
                ├── QCSummary.jsx
                ├── DEGTable.jsx
                ├── AnnotationTable.jsx
                ├── TranscriptPlot.jsx
                ├── WGCNAPlot.jsx
                └── DeconvolutionPlot.jsx
```
