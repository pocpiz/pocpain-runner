#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from datetime import datetime, timedelta
import sys
import locale
from concurrent.futures import ThreadPoolExecutor, as_completed

# Définir la locale en français pour les noms de jours/mois
try:
    locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
except:
    pass  # Si la locale française n'est pas dispo, on garde l'anglais

# ----------------------------
# Fonctions utiles
# ----------------------------
def get_options_data(asset):
    """Récupère la liste des instruments options pour l'asset donné"""
    url = f"https://www.deribit.com/api/v2/public/get_instruments?currency={asset}&kind=option"
    response = requests.get(url)
    data = response.json()
    return data['result']

def get_spot_price(asset):
    """Récupère le prix spot actuel de l'asset"""
    url = f"https://www.deribit.com/api/v2/public/ticker?instrument_name={asset}-PERPETUAL"
    try:
        response = requests.get(url, timeout=5).json()
        return response['result']['last_price']
    except:
        return None

def get_open_interest(instrument_name):
    """Récupère le open_interest réel pour un instrument"""
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
    """Filtre les options entre start_date et end_date"""
    expirations = []
    for opt in options:
        exp_dt = datetime.fromtimestamp(opt['expiration_timestamp'] / 1000)
        if start_date <= exp_dt <= end_date:
            expirations.append(opt)
    return expirations

def calculate_max_pain(options_for_date):
    """Calcule max OI call/put et Max Pain pondéré + précision (VERSION PARALLÈLE)"""

    total_opts = len(options_for_date)
    
    # Récupération des OI en PARALLÈLE avec barre de progression
    print(f"Récupération de {total_opts} OI en parallèle...")
    
    oi_dict = {}
    completed = 0
    
    # Utilisation de ThreadPoolExecutor pour paralléliser les requêtes
    with ThreadPoolExecutor(max_workers=20) as executor:
        # Lancer toutes les requêtes en parallèle
        futures = {
            executor.submit(get_open_interest, opt['instrument_name']): opt
            for opt in options_for_date
        }
        
        # Récupérer les résultats au fur et à mesure
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
    
    print()  # fin barre
    
    # Assigner les OI récupérés aux options
    for opt in options_for_date:
        opt['open_interest'] = oi_dict.get(opt['instrument_name'], 0)

    calls = [opt for opt in options_for_date if opt['option_type'] == 'call' and opt['open_interest'] > 0]
    puts  = [opt for opt in options_for_date if opt['option_type'] == 'put'  and opt['open_interest'] > 0]

    if not calls or not puts:
        return None, None, None, None, None, None

    max_call_oi = max(calls, key=lambda x: x['open_interest'])
    max_put_oi  = max(puts,  key=lambda x: x['open_interest'])

    # Max Pain pondéré
    max_pain = (
        max_call_oi['strike'] * max_call_oi['open_interest'] +
        max_put_oi['strike']  * max_put_oi['open_interest']
    ) / (max_call_oi['open_interest'] + max_put_oi['open_interest'])

    # Degré de précision (méthode V5 : concentration ±5%)
    total_oi = sum(opt['open_interest'] for opt in options_for_date)
    if total_oi == 0:
        degree_precision = 0
    else:
        lower = max_pain * 0.95
        upper = max_pain * 1.05
        oi_near = sum(
            opt['open_interest']
            for opt in options_for_date
            if lower <= opt['strike'] <= upper
        )
        degree_precision = round(oi_near / total_oi * 100, 1)

    # Calcul du ratio Put/Call
    total_call_oi = sum(c['open_interest'] for c in calls)
    total_put_oi  = sum(p['open_interest'] for p in puts)
    pc_ratio = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0

    return max_call_oi, max_put_oi, max_pain, degree_precision, total_oi, pc_ratio

# ----------------------------
# Inputs utilisateur
# ----------------------------
print("==== Calcul du Max Pain pondéré basé sur les OI et strikes ====\n")

asset = input("Quel asset (BTC ou ETH) ? ").upper()

print("Quelle période ?")
print("1 → 1 semaine")
print("2 → 15 jours")
print("3 → 3 semaines")
print("4 → 1 mois")
period_choice = input("Choix (1/2/3/4) : ")

