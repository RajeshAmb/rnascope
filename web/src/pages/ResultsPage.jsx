import { useState, useEffect, useRef } from 'react'
import { useParams } from 'react-router-dom'
import { getJob, getResults, connectWebSocket } from '../api'
import ProgressTracker from '../components/ProgressTracker'
import ChatPanel from '../components/ChatPanel'
import ChartCard from '../components/ChartCard'
import VolcanoPlot from '../components/charts/VolcanoPlot'
import PCAPlot from '../components/charts/PCAPlot'
import HeatmapPlot from '../components/charts/HeatmapPlot'
import GOBubble from '../components/charts/GOBubble'
import KEGGBar from '../components/charts/KEGGBar'
import BiotypePie from '../components/charts/BiotypePie'
import QCSummary from '../components/charts/QCSummary'
import DEGTable from '../components/charts/DEGTable'
import AnnotationTable from '../components/charts/AnnotationTable'
import TranscriptPlot from '../components/charts/TranscriptPlot'
import WGCNAPlot from '../components/charts/WGCNAPlot'
import DeconvolutionPlot from '../components/charts/DeconvolutionPlot'
import VennDiagram from '../components/charts/VennDiagram'
import TreatmentHeatmap from '../components/charts/TreatmentHeatmap'
import { BaseQualityPlot, GCContentPlot, AdapterContentPlot } from '../components/charts/FastQCPlots'
import { MappingRatePlot, ReadDistributionPlot, GeneBodyCoveragePlot } from '../components/charts/AlignmentPlots'
import { ExpressionBoxplot, ExpressionDensity, CorrelationHeatmap } from '../components/charts/ExpressionPlots'
import { MAPlot, DispersionPlot, TimeSeriesPlot } from '../components/charts/DEGAdvancedPlots'
import BiomarkerPlot from '../components/charts/BiomarkerPlot'
import GeneBrowser from '../components/charts/GeneBrowser'
import SampleDistancePlot from '../components/charts/SampleDistancePlot'
import PlantEnrichment from '../components/charts/PlantEnrichment'
import TFEnrichment from '../components/charts/TFEnrichment'
import MethodsText from '../components/charts/MethodsText'
import { Loader2, Lightbulb, FlaskConical, BookOpen, Download } from 'lucide-react'

const ALL_TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'fastqc', label: 'FastQC' },
  { key: 'alignment', label: 'Alignment' },
  { key: 'expression', label: 'Expression' },
  { key: 'qc', label: 'QC Summary' },
  { key: 'deg', label: 'DEG' },
  { key: 'biomarkers', label: 'Biomarkers' },
  { key: 'transcripts', label: 'Transcripts' },
  { key: 'annotation', label: 'Annotation' },
  { key: 'pathway', label: 'Pathways' },
  { key: 'wgcna', label: 'Network' },
  { key: 'deconv', label: 'Cell Types', domains: ['animal'] },
  { key: 'browser', label: 'Gene Browser' },
  { key: 'plant', label: 'Plant Pathways', domains: ['plant'] },
  { key: 'methods', label: 'Methods' },
  { key: 'interpretation', label: 'AI' },
]

// ---- CSV builder helpers ----

function volcanoCSV(data) {
  if (!data) return null
  return {
    filename: 'volcano_data.csv',
    headers: ['gene', 'log2fc', 'pvalue', 'fdr', 'neg_log10_pvalue', 'significant', 'direction'],
    rows: data.map((d) => [d.gene, d.log2fc, d.pvalue, d.fdr, d.neg_log10_pvalue, d.significant, d.direction]),
  }
}

function pcaCSV(data) {
  if (!data) return null
  return {
    filename: 'pca_data.csv',
    headers: ['sample', 'condition', 'pc1', 'pc2'],
    rows: data.map((d) => [d.sample, d.condition, d.pc1, d.pc2]),
  }
}

function heatmapCSV(data) {
  if (!data || !data.matrix) return null
  return {
    filename: 'heatmap_data.csv',
    headers: ['gene', ...data.samples],
    rows: data.genes.map((g, i) => [g, ...data.matrix[i]]),
  }
}

