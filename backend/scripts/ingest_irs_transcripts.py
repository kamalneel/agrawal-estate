"""
Script to ingest IRS Wage and Income Transcripts.
Parses all transcripts in the inbox folder and populates the retirement_contributions table.
This is the AUTHORITATIVE source - it will overwrite any existing data.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from decimal import Decimal

from app.core.config import settings
from app.ingestion.parsers.irs_transcript import IRSTranscriptParser
from app.modules.income.models import RetirementContribution


def ingest_transcripts():
    """Parse and ingest all IRS transcripts. Returns overwrite report."""
    
    # Setup database connection
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Create tables if they don't exist
    from app.shared.models.base import BaseModel
    BaseModel.metadata.create_all(engine)
    
    # Find transcript files
    transcript_dir = Path(__file__).parent.parent.parent / "data" / "inbox" / "tax" / "IRS Reports - Wage and Income Transcripts"
    
    if not transcript_dir.exists():
        print(f"Transcript directory not found: {transcript_dir}")
        return [], []
    
    parser = IRSTranscriptParser()
    
    # Track results
    processed = []
    overwrites = []
    errors = []
    
    for pdf_file in sorted(transcript_dir.glob("*.pdf")):
        print(f"\nProcessing: {pdf_file.name}")
        
        if not parser.can_parse(pdf_file):
            print(f"  - Skipping: Not a recognized IRS transcript")
            continue
        
        result = parser.parse(pdf_file)
        
        if not result.success:
            print(f"  - Parse failed: {result.errors}")
            errors.append((pdf_file.name, result.errors))
            continue
        
        for record in result.records:
            data = record.data
            
            owner = data.get("owner", "Unknown")
            tax_year = data.get("tax_year")
            
            if not tax_year or owner == "Unknown":
                print(f"  - Skipping: Missing owner or tax_year")
                continue
            
            # Prepare new values
            w2_data = data.get("w2_data", [])
            new_values = {
                "contributions_401k": Decimal(str(data.get("total_401k", 0))),
                "roth_401k": Decimal(str(sum(w2.get("roth_401k", 0) for w2 in w2_data))) if w2_data else Decimal("0"),
                "ira_contributions": Decimal(str(data.get("total_ira_contributions", 0))),
                "roth_ira_contributions": Decimal(str(data.get("total_roth_ira_contributions", 0))),
                "rollover_contributions": Decimal(str(data.get("total_rollover", 0))),
                "sep_contributions": Decimal(str(data.get("total_sep_contributions", 0))),
                "simple_contributions": Decimal(str(data.get("total_simple_contributions", 0))),
                "hsa_contributions": Decimal(str(sum(w2.get("hsa_contributions", 0) for w2 in w2_data))) if w2_data else Decimal("0"),
                "ira_fmv": data.get("ira_fmv", []),
                "total_wages": Decimal(str(sum(w2.get("wages", 0) for w2 in w2_data))) if w2_data else Decimal("0"),
                "source_file": str(pdf_file.name),
            }
            
            # Check for existing record
            existing = session.query(RetirementContribution).filter_by(
                owner=owner,
                tax_year=tax_year
            ).first()
            
            if existing:
                # Track what's being overwritten
                changes = {}
                for field, new_val in new_values.items():
                    if field == "source_file" or field == "ira_fmv":
                        continue  # Don't compare these
                    
                    old_val = getattr(existing, field, None)
                    if old_val is not None and old_val != new_val:
                        if isinstance(old_val, Decimal):
                            if float(old_val) != float(new_val):
                                changes[field] = {"old": float(old_val), "new": float(new_val)}
                
                if changes:
                    overwrites.append({
                        "owner": owner,
                        "tax_year": tax_year,
                        "source_file": pdf_file.name,
                        "changes": changes
                    })
                
                # Update existing record
                for field, val in new_values.items():
                    setattr(existing, field, val)
                
                print(f"  - Updated: {owner} {tax_year}" + (f" (overwrote {len(changes)} fields)" if changes else ""))
            else:
                # Create new record
                new_record = RetirementContribution(
                    owner=owner,
                    tax_year=tax_year,
                    **new_values
                )
                session.add(new_record)
                print(f"  - Created: {owner} {tax_year}")
            
            processed.append({
                "owner": owner,
                "tax_year": tax_year,
                "401k": float(new_values["contributions_401k"]),
                "ira": float(new_values["ira_contributions"]),
                "roth_ira": float(new_values["roth_ira_contributions"]),
                "rollover": float(new_values["rollover_contributions"]),
                "wages": float(new_values["total_wages"]),
            })
    
    # Commit changes
    session.commit()
    session.close()
    
    return processed, overwrites, errors


def show_summary(processed):
    """Show summary of ingested data."""
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    print("\n" + "="*80)
    print("RETIREMENT CONTRIBUTIONS SUMMARY (FROM IRS WAGE & INCOME TRANSCRIPTS)")
    print("="*80)
    
    records = session.query(RetirementContribution).order_by(
        RetirementContribution.tax_year.desc(),
        RetirementContribution.owner
    ).all()
    
    if not records:
        print("No records found.")
        return
    
    print(f"\n{'Year':<6} {'Owner':<8} {'401(k)':<12} {'IRA':<12} {'Roth IRA':<12} {'Rollover':<12} {'Wages':<15}")
    print("-"*85)
    
    for r in records:
        print(f"{r.tax_year:<6} {r.owner:<8} ${float(r.contributions_401k):>10,.0f} ${float(r.ira_contributions):>10,.0f} ${float(r.roth_ira_contributions):>10,.0f} ${float(r.rollover_contributions):>10,.0f} ${float(r.total_wages):>13,.0f}")
    
    session.close()


def generate_overwrite_report(overwrites):
    """Generate a report of overwritten data."""
    if not overwrites:
        print("\n" + "="*80)
        print("OVERWRITE REPORT")
        print("="*80)
        print("\nNo existing data was overwritten. All records were new insertions.")
        return
    
    print("\n" + "="*80)
    print("OVERWRITE REPORT - Data that was replaced by IRS Transcript (authoritative source)")
    print("="*80)
    
    for item in overwrites:
        print(f"\n{item['owner']} {item['tax_year']} (from {item['source_file']}):")
        for field, vals in item["changes"].items():
            print(f"  - {field}: ${vals['old']:,.2f} -> ${vals['new']:,.2f}")


if __name__ == "__main__":
    print("="*80)
    print("IRS WAGE & INCOME TRANSCRIPT INGESTION")
    print("This is the AUTHORITATIVE source - existing data will be overwritten")
    print("="*80)
    
    processed, overwrites, errors = ingest_transcripts()
    
    print(f"\n{'='*60}")
    print(f"Processing complete!")
    print(f"  - Records processed: {len(processed)}")
    print(f"  - Records with overwrites: {len(overwrites)}")
    print(f"  - Errors: {len(errors)}")
    
    if errors:
        print("\nErrors:")
        for filename, error_list in errors:
            print(f"  - {filename}: {error_list}")
    
    show_summary(processed)
    generate_overwrite_report(overwrites)
