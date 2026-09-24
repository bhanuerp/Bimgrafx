"""Replacement for frappe.utils.xlsxutils.make_xlsx (v16 / xlsxwriter) that
turns the `row_outline_levels` key produced by our style builders into real
Excel row groups.

Groups are rendered COLLAPSED on open; the user expands whatever they need
using the +/- controls in the outline gutter.
"""

import functools
from io import BytesIO
from typing import Any

import xlsxwriter
from xlsxwriter.format import Format

from frappe.utils.csvutils import FORMULA_TRIGGER_CHARS
from frappe.utils.xlsxutils import (
	ILLEGAL_CHARACTERS_RE,
	XLSXStyleBuilder,
	get_sanitized_sheet_name,
	handle_html,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Rows at this outline level and deeper start collapsed.
#   1 -> only top-level rows visible (fully collapsed)
#   2 -> first tier stays open, leaf accounts folded away
COLLAPSE_FROM_LEVEL = 1

# Excel supports a maximum of 7 outline levels.
MAX_OUTLINE_LEVEL = 7

RAW_SHEETS = {"Data Import Template", "Data Export"}


# ---------------------------------------------------------------------------
# Outline helpers
# ---------------------------------------------------------------------------


def build_row_outline_options(
	row_outline_levels: dict[int, int],
	total_rows: int,
	collapse_from_level: int = COLLAPSE_FROM_LEVEL,
) -> dict[int, dict]:
	"""Turn {row_index: level} into per-row xlsxwriter set_row() options.

	Children at or below `collapse_from_level` are hidden; the summary row
	directly above each such group carries collapsed=True so Excel draws a
	"+" that the user can click to expand.
	"""

	if not row_outline_levels:
		return {}

	levels = {
		int(idx): min(int(level), MAX_OUTLINE_LEVEL)
		for idx, level in row_outline_levels.items()
		if int(level or 0) > 0
	}

	if not levels:
		return {}

	options: dict[int, dict] = {}

	# 1. Assign outline levels, hiding anything at/below the threshold.
	for row_idx, level in levels.items():
		opt = {"level": level}

		if level >= collapse_from_level:
			opt["hidden"] = True

		options[row_idx] = opt

	# 2. Mark summary rows. A row is a summary row when the next row sits at
	#    a deeper level than it does.
	for row_idx in range(total_rows):
		level = levels.get(row_idx, 0)
		next_level = levels.get(row_idx + 1, 0)

		if next_level > level and next_level >= collapse_from_level:
			options.setdefault(row_idx, {})["collapsed"] = True

	return options


def configure_outline(ws):
	"""Summary rows sit ABOVE their children in financial statements, so the
	+/- control must be drawn on the top row of each group."""
	ws.outline_settings(True, False, False, False)


# ---------------------------------------------------------------------------
# The patched function
# ---------------------------------------------------------------------------


def make_xlsx_with_grouping(
	data: list[list[Any]],
	sheet_name: str,
	wb: xlsxwriter.Workbook | None = None,
	column_widths: list[int] | None = None,
	styles: dict | None = None,
) -> BytesIO | None:
	"""Drop-in replacement for frappe.utils.xlsxutils.make_xlsx.

	Identical to the stock implementation except that it consumes the extra
	`row_outline_levels` key from `styles` and applies row grouping.
	"""

	column_widths = column_widths or []
	styles = styles or {}

	xlsx_file = None
	created_wb = False

	if wb is None:
		xlsx_file = BytesIO()
		options = {"constant_memory": True}

		if not styles:
			options["default_date_format"] = XLSXStyleBuilder.get_datetime_format()

		wb = xlsxwriter.Workbook(xlsx_file, options)
		created_wb = True

	ws = wb.add_worksheet(get_sanitized_sheet_name(sheet_name))

	# --- extract style components ----------------------------------------
	def _extract_ids(key: str) -> dict:
		return {k: tuple(v) for k, v in (styles.get(key) or {}).items() if v}

	style_registry: list[dict] = styles.get("styles") or []
	col_style_ids: dict[int, tuple[int, ...]] = _extract_ids("column_styles")
	row_style_ids: dict[int, tuple[int, ...]] = _extract_ids("row_styles")
	cell_style_ids: dict[tuple[int, int], tuple[int, ...]] = _extract_ids("cell_styles")

	styling_enabled = bool(col_style_ids or row_style_ids or cell_style_ids)

	if not styling_enabled:
		ws.set_row(0, cell_format=wb.add_format({"bold": True}))

	def resolve_style_ids(style_ids: tuple[int, ...]) -> dict:
		if len(style_ids) == 1:
			return style_registry[style_ids[0]]

		result = {}

		for sid in style_ids:
			result.update(style_registry[sid])

		return result

	@functools.cache
	def get_format(style_ids: tuple[int, ...]) -> Format:
		return wb.add_format(resolve_style_ids(style_ids))

	# --- our addition: row grouping options ------------------------------
	rows = data if isinstance(data, list) else list(data)

	row_outline_options = build_row_outline_options(
		styles.get("row_outline_levels") or {},
		total_rows=len(rows),
		collapse_from_level=styles.get("collapse_from_level") or COLLAPSE_FROM_LEVEL,
	)

	if row_outline_options:
		configure_outline(ws)

	# --- column widths ----------------------------------------------------
	for i, column_width in enumerate(column_widths):
		if column_width:
			ws.set_column(i, i, column_width)

	# --- column level styles ---------------------------------------------
	for col_idx, style_ids in col_style_ids.items():
		ws.set_column(col_idx, col_idx, cell_format=get_format(style_ids))

	# --- row level styles + outline options -------------------------------
	# Sorted because constant_memory mode requires writing rows in order, and
	# set_row() must be called before the row's cells are written.
	for row_idx in sorted(set(row_style_ids) | set(row_outline_options)):
		style_ids = row_style_ids.get(row_idx)
		cell_format = get_format(style_ids) if style_ids else None
		row_options = row_outline_options.get(row_idx)

		ws.set_row(row_idx, None, cell_format, row_options or {})

	# --- cell formats: column < row < cell --------------------------------
	cell_formats: dict[tuple[int, int], Format] = {}

	for pos, cell_ids in cell_style_ids.items():
		row_idx, col_idx = pos
		col_ids = col_style_ids.get(col_idx, ())
		row_ids = row_style_ids.get(row_idx, ())

		cell_formats[pos] = get_format(col_ids + row_ids + cell_ids)

	for row_idx, row_ids in row_style_ids.items():
		for col_idx, col_ids in col_style_ids.items():
			pos = (row_idx, col_idx)

			if pos not in cell_formats:
				cell_formats[pos] = get_format(col_ids + row_ids)

	# --- write the data ---------------------------------------------------
	handle_html_content = sheet_name not in RAW_SHEETS
	illegal_chars_search = ILLEGAL_CHARACTERS_RE.search
	illegal_chars_sub = ILLEGAL_CHARACTERS_RE.sub

	write = ws.write
	write_string = ws.write_string
	has_cell_formats = bool(cell_formats)
	get_cell_format = cell_formats.get

	for row_idx, row in enumerate(rows):
		for col_idx, value in enumerate(row):
			is_formula_like = False

			if isinstance(value, str):
				if handle_html_content:
					value = handle_html(value)

				if illegal_chars_search(value):
					value = illegal_chars_sub("", value)

				is_formula_like = value.startswith(FORMULA_TRIGGER_CHARS)

			cell_format = get_cell_format((row_idx, col_idx)) if has_cell_formats else None

			if is_formula_like:
				write_string(row_idx, col_idx, value, cell_format)
			else:
				write(row_idx, col_idx, value, cell_format)

	if not created_wb:
		return

	wb.close()
	xlsx_file.seek(0)

	return xlsx_file
