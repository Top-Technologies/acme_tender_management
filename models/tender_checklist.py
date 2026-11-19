# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class TenderChecklist(models.Model):
    _name = 'tender.checklist'
    _description = 'Tender Submission Checklist Line'
    _order = 'sequence asc, id asc'

    tender_id = fields.Many2one(
        'crm.lead',
        string="Tender",
        required=True,
        ondelete='cascade',
        index=True
    )
    sequence = fields.Integer(string="Seq", default=10)
    document_code = fields.Char(string="Doc #")
    name = fields.Char(string="Document Description", required=True)
    is_mandatory = fields.Boolean(string="Mandatory", default=True)

    source_type = fields.Selection([
        ('existing_record', 'Existing Record in Library'),
        ('template_draft', 'Template Draft'),
        ('drafted_no_template', 'Drafted Without Template'),
        ('extracted_filled', 'Extracted and Filled'),
        ('requested_external', 'Requested Externally'),
        ('product_attached', 'Attached per Product'),
        ('external_calc', 'External Calculation'),
    ], string="Source Type", default='template_draft', required=True)

    library_document_id = fields.Many2one(
        'documents.document',
        string="Linked Library Document",
        domain="[('type', '=', 'binary')]"
    )
    document_version = fields.Char(string="Version / Ref", default="v1.0")

    preparer_id = fields.Many2one('res.users', string="Preparer", default=lambda self: self.env.user)
    checker_id = fields.Many2one('res.users', string="Checker")
    reviewer_id = fields.Many2one('res.users', string="Reviewer")

    validity_date = fields.Date(string="Document Validity Date")
    is_valid_for_tender = fields.Boolean(
        string="Valid for Submission",
        compute='_compute_validity_warning',
        store=True,
        help="Checks whether document validity extends past tender submission deadline."
    )
    validity_warning = fields.Char(
        string="Validity Warning",
        compute='_compute_validity_warning',
        store=True
    )

    preparation_status = fields.Selection([
        ('not_started', 'Not Started'),
        ('drafting', 'Drafting'),
        ('ready', 'Ready for Review'),
    ], string="Preparation Status", default='not_started', required=True)

    review_status = fields.Selection([
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected / Revisions Needed'),
    ], string="Review Status", default='pending', required=True)

    attachment_id = fields.Many2one('ir.attachment', string="Attached File / Submission Draft")
    due_date = fields.Date(string="Due Date")
    notes = fields.Char(string="Remarks")

    @api.depends('validity_date', 'tender_id.x_submission_deadline')
    def _compute_validity_warning(self):
        for line in self:
            warning = False
            is_valid = True
            if line.validity_date and line.tender_id.x_submission_deadline:
                sub_date = line.tender_id.x_submission_deadline.date()
                if line.validity_date < sub_date:
                    is_valid = False
                    warning = _(
                        "Validity date (%s) expires before submission deadline (%s)!",
                        line.validity_date, sub_date
                    )
            line.is_valid_for_tender = is_valid
            line.validity_warning = warning

    def action_mark_ready(self):
        self.write({'preparation_status': 'ready'})

    def action_approve(self):
        self.write({
            'review_status': 'approved',
            'reviewer_id': self.env.user.id,
        })

    def action_reject(self):
        self.write({
            'review_status': 'rejected',
            'reviewer_id': self.env.user.id,
        })

    @api.model
    def get_standard_24_package(self):
        """Returns the standard 24-document package definitions (Spec Section 9.2)."""
        return [
            {'code': '01', 'name': 'Covering letter', 'source': 'template_draft', 'mandatory': True},
            {'code': '02', 'name': 'Licence', 'source': 'existing_record', 'mandatory': True},
            {'code': '03', 'name': 'Power of attorney', 'source': 'existing_record', 'mandatory': True},
            {'code': '04', 'name': 'Bid submission sheet', 'source': 'extracted_filled', 'mandatory': True},
            {'code': '05', 'name': 'Bidder form', 'source': 'extracted_filled', 'mandatory': True},
            {'code': '06', 'name': 'Bill of quantity (BOQ)', 'source': 'extracted_filled', 'mandatory': True},
            {'code': '07', 'name': 'Audited financial report and financial fitness evidence', 'source': 'existing_record', 'mandatory': True},
            {'code': '08', 'name': "Manufacturer's authorization", 'source': 'requested_external', 'mandatory': True},
            {'code': '09', 'name': 'Quality and test certificates', 'source': 'product_attached', 'mandatory': True},
            {'code': '10', 'name': 'Implementation schedule', 'source': 'template_draft', 'mandatory': True},
            {'code': '11', 'name': 'Technical compliance sheet', 'source': 'extracted_filled', 'mandatory': True},
            {'code': '12', 'name': 'Technical proposal', 'source': 'template_draft', 'mandatory': True},
            {'code': '13', 'name': 'Sizing and design calculations', 'source': 'external_calc', 'mandatory': False},
            {'code': '14', 'name': 'Technical datasheet and catalogue', 'source': 'product_attached', 'mandatory': True},
            {'code': '15', 'name': 'Satisfactory execution certificates', 'source': 'existing_record', 'mandatory': True},
            {'code': '16', 'name': 'Work methodology', 'source': 'existing_record', 'mandatory': True},
            {'code': '17', 'name': 'Equipment list and ownership proof', 'source': 'existing_record', 'mandatory': True},
            {'code': '18', 'name': 'Key personnel (CVs & credentials)', 'source': 'existing_record', 'mandatory': True},
            {'code': '19', 'name': 'Warranty declaration', 'source': 'template_draft', 'mandatory': True},
            {'code': '20', 'name': 'Delivery and completion schedule', 'source': 'template_draft', 'mandatory': True},
            {'code': '21', 'name': 'Terms and conditions', 'source': 'template_draft', 'mandatory': True},
            {'code': '22', 'name': 'After-sales statement', 'source': 'template_draft', 'mandatory': True},
            {'code': '23', 'name': 'Declaration to provide training', 'source': 'template_draft', 'mandatory': True},
            {'code': '24', 'name': 'Company profile', 'source': 'existing_record', 'mandatory': True},
        ]

