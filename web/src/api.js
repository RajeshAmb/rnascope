const BASE = ''

export async function initJob(metadata) {
  // Accept either a FormData or plain object
  let fd
  if (metadata instanceof FormData) {
    fd = metadata
  } else {
    fd = new FormData()
    Object.entries(metadata).forEach(([k, v]) => fd.append(k, v))
  }
  const res = await fetch(`${BASE}/api/jobs/init`, { method: 'POST', body: fd })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

const CHUNK_SIZE = 5 * 1024 * 1024 // 5 MB per chunk for server upload
const MAX_RETRIES = 15
const BASE_DELAY_MS = 2000 // 2s, doubles each retry (2s, 4s, 8s ... capped at 60s)

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function withRetry(fn, retries = MAX_RETRIES, onRetry) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await fn()
    } catch (err) {
      if (attempt === retries) throw err
      const waitMs = Math.min(BASE_DELAY_MS * Math.pow(2, attempt), 60000) // cap at 60s
      if (onRetry) onRetry(attempt + 1, retries, waitMs, err.message)
      await delay(waitMs)
    }
  }
}

// ---------------------------------------------------------------------------
// localStorage-based resume tracker
// ---------------------------------------------------------------------------
function _resumeKey(jobId, filename) {
  return `upload_${jobId}_${filename}`
}

function getCompletedParts(jobId, filename) {
  try {
    const raw = localStorage.getItem(_resumeKey(jobId, filename))
    return raw ? JSON.parse(raw) : {} // { partIndex: etag }
  } catch { return {} }
}

function markPartComplete(jobId, filename, partIndex, etag) {
  const parts = getCompletedParts(jobId, filename)
  parts[partIndex] = etag
  localStorage.setItem(_resumeKey(jobId, filename), JSON.stringify(parts))
}

function clearResume(jobId, filename) {
  localStorage.removeItem(_resumeKey(jobId, filename))
}

// Save presign data so we can resume without re-requesting
function savePresignData(jobId, filename, presign) {
  localStorage.setItem(`presign_${jobId}_${filename}`, JSON.stringify(presign))
}

