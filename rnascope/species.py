"""Central species resolver — all pipeline handlers use this to get species-specific config.

Every tool handler calls resolve_species(species_key) once to get the correct genome,
annotation database, pathway database, and domain-specific logic flags.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SpeciesConfig:
    key: str
    name: str
    domain: str  # animal, plant, microbe, meta
    genome: str
    gtf: str
    org_db: str  # Bioconductor OrgDb package
    kegg_code: str  # KEGG organism code
    ensembl_dataset: str  # biomaRt dataset name
    # Domain-specific databases
    pathway_dbs: list[str] = field(default_factory=list)
    annotation_dbs: list[str] = field(default_factory=list)
    # Flags
    has_go: bool = True
    has_kegg: bool = True
    has_deconvolution: bool = False
    deconvolution_method: str = ""
    rrna_db: str = "silva"  # silva, rfam
    host_removal_ref: str = ""  # genome for host read removal
    # Plant-specific
    mapman_bin: str = ""  # MapMan bin file for plant pathway mapping
    plantcyc_db: str = ""  # PlantCyc species database
    phytozome_id: str = ""  # Phytozome genome ID


# ---------------------------------------------------------------------------
# Full species registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, SpeciesConfig] = {
    # ==================== ANIMALS ====================
    "human": SpeciesConfig(
        key="human", name="Homo sapiens", domain="animal",
        genome="GRCh38", gtf="Ensembl_110",
        org_db="org.Hs.eg.db", kegg_code="hsa",
        ensembl_dataset="hsapiens_gene_ensembl",
        pathway_dbs=["GO", "KEGG", "Reactome", "MSigDB"],
        annotation_dbs=["Ensembl", "NCBI", "UniProt", "DisGeNET", "DGIdb", "HPA"],
        has_deconvolution=True, deconvolution_method="xcell",
        host_removal_ref="hg38",
    ),
    "mouse": SpeciesConfig(
        key="mouse", name="Mus musculus", domain="animal",
        genome="mm39", gtf="Ensembl_110",
        org_db="org.Mm.eg.db", kegg_code="mmu",
        ensembl_dataset="mmusculus_gene_ensembl",
        pathway_dbs=["GO", "KEGG", "Reactome"],
        annotation_dbs=["Ensembl", "NCBI", "UniProt", "MGI"],
        has_deconvolution=True, deconvolution_method="music",
        host_removal_ref="mm39",
    ),
    "rat": SpeciesConfig(
        key="rat", name="Rattus norvegicus", domain="animal",
        genome="mRatBN7.2", gtf="Ensembl_110",
        org_db="org.Rn.eg.db", kegg_code="rno",
        ensembl_dataset="rnorvegicus_gene_ensembl",
        pathway_dbs=["GO", "KEGG"],
        annotation_dbs=["Ensembl", "NCBI", "UniProt"],
        has_deconvolution=True, deconvolution_method="xcell",
    ),
    "zebrafish": SpeciesConfig(
        key="zebrafish", name="Danio rerio", domain="animal",
        genome="GRCz11", gtf="Ensembl_110",
        org_db="org.Dr.eg.db", kegg_code="dre",
        ensembl_dataset="drerio_gene_ensembl",
        pathway_dbs=["GO", "KEGG"],
        annotation_dbs=["Ensembl", "NCBI", "ZFIN"],
    ),
    "drosophila": SpeciesConfig(
        key="drosophila", name="Drosophila melanogaster", domain="animal",
        genome="dm6", gtf="Ensembl_110",
        org_db="org.Dm.eg.db", kegg_code="dme",
        ensembl_dataset="dmelanogaster_gene_ensembl",
        pathway_dbs=["GO", "KEGG"],
        annotation_dbs=["Ensembl", "FlyBase"],
    ),
    "c_elegans": SpeciesConfig(
        key="c_elegans", name="Caenorhabditis elegans", domain="animal",
        genome="WBcel235", gtf="Ensembl_110",
        org_db="org.Ce.eg.db", kegg_code="cel",
        ensembl_dataset="celegans_gene_ensembl",
        pathway_dbs=["GO", "KEGG"],
        annotation_dbs=["Ensembl", "WormBase"],
    ),
    "chicken": SpeciesConfig(
        key="chicken", name="Gallus gallus", domain="animal",
        genome="GRCg7b", gtf="Ensembl_110",
        org_db="org.Gg.eg.db", kegg_code="gga",
        ensembl_dataset="ggallus_gene_ensembl",
        pathway_dbs=["GO", "KEGG"],
        annotation_dbs=["Ensembl", "NCBI"],
    ),
    "pig": SpeciesConfig(
        key="pig", name="Sus scrofa", domain="animal",
        genome="Sscrofa11.1", gtf="Ensembl_110",
        org_db="org.Ss.eg.db", kegg_code="ssc",
        ensembl_dataset="sscrofa_gene_ensembl",
        pathway_dbs=["GO", "KEGG"],
        annotation_dbs=["Ensembl", "NCBI"],
        has_deconvolution=True, deconvolution_method="xcell",
    ),
    "cow": SpeciesConfig(
        key="cow", name="Bos taurus", domain="animal",
        genome="ARS-UCD1.3", gtf="Ensembl_110",
        org_db="org.Bt.eg.db", kegg_code="bta",
        ensembl_dataset="btaurus_gene_ensembl",
        pathway_dbs=["GO", "KEGG"],
        annotation_dbs=["Ensembl", "NCBI"],
    ),

    # ==================== PLANTS ====================
    "arabidopsis": SpeciesConfig(
        key="arabidopsis", name="Arabidopsis thaliana", domain="plant",
        genome="TAIR10", gtf="Araport11",
        org_db="org.At.tair.db", kegg_code="ath",
        ensembl_dataset="athaliana_eg_gene",
        pathway_dbs=["GO", "KEGG", "MapMan", "PlantCyc", "PlantReactome"],
        annotation_dbs=["TAIR", "Ensembl_Plants", "UniProt", "Phytozome", "PlantRegMap"],
        mapman_bin="Ath_AGI_LOCUS_TAIR10_Aug2012.txt",
        plantcyc_db="AraCyc",
        phytozome_id="Athaliana",
    ),
    "rice": SpeciesConfig(
        key="rice", name="Oryza sativa", domain="plant",
        genome="IRGSP-1.0", gtf="RAP-DB",
        org_db="org.Os.eg.db", kegg_code="osa",
        ensembl_dataset="osativa_eg_gene",
        pathway_dbs=["GO", "KEGG", "MapMan", "PlantCyc", "PlantReactome"],
        annotation_dbs=["RAP-DB", "Ensembl_Plants", "Phytozome", "RiceXPro"],
        mapman_bin="Osa_MSU_v7.txt",
        plantcyc_db="RiceCyc",
        phytozome_id="Osativa",
    ),
    "maize": SpeciesConfig(
        key="maize", name="Zea mays", domain="plant",
        genome="Zm-B73-v5", gtf="Zm00001eb.1",
        org_db="org.Zm.eg.db", kegg_code="zma",
        ensembl_dataset="zmays_eg_gene",
        pathway_dbs=["GO", "KEGG", "MapMan", "PlantCyc"],
        annotation_dbs=["MaizeGDB", "Ensembl_Plants", "Phytozome"],
        mapman_bin="Zma_Zm00001eb.txt",
        plantcyc_db="CornCyc",
        phytozome_id="Zmays",
    ),
    "wheat": SpeciesConfig(
        key="wheat", name="Triticum aestivum", domain="plant",
        genome="IWGSC_v2.1", gtf="IWGSC_v2.1",
        org_db="", kegg_code="tae",
        ensembl_dataset="taestivum_eg_gene",
        pathway_dbs=["GO", "KEGG", "MapMan"],
        annotation_dbs=["Ensembl_Plants", "WheatIS", "Phytozome"],
        has_go=True, has_kegg=True,
        mapman_bin="Tae_IWGSC_v2.1.txt",
    ),
    "tomato": SpeciesConfig(
        key="tomato", name="Solanum lycopersicum", domain="plant",
        genome="SL4.0", gtf="ITAG4.0",
        org_db="", kegg_code="sly",
        ensembl_dataset="slycopersicum_eg_gene",
        pathway_dbs=["GO", "KEGG", "MapMan", "PlantCyc"],
        annotation_dbs=["Sol Genomics", "Ensembl_Plants", "Phytozome"],
        mapman_bin="Sly_ITAG4.0.txt",
        plantcyc_db="TomatoCyc",
        phytozome_id="Slycopersicum",
    ),
    "soybean": SpeciesConfig(
        key="soybean", name="Glycine max", domain="plant",
        genome="Wm82.a4.v1", gtf="Gmax_508",
        org_db="", kegg_code="gmx",
        ensembl_dataset="gmax_eg_gene",
        pathway_dbs=["GO", "KEGG", "MapMan", "PlantCyc"],
        annotation_dbs=["SoyBase", "Ensembl_Plants", "Phytozome"],
        plantcyc_db="SoyCyc",
        phytozome_id="Gmax",
    ),
    "potato": SpeciesConfig(
        key="potato", name="Solanum tuberosum", domain="plant",
        genome="DM_v6.1", gtf="PGSC_DM_v6.1",
        org_db="", kegg_code="stu",
        ensembl_dataset="stuberosum_eg_gene",
        pathway_dbs=["GO", "KEGG", "MapMan"],
        annotation_dbs=["Spud DB", "Ensembl_Plants"],
    ),
    "grape": SpeciesConfig(
        key="grape", name="Vitis vinifera", domain="plant",
        genome="12X.v2", gtf="VCost.v3",
        org_db="", kegg_code="vvi",
        ensembl_dataset="vvinifera_eg_gene",
        pathway_dbs=["GO", "KEGG", "MapMan", "PlantCyc"],
        annotation_dbs=["Ensembl_Plants", "URGI"],
        plantcyc_db="GrapeCyc",
    ),

    # ==================== MICROBE / SOIL / FOOD ====================
    "ecoli": SpeciesConfig(
        key="ecoli", name="Escherichia coli K-12", domain="microbe",
        genome="K-12_MG1655", gtf="NCBI_ASM584",
        org_db="org.EcK12.eg.db", kegg_code="eco",
        ensembl_dataset="",
        pathway_dbs=["GO", "KEGG", "EcoCyc"],
        annotation_dbs=["NCBI", "UniProt", "EcoCyc", "RegulonDB"],
    ),
    "yeast": SpeciesConfig(
        key="yeast", name="Saccharomyces cerevisiae", domain="microbe",
        genome="R64-1-1", gtf="Ensembl_110",
        org_db="org.Sc.sgd.db", kegg_code="sce",
        ensembl_dataset="scerevisiae_gene_ensembl",
        pathway_dbs=["GO", "KEGG", "SGD"],
        annotation_dbs=["SGD", "Ensembl", "UniProt"],
    ),
    "aspergillus": SpeciesConfig(
        key="aspergillus", name="Aspergillus niger", domain="microbe",
        genome="CBS_513.88", gtf="AspGD",
        org_db="", kegg_code="ang",
        ensembl_dataset="",
        pathway_dbs=["GO", "KEGG"],
        annotation_dbs=["AspGD", "NCBI", "UniProt"],
    ),
    "lactobacillus": SpeciesConfig(
        key="lactobacillus", name="Lactobacillus", domain="microbe",
        genome="custom", gtf="custom",
        org_db="", kegg_code="",
        ensembl_dataset="",
        pathway_dbs=["GO", "KEGG"],
        annotation_dbs=["NCBI", "UniProt"],
    ),
    "metatranscriptome": SpeciesConfig(
        key="metatranscriptome", name="Metatranscriptome", domain="meta",
        genome="meta", gtf="meta",
        org_db="", kegg_code="",
        ensembl_dataset="",
        pathway_dbs=["KEGG", "MetaCyc", "HUMAnN3", "eggNOG"],
        annotation_dbs=["NCBI_NR", "UniRef90", "Pfam", "eggNOG"],
        has_go=False,
    ),
    "custom": SpeciesConfig(
        key="custom", name="Custom genome", domain="custom",
        genome="custom", gtf="custom",
        org_db="", kegg_code="",
        ensembl_dataset="",
        pathway_dbs=["GO", "KEGG"],
        annotation_dbs=["NCBI", "UniProt"],
    ),
}


def resolve_species(species_key: str) -> SpeciesConfig:
    """Look up species config. Falls back to 'custom' if unknown."""
    return _REGISTRY.get(species_key, _REGISTRY["custom"])


def is_plant(species_key: str) -> bool:
    return resolve_species(species_key).domain == "plant"


def is_animal(species_key: str) -> bool:
    return resolve_species(species_key).domain == "animal"


def is_microbe(species_key: str) -> bool:
    return resolve_species(species_key).domain == "microbe"


def is_meta(species_key: str) -> bool:
    return resolve_species(species_key).domain == "meta"


def get_org_db(species_key: str) -> str:
    """Return the Bioconductor OrgDb package name, or empty string if none."""
    return resolve_species(species_key).org_db


def get_kegg_code(species_key: str) -> str:
    return resolve_species(species_key).kegg_code


def get_ensembl_dataset(species_key: str) -> str:
    return resolve_species(species_key).ensembl_dataset


def get_annotation_r_code(species_key: str) -> str:
    """Generate the R code snippet for loading the correct annotation source."""
    cfg = resolve_species(species_key)

    if cfg.domain == "plant":
        if cfg.ensembl_dataset:
            return f"""
    library(biomaRt)
    ensembl <- useMart("plants_mart", host="https://plants.ensembl.org",
                       dataset="{cfg.ensembl_dataset}")
    annot <- getBM(
        attributes=c("ensembl_gene_id","external_gene_name","gene_biotype",
                     "chromosome_name","start_position","end_position","description"),
        filters="ensembl_gene_id", values=genes, mart=ensembl
    )"""
        return """
    # Custom plant annotation — load from GTF/GFF3
    library(rtracklayer)
    gff <- import(gtf_path)
    annot <- as.data.frame(gff[gff$type == "gene",])"""

    elif cfg.domain == "microbe":
        return f"""
    library(biomaRt)
    # For microbes: use NCBI-based annotation
    annot <- data.frame(ensembl_gene_id=genes)
    # Fetch from NCBI via rentrez or local GFF"""

    else:
        # Animal (default)
        return f"""
    library(biomaRt)
    ensembl <- useMart("ensembl", dataset="{cfg.ensembl_dataset}")
    annot <- getBM(
        attributes=c("ensembl_gene_id","hgnc_symbol","gene_biotype",
                     "chromosome_name","start_position","end_position","description"),
        filters="ensembl_gene_id", values=genes, mart=ensembl
    )"""


