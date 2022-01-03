import piecash
import argparse
import dateutil
import pprint
from jinja2 import Environment, PackageLoader, select_autoescape

def summarise_account(root_account, level=0):
    summary = []
    for account in root_account.children:
        account_entry = {
            'name': account.name,
            'value': 0,
            'splits': [],
            'children': [],
        }

        for split in account.splits:
            tr = split.transaction
            if (tr.post_date >= args.fy_start_date) and (tr.post_date <= args.fy_end_date):
                account_entry['value'] += split.value
                account_entry['splits'].append({
                    'date': split.transaction.post_date,
                    'description': split.transaction.description,
                    'value': split.value,
                })

        account_entry['children'] = summarise_account(account, level+1)
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
income_account = book.accounts(fullname=args.income_account)

summary = summarise_account(income_account)
pprint.pprint(summary)

env = Environment(
    loader=PackageLoader("tax_report"),
    autoescape=select_autoescape()
)
template = env.get_template("tax_report.html")
with open('tax_report_out.html', 'w') as output_file:
    output_file.write(template.render(summary=summary))
