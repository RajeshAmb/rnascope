import { forwardRef } from 'react'
import Plot from '../../PlotlyChart'

// MA Plot
export const MAPlot = forwardRef(function MAPlot({ data }, ref) {
  if (!data || data.length === 0) return null

  const sig = data.filter((d) => d.significant)
  const ns = data.filter((d) => !d.significant)

  return (
    <Plot
      ref={ref}
      data={[
        {
          x: ns.map((d) => d.mean_expression),
          y: ns.map((d) => d.log2fc),
          text: ns.map((d) => d.gene),
          type: 'scatter',
          mode: 'markers',
          name: 'Not significant',
          marker: { color: '#d1d5db', size: 5, opacity: 0.6 },
          hovertemplate: '<b>%{text}</b><br>Mean expr: %{x:.1f}<br>log2FC: %{y:.2f}<extra></extra>',
        },
        {
          x: sig.map((d) => d.mean_expression),
          y: sig.map((d) => d.log2fc),
          text: sig.map((d) => d.gene),
          type: 'scatter',
          mode: 'markers',
          name: 'Significant',
          marker: { color: '#ef4444', size: 6, opacity: 0.7 },
          hovertemplate: '<b>%{text}</b><br>Mean expr: %{x:.1f}<br>log2FC: %{y:.2f}<extra></extra>',
        },
      ]}
      layout={{
        title: { text: 'MA Plot', font: { size: 15 } },
        xaxis: { title: 'Mean Expression (log2)', type: 'log' },
        yaxis: { title: 'log2 Fold Change' },
        shapes: [{ type: 'line', x0: 0, x1: 1, y0: 0, y1: 0, xref: 'paper', line: { color: '#3b82f6', dash: 'dash' } }],
        margin: { t: 50, b: 60, l: 60, r: 30 },
        paper_bgcolor: 'white',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: 450 }}
    />
  )
})

// Dispersion Plot
export const DispersionPlot = forwardRef(function DispersionPlot({ data }, ref) {
  if (!data) return null

  return (
    <Plot
      ref={ref}
      data={[
        {
          x: data.mean_counts,
          y: data.gene_est,
          type: 'scatter',
          mode: 'markers',
          name: 'Gene-est',
          marker: { color: '#000', size: 3, opacity: 0.3 },
        },
        {
          x: data.mean_counts,
          y: data.fitted,
          type: 'scatter',
          mode: 'lines',
          name: 'Fitted',
          line: { color: '#ef4444', width: 2 },
        },
        {
          x: data.mean_counts,
          y: data.final_est,
          type: 'scatter',
          mode: 'markers',
          name: 'Final',
          marker: { color: '#3b82f6', size: 3, opacity: 0.4 },
        },
      ]}
      layout={{
        title: { text: 'DESeq2 Dispersion Estimates', font: { size: 15 } },
        xaxis: { title: 'Mean of Normalized Counts', type: 'log' },
        yaxis: { title: 'Dispersion', type: 'log' },
        margin: { t: 50, b: 60, l: 60, r: 30 },
        paper_bgcolor: 'white',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: 450 }}
    />
  )
})

// Time-series line plot
export const TimeSeriesPlot = forwardRef(function TimeSeriesPlot({ data }, ref) {
  if (!data || !data.genes) return null
  const colors = ['#ef4444', '#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316']

  return (
    <Plot
      ref={ref}
      data={data.genes.map((g, i) => ({
        x: data.time_points,
        y: g.values,
        type: 'scatter',
        mode: 'lines+markers',
        name: g.gene,
        line: { color: colors[i % colors.length], width: 2 },
        marker: { size: 6 },
        error_y: g.se ? { type: 'data', array: g.se, visible: true, thickness: 1 } : undefined,
      }))}
      layout={{
        title: { text: data.title || 'Gene Expression Over Time', font: { size: 15 } },
        xaxis: { title: data.x_label || 'Time Point (DPI)', tickvals: data.time_points },
        yaxis: { title: 'Expression (log2 TPM)' },
        margin: { t: 50, b: 60, l: 60, r: 30 },
        paper_bgcolor: 'white',
        legend: { x: 1.02, y: 1, xanchor: 'left' },
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: 450 }}
    />
  )
})
