# Copyright 2025 360ERP (<https://www.360erp.com>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    has_portal_validation_access = fields.Boolean(
        compute="_compute_has_portal_validation_access",
        search="_search_has_portal_validation_access",
        help="Implements logic used in record rules",
    )

    def _compute_has_portal_validation_access(self):
        """Assign value to field mainly used for searching"""
        accessible = self.search(self._has_portal_validation_access_domain())
        for record in self:
            record.has_portal_validation_access = record in accessible

    def _has_portal_validation_access_domain(self):
        """Return a domain that allows portal users access based on tier review"""
        invoices = self.env["account.move"].search(
            [("has_portal_validation_access", "=", True)]
        )
        return [("id", "child_of", invoices.commercial_partner_id.ids)]

    def _search_has_portal_validation_access(self, operator, value):
        """Allow to search for records based on tier review by the current user"""
        if operator != "=" and value is not True:
            return NotImplementedError
        return self._has_portal_validation_access_domain()
