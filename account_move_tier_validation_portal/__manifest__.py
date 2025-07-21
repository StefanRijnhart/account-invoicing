# Copyright 2025 360ERP (<https://www.360erp.com>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
{
    "name": "Account Move Tier Validation Portal",
    "summary": "Make invoice validation available in the portal",
    "version": "18.0.1.0.0",
    "category": "Accounting/Accounting",
    "website": "https://github.com/OCA/account-invoicing",
    "author": "360 ERP, Odoo Community Association (OCA)",
    "license": "LGPL-3",
    "application": False,
    "installable": True,
    "depends": ["account_move_tier_validation", "portal"],
    "data": [
        "security/ir_rule_data.xml",
        "views/portal_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "/account_move_tier_validation_portal/static/src/scss/*",
        ],
    },
}
