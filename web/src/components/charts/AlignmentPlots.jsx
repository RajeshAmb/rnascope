import { forwardRef } from 'react'
import Plot from '../../PlotlyChart'

// Mapping Rate Bar Plot
export const MappingRatePlot = forwardRef(function MappingRatePlot({ data }, ref) {
  if (!data) return null
  const { samples, mapped, unmapped } = data

  return (
    <Plot
      ref={ref}
      data={[
        { x: samples, y: mapped, type: 'bar', name: 'Mapped', marker: { color: '#3b82f6' } },
        { x: samples, y: unmapped, type: 'bar', name: 'Unmapped', marker: { color: '#d1d5db' } },
      ]}
      layout={{
        title: { text: 'Mapping Rate per Sample', font: { size: 15 } },
        barmode: 'stack',
        xaxis: { title: 'Sample', tickangle: -45 },
        yaxis: { title: 'Read Count (millions)' },
        margin: { t: 50, b: 80, l: 70, r: 30 },
        paper_bgcolor: 'white',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: 400 }}
    />
  )
})

// Read Distribution Plot (exon, intron, intergenic)
export const ReadDistributionPlot = forwardRef(function ReadDistributionPlot({ data }, ref) {
  if (!data) return null
  const { samples, exonic, intronic, intergenic } = data

  return (
    <Plot
      ref={ref}
      data={[
        { x: samples, y: exonic, type: 'bar', name: 'Exonic', marker: { color: '#3b82f6' } },
        { x: samples, y: intronic, type: 'bar', name: 'Intronic', marker: { color: '#f59e0b' } },
        { x: samples, y: intergenic, type: 'bar', name: 'Intergenic', marker: { color: '#d1d5db' } },
      ]}
      layout={{
        title: { text: 'Read Distribution Across Genomic Regions', font: { size: 15 } },
        barmode: 'stack',
        xaxis: { title: 'Sample', tickangle: -45 },
        yaxis: { title: 'Proportion (%)', range: [0, 100] },
        margin: { t: 50, b: 80, l: 70, r: 30 },
        paper_bgcolor: 'white',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: 400 }}
    />
  )
})

// Gene Body Coverage
export const GeneBodyCoveragePlot = forwardRef(function GeneBodyCoveragePlot({ data }, ref) {
  if (!data) return null
  const { percentile, samples: sampleData } = data
  const colors = ['#3b82f6', '#ef4444', '#22c55e', '#f59e0b', '#8b5cf6', '#ec4899']

  return (
    <Plot
      ref={ref}
      data={sampleData.map((s, i) => ({
        x: percentile,
        y: s.coverage,
        type: 'scatter',
        mode: 'lines',
        name: s.name,
        line: { color: colors[i % colors.length], width: 2 },
      }))}
      layout={{
        title: { text: 'Gene Body Coverage', font: { size: 15 } },
        xaxis: { title: "Gene Body Percentile (5' → 3')", range: [0, 100] },
        yaxis: { title: 'Coverage (normalized)' },
        margin: { t: 50, b: 60, l: 60, r: 30 },
        paper_bgcolor: 'white',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: 400 }}
    />
  )
})
