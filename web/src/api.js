const BASE = ''

export async function createJob(formData) {
  const res = await fetch(`${BASE}/api/jobs`, { method: 'POST', body: formData })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function initJob(metadata) {
  const fd = new FormData()
  Object.entries(metadata).forEach(([k, v]) => fd.append(k, v))
  const res = await fetch(`${BASE}/api/jobs/init`, { method: 'POST', body: fd })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

const CHUNK_SIZE = 50 * 1024 * 1024 // 50 MB per chunk

export async function uploadFile(jobId, file, onProgress) {
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE)

  for (let i = 0; i < totalChunks; i++) {
    const start = i * CHUNK_SIZE
    const end = Math.min(start + CHUNK_SIZE, file.size)
    const chunk = file.slice(start, end)

    const fd = new FormData()
    fd.append('file', chunk, file.name)
    fd.append('chunk_index', i)
    fd.append('total_chunks', totalChunks)
    fd.append('filename', file.name)

    await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${BASE}/api/jobs/${jobId}/upload`)
      if (onProgress) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            const chunkProgress = (start + e.loaded) / file.size
            onProgress(chunkProgress)
          }
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

const S3_PART_SIZE = 50 * 1024 * 1024 // 50 MB per S3 multipart part

export async function uploadFileS3(jobId, file, onProgress) {
  const partCount = Math.ceil(file.size / S3_PART_SIZE)

  // Get presigned URL(s)
  const presignRes = await fetch(`${BASE}/api/jobs/${jobId}/presign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename: file.name, content_type: file.type || 'application/gzip', part_count: partCount }),
  })
  if (!presignRes.ok) throw new Error(await presignRes.text())
  const presign = await presignRes.json()

  if (presign.method === 'PUT') {
    // Single PUT upload (file < 5GB)
    await new Promise((resolve, reject) => {
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
    })

    // Register file with backend
    const regFd = new FormData()
    regFd.append('filename', file.name)
    regFd.append('size_bytes', file.size)
    await fetch(`${BASE}/api/jobs/${jobId}/presign/register`, { method: 'POST', body: regFd })

  } else {
    // Multipart upload for large files
    const parts = []
    for (let i = 0; i < presign.parts.length; i++) {
      const start = i * S3_PART_SIZE
      const end = Math.min(start + S3_PART_SIZE, file.size)
      const chunk = file.slice(start, end)
      const partInfo = presign.parts[i]

      const etag = await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open('PUT', partInfo.url)
        if (onProgress) {
          xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
              onProgress((start + e.loaded) / file.size)
            }
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

      parts.push({ part_number: partInfo.part_number, etag })
    }

    // Complete multipart upload
    await fetch(`${BASE}/api/jobs/${jobId}/presign/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ s3_key: presign.s3_key, upload_id: presign.upload_id, parts }),
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
