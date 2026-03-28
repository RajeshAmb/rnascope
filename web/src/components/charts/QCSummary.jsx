import { CheckCircle2, AlertTriangle } from 'lucide-react'

function StatCard({ label, value, unit, good }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
      <p className="text-sm text-gray-500 mb-1">{label}</p>
      <p className="text-2xl font-bold text-gray-900">
        {value}
        <span className="text-sm font-normal text-gray-400 ml-1">{unit}</span>
      </p>
      {good !== undefined && (
        <div className={`flex items-center gap-1 mt-1 text-xs ${good ? 'text-green-600' : 'text-yellow-600'}`}>
          {good ? <CheckCircle2 className="w-3 h-3" /> : <AlertTriangle className="w-3 h-3" />}
          {good ? 'Passed' : 'Flagged'}
        </div>
      )}
    </div>
  )
}

export default function QCSummary({ data }) {
  if (!data) return null

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4">Quality Control Summary</h3>

      {/* Aggregate stats */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
        <StatCard label="Total Samples" value={data.total_samples} unit="" />
        <StatCard label="Total Reads" value={data.total_reads_m} unit="M" />
        <StatCard label="Avg Q30" value={data.avg_q30} unit="%" good={data.avg_q30 >= 85} />
        <StatCard label="Avg Mapping" value={data.avg_mapping_rate} unit="%" good={data.avg_mapping_rate >= 70} />
        <StatCard label="Avg Duplication" value={data.avg_duplication} unit="%" good={data.avg_duplication < 60} />
        <StatCard label="Avg rRNA" value={data.avg_rrna_pct} unit="%" good={data.avg_rrna_pct < 15} />
      </div>

      {/* Per-sample table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-gray-700">Sample</th>
              <th className="text-left px-4 py-3 font-medium text-gray-700">Condition</th>
              <th className="text-right px-4 py-3 font-medium text-gray-700">Reads (M)</th>
              <th className="text-right px-4 py-3 font-medium text-gray-700">Q30 %</th>
              <th className="text-right px-4 py-3 font-medium text-gray-700">Mapping %</th>
              <th className="text-right px-4 py-3 font-medium text-gray-700">Dup %</th>
              <th className="text-right px-4 py-3 font-medium text-gray-700">rRNA %</th>
              <th className="text-center px-4 py-3 font-medium text-gray-700">Status</th>
            </tr>
          </thead>
          <tbody>
            {(data.samples || []).map((s, i) => (
              <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                <td className="px-4 py-2.5 font-mono font-medium">{s.sample}</td>
                <td className="px-4 py-2.5">{s.condition}</td>
                <td className="px-4 py-2.5 text-right">{s.total_reads_m}</td>
                <td className={`px-4 py-2.5 text-right ${s.q30_pct < 85 ? 'text-yellow-600 font-semibold' : ''}`}>
                  {s.q30_pct}
                </td>
                <td className={`px-4 py-2.5 text-right ${s.mapping_rate < 70 ? 'text-yellow-600 font-semibold' : ''}`}>
                  {s.mapping_rate}
                </td>
                <td className={`px-4 py-2.5 text-right ${s.duplication_pct > 60 ? 'text-yellow-600 font-semibold' : ''}`}>
                  {s.duplication_pct}
                </td>
                <td className="px-4 py-2.5 text-right">{s.rrna_pct}</td>
                <td className="px-4 py-2.5 text-center">
                  {s.passed ? (
                    <CheckCircle2 className="w-4 h-4 text-green-500 inline" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 text-yellow-500 inline" />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
