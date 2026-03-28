import { forwardRef } from 'react'
import Plot from '../../PlotlyChart'

const KEGGBar = forwardRef(function KEGGBar({ data }, ref) {
  if (!data || data.length === 0) return null

  const sorted = [...data].sort((a, b) => a.neg_log10_pvalue - b.neg_log10_pvalue)
  const upData = sorted.filter((d) => d.direction === 'up')
  const downData = sorted.filter((d) => d.direction === 'down')

  const traces = []

  if (upData.length > 0) {
    traces.push({
      y: upData.map((d) => d.pathway),
      x: upData.map((d) => d.neg_log10_pvalue),
      text: upData.map((d) => `${d.count} genes`),
      type: 'bar',
      orientation: 'h',
      name: 'Upregulated',
      marker: { color: '#ef4444', opacity: 0.85 },
      hovertemplate: '<b>%{y}</b><br>-log10(p): %{x:.2f}<br>%{text}<extra></extra>',
    })
  }

  if (downData.length > 0) {
    traces.push({
      y: downData.map((d) => d.pathway),
      x: downData.map((d) => d.neg_log10_pvalue),
      text: downData.map((d) => `${d.count} genes`),
      type: 'bar',
      orientation: 'h',
      name: 'Downregulated',
      marker: { color: '#3b82f6', opacity: 0.85 },
      hovertemplate: '<b>%{y}</b><br>-log10(p): %{x:.2f}<br>%{text}<extra></extra>',
    })
  }

  return (
    <Plot
      ref={ref}
      data={traces}
      layout={{
        title: { text: 'KEGG Pathway Enrichment', font: { size: 16 } },
        xaxis: { title: '-log10(p-value)' },
        yaxis: { autorange: 'reversed', tickfont: { size: 11 } },
        barmode: 'group',
        legend: { x: 0.7, y: 0.05 },
        margin: { t: 50, b: 60, l: 280, r: 30 },
        plot_bgcolor: '#fafafa',
        paper_bgcolor: 'white',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: Math.max(350, data.length * 35 + 100) }}
    />
  )
})

export default KEGGBar
