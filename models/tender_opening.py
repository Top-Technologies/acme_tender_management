# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class TenderOpeningTech(models.Model):
    _name = 'tender.opening.tech'
    _description = 'Technical Bid Opening Record [ACME/OF/74]'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    tender_id = fields.Many2one(
        'crm.lead',
        string="Tender",
        required=True,
        ondelete='cascade',
        index=True
    )
    name = fields.Char(string="Reference", compute='_compute_name', store=True)
    opening_date = fields.Datetime(string="Technical Opening Date", default=fields.Datetime.now, required=True)
    acme_attendees = fields.Char(string="ACME Attendees")
    bidders_present = fields.Text(string="Bidders Present at Opening")
    read_out_results = fields.Text(string="Technical Results Read Out")
    acme_technical_findings = fields.Text(string="Technical Findings on ACME Bid")
    report_attachment_id = fields.Many2one(
        'ir.attachment',
        string="Technical Opening Report [ACME/OF/74]"
    )
    status = fields.Selection([
        ('qualified', 'ACME Technically Qualified'),
        ('disqualified', 'ACME Technically Disqualified'),
        ('pending', 'Under Clarification / Evaluation'),
    ], string="ACME Qualification Status", default='qualified', tracking=True)

    line_ids = fields.One2many(
        'tender.opening.tech.line',
        'opening_id',
        string="Bidders Technical Readout"
    )

    @api.depends('tender_id', 'opening_date')
    def _compute_name(self):
        for rec in self:
            code = rec.tender_id.x_tender_code or rec.tender_id.name or 'Tender'
            rec.name = f"Tech Opening: {code}"


class TenderOpeningTechLine(models.Model):
    _name = 'tender.opening.tech.line'
    _description = 'Technical Bid Opening Bidder Line'

    opening_id = fields.Many2one('tender.opening.tech', string="Technical Opening", required=True, ondelete='cascade')
    bidder_name = fields.Char(string="Bidder / Company Name", required=True)
    is_acme = fields.Boolean(string="Is ACME?", default=False)
    status = fields.Selection([
        ('passed', 'Passed / Compliant'),
        ('failed', 'Disqualified / Non-compliant'),
        ('clarification', 'Clarification Requested'),
    ], string="Status", default='passed')
    score = fields.Float(string="Technical Score %")
    notes = fields.Char(string="Observations / Remarks")


class TenderOpeningFin(models.Model):
    _name = 'tender.opening.fin'
    _description = 'Financial Bid Opening Record [ACME/OF/75]'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    tender_id = fields.Many2one(
        'crm.lead',
        string="Tender",
        required=True,
        ondelete='cascade',
        index=True
    )
    tech_opening_id = fields.Many2one(
        'tender.opening.tech',
        string="Technical Opening Record"
    )
    name = fields.Char(string="Reference", compute='_compute_name', store=True)
    opening_date = fields.Datetime(string="Financial Opening Date", default=fields.Datetime.now, required=True)
    acme_attendees = fields.Char(string="ACME Attendees")
    bidders_admitted = fields.Text(string="Bidders Admitted to Financial Opening")
    acme_position = fields.Integer(string="ACME Rank / Position", default=1, tracking=True)
    acme_quoted_price = fields.Monetary(string="ACME Quoted Price", currency_field='currency_id')
    lowest_bidder_price = fields.Monetary(string="Lowest Read-out Price", currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string="Currency", default=lambda self: self.env.company.currency_id)
    report_attachment_id = fields.Many2one(
        'ir.attachment',
        string="Financial Opening Report [ACME/OF/75]"
    )
    notes = fields.Text(string="Price Evaluation Remarks")

    line_ids = fields.One2many(
        'tender.opening.fin.line',
        'opening_id',
        string="Bidders Financial Readout"
    )

    @api.depends('tender_id', 'opening_date')
    def _compute_name(self):
        for rec in self:
            code = rec.tender_id.x_tender_code or rec.tender_id.name or 'Tender'
            rec.name = f"Fin Opening: {code}"


class TenderOpeningFinLine(models.Model):
    _name = 'tender.opening.fin.line'
    _description = 'Financial Bid Opening Bidder Line'
    _order = 'rank asc, price asc'

    opening_id = fields.Many2one('tender.opening.fin', string="Financial Opening", required=True, ondelete='cascade')
    bidder_name = fields.Char(string="Bidder / Company Name", required=True)
    is_acme = fields.Boolean(string="Is ACME?", default=False)
    currency_id = fields.Many2one('res.currency', string="Currency", related='opening_id.currency_id')
    price = fields.Monetary(string="Read-out Price (Excl / Incl Tax)", currency_field='currency_id', required=True)
    rank = fields.Integer(string="Rank / Position", default=1)
    notes = fields.Char(string="Remarks / Conditions")

