import { forwardRef } from 'react'
import Plot from '../../PlotlyChart'

const TFEnrichment = forwardRef(function TFEnrichment({ data }, ref) {
  if (!data || !data.tf_families || data.tf_families.length === 0) return null

  const families = data.tf_families

  // Bubble chart: x = enrichment score, y = -log10(p-value), size = target count
  const bubbleTrace = {
    x: families.map((f) => f.enrichment_score),
    y: families.map((f) => f.neg_log10_pvalue),
    text: families.map((f) => f.family),
    mode: 'markers+text',
    type: 'scatter',
    textposition: 'top center',
    textfont: { size: 11, color: '#374151' },
    marker: {
      size: families.map((f) => Math.max(f.target_count / 3, 10)),
      color: families.map((f) => f.enrichment_score),
      colorscale: [
        [0, '#bfdbfe'],
        [0.5, '#6366f1'],
        [1, '#7c3aed'],
      ],
      showscale: true,
      colorbar: { title: 'Enrichment<br>Score', thickness: 14, len: 0.75 },
      opacity: 0.8,
      line: { width: 1, color: 'white' },
    },
    hovertemplate:
      '<b>%{text}</b><br>Enrichment score: %{x:.2f}<br>-log10(p): %{y:.2f}<br>' +
      'Target genes: %{marker.size:.0f}<extra></extra>',
    customdata: families.map((f) => f.target_count),
  }

  return (
    <div>
      {/* Bubble chart */}
      <Plot
        ref={ref}
        data={[bubbleTrace]}
        layout={{
          title: { text: 'Transcription Factor Family Enrichment', font: { size: 15 } },
          xaxis: { title: 'Enrichment Score', zeroline: true, zerolinecolor: '#e5e7eb' },
          yaxis: { title: '-log10(p-value)' },
          margin: { t: 55, b: 65, l: 65, r: 80 },
          plot_bgcolor: '#fafafa',
          paper_bgcolor: 'white',
          hovermode: 'closest',
          showlegend: false,
        }}
        config={{ responsive: true, displaylogo: false }}
        style={{ width: '100%', height: 480 }}
      />

      {/* Details table */}
      <div className="mt-6 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
          <h4 className="font-medium text-gray-700">TF Family Details</h4>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-2 font-medium text-gray-600">TF Family</th>
                <th className="text-right px-4 py-2 font-medium text-gray-600">Target Genes</th>
                <th className="text-right px-4 py-2 font-medium text-gray-600">Enrichment Score</th>
                <th className="text-right px-4 py-2 font-medium text-gray-600">p-value</th>
                <th className="text-right px-4 py-2 font-medium text-gray-600">FDR</th>
                <th className="text-left px-4 py-2 font-medium text-gray-600">Top Genes</th>
              </tr>
            </thead>
            <tbody>
              {[...families]
                .sort((a, b) => b.enrichment_score - a.enrichment_score)
                .map((f, i) => (
                  <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-2 font-semibold text-purple-700">{f.family}</td>
                    <td className="px-4 py-2 text-right font-mono">{f.target_count}</td>
                    <td className="px-4 py-2 text-right font-mono text-indigo-600">
                      {f.enrichment_score.toFixed(2)}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-gray-600">
                      {f.pvalue < 0.001 ? f.pvalue.toExponential(2) : f.pvalue.toFixed(4)}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-gray-600">
                      {f.fdr < 0.001 ? f.fdr.toExponential(2) : f.fdr.toFixed(4)}
                    </td>
                    <td className="px-4 py-2 text-gray-500 text-xs font-mono">
                      {(f.top_genes || []).join(', ')}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
})

export default TFEnrichment
