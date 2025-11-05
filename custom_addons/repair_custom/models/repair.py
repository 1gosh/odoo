from random import randint
from datetime import date
import uuid
from odoo import api, Command, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_compare, float_is_zero, clean_context
from odoo.tools.misc import format_date, groupby


class Repair(models.Model):
    """ Repair Orders """
    _name = 'repair.order'
    _description = 'Repair Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority desc, entry_date desc'
    _check_company_auto = True

    @api.model
    def _default_location(self):
       return self.env['repair.pickup.location'].search([('name', '=', 'Boutique')], limit=1).id

    entry_date = fields.Date(
        string="Date d'entrée",
        default=lambda self:date.today(),
        help="Date d'entrée de l'appareil. Par défaut, la date du jour.",
    )
    device_id = fields.Many2one(
        'repair.device',
        string="Appareil",
        help="",
        required=True
    )
    device_picture = fields.Image()
    pickup_location_id = fields.Many2one(
        'repair.pickup.location',
        string="Lieu de prise en charge",
        help="Endroit où l'appareil a été récupéré (boutique ou atelier).",
        required=True,
        default=_default_location
    )
    multiple_devices = fields.Boolean(string="Plusieurs appareils")
    repair_warranty = fields.Selection([('aucune', 'Aucune'), ('sav', 'SAV'), ('sar', 'SAR'),], string="Sous garantie", default='aucune')
    additional_notes = fields.Text(string="Notes additionnelles")
    
    technician_user_id = fields.Many2one(
        'res.users',
        string="Technicien (Utilisateur)",
        readonly=True,
        help="Utilisateur Odoo ayant démarré la réparation."
    )
    technician_employee_id = fields.Many2one(
        'hr.employee',
        string="Technicien",
        readonly=True,
        help="Employé ayant démarré la réparation."
    )

    tracking_token = fields.Char('Tracking Token', default=lambda self: uuid.uuid4().hex, readonly=True)
    tracking_url = fields.Char(
    'Tracking URL',
    compute="_compute_tracking_url"
    )

    @api.depends('tracking_token')
    def _compute_tracking_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for rec in self:
            rec.tracking_url = f"{base_url}/repair/tracking/{rec.tracking_token}"

    name = fields.Char(
        'Repair Reference',
        default='New', index='trigram',
        copy=False, required=True,
        readonly=True)
    company_id = fields.Many2one(
        'res.company', 'Company',
        readonly=True, required=True, index=True,
        default=lambda self: self.env.company)
    state = fields.Selection([
        ('draft', 'New'),
        ('confirmed', 'Confirmed'),
        ('under_repair', 'Under Repair'),
        ('done', 'Repaired'),
        ('cancel', 'Cancelled')], string='Status',
        copy=False, default='draft', readonly=True, tracking=True, index=True,
        help="* The \'New\' status is used when a user is encoding a new and unconfirmed repair order.\n"
             "* The \'Confirmed\' status is used when a user confirms the repair order.\n"
             "* The \'Under Repair\' status is used when the repair is ongoing.\n"
             "* The \'Repaired\' status is set when repairing is completed.\n"
             "* The \'Cancelled\' status is used when user cancel repair order.")
    priority = fields.Selection([('0', 'Normal'), ('1', 'Urgent')], default='0', string="Priority")
    partner_id = fields.Many2one(
        'res.partner', 'Customer',
        index=True, check_company=True, change_default=True,
        help='Choose partner for whom the order will be invoiced and delivered. You can find a partner by its Name, TIN, Email or Internal Reference.')
    user_id = fields.Many2one('res.users', string="Responsible", default=lambda self: self.env.user, check_company=True)
    tag_ids = fields.Many2many('repair.tags', string="Tags")

    # Product To Repair
    lot_id = fields.Many2one(
        'stock.lot', 'Lot/Serial',
        compute="compute_lot_id", store=True,
        domain="[('product_id','=', product_id), ('company_id', '=', company_id)]", check_company=True,
        help="Products repaired are all belonging to this lot")

    # Sale Order Binding
    sale_order_id = fields.Many2one(
        'sale.order', 'Sale Order', check_company=True, readonly=True,
        copy=False, help="Sale Order from which the Repair Order comes from.")
    sale_order_line_id = fields.Many2one(
        'sale.order.line', check_company=True, readonly=True,
        copy=False, help="Sale Order Line from which the Repair Order comes from.")


    def write(self, vals):
        # When going back to draft, clear technician links
        if vals.get('state') == 'draft':
            vals = dict(vals)  # copy to avoid mutating caller's dict
            vals.update({
                'technician_user_id': False,
                'technician_employee_id': False,
            })
        return super(Repair, self).write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_confirmed(self):
        repairs_to_cancel = self.filtered(lambda ro: ro.state not in ('draft', 'cancel'))
        repairs_to_cancel.action_repair_cancel()

    def action_create_sale_order(self):
        if any(repair.sale_order_id for repair in self):
            concerned_ro = self.filtered('sale_order_id')
            ref_str = "\n".join(ro.name for ro in concerned_ro)
            raise UserError(_("You cannot create a quotation for a repair order that is already linked to an existing sale order.\nConcerned repair order(s) :\n") + ref_str)
        if any(not repair.partner_id for repair in self):
            concerned_ro = self.filtered(lambda ro: not ro.partner_id)
            ref_str = "\n".join(ro.name for ro in concerned_ro)
            raise UserError(_("You need to define a customer for a repair order in order to create an associated quotation.\nConcerned repair order(s) :\n") + ref_str)
        sale_order_values_list = []
        for repair in self:
            sale_order_values_list.append({
                "company_id": repair.company_id.id,
                "partner_id": repair.partner_id.id,
                "repair_order_ids": [Command.link(repair.id)],
            })
        self.env['sale.order'].create(sale_order_values_list)
        return self.action_view_sale_order()

    def action_repair_cancel(self):
        if any(repair.state == 'done' for repair in self):
            raise UserError(_("You cannot cancel a Repair Order that's already been completed"))
        return self.write({'state': 'cancel'})

    def action_repair_cancel_draft(self):
        if self.filtered(lambda repair: repair.state != 'cancel'):
            self.action_repair_cancel()
        return self.write({'state': 'draft'})

    def action_repair_done(self):
        return self.write({'state': 'done'})

    def action_repair_end(self):
        if self.filtered(lambda repair: repair.state != 'under_repair'):
            raise UserError(_("Repair must be under repair in order to end reparation."))

        return self.action_repair_done() 

    def action_repair_start(self):
        res = self.write({'state': 'under_repair'})

        user = self.env.user
        employee = self.env['hr.employee'].search([('user_id', '=', user.id)], limit=1)

        self.write({
            'technician_user_id': user.id,
            'technician_employee_id': employee.id if employee else False,
        })

        for repair in self:
            repair.message_post(
            body=_(
                "<b>%s</b> a démarré la réparation le %s."
            ) % (employee.name if employee else user.name, fields.Datetime.now().strftime('%d/%m/%Y à %H:%M')),
            message_type="comment",
            subtype_xmlid="mail.mt_note",  # empêche l'envoi d'email
        )

        return res  

    def _action_repair_confirm(self):
        """ Repair order state is set to 'Confirmed'.
        @param *arg: Arguments
        @return: True
        """
        # repairs_to_confirm = self.filtered(lambda repair: repair.state == 'draft')
        # repairs_to_confirm._check_company()
        # repairs_to_confirm.write({'state': 'confirmed'})
        return self.write({'state': 'confirmed'})  

    def action_validate(self):
        self.ensure_one()

        return self._action_repair_confirm()        

    def action_view_sale_order(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "views": [[False, "form"]],
            "res_id": self.sale_order_id.id,
        }

    def print_repair_order(self):
        return self.env.ref('repair.action_report_repair_order').report_action(self)


class RepairPickupLocation(models.Model):
    _name = 'repair.pickup.location'
    _description = 'Repair Pickup Location'

    name = fields.Char(string="Nom du lieu", required=True)
    street = fields.Char(string="Rue")
    street2 = fields.Char(string="Rue (complément)")
    city = fields.Char(string="Ville")
    zip = fields.Char(string="Code postal")
    country_id = fields.Many2one('res.country', string="Pays")
    contact_id = fields.Many2one('res.partner', string="Contact associé")
    company_id = fields.Many2one(
        'res.company',
        string="Société",
        default=lambda self: self.env.company,
    )

    def _compute_display_name(self):
        for location in self:
            if location.city:
                location.display_name = f"{location.name} – {location.city}"
            else:
                location.display_name = location.name


class RepairTags(models.Model):
    """ Tags of Repair's tasks """
    _name = "repair.tags"
    _description = "Repair Tags"

    def _get_default_color(self):
        return randint(1, 11)

    name = fields.Char('Tag Name', required=True)
    color = fields.Integer(string='Color Index', default=_get_default_color)

    _sql_constraints = [
        ('name_uniq', 'unique (name)', "Tag name already exists!"),
    ]
