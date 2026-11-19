# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class TenderCopyWizard(models.TransientModel):
    _name = 'tender.copy.wizard'
    _description = 'Start Tender from Earlier Tender'

    target_tender_id = fields.Many2one(
        'crm.lead',
        string="Target Tender",
        required=True
    )
    source_tender_id = fields.Many2one(
        'crm.lead',
        string="Source Earlier Tender",
        required=True,
        domain="[('x_is_tender', '=', True), ('id', '!=', target_tender_id)]"
    )
    copy_assessments = fields.Boolean(string="Copy Requirement Assessment Lines", default=True)
    copy_checklist = fields.Boolean(string="Copy Submission Checklist Lines", default=True)
    copy_boq = fields.Boolean(string="Copy BOQ and Cost Build-up Lines", default=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id and 'target_tender_id' in fields_list:
            res['target_tender_id'] = active_id
        return res

    def action_copy_tender_data(self):
        self.ensure_one()
        source = self.source_tender_id
        target = self.target_tender_id

        copied_items = []

        # 1. Copy Requirement Assessments
        if self.copy_assessments and source.x_assessment_ids:
            for line in source.x_assessment_ids:
                line.copy({
                    'tender_id': target.id,
                    'status': 'draft',
                })
            copied_items.append(f"{len(source.x_assessment_ids)} Requirement Assessment lines")

        # 2. Copy Submission Checklist
        if self.copy_checklist and source.x_checklist_ids:
            for line in source.x_checklist_ids:
                line.copy({
                    'tender_id': target.id,
                    'preparation_status': 'not_started',
                    'review_status': 'pending',
                    'attachment_id': False,
                    'due_date': target.x_submission_deadline.date() if target.x_submission_deadline else False,
                })
            copied_items.append(f"{len(source.x_checklist_ids)} Submission Checklist lines")

        # 3. Copy BOQ and Cost Build-up Lines
        if self.copy_boq:
            source_order = self.env['sale.order'].search([
                ('x_tender_id', '=', source.id),
                ('state', '!=', 'cancel')
            ], order='x_tender_revision desc, id desc', limit=1)

            if source_order:
                target_order = self.env['sale.order'].create({
                    'partner_id': target.partner_id.id,
                    'x_tender_id': target.id,
                    'x_is_tender_quotation': True,
                    'origin': f"Cloned from {source.x_tender_code or source.name}",
                    'x_tender_margin_percent': source_order.x_tender_margin_percent,
                })
                count_lines = 0
                for s_line in source_order.order_line:
                    t_line = s_line.copy({
                        'order_id': target_order.id,
                    })
                    for cl in s_line.x_costline_ids:
                        cl.copy({
                            'sale_order_line_id': t_line.id,
                            'earlier_tender_costline_id': cl.id,
                            'revision': 1,
                        })
                        count_lines += 1
                copied_items.append(f"BOQ quotation with {count_lines} cost build-up component lines")

        target.message_post(
            body=_(
                "Started from earlier tender %s (%s). Copied: %s.",
                source.x_tender_code,
                source.name,
                ", ".join(copied_items) if copied_items else "Nothing selected"
            )
        )
        return {'type': 'ir.actions.act_window_close'}

