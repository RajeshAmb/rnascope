import { forwardRef } from 'react'
import Plot from 'react-plotly.js'

const HeatmapPlot = forwardRef(function HeatmapPlot({ data }, ref) {
  if (!data || !data.matrix) return null

  return (
    <Plot
      ref={ref}
      data={[
        {
          z: data.matrix,
          x: data.samples,
          y: data.genes,
          type: 'heatmap',
          colorscale: [
            [0, '#3b82f6'],
            [0.5, '#fafafa'],
            [1, '#ef4444'],
          ],
          zmin: -3,
          zmax: 3,
          hovertemplate: '<b>%{y}</b> in %{x}<br>z-score: %{z:.2f}<extra></extra>',
          colorbar: { title: 'z-score', titleside: 'right', thickness: 15, len: 0.8 },
        },
      ]}
      layout={{
        title: { text: 'Top DE Genes — Expression Heatmap', font: { size: 16 } },
        xaxis: { title: '', tickangle: -45, side: 'bottom' },
        yaxis: { title: '', autorange: 'reversed', tickfont: { size: 10 } },
        margin: { t: 50, b: 80, l: 120, r: 80 },
        paper_bgcolor: 'white',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: Math.max(500, data.genes.length * 18 + 150) }}
    />
  )
})

export default HeatmapPlot
