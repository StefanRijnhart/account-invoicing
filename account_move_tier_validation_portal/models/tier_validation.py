# Copyright 2025 360ERP (<https://www.360erp.com>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from odoo import api, fields, models


class TierValidation(models.AbstractModel):
    _inherit = "tier.validation"

    # While potentially only adding to the mess, I cannot with the ambiguity in
    # base_tier_validation between statuses pending/waitng and 'can_approve'.
    # Also, can_approve on tier.validation cannot be searched negatively.
    waiting_for_me = fields.Boolean(
        compute="_compute_status_for_me",
        search="_search_waiting_for_me",
        help=(
            "Indicates if the 'waiting' status applies to the current user, "
            "or if the current user can submit its validation rightaway.",
        ),
    )
    pending_for_me = fields.Boolean(
        compute="_compute_status_for_me",
        search="_search_pending_for_me",
        help=(
            "Indicates if the 'waiting' status applies to the current user, "
            "or if the current user can submit its validation rightaway.",
        ),
    )
    has_portal_validation_access = fields.Boolean(
        compute="_compute_has_portal_validation_access",
        search="_search_has_portal_validation_access",
        help="Implements logic used in record rules",
    )

    def _compute_has_portal_validation_access(self):
        """Indicate if the current user is a reviewer of each document"""
        for record in self:
            record.has_portal_validation_access = (
                self.env.user in record.review_ids.reviewer_ids
            )

    @api.depends_context("uid")
    def _compute_status_for_me(self):
        """Indicate if the current user has to wait or can validate the documents"""
        self.env.cr.execute(
            """
            select tr.res_id, array_agg(tr.status)
            from tier_review tr
            join res_users_tier_review_rel rel
            on rel.tier_review_id = tr.id
            where tr.status in ('waiting', 'pending')
            and tr.model = %(model)s
            and tr.res_id in %(res_ids)s
            and rel.res_users_id = %(user_id)s
            group by tr.res_id;
            """,
            {
                "model": self._name,
                "res_ids": tuple(self.ids or [0]),
                "user_id": self.env.user.id,
            },
        )
        reviews = dict(self.env.cr.fetchall())
        for move in self:
            if move.validation_status in ("pending", "waiting"):
                statuses = reviews.get(move.id, [])
                if "pending" in statuses:
                    move.pending_for_me = True
                    move.waiting_for_me = False
                    continue
                if "waiting" in statuses:
                    move.pending_for_me = False
                    move.waiting_for_me = True
                    continue
            move.pending_for_me = False
            move.waiting_for_me = False

    def _search_status_for_me(self, status, operator, value):
        """Search records that have the given user status"""
        if operator != "=" and value is not True:
            return NotImplementedError
        reviews = self.env["tier.review"].search(
            [
                ("status", "=", status),
                ("model", "=", self._name),
                ("reviewer_ids", "=", self.env.user.id),
            ],
        )
        return [("id", "in", reviews.mapped("res_id"))]

    def _search_pending_for_me(self, operator, value):
        return self._search_status_for_me("pending", operator, value)

    def _search_waiting_for_me(self, operator, value):
        return self._search_status_for_me("waiting", operator, value)

    def _has_portal_validation_access_domain(self):
        """Return a domain that allows portal users access based on tier review"""
        return [("review_ids.reviewer_ids", "=", self.env.user.id)]

    def _search_has_portal_validation_access(self, operator, value):
        """Allow to search for records based on tier review by the current user"""
        if operator not in ("!=", "=") and not isinstance(value, bool):
            return NotImplementedError
        if operator == "!=":
            value = not value
        domain = self._has_portal_validation_access_domain()
        if not value:
            # Inverse domain
            domain = ["!"] + domain
        return domain
