import { useState, useRef, useEffect } from 'react'
import { askChat } from '../api'
import { MessageCircle, Send, Loader2, X, Image, Download } from 'lucide-react'
import Plot from '../PlotlyChart'

// ---------------------------------------------------------------------------
// Local graph command parser — works without Anthropic API
// ---------------------------------------------------------------------------
function parseGraphCommand(question, results) {
  if (!results) return null
  const q = question.toLowerCase()
  const volcano = results.volcano || []
  const sigGenes = volcano.filter(g => g.significant)
  const heatmap = results.heatmap || {}
  const go = results.go_enrichment || []
  const kegg = results.kegg_pathways || []
  const biomarkers = results.biomarkers || {}

  // --- Bar chart of top N up/down regulated genes ---
  const barMatch = q.match(/(?:bar\s*chart|show|plot|graph|list).*?(?:top\s*)?(\d+)?\s*(?:most\s+)?(up|down|upregulated|downregulated|significant|de[g]?\b)/i)
  if (barMatch || q.includes('top genes') || q.includes('top deg') || (q.includes('bar') && q.includes('gene'))) {
    const n = parseInt(barMatch?.[1]) || 10
    const dir = barMatch?.[2]?.toLowerCase()
    let filtered = sigGenes
    if (dir && (dir.startsWith('up'))) filtered = sigGenes.filter(g => g.log2fc > 0)
    else if (dir && (dir.startsWith('down'))) filtered = sigGenes.filter(g => g.log2fc < 0)
    const top = [...filtered].sort((a, b) => Math.abs(b.log2fc) - Math.abs(a.log2fc)).slice(0, n)
    if (top.length === 0) return null

    return {
      answer: `Here's a bar chart of the top ${top.length} ${dir || 'significant'} genes by fold change:`,
      chart: {
        data: [{
          x: top.map(g => g.gene),
          y: top.map(g => g.log2fc),
          type: 'bar',
          marker: { color: top.map(g => g.log2fc > 0 ? '#ef4444' : '#3b82f6') },
          hovertemplate: '<b>%{x}</b><br>log2FC: %{y:.2f}<extra></extra>',
        }],
        layout: {
          title: `Top ${top.length} ${dir || 'DE'} Genes`,
          xaxis: { title: 'Gene', tickangle: -45 },
          yaxis: { title: 'log2 Fold Change' },
          height: 350, margin: { t: 40, b: 100, l: 60, r: 20 },
        },
      },
    }
  }

  // --- GO biological process ---
  if (q.includes('go') && (q.includes('biological') || q.includes('bp') || q.includes('process') || q.includes('enrichment'))) {
    const bp = go.filter(t => t.source === 'GO_BP')
    if (bp.length === 0) return null
    return {
      answer: `Here are the GO Biological Process enrichment results:`,
      chart: {
        data: [{
          y: bp.map(t => t.term).reverse(),
          x: bp.map(t => t.gene_ratio).reverse(),
          type: 'bar',
          orientation: 'h',
          marker: { color: bp.map(t => t.count).reverse(), colorscale: 'Viridis', showscale: true, colorbar: { title: 'Gene count' } },
          hovertemplate: '<b>%{y}</b><br>Gene ratio: %{x:.3f}<extra></extra>',
        }],
        layout: {
          title: 'GO Biological Process',
          xaxis: { title: 'Gene Ratio' },
          height: 400, margin: { t: 40, b: 40, l: 250, r: 20 },
        },
      },
    }
  }

  // --- KEGG pathways ---
  if (q.includes('kegg') || (q.includes('pathway') && !q.includes('plant'))) {
    if (kegg.length === 0) return null
    return {
      answer: `Here are the KEGG pathway enrichment results:`,
      chart: {
        data: [{
          y: kegg.map(p => p.pathway).reverse(),
          x: kegg.map((_, i) => kegg.length - i).reverse(),
          type: 'bar',
          orientation: 'h',
          marker: { color: kegg.map(p => p.direction === 'up' ? '#ef4444' : '#3b82f6').reverse() },
        }],
        layout: {
          title: 'KEGG Pathways',
          xaxis: { title: 'Enrichment Score' },
          height: 400, margin: { t: 40, b: 40, l: 280, r: 20 },
        },
      },
    }
  }

  // --- Volcano plot ---
  if (q.includes('volcano')) {
    const up = volcano.filter(g => g.direction === 'up')
    const down = volcano.filter(g => g.direction === 'down')
    const ns = volcano.filter(g => g.direction === 'ns')
    return {
      answer: `Here's the volcano plot (${up.length} up, ${down.length} down, ${ns.length} NS):`,
      chart: {
        data: [
          { x: up.map(g => g.log2fc), y: up.map(g => g.neg_log10_pvalue), text: up.map(g => g.gene), mode: 'markers', type: 'scatter', name: 'Up', marker: { color: '#ef4444', size: 6 }, hovertemplate: '<b>%{text}</b><br>log2FC: %{x:.2f}<br>-log10p: %{y:.2f}<extra></extra>' },
          { x: down.map(g => g.log2fc), y: down.map(g => g.neg_log10_pvalue), text: down.map(g => g.gene), mode: 'markers', type: 'scatter', name: 'Down', marker: { color: '#3b82f6', size: 6 }, hovertemplate: '<b>%{text}</b><br>log2FC: %{x:.2f}<br>-log10p: %{y:.2f}<extra></extra>' },
          { x: ns.map(g => g.log2fc), y: ns.map(g => g.neg_log10_pvalue), mode: 'markers', type: 'scatter', name: 'NS', marker: { color: '#d1d5db', size: 4, opacity: 0.5 } },
        ],
        layout: { title: 'Volcano Plot', xaxis: { title: 'log2 Fold Change' }, yaxis: { title: '-log10(p-value)' }, height: 400, margin: { t: 40, b: 40, l: 60, r: 20 } },
      },
    }
  }

  // --- PCA plot ---
  if (q.includes('pca')) {
    const pca = results.pca || []
    const conditions = [...new Set(pca.map(p => p.condition))]
    const colors = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b']
    return {
      answer: `Here's the PCA plot:`,
      chart: {
        data: conditions.map((c, i) => {
          const pts = pca.filter(p => p.condition === c)
          return { x: pts.map(p => p.pc1), y: pts.map(p => p.pc2), text: pts.map(p => p.sample), mode: 'markers+text', type: 'scatter', name: c, textposition: 'top center', marker: { size: 12, color: colors[i % 4] } }
        }),
        layout: { title: 'PCA Plot', xaxis: { title: 'PC1' }, yaxis: { title: 'PC2' }, height: 400, margin: { t: 40, b: 40, l: 60, r: 20 } },
      },
    }
  }

  // --- Specific gene expression ---
  const geneMatch = q.match(/(?:expression|show|plot|graph)\s+(?:of\s+)?(?:gene\s+)?([A-Za-z][A-Za-z0-9_/.-]+)/i)
  if (geneMatch && heatmap.genes) {
    const geneName = geneMatch[1]
    const idx = heatmap.genes?.findIndex(g => g.toLowerCase() === geneName.toLowerCase())
    if (idx >= 0 && heatmap.matrix) {
      const values = heatmap.matrix[idx]
      const samples = heatmap.samples || values.map((_, i) => `S${i + 1}`)
      return {
        answer: `Expression of **${heatmap.genes[idx]}** across samples:`,
        chart: {
          data: [{
            x: samples,
            y: values,
            type: 'bar',
            marker: { color: '#8b5cf6' },
          }],
          layout: { title: `${heatmap.genes[idx]} Expression`, xaxis: { title: 'Sample' }, yaxis: { title: 'Expression (z-score)' }, height: 300, margin: { t: 40, b: 60, l: 60, r: 20 } },
        },
      }
    }
  }

  // --- Biomarker summary ---
  if (q.includes('biomarker') || q.includes('feature importance') || q.includes('random forest')) {
    const rf = biomarkers.random_forest
    if (rf && rf.length > 0) {
      const top = rf.slice(0, 15)
      return {
        answer: `Random Forest feature importance — top ${top.length} biomarker genes:`,
        chart: {
          data: [{
            y: top.map(g => g.gene).reverse(),
            x: top.map(g => g.importance).reverse(),
            type: 'bar',
            orientation: 'h',
            marker: { color: '#3b82f6' },
          }],
          layout: { title: 'RF Feature Importance', xaxis: { title: 'Importance' }, height: 400, margin: { t: 40, b: 40, l: 120, r: 20 } },
        },
      }
    }
  }

  // --- Heatmap ---
  if (q.includes('heatmap')) {
    if (heatmap.matrix && heatmap.genes) {
      const n = Math.min(30, heatmap.genes.length)
      return {
        answer: `Expression heatmap of top ${n} DE genes:`,
        chart: {
          data: [{
            z: heatmap.matrix.slice(0, n),
            y: heatmap.genes.slice(0, n),
            x: heatmap.samples || [],
            type: 'heatmap',
            colorscale: [[0, '#3b82f6'], [0.5, '#ffffff'], [1, '#ef4444']],
          }],
          layout: { title: 'Expression Heatmap', height: 500, margin: { t: 40, b: 60, l: 120, r: 20 } },
        },
      }
    }
  }

  // --- QC summary ---
  if (q.includes('qc') || q.includes('quality')) {
    const qc = results.qc_summary
    if (qc && qc.samples) {
      return {
        answer: `QC metrics across ${qc.samples.length} samples:`,
        chart: {
          data: [
            { x: qc.samples.map(s => s.sample), y: qc.samples.map(s => s.mapping_rate), name: 'Mapping %', type: 'bar', marker: { color: '#10b981' } },
            { x: qc.samples.map(s => s.sample), y: qc.samples.map(s => s.q30_pct), name: 'Q30 %', type: 'bar', marker: { color: '#3b82f6' } },
          ],
          layout: { title: 'QC Metrics', barmode: 'group', xaxis: { title: 'Sample' }, yaxis: { title: '%' }, height: 350, margin: { t: 40, b: 60, l: 60, r: 20 } },
        },
      }
    }
  }

  // --- Pie chart ---
  if (q.includes('pie') || q.includes('biotype')) {
    const bio = results.biotypes
    if (bio) {
      return {
        answer: `RNA biotype distribution:`,
        chart: {
          data: [{
            labels: bio.map(b => b.biotype),
            values: bio.map(b => b.count),
            type: 'pie',
            hole: 0.4,
          }],
          layout: { title: 'RNA Biotypes', height: 350, margin: { t: 40, b: 20, l: 20, r: 20 } },
        },
      }
    }
  }

  return null // no graph command detected
}

