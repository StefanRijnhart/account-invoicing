# Copyright 2025 360ERP (<https://www.360erp.com>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
from odoo import fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_share_url(
        self, redirect=False, signup_partner=False, pid=None, share_token=True
    ):
        """Force invoice validation view if access is based on tier reviews.

        This causes links in mails to open in the correct view.
        """
        res = super()._get_share_url(
            redirect=redirect,
            signup_partner=signup_partner,
            pid=pid,
            share_token=share_token,
        )
        if self.has_portal_validation_access:
            res = res.replace("my/invoices", "my/invoice-validation")
        return res

    def get_portal_url_validation(
        self,
        suffix=None,
        report_type=None,
        download=None,
        query_string=None,
        anchor=None,
        submit=False,
    ):
        """Provide urls for the invoice-validation section of the portal"""
        res = super().get_portal_url(
            suffix=suffix,
            report_type=report_type,
            download=download,
            query_string=query_string,
            anchor=anchor,
        )
        slug = "my/invoice-validation"
        if submit:
            slug += "/submit"
        return res.replace("my/invoices", slug)

    def _get_invoice_validation_portal_extra_values(self):
        """Make additional values available on the invoice validation detail screen"""
        self.ensure_one()
        review = self.review_ids.filtered(
            lambda tr: self.env.user in tr.reviewer_ids
        ).sorted("create_date")[:1]
        invoice_label = (
            " - ".join(term for term in [self.name, self.ref] if term) or "-"
        )
        requested_date = (
            fields.Date.context_today(self, review.create_date) if review else False
        )
        return {
            "invoice_label": invoice_label,
            "relation": self.partner_id.display_name,
            "invoice": self,
            "currency": self.currency_id,
            "requested_date": requested_date,
        }

    def _portal_validate_tier(self, action, comment=None):
        """Process validations from the portal"""
        if self.has_comment and not comment:
            raise UserError(self.env._("A comment is required."))
        sequences = self._get_sequences_to_approve(self.env.user)
        reviews = self.review_ids.filtered(
            lambda tr: (tr.sequence in sequences or tr.approve_sequence_bypass)
            and tr.status == "pending"
            and (self.env.user in tr.reviewer_ids)
        )
        if action == "validate":
            self._validate_tier(reviews)
        elif action == "reject":
            self._rejected_tier(reviews)
        else:
            raise UserError(self.env._("Invalid action"))
        if comment:
            reviews.comment = comment
        self._update_counter({"review_deleted": True})
