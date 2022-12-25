import piecash
import argparse
import dateutil
import csv
from os import listdir
import os.path
from decimal import Decimal
import re

parser = argparse.ArgumentParser(description='Generate tax report')
parser.add_argument('--book', type=str, help='GNUCash file', default='HomeAccounts.gnucash')
parser.add_argument('--exchange_rates_dir', type=str, help='Path with exchange rate CSV files', default='exchange_rates')

args = parser.parse_args()

book = piecash.open_book(args.book, readonly=False)
root_currency = book.root_account.commodity
commodities = [c for c in book.commodities if c.namespace == 'CURRENCY']
currencies = [c.mnemonic for c in book.commodities if c.namespace == 'CURRENCY']


def getValue(dict_value, regex):
    for header in dict_value:
        if re.match(regex, header, re.IGNORECASE):
            return dict_value[header]
    
    return None

for file_name in listdir(args.exchange_rates_dir):
    if not file_name.endswith('.csv'):
        continue
    
    print(f'Parsing file {file_name}')
    with open(os.path.join(args.exchange_rates_dir, file_name), 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        inserted = {}

        for row in reader:
            currency_code = getValue(row, r'Currency\s*Code')
            if currency_code in currencies and not currency_code in inserted:
                exchange_rate = str(1 / float(getValue(row, r'Curre[nc]+y units per.*1')))
                start_date = getValue(row, r'Start Date')

                print(f'{start_date}: Adding price for {currency_code}: {exchange_rate}')
                commodity = book.commodities(mnemonic=currency_code)
                date = dateutil.parser.parse(start_date, dayfirst=True).date()
                inserted[currency_code] = True
                
                skip = float(exchange_rate) <= 1e-4
                for pr in commodity.prices:
                    if (pr.date == date) and (pr.source == 'user:hmrc'):
                        # We already have an entry with this information
                        skip = True
                        break

                if not skip:
                    price = piecash.core.commodity.Price(commodity, root_currency, date, exchange_rate, source='user:hmrc')
                else:
                    print(f'WARNING: Skipping import for price entry for {currency_code} on {date} - {exchange_rate}')

book.save()

for c in commodities:
    print(f'{c.mnemonic}:\n~~~~~~~~~~~~')
    for p in sorted(c.prices, key=lambda x: x.date):
        print(f' - {p.date}: {p.value}, {p.source}')