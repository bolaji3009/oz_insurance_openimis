{
    'name': 'OpenIMIS Insurance Integration',
    'version': '16.0.1.0.0',
    'summary': 'Integration with openIMIS for insurance claim management',
    'description': """
OpenIMIS Insurance Integration
==============================

This module provides integration with openIMIS for managing insurance claims in Odoo 16.
It supports FHIR-based claim submission, eligibility checks, and pricelist parity management.

Key Features:
- Insurance claim flag on invoices/sales orders
- Care setting (OPD/IPD) tracking
- FHIR-based claim submission and status tracking
- Coverage eligibility checks
- Pricelist parity management with openIMIS
- Claim response processing and invoice adjustments
""",
    'category': 'Accounting/Insurance',
    'author': 'Ozone',
    'website': 'https://www.ozone.com',
    'depends': [
        'base',
        'sale',
        'account',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/account_move_views.xml',
        'views/sale_order_views.xml',
        'views/res_config_settings_views.xml',
        'views/pricelist_parity_views.xml',
        'wizard/insurance_eligibility_wizard_views.xml',
        'data/scheduled_actions.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
