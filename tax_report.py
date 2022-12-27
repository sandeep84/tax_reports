import piecash
import argparse
import dateutil
from jinja2 import Environment, PackageLoader, select_autoescape
import babel.numbers
from collections import deque
import copy
import io
from decimal import Decimal

def get_source_account(split):
    sourceAccounts = []
    for other_split in split.transaction.splits:
        if other_split != split:
            if (split.account.type in piecash.core.account.incexp_types and other_split.account.type in piecash.core.account.assetliab_types):
                sourceAccounts.append(other_split.account)

    # Preferably return mutual-fund or stock accounts as the source account
    for account in sourceAccounts:
        if account.type in ['MUTUAL', 'STOCK']:
            return account.fullname

    # Otherwise, just return the first account in the list
    return sourceAccounts[0].fullname

def get_base_currency(commodity):
    if commodity.namespace == 'CURRENCY':
        return commodity

    return commodity.prices[0].currency

def get_exchange_rate(date_, account_currency, root_currency):
    exchange_rate = None

    if account_currency == root_currency:
        exchange_rate = 1
    else:
        for price in account_currency.prices:
            if price.source in ['user:hmrc', 'user:xe'] and price.currency == root_currency and date_.replace(day=1) == price.date:
                exchange_rate = 1/price.value
                break
    
    if exchange_rate is None:
        print(f'WARNING: Unable to find exchange rate ({account_currency.mnemonic} -> {root_currency}) on date {date_.replace(day=1)}')
    return exchange_rate

def insert_account_entry(account_entry, parent_account_entry, summary):
    if parent_account_entry is not None:
        parent_account_entry['children'].append(account_entry)
    else:
        if account_entry['type'] not in summary:
            summary[account_entry['type']] = []
        
        summary[account_entry['type']].append(account_entry)

def calculate_redeemed_split(quantity, purchase_split_entry, sale_split, root_currency):
    redeemed_split = copy.deepcopy(purchase_split_entry)
    redeemed_split['description'] = sale_split.transaction.description
    redeemed_split['sale_date'] = sale_split.transaction.post_date
    redeemed_split['sale_rate'] = sale_split.value / sale_split.quantity

    redeemed_split['purchase_exchange_rate'] = get_exchange_rate(purchase_split_entry['purchase_date'], get_base_currency(sale_split.account.commodity), root_currency)
    if redeemed_split['purchase_exchange_rate'] is not None:
        redeemed_split['purchase_rate_in_root_currency'] = redeemed_split['purchase_rate'] / redeemed_split['purchase_exchange_rate']

    redeemed_split['sale_exchange_rate'] = get_exchange_rate(sale_split.transaction.post_date, get_base_currency(sale_split.account.commodity), root_currency)
    if redeemed_split['sale_exchange_rate'] is not None:
        redeemed_split['sale_rate_in_root_currency'] = redeemed_split['sale_rate'] / redeemed_split['sale_exchange_rate']

    redeemed_split['quantity'] = quantity
    redeemed_split['sale_value'] = quantity * redeemed_split['sale_rate']
    redeemed_split['purchase_value'] = quantity * redeemed_split['purchase_rate']
    redeemed_split['capital_gains'] = redeemed_split['sale_value'] - redeemed_split['purchase_value']

    redeemed_split['sale_value_in_root_currency'] = quantity * redeemed_split['sale_rate_in_root_currency']

    if 'purchase_rate_in_root_currency' in redeemed_split:
        redeemed_split['purchase_value_in_root_currency'] = quantity * redeemed_split['purchase_rate_in_root_currency']
        redeemed_split['capital_gains_in_root_currency'] = redeemed_split['sale_value_in_root_currency'] - redeemed_split['purchase_value_in_root_currency']

    return redeemed_split

def process_capital_gains(account, parent_account_entry, root_currency, summary):
    account_entry = {
        'guid': account.guid,
        'name': account.name,
        'type': account.type,
        'currency': get_base_currency(account.commodity).mnemonic,
        'value': 0,
        'value_in_root_currency': 0,
        'sub_total': 0,
        'sub_total_in_root_currency': 0,
        'splits': [],
        'children': [],
    }

    units = deque()

    splits = sorted(account.splits, key=lambda x: x.transaction.post_date)
    for split in splits:
        #print(f'{split.transaction.post_date}, {split.transaction.description}, {split.quantity}, {split.value}')
        if split.quantity >= 0: # A purchase or a dividend reinvestment
            units.append({
                'purchase_date': split.transaction.post_date,
                'purchase_rate': split.value / split.quantity if split.quantity != 0 else 0,
                'quantity': split.quantity,
            })
        else:
            # A redemption
            quantity = -split.quantity # The quantity to be removed from the oldest splits
            while quantity > 0:
                if units[0]['quantity'] > quantity:
                    # The redemption is a part of the oldest purchase
            
                    if (split.transaction.post_date >= args.fy_start_date) and (split.transaction.post_date <= args.fy_end_date):
                        # Make a copy of the split for reporting
                        redeemed_split = calculate_redeemed_split(quantity, units[0], split, root_currency)
                        account_entry['value'] += redeemed_split['capital_gains']
                        if 'capital_gains_in_root_currency' in redeemed_split:
                            account_entry['value_in_root_currency'] += redeemed_split['capital_gains_in_root_currency']
                        account_entry['splits'].append(redeemed_split)

                    # And modify the original split to remove the redeemed quantity
                    units[0]['quantity'] -= quantity

                    quantity = 0
                else:
                    # The oldest purchase only covers part of the quantity sold
                    # Just pop the original split for reporting
                    purchase_split_entry = units.popleft()
                    if (split.transaction.post_date >= args.fy_start_date) and (split.transaction.post_date <= args.fy_end_date):
                        redeemed_split = calculate_redeemed_split(purchase_split_entry['quantity'], purchase_split_entry, split, root_currency)
                        account_entry['value'] += redeemed_split['capital_gains']
                        if 'capital_gains_in_root_currency' in redeemed_split:
                            account_entry['value_in_root_currency'] += redeemed_split['capital_gains_in_root_currency']
                        account_entry['splits'].append(redeemed_split)

                    quantity -= purchase_split_entry['quantity']

    return account_entry

