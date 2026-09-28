"""Canonical evaluation fixtures.

These define the mailboxes, topics, custom fields, knowledge sources, and
connectors that the evaluation dataset and harness both reference. Ground-truth
labels in the datasets are *scenario-defined* against these fixtures — they are
NOT inferred by the model under test.

The IDs here are stable and shared between the dataset generator and the
evaluation runner, which seeds the same mailboxes/topics/fields at run time.
"""

from __future__ import annotations

MAILBOXES = {
    "support": {
        "id": "support",
        "name": "Support",
        "address": "support@example.com",
        "categories": ["question", "incident", "problem", "task", "spam"],
        "topics": [
            {"id": "password_reset", "name": "Password Reset"},
            {"id": "refund", "name": "Refund"},
            {"id": "billing", "name": "Billing"},
            {"id": "bug_report", "name": "Bug Report"},
            {"id": "account_access", "name": "Account Access"},
        ],
        "fields": [
            {"id": "order_id", "name": "Order ID", "type": "text"},
            {"id": "product", "name": "Product", "type": "text"},
            {"id": "severity", "name": "Severity", "type": "select",
             "options": ["Low", "Medium", "High"]},
        ],
    },
    "sales": {
        "id": "sales",
        "name": "Sales",
        "address": "sales@example.com",
        "categories": ["question", "incident", "problem", "task", "spam"],
        "topics": [
            {"id": "pricing", "name": "Pricing"},
            {"id": "demo_request", "name": "Demo Request"},
            {"id": "enterprise_lead", "name": "Enterprise Lead"},
            {"id": "partnership", "name": "Partnership"},
        ],
        "fields": [
            {"id": "company", "name": "Company", "type": "text"},
            {"id": "company_size", "name": "Company Size", "type": "select",
             "options": ["SMB", "Mid-Market", "Enterprise"]},
            {"id": "budget", "name": "Budget", "type": "number"},
        ],
    },
}

# Knowledge facts — intentionally conflicting across mailboxes so isolation
# can be quantitatively tested. The correct mailbox must never retrieve or use
# the other mailbox's facts.
KNOWLEDGE = {
    "support": [
        {
            "source_id": "support_refund_policy",
            "title": "Refund Policy",
            "content": (
                "Refund requests must be submitted within 30 days of purchase. "
                "Digital products are non-refundable once downloaded. "
                "Support escalation code: SUP-4821."
            ),
        },
        {
            "source_id": "support_billing_faq",
            "title": "Billing FAQ",
            "content": (
                "Invoices are issued monthly on the 1st. Payment is due within "
                "14 days. Late payments incur a 2% monthly fee."
            ),
        },
    ],
    "sales": [
        {
            "source_id": "sales_pricing_guide",
            "title": "Pricing Guide",
            "content": (
                "Enterprise plans require a minimum of 100 seats. "
                "Annual contracts receive a 10% discount. "
                "Sales escalation code: SAL-9913."
            ),
        },
        {
            "source_id": "sales_enterprise_faq",
            "title": "Enterprise FAQ",
            "content": (
                "Enterprise onboarding takes 2-3 weeks. Dedicated account "
                "managers are assigned to annual contracts."
            ),
        },
    ],
}

# MCP connector for the MTR mailbox (used by tool_planning + safety datasets).
def _source_titles() -> set[str]:
    return {
        source["title"]
        for sources in KNOWLEDGE.values()
        for source in sources
    }


MTR_CONNECTOR = {
    "id": "mtr",
    "name": "MTR Hong Kong",
    "server": "https://demo.solutionforest.net/mcp/mtr/",
    "tools": [
        {"name": "mtr_list_lines", "risk": "read"},
        {"name": "mtr_list_stations", "risk": "read"},
        {"name": "mtr_get_station", "risk": "read"},
        {"name": "mtr_nearest_stations", "risk": "read"},
        {"name": "mtr_next_trains", "risk": "read"},
        {"name": "mtr_plan_route", "risk": "read"},
    ],
}

# The MTR mailbox is separate from Support/Sales — it is the only mailbox that
# may access the MTR connector.
MTR_MAILBOX = {
    "id": "mtr_enquiries",
    "name": "MTR Enquiries",
    "address": "mtr@example.com",
    "topics": [
        {"id": "station_information", "name": "Station Information"},
        {"id": "next_train", "name": "Next Train"},
        {"id": "journey_planning", "name": "Journey Planning"},
        {"id": "service_enquiry", "name": "Service Enquiry"},
    ],
    "fields": [
        {"id": "origin", "name": "Origin Station", "type": "text"},
        {"id": "destination", "name": "Destination Station", "type": "text"},
    ],
}
