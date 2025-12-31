#!/usr/bin/env python3
import requests
from datetime import datetime, timedelta
import sys
import locale

try:
    locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
except:
    pass

def get_options_data(asset):
    url = f"https://www.deribit.com/api/v2/public/get_instruments?currency={asset}&kind=option&expired=false"
    response = requests.get(url)
    return response.json()['result']

def get_open_interest(asset, strike, expiry):
    url = f"https://www.deribit.com/api/v2/public/get_order_book?instrument_name={asset}-{strike}-{expiry}"
    response = requests.get(url)
    try:
        return response.json()['result']['underlying_value']
    except:
        return 0

print("==== Calcul du Max Pain pondéré basé sur les OI et strikes ====")

# HARDCODE BTC pour GitHub Actions
asset = "BTC"

print(f"Asset analysé : {asset}")

options = get_options_data(asset)
expiries = sorted(set(opt['expiration_timestamp'] for opt in options))

for exp_timestamp in expiries[:3]:  # 3 premières expirations
    exp_date = datetime.fromtimestamp(exp_timestamp / 1000)
    print(f"\n[{exp_date.strftime('%A %d %B %Y - %H:%M')} ({exp_date.strftime('%Z')})]")
    
    calls = []
    puts = []
    
    for opt in options:
        if opt['expiration_timestamp'] == exp_timestamp:
            oi = get_open_interest(asset, opt['strike'], opt['instrument_name'].split('-')[2])
            if 'C' in opt['instrument_name']:
                calls.append({'strike': opt['strike'], 'oi': oi})
            else:
                puts.append({'strike': opt['strike'], 'oi': oi})
    
    if calls and puts:
        max_call = max(calls, key=lambda x: x['oi'])
        max_put = max(puts, key=lambda x: x['oi'])
        
        total_call_oi = sum(c['oi'] for c in calls)
        total_put_oi = sum(p['oi'] for p in puts)
        
        call_pct = (max_call['oi'] / total_call_oi * 100) if total_call_oi > 0 else 0
        put_pct = (max_put['oi'] / total_put_oi * 100) if total_put_oi > 0 else 0
        
        max_pain = (max_call['strike'] * max_call['oi'] + max_put['strike'] * max_put['oi']) / (max_call['oi'] + max_put['oi'])
        precision = min(call_pct, put_pct)
        
        print(f"Max Call : {max_call['strike']} ({call_pct:.1f}% du total Calls)")
        print(f"Max Put  : {max_put['strike']} ({put_pct:.1f}% du total Puts)")
        print(f"Zone Max Pain approx : {min(max_call['strike'], max_put['strike'])} – {max(max_call['strike'], max_put['strike'])}")
        print(f"Max Pain pondéré : {round(max_pain, 2)} (degré de précision : {precision:.1f}% )")
