import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Decisions from './pages/Decisions'
import Policies from './pages/Policies'
import TrustMonitor from './pages/TrustMonitor'
import GuardTester from './pages/GuardTester'
import Scenarios from './pages/Scenarios'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="decisions" element={<Decisions />} />
          <Route path="policies" element={<Policies />} />
          <Route path="trust" element={<TrustMonitor />} />
          <Route path="guard-tester" element={<GuardTester />} />
          <Route path="scenarios" element={<Scenarios />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