def get_pathway_r_code(species_key: str) -> str:
    """Generate the R code for pathway enrichment appropriate to the species domain."""
    cfg = resolve_species(species_key)

    if cfg.domain == "plant":
        code = f"""
    # ---- Plant pathway enrichment ----
    library(clusterProfiler)"""
        if cfg.org_db:
            code += f"""
    library({cfg.org_db})
    ego_bp <- enrichGO(gene=sig_genes, universe=all_genes,
                       OrgDb={cfg.org_db}, ont="BP", pvalueCutoff=0.05)"""
        else:
            code += """
    # No OrgDb — use Ensembl Plants GO via biomaRt
    library(biomaRt)
    plant_mart <- useMart("plants_mart", host="https://plants.ensembl.org",
                          dataset="{ds}")
    go_annot <- getBM(attributes=c("ensembl_gene_id","go_id","namespace_1003"),
                      filters="ensembl_gene_id", values=all_genes, mart=plant_mart)
    term2gene <- go_annot[,c("go_id","ensembl_gene_id")]
    ego_bp <- enricher(sig_genes, TERM2GENE=term2gene, universe=all_genes,
                       pvalueCutoff=0.05)""".format(ds=cfg.ensembl_dataset)

        if cfg.kegg_code:
            code += f"""
    kk <- enrichKEGG(gene=sig_entrez, organism="{cfg.kegg_code}", pvalueCutoff=0.05)"""

        if cfg.mapman_bin:
            code += f"""
    # MapMan pathway mapping (plant-specific)
    mapman <- read.delim("/refs/mapman/{cfg.mapman_bin}", header=TRUE)
    mapman_enrich <- enricher(sig_genes, TERM2GENE=mapman[,c("BINCODE","IDENTIFIER")],
                              TERM2NAME=mapman[,c("BINCODE","NAME")], pvalueCutoff=0.05)
    write.csv(as.data.frame(mapman_enrich), "/output/mapman_enrichment.csv")"""

        if cfg.plantcyc_db:
            code += f"""
    # PlantCyc metabolic pathways
    plantcyc <- read.delim("/refs/plantcyc/{cfg.plantcyc_db}_pathways.txt")
    pcyc_enrich <- enricher(sig_genes, TERM2GENE=plantcyc[,c("pathway","gene")],
                            pvalueCutoff=0.05)
    write.csv(as.data.frame(pcyc_enrich), "/output/plantcyc_enrichment.csv")"""

        return code

    elif cfg.domain == "microbe":
        code = f"""
    # ---- Microbial pathway enrichment ----
    library(clusterProfiler)"""
        if cfg.org_db:
            code += f"""
    library({cfg.org_db})
    ego_bp <- enrichGO(gene=sig_genes, universe=all_genes,
                       OrgDb={cfg.org_db}, ont="BP", pvalueCutoff=0.05)"""
        if cfg.kegg_code:
            code += f"""
    kk <- enrichKEGG(gene=sig_entrez, organism="{cfg.kegg_code}", pvalueCutoff=0.05)"""
        return code

    elif cfg.domain == "meta":
        return """
    # ---- Metatranscriptome functional profiling ----
    # Use HUMAnN3 for community-level pathway abundance
    # KEGG KO mapping via eggNOG-mapper
    # Skip standard GO/KEGG enrichment — not applicable to mixed communities"""

    else:
        # Animal (default)
        return f"""
    library(clusterProfiler)
    library({cfg.org_db})
    ego_bp <- enrichGO(gene=sig_genes, universe=all_genes,
                       OrgDb={cfg.org_db}, ont="BP", pvalueCutoff=0.05, qvalueCutoff=0.05)
    ego_mf <- enrichGO(gene=sig_genes, universe=all_genes,
                       OrgDb={cfg.org_db}, ont="MF", pvalueCutoff=0.05, qvalueCutoff=0.05)
    ego_cc <- enrichGO(gene=sig_genes, universe=all_genes,
                       OrgDb={cfg.org_db}, ont="CC", pvalueCutoff=0.05, qvalueCutoff=0.05)
    kk_up <- enrichKEGG(gene=sig_up_entrez, organism="{cfg.kegg_code}", pvalueCutoff=0.05)
    kk_down <- enrichKEGG(gene=sig_down_entrez, organism="{cfg.kegg_code}", pvalueCutoff=0.05)"""
