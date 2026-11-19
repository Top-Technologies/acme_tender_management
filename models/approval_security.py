from odoo import models, fields, _
from odoo.exceptions import UserError


class ApprovalApprover(models.Model):
    _inherit = 'approval.approver'

    tender_approval_role = fields.Selection([('dgm', 'DGM'), ('gm', 'GM')], readonly=True, copy=False)
    tender_approval_date = fields.Datetime(readonly=True, copy=False)
    tender_approval_by_id = fields.Many2one('res.users', string='Approved By', readonly=True, copy=False)

    def _tender_security_request(self):
        return self.env['crm.lead'].sudo().search([
            ('x_bid_security_approval_id', '=', self.request_id.id),
            ('x_is_tender', '=', True),
        ], limit=1)

    def _check_tender_approver(self):
        for approver_line in self:
            tender = approver_line._tender_security_request()
            if not tender:
                continue
            role = tender._required_bid_security_role()
            expected = getattr(tender.company_id, 'tender_%s_user_id' % role, False)
            expected_category = self.env.ref(
                'acme_tender_management.approval_cat_tender_cpo_request'
                if tender.x_bid_security_type == 'cpo'
                else 'acme_tender_management.approval_cat_tender_bank_guarantee'
            )
            is_admin = self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager')
            has_approver_access = self.env.user.has_group('acme_tender_management.group_tender_approver')
            if not is_admin and (not has_approver_access or approver_line.user_id != self.env.user or expected != self.env.user):
                raise UserError(_("You are not authorized to approve this tender. The required approval role is %s.", role.upper()))
            if not is_admin and (tender.x_tender_prepared_by_id or tender.user_id) == self.env.user:
                raise UserError(_('The tender preparer cannot approve their own bid security request.'))
            if tender.x_bid_security_amount <= 0:
                raise UserError(_('Bid security amount must be greater than zero.'))
            if approver_line.request_id.amount != tender.x_bid_security_amount:
                raise UserError(_('The bid security amount changed after the request was submitted. Cancel and submit a new request.'))
            if approver_line.request_id.category_id != expected_category:
                raise UserError(_('The bid security type changed after the request was submitted. Cancel and submit a new request.'))
            if approver_line.request_id.request_status != 'pending':
                raise UserError(_('Only a submitted bid security request can be approved.'))
            return role

    def action_approve(self):
        self._check_tender_approver()
        return super().action_approve()

    def action_refuse(self):
        self._check_tender_approver()
        return super().action_refuse()

    def write(self, vals):
        audit_fields = {'tender_approval_role', 'tender_approval_date', 'tender_approval_by_id'}
        if audit_fields.intersection(vals) and not self.env.su:
            raise UserError(_('Tender approval audit fields are system recorded.'))
        if vals.get('status') in ('approved', 'refused') and not self.env.su:
            role = self._check_tender_approver()
            vals = dict(vals)
            if role:
                vals.update({
                    'tender_approval_role': role,
                    'tender_approval_date': fields.Datetime.now(),
                    'tender_approval_by_id': self.env.user.id,
                })
        return super().write(vals)
