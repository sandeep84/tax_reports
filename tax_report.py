import piecash
import argparse
import dateutil

def summarise_account(root_account, prefix=''):
    for account in root_account.children:
        
        account_value = 0
        for split in account.splits:
            tr = split.transaction
            if (tr.post_date >= args.fy_start_date) and (tr.post_date <= args.fy_end_date):
                account_value += split.value

        print(prefix + account.name + ': ' + str(-account_value))

        summarise_account(account, prefix + '    ')

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

summarise_account(income_account)