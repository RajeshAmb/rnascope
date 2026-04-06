import { useState } from 'react'
import { Target, BarChart3, Shield, FlaskConical, ChevronDown, ChevronUp } from 'lucide-react'

function MetricCard({ label, value, suffix = '', color = 'text-gray-900' }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
      <p className="text-sm text-gray-500">{label}</p>
      <p className={`text-2xl font-bold ${color}`}>
        {value}<span className="text-sm font-normal text-gray-400 ml-1">{suffix}</span>
      </p>
    </div>
  )
}

function BarH({ value, maxValue, color = 'bg-brand-600', label }) {
  const pct = Math.min(100, (value / maxValue) * 100)
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-mono text-gray-700 w-24 truncate text-right" title={label}>{label}</span>
      <div className="flex-1 bg-gray-100 rounded-full h-4 relative">
        <div className={`${color} h-4 rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono text-gray-500 w-12 text-right">{value.toFixed(3)}</span>
    </div>
  )
}

function ModelPerformanceTable({ models }) {
  if (!models) return null
  const metrics = ['accuracy', 'auc', 'precision', 'recall', 'f1']
  const names = { random_forest: 'Random Forest', svm: 'SVM (RBF)', lasso: 'LASSO Regression' }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 border-b border-gray-200">
          <tr>
            <th className="text-left px-4 py-3 font-medium text-gray-700">Model</th>
            {metrics.map(m => (
              <th key={m} className="text-right px-4 py-3 font-medium text-gray-700 uppercase text-xs">{m}</th>
            ))}
            <th className="text-right px-4 py-3 font-medium text-gray-700 text-xs">Features</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(models).map(([key, m]) => (
            <tr key={key} className="border-b border-gray-100 hover:bg-gray-50">
              <td className="px-4 py-2.5 font-semibold text-gray-900">{names[key] || key}</td>
              {metrics.map(metric => (
                <td key={metric} className={`px-4 py-2.5 text-right font-mono ${m[metric] >= 0.9 ? 'text-green-600 font-semibold' : 'text-gray-700'}`}>
                  {m[metric]?.toFixed(3)}
                </td>
              ))}
              <td className="px-4 py-2.5 text-right font-mono text-gray-500">{m.n_features_used}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ROCChart({ roc_curves }) {
  if (!roc_curves) return null
  const colors = { random_forest: '#2563eb', svm: '#dc2626', lasso: '#16a34a' }
  const names = { random_forest: 'Random Forest', svm: 'SVM', lasso: 'LASSO' }
  const w = 300, h = 300, pad = 40

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
      <h4 className="text-sm font-semibold text-gray-700 mb-3">ROC Curves</h4>
      <svg viewBox={`0 0 ${w + pad * 2} ${h + pad * 2}`} className="w-full max-w-sm mx-auto">
        {/* Grid */}
        {[0, 0.25, 0.5, 0.75, 1].map(v => (
          <g key={v}>
            <line x1={pad} y1={pad + h - v * h} x2={pad + w} y2={pad + h - v * h} stroke="#e5e7eb" strokeWidth={1} />
            <line x1={pad + v * w} y1={pad} x2={pad + v * w} y2={pad + h} stroke="#e5e7eb" strokeWidth={1} />
            <text x={pad - 5} y={pad + h - v * h + 4} textAnchor="end" fontSize={10} fill="#9ca3af">{v.toFixed(1)}</text>
            <text x={pad + v * w} y={pad + h + 15} textAnchor="middle" fontSize={10} fill="#9ca3af">{v.toFixed(1)}</text>
          </g>
        ))}
        {/* Diagonal */}
        <line x1={pad} y1={pad + h} x2={pad + w} y2={pad} stroke="#d1d5db" strokeWidth={1} strokeDasharray="4,4" />
        {/* Curves */}
        {Object.entries(roc_curves).map(([key, { fpr, tpr, auc }]) => {
          const points = fpr.map((f, i) => `${pad + f * w},${pad + h - tpr[i] * h}`).join(' ')
          return (
            <g key={key}>
              <polyline points={points} fill="none" stroke={colors[key]} strokeWidth={2.5} />
            </g>
          )
        })}
        {/* Labels */}
        <text x={pad + w / 2} y={pad + h + 35} textAnchor="middle" fontSize={12} fill="#374151">False Positive Rate</text>
        <text x={12} y={pad + h / 2} textAnchor="middle" fontSize={12} fill="#374151" transform={`rotate(-90, 12, ${pad + h / 2})`}>True Positive Rate</text>
        {/* Legend */}
        {Object.entries(roc_curves).map(([key, { auc }], i) => (
          <g key={key} transform={`translate(${pad + 10}, ${pad + 15 + i * 18})`}>
            <line x1={0} y1={0} x2={16} y2={0} stroke={colors[key]} strokeWidth={2.5} />
            <text x={20} y={4} fontSize={10} fill="#374151">{names[key]} (AUC={auc.toFixed(3)})</text>
          </g>
        ))}
      </svg>
    </div>
  )
}

function ConfusionMatrix({ matrix }) {
  if (!matrix) return null
  const { tp, fn, fp, tn, labels } = matrix

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
      <h4 className="text-sm font-semibold text-gray-700 mb-3">Confusion Matrix (Best Model: Random Forest)</h4>
      <div className="grid grid-cols-3 gap-1 max-w-xs mx-auto text-center text-sm">
        <div />
        <div className="font-medium text-gray-500 text-xs py-1">Pred: {labels[0]}</div>
        <div className="font-medium text-gray-500 text-xs py-1">Pred: {labels[1]}</div>
        <div className="font-medium text-gray-500 text-xs py-1 text-right pr-2">True: {labels[0]}</div>
        <div className="bg-green-100 text-green-800 font-bold rounded-lg py-3">{tp}</div>
        <div className="bg-red-50 text-red-600 font-bold rounded-lg py-3">{fn}</div>
        <div className="font-medium text-gray-500 text-xs py-1 text-right pr-2">True: {labels[1]}</div>
        <div className="bg-red-50 text-red-600 font-bold rounded-lg py-3">{fp}</div>
        <div className="bg-green-100 text-green-800 font-bold rounded-lg py-3">{tn}</div>
      </div>
    </div>
  )
}

export default function BiomarkerPlot({ biomarkers }) {
  const [showAll, setShowAll] = useState(false)

  if (!biomarkers || !biomarkers.consensus_biomarkers) return null

  const { random_forest, svm_ranking, lasso_coefficients, consensus_biomarkers,
          model_performance, roc_curves, confusion_matrix, summary } = biomarkers

  const maxRfImp = random_forest?.[0]?.importance || 1
  const lasso_selected = lasso_coefficients?.filter(c => c.selected) || []
  const maxLasso = Math.max(...lasso_selected.map(c => Math.abs(c.coefficient)), 0.01)

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div>
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Target className="w-5 h-5 text-brand-600" />
          ML Biomarker Selection
        </h3>
        <p className="text-sm text-gray-500 mb-4">
          Three ML methods identify minimal gene sets that best classify conditions.
          Consensus biomarkers are genes selected by all three methods.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <MetricCard label="DEGs Input" value={summary.total_deg_input} />
          <MetricCard label="RF Top Features" value={summary.rf_top_features} color="text-blue-600" />
          <MetricCard label="SVM Top Features" value={summary.svm_top_features} color="text-red-600" />
          <MetricCard label="LASSO Selected" value={summary.lasso_selected} color="text-green-600" />
          <MetricCard label="Consensus" value={summary.consensus_count} color="text-purple-600" />
        </div>
      </div>

      {/* Model performance */}
      <div>
        <h4 className="text-md font-semibold mb-3 flex items-center gap-2">
          <Shield className="w-4 h-4 text-gray-600" />
          Model Performance (5-fold CV)
        </h4>
        <ModelPerformanceTable models={model_performance} />
      </div>

      {/* ROC + Confusion side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ROCChart roc_curves={roc_curves} />
        <ConfusionMatrix matrix={confusion_matrix} />
      </div>

      {/* Random Forest feature importance */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
        <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-blue-600" />
          Random Forest — Feature Importance (Top 15)
        </h4>
        <div className="space-y-1.5">
          {random_forest?.slice(0, 15).map((g) => (
            <BarH key={g.gene} label={g.gene} value={g.importance} maxValue={maxRfImp} color="bg-blue-500" />
          ))}
        </div>
      </div>

      {/* LASSO coefficients */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
        <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
          <FlaskConical className="w-4 h-4 text-green-600" />
          LASSO — Non-zero Coefficients ({lasso_selected.length} genes)
        </h4>
        <div className="space-y-1.5">
          {lasso_selected.slice(0, 15).map((g) => (
            <BarH key={g.gene} label={g.gene} value={Math.abs(g.coefficient)} maxValue={maxLasso}
                  color={g.coefficient > 0 ? 'bg-red-400' : 'bg-blue-400'} />
          ))}
        </div>
        <p className="text-xs text-gray-400 mt-2">Red = upregulated, Blue = downregulated</p>
      </div>

      {/* Consensus biomarker table */}
      <div>
        <h4 className="text-md font-semibold mb-3 flex items-center gap-2">
          <Target className="w-4 h-4 text-purple-600" />
          Consensus Biomarkers ({consensus_biomarkers.length} genes selected by all 3 methods)
        </h4>
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-700">Gene</th>
                <th className="text-right px-4 py-3 font-medium text-gray-700">log2FC</th>
                <th className="text-right px-4 py-3 font-medium text-gray-700">FDR</th>
                <th className="text-right px-4 py-3 font-medium text-gray-700">RF Importance</th>
                <th className="text-right px-4 py-3 font-medium text-gray-700">RF Rank</th>
                <th className="text-right px-4 py-3 font-medium text-gray-700">SVM Rank</th>
                <th className="text-right px-4 py-3 font-medium text-gray-700">LASSO Coef</th>
              </tr>
            </thead>
            <tbody>
              {(showAll ? consensus_biomarkers : consensus_biomarkers.slice(0, 10)).map((g, i) => (
                <tr key={i} className="border-b border-gray-100 hover:bg-purple-50">
                  <td className="px-4 py-2.5 font-mono font-semibold text-gray-900">{g.gene}</td>
                  <td className={`px-4 py-2.5 text-right font-mono ${g.log2fc > 0 ? 'text-red-600' : 'text-blue-600'}`}>
                    {g.log2fc > 0 ? '+' : ''}{g.log2fc.toFixed(2)}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-gray-500">{g.fdr.toExponential(2)}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-blue-600">{g.rf_importance.toFixed(4)}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-gray-500">#{g.rf_rank}</td>
                  <td className="px-4 py-2.5 text-right font-mono text-gray-500">#{g.svm_rank}</td>
                  <td className={`px-4 py-2.5 text-right font-mono ${g.lasso_coef > 0 ? 'text-red-600' : 'text-blue-600'}`}>
                    {g.lasso_coef.toFixed(4)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {consensus_biomarkers.length > 10 && (
            <button
              onClick={() => setShowAll(!showAll)}
              className="w-full py-2 text-sm text-brand-600 hover:bg-gray-50 flex items-center justify-center gap-1"
            >
              {showAll ? <><ChevronUp className="w-4 h-4" /> Show less</> : <><ChevronDown className="w-4 h-4" /> Show all {consensus_biomarkers.length}</>}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
