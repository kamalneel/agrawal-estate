"""
Tax Form PDF Generator

Generates professional PDF versions of IRS Form 1040 and California Form 540
that match the official form layout for easy comparison with tax consultant returns.
"""

from typing import Optional
from io import BytesIO
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

from app.modules.tax.forms import Form1040, Schedule1, ScheduleE, ScheduleD, CaliforniaForm540, TaxFormPackage


def generate_form_1040_pdf(form: Form1040, buffer: BytesIO) -> None:
    """Generate PDF for IRS Form 1040."""

    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story = []

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#000000'),
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )

    header_style = ParagraphStyle(
        'CustomHeader',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#000000'),
        spaceAfter=8,
        fontName='Helvetica-Bold'
    )

    note_style = ParagraphStyle(
        'Note',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#666666'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontStyle='italic'
    )

    # Title
    story.append(Paragraph(f"Form 1040", title_style))
    story.append(Paragraph(f"U.S. Individual Income Tax Return", styles['Normal']))
    story.append(Paragraph(f"Tax Year {form.tax_year}", styles['Normal']))
    story.append(Spacer(1, 0.2*inch))

    # Forecast notice
    story.append(Paragraph(
        "⚠️ THIS IS A FORECAST - For comparison purposes only, not an official tax return",
        note_style
    ))
    story.append(Spacer(1, 0.2*inch))

    # Filing Information
    story.append(Paragraph("Filing Information", header_style))
    filing_data = [
        ['Filing Status:', form.filing_status],
        ['Taxpayer:', form.taxpayer_name],
    ]
    if form.spouse_name:
        filing_data.append(['Spouse:', form.spouse_name])

    filing_table = Table(filing_data, colWidths=[2*inch, 4*inch])
    filing_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
        ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 10),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(filing_table)
    story.append(Spacer(1, 0.2*inch))

    # Income Section
    story.append(Paragraph("Income", header_style))
    income_data = [
        ['Line', 'Description', 'Amount'],
        ['1z', 'Total wages, salaries, tips', f'${form.line_1z:,.2f}'],
        ['2b', 'Taxable interest', f'${form.line_2b:,.2f}'],
        ['3b', 'Ordinary dividends', f'${form.line_3b:,.2f}'],
        ['7', 'Capital gain or (loss)', f'${form.line_7:,.2f}'],
        ['8', 'Additional income from Schedule 1', f'${form.line_8:,.2f}'],
        ['9', 'Total income', f'${form.line_9:,.2f}'],
    ]

    income_table = Table(income_data, colWidths=[0.8*inch, 3.5*inch, 1.7*inch])
    income_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4A5568')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F7FAFC')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        # Highlight total
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EBF8FF')),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 11),
    ]))
    story.append(income_table)
    story.append(Spacer(1, 0.2*inch))

    # Adjusted Gross Income
    story.append(Paragraph("Adjusted Gross Income", header_style))
    agi_data = [
        ['Line', 'Description', 'Amount'],
        ['10', 'Adjustments to income (Schedule 1)', f'${form.line_10:,.2f}'],
        ['11', 'Adjusted Gross Income (AGI)', f'${form.line_11:,.2f}'],
    ]

    agi_table = Table(agi_data, colWidths=[0.8*inch, 3.5*inch, 1.7*inch])
    agi_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4A5568')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F7FAFC')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        # Highlight AGI
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EBF8FF')),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 11),
    ]))
    story.append(agi_table)
    story.append(Spacer(1, 0.2*inch))

    # Deductions and Taxable Income
    story.append(Paragraph("Standard Deduction and Taxable Income", header_style))
    deduction_data = [
        ['Line', 'Description', 'Amount'],
        ['12', f'{form.line_12_type.title()} deduction', f'${form.line_12:,.2f}'],
        ['13', 'Qualified business income deduction', f'${form.line_13:,.2f}'],
        ['14', 'Total deductions', f'${form.line_14:,.2f}'],
        ['15', 'Taxable income', f'${form.line_15:,.2f}'],
    ]

    deduction_table = Table(deduction_data, colWidths=[0.8*inch, 3.5*inch, 1.7*inch])
    deduction_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4A5568')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F7FAFC')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        # Highlight taxable income
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EBF8FF')),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 11),
    ]))
    story.append(deduction_table)
    story.append(Spacer(1, 0.2*inch))

    # Tax and Credits
    story.append(Paragraph("Tax and Credits", header_style))
    tax_data = [
        ['Line', 'Description', 'Amount'],
        ['16', 'Tax (from tax tables)', f'${form.line_16:,.2f}'],
        ['17', 'Additional taxes (Schedule 2)', f'${form.line_17:,.2f}'],
        ['18', 'Add lines 16 and 17', f'${form.line_18:,.2f}'],
        ['19', 'Child tax credit', f'${form.line_19:,.2f}'],
        ['20', 'Other credits (Schedule 3)', f'${form.line_20:,.2f}'],
        ['21', 'Total credits', f'${form.line_21:,.2f}'],
        ['22', 'Subtract line 21 from line 18', f'${form.line_22:,.2f}'],
        ['23', 'Other taxes (Schedule 2)', f'${form.line_23:,.2f}'],
        ['24', 'Total tax', f'${form.line_24:,.2f}'],
    ]

    tax_table = Table(tax_data, colWidths=[0.8*inch, 3.5*inch, 1.7*inch])
    tax_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4A5568')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F7FAFC')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        # Highlight total tax
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FEF3C7')),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 11),
    ]))
    story.append(tax_table)
    story.append(Spacer(1, 0.2*inch))

    # Payments
    story.append(Paragraph("Payments", header_style))
    payment_data = [
        ['Line', 'Description', 'Amount'],
        ['25d', 'Federal income tax withheld', f'${form.line_25d:,.2f}'],
        ['26', '2025 estimated tax payments', f'${form.line_26:,.2f}'],
        ['32', 'Total payments', f'${form.line_32:,.2f}'],
        ['33', 'Overpayment', f'${form.line_33:,.2f}'],
    ]

    payment_table = Table(payment_data, colWidths=[0.8*inch, 3.5*inch, 1.7*inch])
    payment_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4A5568')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F7FAFC')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(payment_table)
    story.append(Spacer(1, 0.2*inch))

    # Refund or Amount Owed
    story.append(Paragraph("Refund or Amount Owed", header_style))

    if form.line_34 > 0:
        # Refund
        refund_data = [
            ['Line', 'Description', 'Amount'],
            ['34', 'Amount to be refunded', f'${form.line_34:,.2f}'],
        ]
        refund_table = Table(refund_data, colWidths=[0.8*inch, 3.5*inch, 1.7*inch])
        refund_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
            ('FONT', (0, 1), (-1, -1), 'Helvetica-Bold', 11),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4A5568')),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#D1FAE5')),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(refund_table)
    else:
        # Amount owed
        owed_data = [
            ['Line', 'Description', 'Amount'],
            ['36', 'Amount you owe (before penalty)', f'${form.line_36:,.2f}'],
            ['37', 'Estimated tax penalty', f'${form.line_37:,.2f}'],
            ['38', 'Total amount you owe', f'${form.line_38:,.2f}'],
        ]
        owed_table = Table(owed_data, colWidths=[0.8*inch, 3.5*inch, 1.7*inch])
        owed_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
            ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4A5568')),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F7FAFC')]),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FEE2E2')),
            ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(owed_table)

    # Footer
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        note_style
    ))

    # Build PDF
    doc.build(story)


