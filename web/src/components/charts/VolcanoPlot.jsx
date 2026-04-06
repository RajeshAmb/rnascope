import { forwardRef } from 'react'
import Plot from '../../PlotlyChart'

const VolcanoPlot = forwardRef(function VolcanoPlot({ data, fdrThreshold = 0.05, lfcThreshold = 1.0 }, ref) {
  if (!data || data.length === 0) return null

  // Apply thresholds to determine point classification
  const classify = (d) => {
    const sig = d.fdr <= fdrThreshold && Math.abs(d.log2fc) >= lfcThreshold
    if (!sig) return 'ns'
    return d.log2fc > 0 ? 'up' : 'down'
  }

  const up = data.filter((d) => classify(d) === 'up')
  const down = data.filter((d) => classify(d) === 'down')
  const ns = data.filter((d) => classify(d) === 'ns')

  const topGenes = [...data]
    .filter((d) => d.significant)
    .sort((a, b) => b.neg_log10_pvalue - a.neg_log10_pvalue)
    .slice(0, 15)

  const makeTrace = (subset, name, color) => ({
    x: subset.map((d) => d.log2fc),
    y: subset.map((d) => d.neg_log10_pvalue),
    text: subset.map((d) => d.gene),
    mode: 'markers',
    type: 'scatter',
    name,
    marker: { color, size: 7, opacity: 0.75 },
    hovertemplate: '<b>%{text}</b><br>log2FC: %{x:.2f}<br>-log10(p): %{y:.2f}<extra></extra>',
  })

  const annotations = topGenes.map((g) => ({
    x: g.log2fc,
    y: g.neg_log10_pvalue,
    text: g.gene,
    showarrow: true,
    arrowhead: 0,
    arrowsize: 0.5,
    ax: Math.random() > 0.5 ? 30 : -30,
    ay: -20,
    font: { size: 10, color: '#1e3a5f' },
  }))

  return (
    <Plot
      ref={ref}
      data={[
        makeTrace(up, 'Upregulated', '#ef4444'),
        makeTrace(down, 'Downregulated', '#3b82f6'),
        makeTrace(ns, 'Not significant', '#d1d5db'),
      ]}
      layout={{
        title: { text: 'Volcano Plot', font: { size: 16 } },
        xaxis: { title: 'log2 Fold Change', zeroline: true, zerolinecolor: '#e5e7eb' },
        yaxis: { title: '-log10(p-value)' },
        shapes: [
          { type: 'line', x0: -lfcThreshold, x1: -lfcThreshold, y0: 0, y1: 1, yref: 'paper', line: { dash: 'dot', color: '#9ca3af' } },
          { type: 'line', x0: lfcThreshold, x1: lfcThreshold, y0: 0, y1: 1, yref: 'paper', line: { dash: 'dot', color: '#9ca3af' } },
          { type: 'line', x0: 0, x1: 1, xref: 'paper', y0: -Math.log10(fdrThreshold), y1: -Math.log10(fdrThreshold), line: { dash: 'dot', color: '#9ca3af' } },
        ],
        annotations,
        legend: { x: 0.02, y: 0.98 },
        margin: { t: 50, b: 60, l: 60, r: 30 },
        plot_bgcolor: '#fafafa',
        paper_bgcolor: 'white',
        hovermode: 'closest',
      }}
      config={{ responsive: true, displayModeBar: true, displaylogo: false }}
      style={{ width: '100%', height: 500 }}
    />
  )
})

export default VolcanoPlot
