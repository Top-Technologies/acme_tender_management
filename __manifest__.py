# -*- coding: utf-8 -*-
{
    'name': 'ACME Tender Management',
    'version': '19.0.1.6.0',
    'category': 'Sales/CRM',
    'summary': 'Deadline-driven tender pipeline, BOQ cost build-up, bid security recovery and document library.',
    'description': """
ACME Tender Management Module (Odoo 19)
=======================================
Built strictly according to ACME To-Be blueprint (Section 6) and As-Is Tender Management SOP.

Key Features:
- Dedicated Tender Pipeline (stages: Identified, Registered, Bid/No-Bid, Preparation, Bid security issued, Submitted, Under evaluation, Won / Lost).
- Standard CRM opportunities remain completely untouched; tender fields appear only on tenders.
- One unique lifecycle code across opportunity, order, project, and analytic accounts.
- Requirement Assessment and Go/No-Go Decision records with conditional task generation.
- Standard 24-document submission checklist generator integrated with Tender Library.
- BOQ Cost Build-up with single-margin markup, component line roll-ups, and completeness check.
- Bid Security request, CPO / Bank Guarantee approvals, and Office Manager recovery tracking.
- Technical & Financial Bid Opening records and Win/Loss outcome analysis.
- Stage gate controls, automated deadline reminders, library validity warnings, and Start-from-Earlier-Tender wizard.
- Executive Reports: R-08 Pipeline Performance, R-09 Open Bid Security Recovery, R-10 Win/Loss Analysis.
    """,
    'author': 'ACME Engineering and Trading / Odoo Developer',
    'website': 'https://www.acme-engineering.com',
    'depends': [
        'base',
        'mail',
        'crm',
        'sale',
        'sale_management',
        'purchase',
        'stock',
        'account',
        'documents',
        'approvals',
    ],
    'assets': {
        'web.assets_backend': [
            'acme_tender_management/static/src/scss/tender_summary.scss',
        ],
    },
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_sequence_data.xml',
        'data/crm_stage_data.xml',
        'data/approval_category_data.xml',
        'data/approval_category_limits.xml',
        'data/documents_data.xml',
        'data/cron_data.xml',
        'wizard/tender_copy_wizard_views.xml',
        'wizard/tender_boq_import_wizard_views.xml',
        'views/crm_lead_views.xml',
        'views/crm_stage_views.xml',
        'views/tender_assessment_views.xml',
        'views/tender_decision_views.xml',
        'views/tender_checklist_views.xml',
        'views/tender_costline_views.xml',
        'views/sale_order_views.xml',
        'views/tender_opening_views.xml',
        'views/tender_outcome_views.xml',
        'views/res_partner_views.xml',
        'views/res_company_views.xml',
        'views/tender_report_views.xml',
        'views/tender_menu.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}

