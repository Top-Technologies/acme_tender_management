# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class TenderAssessment(models.Model):
    _name = 'tender.assessment'
    _description = 'Tender Requirement Assessment Line'
    _order = 'is_mandatory desc, id asc'

    tender_id = fields.Many2one(
        'crm.lead',
        string="Tender",
        required=True,
        ondelete='cascade',
        index=True
    )
    category = fields.Selection([
        ('scope', 'Scope of Work'),
        ('eligibility', 'Eligibility & Legal'),
        ('technical', 'Technical Specifications'),
        ('commercial', 'Commercial & Payment Terms'),
        ('evaluation_criteria', 'Evaluation Criteria'),
        ('submission_document', 'Submission Documents'),
        ('date', 'Key Deadlines'),
        ('security', 'Bid / Performance Security'),
        ('risk', 'Identified Risks & Liabilities'),
    ], string="Category", required=True, default='technical')

    requirement = fields.Text(string="Requirement / Clause Description", required=True)
    source_page_clause = fields.Char(string="Source Page / Clause")
    is_mandatory = fields.Boolean(string="Mandatory", default=True)

    assessment = fields.Selection([
        ('meets', 'Meets Fully'),
        ('partly_meets', 'Partly Meets'),
        ('does_not_meet', 'Does Not Meet'),
    ], string="Assessment", default='meets', required=True)

    failure_type = fields.Selection([
        ('none', 'None'),
        ('mandatory_failure', 'Mandatory Failure'),
        ('manageable_risk', 'Manageable Risk'),
    ], string="Failure Type", default='none')

    evidence = fields.Text(string="Evidence / Reference")
    attachment_id = fields.Many2one('ir.attachment', string="Attached Evidence")
    gap = fields.Text(string="Identified Gap")
    owner_id = fields.Many2one('res.users', string="Action Owner", default=lambda self: self.env.user)
    action = fields.Text(string="Mitigation Action")

    status = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('cleared', 'Cleared / Compliant'),
        ('failed', 'Disqualifying Failure'),
    ], string="Status", default='draft', required=True)

    @api.onchange('assessment', 'is_mandatory')
    def _onchange_assessment(self):
        if self.assessment == 'does_not_meet':
            if self.is_mandatory:
                self.failure_type = 'mandatory_failure'
                self.status = 'failed'
            else:
                self.failure_type = 'manageable_risk'
                self.status = 'in_progress'
        elif self.assessment == 'partly_meets':
            self.failure_type = 'manageable_risk'
            self.status = 'in_progress'
        else:
            self.failure_type = 'none'
            self.status = 'cleared'

