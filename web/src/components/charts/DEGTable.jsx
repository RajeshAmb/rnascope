import { ArrowUp, ArrowDown } from 'lucide-react'

export default function DEGTable({ data, volcano, fdrThreshold, lfcThreshold }) {
  if (!data) return null

  const fdr = fdrThreshold ?? data.fdr_threshold ?? 0.05
  const lfc = lfcThreshold ?? data.fc_threshold ?? 1.0

  // Get top significant genes from volcano data sorted by fold change
  const topGenes = volcano
    ? [...volcano]
        .filter((g) => g.fdr <= fdr && Math.abs(g.log2fc) >= lfc)
        .sort((a, b) => Math.abs(b.log2fc) - Math.abs(a.log2fc))
        .slice(0, 20)
    : []

  // Dynamic counts based on thresholds
  const filteredUp = volcano ? volcano.filter((g) => g.fdr <= fdr && g.log2fc >= lfc).length : data.upregulated
  const filteredDown = volcano ? volcano.filter((g) => g.fdr <= fdr && g.log2fc <= -lfc).length : data.downregulated
  const filteredSig = filteredUp + filteredDown

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">Differential Expression Summary</h3>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <p className="text-sm text-gray-500">Genes Tested</p>
          <p className="text-2xl font-bold">{data.total_tested?.toLocaleString()}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <p className="text-sm text-gray-500">Significant DEGs</p>
          <p className="text-2xl font-bold text-purple-600">{filteredSig}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <p className="text-sm text-gray-500 flex items-center gap-1">
            <ArrowUp className="w-3 h-3 text-red-500" /> Upregulated
          </p>
          <p className="text-2xl font-bold text-red-600">{filteredUp}</p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
          <p className="text-sm text-gray-500 flex items-center gap-1">
            <ArrowDown className="w-3 h-3 text-blue-500" /> Downregulated
          </p>
          <p className="text-2xl font-bold text-blue-600">{filteredDown}</p>
        </div>
      </div>

      <p className="text-xs text-gray-500 mb-4">
        Thresholds: FDR &lt; {fdr} | |log2FC| &gt; {lfc}
      </p>

      {/* Top DEGs table */}
      {topGenes.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <h4 className="font-medium text-gray-700">Top 20 Significant Genes</h4>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-2 font-medium text-gray-600">#</th>
                <th className="text-left px-4 py-2 font-medium text-gray-600">Gene</th>
                <th className="text-right px-4 py-2 font-medium text-gray-600">log2FC</th>
                <th className="text-right px-4 py-2 font-medium text-gray-600">FDR</th>
                <th className="text-center px-4 py-2 font-medium text-gray-600">Direction</th>
              </tr>
            </thead>
            <tbody>
              {topGenes.map((g, i) => (
                <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-2 text-gray-400">{i + 1}</td>
                  <td className="px-4 py-2 font-mono font-semibold">{g.gene}</td>
                  <td className={`px-4 py-2 text-right font-mono ${g.log2fc > 0 ? 'text-red-600' : 'text-blue-600'}`}>
                    {g.log2fc > 0 ? '+' : ''}{g.log2fc.toFixed(2)}
                  </td>
                  <td className="px-4 py-2 text-right font-mono text-gray-600">{g.fdr.toExponential(2)}</td>
                  <td className="px-4 py-2 text-center">
                    {g.direction === 'up' ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-50 text-red-600 text-xs font-medium">
                        <ArrowUp className="w-3 h-3" /> Up
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-600 text-xs font-medium">
                        <ArrowDown className="w-3 h-3" /> Down
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
