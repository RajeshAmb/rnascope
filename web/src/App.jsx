import { Routes, Route, Link, useLocation } from 'react-router-dom'
import UploadPage from './pages/UploadPage'
import DashboardPage from './pages/DashboardPage'
import ResultsPage from './pages/ResultsPage'
import { Dna, Upload, LayoutDashboard, BarChart3 } from 'lucide-react'

function Nav() {
  const loc = useLocation()
  const links = [
    { to: '/', label: 'Upload', icon: Upload },
    { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  ]
  return (
    <nav className="bg-white border-b border-gray-200 px-6 py-3 flex items-center gap-8 shadow-sm">
      <Link to="/" className="flex items-center gap-2 text-xl font-bold text-brand-700">
        <Dna className="w-7 h-7" />
        RNAscope
      </Link>
      <div className="flex gap-1 ml-8">
        {links.map(({ to, label, icon: Icon }) => (
          <Link
            key={to}
            to={to}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition ${
              loc.pathname === to
                ? 'bg-brand-100 text-brand-700'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </Link>
        ))}
      </div>
    </nav>
  )
}

export default function App() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Nav />
      <main className="max-w-7xl mx-auto px-6 py-8">
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/results/:jobId" element={<ResultsPage />} />
        </Routes>
      </main>
    </div>
  )
}
