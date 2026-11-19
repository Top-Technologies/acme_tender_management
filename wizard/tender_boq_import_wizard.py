# -*- coding: utf-8 -*-
import base64
import io
import re

from openpyxl import load_workbook
from odoo import fields, models, _
from odoo.exceptions import UserError


def _text(value):
    return "" if value is None else str(value).replace("\xa0", " ").strip()


def _number(value):
    try:
        if value in (None, ""):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        text = _text(value)
        negative = text.startswith("(") and text.endswith(")")
        cleaned = re.sub(r"[^0-9.+-]", "", text.replace(",", ""))
        number = float(cleaned) if cleaned else 0.0
        return -number if negative else number
    except (TypeError, ValueError):
        return 0.0


def _bill_from_reference(item_ref):
    match = re.match(r"^\s*(\d+)(?:\.|$)", str(item_ref or ""))
    return match.group(1) if match else False


def _bill_number(value):
    text = _text(value)
    match = re.search(r"(?:\bbill\s*)?(\d+)", text, re.IGNORECASE)
    return match.group(1) if match else text


def _reference_key(item_ref):
    return re.sub(r"\.$", "", _text(item_ref)).strip().casefold()


class TenderBoqImportWizard(models.TransientModel):
    _name = "tender.boq.import.wizard"
    _description = "Import Tender BoQ Lines"

    tender_id = fields.Many2one("crm.lead", required=True, readonly=True)
    file = fields.Binary(string="BoQ Excel File", required=True)
    filename = fields.Char(string="Filename")
    result_message = fields.Text(readonly=True)
    import_done = fields.Boolean(readonly=True)

    @staticmethod
    def _header_key(value):
        return re.sub(r"[^a-z0-9]+", " ", _text(value).casefold()).strip()

    @classmethod
    def _find_header(cls, rows, aliases, required=("item_ref", "description")):
        normalized = {key: {cls._header_key(alias) for alias in options} for key, options in aliases.items()}
        for row_index, row in enumerate(rows[:30]):
            found = {}
            for column, value in enumerate(row):
                key = cls._header_key(value)
                for target, options in normalized.items():
                    matched = key in options or any(
                        len(alias) >= 5 and (key.startswith(alias + " ") or key.endswith(" " + alias))
                        for alias in options
                    )
                    if matched and target not in found:
                        found[target] = column
            if all(key in found for key in required):
                return row_index, found
        return None, {}

    @staticmethod
    def _cell(row, columns, name):
        index = columns.get(name)
        return row[index] if index is not None and index < len(row) else None

    def _load_workbook(self):
        try:
            content = base64.b64decode(self.file)
            return load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        except Exception as error:
            raise UserError(_("Unable to read the workbook. Upload a valid .xlsx file. %s") % error) from error

    def _extract_lines(self, workbook):
        sheet = next((name for name in workbook.sheetnames if name.casefold() == "bills"), workbook.sheetnames[0])
        rows = list(workbook[sheet].iter_rows(values_only=True))
        aliases = {
            "bill_no": ("bill", "bill no", "bill number", "bill no."),
            "category": ("tender bill category", "bill category", "category"),
            "item_ref": ("item reference", "item ref", "item no", "item number", "item", "reference", "ref"),
            "product": ("inventory product", "product", "product code", "default code", "internal reference"),
            "description": ("description", "item description", "work description"),
            "unit": ("unit", "uom", "unit of measure"),
            "quantity": ("quantity", "qty"),
            "unit_rate": (
                "unit rate", "unit rate birr", "unit rate in birr", "unit rate br", "unit rate etb",
                "rate per unit", "rate", "rate birr", "rate in birr", "rate br", "rate etb",
                "unit price", "unit price birr", "unit price in birr", "unit price br", "unit price etb",
                "price", "price birr", "price br", "price etb",
            ),
            "amount": ("amount", "line amount", "line total", "total amount"),
        }
        header_row, columns = self._find_header(rows, aliases)
        if header_row is None:
            # Standard reference workbook layout: Bill, Reference, Description, Unit, Quantity, Unit Rate.
            columns = {
                "bill_no": 0, "item_ref": 1, "description": 2, "unit": 3,
                "quantity": 4, "unit_rate": 5, "amount": 6,
            }

        category_by_bill = {}
        summary_sheet = next((
            name for name in workbook.sheetnames
            if name.casefold() in ("summary bills", "summary of bills")
        ), None)
        if summary_sheet:
            summary_rows = list(workbook[summary_sheet].iter_rows(values_only=True))
            summary_header, summary_columns = self._find_header(summary_rows, {
                "bill_no": ("bill", "bill no", "bill number", "bill no."),
                "category": ("tender bill category", "bill category", "category", "description", "bill description"),
            }, required=("bill_no", "category"))
            if summary_header is not None:
                for row_index, row in enumerate(summary_rows):
                    if row_index == summary_header:
                        continue
                    bill_no = _bill_number(self._cell(list(row), summary_columns, "bill_no"))
                    category = _text(self._cell(list(row), summary_columns, "category"))
                    if bill_no and category:
                        category_by_bill.setdefault(bill_no, category)

        imported = []
        skipped = []
        seen_refs = {}
        current_bill = False
        for row_index, row in enumerate(rows):
            values = list(row)
            if row_index == header_row:
                continue
            heading = " ".join(_text(value) for value in values if value is not None)
            bill_heading = re.search(r"\bBILL\s*(\d+)\b", heading, re.IGNORECASE)
            ref = _text(self._cell(values, columns, "item_ref"))
            description = _text(self._cell(values, columns, "description"))
            total_row = r"^(?:grand\s+total|sub\s*total|total)\b"
            tax_row = r"^(?:\d+(?:[.,]\d+)?\s*%\s*)?(?:vat|tax)\b"
            if (re.match(total_row, ref, re.IGNORECASE) or re.match(total_row, description, re.IGNORECASE)
                    or "%" in ref or re.match(tax_row, ref, re.IGNORECASE)
                    or re.match(tax_row, description, re.IGNORECASE)):
                continue
            if bill_heading and (not ref or not description or "TOTAL" in heading.upper()):
                current_bill = bill_heading.group(1)
                continue
            if not ref and not description:
                if any(_text(value) for value in values):
                    skipped.append((row_index + 1, "No Item Reference or Description; not a BOQ line"))
                continue
            excel_row = row_index + 1
            if not ref or not description or ref.casefold() in {"item", "item reference", "reference"}:
                skipped.append((excel_row, "Missing Item Reference or Description"))
                continue
            ref = re.sub(r"\.$", "", ref).strip()
            bill_no = _bill_from_reference(ref) or _bill_number(self._cell(values, columns, "bill_no")) or current_bill
            if not bill_no:
                skipped.append((excel_row, "Could not determine Bill No."))
                continue
            category = _text(self._cell(values, columns, "category"))
            if category:
                category_by_bill.setdefault(bill_no, category)
            raw_unit_rate = self._cell(values, columns, "unit_rate")
            quantity = _number(self._cell(values, columns, "quantity"))
            raw_amount = self._cell(values, columns, "amount")
            has_unit_rate = bool(_text(raw_unit_rate))
            unit_rate = _number(raw_unit_rate)
            if not has_unit_rate and _text(raw_amount) and quantity:
                unit_rate = _number(raw_amount) / quantity
                has_unit_rate = True
            if quantity <= 0:
                skipped.append((excel_row, "Quantity is missing or not positive"))
                continue
            if not has_unit_rate:
                skipped.append((excel_row, "Unit Rate is missing or invalid"))
                continue
            key = _reference_key(ref)
            if key in seen_refs:
                skipped.append((excel_row, "Duplicate Item Reference %s (first seen on row %s)" % (ref, seen_refs[key])))
                continue
            seen_refs[key] = excel_row
            imported.append({
                "excel_row": excel_row,
                "item_ref": ref,
                "bill_no": bill_no,
                "category": category_by_bill.get(bill_no, ""),
                "product_text": _text(self._cell(values, columns, "product")),
                "description": description,
                "unit": _text(self._cell(values, columns, "unit")),
                "quantity": quantity,
                "unit_rate": unit_rate,
                "has_unit_rate": has_unit_rate,
            })
        if not imported and not skipped:
            raise UserError(_("No BoQ item rows were found. Include Item Reference and Description columns."))

        # Apply a category discovered later in the workbook to every row for its bill.
        for values in imported:
            if not values["category"]:
                values["category"] = category_by_bill.get(values["bill_no"], "")
        return imported, skipped

    def _find_product(self, text):
        if not text:
            return self.env["product.product"]
        Product = self.env["product.product"]
        product = Product.search([("default_code", "=", text)], limit=1)
        if not product:
            product = Product.search([("name", "=", text)], limit=1)
        return product

    def _find_category(self, bill_no, label, order):
        Category = self.env["tender.bill.category"]
        existing = order.order_line.filtered(
            lambda line: line.x_bill_no == bill_no and line.x_bill_category_id
        )[:1].x_bill_category_id
        if existing and (not label or existing.name == label):
            return existing
        name = label or ("Bill %s" % bill_no)
        category = Category.search([("name", "=", name)], limit=1)
        if category:
            if not category.code:
                category.code = bill_no
            return category
        return Category.create({"name": name, "code": bill_no})

    def _get_target_order(self):
        tender = self.tender_id
        order = tender._get_boq_order_for_summary()
        if order:
            if order.state not in ("draft", "sent"):
                raise UserError(_("The latest tender quotation is confirmed or closed. Create a draft tender quotation before importing BoQ lines."))
            return order
        if not tender.partner_id:
            raise UserError(_("Set the tender customer before importing BoQ lines."))
        return self.env["sale.order"].create({
            "partner_id": tender.partner_id.id,
            "x_tender_id": tender.id,
            "x_is_tender_quotation": True,
            "origin": tender.x_tender_code or tender.name,
        })

    def action_import(self):
        self.ensure_one()
        if not self.tender_id.x_is_tender:
            raise UserError(_("BoQ lines can only be imported for a tender."))
        workbook = self._load_workbook()
        rows, skipped = self._extract_lines(workbook)
        import_file = self.env["tender.boq.import.file"].create({
            "tender_id": self.tender_id.id,
            "filename": self.filename or "BoQ.xlsx",
            "file": self.file,
        })

        if not rows:
            self.write({"import_done": True, "result_message": _("Created: 0\nUpdated: 0\nSkipped: %s\n%s") % (
                len(skipped), "\n".join("Row %s: %s" % item for item in skipped)
            )})
            return self._result_action()

        order = self._get_target_order()
        Unit = self.env["uom.uom"]
        default_unit = self.env.ref("uom.product_uom_unit", raise_if_not_found=False)
        existing_by_ref = {}
        for line in order.order_line.filtered(lambda row: not row.display_type and row.x_item_ref):
            existing_by_ref.setdefault(_reference_key(line.x_item_ref), line)

        created = updated = 0
        for row in rows:
            product = self._find_product(row["product_text"])
            unit = product.uom_id if product else Unit.search([("name", "=", row["unit"])], limit=1)
            unit = unit or default_unit
            category = self._find_category(row["bill_no"], row["category"], order) if row["category"] else False
            values = {
                "order_id": order.id,
                "x_item_ref": row["item_ref"],
                "x_bill_no": row["bill_no"],
                "x_bill_category_id": category.id if category else False,
                "product_id": product.id or False,
                "name": row["description"],
                "product_uom_id": unit.id if unit else False,
                "product_uom_qty": row["quantity"],
            }
            if row["has_unit_rate"]:
                values["x_boq_unit_rate"] = row["unit_rate"]
                # Keep the customer quotation amount populated for BOQ-only lines.
                # Cost Build-up is optional and can later replace this with the
                # rolled-up cost plus tender margin where applicable.
                values["price_unit"] = row["unit_rate"]
            ref_key = _reference_key(row["item_ref"])
            existing = existing_by_ref.get(ref_key)
            if existing:
                existing.with_context(preserve_boq_unit_rate=True).write(values)
                updated += 1
            else:
                create_values = dict(values, x_boq_import_file_id=import_file.id)
                existing_by_ref[ref_key] = self.env["sale.order.line"].with_context(
                    preserve_boq_unit_rate=True
                ).create(create_values)
                created += 1

        self.tender_id._sync_bill_summaries()
        details = "\n".join("Row %s: %s" % item for item in skipped)
        result = _("Created: %s\nUpdated: %s\nSkipped: %s") % (created, updated, len(skipped))
        if details:
            result += "\n\n" + _("Skipped rows:") + "\n" + details
        self.write({"import_done": True, "result_message": result})
        self.tender_id.message_post(body=result.replace("\n", "<br/>"))
        return self._result_action()

    def _result_action(self):
        return {"type": "ir.actions.act_window", "res_model": self._name, "view_mode": "form",
                "res_id": self.id, "target": "new"}