today = datetime.now()

if period_choice == "1":
    end_date = today + timedelta(days=7)
elif period_choice == "2":
    end_date = today + timedelta(days=15)
elif period_choice == "3":
    end_date = today + timedelta(days=21)
elif period_choice == "4":
    end_date = today + timedelta(days=30)
else:
    print("Choix invalide, on prend 1 semaine par défaut.")
    end_date = today + timedelta(days=7)

# ----------------------------
# Récupération du prix spot
# ----------------------------
spot_price = get_spot_price(asset)
if spot_price:
    print(f"\n💰 Prix actuel {asset} : {spot_price:,.2f} USD\n")
else:
    print(f"\n⚠️  Impossible de récupérer le prix spot de {asset}\n")

# ----------------------------
# Récupération des options
# ----------------------------
options = get_options_data(asset)
options_in_range = filter_expirations(options, today, end_date)

if not options_in_range:
    print("Pas d'options disponibles pour cette période.")
    exit()

unique_dates = sorted(
    set(datetime.fromtimestamp(opt['expiration_timestamp'] / 1000).date()
        for opt in options_in_range)
)

# ----------------------------
# Calcul et affichage
# ----------------------------
for exp_date in unique_dates:

    options_for_date = [
        opt for opt in options_in_range
        if datetime.fromtimestamp(opt['expiration_timestamp'] / 1000).date() == exp_date
    ]

    print("\n_______________________________________________________________")
    
    # Récupérer l'heure d'expiration depuis Deribit (UTC) et la convertir en heure française
    exp_timestamp = options_for_date[0]['expiration_timestamp'] / 1000
    exp_datetime = datetime.fromtimestamp(exp_timestamp)
    exp_datetime_fr = exp_datetime.strftime('%A %d %B %Y - %H:%M')
    print(f"📅 {exp_datetime_fr} heure française (CET)")
    print()  # Saut de ligne après la date
    
    max_call, max_put, max_pain, precision, total_oi, pc_ratio = calculate_max_pain(options_for_date)

    print(f"Options analysées : {len(options_for_date)}\n")

    if not max_call or not max_put:
        print("Pas d'options exploitables pour cette date.")
        continue

    total_call_oi = sum(c['open_interest'] for c in options_for_date if c['option_type'] == 'call')
    total_put_oi  = sum(p['open_interest'] for p in options_for_date if p['option_type'] == 'put')

    call_pct = round(max_call['open_interest'] / total_call_oi * 100, 1) if total_call_oi else 0
    put_pct  = round(max_put['open_interest']  / total_put_oi  * 100, 1) if total_put_oi  else 0

    # Affichage style Telegram
    print(f"📈 Call max OI : {max_call['strike']:,.1f} (OI={max_call['open_interest']}, {call_pct}%)")
    print(f"📉 Put max OI : {max_put['strike']:,.1f} (OI={max_put['open_interest']}, {put_pct}%)")
    print(f"🎯 Zone Max Pain : {min(max_call['strike'], max_put['strike']):,.1f} – {max(max_call['strike'], max_put['strike']):,.1f}\n")
    
    # MAX PAIN mis en avant avec double saut de ligne
    print()
    print(f"💰 Max Pain pondéré : {max_pain:,.2f} USD")
    print(f"🎲 Précision : {precision}%")
    print()
    print()
    
    # Distance au Max Pain et Ratio P/C (sans icônes redondantes)
    if spot_price:
        distance_pct = ((spot_price - max_pain) / max_pain) * 100
        if distance_pct > 0:
            direction = "(pression baissière)"
        elif distance_pct < 0:
            direction = "(pression haussière)"
        else:
            direction = "(neutre)"
        
        print(f"📍 Distance : {distance_pct:+.2f}% {direction}")
    
    # Ratio Put/Call
    if pc_ratio > 1:
        sentiment = "(sentiment baissier)"
    elif pc_ratio < 1:
        sentiment = "(sentiment haussier)"
    else:
        sentiment = "(sentiment neutre)"
    
    print(f"📊 Ratio P/C : {pc_ratio} {sentiment}")

