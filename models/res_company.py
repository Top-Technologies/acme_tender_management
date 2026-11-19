from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    tender_edm_user_id = fields.Many2one('res.users', string='Tender EDM', domain="[('share', '=', False)]")
    tender_dm_user_id = fields.Many2one('res.users', string='Tender DM', domain="[('share', '=', False)]")
    tender_dgm_user_id = fields.Many2one('res.users', string='Tender DGM', domain="[('share', '=', False)]")
    tender_gm_user_id = fields.Many2one('res.users', string='Tender GM', domain="[('share', '=', False)]")

    @api.constrains('tender_edm_user_id', 'tender_dm_user_id', 'tender_dgm_user_id', 'tender_gm_user_id')
    def _check_distinct_tender_role_users(self):
        for company in self:
            assigned = [user.id for user in (
                company.tender_dm_user_id, company.tender_dgm_user_id,
                company.tender_gm_user_id,
            ) if user]
            if len(assigned) != len(set(assigned)):
                raise ValidationError(_('DM, DGM, and GM must each have a different configured Odoo user.'))
