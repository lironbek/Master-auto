import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './index.css'
import { AuthProvider, useAuth } from './auth'
import { WorkspaceProvider } from './workspace'
import Layout from './components/Layout'
import { Spinner } from './components/ui'
import Login from './pages/Login'
// Control center
import Overview from './pages/cc/Overview'
import CcProjects from './pages/cc/Projects'
import CcProject from './pages/cc/Project'
import Sessions from './pages/cc/Sessions'
import SessionPage from './pages/cc/Session'
import Assets from './pages/cc/Assets'
import AssetPage from './pages/cc/Asset'
import Connections from './pages/cc/Connections'
import InboxPage from './pages/cc/Inbox'
import Costs from './pages/cc/Costs'
import Usage from './pages/cc/Usage'
import Agents from './pages/cc/Agents'
import AgentRunPage from './pages/cc/AgentRun'
import Alerts from './pages/cc/Alerts'
import Workspaces from './pages/cc/Workspaces'
// Billing & service module
import BillingDashboard from './pages/billing/Dashboard'
import BlCustomers from './pages/billing/Customers'
import BlCustomer from './pages/billing/Customer'
import BlCatalog from './pages/billing/Catalog'
import BlEmployees from './pages/billing/Employees'
import BlExpenses from './pages/billing/Expenses'
import BlTickets from './pages/billing/Tickets'
import BlTicketPage from './pages/billing/Ticket'
import BlActivities from './pages/billing/Activities'
import BlCharges from './pages/billing/Charges'
import BlChargePage from './pages/billing/Charge'
import BlHoursReport from './pages/billing/HoursReport'
import BlKnowledgePage from './pages/billing/Knowledge'
import BlSettingsPage from './pages/billing/Settings'
import ExternalUpdate from './pages/public/ExternalUpdate'
// Security surveys (PT module)
import PtDashboard from './pages/pt/Dashboard'
import PtProjects from './pages/pt/Projects'
import PtProject from './pages/pt/Project'
import PtRuns from './pages/pt/Runs'
import PtRun from './pages/pt/Run'
import PtFindings from './pages/pt/Findings'
import PtFinding from './pages/pt/Finding'
import PtEvidence from './pages/pt/Evidence'
import PtReports from './pages/pt/Reports'
import PtAudit from './pages/pt/Audit'
import UsersPage from './pages/pt/Users'

function Protected() {
  const { me, loading } = useAuth()
  if (loading) return <Spinner />
  if (!me) return <Navigate to="/login" replace />
  return <WorkspaceProvider><Layout /></WorkspaceProvider>
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/u/:token" element={<ExternalUpdate />} />
      <Route element={<Protected />}>
        <Route index element={<Overview />} />
        <Route path="projects" element={<CcProjects />} />
        <Route path="projects/:id" element={<CcProject />} />
        <Route path="sessions" element={<Sessions />} />
        <Route path="sessions/:id" element={<SessionPage />} />
        <Route path="assets" element={<Assets />} />
        <Route path="assets/:id" element={<AssetPage />} />
        <Route path="connections" element={<Connections />} />
        <Route path="inbox" element={<InboxPage />} />
        <Route path="costs" element={<Costs />} />
        <Route path="usage" element={<Usage />} />
        <Route path="agents" element={<Agents />} />
        <Route path="agents/runs/:id" element={<AgentRunPage />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="users" element={<UsersPage />} />
        <Route path="workspaces" element={<Workspaces />} />
        <Route path="billing">
          <Route index element={<BillingDashboard />} />
          <Route path="customers" element={<BlCustomers />} />
          <Route path="customers/:id" element={<BlCustomer />} />
          <Route path="catalog" element={<BlCatalog />} />
          <Route path="employees" element={<BlEmployees />} />
          <Route path="expenses" element={<BlExpenses />} />
          <Route path="tickets" element={<BlTickets />} />
          <Route path="tickets/:id" element={<BlTicketPage />} />
          <Route path="activities" element={<BlActivities />} />
          <Route path="charges" element={<BlCharges />} />
          <Route path="charges/:id" element={<BlChargePage />} />
          <Route path="reports/hours" element={<BlHoursReport />} />
          <Route path="knowledge" element={<BlKnowledgePage />} />
          <Route path="settings" element={<BlSettingsPage />} />
        </Route>
        <Route path="security">
          <Route index element={<PtDashboard />} />
          <Route path="projects" element={<PtProjects />} />
          <Route path="projects/:id" element={<PtProject />} />
          <Route path="runs" element={<PtRuns />} />
          <Route path="runs/:id" element={<PtRun />} />
          <Route path="findings" element={<PtFindings />} />
          <Route path="findings/:id" element={<PtFinding />} />
          <Route path="evidence" element={<PtEvidence />} />
          <Route path="reports" element={<PtReports />} />
          <Route path="audit" element={<PtAudit />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode><BrowserRouter><AuthProvider><App /></AuthProvider></BrowserRouter></StrictMode>,
)
