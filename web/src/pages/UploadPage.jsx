import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import { Upload, FileText, X, Loader2, FlaskConical, Table } from 'lucide-react'
import { initJob, uploadFile, uploadFileS3, startJob, getUploadMode } from '../api'

export default function UploadPage() {
  const navigate = useNavigate()
  const [files, setFiles] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [fileProgress, setFileProgress] = useState({}) // { [fileName]: { pct, status } }
  const [metadataFile, setMetadataFile] = useState(null)
  const [metadataPreview, setMetadataPreview] = useState(null) // { headers: [], rows: [] }
  const [error, setError] = useState(null)
  const [useS3, setUseS3] = useState(null) // null = not checked yet
  const [diskFreeGb, setDiskFreeGb] = useState(null)
  const MAX_PARALLEL = 3

  // Check if S3 direct upload is available on mount
  useState(() => {
    getUploadMode().then((m) => {
      setUseS3(m.s3_enabled)
      setDiskFreeGb(m.disk_free_gb)
    }).catch(() => setUseS3(false))
  })
  const [form, setForm] = useState({
    project_name: '',
    species: 'human',
    domain: 'biomedical',
    condition_a: '',
    condition_b: '',
    n_a: 3,
    n_b: 3,
    genotypes: '',
    time_points: '',
    tissue_type: '',
    disease_context: '',
    email: '',
  })

  const onDrop = useCallback((accepted) => {
    setFiles((prev) => [...prev, ...accepted])
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/gzip': ['.gz', '.fastq.gz', '.fq.gz'] },
    multiple: true,
  })

  const removeFile = (idx) => setFiles((f) => f.filter((_, i) => i !== idx))

  const handleMetadataFile = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setMetadataFile(file)
    const reader = new FileReader()
    reader.onload = (evt) => {
      const text = evt.target.result
      const lines = text.split(/\r?\n/).filter((l) => l.trim())
      if (lines.length < 2) { setMetadataPreview(null); return }
      const headers = lines[0].split(',').map((h) => h.trim())
      const rows = lines.slice(1, 11).map((line) => line.split(',').map((c) => c.trim()))
      setMetadataPreview({ headers, rows, totalRows: lines.length - 1 })
    }
    reader.readAsText(file)
  }

  const removeMetadata = () => {
    setMetadataFile(null)
    setMetadataPreview(null)
  }

  const setField = (key, val) => setForm((f) => ({ ...f, [key]: val }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (files.length === 0) { setError('Please upload at least one FASTQ file'); return }
    if (!form.project_name || !form.condition_a || !form.condition_b) {
      setError('Please fill in project name and both conditions')
      return
    }

    setSubmitting(true)
    setError(null)
    setFileProgress({})

    try {
      // Step 1: Create job with metadata only
      const { job_id } = await initJob(form)

      // Step 2a: Upload metadata CSV if provided
      if (metadataFile) {
        const uploader = useS3 ? uploadFileS3 : uploadFile
        setFileProgress((prev) => ({ ...prev, [metadataFile.name]: { pct: 0, status: 'uploading', retry: null } }))
        await uploader(job_id, metadataFile, (pct) => {
          setFileProgress((prev) => ({ ...prev, [metadataFile.name]: { pct: Math.round(pct * 100), status: 'uploading', retry: null } }))
        }, (retryInfo) => {
          setFileProgress((prev) => ({ ...prev, [metadataFile.name]: { ...prev[metadataFile.name], status: 'retrying', retry: retryInfo } }))
        })
        setFileProgress((prev) => ({ ...prev, [metadataFile.name]: { pct: 100, status: 'done', retry: null } }))
      }

      // Step 2b: Upload FASTQ files in parallel (MAX_PARALLEL at a time)
      const uploader = useS3 ? uploadFileS3 : uploadFile
      const queue = [...files]
      const uploadNext = async () => {
        while (queue.length > 0) {
          const file = queue.shift()
          setFileProgress((prev) => ({ ...prev, [file.name]: { pct: 0, status: 'uploading', retry: null } }))
          await uploader(job_id, file, (pct) => {
            setFileProgress((prev) => ({ ...prev, [file.name]: { pct: Math.round(pct * 100), status: 'uploading', retry: null } }))
          }, (retryInfo) => {
            setFileProgress((prev) => ({ ...prev, [file.name]: { ...prev[file.name], status: 'retrying', retry: retryInfo } }))
          })
          setFileProgress((prev) => ({ ...prev, [file.name]: { pct: 100, status: 'done', retry: null } }))
        }
      }

      const workers = Array.from({ length: Math.min(MAX_PARALLEL, files.length) }, () => uploadNext())
      await Promise.all(workers)

      // Step 3: Start the pipeline
      await startJob(job_id)
      navigate(`/results/${job_id}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
      setFileProgress({})
    }
  }

  const totalSize = files.reduce((s, f) => s + f.size, 0)
  const sizeDisplay = totalSize >= 1024 * 1024 * 1024
    ? (totalSize / 1024 / 1024 / 1024).toFixed(2) + ' GB'
    : (totalSize / 1024 / 1024).toFixed(1) + ' MB'

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-3">
          <FlaskConical className="w-8 h-8 text-brand-600" />
          New RNA-seq Analysis
        </h1>
        <p className="mt-2 text-gray-600">
          Upload your FASTQ files and configure your experiment. The autonomous agent handles everything else.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-8">
        {/* Dropzone */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <h2 className="text-lg font-semibold mb-4">Upload FASTQ Files</h2>
          <div
            {...getRootProps()}
            className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition ${
              isDragActive ? 'border-brand-500 bg-brand-50' : 'border-gray-300 hover:border-brand-400 hover:bg-gray-50'
            }`}
          >
            <input {...getInputProps()} />
            <Upload className="w-12 h-12 mx-auto text-gray-400 mb-4" />
            <p className="text-lg font-medium text-gray-700">
              {isDragActive ? 'Drop files here...' : 'Drag & drop FASTQ files here'}
            </p>
            <p className="text-sm text-gray-500 mt-2">or click to browse (.fastq.gz, .fq.gz)</p>
          </div>

          {files.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-gray-700">
                  {files.length} file{files.length > 1 ? 's' : ''} ({sizeDisplay})
                </span>
                <button
                  type="button"
                  onClick={() => setFiles([])}
                  className="text-xs text-red-600 hover:underline"
                >
                  Clear all
                </button>
              </div>
              <div className="max-h-48 overflow-y-auto space-y-1">
                {files.map((f, i) => (
                  <div key={i} className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2 text-sm">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-gray-400" />
                      <span className="font-mono text-gray-800">{f.name}</span>
                      <span className="text-gray-400">({(f.size / 1024 / 1024).toFixed(1)} MB)</span>
                    </div>
                    <button type="button" onClick={() => removeFile(i)} className="text-gray-400 hover:text-red-500">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Metadata CSV */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Table className="w-5 h-5 text-brand-600" />
            Sample Metadata (CSV)
          </h2>
          <p className="text-sm text-gray-500 mb-3">
            Upload a CSV file with sample information. Expected columns: <span className="font-mono text-xs">sample_id, fastq_r1, fastq_r2, condition, genotype, time_point</span>
          </p>
          <div className="flex items-center gap-3">
            <label className="cursor-pointer inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-300 text-sm font-medium text-gray-700 hover:bg-gray-50 transition">
              <Upload className="w-4 h-4" />
              {metadataFile ? 'Change CSV' : 'Choose CSV file'}
              <input type="file" accept=".csv,.tsv,.txt" onChange={handleMetadataFile} className="hidden" />
            </label>
            {metadataFile && (
              <div className="flex items-center gap-2 text-sm text-gray-700">
                <FileText className="w-4 h-4 text-gray-400" />
                <span className="font-mono">{metadataFile.name}</span>
                <button type="button" onClick={removeMetadata} className="text-gray-400 hover:text-red-500">
                  <X className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>

          {metadataPreview && (
            <div className="mt-4 border border-gray-200 rounded-lg overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="bg-gray-50">
                    {metadataPreview.headers.map((h, i) => (
                      <th key={i} className="px-3 py-2 text-left font-semibold text-gray-600 border-b">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {metadataPreview.rows.map((row, ri) => (
                    <tr key={ri} className={ri % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                      {row.map((cell, ci) => (
                        <td key={ci} className="px-3 py-1.5 text-gray-700 border-b border-gray-100">{cell}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {metadataPreview.totalRows > 10 && (
                <p className="text-xs text-gray-400 px-3 py-2">Showing 10 of {metadataPreview.totalRows} rows</p>
              )}
            </div>
          )}
        </div>

        {/* Experiment config */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <h2 className="text-lg font-semibold mb-4">Experiment Configuration</h2>
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Project Name</label>
              <input
                type="text"
                value={form.project_name}
                onChange={(e) => setField('project_name', e.target.value)}
                placeholder="e.g. IBD Colonic Biopsy Study"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Species</label>
              <select
                value={form.species}
                onChange={(e) => setField('species', e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-brand-500"
              >
                <optgroup label="Animals">
                  <option value="human">Human (GRCh38)</option>
                  <option value="mouse">Mouse (mm39)</option>
                  <option value="rat">Rat (mRatBN7.2)</option>
                  <option value="zebrafish">Zebrafish (GRCz11)</option>
                  <option value="drosophila">Drosophila (dm6)</option>
                  <option value="c_elegans">C. elegans (WBcel235)</option>
                  <option value="chicken">Chicken (GRCg7b)</option>
                  <option value="pig">Pig (Sscrofa11.1)</option>
                  <option value="cow">Cow (ARS-UCD1.3)</option>
                </optgroup>
                <optgroup label="Plants">
                  <option value="arabidopsis">Arabidopsis thaliana (TAIR10)</option>
                  <option value="rice">Rice — Oryza sativa (IRGSP-1.0)</option>
                  <option value="maize">Maize — Zea mays (Zm-B73-v5)</option>
                  <option value="wheat">Wheat — Triticum aestivum (IWGSC)</option>
                  <option value="tomato">Tomato — S. lycopersicum (SL4.0)</option>
                  <option value="soybean">Soybean — Glycine max (Wm82.a4)</option>
                  <option value="potato">Potato — S. tuberosum (DM v6.1)</option>
                  <option value="grape">Grape — Vitis vinifera (12X.v2)</option>
                  <option value="cotton">Cotton — Gossypium hirsutum (UTX-TM1)</option>
                  <option value="cotton_arboreum">Cotton — Gossypium arboreum (CRI v1.0)</option>
                </optgroup>
                <optgroup label="Microbiome / Soil / Food">
                  <option value="ecoli">E. coli (K-12 MG1655)</option>
                  <option value="yeast">Yeast — S. cerevisiae (R64)</option>
                  <option value="aspergillus">Aspergillus niger (CBS 513.88)</option>
                  <option value="lactobacillus">Lactobacillus (custom)</option>
                  <option value="metatranscriptome">Metatranscriptome (soil/food)</option>
                </optgroup>
                <optgroup label="Other">
                  <option value="custom">Custom genome (provide reference)</option>
                </optgroup>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Research Domain</label>
              <select
                value={form.domain}
                onChange={(e) => setField('domain', e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-brand-500"
              >
                <option value="biomedical">Biomedical / Clinical</option>
                <option value="plant_biology">Plant Biology / Crop Science</option>
                <option value="soil_microbiome">Soil Microbiome / Environmental</option>
                <option value="food_science">Food Science / Fermentation</option>
                <option value="agriculture">Agriculture / Animal Science</option>
                <option value="ecology">Ecology / Metatranscriptomics</option>
                <option value="other">Other</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Tissue / Sample Type</label>
              <input
                type="text"
                value={form.tissue_type}
                onChange={(e) => setField('tissue_type', e.target.value)}
                placeholder="e.g. leaf, root, rhizosphere soil, colon biopsy, fermented milk"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-brand-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Condition A (Control)</label>
              <input
                type="text"
                value={form.condition_a}
                onChange={(e) => setField('condition_a', e.target.value)}
                placeholder="e.g. Healthy, Untreated, WT"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Condition B (Treatment)</label>
              <input
                type="text"
                value={form.condition_b}
                onChange={(e) => setField('condition_b', e.target.value)}
                placeholder="e.g. Disease, Treated, KO"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-brand-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Samples in A (n)</label>
              <input
                type="number"
                min={1}
                value={form.n_a}
                onChange={(e) => setField('n_a', parseInt(e.target.value) || 1)}
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Samples in B (n)</label>
              <input
                type="number"
                min={1}
                value={form.n_b}
                onChange={(e) => setField('n_b', parseInt(e.target.value) || 1)}
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-brand-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Genotypes</label>
              <input
                type="text"
                value={form.genotypes}
                onChange={(e) => setField('genotypes', e.target.value)}
                placeholder="e.g. Resistant, Susceptible"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
              />
              <p className="text-xs text-gray-400 mt-1">Comma-separated genotype names (optional)</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Time Points</label>
              <input
                type="text"
                value={form.time_points}
                onChange={(e) => setField('time_points', e.target.value)}
                placeholder="e.g. 0DPI, 7DPI, 14DPI, 21DPI"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-brand-500 focus:border-brand-500"
              />
              <p className="text-xs text-gray-400 mt-1">Comma-separated time points (optional)</p>
            </div>

            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Biological Context</label>
              <input
                type="text"
                value={form.disease_context}
                onChange={(e) => setField('disease_context', e.target.value)}
                placeholder="e.g. drought stress, IBD, salt tolerance, food spoilage, nitrogen fixation"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-brand-500"
              />
            </div>

            <div className="col-span-2">
              <label className="block text-sm font-medium text-gray-700 mb-1">Notification Email (optional)</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setField('email', e.target.value)}
                placeholder="you@lab.org"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-brand-500"
              />
            </div>
          </div>
        </div>

        {diskFreeGb !== null && diskFreeGb < 2 && (
          <div className={`border rounded-lg px-4 py-3 text-sm ${diskFreeGb < 0.5 ? 'bg-red-50 border-red-200 text-red-700' : 'bg-amber-50 border-amber-200 text-amber-700'}`}>
            Server disk space low: <strong>{diskFreeGb.toFixed(1)} GB</strong> free. {diskFreeGb < 0.5 ? 'Uploads may fail.' : 'Large uploads may not fit.'} {!useS3 && 'Consider enabling S3 for direct uploads.'}
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
            {error}
          </div>
        )}

        {Object.keys(fileProgress).length > 0 && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 space-y-3">
            <div className="flex items-center justify-between text-sm font-medium text-blue-800">
              <span>Uploading {Object.values(fileProgress).filter((f) => f.status === 'done').length} / {Object.keys(fileProgress).length} files ({MAX_PARALLEL} parallel)</span>
              <span className="text-xs font-normal">{useS3 ? 'Direct to S3' : 'Server upload'}</span>
            </div>
            <div className="max-h-48 overflow-y-auto space-y-2">
              {Object.entries(fileProgress).map(([name, { pct, status, retry }]) => (
                <div key={name}>
                  <div className="flex items-center justify-between text-xs text-blue-700 mb-1">
                    <span className="font-mono truncate max-w-xs">{name}</span>
                    <span>
                      {status === 'done' && 'Done'}
                      {status === 'uploading' && `${pct}%`}
                      {status === 'retrying' && retry && (
                        <span className="text-amber-600">
                          Retry {retry.attempt}/{retry.max} (chunk {retry.chunk}/{retry.totalChunks}) — waiting {Math.round(retry.waitMs / 1000)}s
                        </span>
                      )}
                    </span>
                  </div>
                  <div className="w-full bg-blue-200 rounded-full h-1.5">
                    <div
                      className={`h-1.5 rounded-full transition-all duration-300 ${
                        status === 'done' ? 'bg-green-500' : status === 'retrying' ? 'bg-amber-500' : 'bg-blue-600'
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  {status === 'retrying' && retry && (
                    <p className="text-xs text-amber-600 mt-0.5">{retry.error}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full bg-brand-600 hover:bg-brand-700 text-white font-semibold py-3.5 px-6 rounded-xl transition disabled:opacity-50 flex items-center justify-center gap-2 text-lg"
        >
          {submitting ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              {Object.keys(fileProgress).length > 0 ? 'Uploading Files...' : 'Starting Pipeline...'}
            </>
          ) : (
            <>
              <FlaskConical className="w-5 h-5" />
              Start Analysis
            </>
          )}
        </button>
      </form>
    </div>
  )
}
