import { CheckCircle2, Loader2, Circle } from 'lucide-react'

const STEPS = [
  { key: 'ingestion', label: 'Ingestion & Validation' },
  { key: 'qc', label: 'Quality Control' },
  { key: 'rrna_depletion', label: 'rRNA Depletion' },
  { key: 'alignment', label: 'STAR Alignment' },
  { key: 'quantification', label: 'Gene Quantification' },
  { key: 'transcript_quant', label: 'Transcript Quantification (Salmon)' },
  { key: 'deg', label: 'Differential Expression' },
  { key: 'annotation', label: 'Gene Annotation' },
  { key: 'pathway', label: 'Pathway Enrichment' },
  { key: 'biotype', label: 'Biotype Analysis' },
  { key: 'wgcna', label: 'WGCNA Co-expression Network' },
  { key: 'deconvolution', label: 'Cell Type Deconvolution' },
  { key: 'interpretation', label: 'AI Interpretation' },
  { key: 'report', label: 'Report Generation' },
]

export default function ProgressTracker({ currentStep, stepsCompleted, pctComplete }) {
  const completedSet = new Set(stepsCompleted || [])

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-gray-900">Pipeline Progress</h3>
        <span className="text-sm font-medium text-brand-600">{Math.round(pctComplete || 0)}%</span>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-200 rounded-full h-2.5 mb-6">
        <div
          className="bg-brand-600 h-2.5 rounded-full transition-all duration-500"
          style={{ width: `${pctComplete || 0}%` }}
        />
      </div>

      {/* Steps */}
      <div className="space-y-2">
        {STEPS.map((step) => {
          const done = completedSet.has(step.key)
          const active = currentStep === step.key
          return (
            <div key={step.key} className="flex items-center gap-3">
              {done ? (
                <CheckCircle2 className="w-5 h-5 text-green-500 flex-shrink-0" />
              ) : active ? (
                <Loader2 className="w-5 h-5 text-brand-600 animate-spin flex-shrink-0" />
              ) : (
                <Circle className="w-5 h-5 text-gray-300 flex-shrink-0" />
              )}
              <span
                className={`text-sm ${
                  done ? 'text-green-700 font-medium' : active ? 'text-brand-700 font-semibold' : 'text-gray-400'
                }`}
              >
                {step.label}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
