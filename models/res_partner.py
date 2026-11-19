# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_tender_ids = fields.One2many(
        'crm.lead',
        'partner_id',
        string="Client Tenders",
        domain=[('x_is_tender', '=', True)]
    )
    x_tender_count = fields.Integer(
        string="Tenders Count",
        compute='_compute_tender_count'
    )

    @api.depends('x_tender_ids')
    def _compute_tender_count(self):
        for partner in self:
            partner.x_tender_count = len(partner.x_tender_ids)

    def action_view_tenders(self):
        self.ensure_one()
        return {
            'name': f"Tenders - {self.name}",
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'view_mode': 'kanban,list,form',
            'domain': [('partner_id', '=', self.id), ('x_is_tender', '=', True)],
            'context': {
                'default_partner_id': self.id,
                'default_x_is_tender': True,
                'default_type': 'opportunity',
            }
        }

