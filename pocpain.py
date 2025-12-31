#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from datetime import datetime, timedelta
import sys
import locale
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
except:
    pass

def get_options_data(asset):
    url = f"https://www.deribit.com/api/v2/public/get_instruments?currency={asset}&kind=option"
    response = requests.get(url)
    data = response.json()
    return data['result']

def get_spot_price(asset):
    url = f"https://www.deribit.com/api/v2/public/ticker?instrument_name={asset}-PERPETUAL"
    try:
        response = requests.get(url, timeout=5).json()
        return response['result']['last_price']
    except:
        return None

def get_open_interest(instrument_name):
    url = f"https://www.deribit.com/api/v2/public/get_book_summary_by_instrument?instrument_name={instrument_name}"
    try:
        response = requests.get(url, timeout=5).json()
        result = response.get('result', [])
        if not result:
            return instrument_name, 0
        return instrument_name, result[0].get('open_interest', 0)
    except:
        return instrument_name, 0

def filter_expirations(options, start_date, end_date):
    expirations = []
    for opt in options:
        exp_dt = datetime.fromtimestamp(opt['expiration_timestamp'] / 1000)
        if start_date <= exp_dt <= end_date:
            expirations.append(opt)
    return expirations

def calculate_max_pain(options_for_date):
    total_opts = len(options_for_date)
    
    print(f"Récupération de {total_opts} OI en parallèle...")
    
    oi_dict = {}
    completed = 0
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {
            executor.submit(get_open_interest, opt['instrument_name']): opt
            for opt in options_for_date
        }
        
        for future in as_completed(futures):
            instrument_name, oi = future.result()
            oi_dict[instrument_name] = oi
            completed += 1
            done = int(30 * completed / total_opts)
            sys.stdout.write(
                '\rRécupération OI : |' +
                '█' * done +
                ' ' * (30 - done) +
                f'| {completed}/{total_opts}'
            )
            sys.stdout.flush()
    
    print()
    
    for opt in options_for_date:
        opt['open_interest'] = oi_dict.get(opt['instrument_name'], 0)

    calls = [opt for opt in options_for_date if opt['option_type'] == 'call' and opt['open_interest'] > 0]
    puts  = [opt for opt in options_for_date if opt['option_type'] == 'put'  and opt['open_interest'] > 0]

    if not calls or not puts:
        return None, None, None, None, None, None

    max_call_oi = max(calls, key=lambda x: x['open_interest'])
    max_put_oi  = max(puts,  key=lambda x: x['open_interest'])

    max_pain = (
        max_call_oi['strike'] * max_call_oi['open_interest'] +
        max_put_oi['strike']  * max_put_oi['open_interest']
    ) / (max_call_oi['open_interest'] + max_put_oi['open_interest'])

    total_oi = sum(opt['open_interest'] for opt in options_for_date)
    if total_oi
