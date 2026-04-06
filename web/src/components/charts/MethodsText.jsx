import { useState } from 'react'
import { Copy, Check, BookOpen } from 'lucide-react'

export default function MethodsText({ data }) {
  const [copied, setCopied] = useState(false)

  if (!data || !data.text) return null

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(data.text)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback for browsers without clipboard API
      const el = document.createElement('textarea')
      el.value = data.text
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-brand-600" />
          <h3 className="font-semibold text-gray-900">Methods — Publication Ready Text</h3>
        </div>
        <button
          onClick={handleCopy}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition shadow-sm ${
            copied
              ? 'bg-green-100 text-green-700 border border-green-300'
              : 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50'
          }`}
        >
          {copied ? (
            <>
              <Check className="w-4 h-4" />
              Copied!
            </>
          ) : (
            <>
              <Copy className="w-4 h-4" />
              Copy to Clipboard
            </>
          )}
        </button>
      </div>

      {/* Methods card */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
        <div className="prose prose-sm max-w-none">
          {data.text.split('\n\n').map((paragraph, i) => (
            <p key={i} className="text-gray-800 leading-7 text-sm mb-4 last:mb-0">
              {paragraph}
            </p>
          ))}
        </div>
      </div>

      {/* Software versions table */}
      {data.tools && data.tools.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
            <h4 className="font-medium text-gray-700">Software Versions</h4>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-2 font-medium text-gray-600">Tool</th>
                <th className="text-left px-4 py-2 font-medium text-gray-600">Version</th>
                <th className="text-left px-4 py-2 font-medium text-gray-600">Purpose</th>
                <th className="text-left px-4 py-2 font-medium text-gray-600">Citation</th>
              </tr>
            </thead>
            <tbody>
              {data.tools.map((t, i) => (
                <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-4 py-2 font-semibold text-brand-700">{t.name}</td>
                  <td className="px-4 py-2 font-mono text-gray-600">{t.version}</td>
                  <td className="px-4 py-2 text-gray-700">{t.purpose}</td>
                  <td className="px-4 py-2 text-gray-500 text-xs">{t.citation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Parameters block */}
      {data.parameters && (
        <div className="bg-gray-50 rounded-xl border border-gray-200 p-4">
          <h4 className="font-medium text-gray-700 mb-2 text-sm">Analysis Parameters</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(data.parameters).map(([key, value]) => (
              <div key={key} className="bg-white rounded-lg border border-gray-200 p-3">
                <p className="text-xs text-gray-500 capitalize">{key.replace(/_/g, ' ')}</p>
                <p className="text-sm font-semibold text-gray-800 font-mono">{String(value)}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
