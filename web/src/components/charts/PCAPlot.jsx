import { forwardRef } from 'react'
import Plot from 'react-plotly.js'

const COLORS = { Treatment: '#ef4444', Control: '#3b82f6' }

const PCAPlot = forwardRef(function PCAPlot({ data }, ref) {
  if (!data || data.length === 0) return null

  const conditions = [...new Set(data.map((d) => d.condition))]

  const traces = conditions.map((cond) => {
    const subset = data.filter((d) => d.condition === cond)
    return {
      x: subset.map((d) => d.pc1),
      y: subset.map((d) => d.pc2),
      text: subset.map((d) => d.sample),
      mode: 'markers+text',
      type: 'scatter',
      name: cond,
      marker: { color: COLORS[cond] || '#6b7280', size: 14, line: { width: 2, color: 'white' } },
      textposition: 'top center',
      textfont: { size: 11 },
      hovertemplate: '<b>%{text}</b><br>PC1: %{x:.1f}<br>PC2: %{y:.1f}<extra></extra>',
    }
  })

  return (
    <Plot
      ref={ref}
      data={traces}
      layout={{
        title: { text: 'PCA — Sample Clustering', font: { size: 16 } },
        xaxis: { title: 'PC1 (variance explained)', zeroline: true, zerolinecolor: '#e5e7eb' },
        yaxis: { title: 'PC2 (variance explained)', zeroline: true, zerolinecolor: '#e5e7eb' },
        legend: { x: 0.02, y: 0.98 },
        margin: { t: 50, b: 60, l: 60, r: 30 },
        plot_bgcolor: '#fafafa',
        paper_bgcolor: 'white',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: 450 }}
    />
  )
})

export default PCAPlot