// ---------------------------------------------------------------------------
// Chat Panel component
// ---------------------------------------------------------------------------
export default function ChatPanel({ jobId, results }) {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      text: `Hi! I can answer questions and **generate graphs** from your results. Try:\n\n` +
        `- "bar chart of top 10 upregulated genes"\n` +
        `- "show volcano plot"\n` +
        `- "expression of GaPR1"\n` +
        `- "GO biological process"\n` +
        `- "show heatmap"\n` +
        `- "biomarker feature importance"\n` +
        `- "QC summary"\n` +
        `- "PCA plot"`,
    },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [uploadedImage, setUploadedImage] = useState(null)
  const bottomRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleImageUpload = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (evt) => {
      setUploadedImage({ name: file.name, src: evt.target.result })
      setMessages(m => [...m, { role: 'user', text: `[Uploaded screenshot: ${file.name}]`, image: evt.target.result }])
    }
    reader.readAsDataURL(file)
    e.target.value = '' // reset
  }

  const send = async () => {
    if (!input.trim() || loading) return
    const q = input.trim()
    setInput('')
    setMessages(m => [...m, { role: 'user', text: q }])
    setLoading(true)

    // Try local graph command first
    const graphResult = parseGraphCommand(q, results)
    if (graphResult) {
      setMessages(m => [...m, {
        role: 'assistant',
        text: graphResult.answer,
        chart: graphResult.chart,
      }])
      setLoading(false)
      return
    }

    // Fallback to API
    try {
      const res = await askChat(jobId, q)
      const msg = { role: 'assistant', text: res.answer }
      if (res.chart) msg.chart = res.chart
      setMessages(m => [...m, msg])
    } catch {
      setMessages(m => [...m, { role: 'assistant', text: 'Sorry, I encountered an error. Try asking for a specific graph like "bar chart of top 10 genes".' }])
    }
    setLoading(false)
    setUploadedImage(null)
  }

  const downloadChart = (chartDiv) => {
    if (!chartDiv) return
    // Plotly is already loaded via PlotlyChart.js
    const { Plotly } = require('../PlotlyChart')
    Plotly.downloadImage(chartDiv, { format: 'png', width: 1200, height: 600, filename: 'rnascope_chart' })
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 bg-brand-600 text-white w-14 h-14 rounded-full shadow-lg flex items-center justify-center hover:bg-brand-700 transition z-50"
      >
        <MessageCircle className="w-6 h-6" />
      </button>
    )
  }

  return (
    <div className="fixed bottom-6 right-6 w-[480px] h-[600px] bg-white rounded-2xl shadow-2xl border border-gray-200 flex flex-col z-50">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-brand-600 rounded-t-2xl">
        <div className="flex items-center gap-2 text-white">
          <MessageCircle className="w-5 h-5" />
          <span className="font-semibold">RNAscope Chat</span>
          <span className="text-xs text-white/70 ml-1">graphs + analysis</span>
        </div>
        <button onClick={() => setOpen(false)} className="text-white/80 hover:text-white">
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[95%] rounded-xl px-3 py-2 text-sm ${
              m.role === 'user' ? 'bg-brand-600 text-white' : 'bg-gray-100 text-gray-800'
            }`}>
              {/* Image preview */}
              {m.image && (
                <img src={m.image} alt="uploaded" className="max-w-full rounded-lg mb-2 max-h-40 object-contain" />
              )}
              {/* Text with basic markdown bold */}
              <div className="whitespace-pre-wrap">
                {m.text.split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
                  part.startsWith('**') && part.endsWith('**')
                    ? <strong key={j}>{part.slice(2, -2)}</strong>
                    : part
                )}
              </div>
              {/* Inline chart */}
              {m.chart && (
                <div className="mt-2 bg-white rounded-lg border border-gray-200 overflow-hidden">
                  <Plot
                    data={m.chart.data}
                    layout={{ ...m.chart.layout, autosize: true, paper_bgcolor: 'white', plot_bgcolor: 'white', font: { size: 10 } }}
                    config={{ responsive: true, displayModeBar: true, modeBarButtonsToRemove: ['lasso2d', 'select2d'], displaylogo: false, toImageButtonOptions: { format: 'png', width: 1200, height: 600, filename: 'rnascope_chart' } }}
                    style={{ width: '100%', height: m.chart.layout?.height || 300 }}
                    useResizeHandler
                  />
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-xl px-3 py-2">
              <Loader2 className="w-4 h-4 animate-spin text-gray-500" />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-3 py-3 border-t border-gray-200">
        <input type="file" ref={fileInputRef} className="hidden" accept="image/*" onChange={handleImageUpload} />
        {uploadedImage && (
          <div className="flex items-center gap-2 mb-2 px-2 py-1 bg-gray-50 rounded-lg text-xs text-gray-600">
            <Image className="w-3 h-3" />
            {uploadedImage.name}
            <button onClick={() => setUploadedImage(null)} className="ml-auto text-gray-400 hover:text-red-500"><X className="w-3 h-3" /></button>
          </div>
        )}
        <div className="flex gap-2">
          <button
            onClick={() => fileInputRef.current?.click()}
            className="px-2 py-2 rounded-lg border border-gray-300 text-gray-500 hover:bg-gray-50"
            title="Upload screenshot"
          >
            <Image className="w-4 h-4" />
          </button>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="Ask or request a graph..."
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
          />
          <button
            onClick={send}
            disabled={loading || !input.trim()}
            className="bg-brand-600 text-white px-3 py-2 rounded-lg hover:bg-brand-700 disabled:opacity-50"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