function getPresignData(jobId, filename) {
  try {
    const raw = localStorage.getItem(`presign_${jobId}_${filename}`)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

function clearPresignData(jobId, filename) {
  localStorage.removeItem(`presign_${jobId}_${filename}`)
}

// ---------------------------------------------------------------------------
// Server chunked upload (fallback when S3 is not available)
// ---------------------------------------------------------------------------
function uploadOneChunk(jobId, file, chunkIndex, totalChunks, onChunkProgress) {
  const start = chunkIndex * CHUNK_SIZE
  const end = Math.min(start + CHUNK_SIZE, file.size)
  const chunk = file.slice(start, end)
  const fd = new FormData()
  fd.append('file', chunk, file.name)
  fd.append('chunk_index', chunkIndex)
  fd.append('total_chunks', totalChunks)
  fd.append('filename', file.name)

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${BASE}/api/jobs/${jobId}/upload`)
    xhr.timeout = 120000 // 2 min per 5MB chunk
    if (onChunkProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onChunkProgress(chunkIndex, e.loaded)
      }
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText))
      } else {
        reject(new Error(xhr.responseText || `Upload failed (${xhr.status})`))
      }
    }
    xhr.onerror = () => reject(new Error('Network error during upload'))
    xhr.ontimeout = () => reject(new Error('Upload timed out — retrying'))
    xhr.send(fd)
  })
}

export async function uploadFile(jobId, file, onProgress, onRetryStatus) {
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE)
  const chunkProgress = new Array(totalChunks).fill(0)

  const reportProgress = () => {
    if (!onProgress) return
    const totalUploaded = chunkProgress.reduce((a, b) => a + b, 0)
    onProgress(totalUploaded / file.size)
  }

  for (let idx = 0; idx < totalChunks; idx++) {
    await withRetry(() => {
      chunkProgress[idx] = 0
      return uploadOneChunk(jobId, file, idx, totalChunks, (ci, loaded) => {
        chunkProgress[ci] = loaded
        reportProgress()
      })
    }, MAX_RETRIES, (attempt, max, waitMs, errMsg) => {
      if (onRetryStatus) onRetryStatus({ attempt, max, waitMs, chunk: idx + 1, totalChunks, error: errMsg })
    })
    chunkProgress[idx] = Math.min(CHUNK_SIZE, file.size - idx * CHUNK_SIZE)
    reportProgress()
  }
  return { filename: file.name, size_mb: Math.round(file.size / (1024 * 1024)) }
}

export async function startJob(jobId) {
  const res = await fetch(`${BASE}/api/jobs/${jobId}/start`, { method: 'POST' })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getUploadMode() {
  const res = await fetch(`${BASE}/api/upload-mode`)
  return res.json()
}

// ---------------------------------------------------------------------------
// S3 direct upload — resumable multipart with localStorage tracking
// ---------------------------------------------------------------------------
const S3_PART_SIZE = 2 * 1024 * 1024 // 2 MB per part — small enough to finish before idle timeout

function uploadS3Part(url, chunk, timeoutMs) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', url)
    xhr.timeout = timeoutMs
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.getResponseHeader('ETag'))
      } else {
        reject(new Error(`S3 part failed (${xhr.status})`))
      }
    }
    xhr.onerror = () => reject(new Error('Network error'))
    xhr.ontimeout = () => reject(new Error('Timed out'))
    xhr.send(chunk)
  })
}

export async function uploadFileS3(jobId, file, onProgress, onRetryStatus) {
  const partCount = Math.ceil(file.size / S3_PART_SIZE)

  // Check if we have a saved presign (resume scenario)
  let presign = getPresignData(jobId, file.name)

  if (!presign || presign.parts?.length !== partCount) {
    // Get fresh presigned URLs
    presign = await withRetry(async () => {
      const res = await fetch(`${BASE}/api/jobs/${jobId}/presign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: file.name, content_type: file.type || 'application/gzip', part_count: partCount }),
      })
      if (!res.ok) throw new Error(await res.text())
      return res.json()
    }, MAX_RETRIES, (attempt, max, waitMs, errMsg) => {
      if (onRetryStatus) onRetryStatus({ attempt, max, waitMs, chunk: 0, totalChunks: partCount, error: errMsg })
    })
    savePresignData(jobId, file.name, presign)
  }

  if (presign.method === 'PUT') {
    // Small file — single PUT (shouldn't happen with 2MB parts, but handle it)
    await withRetry(() => {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open('PUT', presign.url)
        xhr.setRequestHeader('Content-Type', file.type || 'application/gzip')
        xhr.timeout = 600000 // 10 min
        if (onProgress) {
          xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) onProgress(e.loaded / e.total)
          }
        }
        xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`S3 upload failed (${xhr.status})`))
        xhr.onerror = () => reject(new Error('Network error during S3 upload'))
        xhr.ontimeout = () => reject(new Error('Upload timed out — retrying'))
        xhr.send(file)
      })
    }, MAX_RETRIES, (attempt, max, waitMs, errMsg) => {
      if (onRetryStatus) onRetryStatus({ attempt, max, waitMs, chunk: 1, totalChunks: 1, error: errMsg })
    })

    const regFd = new FormData()
    regFd.append('filename', file.name)
    regFd.append('size_bytes', file.size)
    await fetch(`${BASE}/api/jobs/${jobId}/presign/register`, { method: 'POST', body: regFd })

  } else {
    // Multipart upload — sequential, resumable via localStorage
    const completedParts = getCompletedParts(jobId, file.name)
    const parts = new Array(presign.parts.length)
    const partProgress = new Array(presign.parts.length).fill(0)

    // Pre-fill completed parts
    for (const [idx, etag] of Object.entries(completedParts)) {
      const i = parseInt(idx)
      parts[i] = { part_number: presign.parts[i].part_number, etag }
      partProgress[i] = Math.min(S3_PART_SIZE, file.size - i * S3_PART_SIZE)
    }

    const reportS3Progress = () => {
      if (!onProgress) return
      const totalUploaded = partProgress.reduce((a, b) => a + b, 0)
      onProgress(totalUploaded / file.size)
    }

    reportS3Progress() // Show already-completed progress immediately

    // Upload remaining parts one at a time
    for (let i = 0; i < presign.parts.length; i++) {
      // Skip already completed parts
      if (completedParts[i]) continue

      const partInfo = presign.parts[i]
      const start = i * S3_PART_SIZE
      const end = Math.min(start + S3_PART_SIZE, file.size)

      const etag = await withRetry(() => {
        partProgress[i] = 0
        const chunk = file.slice(start, end)
        return uploadS3Part(partInfo.url, chunk, 60000) // 60s timeout for 2MB
      }, MAX_RETRIES, (attempt, max, waitMs, errMsg) => {
        if (onRetryStatus) onRetryStatus({ attempt, max, waitMs, chunk: i + 1, totalChunks: presign.parts.length, error: errMsg })
      })

      partProgress[i] = Math.min(S3_PART_SIZE, file.size - i * S3_PART_SIZE)
      parts[i] = { part_number: partInfo.part_number, etag }
      markPartComplete(jobId, file.name, i, etag)
      reportS3Progress()
    }

    // Complete multipart upload
    await withRetry(async () => {
      const res = await fetch(`${BASE}/api/jobs/${jobId}/presign/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ s3_key: presign.s3_key, upload_id: presign.upload_id, parts: parts.filter(Boolean) }),
      })
      if (!res.ok) throw new Error(await res.text())
    })

    // Clean up resume data on success
    clearResume(jobId, file.name)
    clearPresignData(jobId, file.name)
  }

  return { filename: file.name, size_mb: Math.round(file.size / (1024 * 1024)) }
}

export async function listJobs() {
  const res = await fetch(`${BASE}/api/jobs`)
  return res.json()
}

export async function getJob(jobId) {
  const res = await fetch(`${BASE}/api/jobs/${jobId}`)
  if (!res.ok) throw new Error('Job not found')
  return res.json()
}

export async function getResults(jobId) {
  const res = await fetch(`${BASE}/api/jobs/${jobId}/results`)
  if (!res.ok) return null
  return res.json()
}

export async function askChat(jobId, question) {
  const res = await fetch(`${BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ job_id: jobId, question }),
  })
  return res.json()
}

export function connectWebSocket(jobId, onMessage) {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${window.location.host}/ws/${jobId}`)
  ws.onmessage = (e) => onMessage(JSON.parse(e.data))
  ws.onclose = () => console.log('WebSocket closed')
  return ws
}
