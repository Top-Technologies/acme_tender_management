# -*- coding: utf-8 -*-
from odoo import models, fields, api, _

class TenderOutcome(models.Model):
    _name = 'tender.outcome'
    _description = 'Tender Final Outcome Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    tender_id = fields.Many2one(
        'crm.lead',
        string="Tender",
        required=True,
        ondelete='cascade',
        index=True
    )
    name = fields.Char(string="Reference", compute='_compute_name', store=True)

    outcome_type = fields.Selection([
        ('won', 'Won'),
        ('lost', 'Lost to Competitor'),
        ('no_go', 'No-Go'),
        ('cancelled', 'Cancelled by Tenderer'),
    ], string="Outcome Type", required=True, tracking=True)

    lost_reason_id = fields.Many2one(
        'crm.lost.reason',
        string="Reason for Loss / Cancellation"
    )
    winner_name = fields.Char(string="Winner / Competitor Name", tracking=True)
    winning_price = fields.Monetary(string="Winning Price", currency_field='currency_id', tracking=True)
    acme_price = fields.Monetary(string="ACME Final Price", currency_field='currency_id')
    price_variance = fields.Monetary(
        string="Price Difference (ACME - Winner)",
        currency_field='currency_id',
        compute='_compute_variance',
        store=True
    )
    currency_id = fields.Many2one('res.currency', string="Currency", default=lambda self: self.env.company.currency_id)

    bid_security_recovery_status = fields.Selection([
        ('not_required', 'Not Required'),
        ('open', 'Open (Recovery in Progress)'),
        ('returned', 'Returned (Finance Confirmed)'),
    ], string="Bid Security Recovery Status", compute='_compute_recovery_status')

    tech_opening_id = fields.Many2one(
        'tender.opening.tech',
        string="Technical Opening",
        related='tender_id.x_opening_tech_id',
        readonly=True
    )
    fin_opening_id = fields.Many2one(
        'tender.opening.fin',
        string="Financial Opening",
        related='tender_id.x_opening_fin_id',
        readonly=True
    )

    award_letter_attachment_id = fields.Many2one('ir.attachment', string="Award Letter / Official Notice")
    notes = fields.Text(string="Lessons Learned / Analysis")

    @api.depends('tender_id', 'outcome_type')
    def _compute_name(self):
        for rec in self:
            label = dict(rec._fields['outcome_type'].selection).get(rec.outcome_type, '')
            code = rec.tender_id.x_tender_code or rec.tender_id.name or 'Tender'
            rec.name = f"Outcome: {label} ({code})"

    @api.depends('winning_price', 'acme_price')
    def _compute_variance(self):
        for rec in self:
            rec.price_variance = (rec.acme_price or 0.0) - (rec.winning_price or 0.0)

    @api.depends('tender_id.x_bid_security_return_status')
    def _compute_recovery_status(self):
        for rec in self:
            rec.bid_security_recovery_status = rec.tender_id.x_bid_security_return_status

