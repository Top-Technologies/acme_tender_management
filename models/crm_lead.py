# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class CrmLead(models.Model):
    _inherit = 'crm.lead'

    @api.model
    def _read_group_stage_ids(self, stages, domain):
        expanded_stages = super()._read_group_stage_ids(stages, domain)
        if self.env.context.get('tender_pipeline_only'):
            return expanded_stages.filtered('x_is_tender_stage')
        return expanded_stages

    x_is_tender = fields.Boolean(
        string="Is Tender",
        default=False,
        index=True,
        help="Distinguishes tender opportunities from standard commercial sales leads."
    )
    x_tender_code = fields.Char(
        string="Tender Lifecycle Code",
        copy=False,
        readonly=True,
        index=True,
        help="One unique code generated at inception that carries through order, project, and analytic account (LC-11)."
    )
    x_tender_prepared_by_id = fields.Many2one('res.users', string='Tender Prepared By', default=lambda self: self.env.user, readonly=True, copy=False, tracking=True)

    currency_id = fields.Many2one(
        'res.currency',
        string="Tender Currency",
        default=lambda self: self.env.company.currency_id
    )

    # Spec Section 5.1: Tender fields on opportunity
    x_tender_number = fields.Char(
        string="Tender Number",
        index=True,
        help="Unique tender identifier issued by client/procuring entity."
    )
    x_issuer_id = fields.Many2one(
        'res.partner',
        string="Procuring Entity / Issuer",
        help="Procuring entity or issuing authority (may differ from the paying client)."
    )
    x_source = fields.Selection([
        ('newspaper', 'Newspaper Announcement'),
        ('portal', 'Public Procurement Portal'),
        ('client_invitation', 'Direct Client Invitation / RFP'),
        ('other', 'Other Channel'),
    ], string="Tender Source", default='newspaper')

    x_submission_channel = fields.Selection([
        ('online', 'Electronic / Online Portal'),
        ('physical', 'Physical / Hard Copy Delivery'),
    ], string="Submission Channel", default='physical')

    # Key Deadlines
    x_doc_purchase_deadline = fields.Datetime(string="Document Purchase Deadline")
    x_site_visit_date = fields.Datetime(string="Site Visit Date")
    x_site_visit_required = fields.Boolean(string="Site Visit Required", default=False)
    x_submission_deadline = fields.Datetime(
        string="Bid Submission Deadline",
        index=True,
        help="Mandatory tender submission date and time."
    )
    x_tech_opening_date = fields.Datetime(string="Technical Opening Date")
    x_fin_opening_date = fields.Datetime(string="Financial Opening Date")

    # Bid Security
    x_bid_security_required = fields.Boolean(string="Bid Security Required", default=False)
    x_bid_security_type = fields.Selection([
        ('cpo', 'Cashier Payment Order (CPO)'),
        ('bank_guarantee', 'Bank Guarantee / Bid Bond'),
    ], string="Bid Security Type", default='cpo')
    x_bid_security_amount = fields.Monetary(
        string="Bid Security Amount",
        currency_field='currency_id'
    )
    x_bank_name = fields.Char(string="Issuing Bank Name")
    x_bid_security_issue_date = fields.Date(string="Bid Security Issue Date")
    x_expected_return_date = fields.Date(string="Expected Return Date")
    x_bid_security_return_status = fields.Selection([
        ('not_required', 'Not Required'),
        ('open', 'Open (Recovery in Progress)'),
        ('returned', 'Returned (Finance Confirmed)'),
    ], string="Bid Security Recovery Status", default='not_required', tracking=True)
    x_bid_security_return_date = fields.Date(string="Actual Return Date", readonly=True)
    x_bid_security_return_notes = fields.Text(string="Recovery / Refund Notes")
    x_bid_security_approval_id = fields.Many2one('approval.request', string="Bid Security Approval")

    # Joint Venture & Legal
    x_joint_venture_id = fields.Many2one(
        'res.partner',
        string="Joint Venture Partner",
        help="Joint venture partner if bidding as a consortium."
    )
    x_jv_agreement_attachment_id = fields.Many2one('ir.attachment', string="JV Agreement Attachment")

    # Go/No-Go Decision
    x_go_no_go_decision = fields.Selection([
        ('go', 'Go'),
        ('conditional_go', 'Conditional Go'),
        ('no_go', 'No-Go'),
    ], string="Go/No-Go Decision", tracking=True)

    # Final Outcome
    x_outcome_type = fields.Selection([
        ('won', 'Won'),
        ('lost', 'Lost to Competitor'),
        ('no_go', 'No-Go'),
        ('cancelled', 'Cancelled by Tenderer'),
    ], string="Outcome Type", tracking=True)
    x_winner_name = fields.Char(string="Winning Bidder")
    x_winning_price = fields.Monetary(string="Winning Price", currency_field='currency_id')
    x_lost_reason_id = fields.Many2one('crm.lost.reason', string="Lost / Cancellation Reason")

    # Documents & BOQ
    x_documents_folder_id = fields.Many2one('documents.document', string="Tender Dedicated Folder")
    x_submission_proof_attachment_id = fields.Many2one('ir.attachment', string="Proof of Submission")
    x_award_letter_attachment_id = fields.Many2one('ir.attachment', string="Award Letter / Official Notification")
    x_boq_reconciliation_note = fields.Text(string="BOQ Reconciliation Note")

    # Computed Flags
    x_library_validity_warning = fields.Boolean(
        string="Library Validity Warning",
        compute='_compute_library_validity_warning',
        store=True
    )
    x_library_warning_message = fields.Char(
        string="Library Warning Message",
        compute='_compute_library_validity_warning',
        store=True
    )
    x_boq_complete = fields.Boolean(
        string="BOQ Cost Complete",
        compute='_compute_boq_complete'
    )

    # Sub-models
    x_assessment_ids = fields.One2many('tender.assessment', 'tender_id', string="Requirement Assessments")
    x_decision_ids = fields.One2many('tender.decision', 'tender_id', string="Go/No-Go Decisions")
    x_checklist_ids = fields.One2many('tender.checklist', 'tender_id', string="Submission Checklist")
    x_opening_tech_id = fields.Many2one('tender.opening.tech', string="Technical Bid Opening Record")
    x_opening_fin_id = fields.Many2one('tender.opening.fin', string="Financial Bid Opening Record")
    x_outcome_id = fields.Many2one('tender.outcome', string="Final Outcome Record")
    x_costline_ids = fields.One2many('tender.costline', 'tender_id', string="All BOQ Costlines")
    x_tender_order_ids = fields.One2many('sale.order', 'x_tender_id', string="Tender Quotations")
    x_current_boq_order_id = fields.Many2one(
        'sale.order', string="Current Tender Quotation", compute='_compute_current_boq_order_id'
    )
    x_boq_lines_readonly = fields.Boolean(compute='_compute_current_boq_order_id')
    x_boq_line_ids = fields.One2many(
        'sale.order.line', 'x_tender_id', string="BoQ Lines"
    )

    # Counters
    x_quotation_count = fields.Integer(string="Tender Quotations Count", compute='_compute_quotation_count')
    x_checklist_progress = fields.Float(string="Checklist Progress %", compute='_compute_checklist_progress')
    x_can_request_bid_security = fields.Boolean(compute='_compute_tender_action_permissions')
    x_can_issue_bid_security = fields.Boolean(compute='_compute_tender_action_permissions')
    x_can_finalize_tender_outcome = fields.Boolean(compute='_compute_tender_action_permissions')

    @api.depends_context('uid')
    @api.depends('company_id.tender_gm_user_id', 'stage_id', 'x_bid_security_required', 'x_bid_security_approval_id', 'x_bid_security_approval_id.request_status')
    def _compute_tender_action_permissions(self):
        user = self.env.user
        is_admin = self.env.is_superuser() or user._is_admin() or user.has_group('acme_tender_management.group_tender_manager')
        is_tender_user = user.has_group('acme_tender_management.group_tender_user')
        for tender in self:
            stage = tender.stage_id.x_tender_stage_code
            tender.x_can_request_bid_security = bool(
                (is_admin or is_tender_user) and tender.x_is_tender
                and stage == 'preparation' and tender.x_bid_security_required
                and not tender.x_bid_security_approval_id
            )
            tender.x_can_issue_bid_security = bool(
                (is_admin or is_tender_user) and tender.x_is_tender
                and stage == 'preparation'
                and (not tender.x_bid_security_required or tender._has_valid_bid_security_approval())
            )
            tender.x_can_finalize_tender_outcome = bool(is_admin or (user.has_group('acme_tender_management.group_tender_approver') and tender.company_id.tender_gm_user_id == user))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('x_is_tender') or self.env.context.get('default_x_is_tender'):
                if not (self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager') or self.env.user.has_group('acme_tender_management.group_tender_user')):
                    raise UserError(_('Only the Sales Engineer/Tender User can register a tender.'))
                vals['x_is_tender'] = True
                if not (self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager')):
                    vals['x_tender_prepared_by_id'] = self.env.user.id
                    vals.update({
                        'x_go_no_go_decision': False,
                        'x_outcome_type': False,
                        'x_outcome_id': False,
                        'x_winner_name': False,
                        'x_winning_price': False,
                        'x_lost_reason_id': False,
                        'x_award_letter_attachment_id': False,
                        'x_bid_security_approval_id': False,
                        'x_bid_security_return_date': False,
                        'x_bid_security_return_status': 'open' if vals.get('x_bid_security_required') else 'not_required',
                    })
                if not vals.get('x_tender_code'):
                    vals['x_tender_code'] = self.env['ir.sequence'].next_by_code('acme.tender.code') or '/'
                # Assign to Tenders sales team if available
                tenders_team = self.env.ref('acme_tender_management.crm_team_tenders', raise_if_not_found=False)
                if tenders_team and not vals.get('team_id'):
                    vals['team_id'] = tenders_team.id
                # Assign initial stage Identified if not specified
                if not vals.get('stage_id'):
                    stage_id = self.env.ref('acme_tender_management.stage_tender_identified', raise_if_not_found=False)
                    if stage_id:
                        vals['stage_id'] = stage_id.id
                elif not (self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager')):
                    stage_id = self.env.ref('acme_tender_management.stage_tender_identified', raise_if_not_found=False)
                    if stage_id:
                        vals['stage_id'] = stage_id.id
                # Set initial return status
                if vals.get('x_bid_security_required') and not vals.get('x_bid_security_return_status'):
                    vals['x_bid_security_return_status'] = 'open'
        leads = super().create(vals_list)
        for lead in leads.filtered(lambda l: l.x_is_tender):
            # Auto-create tender documents folder
            lead._auto_create_tender_folder()
        return leads

    def write(self, vals):
        is_admin = self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager')
        tenders = self.filtered('x_is_tender')
        preparation_fields = {
            'x_tender_number', 'x_issuer_id', 'x_source', 'x_submission_channel',
            'x_doc_purchase_deadline', 'x_site_visit_date', 'x_site_visit_required',
            'x_submission_deadline', 'x_tech_opening_date', 'x_fin_opening_date',
            'x_bid_security_required', 'x_bid_security_type', 'x_bid_security_amount',
            'x_bank_name', 'x_bid_security_issue_date', 'x_expected_return_date',
            'x_joint_venture_id', 'x_jv_agreement_attachment_id', 'x_submission_proof_attachment_id',
            'x_boq_reconciliation_note',
        }
        finance_fields = {'x_bid_security_return_status', 'x_bid_security_return_date', 'x_bid_security_return_notes'}
        outcome_fields = {'x_winner_name', 'x_winning_price', 'x_lost_reason_id', 'x_outcome_id', 'x_award_letter_attachment_id'}
        if 'x_bid_security_approval_id' in vals and tenders and not is_admin:
            raise UserError(_('Bid security approval links can only be set by the bid security request action.'))
        if 'x_tender_prepared_by_id' in vals and not is_admin:
            raise UserError(_('The original tender preparer is an immutable audit field.'))
        if 'user_id' in vals and tenders and not is_admin:
            raise UserError(_('Only a Tender Administrator can reassign the tender owner.'))
        if preparation_fields.intersection(vals) and tenders and not is_admin:
            if not self.env.user.has_group('acme_tender_management.group_tender_user'):
                raise UserError(_('Only the Sales Engineer/Tender User can edit tender preparation information.'))
            for tender in tenders:
                if tender.stage_id.x_tender_stage_code in ('submitted', 'under_evaluation', 'won_lost'):
                    raise UserError(_('Tender preparation information is locked after submission.'))
                if tender.x_bid_security_approval_id and {
                    'x_bid_security_required', 'x_bid_security_type', 'x_bid_security_amount', 'x_bank_name',
                    'x_bid_security_issue_date', 'x_expected_return_date',
                }.intersection(vals):
                    raise UserError(_('Bid security details are locked after an approval request is submitted. Cancel the request before changing them.'))
        if finance_fields.intersection(vals) and tenders and not is_admin:
            if not self.env.user.has_group('acme_tender_management.group_tender_finance') or {'x_bid_security_return_status', 'x_bid_security_return_date'}.intersection(vals):
                raise UserError(_('Bid security return status can only be recorded through the Finance action.'))
        if outcome_fields.intersection(vals) and tenders and not is_admin:
            if not self.env.user.has_group('acme_tender_management.group_tender_approver') or any(t.company_id.tender_gm_user_id != self.env.user for t in tenders):
                raise UserError(_('Only the configured GM can update final outcome information.'))
        if 'x_bid_security_return_status' in vals and tenders and not is_admin:
            raise UserError(_('Bid security recovery status can only be changed through the Finance action.'))
        if 'x_is_tender' in vals and not is_admin:
            converting = any(not t.x_is_tender for t in self) and bool(vals['x_is_tender'])
            if converting:
                if not self.env.user.has_group('acme_tender_management.group_tender_user'):
                    raise UserError(_('Only the Sales Engineer/Tender User can register an opportunity as a tender.'))
                protected_on_convert = {'x_go_no_go_decision', 'x_outcome_type', 'x_outcome_id', 'x_bid_security_approval_id'}
                if protected_on_convert.intersection(vals):
                    raise UserError(_('Workflow decisions cannot be supplied while converting an opportunity into a tender.'))
                vals = dict(vals)
                vals['stage_id'] = self.env.ref('acme_tender_management.stage_tender_identified').id
                vals.update({
                    'x_go_no_go_decision': False,
                    'x_outcome_type': False,
                    'x_outcome_id': False,
                    'x_bid_security_approval_id': False,
                })
            if any(t.x_is_tender for t in self) and not vals['x_is_tender']:
                raise UserError(_('Only a Tender Administrator can remove tender classification.'))
        if 'x_go_no_go_decision' in vals and tenders and not is_admin:
            for tender in tenders:
                if not tender.x_decision_ids.filtered(lambda d: d.state == 'approved' and d.decision == vals['x_go_no_go_decision'] and d.authorized_by_id == self.env.user):
                    raise UserError(_('Go/No-Go decisions can only be recorded by the user who authorized the reviewed decision.'))
        if 'x_outcome_type' in vals and tenders and not is_admin:
            if not vals.get('stage_id') or self.env['crm.stage'].browse(vals['stage_id']).x_tender_stage_code != 'won_lost':
                raise UserError(_('A tender outcome can only be recorded as part of the final authorized stage transition.'))
            if not self.env.user.has_group('acme_tender_management.group_tender_approver') or any(t.company_id.tender_gm_user_id != self.env.user for t in tenders):
                raise UserError(_('Only the configured GM can finalize a tender outcome.'))
        # Spec Section 4.2: Automated Stage Controls
        if 'stage_id' in vals:
            target_stage = self.env['crm.stage'].browse(vals['stage_id'])
            for tender in self.filtered(lambda l: l.x_is_tender):
                stage_code = target_stage.x_tender_stage_code
                current = tender.stage_id.x_tender_stage_code
                order = ['identified', 'registered', 'bid_nobid', 'preparation', 'bid_security_issued', 'submitted', 'under_evaluation', 'won_lost']
                if not is_admin:
                    if current not in order or stage_code not in order or order.index(stage_code) != order.index(current) + 1:
                        raise UserError(_("Tender stages must be completed in sequence. Current stage: %s.", tender.stage_id.name))
                    if stage_code == 'won_lost':
                        is_configured_gm = self.env.user.has_group('acme_tender_management.group_tender_approver') and tender.company_id.tender_gm_user_id == self.env.user
                        if not (is_configured_gm or is_admin):
                            raise UserError(_('Only the configured GM with Tender / Approver access can finalize the tender outcome.'))
                    elif not self.env.user.has_group('acme_tender_management.group_tender_user'):
                        raise UserError(_("Only the Sales Engineer/Tender User can advance the tender pipeline."))

                # Stage 4: Preparation requires approved Go/No-Go decision
                if stage_code == 'preparation':
                    decision = tender.x_decision_ids.filtered(lambda d: d.state == 'approved')[:1]
                    if not decision or decision.decision not in ('go', 'conditional_go'):
                        raise UserError(_(
                            "Cannot advance to 'Preparation' without an authorized Go or Conditional Go decision! "
                            "Please create and authorize a Decision record in stage 'Bid/No-Bid'."
                        ))

                if stage_code == 'registered':
                    missing = []
                    if not tender.partner_id:
                        missing.append(_('Customer'))
                    if not tender.x_tender_number:
                        missing.append(_('Tender Number'))
                    if not tender.x_issuer_id:
                        missing.append(_('Procuring Entity / Issuer'))
                    if not tender.x_submission_deadline:
                        missing.append(_('Submission Deadline'))
                    if not tender.x_source:
                        missing.append(_('Tender Source'))
                    if missing:
                        raise UserError(_('Cannot register this tender. Complete: %s.', ', '.join(missing)))

                # Stage 5: Bid security issued requires bid security details
                if stage_code == 'bid_security_issued':
                    if tender.x_bid_security_required and (not tender._has_valid_bid_security_approval() or not (tender.x_bid_security_amount and tender.x_bank_name)):
                        raise UserError(_(
                            "Cannot advance to 'Bid security issued': Bid security amount and issuing bank must be recorded."
                        ))

                # Stage 6: Submitted requires approved mandatory checklist and proof of submission
                if stage_code == 'submitted':
                    if tender.x_bid_security_required and not tender._has_valid_bid_security_approval():
                        raise UserError(_("Cannot submit: required bid security approval is missing."))
                    tender._sync_bill_summaries()
                    boq_order = tender._get_boq_order_for_summary()
                    boq_errors = boq_order._tender_boq_validation_errors() if boq_order else [_('No active tender quotation exists.')]
                    if boq_errors:
                        raise ValidationError(_('BOQ validation failed before submission:\n• %s') % '\n• '.join(boq_errors))
                    required_quote_role = boq_order._required_tender_approval_role()
                    required_quote_user = getattr(boq_order.company_id, 'tender_%s_user_id' % required_quote_role, False)
                    if not boq_order.x_tender_approval_user_id or boq_order.x_tender_approval_user_id != required_quote_user or boq_order.x_tender_approval_role != required_quote_role or boq_order.x_tender_approval_signature != boq_order._tender_approval_signature():
                        raise UserError(_('Cannot submit: the current tender quotation has not received valid required approval.'))
                    open_mandatory = tender.x_checklist_ids.filtered(
                        lambda c: c.is_mandatory and c.review_status != 'approved'
                    )
                    if open_mandatory:
                        doc_names = ", ".join(open_mandatory.mapped('name')[:3])
                        raise UserError(_(
                            "Cannot advance to 'Submitted': Mandatory checklist items are still unapproved: %s...",
                            doc_names
                        ))
                    if not (tender.x_submission_proof_attachment_id or any(c.attachment_id for c in tender.x_checklist_ids)):
                        raise UserError(_(
                            "Cannot advance to 'Submitted': Proof of bid submission or final submitted package must be attached!"
                        ))

                # Stage 8: Won/Lost requires outcome record
                if stage_code == 'won_lost':
                    outcome_id = vals.get('x_outcome_id') or tender.x_outcome_id.id
                    outcome = self.env['tender.outcome'].browse(outcome_id) if outcome_id else self.env['tender.outcome']
                    outcome_type = vals.get('x_outcome_type') or tender.x_outcome_type or outcome.outcome_type
                    if not is_admin and (not self.env.user.has_group('acme_tender_management.group_tender_approver') or tender.company_id.tender_gm_user_id != self.env.user):
                        raise UserError(_("Only an authorized manager can finalize a tender outcome."))
                    if not outcome_type and not outcome_id:
                        raise UserError(_(
                            "Cannot close tender in 'Won / Lost' stage without recording the outcome type and Final Outcome record."
                        ))
                    if outcome_type == 'won' and not (tender.x_award_letter_attachment_id or outcome.award_letter_attachment_id):
                        raise UserError(_("A tender award letter or completed award record is required before marking Won."))
                    if outcome_type in ('lost', 'cancelled') and not (tender.x_lost_reason_id or outcome.lost_reason_id):
                        raise UserError(_("Select a Lost Reason before finalizing this tender as Lost."))

        return super().write(vals)

    def _record_approved_tender_decision(self, decision):
        for tender in self:
            approval = decision.filtered(lambda rec: rec.tender_id == tender and rec.state == 'approved' and rec.authorized_by_id == self.env.user)
            if len(approval) != 1:
                raise UserError(_('Only the actual authorizer can record the approved Go/No-Go decision.'))
            # Workflow-validated internal update; approvers need no broad CRM write ACL.
            super(CrmLead, tender.sudo()).write({'x_go_no_go_decision': approval.decision})

    def _has_valid_bid_security_approval(self):
        self.ensure_one()
        request = self.x_bid_security_approval_id.sudo()
        if not request or request.request_status != 'approved' or request.amount != self.x_bid_security_amount:
            return False
        category_ref = 'acme_tender_management.approval_cat_tender_cpo_request' if self.x_bid_security_type == 'cpo' else 'acme_tender_management.approval_cat_tender_bank_guarantee'
        if request.category_id != self.env.ref(category_ref):
            return False
        role = self._required_bid_security_role()
        expected = getattr(self.company_id, 'tender_%s_user_id' % role, False)
        approved_lines = request.sudo().approver_ids.filtered(lambda line: line.user_id == expected and line.status == 'approved')
        return bool(expected and approved_lines and expected != self.user_id)

    @api.depends('x_tender_order_ids', 'x_tender_order_ids.x_is_tender_quotation', 'x_tender_order_ids.state')
    def _compute_quotation_count(self):
        for lead in self:
            # The tender link is authoritative. Keep existing quotations visible
            # even if x_is_tender_quotation was reset on an older record.
            lead.x_quotation_count = len(lead.x_tender_order_ids.filtered(
                lambda o: o.state != 'cancel'
            ))

    @api.depends('x_checklist_ids.review_status')
    def _compute_checklist_progress(self):
        for lead in self:
            total = len(lead.x_checklist_ids)
            if not total:
                lead.x_checklist_progress = 0.0
            else:
                approved = len(lead.x_checklist_ids.filtered(lambda c: c.review_status == 'approved'))
                lead.x_checklist_progress = (approved / total) * 100.0

    @api.depends('x_checklist_ids.is_valid_for_tender', 'x_submission_deadline')
    def _compute_library_validity_warning(self):
        for lead in self:
            invalid_docs = lead.x_checklist_ids.filtered(lambda c: not c.is_valid_for_tender)
            if invalid_docs:
                lead.x_library_validity_warning = True
                lead.x_library_warning_message = _(
                    "Warning: %s checklist document(s) expire before submission deadline!", len(invalid_docs)
                )
            else:
                lead.x_library_validity_warning = False
                lead.x_library_warning_message = False

    @api.depends('x_tender_order_ids.x_boq_is_complete', 'x_tender_order_ids.order_line', 'x_tender_order_ids.order_line.display_type')
    def _compute_boq_complete(self):
        for lead in self:
            order = lead._get_boq_order_for_summary()
            lead.x_boq_complete = bool(order and order.x_boq_is_complete)

    @api.depends(
        'x_tender_order_ids', 'x_tender_order_ids.x_is_tender_quotation',
        'x_tender_order_ids.state', 'x_tender_order_ids.x_tender_revision',
        'x_tender_order_ids.order_line', 'x_tender_order_ids.order_line.display_type',
        'x_boq_line_ids', 'x_boq_line_ids.order_id',
    )
    def _compute_current_boq_order_id(self):
        for lead in self:
            lead.x_current_boq_order_id = lead._get_boq_order_for_summary()
            lead.x_boq_lines_readonly = not lead.x_current_boq_order_id or lead.x_current_boq_order_id.state not in ('draft', 'sent')

    # ---------------------------------------------------------
    # Actions & Business Logic
    # ---------------------------------------------------------
    def action_generate_standard_checklist(self):
        """Generates the 24 standard document package (Spec Section 9.2)."""
        self.ensure_one()
        existing_codes = set(self.x_checklist_ids.mapped('document_code'))
        std_package = self.env['tender.checklist'].get_standard_24_package()

        lines_to_create = []
        for idx, doc in enumerate(std_package, start=1):
            if doc['code'] in existing_codes:
                continue
            lines_to_create.append({
                'tender_id': self.id,
                'sequence': idx * 10,
                'document_code': doc['code'],
                'name': doc['name'],
                'source_type': doc['source'],
                'is_mandatory': doc['mandatory'],
                'preparer_id': self.user_id.id or self.env.user.id,
                'due_date': self.x_submission_deadline.date() if self.x_submission_deadline else False,
            })
        if lines_to_create:
            self.env['tender.checklist'].create(lines_to_create)
            self.message_post(body=_("Standard 24-document submission checklist generated."))

    def _auto_create_tender_folder(self):
        """Creates dedicated tender documents folder hierarchy under Tenders (Spec Section 10)."""
        root_folder = self.env.ref('acme_tender_management.folder_tenders_root', raise_if_not_found=False)
        if not root_folder or self.x_documents_folder_id:
            return

        folder_name = f"{self.x_tender_code} - {self.partner_id.name or self.name}"
        tender_folder = self.env['documents.document'].create({
            'name': folder_name,
            'type': 'folder',
            'folder_id': root_folder.id,
        })
        self.x_documents_folder_id = tender_folder.id

        # Standard sub-folders: Technical, Financial, Administrative, Licences, Submitted
        subfolder_names = ['Technical', 'Financial', 'Administrative', 'Licences', 'Submitted']
        for sub in subfolder_names:
            self.env['documents.document'].create({
                'name': sub,
                'type': 'folder',
                'folder_id': tender_folder.id,
            })

    def action_request_bid_security(self):
        """Triggers bid security approval request (Spec Section 8 & 11)."""
        self.ensure_one()
        if not (self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager') or self.env.user.has_group('acme_tender_management.group_tender_user')):
            raise UserError(_('Only the Sales Engineer or Tender Administrator can request bid security.'))
        if self.stage_id.x_tender_stage_code != 'preparation':
            raise UserError(_('Bid security can only be requested during Preparation.'))
        if self.x_bid_security_approval_id:
            raise UserError(_('A bid security request already exists for this tender.'))
        if self.x_bid_security_amount <= 0 or not self.x_bank_name:
            raise UserError(_("Please specify Bid Security Amount and Issuing Bank Name before requesting."))

        category_ref = (
            'acme_tender_management.approval_cat_tender_cpo_request'
            if self.x_bid_security_type == 'cpo'
            else 'acme_tender_management.approval_cat_tender_bank_guarantee'
        )
        cat = self.env.ref(category_ref, raise_if_not_found=False)
        if not cat:
            raise UserError(_("Approval Category for Bid Security not found."))

        role = self._required_bid_security_role()
        approver = getattr(self.company_id, 'tender_%s_user_id' % role, False)
        if not approver:
            raise UserError(_('Configure the Tender %s user on the company before requesting bid security.', role.upper()))
        if approver == self.env.user or (self.x_tender_prepared_by_id or self.user_id) == approver:
            raise UserError(_('The tender preparer cannot approve their own bid security request.'))

        # Bid-security requests use exactly one designated approver (DGM or GM).
        # Older databases may still have these Approval Categories configured with
        # the standard minimum of 2 approvers, which would make action_confirm()
        # reject the request even though this custom workflow creates one approver.
        if cat.sudo().approval_minimum != 1:
            cat.sudo().write({'approval_minimum': 1})

        app_req = self.env['approval.request'].sudo().create({
            'name': f"Bid Security: {self.x_tender_code} ({self.name})",
            'category_id': cat.id,
            'amount': self.x_bid_security_amount,
            'partner_id': self.x_issuer_id.id or self.partner_id.id,
            'date': self.x_bid_security_issue_date or fields.Date.today(),
            'reference': self.x_tender_number or self.x_tender_code,
            'request_owner_id': self.env.user.id,
            # The custom tender security workflow uses exactly one designated approver.
            # Set this on the request itself as well as the category because Odoo's
            # approval.request confirmation validates the request-level minimum.
            'approval_minimum': 1,
            'approver_ids': [(5, 0, 0), (0, 0, {'user_id': approver.id})],
        })
        app_req.action_confirm()
        super(CrmLead, self).write({'x_bid_security_approval_id': app_req.id})
        self.message_post(body=_("Bid Security approval request submitted (%s).", cat.name))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'approval.request',
            'view_mode': 'form',
            'res_id': app_req.id,
        }

    def _required_bid_security_role(self):
        self.ensure_one()
        if self.x_bid_security_type == 'bank_guarantee':
            return 'gm'
        return 'dgm' if self.x_bid_security_amount <= 250000 else 'gm'

    def action_issue_bid_security(self):
        """Authorized Tender User records receipt of the bid-security instrument and moves the tender to Bid security issued."""
        self.ensure_one()
        if not (self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager') or self.env.user.has_group('acme_tender_management.group_tender_user')):
            raise UserError(_('Only an authorized Tender User can record receipt of the bid-security instrument.'))
        if self.stage_id.x_tender_stage_code != 'preparation':
            raise UserError(_('Bid security can only be issued from Preparation.'))
        if self.x_bid_security_required and not self._has_valid_bid_security_approval():
            raise UserError(_('Bid security cannot be issued before its configured DGM/GM approval.'))
        stage_issued = self.env.ref('acme_tender_management.stage_tender_bid_security_issued', raise_if_not_found=False)
        if stage_issued:
            self.stage_id = stage_issued.id
        issue_date = self.x_bid_security_issue_date or fields.Date.today()
        super(CrmLead, self.sudo()).write({
            'x_bid_security_return_status': 'open' if self.x_bid_security_required else 'not_required',
            'x_bid_security_issue_date': issue_date,
        })

        # Schedule Office Manager recovery activity (Spec Section 8)
        if self.x_bid_security_required:
            self.activity_schedule(
            activity_type_id=self.env.ref('mail.mail_activity_data_todo').id,
            summary=_("Bid Security Recovery Tracking: %s", self.x_tender_code),
            note=_("Track instrument recovery from procuring entity. Attach recovery receipt upon return."),
            date_deadline=self.x_expected_return_date or (fields.Date.today() + timedelta(days=90)),
            )
        self.message_post(body=_(
            "Bid security instrument received and recorded. Recovery status is OPEN. Bid security recovery activity scheduled."
        ))

    def action_confirm_bid_security_return(self):
        """Finance confirms return of bid security instrument / refund (Spec Section 8)."""
        self.ensure_one()
        is_finance = self.env.user.has_group('acme_tender_management.group_tender_finance')
        is_manager = self.env.user.has_group('acme_tender_management.group_tender_manager')
        if not (is_finance or is_manager or self.env.is_superuser() or self.env.user._is_admin()):
            raise UserError(_("Only users in Tender / Finance or Tender / Administrator can confirm bid security return."))

        super(CrmLead, self.sudo()).write({
            'x_bid_security_return_status': 'returned',
            'x_bid_security_return_date': fields.Date.today(),
        })
        # Mark recovery activities as done
        recov_activities = self.activity_ids.filtered(lambda a: 'Bid Security Recovery' in (a.summary or ''))
        recov_activities.action_feedback(feedback=_("Finance confirmed return of bid security instrument."))
        self.message_post(body=_("Finance CONFIRMED return of bid security instrument/refund. Recovery closed."))

    def action_tender_won(self):
        """Executes Award & Handover automation (Spec Section 4.3 & 7.9)."""
        self.ensure_one()
        if not (self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager') or (self.env.user.has_group('acme_tender_management.group_tender_approver') and self.company_id.tender_gm_user_id == self.env.user)):
            raise UserError(_("Only an authorized manager can finalize a tender as Won."))
        stage_won = self.env.ref('acme_tender_management.stage_tender_won_lost', raise_if_not_found=False)
        vals = {'x_outcome_type': 'won'}
        if stage_won:
            vals['stage_id'] = stage_won.id
        self.sudo().write(vals)

        # Rename opportunity to project name, keeping lifecycle code
        current_title = self.name
        if not self.x_tender_code in current_title:
            self.sudo().write({'name': f"[{self.x_tender_code}] {self.partner_id.name or ''} - {current_title}"})

        # Schedule Operations Division Hand-over activity for ODM
        self.sudo().activity_schedule(
            activity_type_id=self.env.ref('mail.mail_activity_data_todo').id,
            summary=_("Operations Division Handover: %s", self.name),
            note=_(
                "Tender AWARDED under code %s. ODM reviews and accepts; convert opportunity to active project. "
                "Prepare acceptance letter, performance bond and advance guarantee.",
                self.x_tender_code
            ),
            date_deadline=fields.Date.today() + timedelta(days=5),
        )
        self.sudo().message_post(body=_(
            "Tender AWARDED! Opportunity renamed to project name preserving code %s. Handover activity dispatched to Operations Division.",
            self.x_tender_code
        ))

    def action_tender_lost(self):
        self.ensure_one()
        if not (self.env.is_superuser() or self.env.user._is_admin() or self.env.user.has_group('acme_tender_management.group_tender_manager') or (self.env.user.has_group('acme_tender_management.group_tender_approver') and self.company_id.tender_gm_user_id == self.env.user)):
            raise UserError(_('Only the configured GM can finalize a tender as Lost.'))
        if self.stage_id.x_tender_stage_code != 'under_evaluation':
            raise UserError(_('A tender can only be finalized as Lost from Under Evaluation.'))
        if not self.x_lost_reason_id:
            raise UserError(_('Select a Lost Reason before finalizing this tender as Lost.'))
        stage = self.env.ref('acme_tender_management.stage_tender_won_lost')
        self.sudo().write({'x_outcome_type': 'lost', 'stage_id': stage.id})
        self.sudo().message_post(body=_('Tender finalized as Lost by %s.', self.env.user.name))

    def action_view_quotations(self):
        self.ensure_one()
        return {
            'name': _("Tender Quotations (BOQs)"),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'list,form',
            'domain': [('x_tender_id', '=', self.id)],
            'context': {
                'default_x_tender_id': self.id,
                'default_x_is_tender_quotation': True,
                'default_partner_id': self.partner_id.id,
                'default_origin': self.x_tender_code or self.name,
            }
        }

    def action_create_tender_quotation(self):
        self.ensure_one()
        order = self._get_boq_order_for_summary()
        if not order:
            order = self.env['sale.order'].create({
                'partner_id': self.partner_id.id,
                'x_tender_id': self.id,
                'x_is_tender_quotation': True,
                'origin': self.x_tender_code or self.name,
            })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'view_mode': 'form',
            'res_id': order.id,
        }

    def action_add_tender_boq_line(self):
        """Create one editable manual BOQ line on the current draft tender quotation."""
        self.ensure_one()
        order = self._get_boq_order_for_summary()
        if not order:
            if not self.partner_id:
                raise UserError(_('Set the tender customer before adding a BOQ line.'))
            order = self.env['sale.order'].create({
                'partner_id': self.partner_id.id,
                'x_tender_id': self.id,
                'x_is_tender_quotation': True,
                'origin': self.x_tender_code or self.name,
            })
        if order.state not in ('draft', 'sent'):
            raise UserError(_('Manual BOQ lines can only be added to a draft or sent tender quotation.'))
        unit = self.env.ref('uom.product_uom_unit', raise_if_not_found=False)
        self.env['sale.order.line'].create({
            'order_id': order.id,
            'x_tender_id': self.id,
            'name': _('New BOQ Line - complete the required fields'),
            'product_uom_id': unit.id if unit else False,
            'product_uom_qty': 1.0,
            'x_boq_unit_rate': 0.0,
        })
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_import_tender_boq(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import BoQ Lines'),
            'res_model': 'tender.boq.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_tender_id': self.id},
        }

    def action_export_tender_boq(self):
        self.ensure_one()
        wizard = self.env['tender.boq.export.wizard'].create({'tender_id': self.id})
        return wizard.action_export()

    # ---------------------------------------------------------
    # Cron Jobs
    # ---------------------------------------------------------
    @api.model
    def _cron_check_tender_deadlines(self):
        """Scans active tenders and schedules reminder activities (Spec Section 7.1)."""
        now = fields.Datetime.now()
        active_tenders = self.search([
            ('x_is_tender', '=', True),
            ('stage_id.x_tender_stage_code', 'not in', ('submitted', 'won_lost'))
        ])

        for tender in active_tenders:
            # 1. Submission Deadline Reminders (repeats until submitted)
            if tender.x_submission_deadline:
                days_left = (tender.x_submission_deadline - now).total_seconds() / 86400.0
                if 0 <= days_left <= 7:
                    tender.activity_schedule(
                        activity_type_id=self.env.ref('mail.mail_activity_data_todo').id,
                        summary=_("URGENT: Submission Deadline in %.1f days", days_left),
                        note=_("Tender %s submission deadline is %s.", tender.x_tender_code, tender.x_submission_deadline),
                        user_id=tender.user_id.id or self.env.user.id,
                        date_deadline=tender.x_submission_deadline.date(),
                    )

            # 2. Document Purchase Deadline
            if tender.x_doc_purchase_deadline and tender.stage_id.x_tender_stage_code == 'identified':
                days_left = (tender.x_doc_purchase_deadline - now).total_seconds() / 86400.0
                if 0 <= days_left <= 3:
                    tender.activity_schedule(
                        activity_type_id=self.env.ref('mail.mail_activity_data_todo').id,
                        summary=_("Document Purchase Deadline Approaching"),
                        note=_("Purchase tender dossier before %s.", tender.x_doc_purchase_deadline),
                        user_id=tender.user_id.id or self.env.user.id,
                        date_deadline=tender.x_doc_purchase_deadline.date(),
                    )

    @api.model
    def _cron_check_library_validity(self):
        """Weekly check for expiring library records linked to tenders (Spec Section 7.3)."""
        now_date = fields.Date.today()
        threshold_date = now_date + timedelta(days=30)
        expiring_checklists = self.env['tender.checklist'].search([
            ('validity_date', '<=', threshold_date),
            ('validity_date', '>=', now_date),
            ('tender_id.x_is_tender', '=', True),
            ('tender_id.stage_id.x_tender_stage_code', 'not in', ('submitted', 'won_lost'))
        ])
        for line in expiring_checklists:
            line.tender_id.activity_schedule(
                activity_type_id=self.env.ref('mail.mail_activity_data_warning').id,
                summary=_("Expiring Library Record: %s", line.name),
                note=_(
                    "Library document '%s' expires on %s. Renewal required for tender %s.",
                    line.name, line.validity_date, line.tender_id.x_tender_code
                ),
                user_id=line.tender_id.user_id.id or self.env.user.id,
                date_deadline=line.validity_date,
            )