def process_income_expense_account(account, parent_account_entry, root_currency, summary):
    account_entry = {
        'guid': account.guid,
        'name': account.name,
        'type': account.type,
        'currency': account.commodity.mnemonic,
        'value': 0,
        'value_in_root_currency': 0,
        'sub_total': 0,
        'sub_total_in_root_currency': 0,
        'splits': {},
        'children': [],
    }

    splits = sorted(account.splits, key=lambda x: x.transaction.post_date)
    for split in splits:
        if (split.transaction.post_date >= args.fy_start_date) and (split.transaction.post_date <= args.fy_end_date) and split.value != 0:
            exchange_rate = get_exchange_rate(split.transaction.post_date, account.commodity, root_currency)
            split_entry = {
                'date': split.transaction.post_date,
                'description': split.transaction.description,
                'value': split.value * account.sign,
                'value_in_root_currency': split.value / exchange_rate * account.sign,
                'exchange_rate': exchange_rate,
            }

            category = get_source_account(split)
            account_entry['value'] += split_entry['value']
            account_entry['value_in_root_currency'] += split_entry['value_in_root_currency']

            if category not in account_entry['splits']:
                account_entry['splits'][category] = {
                    'sub_total': 0,
                    'sub_total_in_root_currency': 0,
                    'splits': [],
                }
            account_entry['splits'][category]['splits'].append(split_entry)
            account_entry['splits'][category]['sub_total'] += split_entry['value']
            account_entry['splits'][category]['sub_total_in_root_currency'] += split_entry['value_in_root_currency']
    
    account_entry['sub_total'] = account_entry['value']
    account_entry['sub_total_in_root_currency'] = account_entry['value_in_root_currency']

    return account_entry

def summarise_account(account, parent_account_entry, root_currency, summary, currency_filter):
    if account.type in ['INCOME', 'EXPENSE']:
        account_entry = process_income_expense_account(account, parent_account_entry, root_currency, summary)
    elif account.type in ['ASSET', 'EQUITY', 'STOCK', 'MUTUAL']:
        account_entry = process_capital_gains(account, parent_account_entry, root_currency, summary)
    elif account.type in ['ROOT', 'BANK', 'CASH', 'LIABILITY', 'CREDIT']:
        account_entry = None
    else:
        assert False, f'Unknown account type {account.type} for account named {account.name}'

    force_subtotal_to_zero = False
    for child_account in account.children:
        child_entry = summarise_account(child_account, account_entry, root_currency, summary, currency_filter)
        if account_entry is not None and child_entry is not None:
            if account_entry['currency'] != child_entry['currency']:
                force_subtotal_to_zero = True
                account_entry['sub_total'] = 0
            
            if force_subtotal_to_zero == False:
                account_entry['sub_total'] += child_entry['sub_total']
                
            account_entry['sub_total_in_root_currency'] += child_entry['sub_total_in_root_currency']

    if account_entry is not None \
        and (currency_filter==None or account_entry['currency'] == currency_filter) \
        and (account_entry['sub_total'] != 0 \
            or len(account_entry['children']) > 0
            or len(account_entry['splits']) > 0
        ):
        insert_account_entry(account_entry, parent_account_entry, summary)

    return account_entry

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate tax report')
    parser.add_argument('--book', type=str, help='GNUCash file', default='HomeAccounts.gnucash')
    parser.add_argument('--fy_start_date', type=str, help='Financial year start date', default='04/04/2022')
    parser.add_argument('--fy_end_date', type=str, help='Financial year end date', default='03/04/2023')

    parser.add_argument('--currency', type=str, help='Restrict report to specified currency', default=None)

    args = parser.parse_args()
    args.fy_start_date = dateutil.parser.parse(args.fy_start_date, dayfirst=True).date()
    args.fy_end_date = dateutil.parser.parse(args.fy_end_date, dayfirst=True).date()

    book = piecash.open_book(args.book, readonly=True, open_if_lock=True)
    root_currency = book.root_account.commodity

    summary = {}
    summarise_account(book.root_account, None, book.default_currency, summary, args.currency)
    #pprint.pprint(summary)

    env = Environment(
        loader=PackageLoader("tax_report"),
        autoescape=select_autoescape()
    )
    template = env.get_template("tax_report.html")
    template.globals['format_currency'] = babel.numbers.format_currency

    with io.open('tax_report_out.html', "w", encoding="utf-8") as output_file:
        output_file.write(template.render(summary=summary, root_currency=root_currency.mnemonic))
