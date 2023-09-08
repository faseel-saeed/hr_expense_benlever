# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re
import logging
import pprint
from markupsafe import Markup
from odoo import api, fields, Command, models, _
from odoo.tools import float_round
from odoo.exceptions import UserError, ValidationError
from odoo.tools import email_split, float_is_zero, float_repr, float_compare, is_html_empty
from odoo.tools.misc import clean_context, format_date


_logger = logging.getLogger(__name__)


class HrExpense(models.Model):
    _inherit = ['hr.expense']

    partner_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        tracking=True,
        check_company=True,
        change_default=True,
        required=True,
        readonly=True,
        states={'draft': [('readonly', False)],
                'refused': [('readonly', False)]},
        ondelete='restrict'
    )


    def _prepare_move_line_vals(self):
        self.ensure_one()
        ref_string = ''
        if self.reference:
            ref_string = '[bill#' + self.reference + '] '

        return {
            'name': ref_string + self.employee_id.name + ': ' + self.name.split('\n')[0][:64],
            'account_id': self.account_id.id,
            'quantity': self.quantity or 1,
            # 'unit_amount' is there when the product selected has a cost defined.
            # This cost will always be in company currency.
            'price_unit': self.unit_amount if self.unit_amount != 0 else self.total_amount_company,
            'product_id': self.product_id.id,
            'product_uom_id': self.product_uom_id.id,
            'analytic_distribution': self.analytic_distribution,
            'expense_id': self.id,
            'partner_id': self.partner_id.id,
            'tax_ids': [Command.set(self.tax_ids.ids)],
            'currency_id': self.company_currency_id.id,
        }

    def get_reference(self):
        return self.reference

    def _get_taxes(self, price, quantity):
        self.ensure_one()
        return self.tax_ids.with_context(force_price_include=True)\
            .compute_all(price_unit=price,
                         currency=self.currency_id,
                         quantity=quantity,
                         product=self.product_id,
                         partner=self.partner_id)


    def _get_default_expense_sheet_values(self):
        # If there is an expense with total_amount_company == 0, it means that expense has not been processed by OCR yet
        expenses_with_amount = self.filtered(lambda expense: not float_compare(expense.total_amount_company, 0.0, precision_rounding=expense.company_currency_id.rounding) == 0)

        if any(expense.state != 'draft' or expense.sheet_id for expense in expenses_with_amount):
            raise UserError(_("You cannot report twice the same line!"))
        if not expenses_with_amount:
            raise UserError(_("You cannot report the expenses without amount!"))
        if len(expenses_with_amount.mapped('employee_id')) != 1:
            raise UserError(_("You cannot report expenses for different employees in the same report."))
        if any(not expense.product_id for expense in expenses_with_amount):
            raise UserError(_("You can not create report without category."))
        if len(expenses_with_amount.mapped('partner_id')) != 1:
            raise UserError(_("You cannot report expenses for different vendors in the same report."))

        # Check if two reports should be created
        own_expenses = expenses_with_amount.filtered(lambda x: x.payment_mode == 'own_account')
        company_expenses = expenses_with_amount - own_expenses
        create_two_reports = own_expenses and company_expenses

        sheets = [own_expenses, company_expenses] if create_two_reports else [expenses_with_amount]
        values = []
        for todo in sheets:
            if len(todo) == 1:
                expense_name = todo.name
            else:
                dates = todo.mapped('date')
                min_date = format_date(self.env, min(dates))
                max_date = format_date(self.env, max(dates))
                expense_name = min_date if max_date == min_date else "%s - %s" % (min_date, max_date)

            vals = {
                'company_id': self.company_id.id,
                'employee_id': self[0].employee_id.id,
                'name': expense_name,
                'expense_line_ids': [Command.set(todo.ids)],
                'state': 'draft',
            }
            values.append(vals)
        return values





class HrExpenseSheet(models.Model):
    _inherit = ['hr.expense.sheet']

    def _prepare_bill_vals(self):
        self.ensure_one()
        res = self._prepare_move_vals()
        partner_id = self.employee_id.sudo().address_home_id.commercial_partner_id.id
        if len(res['line_ids']) > 0:
            partner_id = res['line_ids'][0][2]['partner_id']

        for line in res['line_ids']:
            if partner_id != line[2]['partner_id']:
                raise UserError(_("You cannot report expenses for different vendors in the same report."))

        res.update({
            'journal_id': self.journal_id.id,
            'move_type': 'in_invoice',
            'partner_id': partner_id,
        })
        return res


    def _prepare_move_vals(self):
        self.ensure_one()
        reference = self.name
        if len(self.expense_line_ids) > 0:
            reference = self.expense_line_ids[0].get_reference()

        return {
            # force the name to the default value, to avoid an eventual 'default_name' in the context
            # to set it to '' which cause no number to be given to the account.move when posted.
            'name': '/',
            'date': self.accounting_date or fields.Date.context_today(self),
            'invoice_date': self.accounting_date or fields.Date.context_today(self), # expense payment behave as bills
            'ref': reference,
            'expense_sheet_id': [Command.set(self.ids)],
            'line_ids': [
                Command.create(expense._prepare_move_line_vals())
                for expense in self.expense_line_ids
            ]
        }