import { forwardRef } from 'react'
import Plot from '../../PlotlyChart'
import { Network } from 'lucide-react'

const WGCNAPlot = forwardRef(function WGCNAPlot({ data }, ref) {
  if (!data) return null

  const { modules, network_edges } = data

  // Module-trait correlation bar chart
  const sorted = [...modules].sort((a, b) => Math.abs(b.cor_trait) - Math.abs(a.cor_trait))
  const moduleTrace = {
    y: sorted.map((m) => `${m.color} (${m.n_genes})`),
    x: sorted.map((m) => m.cor_trait),
    type: 'bar',
    orientation: 'h',
    marker: {
      color: sorted.map((m) => m.cor_trait > 0 ? '#ef4444' : '#3b82f6'),
      opacity: 0.85,
    },
    text: sorted.map((m) => `p=${m.pvalue.toExponential(2)}`),
    hovertemplate: '<b>%{y}</b><br>Correlation: %{x:.3f}<br>%{text}<extra></extra>',
  }

  // Network scatter using edge data (force-directed positions simulated)
  const nodeSet = new Set()
  const edges = (network_edges || []).slice(0, 200)
  edges.forEach((e) => { nodeSet.add(e.source); nodeSet.add(e.target) })
  const nodes = [...nodeSet]

  // Simple circular layout
  const nodePos = {}
  nodes.forEach((n, i) => {
    const angle = (2 * Math.PI * i) / nodes.length
    const r = 10
    nodePos[n] = { x: r * Math.cos(angle), y: r * Math.sin(angle) }
  })

  const edgeX = []
  const edgeY = []
  edges.forEach((e) => {
    if (nodePos[e.source] && nodePos[e.target]) {
      edgeX.push(nodePos[e.source].x, nodePos[e.target].x, null)
      edgeY.push(nodePos[e.source].y, nodePos[e.target].y, null)
    }
  })

  const MODULE_COLORS = {
    turquoise: '#40E0D0', blue: '#3b82f6', brown: '#8B4513', yellow: '#f59e0b',
    green: '#10b981', red: '#ef4444', black: '#1f2937', pink: '#ec4899',
    magenta: '#d946ef', purple: '#8b5cf6', greenyellow: '#adff2f', tan: '#d2b48c',
    salmon: '#fa8072', cyan: '#06b6d4', grey: '#6b7280',
  }

  const nodeColors = nodes.map((n) => {
    const edge = edges.find((e) => e.source === n || e.target === n)
    return MODULE_COLORS[edge?.module] || '#6b7280'
  })

  return (
    <div>
      {/* Module-trait correlation */}
      <Plot
        ref={ref}
        data={[moduleTrace]}
        layout={{
          title: { text: 'WGCNA Module–Trait Correlation', font: { size: 16 } },
          xaxis: { title: 'Correlation with condition', zeroline: true, zerolinecolor: '#d1d5db', range: [-1, 1] },
          yaxis: { autorange: 'reversed', tickfont: { size: 11 } },
          shapes: [
            { type: 'line', x0: 0, x1: 0, y0: -0.5, y1: sorted.length - 0.5, line: { color: '#9ca3af', dash: 'dot' } },
          ],
          margin: { t: 50, b: 60, l: 180, r: 30 },
          plot_bgcolor: '#fafafa',
          paper_bgcolor: 'white',
        }}
        config={{ responsive: true, displaylogo: false }}
        style={{ width: '100%', height: Math.max(350, sorted.length * 35 + 100) }}
      />

      {/* Network visualization */}
      {nodes.length > 0 && (
        <div className="mt-6">
          <Plot
            data={[
              { x: edgeX, y: edgeY, mode: 'lines', type: 'scatter', line: { width: 0.5, color: '#d1d5db' }, hoverinfo: 'skip' },
              {
                x: nodes.map((n) => nodePos[n].x),
                y: nodes.map((n) => nodePos[n].y),
                text: nodes,
                mode: 'markers',
                type: 'scatter',
                marker: { size: 8, color: nodeColors, line: { width: 1, color: 'white' } },
                hovertemplate: '<b>%{text}</b><extra></extra>',
              },
            ]}
            layout={{
              title: { text: 'Co-expression Network (Top Hub Genes)', font: { size: 16 } },
              showlegend: false,
              xaxis: { showgrid: false, zeroline: false, showticklabels: false },
              yaxis: { showgrid: false, zeroline: false, showticklabels: false },
              margin: { t: 50, b: 20, l: 20, r: 20 },
              plot_bgcolor: 'white',
              paper_bgcolor: 'white',
              hovermode: 'closest',
            }}
            config={{ responsive: true, displaylogo: false }}
            style={{ width: '100%', height: 450 }}
          />
        </div>
      )}

      {/* Hub genes table per module */}
      <div className="mt-6">
        <h4 className="font-semibold text-gray-900 mb-3 flex items-center gap-2">
          <Network className="w-5 h-5 text-purple-600" />
          Module Summary & Hub Genes
        </h4>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {sorted.filter((m) => m.pvalue < 0.1).map((m, i) => (
            <div key={i} className="bg-white rounded-lg border border-gray-200 p-4">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-4 h-4 rounded-full" style={{ backgroundColor: MODULE_COLORS[m.color] || '#6b7280' }} />
                <span className="font-semibold text-gray-900 capitalize">{m.color}</span>
                <span className="text-xs text-gray-400">({m.n_genes} genes)</span>
                <span className={`ml-auto text-xs font-mono ${m.cor_trait > 0 ? 'text-red-600' : 'text-blue-600'}`}>
                  r={m.cor_trait.toFixed(3)}
                </span>
              </div>
              {m.top_go_term && (
                <p className="text-xs text-gray-500 mb-2">GO: {m.top_go_term}</p>
              )}
              <div className="flex flex-wrap gap-1">
                {m.hub_genes.map((g, j) => (
                  <span key={j} className="text-xs font-mono bg-gray-100 px-2 py-0.5 rounded">{g}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
})

export default WGCNAPlot
