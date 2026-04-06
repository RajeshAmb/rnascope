import { forwardRef } from 'react'
import Plot from '../../PlotlyChart'

/**
 * PlantEnrichment
 * Three horizontal bar chart sections:
 *   1. PlantCyc pathways
 *   2. MapMan functional bins
 *   3. PlantTFDB TF families
 */
const HBarChart = forwardRef(function HBarChart({ title, items, colorUp, colorDown, ref: _ref }, ref) {
  if (!items || items.length === 0) return null

  const sorted = [...items].sort((a, b) => a.neg_log10_pvalue - b.neg_log10_pvalue)

  const upItems = sorted.filter((d) => d.direction !== 'down')
  const downItems = sorted.filter((d) => d.direction === 'down')

  const traces = []
  if (upItems.length > 0) {
    traces.push({
      y: upItems.map((d) => d.name),
      x: upItems.map((d) => d.neg_log10_pvalue),
      text: upItems.map((d) => `${d.count} genes`),
      type: 'bar',
      orientation: 'h',
      name: 'Enriched',
      marker: { color: colorUp || '#22c55e', opacity: 0.85 },
      hovertemplate: '<b>%{y}</b><br>-log10(p): %{x:.2f}<br>%{text}<extra></extra>',
    })
  }
  if (downItems.length > 0) {
    traces.push({
      y: downItems.map((d) => d.name),
      x: downItems.map((d) => d.neg_log10_pvalue),
      text: downItems.map((d) => `${d.count} genes`),
      type: 'bar',
      orientation: 'h',
      name: 'Depleted',
      marker: { color: colorDown || '#f59e0b', opacity: 0.85 },
      hovertemplate: '<b>%{y}</b><br>-log10(p): %{x:.2f}<br>%{text}<extra></extra>',
    })
  }

  return (
    <Plot
      ref={ref}
      data={traces}
      layout={{
        title: { text: title, font: { size: 15 } },
        xaxis: { title: '-log10(p-value)' },
        yaxis: { autorange: 'reversed', tickfont: { size: 11 } },
        barmode: 'group',
        legend: { x: 0.7, y: 0.05 },
        margin: { t: 50, b: 60, l: 240, r: 30 },
        plot_bgcolor: '#fafafa',
        paper_bgcolor: 'white',
      }}
      config={{ responsive: true, displaylogo: false }}
      style={{ width: '100%', height: Math.max(300, items.length * 32 + 110) }}
    />
  )
})

const PlantEnrichment = forwardRef(function PlantEnrichment({ data }, ref) {
  if (!data) return null

  const { plantcyc, mapman, plantTFDB } = data

  return (
    <div className="space-y-8">
      {/* PlantCyc pathways */}
      {plantcyc && plantcyc.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2.5 h-2.5 rounded-full bg-green-500 inline-block" />
            <h4 className="font-semibold text-gray-800">PlantCyc Pathways</h4>
          </div>
          <HBarChart
            ref={ref}
            title="PlantCyc Pathway Enrichment"
            items={plantcyc}
            colorUp="#22c55e"
            colorDown="#10b981"
          />
        </div>
      )}

      {/* MapMan functional bins */}
      {mapman && mapman.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" />
            <h4 className="font-semibold text-gray-800">MapMan Functional Bins</h4>
          </div>
          <HBarChart
            title="MapMan Bin Enrichment"
            items={mapman}
            colorUp="#f59e0b"
            colorDown="#d97706"
          />
        </div>
      )}

      {/* PlantTFDB TF families */}
      {plantTFDB && plantTFDB.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2.5 h-2.5 rounded-full bg-purple-500 inline-block" />
            <h4 className="font-semibold text-gray-800">PlantTFDB — TF Family Enrichment</h4>
          </div>
          <HBarChart
            title="PlantTFDB TF Family Enrichment"
            items={plantTFDB}
            colorUp="#8b5cf6"
            colorDown="#6d28d9"
          />
        </div>
      )}
    </div>
  )
})

export default PlantEnrichment
