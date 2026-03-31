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
