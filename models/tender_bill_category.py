# -*- coding: utf-8 -*-
from odoo import fields, models


class TenderBillCategory(models.Model):
    _name = "tender.bill.category"
    _description = "Tender Bill Category"
    _order = "sequence, name"

    name = fields.Char(required=True, index=True)
    code = fields.Char(string="Bill No.", index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _tender_bill_category_name_unique = models.Constraint(
        "UNIQUE(name)", "Tender bill category names must be unique."
    )
