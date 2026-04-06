import { useState, useMemo } from 'react'
import Plot from '../../PlotlyChart'
import { Search } from 'lucide-react'

export default function GeneBrowser({ data }) {
  const [query, setQuery] = useState('')
  const [selectedGene, setSelectedGene] = useState(null)

  const genes = data?.genes || []
  const samples = data?.samples || []
  const conditions = data?.conditions || []
  const matrix = data?.matrix || []

  // Filter gene list by search query
  const filteredGenes = useMemo(() => {
    if (!query.trim()) return genes.slice(0, 50)
    const q = query.toLowerCase()
    return genes.filter((g) => g.toLowerCase().includes(q)).slice(0, 50)
  }, [query, genes])

  // Get expression values for selected gene
  const geneIndex = selectedGene ? genes.indexOf(selectedGene) : -1
  const expressionValues = geneIndex >= 0 ? matrix[geneIndex] : []

  // Condition color mapping
  const uniqueConditions = [...new Set(conditions)]
  const condColorMap = {
    [uniqueConditions[0]]: '#3b82f6',
    [uniqueConditions[1]]: '#ef4444',
  }
  const barColors = conditions.map((c) => condColorMap[c] || '#6b7280')

  const traces =
    expressionValues.length > 0
      ? [
          {
            x: samples,
            y: expressionValues,
            type: 'bar',
            marker: {
              color: barColors,
              opacity: 0.85,
              line: { color: 'white', width: 1 },
            },
            hovertemplate: '<b>%{x}</b><br>Expression: %{y:.2f}<extra></extra>',
          },
        ]
      : []

  // Legend traces (zero-size for legend only)
  const legendTraces = uniqueConditions.map((cond) => ({
    x: [null],
    y: [null],
    type: 'bar',
    name: cond,
    marker: { color: condColorMap[cond] || '#6b7280' },
    showlegend: true,
  }))

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">Gene Expression Browser</h3>

      {/* Search input */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search gene name…"
          className="w-full pl-9 pr-4 py-2.5 border border-gray-300 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
        />
      </div>

      {/* Gene suggestion list */}
      {filteredGenes.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-5">
          {filteredGenes.map((gene) => (
            <button
              key={gene}
              onClick={() => setSelectedGene(gene)}
              className={`px-3 py-1 rounded-full text-xs font-medium transition ${
                selectedGene === gene
                  ? 'bg-brand-600 text-white shadow-sm'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              {gene}
            </button>
          ))}
        </div>
      )}

      {/* Chart */}
      {selectedGene && expressionValues.length > 0 ? (
        <Plot
          data={[...legendTraces, ...traces]}
          layout={{
            title: { text: `Expression of ${selectedGene} across samples`, font: { size: 15 } },
            xaxis: { title: 'Sample', tickangle: -40, tickfont: { size: 11 } },
            yaxis: { title: 'log2 Expression (z-score)' },
            legend: { x: 0.01, y: 0.99 },
            margin: { t: 55, b: 90, l: 65, r: 30 },
            plot_bgcolor: '#fafafa',
            paper_bgcolor: 'white',
            barmode: 'group',
            showlegend: true,
          }}
          config={{ responsive: true, displaylogo: false }}
          style={{ width: '100%', height: 400 }}
        />
      ) : (
        <div className="flex items-center justify-center h-48 bg-gray-50 rounded-xl border border-dashed border-gray-300 text-gray-400 text-sm">
          {genes.length === 0
            ? 'No heatmap data available.'
            : selectedGene
            ? 'Gene not found in matrix.'
            : 'Select a gene above to view its expression across samples.'}
        </div>
      )}

      {/* Condition legend */}
      {uniqueConditions.length >= 2 && (
        <div className="flex gap-4 mt-3 text-sm text-gray-600">
          {uniqueConditions.map((cond) => (
            <span key={cond} className="flex items-center gap-1.5">
              <span
                className="inline-block w-3 h-3 rounded-sm"
                style={{ background: condColorMap[cond] || '#6b7280' }}
              />
              {cond}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
