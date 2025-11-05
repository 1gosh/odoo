from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class RepairDeviceModel(models.Model):
    _name = "repair.device"
    _description = "Modèle Hi-Fi"
    _order = "brand_id, name"

    name = fields.Char("Nom du modèle", required=True)
    brand_id = fields.Many2one(
        "repair.device.brand",
        string="Marque",
        required=True,
        ondelete="restrict",
    )
    category_id = fields.Many2one(
        "repair.device.category",
        string="Catégorie",
        ondelete="set null"
    )
    production_year = fields.Char("Année de sortie")
    variant = fields.Char("Variante (ex : MKII)")
    wiki_url = fields.Char("Lien HiFi-Wiki")
    image = fields.Image("Image")
    description = fields.Text("Description")

    _sql_constraints = [
        ("unique_brand_model", "unique(brand_id, name)", "Ce modèle existe déjà pour cette marque."),
    ]

    @api.depends("brand_id", "name")
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.brand_id.name or ''} {rec.name or ''}".strip()

    display_name = fields.Char(
        "Nom complet", compute="_compute_display_name", store=True,
    )

    # Saisie intelligente : recherche sur brand + model
    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=80):
        args = args or []
        domain = []
        if name:
            domain = [
                "|",
                ("name", operator, name),
                ("brand_id.name", operator, name),
            ]
        models = self.search(domain + args, limit=limit)
        return models.name_get()

    def name_get(self):
        res = []
        for rec in self:
            name = rec.display_name
            if rec.variant:
                name += f" ({rec.variant})"
            res.append((rec.id, name))
        return res


# --- 1. MARQUES ---------------------------------------------------------

class RepairDeviceBrand(models.Model):
    _name = "repair.device.brand"
    _description = "Marque Hi-Fi"
    _order = "name"

    name = fields.Char("Nom", required=True)
    country = fields.Char("Pays d’origine")
    founded_year = fields.Char("Année de création")
    website = fields.Char("Site web officiel")
    wiki_url = fields.Char("Lien HiFi-Wiki")
    description = fields.Text("Description")
    logo = fields.Image("Logo")

    model_ids = fields.One2many("repair.device", "brand_id", string="Modèles")

    _sql_constraints = [
        ("unique_brand_name", "unique(name)", "Cette marque existe déjà."),
    ]


# --- 2. CATÉGORIES ------------------------------------------------

class RepairDeviceCategory(models.Model):
    _name = "repair.device.category"
    _description = "Catégorie d’appareil Hi-Fi"
    _parent_name = "parent_id"
    _parent_store = True
    _rec_name = "complete_name"
    _order = "complete_name"

    name = fields.Char("Nom", required=True, translate=True, index='trigram')
    complete_name = fields.Char("Nom complet", compute="_compute_complete_name", store=True, recursive=True)
    parent_id = fields.Many2one("repair.device.category", string="Catégorie parente", index=True, ondelete="cascade")
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many("repair.device.category", "parent_id", string="Sous-catégories")
    description = fields.Text("Description")
    icon = fields.Char("Icône FontAwesome", help="Optionnel, pour les vues Kanban")
    device_model_ids = fields.One2many("repair.device", "category_id", string="Modèles de cette catégorie")
    product_count = fields.Integer("# Appareils", compute="_compute_device_count", help="Nombre d’appareils dans cette catégorie (ne compte pas les sous-catégories).")

    # --- Calculs et contraintes ---
    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self):
        for cat in self:
            if cat.parent_id:
                cat.complete_name = f"{cat.parent_id.complete_name} / {cat.name}"
            else:
                cat.complete_name = cat.name

    @api.depends("device_model_ids")
    def _compute_device_count(self):
        for cat in self:
            cat.product_count = len(cat.device_model_ids)

    @api.constrains("parent_id")
    def _check_category_recursion(self):
        if not self._check_recursion():
            raise ValidationError(_("Vous ne pouvez pas créer de hiérarchie récursive."))

    #--- Gestion du nom affiché ---#
    @api.depends_context("hierarchical_naming")
    def _compute_display_name(self):
        if self.env.context.get("hierarchical_naming", True):
            super()._compute_display_name()
        else:
            for record in self:
                record.display_name = record.name

    # @api.model
    # def name_create(self, name):
    #     category = self.create({"name": name})
    #     return category.id, category.display_name


    # @api.ondelete(at_uninstall=False)

    # class RepairOrderModel(models.Model):
    # _inherit = "repair.order"

    # device_id = fields.Many2one(
    #     'repair.device',
    #     string="Lieu de prise en charge",
    #     help="Endroit où l'appareil a été récupéré (boutique ou atelier).",
    #     required=True,
    #     default=_default_location
    # )


class RepairDeviceUnit(models.Model):
    _name = "repair.device.unit"
    _description = "Instance physique d'un appareil"

    device_id = fields.Many2one(
        "repair.device",
        string="Modèle",
        required=True,
        ondelete="restrict",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Propriétaire",
        ondelete="set null",
    )
    serial_number = fields.Char("Numéro de série")
    state = fields.Selection(
        [
            ('new', 'Neuf'),
            ('tb', 'Très bon état'),
            ('good', 'Bon état'),
            ('bad', 'Mauvais état')
        ],
        string="État",
        default='good',
        required=True,
    )
    notes = fields.Text("Notes")
    image = fields.Image("Photo")
    # repair_order_ids = fields.One2many(
    #     "repair.order",
    #     "device_unit_id",
    #     string="Réparations"
    # )
    # repair_count = fields.Integer(
    #     string="Nombre de réparations",
    #     compute="_compute_repair_count"
    # )
    display_name = fields.Char(
        string="Nom complet",
        compute="_compute_display_name",
        store=True
    )

    @api.depends("device_id.brand_id.name", "device_id.name", "serial_number")
    def _compute_display_name(self):
        for rec in self:
            brand = rec.device_id.brand_id.name or ''
            model = rec.device_id.name or ''
            serial = rec.serial_number or ''
            base_name = f"{brand} {model}".strip()
            if serial:
                rec.display_name = f"{base_name} — n° {serial}"
            else:
                rec.display_name = base_name

    @api.depends("repair_order_ids")
    def _compute_repair_count(self):
        for rec in self:
            rec.repair_count = len(rec.repair_order_ids)

    _sql_constraints = [
        ('unique_serial_number', 'unique(serial_number)', 'Le numéro de série doit être unique.'),
    ]
