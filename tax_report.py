import piecash
import argparse
import dateutil
import pprint
from jinja2 import Environment, PackageLoader, select_autoescape
import babel.numbers

def summarise_account(root_account, root_currency, level=0):
    summary = []
    for account in root_account.children:
        account_entry = {
            'name': account.name,
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

        account_entry['children'] = summarise_account(account, root_currency, level+1)
        account_entry['sub_total'] = account_entry['value'] + sum([s['sub_total'] for s in account_entry['children']])
        account_entry['sub_total_in_root_currency'] = account_entry['value_in_root_currency'] + sum([s['sub_total_in_root_currency'] for s in account_entry['children']])
        
        if account_entry["value"] != 0 or len(account_entry["children"]) > 0:
            summary.append(account_entry)

    return summary

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

summary = summarise_account(income_account, root_currency)
pprint.pprint(summary)

env = Environment(
    loader=PackageLoader("tax_report"),
    autoescape=select_autoescape()
)
template = env.get_template("tax_report.html")
template.globals['format_currency'] = babel.numbers.format_currency

with open('tax_report_out.html', 'w') as output_file:
    output_file.write(template.render(summary=summary, root_currency=root_currency.mnemonic))