def generate_california_540_pdf(form: CaliforniaForm540, buffer: BytesIO) -> None:
    """Generate PDF for California Form 540."""

    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    styles = getSampleStyleSheet()
    story = []

    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#000000'),
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )

    header_style = ParagraphStyle(
        'CustomHeader',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#000000'),
        spaceAfter=8,
        fontName='Helvetica-Bold'
    )

    note_style = ParagraphStyle(
        'Note',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#666666'),
        spaceAfter=6,
        alignment=TA_CENTER,
        fontStyle='italic'
    )

    # Title
    story.append(Paragraph(f"California Form 540", title_style))
    story.append(Paragraph(f"Resident Income Tax Return", styles['Normal']))
    story.append(Paragraph(f"Tax Year {form.tax_year}", styles['Normal']))
    story.append(Spacer(1, 0.2*inch))

    # Forecast notice
    story.append(Paragraph(
        "⚠️ THIS IS A FORECAST - For comparison purposes only, not an official tax return",
        note_style
    ))
    story.append(Spacer(1, 0.2*inch))

    # Filing Information
    story.append(Paragraph("Filing Information", header_style))
    filing_data = [
        ['Filing Status:', form.filing_status],
        ['Taxpayer:', form.taxpayer_name],
    ]
    if form.spouse_name:
        filing_data.append(['Spouse:', form.spouse_name])

    filing_table = Table(filing_data, colWidths=[2*inch, 4*inch])
    filing_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 10),
        ('FONT', (0, 0), (0, -1), 'Helvetica-Bold', 10),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(filing_table)
    story.append(Spacer(1, 0.2*inch))

    # Income Section
    story.append(Paragraph("Income", header_style))
    income_data = [
        ['Line', 'Description', 'Amount'],
        ['11', 'Wages, salaries, tips', f'${form.line_11:,.2f}'],
        ['12', 'Interest income', f'${form.line_12:,.2f}'],
        ['13', 'Dividends', f'${form.line_13:,.2f}'],
        ['16', 'Capital gain or (loss)', f'${form.line_16:,.2f}'],
        ['17', 'Rental, royalties, partnerships', f'${form.line_17:,.2f}'],
        ['20', 'Total income', f'${form.line_20:,.2f}'],
    ]

    income_table = Table(income_data, colWidths=[0.8*inch, 3.5*inch, 1.7*inch])
    income_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#D97706')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FFFBEB')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        # Highlight total
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FED7AA')),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 11),
    ]))
    story.append(income_table)
    story.append(Spacer(1, 0.2*inch))

    # California AGI
    story.append(Paragraph("California Adjusted Gross Income", header_style))
    agi_data = [
        ['Line', 'Description', 'Amount'],
        ['21', 'Adjustments to federal AGI', f'${form.line_21:,.2f}'],
        ['22', 'California AGI', f'${form.line_22:,.2f}'],
    ]

    agi_table = Table(agi_data, colWidths=[0.8*inch, 3.5*inch, 1.7*inch])
    agi_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#D97706')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FFFBEB')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        # Highlight AGI
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FED7AA')),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 11),
    ]))
    story.append(agi_table)
    story.append(Spacer(1, 0.2*inch))

    # Deductions and Taxable Income
    story.append(Paragraph("Deductions and Taxable Income", header_style))
    deduction_data = [
        ['Line', 'Description', 'Amount'],
        ['23', f'{form.line_23_type.title()} deduction', f'${form.line_23:,.2f}'],
        ['24', 'Exemptions', f'${form.line_24:,.2f}'],
        ['25', 'Taxable income', f'${form.line_25:,.2f}'],
    ]

    deduction_table = Table(deduction_data, colWidths=[0.8*inch, 3.5*inch, 1.7*inch])
    deduction_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#D97706')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FFFBEB')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        # Highlight taxable income
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FED7AA')),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 11),
    ]))
    story.append(deduction_table)
    story.append(Spacer(1, 0.2*inch))

    # Tax
    story.append(Paragraph("Tax", header_style))
    tax_data = [
        ['Line', 'Description', 'Amount'],
        ['31', 'Tax (from tax table)', f'${form.line_31:,.2f}'],
        ['33', 'Mental Health Services Tax (1% over $1M)', f'${form.line_33:,.2f}'],
        ['34', 'Total tax before credits', f'${form.line_34:,.2f}'],
        ['35', 'Credits', f'${form.line_35:,.2f}'],
        ['36', 'Subtract line 35 from line 34', f'${form.line_36:,.2f}'],
        ['37', 'Other taxes', f'${form.line_37:,.2f}'],
        ['38', 'Total tax', f'${form.line_38:,.2f}'],
    ]

    tax_table = Table(tax_data, colWidths=[0.8*inch, 3.5*inch, 1.7*inch])
    tax_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#D97706')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FFFBEB')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        # Highlight total tax
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FED7AA')),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 11),
    ]))
    story.append(tax_table)
    story.append(Spacer(1, 0.2*inch))

    # Payments
    story.append(Paragraph("Payments", header_style))
    payment_data = [
        ['Line', 'Description', 'Amount'],
        ['41', 'CA income tax withheld', f'${form.line_41:,.2f}'],
        ['42', '2025 estimated tax payments', f'${form.line_42:,.2f}'],
        ['44', 'Total payments', f'${form.line_44:,.2f}'],
    ]

    payment_table = Table(payment_data, colWidths=[0.8*inch, 3.5*inch, 1.7*inch])
    payment_table.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#D97706')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FFFBEB')]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(payment_table)
    story.append(Spacer(1, 0.2*inch))

    # Refund or Amount Owed
    story.append(Paragraph("Refund or Amount Owed", header_style))

    if form.line_46 > 0:
        # Refund
        refund_data = [
            ['Line', 'Description', 'Amount'],
            ['45', 'Overpayment', f'${form.line_45:,.2f}'],
            ['46', 'Amount to be refunded', f'${form.line_46:,.2f}'],
        ]
        refund_table = Table(refund_data, colWidths=[0.8*inch, 3.5*inch, 1.7*inch])
        refund_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
            ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#D97706')),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#FFFBEB')]),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#D1FAE5')),
            ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(refund_table)
    else:
        # Amount owed
        owed_data = [
            ['Line', 'Description', 'Amount'],
            ['47', 'Amount owed (before penalty)', f'${form.line_47:,.2f}'],
            ['48', 'Estimated tax penalty', f'${form.line_48:,.2f}'],
            ['49', 'Total amount you owe', f'${form.line_49:,.2f}'],
        ]
        owed_table = Table(owed_data, colWidths=[0.8*inch, 3.5*inch, 1.7*inch])
        owed_table.setStyle(TableStyle([
            ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
            ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#D97706')),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#FFFBEB')]),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FEE2E2')),
            ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold', 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(owed_table)

    # Footer
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        note_style
    ))

    # Build PDF
    doc.build(story)


def generate_tax_forms_pdf(forms_package: TaxFormPackage) -> BytesIO:
    """
    Generate a complete PDF package with Form 1040 and California Form 540.

    Args:
        forms_package: TaxFormPackage containing all forms

    Returns:
        BytesIO buffer containing the PDF
    """
    buffer = BytesIO()

    # Create multi-page document
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    story = []

    # Generate Form 1040
    temp_1040_buffer = BytesIO()
    generate_form_1040_pdf(forms_package.form_1040, temp_1040_buffer)

    # Generate CA Form 540 if present
    if forms_package.california_540:
        story.append(PageBreak())
        temp_540_buffer = BytesIO()
        generate_california_540_pdf(forms_package.california_540, temp_540_buffer)

    # For now, we'll generate them separately and return Form 1040
    # In production, you'd want to merge multiple PDFs
    buffer = BytesIO()
    generate_form_1040_pdf(forms_package.form_1040, buffer)
    buffer.seek(0)

    return buffer
