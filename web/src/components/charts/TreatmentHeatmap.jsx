import { forwardRef } from 'react'
import Plot from '../../PlotlyChart'

const TreatmentHeatmap = forwardRef(function TreatmentHeatmap({ data }, ref) {
  if (!data || !data.matrix) return null

  const { genes, treatments, matrix, annotation_categories } = data

  // Build x-axis labels with treatment grouping
  const xLabels = treatments || []

  // Color annotations as a second heatmap track if available
  const traces = [
    {
      z: matrix,
      x: xLabels,
      y: genes,
      type: 'heatmap',
      colorscale: [
        [0, '#2563eb'],
        [0.25, '#60a5fa'],
        [0.5, '#fefce8'],
        [0.75, '#f87171'],
        [1, '#dc2626'],
      ],
      hovertemplate: '<b>%{y}</b><br>Treatment: %{x}<br>Expression: %{z:.2f}<extra></extra>',
      colorbar: { title: 'log2(FPKM+1)', titleside: 'right', thickness: 15, len: 0.8 },
    },
  ]

  // Annotation category bar if provided
  if (annotation_categories && annotation_categories.length > 0) {
    const catMap = {}
    const colors = ['#ef4444', '#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6', '#ec4899', '#14b8a6']
    annotation_categories.forEach((cat, i) => {
      if (!catMap[cat]) catMap[cat] = colors[Object.keys(catMap).length % colors.length]
    })

    traces.push({
      z: [annotation_categories.map((c) => Object.keys(catMap).indexOf(c))],
      x: xLabels,
      y: ['Category'],
      type: 'heatmap',
      colorscale: Object.values(catMap).map((c, i, arr) => [i / Math.max(arr.length - 1, 1), c]),
      showscale: false,
      hovertemplate: '%{x}: <b>%{text}</b><extra></extra>',
      text: [annotation_categories],
      xaxis: 'x',
      yaxis: 'y2',
    })
  }

  return (
    <Plot
      ref={ref}
      data={traces}
      layout={{
        title: { text: 'Treatment-wise Expression Profiles of Annotated Genes', font: { size: 15 } },
        xaxis: { title: 'Treatment / Condition', tickangle: -45, side: 'bottom' },
        yaxis: { title: '', autorange: 'reversed', tickfont: { size: 9 } },
        margin: { t: 50, b: 100, l: 130, r: 80 },
        paper_bgcolor: 'white',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: Math.max(550, genes.length * 18 + 180) }}
    />
  )
})

export default TreatmentHeatmap
