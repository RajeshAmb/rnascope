import { forwardRef } from 'react'
import Plot from 'react-plotly.js'

const TranscriptPlot = forwardRef(function TranscriptPlot({ data }, ref) {
  if (!data) return null

  const { top_isoforms, isoform_switch } = data

  // Top isoforms bar chart
  const barTrace = {
    y: top_isoforms.map((d) => d.gene_symbol),
    x: top_isoforms.map((d) => d.tpm),
    text: top_isoforms.map((d) => `${d.transcript_id} (${d.tpm.toFixed(1)} TPM)`),
    type: 'bar',
    orientation: 'h',
    marker: {
      color: top_isoforms.map((d) => d.is_primary ? '#3b82f6' : '#93c5fd'),
      opacity: 0.85,
    },
    hovertemplate: '<b>%{y}</b><br>%{text}<extra></extra>',
  }

  return (
    <div>
      <Plot
        ref={ref}
        data={[barTrace]}
        layout={{
          title: { text: 'Top Expressed Transcripts (TPM)', font: { size: 16 } },
          xaxis: { title: 'TPM (Transcripts Per Million)' },
          yaxis: { autorange: 'reversed', tickfont: { size: 11 } },
          margin: { t: 50, b: 60, l: 160, r: 30 },
          plot_bgcolor: '#fafafa',
          paper_bgcolor: 'white',
        }}
        config={{ responsive: true, displaylogo: false }}
        style={{ width: '100%', height: Math.max(350, top_isoforms.length * 28 + 100) }}
      />

      {/* Isoform switch table */}
      {isoform_switch && isoform_switch.length > 0 && (
        <div className="mt-6">
          <h4 className="font-semibold text-gray-900 mb-3">Differential Transcript Usage</h4>
          <p className="text-sm text-gray-500 mb-3">
            Genes where the dominant isoform switches between conditions — potential functional consequences.
          </p>
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-4 py-2 font-medium text-gray-600">Gene</th>
                  <th className="text-left px-4 py-2 font-medium text-gray-600">Condition A Isoform</th>
                  <th className="text-left px-4 py-2 font-medium text-gray-600">Condition B Isoform</th>
                  <th className="text-right px-4 py-2 font-medium text-gray-600">dIF</th>
                  <th className="text-right px-4 py-2 font-medium text-gray-600">FDR</th>
                </tr>
              </thead>
              <tbody>
                {isoform_switch.map((s, i) => (
                  <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-2 font-mono font-semibold">{s.gene}</td>
                    <td className="px-4 py-2 text-xs font-mono text-blue-600">{s.isoform_a}</td>
                    <td className="px-4 py-2 text-xs font-mono text-red-600">{s.isoform_b}</td>
                    <td className="px-4 py-2 text-right font-mono">{s.dIF.toFixed(3)}</td>
                    <td className="px-4 py-2 text-right font-mono text-gray-500">{s.fdr.toExponential(2)}</td>
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

export default TranscriptPlot
