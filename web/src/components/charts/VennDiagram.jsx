import { forwardRef } from 'react'
import Plot from '../../PlotlyChart'

const VennDiagram = forwardRef(function VennDiagram({ data }, ref) {
  if (!data) return null

  const { set_a, set_b, label_a, label_b } = data
  const setA = new Set(set_a || [])
  const setB = new Set(set_b || [])
  const common = [...setA].filter((g) => setB.has(g))
  const onlyA = [...setA].filter((g) => !setB.has(g))
  const onlyB = [...setB].filter((g) => !setA.has(g))

  return (
    <Plot
      ref={ref}
      data={[
        // Invisible traces just for legend
        { x: [null], y: [null], type: 'scatter', mode: 'markers', marker: { size: 20, color: 'rgba(239,68,68,0.4)' }, name: label_a || 'Condition A', showlegend: true },
        { x: [null], y: [null], type: 'scatter', mode: 'markers', marker: { size: 20, color: 'rgba(59,130,246,0.4)' }, name: label_b || 'Condition B', showlegend: true },
      ]}
      layout={{
        title: { text: 'Venn Diagram — Up-regulated DEGs', font: { size: 16 } },
        xaxis: { visible: false, range: [-3, 3] },
        yaxis: { visible: false, range: [-2.5, 2.5], scaleanchor: 'x' },
        margin: { t: 50, b: 20, l: 20, r: 20 },
        paper_bgcolor: 'white',
        plot_bgcolor: 'white',
        width: 600,
        height: 450,
        shapes: [
          { type: 'circle', x0: -1.5, y0: -1.2, x1: 1, y1: 1.2, fillcolor: 'rgba(239,68,68,0.25)', line: { color: '#ef4444', width: 2 } },
          { type: 'circle', x0: -0.5, y0: -1.2, x1: 2, y1: 1.2, fillcolor: 'rgba(59,130,246,0.25)', line: { color: '#3b82f6', width: 2 } },
        ],
        annotations: [
          { x: -0.9, y: 0.15, text: `<b>${onlyA.length}</b>`, showarrow: false, font: { size: 28, color: '#ef4444' } },
          { x: 0.25, y: 0.15, text: `<b>${common.length}</b>`, showarrow: false, font: { size: 28, color: '#7c3aed' } },
          { x: 1.4, y: 0.15, text: `<b>${onlyB.length}</b>`, showarrow: false, font: { size: 28, color: '#3b82f6' } },
          { x: -1.1, y: -1.5, text: label_a || 'Condition A', showarrow: false, font: { size: 13, color: '#ef4444' } },
          { x: 1.6, y: -1.5, text: label_b || 'Condition B', showarrow: false, font: { size: 13, color: '#3b82f6' } },
          { x: -0.9, y: -0.45, text: onlyA.slice(0, 5).join('<br>'), showarrow: false, font: { size: 9, color: '#666' }, align: 'center' },
          { x: 0.25, y: -0.45, text: common.slice(0, 5).join('<br>'), showarrow: false, font: { size: 9, color: '#666' }, align: 'center' },
          { x: 1.4, y: -0.45, text: onlyB.slice(0, 5).join('<br>'), showarrow: false, font: { size: 9, color: '#666' }, align: 'center' },
        ],
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: 450 }}
    />
  )
})

export default VennDiagram
