import piecash
import argparse
import dateutil
import pprint
from jinja2 import Environment, PackageLoader, select_autoescape
import babel.numbers

def insert_account_entry(account_entry, parent_account_entry, summary):
    if parent_account_entry is not None and account_entry['currency'] == parent_account_entry['currency']:
        parent_account_entry['children'].append(account_entry)
    else:
        if account_entry['currency'] not in summary:
            summary[account_entry['currency']] = {}
        if account_entry['type'] not in summary[account_entry['currency']]:
            summary[account_entry['currency']][account_entry['type']] = []
        
        summary[account_entry['currency']][account_entry['type']].append(account_entry)

def summarise_account(account, parent_account, root_currency, summary):
    account_entry = {
        'guid': account.guid,
        'name': account.name,
        'type': account.type,
        'currency': account.commodity.mnemonic,
        'value': 0,
        'value_in_root_currency': 0,
        'sub_total': 0,
        'sub_total_in_root_currency': 0,
        'splits': [],
        'children': [],
    }

    for split in account.splits:
        tr = split.transaction
        if (tr.post_date >= args.fy_start_date) and (tr.post_date <= args.fy_end_date):

            # TODO - FIXME
            exchange_rate = 1

            if account.commodity == root_currency:
                exchange_rate = 1
            else:
                for price in account.commodity.prices:
                    if price.source == 'user:hmrc' and price.currency == root_currency and split.transaction.post_date.replace(day=1) == price.date:
                        exchange_rate = price.value
                        break
            
            split_entry = {
                'date': split.transaction.post_date,
                'description': split.transaction.description,
                'value': -split.value,
                'value_in_root_currency': -split.value / exchange_rate
            }
            account_entry['value'] += split_entry['value']
            account_entry['value_in_root_currency'] += split_entry['value_in_root_currency']
            account_entry['splits'].append(split_entry)
    
    account_entry['sub_total'] = account_entry['value']
    account_entry['sub_total_in_root_currency'] = account_entry['value_in_root_currency']

    if account_entry['value'] != 0 or len(account.children) > 0:
        insert_account_entry(account_entry, parent_account, summary)

        for child_account in account.children:
            child_entry = summarise_account(child_account, account_entry, root_currency, summary)
            if child_account.commodity == account.commodity:
                account_entry['sub_total'] += child_entry['sub_total']
                account_entry['sub_total_in_root_currency'] += child_entry['sub_total_in_root_currency']

    return account_entry

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate tax report')
    parser.add_argument('--book', type=str, help='GNUCash file', default='HomeAccounts.gnucash')
    parser.add_argument('--fy_start_date', type=str, help='Financial year start date', default='04/04/2020')
    parser.add_argument('--fy_end_date', type=str, help='Financial year end date', default='03/04/2021')

    parser.add_argument('--income_account', type=str, help='Income account root (full path)', default='Income:India Income')

    args = parser.parse_args()
    args.fy_start_date = dateutil.parser.parse(args.fy_start_date, dayfirst=True).date()
    args.fy_end_date = dateutil.parser.parse(args.fy_end_date, dayfirst=True).date()

    book = piecash.open_book(args.book, readonly=True, open_if_lock=True)
    root_currency = book.root_account.commodity
    income_account = book.accounts(fullname=args.income_account)

    summary = {}
    summarise_account(book.root_account, None, book.default_currency, summary)
    pprint.pprint(summary)

    env = Environment(
        loader=PackageLoader("tax_report"),
        autoescape=select_autoescape()
    )
    template = env.get_template("tax_report.html")
    template.globals['format_currency'] = babel.numbers.format_currency

    with open('tax_report_out.html', 'w') as output_file:
        output_file.write(template.render(summary=summary, root_currency=root_currency.mnemonic))
