import { forwardRef } from 'react'
import Plot from '../../PlotlyChart'

const SOURCE_COLORS = { GO_BP: '#3b82f6', GO_MF: '#f59e0b', GO_CC: '#10b981' }

const GOBubble = forwardRef(function GOBubble({ data }, ref) {
  if (!data || data.length === 0) return null

  const sources = [...new Set(data.map((d) => d.source))]

  const traces = sources.map((src) => {
    const subset = data.filter((d) => d.source === src)
    return {
      x: subset.map((d) => d.gene_ratio),
      y: subset.map((d) => d.term),
      text: subset.map((d) => `${d.count} genes`),
      mode: 'markers',
      type: 'scatter',
      name: src.replace('_', ' '),
      marker: {
        color: SOURCE_COLORS[src] || '#6b7280',
        size: subset.map((d) => Math.max(d.count * 1.8, 10)),
        opacity: 0.75,
        line: { width: 1, color: 'white' },
      },
      hovertemplate: '<b>%{y}</b><br>Gene ratio: %{x:.2f}<br>%{text}<extra></extra>',
    }
  })

  return (
    <Plot
      ref={ref}
      data={traces}
      layout={{
        title: { text: 'GO Enrichment — Bubble Chart', font: { size: 16 } },
        xaxis: { title: 'Gene Ratio' },
        yaxis: { autorange: 'reversed', tickfont: { size: 11 } },
        legend: { x: 1.02, y: 1 },
        margin: { t: 50, b: 60, l: 260, r: 120 },
        plot_bgcolor: '#fafafa',
        paper_bgcolor: 'white',
        hovermode: 'closest',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: Math.max(400, data.length * 35 + 100) }}
    />
  )
})

export default GOBubble
