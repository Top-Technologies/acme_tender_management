# -*- coding: utf-8 -*-
import re
from odoo import api, fields, models


def _bill_no_from_ref(item_ref):
    match = re.match(r"^\s*(\d+)(?:\.|$)", str(item_ref or ""))
    return match.group(1) if match else False


class TenderBillSummary(models.Model):
    _name = "tender.bill.summary"
    _description = "Tender BOQ Bill Summary"
    _order = "bill_no asc, id asc"

    tender_id = fields.Many2one("crm.lead", string="Tender", required=True, ondelete="cascade", index=True)
    bill_no = fields.Char(string="Bill No.", required=True, index=True)
    bill_category = fields.Char(string="Tender Bill Category", required=True)
    boq_amount = fields.Monetary(
        string="BOQ Amount", currency_field="currency_id"
    )
    cost_build_up_amount = fields.Monetary(
        string="Cost Build-up", currency_field="currency_id"
    )
    amount = fields.Monetary(
        string="Total Amount", currency_field="currency_id",
        help="BOQ Amount plus any additional Cost Build-up amount for the bill."
    )
    currency_id = fields.Many2one("res.currency", related="tender_id.currency_id", store=True, readonly=True)

    _tender_bill_unique = models.Constraint(
        "UNIQUE(tender_id, bill_no)", "Each bill number must be unique per tender."
    )


class CrmLeadBillSummary(models.Model):
    _inherit = "crm.lead"

    x_bill_summary_ids = fields.One2many("tender.bill.summary", "tender_id", string="Summary of Bills")
    x_boq_vat_rate = fields.Float(string="VAT (%)", default=15.0)
    x_boq_amount_untaxed = fields.Monetary(
        string="Amount Untaxed", currency_field="currency_id", compute="_compute_boq_summary_totals"
    )
    x_boq_amount_vat = fields.Monetary(
        string="Amount VAT", currency_field="currency_id", compute="_compute_boq_summary_totals"
    )
    x_boq_amount_total = fields.Monetary(
        string="Amount Total", currency_field="currency_id", compute="_compute_boq_summary_totals"
    )

    @api.depends("x_bill_summary_ids.amount", "x_bill_summary_ids.boq_amount", "x_bill_summary_ids.cost_build_up_amount", "x_boq_vat_rate")
    def _compute_boq_summary_totals(self):
        for tender in self:
            untaxed = sum(tender.x_bill_summary_ids.mapped("amount"))
            vat = untaxed * (tender.x_boq_vat_rate or 0.0) / 100.0
            tender.x_boq_amount_untaxed = untaxed
            tender.x_boq_amount_vat = vat
            tender.x_boq_amount_total = untaxed + vat

    def _get_boq_order_for_summary(self):
        self.ensure_one()

        # Primary source: every quotation explicitly linked to this tender.
        # Do NOT require x_is_tender_quotation here. Older/existing quotation
        # records can still contain the tender BOQ even if that flag was reset
        # during a quotation edit or module upgrade. The tender link is the
        # authoritative relationship for this tender's BOQ.
        orders = self.x_tender_order_ids.filtered(
            lambda order: order.state != "cancel"
        ).sorted(key=lambda order: (order.x_tender_revision, order.id))

        # Recovery source: if the quotation's tender link is missing but its
        # BOQ lines still point to this tender, recover that quotation instead
        # of showing an empty BOQ tab or creating a duplicate quotation.
        if not orders:
            line_orders = self.env['sale.order'].search([
                ('state', '!=', 'cancel'),
                ('order_line.x_tender_id', '=', self.id),
            ]).sorted(key=lambda order: (order.x_tender_revision, order.id))
            orders = line_orders

        if not orders:
            return self.env['sale.order']

        # Treat populated editable quotations as the current BOQ. Empty quotes
        # created alongside/imported after an existing BOQ must not hide the
        # actual lines from the BOQ tab, summary, or submission gate.
        editable = orders.filtered(lambda order: order.state in ("draft", "sent"))
        populated_editable = editable.filtered(
            lambda order: bool(order.order_line.filtered(lambda line: not line.display_type))
        )
        if populated_editable:
            return populated_editable[-1:]
        if editable:
            return editable[-1:]

        populated = orders.filtered(
            lambda order: bool(order.order_line.filtered(lambda line: not line.display_type))
        )
        return populated[-1:] if populated else orders[-1:]

    def _sync_bill_summaries(self):
        Summary = self.env["tender.bill.summary"].sudo()
        for tender in self:
            order = tender._get_boq_order_for_summary()
            grouped = {}
            if order:
                lines = order.order_line.filtered(lambda line: (
                    not line.display_type and line.x_item_ref
                    and (line.x_bill_no or _bill_no_from_ref(line.x_item_ref))
                    and line.product_uom_qty > 0
                ))
                for line in lines.sorted(key=lambda row: (row.sequence, row.id)):
                    bill_no = (line.x_bill_no or _bill_no_from_ref(line.x_item_ref) or "").strip()
                    if not bill_no:
                        continue
                    group = grouped.setdefault(bill_no, {
                        "category": "",
                        "boq_amount": 0.0,
                        "cost_build_up_amount": 0.0,
                    })
                    if not group["category"] and line.x_bill_category_id:
                        group["category"] = line.x_bill_category_id.name
                    # BOQ Amount is the customer's BOQ value. Cost Build-up is
                    # the separate internal/additional cost entered for this line.
                    # Keep the two values separate in the summary and combine
                    # them only for Total Amount.
                    # Normalize the accumulator keys defensively so an older
                    # in-memory/grouped structure cannot cause a KeyError while
                    # existing tenders are being re-synchronized after upgrade.
                    group.setdefault("boq_amount", 0.0)
                    group.setdefault("cost_build_up_amount", 0.0)

                    # BOQ Amount is always derived from the BOQ quantity and
                    # BOQ unit rate. Use the stored computed field when it is
                    # available, with a direct fallback so existing/imported
                    # lines are still reflected immediately after an upgrade.
                    boq_amount = line.x_boq_amount or (
                        (line.product_uom_qty or 0.0) * (line.x_boq_unit_rate or 0.0)
                    )

                    # Cost Build-up is the rolled-up internal cost of the line.
                    # It is intentionally optional: a BOQ line without cost
                    # components remains valid and contributes 0.00 here.
                    cost_build_up_amount = line.x_rolled_up_cost or sum(
                        line.x_costline_ids.mapped("total_cost")
                    )

                    group["boq_amount"] += boq_amount
                    group["cost_build_up_amount"] += cost_build_up_amount

            existing = {row.bill_no: row for row in tender.x_bill_summary_ids}
            for bill_no, values in grouped.items():
                # Use .get() as a final compatibility guard for summary data
                # created by earlier module versions. This prevents a tender
                # save from failing with KeyError during the first sync after
                # upgrading the module.
                boq_amount = values.get("boq_amount", 0.0) or 0.0
                cost_build_up_amount = values.get("cost_build_up_amount", 0.0) or 0.0
                summary_values = {
                    "bill_category": values.get("category") or ("Bill %s" % bill_no),
                    "boq_amount": boq_amount,
                    "cost_build_up_amount": cost_build_up_amount,
                    "amount": boq_amount + cost_build_up_amount,
                }
                if bill_no in existing:
                    existing.pop(bill_no).write(summary_values)
                else:
                    Summary.create({"tender_id": tender.id, "bill_no": bill_no, **summary_values})
            for obsolete in existing.values():
                obsolete.unlink()

