import { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import { Upload, FileText, X, Loader2, FlaskConical, Table } from 'lucide-react'
import { initJob, uploadFile, uploadFileS3, startJob, getUploadMode } from '../api'

const MAX_PARALLEL_FILES = 1

export default function UploadPage() {
  const navigate = useNavigate()
  const [files, setFiles] = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [metadataFile, setMetadataFile] = useState(null)
  const [metadataPreview, setMetadataPreview] = useState(null)
  const [uploadState, setUploadState] = useState(null) // { phase, fileProgress, filesDone, totalFiles }
  const [useS3, setUseS3] = useState(null)

  // Check if S3 direct upload is available on mount
  useEffect(() => {
    getUploadMode().then((m) => setUseS3(m.s3_enabled)).catch(() => setUseS3(false))
  }, [])

  const [form, setForm] = useState({
    project_name: '',
    species: 'human',
    domain: 'biomedical',
    condition_a: '',
    condition_b: '',
    n_a: 3,
    n_b: 3,
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
      const rows = lines.slice(1, 6).map((line) => line.split(',').map((c) => c.trim()))
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

    try {
      // Step 1: Init job with metadata only
      const fd = new FormData()
      Object.entries(form).forEach(([k, v]) => fd.append(k, v))
      const { job_id } = await initJob(fd)

      // Step 2a: Upload metadata CSV if provided
      if (metadataFile) {
        const metaUploader = useS3 ? uploadFileS3 : uploadFile
        await metaUploader(job_id, metadataFile)
      }

      // Step 2b: Upload FASTQ files in parallel (up to MAX_PARALLEL_FILES at a time)
      const fileProgress = {}
      files.forEach((f) => { fileProgress[f.name] = 0 })
      setUploadState({ phase: 'uploading', fileProgress: { ...fileProgress }, filesDone: 0, totalFiles: files.length })

      const queue = [...files]
      let filesDone = 0

      const uploader = useS3 ? uploadFileS3 : uploadFile
      const uploadNext = async () => {
        while (queue.length > 0) {
          const file = queue.shift()
          await uploader(job_id, file, (fraction) => {
            fileProgress[file.name] = Math.round(fraction * 100)
            setUploadState((s) => ({ ...s, fileProgress: { ...fileProgress } }))
          })
          filesDone++
          fileProgress[file.name] = 100
          setUploadState((s) => ({ ...s, fileProgress: { ...fileProgress }, filesDone }))
        }
      }

      const workers = Array.from({ length: Math.min(MAX_PARALLEL_FILES, files.length) }, () => uploadNext())
      await Promise.all(workers)

      // Step 3: Start pipeline
      setUploadState((s) => ({ ...s, phase: 'starting' }))
      await startJob(job_id)

      navigate(`/results/${job_id}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
      setUploadState(null)
    }
  }

  const totalSize = files.reduce((s, f) => s + f.size, 0)
  const sizeMB = (totalSize / 1024 / 1024).toFixed(1)

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
                  {files.length} file{files.length > 1 ? 's' : ''} ({sizeMB} MB)
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
          <h2 className="text-lg font-semibold mb-2">Sample Metadata (optional)</h2>
          <p className="text-sm text-gray-500 mb-4">
            Upload a CSV with sample info (sample_id, condition, genotype, replicate, etc.)
          </p>
          {!metadataFile ? (
            <label className="flex items-center gap-3 border-2 border-dashed border-gray-300 rounded-lg px-4 py-3 cursor-pointer hover:border-brand-400 hover:bg-gray-50 transition">
              <Table className="w-5 h-5 text-gray-400" />
              <span className="text-sm text-gray-600">Click to upload .csv file</span>
              <input type="file" accept=".csv,.tsv,.txt" className="hidden" onChange={handleMetadataFile} />
            </label>
          ) : (
            <div>
              <div className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2 text-sm mb-3">
                <div className="flex items-center gap-2">
                  <Table className="w-4 h-4 text-brand-600" />
                  <span className="font-mono text-gray-800">{metadataFile.name}</span>
                </div>
                <button type="button" onClick={removeMetadata} className="text-gray-400 hover:text-red-500">
                  <X className="w-4 h-4" />
                </button>
              </div>
              {metadataPreview && (
                <div className="overflow-x-auto">
                  <table className="text-xs border-collapse w-full">
                    <thead>
                      <tr>
                        {metadataPreview.headers.map((h, i) => (
                          <th key={i} className="border border-gray-200 bg-gray-100 px-2 py-1 text-left font-medium">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {metadataPreview.rows.map((row, ri) => (
                        <tr key={ri}>
                          {row.map((cell, ci) => (
                            <td key={ci} className="border border-gray-200 px-2 py-1">{cell}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {metadataPreview.totalRows > 5 && (
                    <p className="text-xs text-gray-400 mt-1">Showing 5 of {metadataPreview.totalRows} rows</p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Upload progress */}
        {uploadState && (
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">
                Uploading {uploadState.filesDone} / {uploadState.totalFiles} files ({MAX_PARALLEL_FILES} parallel)
              </h2>
              <span className="text-sm text-gray-500">Server upload</span>
            </div>
            <div className="space-y-3">
              {Object.entries(uploadState.fileProgress).map(([name, pct]) => (
                <div key={name}>
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span className="font-mono text-gray-700 truncate">{name}</span>
                    <span className="text-gray-500 ml-2">{pct}%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-brand-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

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
                  <option value="cotton">Cotton — Gossypium hirsutum (UTX-TM1 v2.1)</option>
                  <option value="cotton_arboreum">Cotton — Gossypium arboreum (CRI-updated_v1)</option>
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
              <label className="block text-sm font-medium text-gray-700 mb-1">Condition A (Treatment)</label>
              <input
                type="text"
                value={form.condition_a}
                onChange={(e) => setField('condition_a', e.target.value)}
                placeholder="e.g. Resistant, Disease, Treated, KO"
                className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm focus:ring-2 focus:ring-brand-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Condition B (Control)</label>
              <input
                type="text"
                value={form.condition_b}
                onChange={(e) => setField('condition_b', e.target.value)}
                placeholder="e.g. Susceptible, Healthy, Untreated, WT"
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

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
            {error}
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
              {uploadState?.phase === 'starting' ? 'Starting Pipeline...' : 'Uploading Files...'}
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
