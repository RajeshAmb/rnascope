import { forwardRef } from 'react'
import Plot from '../../PlotlyChart'

// Expression Distribution Boxplots (FPKM/TPM)
export const ExpressionBoxplot = forwardRef(function ExpressionBoxplot({ data }, ref) {
  if (!data) return null
  const colors = ['#3b82f6', '#ef4444', '#22c55e', '#f59e0b', '#8b5cf6', '#ec4899']

  return (
    <Plot
      ref={ref}
      data={data.samples.map((s, i) => ({
        y: s.values,
        type: 'box',
        name: s.name,
        marker: { color: colors[i % colors.length] },
        boxpoints: 'outliers',
      }))}
      layout={{
        title: { text: 'Gene Expression Distribution (log2 TPM)', font: { size: 15 } },
        xaxis: { title: 'Sample' },
        yaxis: { title: 'log2(TPM + 1)' },
        margin: { t: 50, b: 80, l: 60, r: 30 },
        paper_bgcolor: 'white',
        showlegend: false,
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: 400 }}
    />
  )
})

// Expression Density Plot
export const ExpressionDensity = forwardRef(function ExpressionDensity({ data }, ref) {
  if (!data) return null
  const colors = ['#3b82f6', '#ef4444', '#22c55e', '#f59e0b', '#8b5cf6', '#ec4899']

  return (
    <Plot
      ref={ref}
      data={data.samples.map((s, i) => ({
        x: s.values,
        type: 'violin',
        name: s.name,
        side: 'positive',
        line: { color: colors[i % colors.length] },
        meanline: { visible: true },
        scalemode: 'width',
        width: 1.5,
      }))}
      layout={{
        title: { text: 'Expression Density per Sample', font: { size: 15 } },
        xaxis: { title: 'log2(TPM + 1)' },
        yaxis: { title: '' },
        margin: { t: 50, b: 60, l: 60, r: 30 },
        paper_bgcolor: 'white',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: 400 }}
    />
  )
})

// Correlation Heatmap
export const CorrelationHeatmap = forwardRef(function CorrelationHeatmap({ data }, ref) {
  if (!data) return null

  return (
    <Plot
      ref={ref}
      data={[
        {
          z: data.matrix,
          x: data.samples,
          y: data.samples,
          type: 'heatmap',
          colorscale: [
            [0, '#3b82f6'],
            [0.5, '#fefce8'],
            [1, '#ef4444'],
          ],
          zmin: data.min || 0.7,
          zmax: 1.0,
          hovertemplate: '%{x} vs %{y}<br>r = %{z:.3f}<extra></extra>',
          colorbar: { title: 'Pearson r', thickness: 15, len: 0.8 },
        },
      ]}
      layout={{
        title: { text: 'Sample Correlation Heatmap', font: { size: 15 } },
        xaxis: { tickangle: -45 },
        yaxis: { autorange: 'reversed' },
        margin: { t: 50, b: 80, l: 80, r: 80 },
        paper_bgcolor: 'white',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: 500 }}
    />
  )
})
