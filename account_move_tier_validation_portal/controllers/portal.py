# Copyright 2025 360ERP (<https://www.360erp.com>)
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl.html).

from collections import OrderedDict

from odoo import http
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.osv import expression

from odoo.addons.account.controllers.download_docs import (
    _build_zip_from_data,
    _get_headers,
)
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.addons.portal.controllers.portal import pager as portal_pager


class PortalAccountMoveTierValidation(CustomerPortal):
    def _prepare_home_portal_values(self, counters):
        # Add a counter of bills to validate
        values = super()._prepare_home_portal_values(counters)
        if "invoice_validation_count" in counters:
            values["invoice_validation_count"] = self._get_invoice_validation_count()
        return values

    def _get_invoices_domain(self, m_type=None):
        # Exclude invoices based on reviewer status in the standard Invoice portal,
        # just to keep things separate.
        return expression.AND(
            [
                [("has_portal_validation_access", "=", False)],
                super()._get_invoices_domain(m_type=m_type),
            ]
        )

    def _get_invoice_validation_domain(self):
        """The base domain depends on the user being a validator of the invoices"""
        return [
            ("has_portal_validation_access", "=", True),
        ]

    def _get_invoice_validation_count(self):
        return (
            request.env["account.move"].search_count(
                self._get_invoice_validation_domain()
            )
            if request.env["account.move"].has_access("read")
            else 0
        )

    def _get_invoice_validation_searchbar_sortings(self):
        """Add some sorting options"""
        return {
            "date": {"label": request.env._("Date"), "order": "date"},
            "partner_id": {"label": request.env._("Vendor"), "order": "partner_id"},
            "validation_status": {
                "label": request.env._("Validation Status"),
                "order": "validation_status",
            },
        }

    def _get_invoice_validation_searchbar_filters(self):
        """Add some filtering options"""
        return {
            "all": {
                "label": request.env._("All"),
                "domain": [],
            },
            "pending": {
                "label": request.env._("Validation Required"),
                "domain": [
                    ("has_portal_validation_access", "=", True),
                    ("pending_for_me", "=", True),
                ],
            },
            "waiting": {
                "label": request.env._("Waiting on Others"),
                "domain": [
                    ("has_portal_validation_access", "=", True),
                    ("waiting_for_me", "=", True),
                ],
            },
            "rejected": {
                "label": request.env._("Rejected"),
                "domain": [
                    ("has_portal_validation_access", "=", True),
                    ("validation_status", "=", "rejected"),
                ],
            },
        }

    @http.route(
        ["/my/invoice-validation", "/my/invoice-validation/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_invoice_validation(self, page=1, sortby=None, filterby=None, **kw):
        """Main controller"""
        values = self._prepare_my_invoice_validation_values(page, sortby, filterby)

        # pager
        pager = portal_pager(**values["pager"])

        # content according to pager and archive selected
        invoices = values["invoices"](pager["offset"])
        request.session["my_invoice_validation_history"] = [
            i["invoice"].id for i in invoices
        ][:100]

        values.update(
            {
                "invoices": invoices,
                "pager": pager,
            }
        )
        return request.render(
            "account_move_tier_validation_portal.portal_invoice_validation", values
        )

    def _prepare_my_invoice_validation_values(
        self,
        page,
        sortby,
        filterby,
        domain=None,
        url="/my/invoice-validation",
    ):
        """Gather the various parts of the portal section"""
        values = self._prepare_portal_layout_values()
        AccountInvoice = request.env["account.move"]

        domain = expression.AND(
            [
                domain or [],
                self._get_invoice_validation_domain(),
            ]
        )

        searchbar_sortings = self._get_invoice_validation_searchbar_sortings()
        # default sort by order
        if not sortby:
            sortby = "date"
        order = searchbar_sortings[sortby]["order"]

        searchbar_filters = self._get_invoice_validation_searchbar_filters()
        # default filter by value
        if not filterby:
            filterby = "pending"
        domain += searchbar_filters[filterby]["domain"]

        values.update(
            {
                "invoices": lambda pager_offset: (
                    [
                        invoice._get_invoice_validation_portal_extra_values()
                        for invoice in AccountInvoice.search(
                            domain,
                            order=order,
                            limit=self._items_per_page,
                            offset=pager_offset,
                        )
                    ]
                    if AccountInvoice.has_access("read")
                    else AccountInvoice
                ),
                "page_name": "invoice-validation",
                "pager": {  # vals to define the pager.
                    "url": url,
                    "url_args": {
                        "sortby": sortby,
                        "filterby": filterby,
                    },
                    "total": AccountInvoice.search_count(domain)
                    if AccountInvoice.has_access("read")
                    else 0,
                    "page": page,
                    "step": self._items_per_page,
                },
                "default_url": url,
                "searchbar_sortings": searchbar_sortings,
                "sortby": sortby,
                "searchbar_filters": OrderedDict(sorted(searchbar_filters.items())),
                "filterby": filterby,
            }
        )
        return values

    def _invoice_validation_get_page_view_values(self, invoice, access_token, **kwargs):
        """Gather the various parts of the single invoice view"""
        values = {
            "page_name": "invoice-validation",
            **invoice._get_invoice_validation_portal_extra_values(),
        }
        res = self._get_page_view_values(
            invoice,
            access_token,
            values,
            "my_invoice_validation_history",
            False,
            **kwargs,
        )
        if res.get("prev_record"):
            res["prev_record"] = values["prev_record"].replace(
                "my/invoices/", "my/invoice-validation/"
            )
        if res.get("next_record"):
            res["next_record"] = values["next_record"].replace(
                "my/invoices/", "my/invoice-validation/"
            )
        return res

    @http.route(
        ["/my/invoice-validation/<int:invoice_id>"],
        type="http",
        auth="public",
        website=True,
    )
    def portal_my_invoice_validation_detail(
        self, invoice_id, access_token=None, report_type=None, download=False, **kw
    ):
        """Implement the single invoice view controller"""
        try:
            self._document_check_access("account.move", invoice_id, access_token)
        except (AccessError, MissingError):
            return request.redirect("/my")

        # Preserve original user to get a proper value for pending_for_me
        invoice_sudo = request.env["account.move"].browse(invoice_id).sudo()
        if report_type == "pdf":
            # Download the official attachment(s) or a Pro Forma invoice
            docs_data = invoice_sudo._get_invoice_legal_documents_all(
                allow_fallback=True
            )
            if len(docs_data) == 1:
                headers = self._get_http_headers(
                    invoice_sudo, report_type, docs_data[0]["content"], download
                )
                return request.make_response(
                    docs_data[0]["content"], list(headers.items())
                )
            else:
                filename = invoice_sudo._get_invoice_report_filename(extension="zip")
                zip_content = _build_zip_from_data(docs_data)
                headers = _get_headers(filename, "zip", zip_content)
                return request.make_response(zip_content, headers)

        elif report_type in ("html", "pdf", "text"):
            has_generated_invoice = bool(invoice_sudo.invoice_pdf_report_id)
            request.update_context(proforma_invoice=not has_generated_invoice)
            pdf_report_name = (
                invoice_sudo.partner_id.invoice_template_pdf_report_id.report_name
                or "account.account_invoices"
            )
            return self._show_report(
                model=invoice_sudo,
                report_type=report_type,
                report_ref=pdf_report_name,
                download=download,
            )

        values = self._invoice_validation_get_page_view_values(
            invoice_sudo, access_token, **kw
        )
        return request.render(
            "account_move_tier_validation_portal.portal_invoice_validation_page", values
        )

    @http.route(
        ["/my/invoice-validation/submit/<int:invoice_id>"],
        type="http",
        auth="public",
        website=True,
    )
    def portal_my_invoice_validation_submit(self, invoice_id, access_token=None, **kw):
        # Process the validation submitted by the user
        try:
            self._document_check_access("account.move", invoice_id, access_token)
        except (AccessError, MissingError):
            return request.redirect("/my")
        if kw and request.httprequest.method == "POST":
            comment = kw.get("comment")
            action = kw["action"]
            # Preserve original user, because no one else can validate its reviews.
            invoice_sudo = request.env["account.move"].browse(invoice_id).sudo()
            invoice_sudo._portal_validate_tier(action, comment=comment)
        return request.redirect("/my/invoice-validation")
