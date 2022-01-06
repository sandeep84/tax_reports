import piecash
import argparse
import dateutil
import csv
from os import listdir
import os.path

parser = argparse.ArgumentParser(description='Generate tax report')
parser.add_argument('--book', type=str, help='GNUCash file', default='HomeAccounts.gnucash')
parser.add_argument('--exchange_rates_dir', type=str, help='Path with exchange rate CSV files', default='exchange_rates')

args = parser.parse_args()

book = piecash.open_book(args.book, readonly=False)
root_currency = book.root_account.commodity
commodities = [c for c in book.commodities if c.namespace == 'CURRENCY']
currencies = [c.mnemonic for c in book.commodities if c.namespace == 'CURRENCY']

for file_name in listdir(args.exchange_rates_dir):
    print(f'Parsing file {file_name}')
    with open(os.path.join(args.exchange_rates_dir, file_name), 'r') as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            if row['Currency Code'] in currencies:
                print(f'{row["Start Date"]}: Adding price for {row["Currency Code"]}: {row["Currency units per 1 "]}')
                commodity = book.commodities(mnemonic=row["Currency Code"])
                date = dateutil.parser.parse(row["Start Date"], dayfirst=True).date()
                
                skip = False
                for pr in commodity.prices:
                    if (pr.date == date) and (pr.source == 'user:hmrc'):
                        # We already have an entry with this information
                        skip = True
                        break

                if not skip:
                    price = piecash.core.commodity.Price(commodity, root_currency, date, row["Currency units per 1 "], source='user:hmrc')


book.save()

for c in commodities:
    print(f'{c.mnemonic}:\n~~~~~~~~~~~~')
    for p in c.prices:
        print(f' - {p.date}: {p.value}, {p.source}')