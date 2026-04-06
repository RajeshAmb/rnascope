import { forwardRef, useMemo } from 'react'
import Plot from '../../PlotlyChart'

/**
 * SampleDistancePlot
 * Converts a Pearson correlation matrix into a distance matrix (1 - r)
 * and renders it as a Plotly heatmap.
 */
const SampleDistancePlot = forwardRef(function SampleDistancePlot({ data }, ref) {
  if (!data || !data.matrix || !data.samples) return null

  const { samples, matrix } = data

  // Convert correlation to distance: d = 1 - r
  const distMatrix = useMemo(
    () => matrix.map((row) => row.map((r) => parseFloat((1 - r).toFixed(4)))),
    [matrix]
  )

  return (
    <Plot
      ref={ref}
      data={[
        {
          z: distMatrix,
          x: samples,
          y: samples,
          type: 'heatmap',
          colorscale: [
            [0, '#ffffff'],
            [0.5, '#93c5fd'],
            [1, '#1d4ed8'],
          ],
          zmin: 0,
          zmax: 0.3,
          hovertemplate: '%{x} vs %{y}<br>Distance: %{z:.4f}<extra></extra>',
          colorbar: {
            title: 'Distance<br>(1 − r)',
            thickness: 15,
            len: 0.8,
          },
        },
      ]}
      layout={{
        title: { text: 'Sample-to-Sample Distance Heatmap', font: { size: 15 } },
        xaxis: { tickangle: -45, tickfont: { size: 11 } },
        yaxis: { autorange: 'reversed', tickfont: { size: 11 } },
        margin: { t: 55, b: 90, l: 90, r: 90 },
        paper_bgcolor: 'white',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: 500 }}
    />
  )
})

export default SampleDistancePlot