function goCSV(data) {
  if (!data) return null
  return {
    filename: 'go_enrichment.csv',
    headers: ['term', 'source', 'gene_count', 'gene_ratio', 'pvalue', 'neg_log10_pvalue'],
    rows: data.map((d) => [d.term, d.source, d.count, d.gene_ratio, d.pvalue, d.neg_log10_pvalue]),
  }
}

function keggCSV(data) {
  if (!data) return null
  return {
    filename: 'kegg_pathways.csv',
    headers: ['pathway', 'direction', 'gene_count', 'pvalue', 'neg_log10_pvalue'],
    rows: data.map((d) => [d.pathway, d.direction, d.count, d.pvalue, d.neg_log10_pvalue]),
  }
}

function biotypesCSV(data) {
  if (!data) return null
  return {
    filename: 'biotype_distribution.csv',
    headers: ['biotype', 'count', 'percent'],
    rows: data.map((d) => [d.biotype, d.count, d.pct]),
  }
}

function qcCSV(data) {
  if (!data || !data.samples) return null
  return {
    filename: 'qc_metrics.csv',
    headers: ['sample', 'condition', 'total_reads_m', 'q30_pct', 'mapping_rate', 'duplication_pct', 'rrna_pct', 'passed'],
    rows: data.samples.map((s) => [s.sample, s.condition, s.total_reads_m, s.q30_pct, s.mapping_rate, s.duplication_pct, s.rrna_pct, s.passed]),
  }
}

function transcriptCSV(data) {
  if (!data) return null
  return {
    filename: 'transcript_tpm.csv',
    headers: ['gene_symbol', 'transcript_id', 'tpm', 'is_primary'],
    rows: data.top_isoforms.map((d) => [d.gene_symbol, d.transcript_id, d.tpm, d.is_primary]),
  }
}

function wgcnaCSV(data) {
  if (!data) return null
  return {
    filename: 'wgcna_modules.csv',
    headers: ['module', 'n_genes', 'cor_trait', 'pvalue', 'top_go_term', 'hub_genes'],
    rows: data.modules.map((m) => [m.color, m.n_genes, m.cor_trait, m.pvalue, m.top_go_term, m.hub_genes.join(';')]),
  }
}

function deconvCSV(data) {
  if (!data) return null
  return {
    filename: 'cell_type_fractions.csv',
    headers: ['sample', ...data.cell_types],
    rows: data.samples.map((s, i) => [s, ...data.cell_types.map((ct) => data.fractions[i][ct] || 0)]),
  }
}

function degCSV(volcano) {
  if (!volcano) return null
  const sig = volcano.filter((g) => g.significant).sort((a, b) => Math.abs(b.log2fc) - Math.abs(a.log2fc))
  return {
    filename: 'deg_significant.csv',
    headers: ['gene', 'log2fc', 'pvalue', 'fdr', 'direction'],
    rows: sig.map((g) => [g.gene, g.log2fc, g.pvalue, g.fdr, g.direction]),
  }
}

function downloadAllCSV(results) {
  const csvs = [
    volcanoCSV(results.volcano),
    pcaCSV(results.pca),
    heatmapCSV(results.heatmap),
    goCSV(results.go_enrichment),
    keggCSV(results.kegg_pathways),
    biotypesCSV(results.biotypes),
    qcCSV(results.qc_summary),
    degCSV(results.volcano),
  ].filter(Boolean)

  for (const csv of csvs) {
    const escaped = (v) => {
      const s = String(v ?? '')
      return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s
    }
    const lines = [csv.headers.map(escaped).join(',')]
    for (const row of csv.rows) lines.push(row.map(escaped).join(','))
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = csv.filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }
}

// ---- Main component ----

