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
import CostBasis from './pages/CostBasis'
import TaxDocuments from './pages/TaxDocuments'
import ActualTaxFile from './pages/ActualTaxFile'
import TaxPlanning from './pages/TaxPlanning'
import OptionsSelling from './pages/OptionsSelling'
import BuyBorrowDie from './pages/BuyBorrowDie'
import Spending from './pages/Spending'
import RetirementDeductions from './pages/RetirementDeductions'
import StrategyManagement from './pages/StrategyManagement'
import LearningDashboard from './pages/LearningDashboard'
import IndiaStrategy from './pages/IndiaStrategy'
import PlaidIntegration from './pages/PlaidIntegration'
import Notifications from './pages/Notifications'
import Airbnb from './pages/Airbnb'
import CompanyDissolution from './pages/CompanyDissolution'
import { DataIngestion } from './pages/DataIngestion'

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
        <Route path="/equity/dissolution" element={<CompanyDissolution />} />
        <Route path="/real-estate" element={<RealEstate />} />
        <Route path="/cash" element={<Cash />} />
        <Route path="/tax" element={<Tax />} />
        <Route path="/tax/forms" element={<TaxForms />} />
        <Route path="/tax/cost-basis" element={<CostBasis />} />
        <Route path="/tax/documents" element={<TaxDocuments />} />
        <Route path="/tax/actual" element={<ActualTaxFile />} />

        {/* Strategies */}
        <Route path="/strategies/tax-optimization" element={<TaxPlanning />} />
        <Route path="/strategies/options-selling" element={<OptionsSelling />} />
        <Route path="/strategies/buy-borrow-die" element={<BuyBorrowDie />} />
        <Route path="/strategies/spending" element={<Spending />} />
        <Route path="/strategies/retirement-deductions" element={<RetirementDeductions />} />
        <Route path="/strategies/management" element={<StrategyManagement />} />
        <Route path="/strategies/learning" element={<LearningDashboard />} />
        <Route path="/strategies/india-investments" element={<IndiaStrategy />} />
        <Route path="/airbnb" element={<Airbnb />} />
        <Route path="/integrations/plaid" element={<PlaidIntegration />} />
        
        {/* Legacy route redirect - keep for backwards compatibility */}
        <Route path="/tax-planning" element={<TaxPlanning />} />
        
        <Route path="/data-ingestion" element={<DataIngestion />} />
      </Route>
    </Routes>
  )
}
