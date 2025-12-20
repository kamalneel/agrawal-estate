"""
Tax Planning and Improvements module.

Analyzes tax patterns over the years and provides recommendations
for tax optimization.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from sqlalchemy.orm import Session
import json

from app.modules.tax.models import IncomeTaxReturn


class TaxPlanningRecommendation(BaseModel):
    """A single tax planning recommendation."""
    category: str
    title: str
    description: str
    potential_savings: Optional[float] = None
    priority: str = "medium"  # low, medium, high


class TaxAreaAnalysis(BaseModel):
    """Analysis for a specific tax area."""
    area: str
    display_name: str
    description: str
    yearly_data: List[Dict[str, Any]]
    average: float
    trend: str  # up, down, stable
    insights: List[str]
    recommendations: List[str]


class TaxPlanningAnalysis(BaseModel):
    """Complete tax planning analysis."""
    summary: Dict[str, Any]
    areas: List[TaxAreaAnalysis]
    recommendations: List[TaxPlanningRecommendation]


def get_tax_planning_analysis(db: Session) -> TaxPlanningAnalysis:
    """
    Analyze tax data and generate planning recommendations.
    """
    # Get all tax returns ordered by year
    returns = db.query(IncomeTaxReturn).order_by(IncomeTaxReturn.tax_year).all()
    
    if not returns:
        return TaxPlanningAnalysis(
            summary={},
            areas=[],
            recommendations=[]
        )
    
    # Parse details_json for each return
    years_data = []
    for tr in returns:
        details = {}
        if tr.details_json:
            try:
                details = json.loads(tr.details_json)
            except:
                pass
        
        years_data.append({
            "year": tr.tax_year,
            "agi": tr.agi or 0,
            "federal_tax": tr.federal_tax or 0,
            "state_tax": tr.state_tax or 0,
            "effective_rate": tr.effective_rate or 0,
            "details": details
        })
    
    # Analyze different areas
    areas = []
    recommendations = []
    
    # 1. Retirement Contributions Analysis
    retirement_area = analyze_retirement_contributions(years_data)
    if retirement_area:
        areas.append(retirement_area)
        recommendations.extend(generate_retirement_recommendations(retirement_area))
    
    # 2. Rental Income Analysis
    rental_area = analyze_rental_income(years_data)
    if rental_area:
        areas.append(rental_area)
        recommendations.extend(generate_rental_recommendations(rental_area))
    
    # 3. Charitable Contributions Analysis
    charitable_area = analyze_charitable_contributions(years_data)
    if charitable_area:
        areas.append(charitable_area)
        recommendations.extend(generate_charitable_recommendations(charitable_area))
    
    # 4. Capital Gains Analysis
    capital_gains_area = analyze_capital_gains(years_data)
    if capital_gains_area:
        areas.append(capital_gains_area)
        recommendations.extend(generate_capital_gains_recommendations(capital_gains_area))
    
    # 5. Additional Taxes (NIIT, AMT)
    additional_taxes_area = analyze_additional_taxes(years_data)
    if additional_taxes_area:
        areas.append(additional_taxes_area)
        recommendations.extend(generate_additional_taxes_recommendations(additional_taxes_area))
    
    # 6. Deductions Analysis
    deductions_area = analyze_deductions(years_data)
    if deductions_area:
        areas.append(deductions_area)
        recommendations.extend(generate_deductions_recommendations(deductions_area))
    
    # Generate summary
    total_taxes_paid = sum(yd["federal_tax"] + yd["state_tax"] for yd in years_data)
    avg_effective_rate = sum(yd["effective_rate"] for yd in years_data if yd["effective_rate"]) / len([yd for yd in years_data if yd["effective_rate"]]) if years_data else 0
    
    total_potential_savings = sum(r.potential_savings or 0 for r in recommendations)
    
    summary = {
        "years_analyzed": len(years_data),
        "total_taxes_paid": total_taxes_paid,
        "average_effective_rate": round(avg_effective_rate, 2),
        "areas_analyzed": len(areas),
        "total_recommendations": len(recommendations),
        "total_potential_savings": total_potential_savings,
    }
    
    return TaxPlanningAnalysis(
        summary=summary,
        areas=areas,
        recommendations=recommendations
    )


def analyze_retirement_contributions(years_data: List[Dict]) -> Optional[TaxAreaAnalysis]:
    """Analyze retirement contribution patterns."""
    yearly_data = []
    
    for yd in years_data:
        details = yd.get("details", {})
        
        # Look for 401k contributions in payroll or deductions
        retirement_contribution = 0
        payroll = details.get("payroll_taxes", [])
        if payroll:
            for p in payroll:
                # This is a placeholder - actual data would come from W-2 box 12
                pass
        
        # Look for IRA deductions
        deductions = details.get("deductions", {})
        ira_deduction = deductions.get("ira_deduction", 0)
        
        yearly_data.append({
            "year": yd["year"],
            "amount": retirement_contribution + ira_deduction,
            "agi": yd["agi"]
        })
    
    amounts = [y["amount"] for y in yearly_data]
    avg = sum(amounts) / len(amounts) if amounts else 0
    
    # Determine trend
    if len(amounts) >= 2:
        recent = amounts[-2:]
        older = amounts[:-2] if len(amounts) > 2 else [avg]
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older) if older else avg
        trend = "up" if recent_avg > older_avg * 1.1 else "down" if recent_avg < older_avg * 0.9 else "stable"
    else:
        trend = "stable"
    
    insights = [
        "Maximizing retirement contributions reduces taxable income",
        "Consider backdoor Roth IRA if income exceeds limits"
    ]
    
    recommendations = [
        "Max out 401(k) contributions ($23,000 for 2024)",
        "Consider catch-up contributions if over 50"
    ]
    
    return TaxAreaAnalysis(
        area="retirement",
        display_name="Retirement Contributions",
        description="Analysis of retirement account contributions and their tax impact",
        yearly_data=yearly_data,
        average=avg,
        trend=trend,
        insights=insights,
        recommendations=recommendations
    )


def analyze_rental_income(years_data: List[Dict]) -> Optional[TaxAreaAnalysis]:
    """Analyze rental income and expense patterns."""
    yearly_data = []
    has_data = False
    
    for yd in years_data:
        details = yd.get("details", {})
        rentals = details.get("rental_properties", [])
        
        total_income = 0
        total_expenses = 0
        total_depreciation = 0
        
        for rental in rentals:
            total_income += rental.get("income", 0)
            total_expenses += rental.get("expenses", 0)
            total_depreciation += rental.get("depreciation", 0)
            has_data = True
        
        net = total_income - total_expenses - total_depreciation
        yearly_data.append({
            "year": yd["year"],
            "income": total_income,
            "expenses": total_expenses,
            "depreciation": total_depreciation,
            "net": net
        })
    
    if not has_data:
        return None
    
    nets = [y["net"] for y in yearly_data]
    avg = sum(nets) / len(nets) if nets else 0
    
    # Trend analysis
    if len(nets) >= 2:
        recent = nets[-2:]
        older = nets[:-2] if len(nets) > 2 else [avg]
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older) if older else avg
        trend = "up" if recent_avg > older_avg * 1.1 else "down" if recent_avg < older_avg * 0.9 else "stable"
    else:
        trend = "stable"
    
    # Check for expense consistency
    expense_rates = []
    for y in yearly_data:
        if y["income"] > 0:
            expense_rates.append(y["expenses"] / y["income"])
    
    insights = []
    if expense_rates:
        avg_rate = sum(expense_rates) / len(expense_rates)
        min_rate = min(expense_rates)
        max_rate = max(expense_rates)
        if max_rate - min_rate > 0.2:
            insights.append(f"Expense ratios vary significantly ({min_rate:.0%} to {max_rate:.0%})")
    
    insights.append("Ensure all deductible expenses are being captured")
    
    recommendations = [
        "Review depreciation schedules for accuracy",
        "Consider cost segregation study for accelerated depreciation"
    ]
    
    return TaxAreaAnalysis(
        area="rental",
        display_name="Rental Property Income",
        description="Analysis of rental property income, expenses, and tax implications",
        yearly_data=yearly_data,
        average=avg,
        trend=trend,
        insights=insights,
        recommendations=recommendations
    )


def analyze_charitable_contributions(years_data: List[Dict]) -> Optional[TaxAreaAnalysis]:
    """Analyze charitable contribution patterns."""
    yearly_data = []
    has_data = False
    
    for yd in years_data:
        details = yd.get("details", {})
        deductions = details.get("deductions", {})
        
        charitable = deductions.get("charitable", 0)
        if charitable > 0:
            has_data = True
        
        yearly_data.append({
            "year": yd["year"],
            "amount": charitable,
            "agi": yd["agi"],
            "percent_of_agi": (charitable / yd["agi"] * 100) if yd["agi"] > 0 else 0
        })
    
    amounts = [y["amount"] for y in yearly_data]
    avg = sum(amounts) / len(amounts) if amounts else 0
    
    # Trend
    if len(amounts) >= 2:
        recent = amounts[-2:]
        older = amounts[:-2] if len(amounts) > 2 else [avg]
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older) if older else avg
        trend = "up" if recent_avg > older_avg * 1.1 else "down" if recent_avg < older_avg * 0.9 else "stable"
    else:
        trend = "stable"
    
    insights = []
    
    # Check for years with no contributions
    zero_years = [y for y in yearly_data if y["amount"] == 0]
    if zero_years and has_data:
        insights.append(f"No charitable deductions in {len(zero_years)} years")
    
    # Check percent of AGI consistency
    percents = [y["percent_of_agi"] for y in yearly_data if y["percent_of_agi"] > 0]
    if percents:
        avg_pct = sum(percents) / len(percents)
        insights.append(f"Average charitable giving: {avg_pct:.1f}% of AGI")
    
    recommendations = [
        "Consider bunching donations in alternating years for itemizing",
        "Donate appreciated securities instead of cash for additional tax benefit",
        "Consider donor-advised fund for flexibility"
    ]
    
    return TaxAreaAnalysis(
        area="charitable",
        display_name="Charitable Contributions",
        description="Analysis of charitable giving patterns and tax deductions",
        yearly_data=yearly_data,
        average=avg,
        trend=trend,
        insights=insights,
        recommendations=recommendations
    )


def analyze_capital_gains(years_data: List[Dict]) -> Optional[TaxAreaAnalysis]:
    """Analyze capital gains and losses patterns."""
    yearly_data = []
    has_data = False
    
    for yd in years_data:
        details = yd.get("details", {})
        capital = details.get("capital_gains", {})
        
        short_term = capital.get("short_term", 0)
        long_term = capital.get("long_term", 0)
        carryover = capital.get("loss_carryover", 0)
        
        if short_term != 0 or long_term != 0 or carryover != 0:
            has_data = True
        
        yearly_data.append({
            "year": yd["year"],
            "short_term": short_term,
            "long_term": long_term,
            "loss_carryover": carryover,
            "net": short_term + long_term
        })
    
    if not has_data:
        # Still return the area with zero data
        pass
    
    nets = [y["net"] for y in yearly_data]
    avg = sum(nets) / len(nets) if nets else 0
    
    # Trend
    if len(nets) >= 2:
        recent = nets[-2:]
        older = nets[:-2] if len(nets) > 2 else [avg]
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older) if older else avg
        trend = "up" if recent_avg > older_avg * 1.1 else "down" if recent_avg < older_avg * 0.9 else "stable"
    else:
        trend = "stable"
    
    insights = []
    
    # Check for heavy short-term gains
    for y in yearly_data:
        if y["short_term"] > 50000:
            insights.append(f"{y['year']}: High short-term gains (${y['short_term']:,.0f}) taxed at ordinary rates")
            break
    
    # Check for loss carryovers
    carryovers = [y for y in yearly_data if y["loss_carryover"] > 0]
    if carryovers:
        insights.append("Loss carryover available - consider harvesting gains")
    
    recommendations = [
        "Hold investments >1 year for long-term capital gains rates",
        "Consider tax-loss harvesting at year end",
        "Review ESPP/RSU sales timing for tax efficiency"
    ]
    
    return TaxAreaAnalysis(
        area="capital_gains",
        display_name="Capital Gains & Losses",
        description="Analysis of investment gains, losses, and tax treatment",
        yearly_data=yearly_data,
        average=avg,
        trend=trend,
        insights=insights,
        recommendations=recommendations
    )


def analyze_additional_taxes(years_data: List[Dict]) -> Optional[TaxAreaAnalysis]:
    """Analyze additional taxes like NIIT, AMT, etc."""
    yearly_data = []
    has_data = False
    
    for yd in years_data:
        details = yd.get("details", {})
        additional = details.get("additional_taxes", {})
        
        niit = additional.get("niit", 0)
        amt = additional.get("amt", 0)
        se_tax = additional.get("self_employment", 0)
        
        if niit > 0 or amt > 0 or se_tax > 0:
            has_data = True
        
        total = niit + amt + se_tax
        yearly_data.append({
            "year": yd["year"],
            "niit": niit,
            "amt": amt,
            "self_employment": se_tax,
            "total": total
        })
    
    totals = [y["total"] for y in yearly_data]
    avg = sum(totals) / len(totals) if totals else 0
    
    # Trend
    if len(totals) >= 2:
        recent = totals[-2:]
        older = totals[:-2] if len(totals) > 2 else [avg]
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older) if older else avg
        trend = "up" if recent_avg > older_avg * 1.1 else "down" if recent_avg < older_avg * 0.9 else "stable"
    else:
        trend = "stable"
    
    insights = []
    
    # Check NIIT exposure
    niit_years = [y for y in yearly_data if y["niit"] > 0]
    if niit_years:
        total_niit = sum(y["niit"] for y in niit_years)
        insights.append(f"NIIT exposure in {len(niit_years)} years (total: ${total_niit:,.0f})")
    
    recommendations = [
        "Consider tax-exempt municipal bonds to reduce investment income",
        "Real estate professional status may help avoid NIIT on rental income",
        "Review AMT projections before exercising ISOs"
    ]
    
    return TaxAreaAnalysis(
        area="additional_taxes",
        display_name="Additional Taxes",
        description="Analysis of NIIT, AMT, and other additional taxes",
        yearly_data=yearly_data,
        average=avg,
        trend=trend,
        insights=insights,
        recommendations=recommendations
    )


def analyze_deductions(years_data: List[Dict]) -> Optional[TaxAreaAnalysis]:
    """Analyze deduction patterns and itemizing vs standard."""
    yearly_data = []
    
    # Standard deduction amounts by year (married filing jointly)
    standard_deductions = {
        2024: 29200, 2023: 27700, 2022: 25900, 2021: 25100,
        2020: 24800, 2019: 24400, 2018: 24000, 2017: 12700,
        2016: 12600, 2015: 12600, 2014: 12400, 2013: 12200,
        2012: 11900, 2011: 11600, 2010: 11400
    }
    
    for yd in years_data:
        details = yd.get("details", {})
        deductions = details.get("deductions", {})
        
        itemized = deductions.get("itemized_total", 0)
        mortgage_interest = deductions.get("mortgage_interest", 0)
        salt = deductions.get("salt", 0)
        charitable = deductions.get("charitable", 0)
        
        std = standard_deductions.get(yd["year"], 25000)
        
        yearly_data.append({
            "year": yd["year"],
            "itemized_total": itemized,
            "standard": std,
            "mortgage_interest": mortgage_interest,
            "salt": salt,
            "charitable": charitable,
            "method": "itemized" if itemized > std else "standard"
        })
    
    itemized_totals = [y["itemized_total"] for y in yearly_data]
    avg = sum(itemized_totals) / len(itemized_totals) if itemized_totals else 0
    
    # Trend
    if len(itemized_totals) >= 2:
        recent = itemized_totals[-2:]
        older = itemized_totals[:-2] if len(itemized_totals) > 2 else [avg]
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older) if older else avg
        trend = "up" if recent_avg > older_avg * 1.1 else "down" if recent_avg < older_avg * 0.9 else "stable"
    else:
        trend = "stable"
    
    insights = []
    
    # Check itemizing vs standard
    itemized_years = [y for y in yearly_data if y["method"] == "itemized"]
    standard_years = [y for y in yearly_data if y["method"] == "standard"]
    
    if itemized_years and standard_years:
        insights.append(f"Itemized in {len(itemized_years)} years, standard in {len(standard_years)} years")
    
    # SALT cap impact (post-2017)
    for y in yearly_data:
        if y["year"] >= 2018 and y["salt"] >= 10000:
            insights.append(f"{y['year']}: SALT capped at $10,000 (actual: ${y['salt']:,.0f})")
            break
    
    recommendations = [
        "Consider bunching deductions in alternating years",
        "Prepay property taxes or make January mortgage payment in December",
        "Review timing of large charitable donations"
    ]
    
    return TaxAreaAnalysis(
        area="deductions",
        display_name="Deductions Strategy",
        description="Analysis of itemized vs standard deductions",
        yearly_data=yearly_data,
        average=avg,
        trend=trend,
        insights=insights,
        recommendations=recommendations
    )


def generate_retirement_recommendations(area: TaxAreaAnalysis) -> List[TaxPlanningRecommendation]:
    """Generate specific recommendations for retirement."""
    recommendations = []
    
    recommendations.append(TaxPlanningRecommendation(
        category="retirement",
        title="Maximize 401(k) Contributions",
        description="Contributing the maximum $23,000 (2024) reduces taxable income and grows tax-deferred",
        potential_savings=8000,  # Estimated based on marginal rate
        priority="high"
    ))
    
    return recommendations


def generate_rental_recommendations(area: TaxAreaAnalysis) -> List[TaxPlanningRecommendation]:
    """Generate specific recommendations for rental properties."""
    recommendations = []
    
    # Check if depreciation is being maximized
    for yd in area.yearly_data:
        if yd.get("income", 0) > 0 and yd.get("depreciation", 0) == 0:
            recommendations.append(TaxPlanningRecommendation(
                category="rental",
                title="Review Depreciation Deductions",
                description="Ensure all rental properties have proper depreciation schedules",
                potential_savings=5000,
                priority="high"
            ))
            break
    
    return recommendations


def generate_charitable_recommendations(area: TaxAreaAnalysis) -> List[TaxPlanningRecommendation]:
    """Generate specific recommendations for charitable giving."""
    recommendations = []
    
    # Check for inconsistent giving
    amounts = [y["amount"] for y in area.yearly_data]
    if amounts:
        max_amt = max(amounts)
        min_amt = min(amounts)
        if max_amt > 0 and min_amt == 0:
            recommendations.append(TaxPlanningRecommendation(
                category="charitable",
                title="Consider Bunching Strategy",
                description="Combine multiple years of donations to exceed standard deduction threshold",
                potential_savings=2000,
                priority="medium"
            ))
    
    return recommendations


def generate_capital_gains_recommendations(area: TaxAreaAnalysis) -> List[TaxPlanningRecommendation]:
    """Generate specific recommendations for capital gains."""
    recommendations = []
    
    # Check for short-term gains
    for yd in area.yearly_data:
        if yd.get("short_term", 0) > 20000:
            recommendations.append(TaxPlanningRecommendation(
                category="capital_gains",
                title="Hold Investments Longer",
                description="Converting short-term to long-term gains can save up to 20% in taxes",
                potential_savings=yd["short_term"] * 0.15,
                priority="high"
            ))
            break
    
    return recommendations


def generate_additional_taxes_recommendations(area: TaxAreaAnalysis) -> List[TaxPlanningRecommendation]:
    """Generate specific recommendations for additional taxes."""
    recommendations = []
    
    # Check NIIT exposure
    niit_total = sum(y.get("niit", 0) for y in area.yearly_data)
    if niit_total > 0:
        recommendations.append(TaxPlanningRecommendation(
            category="additional_taxes",
            title="Reduce NIIT Exposure",
            description="Consider tax-exempt investments or rental real estate with professional status",
            potential_savings=niit_total * 0.5,  # Potential to reduce by half
            priority="medium"
        ))
    
    return recommendations


def generate_deductions_recommendations(area: TaxAreaAnalysis) -> List[TaxPlanningRecommendation]:
    """Generate specific recommendations for deductions."""
    recommendations = []
    
    # Check if consistently below itemizing threshold
    standard_years = [y for y in area.yearly_data if y["method"] == "standard"]
    if len(standard_years) > 2:
        recommendations.append(TaxPlanningRecommendation(
            category="deductions",
            title="Deduction Bunching Strategy",
            description="Alternate between itemizing and standard deduction by bunching expenses",
            potential_savings=3000,
            priority="medium"
        ))
    
    return recommendations