export default function ResultsPage() {
  const { jobId } = useParams()
  const [job, setJob] = useState(null)
  const [results, setResults] = useState(null)
  const [activeTab, setActiveTab] = useState('overview')
  const [loading, setLoading] = useState(true)
  const [fdrThreshold, setFdrThreshold] = useState(0.05)
  const [lfcThreshold, setLfcThreshold] = useState(1.0)
  const wsRef = useRef(null)

  // Plotly chart refs for image export
  const volcanoRef = useRef(null)
  const volcanoRef2 = useRef(null)
  const pcaRef = useRef(null)
  const heatmapRef = useRef(null)
  const goRef = useRef(null)
  const keggRef = useRef(null)
  const biotypesRef = useRef(null)
  const transcriptRef = useRef(null)
  const wgcnaRef = useRef(null)
  const deconvRef = useRef(null)
  const vennRef = useRef(null)
  const treatmentHeatmapRef = useRef(null)
  const baseQualRef = useRef(null)
  const gcRef = useRef(null)
  const adapterRef = useRef(null)
  const mappingRef = useRef(null)
  const readDistRef = useRef(null)
  const geneBodyRef = useRef(null)
  const exprBoxRef = useRef(null)
  const exprDensRef = useRef(null)
  const corrRef = useRef(null)
  const maRef = useRef(null)
  const dispRef = useRef(null)
  const timeSeriesRef = useRef(null)
  const sampleDistRef = useRef(null)
  const plantEnrichRef = useRef(null)
  const tfEnrichRef = useRef(null)

  useEffect(() => {
    const load = async () => {
      try {
        const j = await getJob(jobId)
        setJob(j)
        if (j.status === 'completed') {
          const r = await getResults(jobId)
          setResults(r)
        }
      } catch {}
      setLoading(false)
    }
    load()
  }, [jobId])

  useEffect(() => {
    const ws = connectWebSocket(jobId, (msg) => {
      if (msg.type === 'step_update') {
        setJob((prev) =>
          prev ? { ...prev, current_step: msg.step, pct_complete: msg.pct_complete, steps_completed: msg.steps_completed } : prev
        )
      }
      if (msg.type === 'pipeline_complete') {
        setJob((prev) => (prev ? { ...prev, status: 'completed', pct_complete: 100 } : prev))
        getResults(jobId).then((r) => setResults(r))
      }
    })
    wsRef.current = ws
    return () => ws.close()
  }, [jobId])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-brand-600" />
      </div>
    )
  }

  if (!job) return <div className="text-center py-20 text-gray-600">Job not found.</div>

  const isRunning = job.status === 'running'

  return (
    <div>
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <FlaskConical className="w-7 h-7 text-brand-600" />
            <h1 className="text-2xl font-bold text-gray-900">{job.project_name || jobId}</h1>
            <span
              className={`ml-3 text-xs font-medium px-2.5 py-1 rounded-full ${
                job.status === 'completed'
                  ? 'bg-green-100 text-green-700'
                  : job.status === 'running'
                  ? 'bg-blue-100 text-blue-700'
                  : 'bg-gray-100 text-gray-600'
              }`}
            >
              {job.status}
            </span>
          </div>
          <p className="text-sm text-gray-500">
            {job.species} &middot; {job.condition_a} vs {job.condition_b} &middot; {job.n_samples || job.n_a + job.n_b} samples &middot; Job {jobId}
          </p>
        </div>

        {/* Download All button */}
        {results && (
          <button
            onClick={() => downloadAllCSV(results)}
            className="flex items-center gap-2 px-4 py-2.5 bg-brand-600 hover:bg-brand-700 text-white text-sm font-medium rounded-xl transition shadow-sm"
          >
            <Download className="w-4 h-4" />
            Download All CSV
          </button>
        )}
      </div>

      {/* Pipeline in progress */}
      {isRunning && (
        <div className="mb-8">
          <ProgressTracker
            currentStep={job.current_step}
            stepsCompleted={job.steps_completed}
            pctComplete={job.pct_complete}
          />
        </div>
      )}

      {/* Results tabs */}
      {results && (
        <>
          <div className="flex gap-1 mb-6 bg-white rounded-xl border border-gray-200 p-1 shadow-sm">
            {ALL_TABS.filter((tab) => !tab.domains || tab.domains.includes(results.domain || 'animal')).map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex-1 py-2.5 px-4 rounded-lg text-sm font-medium transition ${
                  activeTab === tab.key ? 'bg-brand-600 text-white shadow-sm' : 'text-gray-600 hover:bg-gray-100'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* ============ OVERVIEW TAB ============ */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              {results.interpretation?.executive_summary && (
                <div className="bg-gradient-to-r from-brand-50 to-purple-50 rounded-xl border border-brand-200 p-6">
                  <div className="flex items-center gap-2 mb-3">
                    <Lightbulb className="w-5 h-5 text-brand-600" />
                    <h3 className="font-semibold text-brand-900">AI Summary</h3>
                  </div>
                  <p className="text-gray-800 leading-relaxed">{results.interpretation.executive_summary}</p>
                </div>
              )}

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <ChartCard title="Differential Expression" csvData={degCSV(results.volcano)}>
                  <DEGTable data={results.deg_summary} volcano={results.volcano} />
                </ChartCard>
                <ChartCard title="Volcano Plot" plotRef={volcanoRef} csvData={volcanoCSV(results.volcano)}>
                  <VolcanoPlot ref={volcanoRef} data={results.volcano} />
                </ChartCard>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <ChartCard title="PCA — Sample Clustering" plotRef={pcaRef} csvData={pcaCSV(results.pca)}>
                  <PCAPlot ref={pcaRef} data={results.pca} />
                </ChartCard>
                <ChartCard title="RNA Biotype Distribution" plotRef={biotypesRef} csvData={biotypesCSV(results.biotypes)}>
                  <BiotypePie ref={biotypesRef} data={results.biotypes} />
                </ChartCard>
              </div>
            </div>
          )}

          {/* ============ FASTQC TAB ============ */}
          {activeTab === 'fastqc' && results.fastqc && (
            <div className="space-y-6">
              <ChartCard title="Per Base Sequence Quality" plotRef={baseQualRef}>
                <BaseQualityPlot ref={baseQualRef} data={results.fastqc.base_quality} />
              </ChartCard>
              <ChartCard title="GC Content Distribution" plotRef={gcRef}>
                <GCContentPlot ref={gcRef} data={results.fastqc.gc_content} />
              </ChartCard>
              <ChartCard title="Adapter Content" plotRef={adapterRef}>
                <AdapterContentPlot ref={adapterRef} data={results.fastqc.adapter_content} />
              </ChartCard>
            </div>
          )}

          {/* ============ ALIGNMENT TAB ============ */}
          {activeTab === 'alignment' && results.alignment && (
            <div className="space-y-6">
              <ChartCard title="Mapping Rate" plotRef={mappingRef}>
                <MappingRatePlot ref={mappingRef} data={results.alignment.mapping_rate} />
              </ChartCard>
              <ChartCard title="Read Distribution" plotRef={readDistRef}>
                <ReadDistributionPlot ref={readDistRef} data={results.alignment.read_distribution} />
              </ChartCard>
              <ChartCard title="Gene Body Coverage" plotRef={geneBodyRef}>
                <GeneBodyCoveragePlot ref={geneBodyRef} data={results.alignment.gene_body_coverage} />
              </ChartCard>
            </div>
          )}

          {/* ============ EXPRESSION TAB ============ */}
          {activeTab === 'expression' && (
            <div className="space-y-6">
              {results.expression_dist && (
                <ChartCard title="Expression Distribution (Boxplot)" plotRef={exprBoxRef}>
                  <ExpressionBoxplot ref={exprBoxRef} data={results.expression_dist} />
                </ChartCard>
              )}
              {results.expression_dist && (
                <ChartCard title="Expression Density" plotRef={exprDensRef}>
                  <ExpressionDensity ref={exprDensRef} data={results.expression_dist} />
                </ChartCard>
              )}
              {results.correlation && (
                <ChartCard title="Sample Correlation Heatmap" plotRef={corrRef}>
                  <CorrelationHeatmap ref={corrRef} data={results.correlation} />
                </ChartCard>
              )}
              {results.correlation && (
                <ChartCard title="Sample Distance Heatmap" plotRef={sampleDistRef}>
                  <SampleDistancePlot ref={sampleDistRef} data={results.correlation} />
                </ChartCard>
              )}
            </div>
          )}

          {/* ============ QC SUMMARY TAB ============ */}
          {activeTab === 'qc' && (
            <ChartCard title="Quality Control Metrics" csvData={qcCSV(results.qc_summary)}>
              <QCSummary data={results.qc_summary} />
            </ChartCard>
          )}

          {/* ============ DEG TAB ============ */}
          {activeTab === 'deg' && (
            <div className="space-y-6">
              {/* Threshold controls */}
              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
                <h3 className="font-semibold text-gray-800 mb-4">Significance Thresholds</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* FDR slider */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-sm font-medium text-gray-700">FDR threshold</label>
                      <span className="text-sm font-semibold text-brand-700 font-mono">{fdrThreshold}</span>
                    </div>
                    <input
                      type="range"
                      min={0.001}
                      max={0.1}
                      step={0.001}
                      value={fdrThreshold}
                      onChange={(e) => setFdrThreshold(parseFloat(e.target.value))}
                      className="w-full accent-brand-600"
                    />
                    <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                      <span>0.001</span><span>0.1</span>
                    </div>
                  </div>
                  {/* log2FC slider */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-sm font-medium text-gray-700">|log2FC| threshold</label>
                      <span className="text-sm font-semibold text-brand-700 font-mono">{lfcThreshold.toFixed(1)}</span>
                    </div>
                    <input
                      type="range"
                      min={0.5}
                      max={3.0}
                      step={0.1}
                      value={lfcThreshold}
                      onChange={(e) => setLfcThreshold(parseFloat(e.target.value))}
                      className="w-full accent-brand-600"
                    />
                    <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                      <span>0.5</span><span>3.0</span>
                    </div>
                  </div>
                </div>
                {/* Live count */}
                {results.volcano && (
                  <p className="mt-3 text-sm text-gray-500">
                    Significant genes at current thresholds:{' '}
                    <span className="font-bold text-brand-700">
                      {results.volcano.filter((g) => g.fdr <= fdrThreshold && Math.abs(g.log2fc) >= lfcThreshold).length}
                    </span>{' '}
                    /{' '}
                    <span className="text-gray-600">{results.volcano.length} tested</span>
                  </p>
                )}
              </div>

              <ChartCard title="DEG Summary" csvData={degCSV(results.volcano)}>
                <DEGTable data={results.deg_summary} volcano={results.volcano} fdrThreshold={fdrThreshold} lfcThreshold={lfcThreshold} />
              </ChartCard>
              <ChartCard title="Volcano Plot" plotRef={volcanoRef2} csvData={volcanoCSV(results.volcano)}>
                <VolcanoPlot ref={volcanoRef2} data={results.volcano} fdrThreshold={fdrThreshold} lfcThreshold={lfcThreshold} />
              </ChartCard>
              <ChartCard title="Expression Heatmap" plotRef={heatmapRef} csvData={heatmapCSV(results.heatmap)}>
                <HeatmapPlot ref={heatmapRef} data={results.heatmap} />
              </ChartCard>
              {results.venn && (
                <ChartCard title="Venn Diagram — Up-regulated DEGs" plotRef={vennRef}>
                  <VennDiagram ref={vennRef} data={results.venn} />
                </ChartCard>
              )}
              {results.ma_plot && (
                <ChartCard title="MA Plot" plotRef={maRef}>
                  <MAPlot ref={maRef} data={results.ma_plot} />
                </ChartCard>
              )}
              {results.dispersion && (
                <ChartCard title="Dispersion Estimates" plotRef={dispRef}>
                  <DispersionPlot ref={dispRef} data={results.dispersion} />
                </ChartCard>
              )}
              {results.treatment_heatmap && (
                <ChartCard title="Treatment-wise Expression Profiles" plotRef={treatmentHeatmapRef}>
                  <TreatmentHeatmap ref={treatmentHeatmapRef} data={results.treatment_heatmap} />
                </ChartCard>
              )}
              {results.time_series && (
                <ChartCard title="Time-Series Expression" plotRef={timeSeriesRef}>
                  <TimeSeriesPlot ref={timeSeriesRef} data={results.time_series} />
                </ChartCard>
              )}
            </div>
          )}

          {/* ============ BIOMARKERS TAB ============ */}
          {activeTab === 'biomarkers' && results.biomarkers && (
            <ChartCard title="ML Biomarker Selection">
              <BiomarkerPlot biomarkers={results.biomarkers} />
            </ChartCard>
          )}

          {/* ============ TRANSCRIPTS TAB ============ */}
          {activeTab === 'transcripts' && results.transcripts && (
            <ChartCard title="Transcript-Level Quantification (Salmon)" plotRef={transcriptRef} csvData={transcriptCSV(results.transcripts)}>
              <TranscriptPlot ref={transcriptRef} data={results.transcripts} />
            </ChartCard>
          )}

          {/* ============ ANNOTATION TAB ============ */}
          {activeTab === 'annotation' && (
            <ChartCard title="Functional Annotation" csvData={degCSV(results.volcano)}>
              <AnnotationTable volcano={results.volcano} annotations={results.annotations} />
            </ChartCard>
          )}

          {/* ============ PATHWAY TAB ============ */}
          {activeTab === 'pathway' && (
            <div className="space-y-6">
              <ChartCard title="GO Enrichment" plotRef={goRef} csvData={goCSV(results.go_enrichment)}>
                <GOBubble ref={goRef} data={results.go_enrichment} />
              </ChartCard>
              <ChartCard title="KEGG Pathway Enrichment" plotRef={keggRef} csvData={keggCSV(results.kegg_pathways)}>
                <KEGGBar ref={keggRef} data={results.kegg_pathways} />
              </ChartCard>
            </div>
          )}

          {/* ============ WGCNA TAB ============ */}
          {activeTab === 'wgcna' && results.wgcna && (
            <ChartCard title="WGCNA Co-expression Network" plotRef={wgcnaRef} csvData={wgcnaCSV(results.wgcna)}>
              <WGCNAPlot ref={wgcnaRef} data={results.wgcna} />
            </ChartCard>
          )}

          {/* ============ CELL TYPES TAB ============ */}
          {activeTab === 'deconv' && results.deconvolution && (
            <ChartCard title="Cell Type Deconvolution" plotRef={deconvRef} csvData={deconvCSV(results.deconvolution)}>
              <DeconvolutionPlot ref={deconvRef} data={results.deconvolution} />
            </ChartCard>
          )}

          {/* ============ GENE BROWSER TAB ============ */}
          {activeTab === 'browser' && (
            <ChartCard title="Gene Expression Browser">
              <GeneBrowser data={results.heatmap} />
            </ChartCard>
          )}

          {/* ============ PLANT PATHWAYS TAB ============ */}
          {activeTab === 'plant' && (
            <div className="space-y-6">
              {results.plant_enrichment ? (
                <ChartCard title="Plant-specific Pathway Enrichment" plotRef={plantEnrichRef}>
                  <PlantEnrichment ref={plantEnrichRef} data={results.plant_enrichment} />
                </ChartCard>
              ) : (
                <div className="text-center py-10 text-gray-400">Plant enrichment data not available.</div>
              )}
              {results.tf_enrichment && (
                <ChartCard title="Transcription Factor Enrichment" plotRef={tfEnrichRef}>
                  <TFEnrichment ref={tfEnrichRef} data={results.tf_enrichment} />
                </ChartCard>
              )}
            </div>
          )}

          {/* ============ METHODS TAB ============ */}
          {activeTab === 'methods' && (
            <ChartCard title="Methods">
              <MethodsText data={results.methods_text} />
            </ChartCard>
          )}

          {/* ============ INTERPRETATION TAB ============ */}
          {activeTab === 'interpretation' && results.interpretation && (
            <div className="space-y-6">
              <div className="bg-gradient-to-r from-brand-50 to-purple-50 rounded-xl border border-brand-200 p-6">
                <div className="flex items-center gap-2 mb-3">
                  <Lightbulb className="w-5 h-5 text-brand-600" />
                  <h3 className="font-semibold text-brand-900">Executive Summary</h3>
                </div>
                <p className="text-gray-800 leading-relaxed">{results.interpretation.executive_summary}</p>
              </div>

              <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
                <div className="flex items-center gap-2 mb-4">
                  <BookOpen className="w-5 h-5 text-purple-600" />
                  <h3 className="font-semibold text-gray-900">Biological Hypotheses</h3>
                </div>
                <div className="space-y-4">
                  {(results.interpretation.top_hypotheses || []).map((h, i) => (
                    <div key={i} className="border border-gray-100 rounded-lg p-4 bg-gray-50">
                      <h4 className="font-semibold text-gray-900 mb-2">
                        <span className="text-brand-600">{h.id}:</span> {h.hypothesis}
                      </h4>
                      <p className="text-sm text-gray-700 mb-1">
                        <span className="font-medium">Rationale:</span> {h.rationale}
                      </p>
                      <p className="text-sm text-gray-700">
                        <span className="font-medium">Experiment:</span> {h.test}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {!results && !isRunning && (
        <div className="text-center py-16 text-gray-500">No results available yet.</div>
      )}

      <ChatPanel jobId={jobId} results={results} />
    </div>
  )
}
