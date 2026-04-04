import { forwardRef } from 'react'
import Plot from '../../PlotlyChart'

// Per-base quality score plot
export const BaseQualityPlot = forwardRef(function BaseQualityPlot({ data }, ref) {
  if (!data) return null
  const { positions, mean_quality, q1, q3, lower_whisker, upper_whisker } = data

  return (
    <Plot
      ref={ref}
      data={[
        {
          x: positions,
          y: mean_quality,
          type: 'scatter',
          mode: 'lines+markers',
          name: 'Mean Quality',
          line: { color: '#3b82f6', width: 2 },
          marker: { size: 4 },
        },
        {
          x: positions,
          y: upper_whisker,
          type: 'scatter',
          mode: 'lines',
          name: 'Upper (90th)',
          line: { color: '#86efac', width: 1, dash: 'dot' },
          showlegend: true,
        },
        {
          x: positions,
          y: q3,
          type: 'scatter',
          mode: 'lines',
          name: 'Q3 (75th)',
          line: { width: 0 },
          showlegend: false,
        },
        {
          x: positions,
          y: q1,
          type: 'scatter',
          mode: 'lines',
          name: 'IQR',
          fill: 'tonexty',
          fillcolor: 'rgba(59,130,246,0.15)',
          line: { width: 0 },
          showlegend: true,
        },
        {
          x: positions,
          y: lower_whisker,
          type: 'scatter',
          mode: 'lines',
          name: 'Lower (10th)',
          line: { color: '#fca5a5', width: 1, dash: 'dot' },
          showlegend: true,
        },
      ]}
      layout={{
        title: { text: 'Per Base Sequence Quality', font: { size: 15 } },
        xaxis: { title: 'Position in read (bp)' },
        yaxis: { title: 'Phred Quality Score', range: [0, 42] },
        shapes: [
          { type: 'rect', x0: 0, x1: positions[positions.length - 1], y0: 28, y1: 42, fillcolor: 'rgba(34,197,94,0.08)', line: { width: 0 } },
          { type: 'rect', x0: 0, x1: positions[positions.length - 1], y0: 20, y1: 28, fillcolor: 'rgba(234,179,8,0.08)', line: { width: 0 } },
          { type: 'rect', x0: 0, x1: positions[positions.length - 1], y0: 0, y1: 20, fillcolor: 'rgba(239,68,68,0.08)', line: { width: 0 } },
        ],
        margin: { t: 50, b: 60, l: 60, r: 30 },
        paper_bgcolor: 'white',
        legend: { x: 0.7, y: 0.15 },
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: 400 }}
    />
  )
})

// GC Content Distribution
export const GCContentPlot = forwardRef(function GCContentPlot({ data }, ref) {
  if (!data) return null
  const { gc_pct, count, theoretical } = data

  return (
    <Plot
      ref={ref}
      data={[
        {
          x: gc_pct,
          y: count,
          type: 'scatter',
          mode: 'lines',
          name: 'Observed',
          line: { color: '#ef4444', width: 2 },
        },
        {
          x: gc_pct,
          y: theoretical,
          type: 'scatter',
          mode: 'lines',
          name: 'Theoretical',
          line: { color: '#3b82f6', width: 2, dash: 'dash' },
        },
      ]}
      layout={{
        title: { text: 'GC Content Distribution', font: { size: 15 } },
        xaxis: { title: 'GC Content (%)' },
        yaxis: { title: 'Read Count' },
        margin: { t: 50, b: 60, l: 60, r: 30 },
        paper_bgcolor: 'white',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: 400 }}
    />
  )
})

// Adapter Content Plot
export const AdapterContentPlot = forwardRef(function AdapterContentPlot({ data }, ref) {
  if (!data) return null
  const { positions, illumina_universal, illumina_small_rna, nextera } = data

  return (
    <Plot
      ref={ref}
      data={[
        { x: positions, y: illumina_universal, type: 'scatter', mode: 'lines', name: 'Illumina Universal', line: { color: '#ef4444', width: 2 } },
        { x: positions, y: illumina_small_rna, type: 'scatter', mode: 'lines', name: 'Illumina Small RNA', line: { color: '#3b82f6', width: 2 } },
        { x: positions, y: nextera, type: 'scatter', mode: 'lines', name: 'Nextera', line: { color: '#22c55e', width: 2 } },
      ]}
      layout={{
        title: { text: 'Adapter Content', font: { size: 15 } },
        xaxis: { title: 'Position in read (bp)' },
        yaxis: { title: 'Adapter Content (%)', range: [0, 10] },
        margin: { t: 50, b: 60, l: 60, r: 30 },
        paper_bgcolor: 'white',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: 400 }}
    />
  )
})
