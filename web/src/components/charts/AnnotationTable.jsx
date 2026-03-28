import { Target, MapPin, BookOpen } from 'lucide-react'

export default function AnnotationTable({ volcano, annotations }) {
  if (!volcano || volcano.length === 0) return null

  const topGenes = [...volcano]
    .filter((g) => g.significant)
    .sort((a, b) => Math.abs(b.log2fc) - Math.abs(a.log2fc))
    .slice(0, 25)

  // Use annotations from API if available, otherwise display what we have
  const annotMap = {}
  if (annotations && Array.isArray(annotations)) {
    annotations.forEach((a) => { annotMap[a.gene] = a })
  }

  return (
    <div>
      <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <BookOpen className="w-5 h-5 text-purple-600" />
        Functional Annotation — Top DE Genes
      </h3>
      <p className="text-sm text-gray-500 mb-4">
        Gene biotype, GO terms, disease associations, and drug target status for top differentially expressed genes.
        Annotations are fetched dynamically based on the uploaded species.
      </p>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="text-left px-4 py-3 font-medium text-gray-700 whitespace-nowrap">Gene</th>
              <th className="text-right px-4 py-3 font-medium text-gray-700 whitespace-nowrap">log2FC</th>
              <th className="text-right px-4 py-3 font-medium text-gray-700 whitespace-nowrap">FDR</th>
              <th className="text-left px-4 py-3 font-medium text-gray-700 whitespace-nowrap">Biotype</th>
              <th className="text-left px-4 py-3 font-medium text-gray-700 whitespace-nowrap">GO Biological Process</th>
              <th className="text-left px-4 py-3 font-medium text-gray-700 whitespace-nowrap">Associations</th>
              <th className="text-left px-4 py-3 font-medium text-gray-700 whitespace-nowrap">Drug/Target</th>
            </tr>
          </thead>
          <tbody>
            {topGenes.map((g, i) => {
              const annot = annotMap[g.gene] || {}
              return (
                <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-2.5 font-mono font-semibold text-gray-900">{g.gene}</td>
                  <td className={`px-4 py-2.5 text-right font-mono ${g.log2fc > 0 ? 'text-red-600' : 'text-blue-600'}`}>
                    {g.log2fc > 0 ? '+' : ''}{g.log2fc.toFixed(2)}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-gray-500">
                    {g.fdr.toExponential(2)}
                  </td>
                  <td className="px-4 py-2.5">
                    {annot.biotype ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 text-xs font-medium">
                        {annot.biotype}
                      </span>
                    ) : (
                      <span className="text-gray-400 text-xs">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-gray-700 max-w-xs truncate" title={annot.go_bp || ''}>
                    {annot.go_bp || <span className="text-gray-400 text-xs">Pending pipeline</span>}
                  </td>
                  <td className="px-4 py-2.5 text-gray-700 max-w-xs truncate" title={annot.disease || ''}>
                    {annot.disease || <span className="text-gray-400 text-xs">—</span>}
                  </td>
                  <td className="px-4 py-2.5">
                    {annot.drug && annot.drug !== 'None' ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-50 text-green-700 text-xs font-medium">
                        <Target className="w-3 h-3" />
                        {annot.drug}
                      </span>
                    ) : (
                      <span className="text-gray-400 text-xs">—</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
