# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.


{
    'name': 'Expenses (Benlever fix)',
    'version': '0.1.0',
    'author': 'Benlever Pvt Ltd',
    'company': 'Benelever Pvt Ltd',
    'website': 'https://www.benlever.com',
    'maintainer': 'Benlever Pvt Ltd',
    'category': 'Human Resources/Expenses',
    'sequence': 70,
    'summary': 'Introduces vendor for the expense',
    'description': """
    """,
    'depends': ['hr_contract', 'account', 'hr_expense'],
    'data': [
        'views/hr_expense_views.xml',
    ],
    'installable': True,
    'application': False,
    'assets': {
    },
    'license': 'LGPL-3',
}
