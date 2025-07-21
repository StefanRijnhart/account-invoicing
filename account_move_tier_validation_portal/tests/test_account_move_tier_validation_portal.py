# Copyright 2025 360ERP (<https://www.360erp.com>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).
from odoo import Command
from odoo.http import Request
from odoo.tests.common import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingHttpCommon
from odoo.addons.account_move_tier_validation_portal.controllers.portal import (
    PortalAccountMoveTierValidation as ControllerClass,
)
from odoo.addons.website.tools import MockRequest


@tagged("post_install", "-at_install")
class TestAccountMoveTierValidationPortal(AccountTestInvoicingHttpCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        login = "amtv_portal@example.com"
        cls.portal_user = cls.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "password": login,
                "groups_id": [Command.set([cls.env.ref("base.group_portal").id])],
            }
        )
        cls.demo_user = cls.env.ref("base.user_demo")
        cls.demo_user.company_ids += cls.env.company
        cls.account_move_model = cls.env["ir.model"]._get("account.move")
        cls.definition1 = cls.env["tier.definition"].create(
            {
                "model_id": cls.account_move_model.id,
                "definition_domain": "[('move_type', '=', 'in_invoice')]",
                "reviewer_id": cls.env.ref("base.user_demo").id,
                "sequence": 20,
                "has_comment": True,
                "approve_sequence": True,
            }
        )
        cls.definition2 = cls.env["tier.definition"].create(
            {
                "model_id": cls.account_move_model.id,
                "definition_domain": "[('move_type', '=', 'in_invoice')]",
                "reviewer_id": cls.portal_user.id,
                "sequence": 10,
                "has_comment": True,
                "approve_sequence": True,
            }
        )
        cls.company_partner = cls.env["res.partner"].create(
            {
                "name": "Company",
                "is_company": True,
                "email": "company@example.com",
            },
        )
        cls.other_company_partner = cls.env["res.partner"].create(
            {
                "name": "Company",
                "is_company": True,
                "email": "other_company@example.com",
            },
        )
        cls.invoice_partner = cls.env["res.partner"].create(
            {
                "type": "invoice",
                "is_company": False,
                "name": "Invoicing",
                "email": "invoicing@example.com",
                "parent_id": cls.company_partner.id,
            },
        )
        cls.invoice = cls.init_invoice(
            "in_invoice",
            partner=cls.invoice_partner,
            products=cls.product_a,
        )
        cls.other_invoice = cls.init_invoice(
            "in_invoice",
            partner=cls.invoice_partner,
            products=cls.product_a,
        )

    def portal_user_has_access(self, record, operation="read"):
        return record.with_user(self.portal_user).has_access(operation)

    def test_portal_access(self):
        self.assertFalse(self.portal_user_has_access(self.invoice))
        self.assertFalse(self.portal_user_has_access(self.invoice.line_ids))
        self.assertFalse(self.portal_user_has_access(self.company_partner))
        self.assertFalse(self.portal_user_has_access(self.invoice_partner))
        self.assertFalse(self.portal_user_has_access(self.other_company_partner))
        self.assertFalse(self.portal_user_has_access(self.other_invoice))

        self.invoice.request_validation()
        self.assertIn(self.portal_user, self.invoice.review_ids.reviewer_ids)

        # Force a recompute of has_portal_validation_access on the records
        self.env.invalidate_all()

        # Records related to the invoice are now accessible
        self.assertTrue(self.portal_user_has_access(self.invoice))
        self.assertTrue(self.portal_user_has_access(self.invoice.line_ids))
        self.assertTrue(self.portal_user_has_access(self.company_partner))
        self.assertTrue(self.portal_user_has_access(self.invoice_partner))
        self.assertFalse(self.portal_user_has_access(self.other_company_partner))
        self.assertFalse(self.portal_user_has_access(self.other_invoice))

    def test_waiting_for_me(self):
        self.invoice.request_validation()
        self.env.flush_all()
        self.assertTrue(self.invoice.validation_status, "waiting")
        # Demo user needs to be validating first (because its definition has
        # a *higher* priority), so portal user needs to be waiting.
        self.assertTrue(self.invoice.with_user(self.portal_user).waiting_for_me)
        self.assertFalse(self.invoice.with_user(self.portal_user).pending_for_me)
        self.assertFalse(self.invoice.with_user(self.demo_user).waiting_for_me)
        self.assertTrue(self.invoice.with_user(self.demo_user).pending_for_me)
        # Test search method
        self.assertIn(
            self.invoice,
            self.env["account.move"]
            .with_user(self.portal_user)
            .search(
                [("waiting_for_me", "=", True)],
            ),
        )
        self.assertNotIn(
            self.invoice,
            self.env["account.move"]
            .with_user(self.demo_user)
            .search(
                [("waiting_for_me", "=", True)],
            ),
        )
        self.assertNotIn(
            self.invoice,
            self.env["account.move"]
            .with_user(self.portal_user)
            .search(
                [("pending_for_me", "=", True)],
            ),
        )
        self.assertIn(
            self.invoice,
            self.env["account.move"]
            .with_user(self.demo_user)
            .search(
                [("pending_for_me", "=", True)],
            ),
        )

    def test_portal_controllers(self):
        self.authenticate(self.portal_user.login, self.portal_user.login)
        self.invoice.request_validation()
        self.env.flush_all()
        # Submit the first review with comment through backend
        action = self.invoice.with_user(self.demo_user).validate_tier()
        wiz = (
            self.env(user=self.demo_user)[action["res_model"]]  # pylint: disable=context-overridden
            .with_context(action["context"])
            .create({"comment": "Blah"})
        )
        wiz.add_comment()

        controller = ControllerClass()
        # Invoice is provided to the frontend as data
        with MockRequest(self.env(user=self.portal_user)):
            res = controller._prepare_my_invoice_validation_values(0, None, None)
            invoice_data = res["invoices"](0)
        self.assertEqual(len(invoice_data), 1)
        self.assertEqual(invoice_data[0]["invoice"], self.invoice)

        # Frontend can be rendered
        self.url_open("/my/invoice-validation")
        self.url_open(f"/my/invoice-validation/{self.invoice.id}")

        # Review can be submitted
        review = self.invoice.review_ids.filtered(
            lambda tr: tr.reviewer_ids == self.portal_user
        )
        self.assertEqual(review.status, "pending")
        self.url_open(
            f"/my/invoice-validation/submit/{self.invoice.id}",
            data={
                "csrf_token": Request.csrf_token(self),
                "action": "validate",
                "comment": "No biggie",
            },
        )
        self.assertEqual(review.status, "approved")
        self.assertEqual(review.comment, "No biggie")
