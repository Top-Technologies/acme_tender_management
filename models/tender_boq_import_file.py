# -*- coding: utf-8 -*-
from odoo import fields, models, _
from odoo.exceptions import UserError


class TenderBoqImportFile(models.Model):
    _name = "tender.boq.import.file"
    _description = "Imported Tender BoQ Workbook"
    _order = "imported_on desc, id desc"

    tender_id = fields.Many2one("crm.lead", string="Tender", required=True, ondelete="cascade", index=True)
    filename = fields.Char(string="Filename", required=True)
    file = fields.Binary(string="Workbook", required=True, attachment=True)
    imported_on = fields.Datetime(string="Imported On", required=True, default=fields.Datetime.now)
    imported_by_id = fields.Many2one("res.users", string="Imported By", required=True, default=lambda self: self.env.user)
    created_boq_line_ids = fields.One2many(
        "sale.order.line", "x_boq_import_file_id", string="BOQ Lines Created by This Import"
    )
    created_boq_line_count = fields.Integer(
        string="Created BOQ Lines", compute="_compute_created_boq_line_count"
    )

    def _compute_created_boq_line_count(self):
        for record in self:
            record.created_boq_line_count = len(record.created_boq_line_ids)

    def action_remove_imported_boq(self):
        """Remove this import record and only the BOQ lines created by this import.

        Existing BOQ lines that were updated by a later import are deliberately not
        deleted because they pre-dated this file and are not safely reversible here.
        """
        if not (
            self.env.is_superuser()
            or self.env.user._is_admin()
            or self.env.user.has_group("acme_tender_management.group_tender_manager")
            or self.env.user.has_group("acme_tender_management.group_tender_user")
        ):
            raise UserError(_("Only a Tender User or Tender Manager can remove an imported BoQ file."))
        self.sudo().unlink()
        return {"type": "ir.actions.client", "tag": "reload"}

    def unlink(self):
        # Remove only lines that this import actually created. Their cost build-up
        # components cascade from the sale.order.line relation.
        created_lines = self.mapped("created_boq_line_ids")
        tenders = self.mapped("tender_id")
        if created_lines:
            created_lines.unlink()
        result = super().unlink()
        if tenders:
            tenders._sync_bill_summaries()
        return result


class CrmLeadBoqImportFile(models.Model):
    _inherit = "crm.lead"

    x_boq_import_file_ids = fields.One2many(
        "tender.boq.import.file", "tender_id", string="Imported BoQ Files"
    )
