# Agrawal Estate Planner

A comprehensive family estate planning and financial management application for the Agrawal family.

## Overview

This is a modular monolithic web application designed to run on your home network. It provides:

- **Dashboard**: Wealth summary and overview
- **Income Management**: Track salary, stock income, rental income, and passive income
- **Tax Center**: Property tax records with 20+ years of history
- **Investment Portfolio**: Track investments from Robinhood, Schwab, and other brokers
- **Real Estate**: Property tracking, mortgages, and equity
- **Estate Planning**: Wills, trusts, beneficiaries, and important contacts
- **Reports & Analytics**: Comprehensive financial reports

## Architecture

- **Backend**: Python 3.13 + FastAPI
- **Database**: PostgreSQL
- **Frontend**: (Coming soon)

### File-Based Data Ingestion

Instead of integrating with financial APIs, this application uses a file-based approach:

1. Download reports/exports from your financial institutions (Robinhood, Schwab, etc.)
2. Drop the files into the appropriate `data/inbox/` folder
3. The application parses and imports the data with automatic deduplication

## Directory Structure

```
agrawal-estate-planner/
├── backend/
│   ├── app/
│   │   ├── core/           # Configuration, database
│   │   ├── modules/        # Business modules
│   │   ├── ingestion/      # File processing engine
│   │   └── shared/         # Shared utilities
│   ├── migrations/         # Alembic migrations
│   └── requirements.txt
├── data/
│   ├── inbox/              # Drop files here for processing
│   │   ├── investments/
│   │   │   ├── robinhood/
│   │   │   ├── schwab/
│   │   │   └── other/
│   │   ├── income/
│   │   ├── tax/
│   │   ├── real_estate/
│   │   └── estate_planning/
│   ├── processed/          # Successfully processed files
│   ├── failed/             # Files that failed processing
│   └── documents/          # Permanent document storage
└── frontend/               # (Coming soon)
```

## Setup

### Prerequisites

- macOS with Homebrew
- Python 3.11+
- PostgreSQL 15+

### Installation

1. **Install Homebrew** (if not already installed):
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

2. **Install PostgreSQL**:
   ```bash
   brew install postgresql@15
   brew services start postgresql@15
   ```

3. **Create the database**:
   ```bash
   createdb agrawal_estate
   psql -d agrawal_estate -c "CREATE USER agrawal_user WITH PASSWORD 'agrawal_secure_2024';"
   psql -d agrawal_estate -c "GRANT ALL PRIVILEGES ON DATABASE agrawal_estate TO agrawal_user;"
   ```

4. **Set up Python environment**:
   ```bash
   cd backend
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

5. **Run database migrations**:
   ```bash
   alembic upgrade head
   ```

6. **Start the server**:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

7. **Access the application**:
   - API Documentation: http://localhost:8000/api/docs
   - Health Check: http://localhost:8000/api/health

## Usage

### Importing Data

1. Export data from your financial institution (e.g., Robinhood transaction history CSV)
2. Copy the file to the appropriate inbox folder:
   - Robinhood: `data/inbox/investments/robinhood/`
   - Schwab: `data/inbox/investments/schwab/`
   - Property taxes: `data/inbox/tax/property_tax/`
3. Trigger a scan via the API or wait for scheduled processing

### Deduplication

The system automatically handles duplicate data. If you download overlapping date ranges, only new records will be imported. This means you can safely drop cumulative exports without worrying about duplicates.

For detailed information on data management patterns, deduplication strategies, and troubleshooting, see the [Data Management Best Practices](docs/DATA_MANAGEMENT_BEST_PRACTICES.md) guide.

## API Endpoints

| Module | Endpoint | Description |
|--------|----------|-------------|
| Dashboard | `/api/v1/dashboard/summary` | Wealth summary |
| Income | `/api/v1/income/entries` | Income records |
| Tax | `/api/v1/tax/records` | Property tax records |
| Investments | `/api/v1/investments/holdings` | Current holdings |
| Real Estate | `/api/v1/real-estate/properties` | Properties |
| Estate Planning | `/api/v1/estate-planning/documents` | Estate documents |
| Ingestion | `/api/v1/ingestion/scan` | Trigger file import |

## Security

This application is designed for home network use only. It includes:

- Basic authentication
- CORS restrictions
- No external API integrations (data stays local)

## License

Private - Agrawal Family Use Only

