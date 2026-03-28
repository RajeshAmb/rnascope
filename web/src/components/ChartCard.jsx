import { useState, useRef, useCallback } from 'react'
import { Download, Image, FileSpreadsheet, FileImage, ChevronDown } from 'lucide-react'
import Plotly from 'plotly.js-dist-min'

/**
 * ChartCard — wraps any chart or table with a title bar and download dropdown.
 *
 * Props:
 *   title       – card heading
 *   plotRef     – React ref whose .current is the Plotly <div> (for image export)
 *   csvData     – { filename, headers, rows } for CSV export
 *   children    – the chart / table content
 */
export default function ChartCard({ title, plotRef, csvData, children }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const wrapperRef = useRef(null)

  // Close dropdown on outside click
  const close = useCallback(() => setMenuOpen(false), [])

  // ---- PNG download via Plotly ----
  const downloadPNG = async () => {
    setMenuOpen(false)
    const el = plotRef?.current?.el
    if (!el) return
    try {
      const url = await Plotly.toImage(el, { format: 'png', width: 1600, height: 1000, scale: 2 })
      triggerDownload(url, `${slugify(title)}.png`)
    } catch (e) {
      console.error('PNG export failed', e)
    }
  }

  // ---- SVG download via Plotly ----
  const downloadSVG = async () => {
    setMenuOpen(false)
    const el = plotRef?.current?.el
    if (!el) return
    try {
      const url = await Plotly.toImage(el, { format: 'svg', width: 1600, height: 1000 })
      triggerDownload(url, `${slugify(title)}.svg`)
    } catch (e) {
      console.error('SVG export failed', e)
    }
  }

  // ---- CSV download from data ----
  const downloadCSV = () => {
    setMenuOpen(false)
    if (!csvData) return
    const { filename, headers, rows } = csvData
    const escaped = (v) => {
      const s = String(v ?? '')
      return s.includes(',') || s.includes('"') || s.includes('\n')
        ? `"${s.replace(/"/g, '""')}"`
        : s
    }
    const lines = [headers.map(escaped).join(',')]
    for (const row of rows) {
      lines.push(row.map(escaped).join(','))
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    triggerDownload(url, filename || `${slugify(title)}.csv`)
    URL.revokeObjectURL(url)
  }

  const hasPlot = !!plotRef
  const hasCsv = !!csvData

  if (!hasPlot && !hasCsv) {
    // No download capability — render plain card
    return (
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {title && (
          <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
            <h3 className="font-semibold text-gray-900 text-sm">{title}</h3>
          </div>
        )}
        <div className="p-4">{children}</div>
      </div>
    )
  }

  return (
    <div ref={wrapperRef} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-visible relative">
      {/* Header bar */}
      <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
        <h3 className="font-semibold text-gray-900 text-sm">{title}</h3>

        {/* Download button */}
        <div className="relative">
          <button
            onClick={() => setMenuOpen((v) => !v)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-50 hover:bg-gray-100 rounded-lg border border-gray-200 transition"
          >
            <Download className="w-3.5 h-3.5" />
            Download
            <ChevronDown className={`w-3 h-3 transition ${menuOpen ? 'rotate-180' : ''}`} />
          </button>

          {menuOpen && (
            <>
              {/* Backdrop to close */}
              <div className="fixed inset-0 z-40" onClick={close} />
              <div className="absolute right-0 top-full mt-1 w-48 bg-white rounded-lg shadow-xl border border-gray-200 py-1 z-50">
                {hasPlot && (
                  <>
                    <button
                      onClick={downloadPNG}
                      className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                    >
                      <Image className="w-4 h-4 text-blue-500" />
                      Download PNG
                    </button>
                    <button
                      onClick={downloadSVG}
                      className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                    >
                      <FileImage className="w-4 h-4 text-purple-500" />
                      Download SVG
                    </button>
                  </>
                )}
                {hasCsv && (
                  <button
                    onClick={downloadCSV}
                    className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
                  >
                    <FileSpreadsheet className="w-4 h-4 text-green-500" />
                    Download CSV
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Chart content */}
      <div className="p-3">{children}</div>
    </div>
  )
}

// ---- Helpers ----

function slugify(text) {
  return (text || 'chart')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
}

function triggerDownload(url, filename) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}
