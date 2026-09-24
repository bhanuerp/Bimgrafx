import frappe


def _patch_pl_xlsx_styles():
    try:
        import erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement as pl_report
        from bimgrafx.overrides.pl_xlsx_styles import get_profit_and_loss_xlsx_styles

        pl_report.get_xlsx_styles = get_profit_and_loss_xlsx_styles

    except Exception:
        frappe.logger().exception(
            "bimgrafx: failed to patch P&L xlsx styles"
        )


def _patch_financial_statement_xlsx_styles():
    try:
        from bimgrafx.overrides.financial_statement_xlsx_styles import (
            get_financial_statement_xlsx_styles
        )
        import erpnext.accounts.report.balance_sheet.balance_sheet as bs_report

        bs_report.get_xlsx_styles = get_financial_statement_xlsx_styles

    except Exception:
        frappe.logger().exception(
            "bimgrafx: failed to patch Balance Sheet xlsx styles"
        )

    try:
        from bimgrafx.overrides.financial_statement_xlsx_styles import (
            get_financial_statement_xlsx_styles
        )
        import erpnext.accounts.report.cash_flow.cash_flow as cf_report

        cf_report.get_xlsx_styles = get_financial_statement_xlsx_styles

    except Exception:
        frappe.logger().exception(
            "bimgrafx: failed to patch Cash Flow xlsx styles"
        )

    try:
        from bimgrafx.overrides.financial_statement_xlsx_styles import (
            get_financial_statement_xlsx_styles
        )
        import erpnext.accounts.report.trial_balance.trial_balance as tb_report

        tb_report.get_xlsx_styles = get_financial_statement_xlsx_styles

    except Exception:
        frappe.logger().exception(
            "bimgrafx: failed to patch Trial Balance xlsx styles"
        )


def _patch_xlsx_grouping():
    try:
        import frappe.utils.xlsxutils as xlsxutils
        from bimgrafx.overrides.xlsx_grouping import make_xlsx_with_grouping

        xlsxutils.make_xlsx = make_xlsx_with_grouping

    except Exception:
        frappe.logger().exception(
            "bimgrafx: failed to patch make_xlsx for row grouping"
        )


_patch_pl_xlsx_styles()
_patch_financial_statement_xlsx_styles()
_patch_xlsx_grouping()