# Agrawal Estate Planner - App Goals & Architecture

This directory contains goal documentation, architecture notes, and design specifications for each application module within the Agrawal Estate Planner.

## Application Modules

### Core Financial Apps

| App | Documentation | Status | Description |
|-----|---------------|--------|-------------|
| [Dashboard](./DASHBOARD.md) | Goals & Architecture | Active | Wealth summary and overview |
| [Income](./INCOME.md) | Goals & Architecture | Active | Track salary, stock income, rental income |
| [Investments](./INVESTMENTS.md) | Goals & Architecture | Active | Portfolio tracking from multiple brokers |
| [Equity](./EQUITY.md) | Goals & Architecture | Active | Stock holdings and equity positions |
| [Real Estate](./REAL-ESTATE.md) | Goals & Architecture | Active | Property tracking and mortgages |
| [Cash & Banking](./CASH.md) | Goals & Architecture | Active | Cash accounts and banking |
| [Tax Center](./TAX-CENTER.md) | Goals & Architecture | Active | Tax records, forecasting, and document management |
| [Estate Planning](./ESTATE-PLANNING.md) | Goals & Architecture | Active | Wills, trusts, beneficiaries |
| [India Investments](./INDIA-INVESTMENTS.md) | Goals & Architecture | Active | India-specific portfolio |

### Strategy & Planning Apps

| App | Documentation | Status | Description |
|-----|---------------|--------|-------------|
| [Options Selling](./OPTIONS-SELLING.md) | Goals & Architecture | Active | Options selling strategy with ML recommendations |
| [Buy/Borrow/Die](./BUY-BORROW-DIE.md) | Goals & Architecture | Active | Wealth strategy using leverage |
| [Tax Planning](./TAX-PLANNING.md) | Goals & Architecture | Active | Tax optimization strategies |
| [Retirement Deductions](./RETIREMENT-DEDUCTIONS.md) | Goals & Architecture | Active | Retirement optimization |

### Utility Apps

| App | Documentation | Status | Description |
|-----|---------------|--------|-------------|
| [Data Ingestion](./DATA-INGESTION.md) | Goals & Architecture | Active | File upload and parsing |
| [Notifications](./NOTIFICATIONS.md) | Goals & Architecture | Active | Real-time alerts and recommendations |

## Documentation Structure

Each app documentation file follows this structure:

1. **Goal** - The primary purpose and objectives of the app
2. **Features** - Current implemented features
3. **Roadmap** - Planned features and enhancements
4. **Architecture** - Technical implementation details
5. **Data Model** - Database tables and relationships
6. **API Endpoints** - Backend REST API routes
7. **Frontend Components** - React pages and components

## Related Documentation

- [Data Architecture](../DATA_ARCHITECTURE.md) - Data integrity and deduplication
- [External Data Patterns](../EXTERNAL_DATA_PATTERNS.md) - External data integration
- [Notification System](../NOTIFICATION-SYSTEM.md) - Notification architecture
- [UI Design System](../UI_DESIGN_SYSTEM.md) - Frontend design guidelines
