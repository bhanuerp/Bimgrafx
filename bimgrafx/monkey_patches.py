"""Runtime monkey patches applied by the bimgrafx app.

These must NOT live in __init__.py: pip builds the app in an isolated
environment where `frappe` is not importable, and any frappe import at
that level breaks installation. apply_patches() is invoked from hooks.py,
which frappe imports once per process (web workers, background workers
and bench commands).
"""

import logging

logger = logging.getLogger(__name__)

_PATCHED = False


def _patch_pl_xlsx_styles():
	"""Override xlsx styling for the Profit and Loss Statement report."""
	try:
		import erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement as pl_report

		from bimgrafx.overrides.pl_xlsx_styles import get_profit_and_loss_xlsx_styles

		pl_report.get_xlsx_styles = get_profit_and_loss_xlsx_styles
	except Exception:
		logger.exception("bimgrafx: failed to patch P&L xlsx styles")


def _patch_financial_statement_xlsx_styles():
	"""Override xlsx styling for Balance Sheet, Cash Flow and Trial Balance."""
	try:
		from bimgrafx.overrides.financial_statement_xlsx_styles import (
			get_financial_statement_xlsx_styles,
		)
	except Exception:
		logger.exception("bimgrafx: failed to import financial statement xlsx styles")
		return

	targets = (
		("balance_sheet", "Balance Sheet"),
		("cash_flow", "Cash Flow"),
		("trial_balance", "Trial Balance"),
	)

	for module_name, label in targets:
		try:
			module = __import__(
				f"erpnext.accounts.report.{module_name}.{module_name}",
				fromlist=["get_xlsx_styles"],
			)
			module.get_xlsx_styles = get_financial_statement_xlsx_styles
		except Exception:
			logger.exception("bimgrafx: failed to patch %s xlsx styles", label)


def _patch_xlsx_grouping():
	"""Replace frappe's make_xlsx with a version that supports row grouping."""
	try:
		import frappe.utils.xlsxutils as xlsxutils

		from bimgrafx.overrides.xlsx_grouping import make_xlsx_with_grouping

		xlsxutils.make_xlsx = make_xlsx_with_grouping
	except Exception:
		logger.exception("bimgrafx: failed to patch make_xlsx for row grouping")


def apply_patches():
	"""Apply all patches once per process. Safe to call repeatedly."""
	global _PATCHED

	if _PATCHED:
		return

	_patch_pl_xlsx_styles()
	_patch_financial_statement_xlsx_styles()
	_patch_xlsx_grouping()

	_PATCHED = True
