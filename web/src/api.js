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

const CHUNK_SIZE = 10 * 1024 * 1024 // 10 MB per chunk (fits Render's 512MB RAM with parallel uploads)
const MAX_RETRIES = 5
const BASE_DELAY_MS = 1000 // 1s, doubles each retry (1s, 2s, 4s, 8s, 16s)

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function withRetry(fn, retries = MAX_RETRIES, onRetry) {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await fn()
    } catch (err) {
      if (attempt === retries) throw err
      const waitMs = BASE_DELAY_MS * Math.pow(2, attempt)
      if (onRetry) onRetry(attempt + 1, retries, waitMs, err.message)
      await delay(waitMs)
    }
  }
}

const PARALLEL_CHUNKS = 4 // upload 4 chunks of the same file concurrently

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
    xhr.send(fd)
  })
}

export async function uploadFile(jobId, file, onProgress, onRetryStatus) {
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE)
  const chunkProgress = new Array(totalChunks).fill(0) // bytes uploaded per chunk

  const reportProgress = () => {
    if (!onProgress) return
    const totalUploaded = chunkProgress.reduce((a, b) => a + b, 0)
    onProgress(totalUploaded / file.size)
  }

  // Process chunks with a pool of PARALLEL_CHUNKS workers
  const queue = Array.from({ length: totalChunks }, (_, i) => i)
  const workers = Array.from({ length: Math.min(PARALLEL_CHUNKS, totalChunks) }, async () => {
    while (queue.length > 0) {
      const idx = queue.shift()
      if (idx === undefined) break
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
  })

  await Promise.all(workers)
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

const S3_PART_SIZE = 10 * 1024 * 1024 // 10 MB per S3 multipart part

export async function uploadFileS3(jobId, file, onProgress, onRetryStatus) {
  const partCount = Math.ceil(file.size / S3_PART_SIZE)

  // Get presigned URL(s) — retry this too
  const presign = await withRetry(async () => {
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

  if (presign.method === 'PUT') {
    // Single PUT upload (file < 5GB) with retry
    await withRetry(() => new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('PUT', presign.url)
      xhr.setRequestHeader('Content-Type', file.type || 'application/gzip')
      if (onProgress) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) onProgress(e.loaded / e.total)
        }
      }
      xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`S3 upload failed (${xhr.status})`))
      xhr.onerror = () => reject(new Error('Network error during S3 upload'))
      xhr.send(file)
    }), MAX_RETRIES, (attempt, max, waitMs, errMsg) => {
      if (onRetryStatus) onRetryStatus({ attempt, max, waitMs, chunk: 1, totalChunks: 1, error: errMsg })
    })

    // Register file with backend
    const regFd = new FormData()
    regFd.append('filename', file.name)
    regFd.append('size_bytes', file.size)
    await fetch(`${BASE}/api/jobs/${jobId}/presign/register`, { method: 'POST', body: regFd })

  } else {
    // Multipart upload — parallel parts with worker pool
    const parts = new Array(presign.parts.length)
    const partProgress = new Array(presign.parts.length).fill(0)

    const reportS3Progress = () => {
      if (!onProgress) return
      const totalUploaded = partProgress.reduce((a, b) => a + b, 0)
      onProgress(totalUploaded / file.size)
    }

    const partQueue = presign.parts.map((p, i) => ({ ...p, index: i }))
    const s3Workers = Array.from({ length: Math.min(PARALLEL_CHUNKS, presign.parts.length) }, async () => {
      while (partQueue.length > 0) {
        const partInfo = partQueue.shift()
        if (!partInfo) break
        const i = partInfo.index
        const start = i * S3_PART_SIZE
        const end = Math.min(start + S3_PART_SIZE, file.size)

        const etag = await withRetry(() => {
          partProgress[i] = 0
          const chunk = file.slice(start, end)
          return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest()
            xhr.open('PUT', partInfo.url)
            xhr.upload.onprogress = (e) => {
              if (e.lengthComputable) {
                partProgress[i] = e.loaded
                reportS3Progress()
              }
            }
            xhr.onload = () => {
              if (xhr.status >= 200 && xhr.status < 300) {
                resolve(xhr.getResponseHeader('ETag'))
              } else {
                reject(new Error(`S3 part upload failed (${xhr.status})`))
              }
            }
            xhr.onerror = () => reject(new Error('Network error during S3 part upload'))
            xhr.send(chunk)
          })
        }, MAX_RETRIES, (attempt, max, waitMs, errMsg) => {
          if (onRetryStatus) onRetryStatus({ attempt, max, waitMs, chunk: i + 1, totalChunks: presign.parts.length, error: errMsg })
        })

        partProgress[i] = Math.min(S3_PART_SIZE, file.size - i * S3_PART_SIZE)
        reportS3Progress()
        parts[i] = { part_number: partInfo.part_number, etag }
      }
    })

    await Promise.all(s3Workers)

    // Complete multipart upload
    await withRetry(async () => {
      const res = await fetch(`${BASE}/api/jobs/${jobId}/presign/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ s3_key: presign.s3_key, upload_id: presign.upload_id, parts: parts.filter(Boolean) }),
      })
      if (!res.ok) throw new Error(await res.text())
    })
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
