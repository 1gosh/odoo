{
    "name": "Repair Devices",
    "version": "17.0.1.0.0",
    "summary": "Catalogue d’appareils Hi-Fi pour les ordres de réparation",
    "depends": [
        "base",
        "repair",          # si tu utilises le module standard
        "repair_custom",   # ton module à toi (change le nom si différent)
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/repair_device_views.xml",
        "views/repair_order_views.xml",
        "views/menu.xml",
    ],
    "application": False,
    "installable": True,
}