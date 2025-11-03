from odoo import models, api, fields
from odoo.addons.phone_validation.tools import phone_validation

class ResPartner(models.Model):
    _inherit = "res.partner"

    country_id = fields.Many2one(
        'res.country',
        string='Country',
        ondelete='restrict',
        default=lambda self: self.env.ref('base.fr', raise_if_not_found=False)
    )

    @api.onchange('phone', 'country_id', 'company_id')
    def _onchange_phone_auto_format(self):
        """Format automatically the phone number when it is changed"""
        for rec in self:
            if rec.phone:
                formatted = phone_validation.phone_format(
                    rec.phone,
                    (rec.country_id.code or rec.env.company.country_id.code or 'FR'),
                    None,
                    force_format='INTERNATIONAL',
                    raise_exception=False,
                )
                if formatted:
                    rec.phone = formatted

    @api.onchange('mobile', 'country_id', 'company_id')
    def _onchange_mobile_auto_format(self):
        """Format automatically the mobile number when it is changed"""
        for rec in self:
            if rec.mobile:
                formatted = phone_validation.phone_format(
                    rec.mobile,
                    (rec.country_id.code or rec.env.company.country_id.code or 'FR'),
                    None,
                    force_format='INTERNATIONAL',
                    raise_exception=False,
                )
                if formatted:
                    rec.mobile = formatted