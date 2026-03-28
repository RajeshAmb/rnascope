import { forwardRef } from 'react'
import Plot from 'react-plotly.js'

const CELL_COLORS = [
  '#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6',
  '#ec4899', '#06b6d4', '#f97316', '#6366f1', '#84cc16',
  '#14b8a6', '#e11d48', '#a855f7', '#0ea5e9', '#d946ef',
]

const DeconvolutionPlot = forwardRef(function DeconvolutionPlot({ data }, ref) {
  if (!data) return null

  const { fractions, cell_types, samples, conditions, comparison } = data

  // Stacked bar chart: samples on x-axis, cell fractions stacked
  const traces = cell_types.map((ct, i) => ({
    x: samples,
    y: fractions.map((row) => row[ct] || 0),
    name: ct,
    type: 'bar',
    marker: { color: CELL_COLORS[i % CELL_COLORS.length] },
    hovertemplate: `<b>${ct}</b><br>%{x}: %{y:.1%}<extra></extra>`,
  }))

  // Condition comparison: grouped box plot
  const boxTraces = cell_types.slice(0, 8).map((ct, i) => {
    const condA = comparison.filter((d) => d.cell_type === ct && d.condition === 'A')
    const condB = comparison.filter((d) => d.cell_type === ct && d.condition === 'B')
    return [
      {
        y: condA.map((d) => d.fraction),
        name: ct,
        type: 'box',
        marker: { color: CELL_COLORS[i % CELL_COLORS.length] },
        boxpoints: 'all',
        jitter: 0.3,
        pointpos: -1.5,
        legendgroup: ct,
        xaxis: 'x2',
        yaxis: 'y2',
        showlegend: false,
        hovertemplate: `<b>${ct}</b> (Cond A)<br>%{y:.1%}<extra></extra>`,
      },
      {
        y: condB.map((d) => d.fraction),
        name: ct,
        type: 'box',
        marker: { color: CELL_COLORS[i % CELL_COLORS.length], opacity: 0.5 },
        boxpoints: 'all',
        jitter: 0.3,
        pointpos: -1.5,
        legendgroup: ct,
        xaxis: 'x2',
        yaxis: 'y2',
        showlegend: false,
        hovertemplate: `<b>${ct}</b> (Cond B)<br>%{y:.1%}<extra></extra>`,
      },
    ]
  }).flat()

  return (
    <div>
      {/* Stacked bar: cell composition per sample */}
      <Plot
        ref={ref}
        data={traces}
        layout={{
          title: { text: 'Cell Type Composition per Sample', font: { size: 16 } },
          xaxis: { title: '', tickangle: -45 },
          yaxis: { title: 'Cell fraction', tickformat: '.0%', range: [0, 1] },
          barmode: 'stack',
          legend: { x: 1.02, y: 1, font: { size: 10 } },
          margin: { t: 50, b: 80, l: 60, r: 150 },
          plot_bgcolor: '#fafafa',
          paper_bgcolor: 'white',
        }}
        config={{ responsive: true, displaylogo: false }}
        style={{ width: '100%', height: 450 }}
      />

      {/* Condition comparison */}
      {comparison && comparison.length > 0 && (
        <div className="mt-6">
          <h4 className="font-semibold text-gray-900 mb-3">Cell Type Differences Between Conditions</h4>
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-2 font-medium text-gray-600">Cell Type</th>
                  <th className="text-right px-4 py-2 font-medium text-gray-600">Mean (A)</th>
                  <th className="text-right px-4 py-2 font-medium text-gray-600">Mean (B)</th>
                  <th className="text-right px-4 py-2 font-medium text-gray-600">Difference</th>
                  <th className="text-right px-4 py-2 font-medium text-gray-600">p-value</th>
                </tr>
              </thead>
              <tbody>
                {data.cell_type_stats.map((ct, i) => (
                  <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-2 font-medium flex items-center gap-2">
                      <div className="w-3 h-3 rounded-full" style={{ backgroundColor: CELL_COLORS[i % CELL_COLORS.length] }} />
                      {ct.cell_type}
                    </td>
                    <td className="px-4 py-2 text-right font-mono">{(ct.mean_a * 100).toFixed(1)}%</td>
                    <td className="px-4 py-2 text-right font-mono">{(ct.mean_b * 100).toFixed(1)}%</td>
                    <td className={`px-4 py-2 text-right font-mono ${ct.diff > 0 ? 'text-red-600' : 'text-blue-600'}`}>
                      {ct.diff > 0 ? '+' : ''}{(ct.diff * 100).toFixed(1)}%
                    </td>
                    <td className={`px-4 py-2 text-right font-mono ${ct.pvalue < 0.05 ? 'text-red-600 font-semibold' : 'text-gray-500'}`}>
                      {ct.pvalue.toExponential(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
})

export default DeconvolutionPlot
