from frappe.utils.xlsxutils import XLSXMetadata, XLSXStyleBuilder


def get_row_outline_levels(metadata: XLSXMetadata) -> dict:
	levels = {}
	for row_idx, row in metadata.row_map.items():
		if not isinstance(row, dict):
			continue
		indent = int(row.get("indent") or 0)
		if indent:
			levels[row_idx] = indent
	return levels


def apply_account_indentation(builder, metadata, col_idx=0, pt=3):
	last_row_index = metadata.get_last_row_index()
	skip_last_row = metadata.has_total_row
	indent_style_cache = {}

	for row_idx, row in metadata.row_map.items():
		if not isinstance(row, dict):
			continue
		if skip_last_row and row_idx == last_row_index:
			continue
		indent = int(row.get("indent") or 0)
		if not indent:
			continue
		if indent not in indent_style_cache:
			indent_style_cache[indent] = builder.register_style({"align": "left", "indent": indent * pt})
		builder.style_cell(row_idx, col_idx, indent_style_cache[indent])


def get_financial_statement_xlsx_styles(metadata: XLSXMetadata) -> dict:
	builder = XLSXStyleBuilder(metadata, default_styling=True)
	bold_style = builder.register_style({"bold": True})
	apply_account_indentation(builder, metadata, col_idx=0, pt=3)

	for row_idx, row in metadata.row_map.items():
		if not isinstance(row, dict):
			continue
		account = str(row.get("account") or "").strip()
		clean_account = account.strip("'\"").strip().lower()
		is_group = bool(row.get("is_group"))
		is_total = clean_account.startswith("total")
		is_profit = clean_account in {
			"profit for the year", "profit for the period",
			"net profit", "net profit/loss",
		}
		if is_group or is_total or is_profit:
			builder.style_row(row_idx, bold_style)

	result = builder.result
	result["row_outline_levels"] = get_row_outline_levels(metadata)
	return result