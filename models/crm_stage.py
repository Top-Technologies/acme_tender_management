# -*- coding: utf-8 -*-
from odoo import models, fields

class CrmStage(models.Model):
    _inherit = 'crm.stage'

    x_is_tender_stage = fields.Boolean(
        string="Is Tender Stage",
        default=False,
        help="Flag this stage as specifically belonging to the ACME Tender pipeline."
    )
    x_tender_stage_code = fields.Selection([
        ('identified', 'Identified'),
        ('registered', 'Registered'),
        ('bid_nobid', 'Bid/No-Bid'),
        ('preparation', 'Preparation'),
        ('bid_security_issued', 'Bid security issued'),
        ('submitted', 'Submitted'),
        ('under_evaluation', 'Under evaluation'),
        ('won_lost', 'Won / Lost'),
    ], string="Tender Stage Code", help="Standard ACME stage code used in pipeline business rules.")

