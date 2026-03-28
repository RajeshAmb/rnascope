import { forwardRef } from 'react'
import Plot from 'react-plotly.js'

const BiotypePie = forwardRef(function BiotypePie({ data }, ref) {
  if (!data || data.length === 0) return null

  return (
    <Plot
      ref={ref}
      data={[
        {
          labels: data.map((d) => d.biotype),
          values: data.map((d) => d.count),
          type: 'pie',
          hole: 0.45,
          textinfo: 'label+percent',
          textposition: 'outside',
          marker: {
            colors: ['#3b82f6', '#8b5cf6', '#f59e0b', '#10b981', '#ef4444', '#6366f1', '#94a3b8'],
          },
          hovertemplate: '<b>%{label}</b><br>%{value:,} genes (%{percent})<extra></extra>',
        },
      ]}
      layout={{
        title: { text: 'RNA Biotype Distribution', font: { size: 16 } },
        showlegend: true,
        legend: { x: 1.05, y: 0.5 },
        margin: { t: 50, b: 30, l: 30, r: 150 },
        paper_bgcolor: 'white',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: 400 }}
    />
  )
})

export default BiotypePie
