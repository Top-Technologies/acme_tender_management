# -*- coding: utf-8 -*-
import re
import hashlib
import json
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


def _bill_number_from_item_ref(item_ref):
    match = re.match(r"^\s*(\d+)(?:\.|$)", str(item_ref or ""))
    return match.group(1) if match else False

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    x_is_tender_quotation = fields.Boolean(
        string="Is Tender Quotation",
        default=False,
        index=True
    )
    x_tender_id = fields.Many2one(
        'crm.lead',
        string="Tender",
        index=True
    )
    x_tender_revision = fields.Integer(
        string="Tender Revision",
        default=1
    )
    x_tender_margin_percent = fields.Float(
        string="Tender Margin %",
        default=15.0,
        help="Single margin applied to rolled-up BOQ cost across the tender."
    )
    x_total_built_up_cost = fields.Monetary(
        string="Total Rolled-up Cost",
        compute='_compute_tender_totals',
        store=True,
        currency_field='currency_id'
    )
    x_total_tender_margin = fields.Monetary(
        string="Total Tender Margin",
        compute='_compute_tender_totals',
        store=True,
        currency_field='currency_id'
    )
    x_boq_is_complete = fields.Boolean(
        string="BOQ Complete",
        compute='_compute_tender_totals',
        store=True,
        help="True when all BOQ lines that have Cost Build-up components are complete; BOQ-only lines are allowed."
    )
    x_tender_approval_user_id = fields.Many2one('res.users', string='Tender Approved By', readonly=True, copy=False)
    x_tender_approval_role = fields.Selection([('dm', 'DM'), ('dgm', 'DGM'), ('gm', 'GM')], readonly=True, copy=False)
    x_tender_approval_date = fields.Datetime(readonly=True, copy=False)
    x_tender_approval_amount = fields.Monetary(string='Tender Approval Amount', readonly=True, copy=False, currency_field='currency_id')
    x_tender_approval_signature = fields.Char(readonly=True, copy=False)
    x_tender_requotation_approved_by_id = fields.Many2one('res.users', string='Re-quotation Approved By (DM)', readonly=True, copy=False)
    x_tender_requotation_approval_date = fields.Datetime(readonly=True, copy=False)
    x_tender_requotation_signature = fields.Char(readonly=True, copy=False)
    x_can_approve_tender_quotation = fields.Boolean(compute='_compute_tender_action_rights')
    x_can_reapprove_tender_quotation = fields.Boolean(compute='_compute_tender_action_rights')
    x_can_confirm_tender_quotation = fields.Boolean(compute='_compute_tender_action_rights')

    @api.depends_context('uid')
    @api.depends('company_id.tender_dm_user_id', 'company_id.tender_dgm_user_id', 'company_id.tender_gm_user_id', 'amount_total', 'order_line.discount', 'order_line.price_unit', 'x_tender_id.stage_id', 'x_tender_id.x_tender_prepared_by_id', 'state', 'is_expired', 'x_tender_approval_user_id', 'x_tender_approval_role', 'x_tender_approval_signature', 'x_tender_requotation_approved_by_id', 'x_tender_requotation_signature')
    def _compute_tender_action_rights(self):
        user = self.env.user
        admin = self.env.is_superuser() or user._is_admin() or user.has_group('acme_tender_management.group_tender_manager')
        for order in self:
            is_tender = order.x_is_tender_quotation
            role = order._required_tender_approval_role() if is_tender else False
            role_user = getattr(order.company_id, 'tender_%s_user_id' % role, False) if role else False
            role_ok = admin or (user.has_group('acme_tender_management.group_tender_approver') and role_user == user)
            preparer = order.x_tender_id.x_tender_prepared_by_id or order.x_tender_id.user_id
            not_self = admin or (preparer != user and order.create_uid != user)
            stage_ok = not order.x_tender_id or order.x_tender_id.stage_id.x_tender_stage_code in ('preparation', 'bid_security_issued')
            order.x_can_approve_tender_quotation = bool(is_tender and role_ok and not_self and stage_ok and order.state in ('draft', 'sent'))
            order.x_can_reapprove_tender_quotation = bool(is_tender and order.is_expired and order.state in ('draft', 'sent') and (admin or (user.has_group('acme_tender_management.group_tender_approver') and order.company_id.tender_dm_user_id == user)) and not_self)
            approval_ok = (user.has_group('acme_tender_management.group_tender_approver') and order.x_tender_approval_user_id == user and order.x_tender_approval_user_id == role_user
                           and order.x_tender_approval_role == role and order.x_tender_approval_signature == order._tender_approval_signature())
            expiry_ok = not order.is_expired or (
                order.x_tender_requotation_approved_by_id == order.company_id.tender_dm_user_id
                and order.x_tender_requotation_signature == order._tender_approval_signature()
            )
            bid_security_ok = not order.x_tender_id or not order.x_tender_id.x_bid_security_required or order.x_tender_id._has_valid_bid_security_approval()
            order.x_can_confirm_tender_quotation = bool(not is_tender or admin or (
                approval_ok and expiry_ok and bid_security_ok and not order._tender_boq_validation_errors()
            ))

    def _tender_boq_validation_errors(self):
        self.ensure_one()
        errors = []
        lines = self.order_line.filtered(lambda line: not line.display_type)
        if not lines:
            return [_('No BOQ lines are present.')]
        seen = {}
        for line in lines:
            row = line.x_item_ref or line.name or _('BOQ line %s', line.id)
            bill_no = (line.x_bill_no or _bill_number_from_item_ref(line.x_item_ref) or '').strip()
            for label, value in (
                (_('Item Reference'), (line.x_item_ref or '').strip()),
                (_('Bill No.'), bill_no),
                (_('Tender Bill Category'), line.x_bill_category_id),
            ):
                if not value:
                    errors.append(_('%s: missing %s') % (row, label))
            if line.product_uom_qty <= 0:
                errors.append(_('%s: Quantity must be greater than zero.') % row)
            if line.x_boq_unit_rate <= 0:
                errors.append(_('%s: Unit Rate must be greater than zero.') % row)
            # Cost Build-up is optional. If a line has been given cost components,
            # those components must be complete; BOQ-only lines remain valid.
            if line.x_costline_ids and not line.x_cost_built:
                errors.append(_('%s: Cost Build-up is incomplete.') % row)
            reference = (line.x_item_ref or '').strip().casefold()
            if reference in seen:
                errors.append(_("Duplicate Item Reference '%s' on lines %s and %s") % (line.x_item_ref, seen[reference], row))
            elif reference:
                seen[reference] = row
        return errors

    def _tender_approval_signature(self):
        self.ensure_one()
        rows = []
        for line in self.order_line.sorted('id'):
            rows.append((line.id, line.product_id.id, line.product_uom_qty, line.price_unit, line.discount,
                         tuple(sorted(line.tax_id.ids)), line.x_boq_unit_rate,
                         tuple(sorted((cost.quantity, cost.rate, cost.total_cost) for cost in line.x_costline_ids))))
        data = (self.amount_total, self.payment_term_id.id, self.partner_id.id, self.company_id.id,
                self.currency_id.id, self.validity_date, self.x_tender_margin_percent, tuple(rows))
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()

    def _check_tender_confirmation(self):
        self.ensure_one()
        if self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager'):
            return
        if not self.x_tender_id:
            raise UserError(_('Tender quotations must be linked to a tender before they can be confirmed.'))
        if self.x_tender_id.stage_id.x_tender_stage_code not in ('preparation', 'bid_security_issued', 'submitted', 'under_evaluation', 'won_lost'):
            raise UserError(_('Tender quotation confirmation is only allowed from Preparation onward.'))
        errors = self._tender_boq_validation_errors()
        if errors:
            raise UserError(_('Quotation confirmation is blocked because BOQ/Cost Build-up is incomplete:\n• %s') % '\n• '.join(errors))
        required_role = self._required_tender_approval_role()
        required_user = getattr(self.company_id, 'tender_%s_user_id' % required_role, False)
        if not self.x_tender_approval_user_id or self.x_tender_approval_user_id != required_user or self.x_tender_approval_role != required_role:
            raise UserError(_('Quotation confirmation requires approval from the configured %s user.', required_role.upper()))
        if self.x_tender_approval_signature != self._tender_approval_signature():
            raise UserError(_('Quotation details changed after approval. Obtain approval again.'))
        if not (self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager')):
            if self.x_tender_approval_user_id != self.env.user:
                raise UserError(_('Only the user who approved this quotation can confirm it.'))
            if not self.env.user.has_group('acme_tender_management.group_tender_approver'):
                raise UserError(_('Quotation confirmation requires Tender / Approver access.'))
        tender = self.x_tender_id
        if tender and tender.x_bid_security_required:
            if not tender._has_valid_bid_security_approval():
                raise UserError(_('Quotation confirmation requires approved bid security where applicable.'))
        if self.is_expired and (
            self.x_tender_requotation_approved_by_id != self.company_id.tender_dm_user_id
            or self.x_tender_requotation_signature != self._tender_approval_signature()
        ):
            raise UserError(_('Expired quotations require the configured DM re-quotation approval process.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('x_is_tender_quotation'):
                vals.update({
                    'state': 'draft',
                    'x_tender_approval_user_id': False,
                    'x_tender_approval_role': False,
                    'x_tender_approval_date': False,
                    'x_tender_approval_amount': 0.0,
                    'x_tender_approval_signature': False,
                    'x_tender_requotation_approved_by_id': False,
                    'x_tender_requotation_approval_date': False,
                    'x_tender_requotation_signature': False,
                })
        return super().create(vals_list)

    def _required_tender_approval_role(self):
        self.ensure_one()
        amount = self.amount_total
        roles = []
        roles.append('dm' if amount <= 500000 else ('dgm' if amount <= 2000000 else 'gm'))
        if self.payment_term_id and self.payment_term_id != self.env.ref('account.account_payment_term_immediate', raise_if_not_found=False):
            roles.append('dgm' if amount <= 1000000 else 'gm')
        return max(roles, key={'dm': 1, 'dgm': 2, 'gm': 3}.get)

    def action_reapprove_expired_tender_quotation(self):
        for order in self.filtered(lambda rec: rec.x_is_tender_quotation and rec.is_expired):
            if order.state not in ('draft', 'sent'):
                raise UserError(_('Only a draft or sent expired quotation can be re-approved.'))
            if (not self.env.user.has_group('acme_tender_management.group_tender_approver') or order.company_id.tender_dm_user_id != self.env.user) and not (self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager')):
                raise UserError(_('Only the configured DM can approve re-quotation of an expired quotation.'))
            if ((order.x_tender_id and (order.x_tender_id.x_tender_prepared_by_id or order.x_tender_id.user_id) == self.env.user) or order.create_uid == self.env.user) and not (self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager')):
                raise UserError(_('The tender preparer cannot approve their own re-quotation.'))
            errors = order._tender_boq_validation_errors()
            if errors:
                raise UserError(_('Re-quotation approval is blocked because BOQ/Cost Build-up is incomplete:\n• %s') % '\n• '.join(errors))
            super(SaleOrder, order.sudo()).write({
                'x_tender_requotation_approved_by_id': self.env.user.id,
                'x_tender_requotation_approval_date': fields.Datetime.now(),
                'x_tender_requotation_signature': order._tender_approval_signature(),
            })
        return True

    def action_approve_tender_quotation(self):
        for order in self.filtered('x_is_tender_quotation'):
            if not order.x_tender_id and not (self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager')):
                raise UserError(_('Tender quotations must be linked to a tender before approval.'))
            if order.state not in ('draft', 'sent'):
                raise UserError(_('Only a draft or sent tender quotation can be approved.'))
            if order.x_tender_id and order.x_tender_id.stage_id.x_tender_stage_code not in ('preparation', 'bid_security_issued'):
                raise UserError(_('Tender quotations can only be approved during Preparation or Bid Security Issued.'))
            role = order._required_tender_approval_role()
            approver = getattr(order.company_id, 'tender_%s_user_id' % role, False)
            if not (self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager') or (self.env.user.has_group('acme_tender_management.group_tender_approver') and approver == self.env.user)):
                raise UserError(_("You are not authorized to approve this quotation. The required approval role is %s.", role.upper()))
            if ((order.x_tender_id and (order.x_tender_id.x_tender_prepared_by_id or order.x_tender_id.user_id) == self.env.user) or order.create_uid == self.env.user) and not (self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager')):
                raise UserError(_('The tender preparer cannot approve their own quotation.'))
            errors = order._tender_boq_validation_errors()
            if errors:
                raise UserError(_('Quotation approval is blocked because BOQ/Cost Build-up is incomplete:\n• %s') % '\n• '.join(errors))
            super(SaleOrder, order.sudo()).write({
                'x_tender_approval_user_id': self.env.user.id,
                'x_tender_approval_role': role,
                'x_tender_approval_date': fields.Datetime.now(),
                'x_tender_approval_amount': order.amount_total,
                'x_tender_approval_signature': order._tender_approval_signature(),
            })

    def action_confirm(self):
        for order in self.filtered('x_is_tender_quotation'):
            order._check_tender_confirmation()
        return super(SaleOrder, self.sudo()).action_confirm()

    def write(self, vals):
        is_tender_admin = self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager')
        if 'validity_date' in vals and not is_tender_admin:
            if any(order.x_is_tender_quotation and order.state != 'draft' for order in self):
                raise UserError(_('A sent tender quotation expiration cannot be changed outside the authorized re-quotation process.'))
        if vals.get('state') in ('sale', 'done'):
            for order in self.filtered('x_is_tender_quotation'):
                order._check_tender_confirmation()
            sensitive = {'partner_id', 'company_id', 'currency_id', 'payment_term_id', 'validity_date', 'x_tender_id', 'x_tender_margin_percent', 'order_line'}
            if sensitive.intersection(vals) and not is_tender_admin:
                raise UserError(_('Quotation terms cannot be changed in the same operation that confirms an approved tender quotation.'))
        protected = {'x_tender_approval_user_id', 'x_tender_approval_role', 'x_tender_approval_date', 'x_tender_approval_amount', 'x_tender_approval_signature', 'x_tender_requotation_approved_by_id', 'x_tender_requotation_approval_date', 'x_tender_requotation_signature'}
        if {'x_is_tender_quotation', 'x_tender_id'}.intersection(vals) and not is_tender_admin:
            for order in self.filtered('x_is_tender_quotation'):
                if vals.get('x_is_tender_quotation') is False or ('x_tender_id' in vals and not vals['x_tender_id']):
                    raise UserError(_('A tender quotation cannot be converted to an ordinary quotation by a tender user.'))
        if protected.intersection(vals) and not self.env.user.has_group('acme_tender_management.group_tender_manager'):
            raise UserError(_('Tender quotation approval details can only be recorded by the approval action.'))
        old_tenders = self.mapped('x_tender_id')
        result = super().write(vals)
        if {'x_tender_id', 'x_is_tender_quotation'}.intersection(vals):
            for order in self:
                tender_id = order.x_tender_id.id if order.x_is_tender_quotation else False
                order.order_line.with_context(skip_bill_summary_sync=True).write({'x_tender_id': tender_id})
            (old_tenders | self.mapped('x_tender_id'))._sync_bill_summaries()
        return result

    @api.depends(
        'order_line.x_rolled_up_cost', 'order_line.x_cost_built', 'order_line.price_subtotal',
        'order_line.x_item_ref', 'order_line.x_bill_no', 'order_line.x_bill_category_id',
        'order_line.product_uom_qty', 'order_line.x_boq_unit_rate', 'order_line.x_costline_ids.total_cost',
    )
    def _compute_tender_totals(self):
        for order in self:
            if not order.x_is_tender_quotation:
                order.x_total_built_up_cost = 0.0
                order.x_total_tender_margin = 0.0
                order.x_boq_is_complete = True
                continue

            product_lines = order.order_line.filtered(lambda l: not l.display_type and l.product_id)
            # Use the cost-line totals as the authoritative internal costing
            # value. The direct fallback prevents a stale stored computed value
            # from showing 0.00 immediately after cost lines are added/updated.
            total_cost = sum(
                (line.x_rolled_up_cost or sum(line.x_costline_ids.mapped('total_cost')))
                for line in product_lines
            )
            # Tender margin is the explicit margin calculated from the pricing
            # basis, not customer BOQ value minus internal cost. BOQ-only lines
            # therefore do not create a false margin.
            total_margin = sum(product_lines.mapped('x_margin_amount'))
            order.x_total_built_up_cost = total_cost
            order.x_total_tender_margin = total_margin

            order.x_boq_is_complete = not order._tender_boq_validation_errors()

    def action_apply_overall_margin(self):
        """Apply the single tender markup to every BOQ line using its internal rolled-up cost."""
        self.ensure_one()
        product_lines = self.order_line.filtered(lambda l: not l.display_type and l.product_id)
        if not product_lines:
            raise UserError(_('Add at least one BOQ product line before applying the Tender Markup Margin.'))
        incomplete = product_lines.filtered(lambda l: l.x_costline_ids and not l.x_cost_built)
        if incomplete:
            names = ', '.join((l.x_item_ref or l.product_id.display_name or _('BOQ line %s', l.id)) for l in incomplete[:5])
            raise UserError(_('Complete the BOQ Cost Build-up for lines that have costing components before applying the Tender Markup Margin. Incomplete: %s') % names)
        for line in product_lines:
            if line.x_costline_ids and line.x_cost_built:
                line.x_margin_percent = self.x_tender_margin_percent
                line.price_unit = line.x_unit_cost * (1.0 + (self.x_tender_margin_percent / 100.0))
            else:
                # BOQ-only lines have no internal cost basis; keep their BOQ rate
                # as the customer quotation price and do not invent a cost margin.
                line.x_margin_percent = 0.0
                line.price_unit = line.x_boq_unit_rate
        self._sync_bill_summaries() if self.x_tender_id else None
        return True

    def action_create_tender_revision(self):
        """Creates a new quotation revision (Spec 7.5)."""
        self.ensure_one()
        new_revision = self.x_tender_revision + 1
        copy_order = self.copy({
            'name': f"{self.name}-R{new_revision}",
            'x_tender_revision': new_revision,
            'origin': self.name,
        })
        # Deep copy cost lines for each order line
        for orig_line, new_line in zip(self.order_line, copy_order.order_line):
            for cl in orig_line.x_costline_ids:
                cl.copy({
                    'sale_order_line_id': new_line.id,
                    'revision': new_revision,
                })
        self.message_post(body=_("Created Tender Quotation Revision %s: %s", new_revision, copy_order.name))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': copy_order.id,
        }


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    x_tender_id = fields.Many2one('crm.lead', string="Tender", index=True, ondelete='set null')
    x_boq_import_file_id = fields.Many2one(
        'tender.boq.import.file',
        string="BOQ Import File",
        index=True,
        ondelete='set null',
        copy=False,
    )
    x_item_ref = fields.Char(string="Item Reference", index=True)
    x_bill_no = fields.Char(string="Bill No.", index=True)
    x_bill_category_id = fields.Many2one(
        'tender.bill.category', string="Tender Bill Category", ondelete='set null', index=True
    )
    x_boq_unit_rate = fields.Monetary(
        string="Unit Rate", currency_field='currency_id',
        help="BOQ unit rate. Selecting a product fills this from its cost without changing the quotation price."
    )
    x_boq_amount = fields.Monetary(
        string="Amount", currency_field='currency_id', compute='_compute_boq_amount', store=True
    )

    def init(self):
        super().init()
        self.env.cr.execute("""
            UPDATE sale_order_line AS line
               SET x_tender_id = CASE WHEN order_doc.x_is_tender_quotation THEN order_doc.x_tender_id ELSE NULL END
              FROM sale_order AS order_doc
             WHERE line.order_id = order_doc.id
               AND line.x_tender_id IS DISTINCT FROM
                   CASE WHEN order_doc.x_is_tender_quotation THEN order_doc.x_tender_id ELSE NULL END
        """)

    x_costline_ids = fields.One2many(
        'tender.costline',
        'sale_order_line_id',
        string="Cost Build-up Components"
    )
    x_rolled_up_cost = fields.Monetary(
        string="Rolled-up Cost",
        compute='_compute_cost_and_margin',
        store=True,
        currency_field='currency_id'
    )
    x_unit_cost = fields.Monetary(
        string="Unit Cost",
        compute='_compute_cost_and_margin',
        store=True,
        currency_field='currency_id'
    )
    x_margin_percent = fields.Float(
        string="Margin %",
        default=0.0
    )
    x_margin_amount = fields.Monetary(
        string="Margin Amount",
        compute='_compute_cost_and_margin',
        store=True,
        currency_field='currency_id'
    )
    x_cost_built = fields.Boolean(
        string="Cost Built",
        compute='_compute_cost_and_margin',
        store=True
    )

    @api.constrains('order_id', 'x_item_ref', 'display_type')
    def _check_unique_tender_item_reference(self):
        for line in self:
            order = line.order_id
            reference = re.sub(r'\.$', '', (line.x_item_ref or '').strip()).casefold()
            if not order.x_is_tender_quotation or line.display_type or not reference:
                continue
            duplicate = order.order_line.filtered(
                lambda other: other.id != line.id
                and not other.display_type
                and re.sub(r'\.$', '', (other.x_item_ref or '').strip()).casefold() == reference
            )[:1]
            if duplicate:
                raise ValidationError(_("Item Reference '%s' already exists on this tender quotation.", line.x_item_ref))

    def _check_tender_boq_edit(self, orders):
        if self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager'):
            return
        for order in orders.filtered('x_is_tender_quotation'):
            if not self.env.user.has_group('acme_tender_management.group_tender_user'):
                raise UserError(_('Only the Sales Engineer/Tender User can maintain tender BOQ lines and costs.'))
            if not order.x_tender_id:
                raise UserError(_('Tender BOQ lines must be linked to a tender opportunity.'))
            if order.x_tender_id.stage_id.x_tender_stage_code not in ('preparation', 'bid_security_issued'):
                raise UserError(_('Tender BOQ lines are locked outside Preparation and Bid Security Issued.'))

    @api.depends('product_uom_qty', 'x_boq_unit_rate')
    def _compute_boq_amount(self):
        for line in self:
            line.x_boq_amount = (line.product_uom_qty or 0.0) * (line.x_boq_unit_rate or 0.0)

    @api.onchange('product_id')
    def _onchange_tender_boq_product(self):
        for line in self:
            if line.order_id.x_is_tender_quotation and line.product_id:
                line.name = line.product_id.description_sale or line.product_id.name
                line.product_uom_id = line.product_id.uom_id
                line.x_boq_unit_rate = line.product_id.standard_price

    @api.onchange('x_item_ref', 'x_bill_no')
    def _onchange_tender_boq_item_ref(self):
        for line in self:
            number = _bill_number_from_item_ref(line.x_item_ref)
            if number:
                line.x_bill_no = number
            else:
                number = line.x_bill_no
            sibling = line.order_id.order_line.filtered(
                lambda other: other != line and other.x_bill_no == number and other.x_bill_category_id
            )[:1] if number else self.env['sale.order.line']
            line.x_bill_category_id = sibling.x_bill_category_id if sibling else False

    @api.onchange('x_bill_category_id')
    def _onchange_tender_boq_category(self):
        for line in self:
            if line.order_id and line.x_bill_no:
                for sibling in line.order_id.order_line.filtered(
                    lambda other: other != line and other.x_bill_no == line.x_bill_no
                ):
                    sibling.x_bill_category_id = line.x_bill_category_id

    @api.model
    def _prepare_tender_boq_vals(self, vals):
        vals = dict(vals)
        if vals.get('x_item_ref') and not vals.get('x_bill_no'):
            vals['x_bill_no'] = _bill_number_from_item_ref(vals['x_item_ref']) or vals.get('x_bill_no')
        order_id = vals.get('order_id') or self.env.context.get('default_order_id')
        order = self.env['sale.order'].browse(order_id) if order_id else self.env['sale.order']
        product_id = vals.get('product_id')
        if order.x_is_tender_quotation and product_id:
            product = self.env['product.product'].browse(product_id)
            product_values = {
                'name': product.description_sale or product.name,
                'product_uom_id': product.uom_id.id,
            }
            if not self.env.context.get('preserve_boq_unit_rate') or 'x_boq_unit_rate' not in vals:
                product_values['x_boq_unit_rate'] = product.standard_price
            # A tender BOQ line must also have a customer-facing quotation price.
            # If no explicit quotation price was supplied, use the BOQ unit rate
            # so the standard Odoo quotation totals are populated immediately.
            if not vals.get('price_unit') and product_values.get('x_boq_unit_rate'):
                product_values['price_unit'] = product_values['x_boq_unit_rate']
            vals.update(product_values)
        elif order.x_is_tender_quotation and vals.get('x_boq_unit_rate') and not vals.get('price_unit'):
            # Imported/manual BOQ rows without a product still need a quotation
            # price when their BOQ unit rate is provided.
            vals['price_unit'] = vals['x_boq_unit_rate']
        return vals

    def _sync_tender_bill_category(self, category_is_authoritative=False):
        for line in self.filtered(lambda row: row.order_id.x_is_tender_quotation and row.x_bill_no):
            siblings = line.order_id.order_line.filtered(
                lambda other: other != line and not other.display_type and other.x_bill_no == line.x_bill_no
            )
            if line.x_bill_category_id or category_is_authoritative:
                category_id = line.x_bill_category_id.id or False
                mismatched = siblings.filtered(lambda other: other.x_bill_category_id.id != category_id)
                if mismatched:
                    mismatched.with_context(skip_bill_category_sync=True).write({'x_bill_category_id': category_id})
            else:
                category = siblings.filtered('x_bill_category_id')[:1].x_bill_category_id
                if category:
                    line.with_context(skip_bill_category_sync=True).write({'x_bill_category_id': category.id})

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals = []
        for source_vals in vals_list:
            vals = dict(source_vals)
            order_id = vals.get('order_id') or self.env.context.get('default_order_id')
            tender_id = vals.get('x_tender_id')
            if not order_id and tender_id:
                tender = self.env['crm.lead'].browse(tender_id)
                order = self.env['sale.order'].search([
                    ('x_tender_id', '=', tender.id),
                    ('x_is_tender_quotation', '=', True),
                    ('state', 'in', ('draft', 'sent')),
                ], order='x_tender_revision desc, id desc', limit=1)
                if not order:
                    if not tender.partner_id:
                        raise UserError(_('Set the tender customer before adding BoQ lines.'))
                    order = self.env['sale.order'].create({
                        'partner_id': tender.partner_id.id,
                        'x_tender_id': tender.id,
                        'x_is_tender_quotation': True,
                        'origin': tender.x_tender_code or tender.name,
                    })
                order_id = order.id
                vals['order_id'] = order_id
            if order_id:
                order = self.env['sale.order'].browse(order_id)
                if order.x_is_tender_quotation:
                    self._check_tender_boq_edit(order)
                    vals['x_tender_id'] = order.x_tender_id.id
            prepared_vals.append(self._prepare_tender_boq_vals(vals))
        vals_list = prepared_vals
        lines = super().create(vals_list)
        if not self.env.context.get('skip_bill_category_sync'):
            lines._sync_tender_bill_category()
        if not self.env.context.get('skip_bill_summary_sync'):
            lines.mapped('order_id.x_tender_id')._sync_bill_summaries()
        return lines

    def write(self, vals):
        orders = self.mapped('order_id')
        target_order_id = vals.get('order_id')
        if target_order_id:
            orders |= self.env['sale.order'].browse(target_order_id)
        self._check_tender_boq_edit(orders)
        old_tenders = self.mapped('order_id.x_tender_id')
        if {'x_item_ref', 'x_bill_no', 'product_id', 'order_id'}.intersection(vals):
            for line in self:
                line_vals = dict(vals)
                if 'x_item_ref' in vals and 'x_bill_no' not in vals:
                    inferred = _bill_number_from_item_ref(vals.get('x_item_ref'))
                    if inferred:
                        line_vals['x_bill_no'] = inferred
                if 'x_bill_no' in line_vals and line_vals['x_bill_no'] != line.x_bill_no:
                    inferred = line_vals['x_bill_no']
                    if inferred:
                        line_vals['x_bill_no'] = str(inferred).strip()
                    if 'x_bill_category_id' not in vals:
                        line_vals['x_bill_category_id'] = False
                line_vals['order_id'] = vals.get('order_id') or line.order_id.id
                if 'order_id' in vals:
                    target_order = self.env['sale.order'].browse(line_vals['order_id'])
                    line_vals['x_tender_id'] = target_order.x_tender_id.id if target_order.x_is_tender_quotation else False
                line_vals = self._prepare_tender_boq_vals(line_vals)
                super(SaleOrderLine, line).write(line_vals)
        else:
            super().write(vals)

        if not self.env.context.get('skip_bill_category_sync'):
            authoritative = 'x_bill_category_id' in vals
            self._sync_tender_bill_category(category_is_authoritative=authoritative)

        if not self.env.context.get('skip_bill_summary_sync'):
            (old_tenders | self.mapped('order_id.x_tender_id'))._sync_bill_summaries()
        return True

    def unlink(self):
        self._check_tender_boq_edit(self.mapped('order_id'))
        tenders = self.mapped('order_id.x_tender_id')
        result = super().unlink()
        if not self.env.context.get('skip_bill_summary_sync'):
            tenders._sync_bill_summaries()
        return result

    @api.depends('x_costline_ids.total_cost', 'product_uom_qty', 'x_margin_percent', 'order_id.x_is_tender_quotation')
    def _compute_cost_and_margin(self):
        for line in self:
            if not line.order_id.x_is_tender_quotation:
                line.x_rolled_up_cost = 0.0
                line.x_unit_cost = 0.0
                line.x_margin_amount = 0.0
                line.x_cost_built = True
                continue

            total_cost = sum(line.x_costline_ids.mapped('total_cost'))
            line.x_rolled_up_cost = total_cost
            qty = line.product_uom_qty or 1.0
            unit_cost = total_cost / qty if qty > 0 else 0.0
            line.x_unit_cost = unit_cost
            line.x_cost_built = bool(line.x_costline_ids and total_cost > 0)
            line.x_margin_amount = (unit_cost * (line.x_margin_percent / 100.0)) * qty

    @api.onchange('x_margin_percent', 'x_unit_cost')
    def _onchange_tender_margin(self):
        if self.order_id.x_is_tender_quotation and self.x_unit_cost > 0:
            self.price_unit = self.x_unit_cost * (1.0 + (self.x_margin_percent / 100.0))

