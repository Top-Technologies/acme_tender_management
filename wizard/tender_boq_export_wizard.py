# -*- coding: utf-8 -*-
import base64
import io

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from odoo import fields, models, _
from odoo.exceptions import UserError


class TenderBoqExportWizard(models.TransientModel):
    _name = "tender.boq.export.wizard"
    _description = "Export Tender BoQ to Excel"

    tender_id = fields.Many2one("crm.lead", required=True, readonly=True)
    file_data = fields.Binary(readonly=True)
    filename = fields.Char(readonly=True)

    @staticmethod
    def _format_sheet(sheet, widths):
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E78")
        for index, width in enumerate(widths, start=1):
            sheet.column_dimensions[get_column_letter(index)].width = width

    def action_export(self):
        self.ensure_one()
        tender = self.tender_id
        if not tender.x_is_tender:
            raise UserError(_("BOQ Excel export is available only for tenders."))

        order = tender._get_boq_order_for_summary()
        workbook = Workbook()
        lines_sheet = workbook.active
        lines_sheet.title = "BoQ Lines"
        lines_sheet.append([
            "Bill No.", "Tender Bill Category", "Item Reference", "Inventory Product",
            "Description", "Unit", "Quantity", "Unit Rate", "Amount", "Built-up Cost", "Cost Built",
        ])

        lines = order.order_line.filtered(lambda line: not line.display_type).sorted(
            key=lambda line: (line.sequence, line.id)
        ) if order else self.env["sale.order.line"]

        for line in lines:
            lines_sheet.append([
                line.x_bill_no or "",
                line.x_bill_category_id.name or "",
                line.x_item_ref or "",
                line.product_id.display_name or "",
                line.name or "",
                line.product_uom_id.name or "",
                line.product_uom_qty or 0.0,
                line.x_boq_unit_rate or 0.0,
                line.x_boq_amount or 0.0,
                line.x_rolled_up_cost or 0.0,
                "Yes" if line.x_cost_built else "No",
            ])
        self._format_sheet(lines_sheet, [14, 28, 18, 28, 60, 14, 14, 16, 16, 18, 12])

        # Detailed internal BOQ Cost Build-up. This is intentionally a separate
        # sheet so the customer-facing BOQ Lines stay clean while the internal
        # costing components are still included in the exported workbook.
        cost_sheet = workbook.create_sheet("BOQ Cost Build-up")
        cost_sheet.append([
            "Bill No.", "Item Reference", "BOQ Item", "Cost Component", "Component Type",
            "Description", "Quantity", "Unit", "Rate", "Total Cost", "Rate Source",
        ])
        if order:
            cost_lines = order.order_line.filtered(lambda line: not line.display_type).mapped("x_costline_ids")
            cost_lines = cost_lines.sorted(key=lambda line: (line.sale_order_line_id.sequence, line.sale_order_line_id.id, line.id))
            for cost in cost_lines:
                boq_line = cost.sale_order_line_id
                cost_sheet.append([
                    boq_line.x_bill_no or "",
                    boq_line.x_item_ref or "",
                    boq_line.name or "",
                    cost.product_id.display_name or "",
                    dict(cost._fields["component_type"].selection).get(cost.component_type, cost.component_type or ""),
                    cost.description or "",
                    cost.quantity or 0.0,
                    cost.uom_id.name or "",
                    cost.rate or 0.0,
                    cost.total_cost or 0.0,
                    dict(cost._fields["source_of_rate"].selection).get(cost.source_of_rate, cost.source_of_rate or ""),
                ])
        self._format_sheet(cost_sheet, [14, 18, 30, 28, 18, 50, 14, 14, 16, 18, 32])

        # Summary Bills mirrors the Odoo Summary Bills tab: keep the BOQ amount
        # and internal Cost Build-up separate, then show their combined Total
        # Amount. Include a grand-total row so the exported workbook contains
        # the same roll-up information visible on the tender.
        summary_sheet = workbook.create_sheet("Summary Bills")
        summary_sheet.append([
            "Bill No.", "Tender Bill Category", "BOQ Amount",
            "Cost Build-up", "Total Amount",
        ])
        summaries = tender.x_bill_summary_ids.sorted(
            key=lambda row: (int(row.bill_no) if str(row.bill_no).strip().isdigit() else 999999, str(row.bill_no), row.id)
        )
        total_boq = 0.0
        total_cost = 0.0
        total_amount = 0.0
        for summary in summaries:
            boq_amount = summary.boq_amount or 0.0
            cost_amount = summary.cost_build_up_amount or 0.0
            total = summary.amount if summary.amount is not None else boq_amount + cost_amount
            total_boq += boq_amount
            total_cost += cost_amount
            total_amount += total
            summary_sheet.append([
                summary.bill_no or "",
                summary.bill_category or "",
                boq_amount,
                cost_amount,
                total,
            ])

        total_row = summary_sheet.max_row + 1
        summary_sheet.cell(total_row, 1, "TOTAL")
        summary_sheet.cell(total_row, 3, total_boq)
        summary_sheet.cell(total_row, 4, total_cost)
        summary_sheet.cell(total_row, 5, total_amount)
        for cell in summary_sheet[total_row]:
            cell.font = Font(bold=True)

        self._format_sheet(summary_sheet, [14, 45, 20, 20, 20])
        for row in summary_sheet.iter_rows(min_row=2, max_row=total_row, min_col=3, max_col=5):
            for cell in row:
                cell.number_format = '#,##0.00'

        output = io.BytesIO()
        workbook.save(output)
        filename = "%s_BOQ.xlsx" % (tender.x_tender_code or "Tender")
        self.write({
            "file_data": base64.b64encode(output.getvalue()),
            "filename": filename,
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/?model=%s&id=%s&field=file_data&filename_field=filename&download=true" % (
                self._name, self.id
            ),
            "target": "self",
        }
