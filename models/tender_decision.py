# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class TenderDecision(models.Model):
    _name = 'tender.decision'
    _description = 'Tender Go / No-Go Decision Record'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    tender_id = fields.Many2one(
        'crm.lead',
        string="Tender",
        required=True,
        ondelete='cascade',
        index=True
    )
    name = fields.Char(string="Reference", compute='_compute_name', store=True)

    decision = fields.Selection([
        ('go', 'Go'),
        ('conditional_go', 'Conditional Go'),
        ('no_go', 'No-Go'),
    ], string="Decision", default='go', required=True, tracking=True)
    required_approval_role = fields.Selection([('dm', 'DM'), ('dgm', 'DGM'), ('gm', 'GM')], string="Required Decision Authority", default='dm', required=True)

    reasons = fields.Text(string="Reasons / Assessment Summary", required=True, tracking=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted to EDM'),
        ('reviewed', 'Reviewed by EDM'),
        ('approved', 'Authorized by DM/DGM/GM'),
        ('rejected', 'Rejected'),
    ], string="Status", default='draft', tracking=True)

    recommended_by_id = fields.Many2one(
        'res.users',
        string="Recommended by (Sales Engineer)",
        default=lambda self: self.env.user,
        tracking=True
    )
    reviewed_by_id = fields.Many2one(
        'res.users',
        string="Reviewed by (EDM)",
        tracking=True
    )
    reviewed_date = fields.Datetime(string='EDM Review Date', readonly=True, copy=False)
    authorized_by_id = fields.Many2one(
        'res.users',
        string="Authorized by (DM / DGM / GM)",
        tracking=True
    )
    approval_date = fields.Datetime(string="Authorization Date", readonly=True)
    approval_role = fields.Selection([('dm', 'DM'), ('dgm', 'DGM'), ('gm', 'GM')], readonly=True, copy=False)
    x_can_submit_for_review = fields.Boolean(compute='_compute_user_action_rights')
    x_can_review_edm = fields.Boolean(compute='_compute_user_action_rights')
    x_can_authorize = fields.Boolean(compute='_compute_user_action_rights')

    condition_ids = fields.One2many(
        'tender.decision.condition',
        'decision_id',
        string="Open Conditions & Action Items"
    )

    @api.depends_context('uid')
    @api.depends('state', 'recommended_by_id', 'reviewed_by_id', 'required_approval_role', 'tender_id.company_id.tender_edm_user_id', 'tender_id.company_id.tender_dm_user_id', 'tender_id.company_id.tender_dgm_user_id', 'tender_id.company_id.tender_gm_user_id')
    def _compute_user_action_rights(self):
        admin = self._is_tender_admin()
        user = self.env.user
        for rec in self:
            rec.x_can_submit_for_review = bool(admin or (rec.state == 'draft' and rec.recommended_by_id == user and rec._is_tender_preparer()))
            edm = rec.tender_id.company_id.tender_edm_user_id
            edm_access = user.has_group('acme_tender_management.group_tender_reviewer')
            rec.x_can_review_edm = bool(rec.state == 'submitted' and (admin or (edm_access and edm == user and rec.recommended_by_id != user)))
            role_user = getattr(rec.tender_id.company_id, 'tender_%s_user_id' % rec.required_approval_role, False)
            approver_access = user.has_group('acme_tender_management.group_tender_approver')
            rec.x_can_authorize = bool(rec.state == 'reviewed' and (admin or (approver_access and role_user == user and user not in (rec.recommended_by_id | rec.reviewed_by_id))))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.update({
                'state': 'draft',
                'recommended_by_id': self.env.user.id,
                'reviewed_by_id': False,
                'authorized_by_id': False,
                'approval_date': False,
                'approval_role': False,
                'required_approval_role': 'dm',
            })
        return super().create(vals_list)

    @api.depends('tender_id', 'decision')
    def _compute_name(self):
        for rec in self:
            dec_label = dict(rec._fields['decision'].selection).get(rec.decision, '')
            tnd_name = rec.tender_id.x_tender_code or rec.tender_id.name or 'New'
            rec.name = f"Decision: {dec_label} ({tnd_name})"

    def action_submit_for_review(self):
        for rec in self:
            if rec.state != 'draft' or (not self._is_tender_admin() and (not rec._is_tender_preparer() or rec.recommended_by_id != self.env.user)):
                raise UserError(_("Only the Sales Engineer can submit a draft decision for EDM review."))
        super(TenderDecision, self).write({'state': 'submitted'})
        self.tender_id.message_post(
            body=_("Go/No-Go Decision submitted for EDM review. Proposed Decision: %s", self.decision)
        )

    def action_review_edm(self):
        for rec in self:
            rec._require_tender_role('edm', 'review')
            if rec.state != 'submitted':
                raise UserError(_("Only a decision submitted to EDM can be reviewed."))
            if rec.recommended_by_id == self.env.user and not self._is_tender_admin():
                raise UserError(_("The decision preparer cannot perform the EDM review."))
        super(TenderDecision, self).write({
            'state': 'reviewed',
            'reviewed_by_id': self.env.user.id,
            'reviewed_date': fields.Datetime.now(),
        })
        self.tender_id.message_post(
            body=_("Go/No-Go Decision reviewed and endorsed by EDM (%s). Awaiting DM/DGM/GM authorization.", self.env.user.name)
        )

    def action_approve(self):
        roles = []
        for rec in self:
            if rec.state != 'reviewed':
                raise UserError(_("The decision must be reviewed by EDM before authorization."))
            role = rec._decision_approval_role()
            rec._require_tender_role(role, 'authorize')
            if (rec.recommended_by_id == self.env.user or rec.reviewed_by_id == self.env.user) and not self._is_tender_admin():
                raise UserError(_("The preparer or EDM reviewer cannot authorize this decision."))
            if rec.decision == 'no_go' and not (rec.reasons or '').strip():
                raise UserError(_('No-Go requires a justification.'))
            roles.append(role)
        super(TenderDecision, self).write({
            'state': 'approved',
            'authorized_by_id': self.env.user.id,
            'approval_date': fields.Datetime.now(),
            'approval_role': roles[0] if len(set(roles)) == 1 else False,
        })
        self.tender_id._record_approved_tender_decision(self)
        # If conditional go, create activities for open conditions
        if self.decision == 'conditional_go':
            for cond in self.condition_ids.filtered(lambda c: not c.is_done):
                cond.action_create_activity()

        self.tender_id.message_post(
            body=_(
                "Go/No-Go Decision formally AUTHORIZED by %s. Decision: %s.",
                self.env.user.name,
                dict(self._fields['decision'].selection).get(self.decision)
            )
        )

    def action_reject(self):
        for rec in self:
            if rec.state != 'reviewed' or rec.decision != 'no_go' or not rec.reasons.strip():
                raise UserError(_("No-Go requires an EDM-reviewed decision and a justification."))
        return self.action_approve()

    def _is_tender_preparer(self):
        return self.env.user.has_group('acme_tender_management.group_tender_user') or self.env.user.has_group('acme_tender_management.group_tender_manager')

    def _is_tender_admin(self):
        return self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager')

    def _decision_approval_role(self):
        return self.required_approval_role

    def _require_tender_role(self, role, action):
        company = self.tender_id.company_id
        configured = getattr(company, 'tender_%s_user_id' % role, False)
        group_xmlid = 'acme_tender_management.group_tender_reviewer' if role == 'edm' else 'acme_tender_management.group_tender_approver'
        role_access = self.env.user.has_group(group_xmlid)
        if not (self.env.is_superuser() or self.env.user._is_admin() or (role_access and configured == self.env.user)):
            label = role.upper()
            raise UserError(_("You are not authorized to %s this tender. The required approval role is %s.", action, label))

    def write(self, vals):
        protected = {'state', 'reviewed_by_id', 'reviewed_date', 'authorized_by_id', 'approval_date', 'approval_role'}
        if protected.intersection(vals):
            raise UserError(_("Tender approval details can only be changed through the authorized workflow actions."))
        if {'decision', 'reasons', 'recommended_by_id'}.intersection(vals):
            for rec in self:
                if rec.state != 'draft' or rec.recommended_by_id != self.env.user:
                    raise UserError(_("Only the original preparer can edit a draft recommendation, and it is locked after submission."))
        if 'required_approval_role' in vals:
            for rec in self:
                is_edm = self.env.user.has_group('acme_tender_management.group_tender_reviewer') and rec.tender_id.company_id.tender_edm_user_id == self.env.user
                is_admin = self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager')
                if rec.state != 'submitted' or not (is_edm or is_admin):
                    raise UserError(_('Only EDM can select the required authority after the decision is submitted for review.'))
        return super().write(vals)


class TenderDecisionCondition(models.Model):
    _name = 'tender.decision.condition'
    _description = 'Tender Decision Open Condition'

    decision_id = fields.Many2one('tender.decision', string="Decision", required=True, ondelete='cascade')
    name = fields.Char(string="Condition / Pre-requisite", required=True)
    owner_id = fields.Many2one('res.users', string="Condition Owner", required=True, default=lambda self: self.env.user)
    due_date = fields.Date(string="Due Date")
    is_done = fields.Boolean(string="Fulfilled / Cleared", default=False)
    notes = fields.Text(string="Fulfillment Evidence / Notes")

    def action_create_activity(self):
        if self.owner_id and self.decision_id.tender_id:
            self.decision_id.tender_id.activity_schedule(
                activity_type_id=self.env.ref('mail.mail_activity_data_todo').id,
                summary=_("Tender Go/No-Go Condition: %s", self.name),
                user_id=self.owner_id.id,
                date_deadline=self.due_date or fields.Date.today(),
            )

