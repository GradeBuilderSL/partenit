import { NavLink, Outlet } from 'react-router-dom'
import { LayoutDashboard, Shield, FileText, Radio, Activity, PlayCircle } from 'lucide-react'
import { cn } from '../lib/utils'

const nav = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, exact: true },
  { to: '/decisions', label: 'Decisions', icon: FileText },
  { to: '/policies', label: 'Policies', icon: Shield },
  { to: '/trust', label: 'Trust Monitor', icon: Activity },
  { to: '/scenarios', label: 'Scenarios', icon: PlayCircle },
  { to: '/guard-tester', label: 'Guard Tester', icon: Radio },
]

export default function Layout() {
  return (
    <div className="flex h-screen bg-gray-950 text-gray-100">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 border-r border-gray-800 flex flex-col">
        {/* Logo */}
        <div className="px-4 py-5 border-b border-gray-800">
          <span className="text-xl font-bold tracking-tight text-white">
            <span className="text-brand-400">●</span> Partenit
          </span>
          <p className="text-xs text-gray-500 mt-0.5">Analyzer</p>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-3 space-y-1">
          {nav.map(({ to, label, icon: Icon, exact }) => (
            <NavLink
              key={to}
              to={to}
              end={exact}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors',
                  isActive
                    ? 'bg-brand-600 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-gray-800'
                )
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="p-3 border-t border-gray-800 text-xs text-gray-600">
          partenit-analyzer v0.1.0
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
