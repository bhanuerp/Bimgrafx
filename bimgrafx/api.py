import json

import frappe
from frappe.utils import today, date_diff, nowdate


# ---------------------------------------------------------------------------
# Frappe v16 workaround
#
# frappe.core.doctype.user.user.user_query filters on `User.user_type`, which is
# permlevel 1. v16's query engine (Engine.check_filter_field_permission) rejects
# filters on fields above the caller's permlevel and raises PermissionError.
# search_widget catches that and calls respond_as_web_page(http_status_code=404),
# so the Assign To dialog gets an HTML 404 instead of results.
#
# frappe.get_all() runs with ignore_permissions=True, which skips the permlevel
# check. Registered via `standard_queries = {"User": "bimgrafx.api.user_query"}`
# in hooks.py.
#
# TODO: remove this override once frappe/frappe fixes permlevel filtering in
#       user_query, and drop the standard_queries entry from hooks.py.
# ---------------------------------------------------------------------------
@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def user_query(doctype, txt, searchfield, start, page_len, filters):
    """Link-field search for User, bypassing the permlevel-1 filter check."""
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = dict(filters or {})

    # core accepts this flag; it is not a real field
    filters.pop("ignore_user_type", None)

    list_filters = [
        ["enabled", "=", 1],
        ["name", "not in", ["Administrator", "Guest"]],
    ]

    for key, value in filters.items():
        if isinstance(value, (list, tuple)) and len(value) == 2:
            list_filters.append([key, value[0], value[1]])
        else:
            list_filters.append([key, "=", value])

    or_filters = []
    if txt:
        or_filters = [
            ["name", "like", f"%{txt}%"],
            ["full_name", "like", f"%{txt}%"],
        ]

    return frappe.get_all(
        "User",
        filters=list_filters,
        or_filters=or_filters,
        fields=["name", "full_name"],
        limit_start=start,
        limit_page_length=page_len,
        order_by="name asc",
        as_list=True,
    )


def get_hr_managers():
    """Fetch all enabled users having HR Manager role"""
    users = frappe.get_all(
        "Has Role",
        filters={"role": "HR Manager"},
        fields=["parent"]
    )
    user_ids = [u.parent for u in users]
    if not user_ids:
        return []
    emails = frappe.get_all(
        "User",
        filters={
            "name": ["in", user_ids],
            "enabled": 1
        },
        pluck="email"
    )
    return emails


def send_birthday_reminder_hr():
    """Send birthday list to HR Managers, excluding B4 (payroll-only) employees,
    across all companies."""
    report_data = frappe.get_all(
        "Employee",
        fields=["name", "employee_name", "date_of_birth"],
        filters={
            "date_of_birth": ["like", f"%{today()[5:]}"],
            "status": "Active",
            "name": ["not like", "B4%"],
        },
    )

    if not report_data:
        return

    seen = set()
    unique_data = []
    for emp in report_data:
        if emp.name not in seen:
            seen.add(emp.name)
            unique_data.append(emp)
    report_data = unique_data

    recipients = get_hr_managers()
    if not recipients:
        return

    cache_key = f"birthday_reminder_hr_sent_{today()}"
    if frappe.cache().get_value(cache_key):
        return
    frappe.cache().set_value(cache_key, 1, expires_in_sec=24 * 60 * 60)

    rows = ""
    for emp in report_data:
        rows += f"""
        <tr>
            <td>{emp.employee_name}</td>
            <td>{emp.name}</td>
            <td>{emp.date_of_birth}</td>
        </tr>
        """

    message = f"""
    <p>Dear Team,</p>
    <p>Here are the employees who have birthdays today:</p>
    <table border="1" cellpadding="6" cellspacing="0">
        <tr>
            <th>Employee Name</th>
            <th>Employee ID</th>
            <th>Date of Birth</th>
        </tr>
        {rows}
    </table>
    <p>Regards,<br>HR &amp; Admin Department</p>
    """

    frappe.sendmail(
        recipients=recipients,
        subject=f"🎂 Birthday Reminder – {today()}",
        message=message,
    )


def send_birthday_reminders_all_companies():
    """Announce today's birthdays to all active employees across all companies,
    excluding B4 (payroll-only) employees both as recipients and as
    birthday-people announced."""
    birthday_employees = frappe.get_all(
        "Employee",
        fields=["name", "employee_name", "date_of_birth", "user_id", "personal_email", "company_email"],
        filters={
            "date_of_birth": ["like", f"%{today()[5:]}"],
            "status": "Active",
            "name": ["not like", "B4%"],
        },
    )

    if not birthday_employees:
        return

    cache_key = f"birthday_all_company_sent_{today()}"
    if frappe.cache().get_value(cache_key):
        return
    frappe.cache().set_value(cache_key, 1, expires_in_sec=24 * 60 * 60)

    all_employees = frappe.get_all(
        "Employee",
        fields=["name", "user_id", "personal_email", "company_email"],
        filters={
            "status": "Active",
            "name": ["not like", "B4%"],
        },
    )

    birthday_names = {e.name for e in birthday_employees}

    def get_email(emp):
        return emp.get("user_id") or emp.get("company_email") or emp.get("personal_email")

    recipients = list({
        get_email(e) for e in all_employees
        if e.name not in birthday_names and get_email(e)
    })

    if not recipients:
        return

    names = ", ".join(e.employee_name for e in birthday_employees)
    message = f"""
    <p>🎉 Please join us in wishing a very happy birthday to <b>{names}</b> today!</p>
    """

    frappe.sendmail(
        recipients=recipients,
        subject=f"🎂 Birthday Reminder – {today()}",
        message=message,
    )


def send_work_anniversary_reminder():
    """Send work anniversary reminders to all HR Managers, excluding B4 employees."""
    report_data = frappe.db.sql(
        """
        SELECT
            name,
            employee_name,
            date_of_joining,
            FLOOR(DATEDIFF(CURDATE(), date_of_joining) / 365) AS years
        FROM `tabEmployee`
        WHERE
            DATE_FORMAT(date_of_joining, '%%m-%%d') = DATE_FORMAT(CURDATE(), '%%m-%%d')
            AND status = 'Active'
            AND name NOT LIKE 'B4%%'
        """,
        as_dict=True,
    )

    if not report_data:
        return

    recipients = get_hr_managers()
    if not recipients:
        return

    cache_key = f"anniversary_reminder_sent_{today()}"
    if frappe.cache().get_value(cache_key):
        return
    frappe.cache().set_value(cache_key, 1, expires_in_sec=24 * 60 * 60)

    rows = ""
    for emp in report_data:
        rows += f"""
        <tr>
            <td>{emp.employee_name}</td>
            <td>{emp.name}</td>
            <td>{emp.date_of_joining}</td>
            <td>{emp.years} Years</td>
        </tr>
        """

    message = f"""
    <p>Dear Team,</p>
    <p>The following employees are celebrating their work anniversary today:</p>
    <table border="1" cellpadding="6" cellspacing="0">
        <tr>
            <th>Employee Name</th>
            <th>Employee ID</th>
            <th>Date of Joining</th>
            <th>Years Completed</th>
        </tr>
        {rows}
    </table>
    <p>Regards,<br>HR &amp; Admin Department</p>
    """

    frappe.sendmail(
        recipients=recipients,
        subject=f"🎉 Work Anniversary Reminder – {today()}",
        message=message,
    )
