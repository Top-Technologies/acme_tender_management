# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class TenderCostLine(models.Model):
    _name = 'tender.costline'
    _description = 'Tender BOQ Component Cost Build-up Line'
    _order = 'sale_order_line_id asc, id asc'

    tender_id = fields.Many2one(
        'crm.lead',
        string="Tender",
        related='sale_order_line_id.order_id.x_tender_id',
        store=True,
        index=True
    )
    sale_order_line_id = fields.Many2one(
        'sale.order.line',
        string="Quotation Line (BOQ Item)",
        required=True,
        ondelete='cascade',
        index=True
    )
    product_id = fields.Many2one(
        'product.product',
        string="Internal Reference / Component Product",
        index=True
    )
    component_type = fields.Selection([
        ('materials', 'Materials'),
        ('equipment', 'Equipment'),
        ('labour', 'Labour'),
        ('installation', 'Installation'),
        ('subcontracting', 'Subcontracting'),
        ('transport', 'Transport'),
        ('other', 'Other Direct Cost'),
    ], string="Component Type", default='materials', required=True)

    description = fields.Char(string="Component Description", required=True)
    quantity = fields.Float(string="Quantity", default=1.0, digits='Product Unit of Measure')
    uom_id = fields.Many2one('uom.uom', string="Unit of Measure")

    currency_id = fields.Many2one(
        'res.currency',
        string="Currency",
        related='sale_order_line_id.currency_id',
        store=True
    )
    rate = fields.Monetary(
        string="Rate (Cost Only)",
        currency_field='currency_id',
        required=True,
        help="Direct unit cost rate. Margin must never be added here."
    )
    total_cost = fields.Monetary(
        string="Total Cost",
        currency_field='currency_id',
        compute='_compute_total_cost',
        store=True
    )

    source_of_rate = fields.Selection([
        ('vendor_pricelist', 'Vendor Price List / Standard Cost'),
        ('earlier_tender', 'Earlier Tender Rate'),
        ('rfq', 'Supplier Offer (RFQ)'),
    ], string="Source of Rate", default='vendor_pricelist', required=True)

    supplier_offer_id = fields.Many2one(
        'purchase.order',
        string="Supplier Offer (RFQ / PO)",
        domain="[('state', 'in', ('draft', 'sent', 'to approve', 'purchase', 'done'))]"
    )
    earlier_tender_costline_id = fields.Many2one(
        'tender.costline',
        string="Reference Earlier Tender Costline"
    )
    earlier_rate_display = fields.Char(
        string="Historical / Price List Rate Ref",
        compute='_compute_earlier_rate_display'
    )
    revision = fields.Integer(string="Revision", default=1)

    def _check_tender_cost_edit(self, order_lines):
        if self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager'):
            return
        for order_line in order_lines.filtered(lambda line: line.order_id.x_is_tender_quotation):
            if not self.env.user.has_group('acme_tender_management.group_tender_user'):
                raise UserError(_('Only the Sales Engineer/Tender User can maintain tender BOQ costing.'))
            if order_line.order_id.x_tender_id.stage_id.x_tender_stage_code not in ('preparation', 'bid_security_issued'):
                raise UserError(_('Tender costing is locked outside Preparation and Bid Security Issued.'))

    @api.model_create_multi
    def create(self, vals_list):
        lines = self.env['sale.order.line'].browse([vals.get('sale_order_line_id') for vals in vals_list if vals.get('sale_order_line_id')])
        self._check_tender_cost_edit(lines)
        result = super().create(vals_list)
        # Cost Build-up changes must immediately refresh Summary Bills.
        # Previously only BOQ-line changes triggered the summary sync, so a
        # newly added cost component could show in BOQ Cost Build-up while the
        # Summary Bills tab still showed the old cost/total amount.
        result.mapped('sale_order_line_id.order_id.x_tender_id')._sync_bill_summaries()
        return result

    def write(self, vals):
        lines = self.mapped('sale_order_line_id')
        if vals.get('sale_order_line_id'):
            lines |= self.env['sale.order.line'].browse(vals['sale_order_line_id'])
        self._check_tender_cost_edit(lines)
        old_tenders = self.mapped('sale_order_line_id.order_id.x_tender_id')
        result = super().write(vals)
        (old_tenders | self.mapped('sale_order_line_id.order_id.x_tender_id'))._sync_bill_summaries()
        return result

    def unlink(self):
        self._check_tender_cost_edit(self.mapped('sale_order_line_id'))
        tenders = self.mapped('sale_order_line_id.order_id.x_tender_id')
        result = super().unlink()
        tenders._sync_bill_summaries()
        return result

    @api.depends('quantity', 'rate')
    def _compute_total_cost(self):
        for line in self:
            line.total_cost = (line.quantity or 0.0) * (line.rate or 0.0)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            if not self.description:
                self.description = self.product_id.display_name
            if not self.uom_id:
                self.uom_id = self.product_id.uom_id
            # Set rate from standard_price (cost)
            if not self.rate:
                self.rate = self.product_id.standard_price

    @api.depends('product_id')
    def _compute_earlier_rate_display(self):
        for line in self:
            if not line.product_id:
                line.earlier_rate_display = False
                continue
            # Search latest earlier costline for same product in another tender
            earlier = self.search([
                ('product_id', '=', line.product_id.id),
                ('id', '!=', line._origin.id or 0),
                ('rate', '>', 0)
            ], order='id desc', limit=1)
            parts = []
            if line.product_id.standard_price:
                parts.append(f"Cost: {line.product_id.standard_price:.2f}")
            if earlier and earlier.tender_id:
                tnd_name = earlier.tender_id.x_tender_code or earlier.tender_id.name
                parts.append(f"Earlier ({tnd_name}): {earlier.rate:.2f}")
            line.earlier_rate_display = " | ".join(parts) if parts else "No earlier rates"

