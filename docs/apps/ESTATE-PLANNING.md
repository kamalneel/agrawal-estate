# Estate Planning App

## Goal

Manage estate planning documents, beneficiary designations, and wealth transfer strategies. Ensure all legal documents are current and family members are informed of the estate plan.

---

## Features

### Current Features

1. **Document Management**
   - Wills
   - Living trusts
   - Power of attorney
   - Healthcare directives
   - Insurance policies

2. **Beneficiary Tracking**
   - Account beneficiaries
   - Trust beneficiaries
   - Contingent beneficiaries

3. **Asset Distribution**
   - Planned asset allocation
   - Trust funding status
   - Probate vs non-probate assets

4. **Document Expiration**
   - Review date tracking
   - Update reminders

---

## Roadmap

- [ ] Family tree visualization
- [ ] Attorney/advisor contact management
- [ ] Estate tax projections
- [ ] Charitable giving integration
- [ ] Digital asset inventory

---

## Architecture

### Frontend
- **Page:** `/pages/EstatePlanning.tsx`
- **Route:** `/estate-planning`

### Backend
- **Module:** `/backend/app/modules/estate_planning/`

### Data Model

Key tables:
- `estate_documents` - Legal documents
- `beneficiaries` - Beneficiary records
- `trust_assets` - Trust funding records
