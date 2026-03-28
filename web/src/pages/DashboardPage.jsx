import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { listJobs } from '../api'
import { Clock, CheckCircle2, Loader2, AlertCircle, ArrowRight } from 'lucide-react'

const STATUS_STYLES = {
  running: { icon: Loader2, color: 'text-blue-600', bg: 'bg-blue-50', label: 'Running', spin: true },
  completed: { icon: CheckCircle2, color: 'text-green-600', bg: 'bg-green-50', label: 'Completed' },
  failed: { icon: AlertCircle, color: 'text-red-600', bg: 'bg-red-50', label: 'Failed' },
  pending: { icon: Clock, color: 'text-yellow-600', bg: 'bg-yellow-50', label: 'Pending' },
}

export default function DashboardPage() {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const data = await listJobs()
        setJobs(data.jobs || [])
      } catch {}
      setLoading(false)
    }
    load()
    const interval = setInterval(load, 5000)
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-brand-600" />
      </div>
    )
  }

  if (jobs.length === 0) {
    return (
      <div className="text-center py-20">
        <h2 className="text-2xl font-bold text-gray-700 mb-2">No jobs yet</h2>
        <p className="text-gray-500 mb-6">Upload your first RNA-seq dataset to get started.</p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 bg-brand-600 text-white px-6 py-3 rounded-xl font-medium hover:bg-brand-700"
        >
          Upload Data <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Pipeline Dashboard</h1>
      <div className="space-y-4">
        {jobs.map((job) => {
          const st = STATUS_STYLES[job.status] || STATUS_STYLES.pending
          const Icon = st.icon
          return (
            <Link
              key={job.job_id}
              to={`/results/${job.job_id}`}
              className="block bg-white rounded-xl border border-gray-200 shadow-sm p-5 hover:shadow-md transition"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className={`w-10 h-10 rounded-lg ${st.bg} flex items-center justify-center`}>
                    <Icon className={`w-5 h-5 ${st.color} ${st.spin ? 'animate-spin' : ''}`} />
                  </div>
                  <div>
                    <h3 className="font-semibold text-gray-900">{job.project_name || job.job_id}</h3>
                    <p className="text-sm text-gray-500">
                      {job.n_samples} samples &middot; Job {job.job_id}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-6">
                  <div className="text-right">
                    <span className={`text-sm font-medium ${st.color}`}>{st.label}</span>
                    {job.status === 'running' && (
                      <div className="w-32 bg-gray-200 rounded-full h-2 mt-1">
                        <div
                          className="bg-brand-600 h-2 rounded-full transition-all"
                          style={{ width: `${job.pct_complete || 0}%` }}
                        />
                      </div>
                    )}
                  </div>
                  <ArrowRight className="w-5 h-5 text-gray-400" />
                </div>
              </div>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
