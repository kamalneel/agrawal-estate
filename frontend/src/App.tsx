import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ProtectedRoute } from './components/ProtectedRoute'
import { Login } from './pages/Login'
import { Dashboard } from './pages/Dashboard'
import { Income } from './pages/Income'
import { Investments } from './pages/Investments'
import { IndiaInvestments } from './pages/IndiaInvestments'
import { Equity } from './pages/Equity'
import { RealEstate } from './pages/RealEstate'
import { Cash } from './pages/Cash'
import Tax from './pages/Tax'
import TaxForms from './pages/TaxForms'
import TaxPlanning from './pages/TaxPlanning'
import OptionsSelling from './pages/OptionsSelling'
import BuyBorrowDie from './pages/BuyBorrowDie'
import RetirementDeductions from './pages/RetirementDeductions'
import StrategyManagement from './pages/StrategyManagement'
import LearningDashboard from './pages/LearningDashboard'
import PlaidIntegration from './pages/PlaidIntegration'
import Notifications from './pages/Notifications'
import { DataIngestion } from './pages/DataIngestion'
import { EstatePlanning } from './pages/EstatePlanning'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/" element={<Notifications />} />
        <Route path="/notifications" element={<Notifications />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/income" element={<Income />} />
        <Route path="/investments" element={<Investments />} />
        <Route path="/india-investments" element={<IndiaInvestments />} />
        <Route path="/equity" element={<Equity />} />
        <Route path="/real-estate" element={<RealEstate />} />
        <Route path="/cash" element={<Cash />} />
        <Route path="/tax" element={<Tax />} />
        <Route path="/tax/forms" element={<TaxForms />} />

        {/* Strategies */}
        <Route path="/strategies/tax-optimization" element={<TaxPlanning />} />
        <Route path="/strategies/options-selling" element={<OptionsSelling />} />
        <Route path="/strategies/buy-borrow-die" element={<BuyBorrowDie />} />
        <Route path="/strategies/retirement-deductions" element={<RetirementDeductions />} />
        <Route path="/strategies/management" element={<StrategyManagement />} />
        <Route path="/strategies/learning" element={<LearningDashboard />} />
        <Route path="/integrations/plaid" element={<PlaidIntegration />} />
        
        {/* Legacy route redirect - keep for backwards compatibility */}
        <Route path="/tax-planning" element={<TaxPlanning />} />
        
        <Route path="/data-ingestion" element={<DataIngestion />} />
        <Route path="/estate-planning" element={<EstatePlanning />} />
      </Route>
    </Routes>
  )
}
