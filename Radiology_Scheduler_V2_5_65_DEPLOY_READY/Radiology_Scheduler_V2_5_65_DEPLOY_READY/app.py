from __future__ import annotations

import os
import json
import subprocess
import sys
import tempfile
import signal
from copy import deepcopy
import calendar
import html
import unicodedata
import smtplib
import hashlib
import re
import urllib.parse
from statistics import median
from io import BytesIO
from datetime import date, datetime, time, timezone, timedelta
from time import perf_counter
from pathlib import Path
from zoneinfo import ZoneInfo
from email.message import EmailMessage

import pandas as pd
import numpy as np
import streamlit as st
import streamlit.components.v1 as components
import xlsxwriter
from pypdf import PdfReader
from docx import Document
from supabase import create_client

import scheduler_engine as _scheduler_engine
from scheduler_engine import (
    Person, Slot, SolveResult, DEFAULT_PEOPLE, PERSON_COLORS, next_month, weekday_count, round_half_up,
    standard_target, make_slots, solve_schedule, attempt_swap, preview_swap, validate_schedule,
    cohort_october_model, night_xray_duty_active, slot_visible_in_schedule, scheduled_slot_hours, scheduled_slot_clock, is_onko_slot, is_duty_slot, explicit_night_duty_owner, ANNUAL_EXAM_DATES,
    lithuanian_public_holidays, public_holiday_days_in_month, is_public_holiday,
    serialize_result, deserialize_result, revalidate_loaded_result, calculate_targets, blocks_overlap, hard_unavailable_for_block,
    resident_hard_unavailable_for_block, absolute_unavailable_for_block,
    serialize_people_request_snapshot, people_from_request_snapshot,
    ROTATION_CATEGORIES, rotation_category, backup_required_slot, backup_best_effort_slot, weekend_fcfs_backup_mode, weekend_fcfs_backup_slots,
    effective_actual_assignments, calculate_live_fairness_snapshot,
    is_emergency_critical_slot, is_emergency_lower_priority_donor_slot,
    emergency_donor_source_slots, apply_emergency_critical_transfer,
    DEFAULT_RULE_PROFILE, validate_rule_profile, set_runtime_rules, get_runtime_rules, rule_value,
    FATIGUE_MAX_WORKDAYS_ROLLING7, FATIGUE_ROLLING7_HARD_CEILING_HOURS, WEEKLY_LOAD_SOFT_TARGET_HOURS,
    SWAP_ABSOLUTE_MAX_HOURS_ROLLING7, SWAP_MAX_WORKDAYS_ROLLING7, SWAP_MIN_DAILY_REST_HOURS, SWAP_MAX_HOURS_PER_DAY
)
import db
from extension_core import load_extension as load_optus_extension, extension_summary as optus_extension_summary, solve_extension_preview as solve_optus_extension_preview, ExtensionError as OptusExtensionError
from opto_research import (
    parse_extension_upload as parse_opto_extension_upload,
    extension_template_xlsx as opto_extension_template_xlsx,
    preferences_template_xlsx as opto_preferences_template_xlsx,
    parse_preferences_excel as parse_opto_preferences_excel,
    apply_preferences as apply_opto_preferences,
    schedule_template_xlsx as opto_schedule_template_xlsx,
    parse_schedule_excel as parse_opto_schedule_excel,
    solve_rapa_extension as solve_rapa_extension_research,
    evaluate_schedule as evaluate_opto_schedule,
    comparison_dataframe as opto_comparison_dataframe,
    comparison_xlsx as opto_comparison_xlsx,
    assignments_dataframe as opto_assignments_dataframe,
)
from notification_core import smtp_config as _smtp_config_core, smtp_missing as _smtp_missing_core, smtp_probe as _smtp_probe_core, send_email as _send_email_core

ENGINE_API_VERSION = str(getattr(_scheduler_engine,"ENGINE_API_VERSION","LEGACY_OR_UNKNOWN"))
APP_VERSION = "2.5.166 GENERATION UX"
EXPECTED_ENGINE_API_VERSION = "2.5.165"
COMPATIBLE_ENGINE_API_VERSIONS = {"2.5.165"}

# V2.5.139: import-safe reward credit compatibility. Older deployed engines used
# by the same app already contain the scheduling API but predate the credit helpers.
# Keep the app bootable and use the exact same coefficient formula locally.
def _fallback_reward_credit_units_for_shift(year: int, month: int, day: int, block: str) -> int:
    b = str(block or "").upper()
    d0 = date(int(year), int(month), int(day))
    d1 = d0 + timedelta(days=1)
    h0 = is_public_holiday(d0.year, d0.month, d0.day)
    h1 = is_public_holiday(d1.year, d1.month, d1.day)
    day_mult0 = 2 if h0 else 1
    day_mult1 = 2 if h1 else 1
    night_mult0 = 3 if h0 else 2
    night_mult1 = 3 if h1 else 2
    if b in ("AM", "PM"):
        return 6 * day_mult0
    if b == "FULL":
        return 12 * day_mult0
    if b == "NIGHT":
        return 2 * day_mult0 + 2 * night_mult0 + 6 * night_mult1 + 2 * day_mult1
    raise ValueError(f"Unsupported reward-credit shift block: {block}")

def _fallback_reward_credit_value(units: int) -> float:
    return float(units) / 12.0

reward_credit_units_for_shift = getattr(
    _scheduler_engine, "reward_credit_units_for_shift", _fallback_reward_credit_units_for_shift
)
reward_credit_value = getattr(
    _scheduler_engine, "reward_credit_value", _fallback_reward_credit_value
)

DRAFT_COMPATIBILITY_VERSION = "2.5.150"
BASE = Path(__file__).parent
SENIOR_INITIALS = "SP"
RESEARCHER_INITIALS = "ŠR"
WESTON_CREDITOR_INITIALS = RESEARCHER_INITIALS  # SP generation clicks are owed to ŠR
EMAIL_LIFECYCLE_ENABLED = False  # V2.5.119: email removed from operational workflow; RAPA will use in-app/push
DEFAULT_SUPABASE_URL = "https://gqdlwhjgwqmuoolybusy.supabase.co"
DEFAULT_SUPABASE_PUBLISHABLE_KEY = "sb_publishable_kHX4M55rZoHJr61S9kzdLg_tgKN-oDI"
DEFAULT_MANUAL_LT = (BASE / "manual_lt.md").read_text(encoding="utf-8")
DEFAULT_MANUAL_EN = DEFAULT_MANUAL_LT
SENIOR_GUIDE_LT = (BASE / "SENIOR_USABILITY_GUIDE_LT.md").read_text(encoding="utf-8")
SENIOR_GUIDE_EN = SENIOR_GUIDE_LT

db.init_db(DEFAULT_MANUAL_LT, DEFAULT_MANUAL_EN, DEFAULT_PEOPLE)

st.set_page_config(page_title="Shift Happens", layout="wide", initial_sidebar_state="expanded")

if str(ENGINE_API_VERSION) not in COMPATIBLE_ENGINE_API_VERSIONS:
    st.error(
        "Nesuderinta programos ir planavimo variklio versija. "
        f"Programai tinka {sorted(COMPATIBLE_ENGINE_API_VERSIONS)}, "
        f"bet įkelta {ENGINE_API_VERSION}. Įkelkite app.py ir scheduler_engine.py iš to paties leidimo."
    )
    st.stop()
st.markdown("""
<style>
html, body, [class*="css"] {font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}
.block-container {max-width:1550px;padding-top:1.6rem;}
h1 {font-weight:720!important;letter-spacing:-.025em;}
h2,h3 {font-weight:650!important;letter-spacing:-.015em;}
div[data-testid="stMarkdownContainer"] p, div[data-testid="stMarkdownContainer"] li {line-height:1.58;}
div[data-testid="stMetric"] {border:1px solid rgba(128,128,128,.22);padding:10px 14px;border-radius:10px;}
.deadline-card {border:1px solid rgba(128,128,128,.25);border-radius:12px;padding:12px 16px;margin:8px 0 18px 0;}
</style>
""", unsafe_allow_html=True)

TR = {
"LT": {
"language":"Kalba","user":"Vartotojas","profile":"Profilis","resident_profile":"Rezidento profilis","senior_profile":"Seniūnės profilis",
"resident_pin":"Asmeninis PIN","admin_pin":"Seniūnės PIN","local_resident":"Vietinis testavimo režimas: asmeniniai PIN nesukonfigūruoti.",
"local_senior":"Vietinis testavimo režimas: seniūnės profilis atrakintas tik seniūnės paskyrai.","bad_pin":"Neteisingas PIN.",
"login_title":"Prisijungimas","login":"PRISIJUNGTI","logout":"ATSIJUNGTI","signup":"SUKURTI PASKYRĄ","signup_title":"Pirma registracija","password":"Slaptažodis","password_repeat":"Pakartokite slaptažodį","auth_email":"El. paštas","auth_invalid":"Nepavyko prisijungti. Patikrinkite el. paštą ir slaptažodį.","forgot_password":"Pamiršau slaptažodį?","forgot_password_help":"Įveskite paskyros el. paštą. Jei tokia paskyra egzistuoja, atsiųsime saugią nuorodą naujam slaptažodžiui nustatyti.","forgot_password_send":"SIŲSTI ATKŪRIMO NUORODĄ","forgot_password_sent":"Jei paskyra su šiuo el. paštu egzistuoja, atkūrimo nuoroda išsiųsta. Patikrinkite ir SPAM / Šlamšto aplanką.","forgot_password_bad_email":"Įveskite galiojantį el. pašto adresą.","forgot_password_rate_limit":"Atkūrimo laiškų limitas laikinai pasiektas. Pabandykite vėliau.","forgot_password_error":"Atkūrimo laiško išsiųsti nepavyko. Pabandykite dar kartą arba kreipkitės į administratorių.","signup_sent":"Paskyra sukurta. Jei el. pašto patvirtinimas įjungtas, patvirtinkite laišką ir tada prisijunkite.","signup_password_mismatch":"Slaptažodžiai nesutampa.","claim_title":"Susiekite paskyrą","resident_claim_tab":"Rezidentas","observer_claim_tab":"Skyriaus administratorė / stebėtoja","observer_claim_help":"Ši paskyra skirta skyriaus administracinei peržiūrai. Ji yra tik skaitymui: galima matyti paskelbtą ir aktualų grafiką, apsikeitimus, dublius, teisingumą ir auditą, bet negalima nieko keisti.","observer_invite_code":"Skyriaus stebėtojo kvietimo kodas","observer_claim":"AKTYVUOTI TIK PERŽIŪROS PRIEIGĄ","observer_read_only":"TIK PERŽIŪRA","observer_role":"Skyriaus stebėtojas","observer_portal":"Skyriaus grafiko stebėsena","observer_overview":"Apžvalga","observer_schedule":"Grafikai","observer_changes":"Pakeitimų žurnalas","observer_fairness":"Teisingumas","observer_backups":"Dubliai","observer_rules":"Taisyklės","observer_scope_note":"Ši paskyra negali generuoti, publikuoti, tvirtinti, keisti ar anuliuoti grafikų ir apsikeitimų.","observer_privacy_note":"Nerodomi privatūs rezidentų pageidavimai, privalomo negalėjimo datos, asmeninės pastabos, el. paštai ar paskyrų nustatymai.","observer_baseline_schedule":"Sistemos pradinis grafikas — paskelbimo momentu","observer_actual_schedule":"Faktinis grafikas — dabar","observer_change_count":"Pakeistų normalių pamainų","observer_normal_swaps":"Normalių pamainų apsikeitimai","observer_backup_swaps":"Dublių apsikeitimai","observer_pending_swaps":"Laukiantys","observer_approved_swaps":"Patvirtinti","observer_rejected_swaps":"Atmesti","observer_no_changes":"Po paskelbimo normalių pamainų pakeitimų nėra.","observer_from":"Buvo","observer_to":"Dabar","observer_change_log_help":"Sistemos pradinis grafikas lieka teisingumo apskaitai. Faktinis grafikas rodo realią situaciją po abipusių savanoriškų apsikeitimų.","observer_backup_status":"Būsena","observer_planned_backup":"Planuotas dublis","observer_actual_backup":"Faktinis dublis","observer_activated":"Aktyvuotas","observer_completed":"Realiai pavadavo","observer_no_schedule":"Šiam mėnesiui dar nėra paskelbto grafiko.","observer_access_ready":"Tik peržiūros skyriaus prieiga aktyvuota.","claim_help":"Pasirinkite tik savo inicialus ir įveskite jums skirtą vienkartinį beta kvietimo kodą.","invite_code":"Kvietimo kodas","claim":"SUSIETI PASKYRĄ","claim_failed":"Paskyros susieti nepavyko. Patikrinkite inicialus ir kvietimo kodą.","account_unlinked":"Prisijungėte, bet ši paskyra dar nesusieta su rezidentu.",
"app_title":"Rezidentų grafiko sistema","app_caption":"Rezidentų grafiko planavimas, pageidavimai, dubliai ir kontroliuojami pakeitimai.",
"year":"Metai","month":"Mėnuo","weekdays":"Darbo dienos","base_target":"Bazinis pamainų tikslas",
"deadline":"Pageidavimų pateikimo terminas","days_left":"Liko dienų","deadline_today":"Šiandien paskutinė diena.","deadline_passed":"Terminas praėjo prieš {n} d.",
"deadline_future":"Iki termino liko {n} d.","deadline_note":"Kito mėnesio pageidavimus galima pildyti iki ankstesnio mėnesio 14 d. 00:00. Iki to laiko pateiktus pageidavimus galima koreguoti.",
"preferences":"Pageidavimai","settings":"Nustatymai","special_days":"Specialios dienos","generation":"Sudarymas","schedule":"Grafikas",
"summary":"Suvestinė","transparency":"Skaidrumas","credits_debts":"Kreditai","backups":"Dubliai","swaps":"Swap","calendar":"Kalendorius","proof":"Patikra","senior_guide":"Seniūnės vadovas","rules":"Taisyklės",
"my_preferences":"Mano mėnesio pageidavimai","hard_unavailable":"Dirbti negaliu","hard_help":"Pažymėkite visą dieną arba tik rytą / popietę. Tuo metu sistema jūsų į darbą neskirs. Jei pažymite tik dalį dienos, kitu dienos metu vis tiek galite būti paskirtas dirbti.","hard_all_day":"Visa diena","hard_morning":"Rytas (08:00–14:00)","hard_afternoon":"Popietė (14:00–20:00)","hard_partial_note":"Jei pažymite rytą arba popietę, kitu paros bloku vis tiek galite būti paskirtas į normalią pamainą arba būti dubliu.","hard_overlap":"Ta pati data negali būti kartu pažymėta kaip visa diena ir dalinis privalomas negalėjimas.",
"soft_free":"Noriu laisvos","soft_help":"Pasirinkite visą dieną, rytą arba popietę. Sistema stengsis šį pageidavimą įvykdyti kuo geriau, kartu išlaikydama saugų ir teisingą grafiką.","soft_overlap":"Ta pati data negali būti kartu pažymėta kaip visa diena ir dalinis noras būti laisvam.",
"preferred":"Pageidauju dirbti","preferred_help":"Pasirinkite visą dieną, rytą arba popietę. Sistema stengsis atsižvelgti į norą dirbti. Savaitgaliui galima pasirinkti tik vieną konkrečią šeštadienio arba sekmadienio datą per mėnesį.","preferred_overlap":"Ta pati data negali būti kartu pažymėta kaip visa diena ir dalinis pageidavimas dirbti.","vacation":"Atostogos — patvirtintos nedarbo dienos","vacation_help":"Pažymėkite patvirtintas atostogų dienas. Tomis dienomis sistema jūsų neskirs dirbti ar dubliuoti ir proporcingai sumažins mėnesio darbo tikslą, kad atostogos nebūtų laikomos teisingumo trūkumu.","vacation_overlap":"Ta pati diena pažymėta ir kaip atostogos, ir kaip kitas pateisinamas neatvykimas — palikite ją tik viename laukelyje.","note":"Papildomas komentaras","note_ph":"Pvz. po kelių dienų iš eilės nenorėčiau dvigubos pamainos.",
"save":"Išsaugoti","saved":"Išsaugota.","hard_conflict":"Pageidavimas dirbti kertasi su privalomu negalėjimu dirbti tuo pačiu laiku.","soft_conflict":"„Noriu laisvos“ ir „Pageidauju dirbti“ negali būti pasirinkti tam pačiam laikui.",
"all_preferences":"Visų rezidentų pageidavimai","preference_load":"Pageidavimų apimtis","review":"Peržiūrėti","normal":"Įprasta","visibility_flag":"Žyma „Peržiūrėti“ yra tik seniūnės dėmesio indikatorius, ne bauda ir ne automatinis apribojimas.",
"submitted":"Pateikta","updated":"Atnaujinta","hard_dates":"Negaliu dirbti — visa diena","hard_am_dates":"Negaliu dirbti — rytas","hard_pm_dates":"Negaliu dirbti — popietė","soft_dates":"Noriu laisvos — visa diena","soft_am_dates":"Noriu laisvos — rytas","soft_pm_dates":"Noriu laisvos — popietė","preferred_dates":"Pageidauju dirbti — visa diena","preferred_am_dates":"Pageidauju dirbti — rytas","preferred_pm_dates":"Pageidauju dirbti — popietė","comment":"Komentaras",
"settings_title":"Mano paskyros ir darbo pobūdžio nustatymai","short_term":"Trumpalaikiai mėnesio pageidavimai","legal_safety_inputs":"Darbas kitur","justified_absence":"Pateisinamas neatvykimas","justified_absence_help":"Ši funkcija naudojama tik po grafiko paskelbimo. Ji keičia faktinį ACTUAL grafiką, bet neperrašo pradinio SYSTEM fairness.","long_duty":"Ilgas / naktinis budėjimas kitur","long_duty_help":"Pažymėkite iš anksto žinomo ilgo ar naktinio budėjimo kitur pradžios datą. RAPA pati šio darbo nemato, todėl pagal šią datą apsaugo kitą dieną poilsiui. Jei budėjimą planuoja pati RAPA, jo čia žymėti nereikia.","labour_hard_summary":"RAPA automatiškai saugo poilsį ir darbo krūvį. Čia reikia įvesti tik darbą, kurio sistema pati nemato.","labour_scope_note":"RAPA gali įvertinti tik jai žinomą darbo laiką. Įveskite ilgus / naktinius budėjimus kitur, kad planuojant būtų palikta pakankamai poilsio.","long_term":"Ilgalaikiai pasikartojantys pageidavimai","long_term_help":"Šie nustatymai automatiškai taikomi kiekvienam mėnesiui, kol juos pakeisite. Konkretaus mėnesio pasirinkimas turi pirmenybę prieš priešingą ilgalaikį pageidavimą. Jei ilgalaikėje taisyklėje pažymite, kad dirbti negalite, tuo metu sistema jūsų neskirs.","weekday_name":"Savaitės diena","recurring_rule":"Pasikartojanti taisyklė","recurring_time":"Laikas","rec_none":"Nėra","rec_hard":"Dirbti negaliu","rec_soft":"Noriu laisvos","rec_preferred":"Pageidauju dirbti","save_long_term":"IŠSAUGOTI ILGALAIKIUS PAGEIDAVIMUS","long_term_saved":"Ilgalaikiai pageidavimai išsaugoti.","email":"El. paštas","email_required":"Kiekvienoje paskyroje turi būti galiojantis el. pašto adresas.",
"shift_length_pref":"Pageidaujama darbo dienos trukmė","shift_length_help":"Ilgalaikis privatus darbo pobūdžio pasirinkimas. Sistema stengiasi formuoti darbo dienų trukmę pagal jūsų pasirinkimą, jei tai leidžia privalomos taisyklės, poilsio reikalavimai ir mėnesio darbo krūvis. Onko RO lieka atskira 9 val. pilnos dienos pamaina.","shift_length_any":"Nesvarbu","shift_length_6":"Dažniausiai 6 val.","shift_length_mixed":"Mišriai – tinka ir 6 val., ir 12 val. darbo dienos","shift_length_12":"Dažniausiai 12 val.","weekday_pref":"Darbo dienų pobūdis","weekend_pref":"Savaitgalių pobūdis","holiday_pref":"Švenčių dienos","holiday_pref_help":"Ilgalaikis pasirinkimas oficialioms Lietuvos švenčių dienoms. Sistema pirmiausia skiria šventinį darbą norintiems, po jų — neutraliems, o norinčius ilsėtis naudoja tik kai reikia. Tarp vienodai pasirinkusių žmonių šventinis darbas paskirstomas kuo tolygiau, atsižvelgiant ir į ankstesnius mėnesius.","holiday_rest":"Norėčiau ilsėtis per šventes","holiday_neutral":"Neutralu / nesvarbu","holiday_work":"Norėčiau dirbti per šventes","spread_pref":"Pamainų išdėstymas","avoid_double_shifts":"Jei įmanoma, vengti dvigubų pamainų",
"weekday_help":"−2 = santykinai mažiau darbo dienomis, 0 = nesvarbu, +2 = santykinai daugiau.","weekend_help":"−2 = mažiau savaitgalių, 0 = nesvarbu, +2 = daugiau.",
"spread_help":"−2 = labiau sutelktas grafikas, 0 = nesvarbu, +2 = labiau išsklaidytas.","notifications":"Pranešimai","notifications_on":"Gauti el. pašto priminimus apie pageidavimų pateikimo termino pabaigą","notification_default":"Pagal nutylėjimą pranešimai įjungti.",
"reminder_start":"Asmeninių priminimų pradžia (mėnesio diena)","reminder_help":"Parodo, nuo kurios mėnesio dienos pradėsite gauti asmeninius el. pašto priminimus apie savo artėjantį grafiką, jei dar nebūsite pateikę pageidavimų. Pvz.: „Liko 4 dienos iki pageidavimų pateikimo pabaigos.“ Priminimai sustoja, kai pageidavimai pateikiami arba terminas pasibaigia.","include_backups_calendar":"Rodyti dublius mano .ics kalendoriuje","backup_email_alerts":"Gauti el. laišką, kai seniūnė aktyvuoja mano dublį","phone_optional":"Telefono numeris SMS pranešimams (pasirinktinai)","sms_future":"SMS pranešimai paruošti nustatymuose, bet beta versijoje dar nesiunčiami.","backup_sms_alerts":"Gauti SMS, kai aktyvuojamas dublis","backup_activation":"Dublio aktyvavimas","activate_backup":"KVIESTI DUBLĮ DABAR","backup_activated":"Dublis aktyvuotas.","backup_email_sent":"El. pranešimas dubliui išsiųstas.","backup_email_failed":"Dublis aktyvuotas, bet el. laiško išsiųsti nepavyko.","undo_activation":"ATŠAUKTI DUBLIO AKTYVAVIMĄ","activation_undone":"Dublio aktyvavimas atšauktas.","smtp_admin_note":"Siunčiančio pašto slaptažodis yra vienas bendras sistemos secret ir jo rezidentai neįveda.","settings_saved":"Nustatymai išsaugoti.","backup_bonus":"Dublių bonusai","bonus_balance":"Sukaupti dublių bonusai","bonus_help":"Kai realiai pavaduojate kitą rezidentą, gaunate POILSIO kreditą kaip naudą būsimam mėnesiui. Pavaduotam žmogui jokia skola nesukuriama. RYTAS, POPIETĖ ir NAKTIS apskaitomi atskirai.","use_bonus":"Šį mėnesį panaudoti bonusų","bonus_target_effect":"Per vieną mėnesį galima panaudoti daugiausia 2 dieninius poilsio kreditus iš viso. RYTO ir POPIETĖS kreditai apskaitomi atskirai; NAKTIES kreditas dabartinio PGY1 dieninio targeto nemažina.","bonus_insufficient":"Pasirinkta daugiau bonusų nei turite sukaupę.",
"dashboard_title":"Seniūnės mėnesio kontrolės skydas","completion":"Pageidavimų užpildymas","missing_preferences":"Dar nepateikė","missing_email":"Nenurodė el. pašto","all_complete":"Visi pageidavimus pateikė.",
"email_ready":"El. pašto kanalo konfigūracija rasta","email_not_ready":"El. pašto kanalas dar neparuoštas. Seniūnės lange matysite vieną aiškų taisytiną punktą ir galėsite atlikti kanalo testą.",
"send_reminders":"SIŲSTI ŠIANDIENOS PRIMINIMUS","reminders_result":"Priminimų rezultatas","no_due_reminders":"Šiandien pagal nustatymus priminimų siųsti nereikia.","email_log":"El. laiškų žurnalas",
"generation_title":"Grafiko sudarymas ir paskelbimas","senior_only":"Šią funkciją gali atlikti tik seniūnė.","generate_draft":"GENERUOTI / PERKURTI JUODRAŠTĮ","solver_wait":"Sistema ieško geriausio sprendinio...",
"draft_saved":"Juodraštis sukurtas. Oficialus grafikas dar nepakeistas.","no_solution":"Pagal dabartines kietas taisykles tinkamo grafiko rasti nepavyko.","publish":"PASKELBTI IR UŽRAKINTI",
"published":"Grafikas paskelbtas ir pradinė versija užrakinta.","publication_mail":"Paskelbimo laiškai","no_draft":"Nėra juodraščio, kurį būtų galima paskelbti.","draft_outdated":"Po juodraščio sukūrimo pasikeitė pageidavimai, ilgalaikės taisyklės arba bonusų pasirinkimas. Perkurkite juodraštį prieš paskelbiant.","state":"Būsena","draft":"Juodraštis","published_state":"Paskelbtas","not_created":"Nesukurtas",
"hard_errors":"Privalomų taisyklių klaidos","fairness_score":"Teisingumo rodiklis","monthly_fairness":"Mėnesio teisingumas","cumulative_fairness":"Kaupiamasis teisingumas","fairness_hierarchy":"Grafiko vertinimo hierarchija","fairness_hierarchy_intro":"1) sauga, SPS RO budėjimų HARD water-fill, privalomas padengimas ir tikslus krūvis; 2) „Dirbti negaliu“ – 0 pažeidimų; 3) struktūrinis penktadienių / savaitgalių balansas; 4) jo viduje maksimaliai pildomi visi guardrail praėję konkretūs pageidavimai – tikslas 100 %; 5) tik vienodai gerų likusių konfliktų atveju – pateikimo eilė. Po paskelbimo savanoriški apsikeitimai keičia faktinį grafiką tik po abiejų rezidentų sutikimo ir seniūnės patvirtinimo.","hard_validity":"Privalomų saugos taisyklių atitiktis","hard_validity_pass":"0 privalomų saugos klaidų – tinkama","hard_validity_fail":"Yra privalomų saugos klaidų – skelbti negalima","fairness_monthly_explain":"Mėnesio teisingumas vertina tik pasirinktą mėnesį. Ankstesni mėnesiai rodomi istorijai ir auditui, bet nesukuria automatinės „skolos“, kurią naujas mėnuo privalėtų grąžinti.","fairness_cumulative_explain":"Kaupiamasis teisingumas sumuoja visus sistemoje paskelbtus ankstesnius mėnesius ir šį mėnesį. Tai pagrindinis ilgalaikio grupės lygumo rodiklis.","fairness_100_note":"100% reiškia, kad pradinis grafikas pagal galiojančias privalomas taisykles yra optimaliai subalansuotas. Vien noras dirbti savaitgalį nesuteikia teisės gauti neproporcingai daugiau savaitgalių. Po paskelbimo faktinis balansas gali pasikeisti tik per savanorišką abiejų žmonių suderintą apsikeitimą ir seniūnės patvirtinimą.","fairness_formula_month":"Mėnesio formulė: 100 − 18× savaitgalių skirtumas − 7× penktadienių skirtumas − 4× dublių skirtumas − 2× darbo dienų skirtumas.","fairness_formula_cumulative":"Kaupiamojo teisingumo formulė tokia pati, bet kiekvienas skirtumas skaičiuojamas iš visų paskelbtų mėnesių sukauptų sumų.","fairness_breakdown":"Teisingumo išskaidymas","fairness_penalty":"Baudos taškai","fairness_scope":"Apimtis","fairness_metric":"Komponentas","fairness_spread":"Skirtumas (didž.−maž.)","fairness_history":"Teisingumo istorija","fairness_history_help":"Grafike mėnesio teisingumas parodo konkretaus mėnesio lygumą, o kaupiamasis teisingumas — ar sistema laikui bėgant artėja prie lygaus bendro krūvio.","fairness_ledger":"Sistemos teisingumo apskaita","actual_ledger":"Faktinio darbo apskaita","fairness_swap_neutral":"Abipusis savanoriškas apsikeitimas nekeičia teisingumo apskaitos: keičiasi faktinis darbas, bet ne algoritmo paskirstymo vertinimas.","fairness_forced_change":"Pateisinamas pakeitimas po paskelbimo (liga, atostogos, nenumatytas įvykis ar kritinės SPS vietos padengimas) registruojamas faktinio grafiko audite, tačiau nekeičia pradinio paskirstymo teisingumo istorijos. Savanoriški apsikeitimai taip pat keičia tik faktinį grafiką ir galutinį pageidavimų išpildymą.","fairness_no_history":"Dar nėra pakankamai paskelbtų mėnesių teisingumo istorijai.","fairness_priority_table":"Ką reiškia hierarchija","fairness_level":"Lygis","fairness_goal":"Tikslas","fairness_interpretation":"Kaip interpretuoti","fairness_hard_goal":"Privaloma: 0 saugos ir fiziškai neįmanomų paskyrimų","voluntary_unpopular_goal":"Atsižvelgti į aiškiai savanoriškai pasirinktą nepopuliarų darbą, kai tai nepažeidžia saugos ir privalomo padengimo. Likęs nesavanoriškas krūvis vis tiek paskirstomas kuo tolygiau.","voluntary_unpopular_explain":"Savaitgalio „Pageidauju dirbti“ yra savanoriškas pasirinkimas. Sistema stengiasi į jį atsižvelgti, jei leidžia poilsio ir padengimo taisyklės, tačiau kitų rezidentų savaitgalių krūvis vis tiek saugomas nuo nelygaus paskirstymo. Po paskelbimo balansą gali keisti tik savanoriški apsikeitimai.","other_preferences_goal":"Pageidavimai: pirmiausia apsaugomi svarbesni norai, tada maksimaliai didinamas bendras įmanomas išpildymas","other_preferences_explain":"Pageidavimai optimizuojami tik po privalomų saugos, darbo krūvio ir teisingo paskirstymo taisyklių. Sistema visada siekia 100% pageidavimų išpildymo; jei dėl realių konfliktų tai neįmanoma, išsaugo geriausią bendrą rezultatą ir tik tada vienodai geriems likusiems variantams taiko pateikimo eilę.","fairness_cumulative_goal":"Ilgalaikė suvestinė: stebėti, kaip laikui bėgant išsilaiko grupės darbo krūvio lygumas","fairness_monthly_goal":"SPS UG, SPS RO, savaitgaliai, penktadieniai ir kitos darbo vietos pirmiausia paskirstomos kuo tolygiau. Platesnis skirtumas leidžiamas tik tada, kai siauresnis paskirstymas matematiškai neįmanomas dėl svarbesnių apribojimų.","preference_avg":"Vidutinis pageidavimų išpildymas","weekend_spread":"Savaitgalių skirtumas",
"published_schedule":"Galiojantis paskelbtas grafikas","not_published":"Šiam mėnesiui oficialus grafikas dar nepaskelbtas.","colors":"Nuolatinės žmonių spalvos","download_xlsx":"ATSISIŲSTI SPALVOTĄ GRAFIKĄ (.xlsx)","download_csv":"Atsisiųsti duomenų sąrašą (.csv)",
"summary_title":"Žmonių suvestinė","frozen_fairness":"Paskelbimo teisingumas","current_after_changes":"Dabartinė būsena po savanoriškų pakeitimų","fairness_frozen_note":"Pradinio paskirstymo teisingumo apskaita fiksuojama paskelbimo momentu. Vėlesni abipusiai apsikeitimai ir pateisinami pakeitimai dėl ligos, atostogų ar nenumatytų įvykių keičia faktinį grafiką, bet neperrašo pradinio algoritmo teisingumo istorijos. Faktinis darbas ir galutinis pageidavimų išpildymas rodomi atskirai.",
"person":"Žmogus","name":"Vardas","target":"Tikslas","workload":"Krūvis","weekday_assignments":"Darbo dienų paskyrimai","weekday_days":"Atskiros darbo dienos","weekend_assignments":"Savaitgalio pamainos","saturday_assignments":"Šeštadienio pamainos","sunday_assignments":"Sekmadienio pamainos","prior_weekends":"Ankstesni savaitgaliai","cumulative_weekends":"Sukaupti savaitgaliai","fridays":"Penktadieniai","double_shifts":"12h darbo dienos (AM+PM)","max_consecutive":"Daugiausia dienų iš eilės","max_rolling7_hours":"Daugiausia val. per 7 d.","max_calendar_week_hours":"Daugiausia val. kalendorinę savaitę","free_days":"Laisvos dienos","preference_score":"Bendras prašymų išpildymas, %","planned_backups":"Planuoti dubliai","effective_backups":"Galiojantys pavadavimai / dubliai",
"transparency_title":"Skaidrumas","validity_heading":"1. Privalomų taisyklių patikra","validity_text":"0 klaidų reiškia, kad paskelbta bazinė versija nepažeidė nė vienos privalomos taisyklės. Tai galiojimo, o ne teisingumo procentas.",
"fairness_heading":"2. Grupės teisingumas","fairness_text":"Teisingumas skiriamas į mėnesio ir kaupiamąjį. Kaupiamasis yra pagrindinis ilgalaikis sistemos lygumo rodiklis; mėnesio teisingumas padeda suprasti konkretų mėnesį.","fair_formula":"Abiejų rodiklių formulė vienoda: 100 − 18×savaitgalių skirtumas − 7×penktadienių skirtumas − 4×dublių skirtumas − 2×darbo dienų skirtumas. Skiriasi tik apimtis: vienas mėnuo arba visų paskelbtų mėnesių suma.",
"metric_weekend":"Savaitgalių skirtumas","metric_friday":"Penktadienių skirtumas","metric_double":"Dvigubų pamainų skirtumas","metric_weekday":"Darbo dienų skirtumas",
"personal_vs_group":"Asmeninis pageidavimų išpildymas ir grupės teisingumas","balance_ratio":"Balanso santykis","ratio_help":"Balanso santykis = mažesnis procentas / didesnis procentas. 1,00 reiškia, kad abu rodikliai yra vienodo lygio; jis neparodo absoliučios kokybės.",
"baseline_personal":"Asmeninis paskelbimo momentu","current_personal":"Asmeninis dabar","not_applicable":"Netaikoma","all_resident_scores":"Visų rezidentų pageidavimų išpildymas",
"backup_title":"Dubliai / pavadavimai","backup_self_select":"Pasirink mano mėnesio dublį","backup_self_select_help":"Rezervuojama dublio vieta pagal privalomai dengiamas pozicijas. CENTRO RO dengiama automatiškai tiek, kiek saugiai įmanoma. Pasirinktas dublis negali persidengti su jūsų įprasta pamaina.","backup_claim_deadline":"Dublių pasirinkimo terminas","backup_claim_saved":"Dublio vieta rezervuota.","backup_claim_released":"Dublio pasirinkimas atšauktas.","backup_claim_taken":"Šią vietą ką tik pasirinko kitas rezidentas. Pasirinkite kitą.","backup_claim_locked":"Pasirinkimo terminas pasibaigė arba grafikas jau paskelbtas. Toliau dubliai keičiami per Apsikeitimus.","backup_claim_missing_penalty":"Dar nepasirinkote dublio. Jei jo nepasirinksite iki termino, sistema likusias vietas paskirs automatiškai, išlaikydama kuo tolygesnį dublių krūvį.","backup_claim_yours":"Jūsų rezervuoti dubliai","backup_claim_board":"Dublių rezervacijos","backup_claim_free":"Laisva","backup_claim_auto_queue":"Automatinio paskyrimo eilė","backup_claim_auto_queue_help":"Jei dalis rezidentų nepasirenka dublio patys, likusios vietos paskiriamos automatiškai. Sistema išlaiko kuo tolygesnį bendrą dublių krūvį ir nepažeidžia „Dirbti negaliu“ bei saugos taisyklių.","release_backup_claim":"ATŠAUKTI MANO PASIRINKIMĄ","backup_claim_reminder_kind":"Dublių pasirinkimo priminimas","backup_swap_title":"Dublių apsikeitimai","backup_swap_help":"Po grafiko paskelbimo galite pasiūlyti apsikeisti bet kuria suplanuota privalomo dublio vieta. Apsikeitimas taikomas tik jei abu rezidentai gali saugiai perimti naujas dublio vietas.","my_backup_duty":"Mano dublio vieta","their_backup_duty":"Kito rezidento dublio vieta","request_backup_swap":"SIŪLYTI DUBLIŲ APSIKEITIMĄ","backup_swap_sent":"Dublio apsikeitimo pasiūlymas išsiųstas.","backup_swap_invalid":"Šio apsikeitimo negalima atlikti, nes bent vienas rezidentas negalėtų saugiai perimti naujos dublio vietos.","backup_swap_accepted":"Dublių apsikeitimas patvirtintas ir pritaikytas.","backup_swap_rejected":"Dublio apsikeitimas atmestas.","backup_definition":"Privalomas vardinis dublis pagal poziciją: SPS RO bet kurią dieną / bloką, SPS UG bet kurią dieną / bloką, Centro UG 120 rytas ir Onko RO pilna 9 val. pamaina. CENTRO RO dengiama kuo plačiau pagal likusią saugią talpą; jos nepadengimas publikavimo neblokuoja. Privalomos saugos taisyklės ir persidengianti įprasta pamaina niekada neleidžiamos.",
"my_backup_schedule":"Mano dublių grafikas","no_backups":"Šiam žmogui šį mėnesį dublio pareigų nėra.","covered_assignment":"Dubliuojamas žmogus ir jo grafikas","covered_person":"Dubliuojamas žmogus","covered_schedule":"Dubliuojama pamaina","planned_backup":"Planuotas dublis","actual_backup":"Faktinis dublis","effective_backup":"Galiojantis dublis","backup_note":"Pastaba",
"manage_backups":"Seniūnės dublių kontrolė","backup_coverage":"Dublių padengimas","working_person_days":"Privalomų padengti pamainų","covered_person_days":"Pamainų su vardiniu dubliu","backup_complete":"Visos privalomai dengiamos pamainos turi konkretų vardinį dublį.","backup_incomplete":"Bent viena privalomai dengiama pamaina neturi tinkamo dublio. Tokio grafiko negalima skelbti.","resync_backups":"ATNAUJINTI DUBLIUS PAGAL GALIOJANTĮ GRAFIKĄ","backup_synced":"Dubliai automatiškai perskaičiuoti pagal galiojantį grafiką.","backup_capacity_block":"Juodraščio negalima paskelbti, jei bent vienai privalomai dengiama pamainai nėra nė vieno tuo metu laisvo ir saugiai tinkamo žmogaus. CENTRO RO papildomo padengimo trūkumas publikavimo neblokuoja. „Dirbti negaliu“ yra privaloma: juodraštis su tokiu pažeidimu negali būti paskelbtas.",
"cover_credit_type":"Automatiškai nustatoma pavadavimo rūšis","cover_6h":"RYTAS 08:00–14:00 = 6 val.","cover_12h":"DIENA 08:00–20:00 = 12 val.","cover_night12h":"NAKTIS 20:00–08:00 = 12 val.","cover_credit_note":"Pavadavimo kreditas nustatomas automatiškai pagal realiai dubliuotą pamainą ir jos tarifinį koeficientą. Nuo spalio savaitgalio DIENA yra vienas 12 val. įvykis. Naktinis kredito tipas lieka paruoštas ateičiai, bet naktiniai budėjimai į operacinį grafiką neįtraukiami, kol nėra galutinio patvirtinimo.","actual_override":"Faktinio dublio rankinis pakeitimas","mark_backup_completed":"PAŽYMĖTI REALIAI ĮVYKDYTĄ PAVADAVIMĄ","backup_completed":"Realus pavadavimas užregistruotas. Pavaduojančiam rezidentui suteiktas poilsio kreditas; pavaduotam žmogui jokia skola nesukuriama.","undo_backup_completed":"ATŠAUKTI REALŲ PAVADAVIMĄ IR JO KREDITĄ","backup_completion_undone":"Realus pavadavimas ir pavaduojančiam suteiktas kreditas atšaukti.","completed_backup":"Įvykdyta","credit_balances":"Poilsio kreditai","bonus_units":"Kreditai","bonus_shift_value":"Galimas pamainų sumažinimas","rest_credit_bank":"Poilsio kreditų bankas","credit_type":"Kredito rūšis","credit_am":"RYTAS — 6 val.","credit_pm":"POPIETĖ — 6 val.","credit_night":"NAKTIS — 12 val.","use_credit_am":"Panaudoti RYTO poilsio kreditų","use_credit_pm":"Panaudoti POPIETĖS poilsio kreditų","credit_month_cap":"Per mėnesį galima panaudoti daugiausia 2 dieninius poilsio kreditus iš viso.","night_bank_only":"NAKTIES kreditai kol kas tik kaupiami; jie negali būti panaudoti dabartiniam dieniniam PGY1 targetui.","netting_explain":"Kreditas yra vienpusė nauda realiai pavaduojančiam rezidentui. Pavaduotam žmogui skola nesukuriama ir jo turimi poilsio kreditai dėl pavadavimo neatimami.","cover_effect_rest":"Pavaduojančiam rezidentui suteiktas naujas poilsio kreditas.","max_credit_error":"Vienam mėnesiui galima pasirinkti daugiausia 2 dieninius poilsio kreditus iš viso.","backup_record":"Dublio įrašas","record_actual":"ĮRAŠYTI FAKTINĮ DUBLĮ","actual_saved":"Faktinis dublis įrašytas. Dublių statistika naudos šį žmogų.","clear_actual":"GRĄŽINTI PLANUOTĄ DUBLĮ","actual_cleared":"Faktinis pakeitimas pašalintas; vėl galioja planuotas dublis.","no_eligible_backup":"Šiai pamainai nėra tinkamo žmogaus: kandidatas turi būti laisvas tuo pačiu laiku ir nepažeisti saugos bei „Dirbti negaliu“ taisyklių.",
"swap_title":"Swap","swap_note":"Savanoriški apsikeitimai keičia faktinį grafiką tik po abiejų žmonių sutikimo ir privalomų taisyklių patikros. Tikslus mėnesio krūvis ir Onko porų taisyklė negali būti apeiti apsikeitimu. Jei apsikeitimas sukurtų Onko dienas iš eilės ar kitą įspėjimą, tai turi būti aiškiai patvirtinta. Pradinio algoritmo teisingumo apskaita po apsikeitimo neperrašoma.","repair_title":"Neplanuoti pakeitimai po publikavimo","repair_help":"Liga, atostogos ar kita pateisinama nenumatyta priežastis keičia tik faktinį grafiką. Paskelbimo momento pradinio paskirstymo teisingumo bazė nekeičiama ir neatvykstančiam rezidentui nesukuriama jokia „skola“. Jei reikia išlaikyti kritinę SPS RO ar SPS UG vietą, pirmiausia ieškoma saugaus perkėlimo iš mažiau svarbios tos pačios pamainos vietos; tik tada ieškoma laisvo pavaduojančio rezidento. Saugos, persidengimo ir privalomo padengimo taisyklės visada lieka galioti.","repair_assignment":"Keičiama pamaina","repair_replacement":"Pavaduojantis rezidentas","repair_reason":"Priežasties kategorija","repair_reason_sickness":"Liga","repair_reason_leave":"Atostogos","repair_reason_approved":"Kitas pateisinamas neatvykimas","repair_reason_force":"Force majeure / nenumatytas įvykis","repair_note":"Vidinė pastaba (nebūtina)","apply_repair":"PRITAIKYTI NEPLANUOTĄ PAKEITIMĄ","repair_applied":"Pakeitimas pritaikytas faktiniam grafikui. Pradinio paskirstymo teisingumo istorija nekeičiama. Faktinis grafikas ir pageidavimų išpildymas perskaičiuoti.","repair_invalid":"Šio pakeitimo negalima taikyti dėl privalomos saugos taisyklės","repair_no_candidate":"Šiai pamainai nėra saugiai tinkamo pavaduojančio rezidento.","repair_history":"Neplanuotų pakeitimų istorija","repair_load":"Papildoma repair našta šį mėnesį","repair_load_help":"Tai tik faktinių pakeitimų audito skaitiklis. Jis nenaudojamas ateities kompensacijoms ar pradinio paskirstymo teisingumui perskaičiuoti. Kritinės vietos padengimas reiškia darbo vietos pakeitimą jau suplanuotos pamainos metu, o ne papildomą teisingumo skolą.","repair_fairness_neutral":"NEKEIČIA PRADINIO TEISINGUMO","repair_from":"Negalintis dirbti","repair_to":"Pavadavo","repair_date":"Data / pamaina","my_assignment":"Mano pamaina","their_assignment":"Kito žmogaus pamaina","request_swap":"SIŪLYTI APSIKEITIMĄ","request_sent":"Apsikeitimo pasiūlymas išsiųstas.","incoming":"Gauti pasiūlymai","accept":"PRIIMTI","reject":"ATMESTI","accepted":"Apsikeitimas patvirtintas ir pritaikytas.","accepted_pending":"Apsikeitimą patvirtino abu žmonės. Beta versijoje seniūnė atliks galutinę privalomų taisyklių patikrą ir pritaikys pakeitimą.","finalize_swap":"PRITAIKYTI PATVIRTINTĄ APSIKEITIMĄ","swap_applied":"Apsikeitimas pritaikytas, privalomos taisyklės patikrintos, dubliai perskaičiuoti.","swap_finalize_failed":"Apsikeitimo pritaikyti nepavyko, nes po galutinės patikros būtų pažeista privaloma taisyklė.","rejected":"Apsikeitimas atmestas.","hard_reject":"Apsikeitimas atmestas, nes pažeistų privalomą taisyklę.","history":"Apsikeitimų istorija","pending":"Laukiama","approved":"Patvirtinta","rejected_status":"Atmesta",
"calendar_title":"Mano grafikas kalendoriui","calendar_help":"Galite atsisiųsti vienkartinį .ics failą arba vieną kartą užsiprenumeruoti privačią kalendoriaus nuorodą. Prenumerata atnaujinama paskelbus naują grafiką ir po svarbių faktinio grafiko pakeitimų. Jei Nustatymuose įjungti dubliai, jie taip pat įtraukiami.","download_ics":"ATSISIŲSTI MANO GRAFIKĄ (.ics)","calendar_feed":"Privati kalendoriaus prenumeratos nuoroda","calendar_feed_private":"Ši nuoroda veikia kaip slaptažodis į jūsų grafiką — nesidalinkite ja. Ji turi atsitiktinį ilgą kodą ir nėra rodoma kitiems rezidentams.","calendar_google":"GOOGLE CALENDAR","calendar_apple":"APPLE CALENDAR","calendar_other":"OUTLOOK CALENDAR","calendar_google_help":"Google Calendar kompiuteryje pasirinkite kitų kalendorių pridėjimą pagal nuorodą ir įklijuokite žemiau esančią privačią nuorodą. Tai daroma vieną kartą.","calendar_apple_help":"Apple Calendar gali užsiprenumeruoti nuorodą tiesiogiai. Paspaudus mygtuką turėtų atsidaryti kalendoriaus prenumeratos langas.","calendar_other_help":"Outlook gali prenumeruoti tą pačią privačią iCalendar nuorodą per kalendoriaus pridėjimą iš interneto. Jei naudojate kitą programą, naudokite .ics failą arba prenumeratos nuorodą, jei ji palaikoma.",
"proof_title":"Mano grafiko patikra","proof_intro":"Vizuali patikra parodo, kas tiksliai atitiko jūsų poreikius ir kur liko neatitikimų. Čia nerodomas programinis kodas — tik galutiniai rezultatai.","matches":"ATITINKA","partial":"DALINAI","mismatch":"NEATITINKA","baseline":"Paskelbimo momentu","current":"Dabar","hard_ok":"Privalomas negalėjimas dirbti išlaikytas","hard_bad":"Privaloma taisyklė pažeista","soft_off_ok":"Norėtos laisvos dienos","preferred_ok":"Pageidautos darbo dienos","workload_ok":"Mėnesio krūvio tikslas","style_component":"Darbo pobūdžio kriterijus","missed_dates":"Neatitikusios datos","criterion":"Kriterijus","result":"Rezultatas","score":"Išpildymas","explanation":"Paaiškinimas","proof_all_good":"Pagal pateiktus duomenis privalomos taisyklės išlaikytos, o aktyvūs pageidavimai neturi ryškių neatitikimų.","proof_soft_issues":"Privalomos taisyklės išlaikytos, tačiau ne visi pageidavimai buvo įvykdyti.","proof_hard_issue":"Aptiktas privalomos taisyklės neatitikimas — grafiką būtina peržiūrėti.","no_active_preferences":"Šiai kategorijai aktyvaus pageidavimo nepateikėte.","swap_suggestion":"Jei privalomos taisyklės nepažeistos, bet pageidavimas liko neįvykdytas, galima ieškoti savanoriško sprendimo Apsikeitimų lange.",
"rules_title":"Grafiko taisyklės","read":"Skaityti","edit":"Redaguoti","save_rules":"IŠSAUGOTI TAISYKLIŲ PAKEITIMUS","rules_saved":"Taisyklės atnaujintos.","edit_senior_only":"Taisykles redaguoti gali tik seniūnė.",
"yes":"TAIP","no":"NE","reminder_kind":"Priminimas","publication_kind":"Grafiko paskelbimas","date":"Data","day":"Diena","time":"Laikas","department":"Padalinys","shift":"Pamaina","morning":"Rytas","afternoon":"Popietė","full_day":"Pilna diena","night":"Naktis","status":"Statusas","details":"Informacija","sent":"Išsiųsta","failed":"Nepavyko","skipped":"Praleista"
},
"EN": {
"language":"Language","user":"User","profile":"Profile","resident_profile":"Resident profile","senior_profile":"Senior scheduler profile","resident_pin":"Personal PIN","admin_pin":"Senior scheduler PIN","local_resident":"Local test mode: personal PINs are not configured.","local_senior":"Local test mode: senior functions are unlocked only for the senior account.","bad_pin":"Incorrect PIN.",
"login_title":"Sign in","login":"SIGN IN","logout":"SIGN OUT","signup":"CREATE ACCOUNT","signup_title":"First registration","password":"Password","password_repeat":"Repeat password","auth_email":"Email","auth_invalid":"Sign-in failed. Check your email and password.","forgot_password":"Forgot password?","forgot_password_help":"Enter the email used for this account. If the account exists, we will send a secure link to choose a new password.","forgot_password_send":"SEND RECOVERY LINK","forgot_password_sent":"If an account with this email exists, a recovery link has been sent. Check your spam folder too.","forgot_password_bad_email":"Enter a valid email address.","forgot_password_rate_limit":"The recovery email rate limit has been reached temporarily. Try again later.","forgot_password_error":"Could not send the recovery email. Try again or contact the administrator.","signup_sent":"Account created. If email confirmation is enabled, confirm the email and then sign in.","signup_password_mismatch":"Passwords do not match.","claim_title":"Link this account","resident_claim_tab":"Resident","observer_claim_tab":"Department administrator / observer","observer_claim_help":"This account is for departmental oversight only. It is read-only: it can view the published and current schedules, swaps, backups, fairness and audit history, but cannot change anything.","observer_invite_code":"Department observer invite code","observer_claim":"ACTIVATE READ-ONLY ACCESS","observer_read_only":"TIK PERŽIŪRA","observer_role":"Department observer","observer_portal":"Department grafikas oversight","observer_overview":"Overview","observer_schedule":"Schedules","observer_changes":"Change log","observer_fairness":"Teisingumas","observer_backups":"Backups","observer_rules":"Rules","observer_scope_note":"This account cannot generate, publish, approve, edit or undo schedules or swaps.","observer_privacy_note":"Private resident preferences, HARD-unavailable dates, personal notes, emails and account settings are not shown.","observer_baseline_schedule":"SYSTEM baseline — at publication","observer_actual_schedule":"ACTUAL grafikas — now","observer_change_count":"Changed normal assignments","observer_normal_swaps":"Normal-shift swaps","observer_backup_swaps":"Backup swaps","observer_pending_swaps":"Laukia","observer_approved_swaps":"Approved","observer_rejected_swaps":"Rejected","observer_no_changes":"There are no normal-assignment changes after publication.","observer_from":"From","observer_to":"Now","observer_change_log_help":"The SYSTEM baseline remains the fairness ledger. The ACTUAL grafikas shows the real situation after bilateral voluntary swaps.","observer_backup_status":"Status","observer_planned_backup":"Planned backup","observer_actual_backup":"Actual backup","observer_activated":"Activated","observer_completed":"Actually covered","observer_no_schedule":"No grafikas has been published for this month yet.","observer_access_ready":"Read-only department access activated.","claim_help":"Choose only your own initials and enter the one-time beta invite code provided to you.","invite_code":"Invite code","claim":"LINK ACCOUNT","claim_failed":"Could not link the account. Check the initials and invite code.","account_unlinked":"You are signed in, but this account is not linked to a resident yet.",
"app_title":"Resident scheduling system","app_caption":"Hard rules → transparency → soft preferences → controlled changes.","year":"Year","month":"Month","weekdays":"Weekdays","base_target":"Base shift target","deadline":"Preference deadline","days_left":"Days remaining","deadline_today":"Today is the deadline.","deadline_passed":"Deadline passed {n} day(s) ago.","deadline_future":"{n} day(s) remain until the deadline.","deadline_note":"Next month's preferences are due by 00:00 on the 14th of the preceding month (the 13th is the last full day).",
"preferences":"Preferences","settings":"Settings","special_days":"Special days","generation":"Generation","schedule":"Schedule","summary":"Summary","transparency":"Transparency","credits_debts":"Credits","backups":"Backups","swaps":"Swaps","calendar":"Calendar","proof":"Proof","senior_guide":"Senior guide","rules":"Rules",
"my_preferences":"My monthly preferences","hard_unavailable":"Unavailable — RESIDENT HARD","hard_help":"You may mark the whole day or only the morning / afternoon. In V2.5.107 this is a mandatory SYSTEM-generation constraint: you cannot be assigned in that blocked time. It is never traded for higher SOFT satisfaction or prettier fairness. If coverage, safety, exact workload and every Unavailable block cannot coexist, no draft is returned.","hard_all_day":"Whole day","hard_morning":"Morning (08:00–14:00)","hard_afternoon":"Afternoon (14:00–20:00)","hard_partial_note":"If only morning or afternoon is marked, you may still receive a normal shift or backup duty in the other time block.","hard_overlap":"The same date cannot be marked as both whole-day and partial required unavailability.","soft_free":"Would like time off — preference","soft_help":"Choose whole day, morning, or afternoon. The system tries to honor this unless a higher-priority rule prevents it.","soft_overlap":"The same date cannot be marked as both whole-day and partial requested time off.","preferred":"Prefer to work — preference","preferred_help":"Choose whole day, morning, or afternoon. Voluntary unpopular work is prioritized when labour-law and rest-safety rules allow it.","preferred_overlap":"The same date cannot be marked as both whole-day and partial preferred work.","vacation":"Approved vacation / leave days","vacation_help":"Select approved vacation days. The scheduler will not assign work or backup on those days and will proportionally reduce the monthly workload target so approved leave is not treated as a fairness deficit.","vacation_overlap":"The same day is entered as both vacation and another justified absence; keep it in only one field.","note":"Additional note","note_ph":"Example: I would prefer not to have a double shift after several consecutive days.","save":"Save","saved":"Saved.","hard_conflict":"A preferred-work request conflicts with required unavailability in the same time block.","soft_conflict":"Requested time off and preferred work cannot overlap in the same time block.",
"all_preferences":"All resident preferences","preference_load":"Preference volume","review":"Review","normal":"Normal","visibility_flag":"The Review flag is only a visibility prompt for the senior scheduler; it is not a penalty or automatic restriction.","submitted":"Submitted","updated":"Updated","hard_dates":"Unavailable — whole day","hard_am_dates":"Unavailable — morning","hard_pm_dates":"Unavailable — afternoon","soft_dates":"Time off — whole day","soft_am_dates":"Time off — morning","soft_pm_dates":"Time off — afternoon","preferred_dates":"Prefer work — whole day","preferred_am_dates":"Prefer work — morning","preferred_pm_dates":"Prefer work — afternoon","comment":"Comment",
"settings_title":"My account and work-style settings","short_term":"Short-term monthly preferences","legal_safety_inputs":"Work elsewhere","justified_absence":"Justified absence","justified_absence_help":"This function is used only after publication. It changes the ACTUAL schedule without rewriting the original SYSTEM fairness baseline.","long_duty":"Long / night duty elsewhere","long_duty_help":"Mark the start date of a known long or night duty outside RAPA. RAPA cannot see that work itself, so it protects the following day for recovery. Duties scheduled by RAPA do not need to be entered here.","labour_hard_summary":"RAPA protects rest and workload automatically. Enter only outside work that the system cannot see.","labour_scope_note":"RAPA can only account for work it knows about. Enter long / night duties elsewhere so enough recovery time can be protected.","long_term":"Long-term recurring preferences","long_term_help":"These rules are applied automatically every month until you change them. A month-specific SOFT preference overrides an opposite recurring SOFT preference; recurring “Unavailable” remains RESIDENT HARD. The time column applies to RESIDENT HARD; recurring SOFT weekday preferences are whole-day.","weekday_name":"Weekday","recurring_rule":"Recurring rule","recurring_time":"Time","rec_none":"None","rec_hard":"Unavailable (RESIDENT HARD)","rec_soft":"Would like the day off","rec_preferred":"Prefer to work","save_long_term":"SAVE LONG-TERM PREFERENCES","long_term_saved":"Long-term preferences saved.","email":"Email","email_required":"Every account should contain a valid email address.","shift_length_pref":"Preferred workday length","shift_length_help":"Persistent private work-style preference. The system tries to shape your workday length according to this choice when mandatory rules, rest requirements, and monthly workload allow it. Onko RO remains a separate 9-hour full-day shift.","shift_length_any":"No preference","shift_length_6":"Mostly 6 hours","shift_length_mixed":"Mixed – both 6-hour and 12-hour workdays are fine","shift_length_12":"Mostly 12 hours","weekday_pref":"Weekday pattern","weekend_pref":"Weekend pattern","holiday_pref":"Public holidays","holiday_pref_help":"Long-term preference for official Lithuanian public holidays. Holiday duty is offered first to residents who prefer working holidays, then to neutral residents, while residents who prefer rest are used only when needed. Among residents with the same choice, holiday work is distributed as evenly as possible using current and prior months.","holiday_rest":"Prefer to rest on holidays","holiday_neutral":"Neutral / no preference","holiday_work":"Prefer to work on holidays","spread_pref":"Shift distribution","avoid_double_shifts":"Avoid double shifts when possible","weekday_help":"−2 = relatively fewer weekdays, 0 = neutral, +2 = relatively more.","weekend_help":"−2 = fewer weekends, 0 = neutral, +2 = more.","spread_help":"−2 = more clustered, 0 = neutral, +2 = more dispersed.","notifications":"Notifications","notifications_on":"Receive email reminders about the preference-submission deadline","notification_default":"Notifications are on by default.","reminder_start":"Start personal reminders on day of month","reminder_help":"Choose the day of the month from which you want to receive personal email reminders about your upcoming grafikas if your preferences are still missing. Example: “4 days left until preference submission closes.” Reminders stop after you submit or the deadline passes.","include_backups_calendar":"Include backup duties in my .ics calendar","backup_email_alerts":"Email me when the senior activates my backup duty","phone_optional":"Phone number for SMS alerts (optional)","sms_future":"SMS preferences are prepared, but SMS delivery is not enabled in this beta yet.","backup_sms_alerts":"Send me an SMS when my backup duty is activated","backup_activation":"Backup activation","activate_backup":"CALL BACKUP NOW","backup_activated":"Backup activated.","backup_email_sent":"Backup alert email sent.","backup_email_failed":"Backup activated, but the alert email could not be sent.","undo_activation":"UNDO BACKUP ACTIVATION","activation_undone":"Backup activation undone.","smtp_admin_note":"The sending-mailbox password is one shared system secret; residents never enter it.","settings_saved":"Settings saved.","backup_bonus":"Backup bonuses","bonus_balance":"Available backup bonuses","bonus_help":"When you actually cover another resident, you earn a REST credit as a future benefit. The covered resident receives no debt. MORNING, AFTERNOON and NIGHT are tracked separately.","use_bonus":"Use bonuses this month","bonus_target_effect":"At most 2 daytime rest credits in total may be used in one month. MORNING and AFTERNOON are tracked separately; NIGHT credits cannot reduce the current PGY1 daytime target.","bonus_insufficient":"You selected more bonuses than you currently have.",
"dashboard_title":"Senior monthly control dashboard","completion":"Preference completion","missing_preferences":"Not submitted","missing_email":"Missing email","all_complete":"Everyone submitted preferences.","email_ready":"Email channel configuration found","email_not_ready":"Email channel is not ready yet. The Senior control shows one clear fix and provides a channel test.","send_reminders":"SEND TODAY'S REMINDERS","reminders_result":"Reminder result","no_due_reminders":"No reminders are due today under the current settings.","email_log":"Email log",
"generation_title":"Schedule generation and publication","senior_only":"Only the senior scheduler can use this function.","generate_draft":"GENERATE / REGENERATE DRAFT","solver_wait":"The system is searching for the best solution...","draft_saved":"Draft created. The official grafikas has not changed.","no_solution":"No feasible grafikas could be found under the current hard rules.","publish":"PUBLISH AND LOCK","published":"Schedule published and baseline locked.","publication_mail":"Publication emails","no_draft":"There is no draft to publish.","draft_outdated":"Preferences, recurring rules, or bonus selection changed after the draft was generated. Regenerate the draft before publishing.","state":"Status","draft":"Draft","published_state":"Paskelbtas","not_created":"Not created","hard_errors":"Privalomų taisyklių klaidos","fairness_score":"Teisingumo įvertis","monthly_fairness":"Mėnesio teisingumas","cumulative_fairness":"Kaupiamasis teisingumas","fairness_hierarchy":"Grafiko vertinimo hierarchija","fairness_hierarchy_intro":"Prioritetų tvarka: absoliučios saugos ir darbo taisyklės → rezidentų „Negaliu dirbti“ (0 pažeidimų privaloma) → kuo lygesnis SPS RO, SPS UG ir savaitgalių paskirstymas → poilsis ir darbo krūvis → švenčių pasirinkimai → visų ne-Onko darbo vietų struktūrinis water-filling → SOFT pageidavimai. SOFT konflikte, jau išlaikius water-fill, aukštesnius prioritetinius taškus turintis anksčiau anketą pateikęs rezidentas turi pirmenybę. Didesnis pageidavimų skaičius prioriteto nesuteikia.","hard_validity":"Privalomų taisyklių atitiktis","hard_validity_pass":"0 privalomų taisyklių klaidų — tinkama","hard_validity_fail":"Yra privalomų taisyklių klaidų — skelbti negalima","fairness_monthly_explain":"Mėnesio teisingumas vertina tik pasirinktą mėnesį. Jis gali būti sąmoningai mažesnis, kai taisomas ankstesniais mėnesiais susikaupęs netolygumas.","fairness_cumulative_explain":"Kaupiamasis teisingumas apima visus anksčiau paskelbtus mėnesius ir pasirinktą mėnesį. Tai pagrindinis ilgalaikio grupės balanso rodiklis.","fairness_100_note":"100 % reiškia, kad sistemos paskirtas nesavanoriškas nepopuliarus krūvis ir kiti teisingumo komponentai yra optimaliai subalansuoti. Aiškiai savanoriškai pasirinkta penktadienio ar savaitgalio darbo data pati savaime teisingumo balo nemažina.","fairness_formula_month":"Mėnesio formulė: 100 − 18× savaitgalių skirtumas − 7× penktadienių skirtumas − 4× dvigubų pamainų skirtumas − 2× darbo dienų skirtumas.","fairness_formula_cumulative":"Kaupiamoji formulė tokia pati, tačiau kiekvienas skirtumas skaičiuojamas iš visų paskelbtų mėnesių sukauptų sumų.","fairness_breakdown":"Teisingumo išskaidymas","fairness_penalty":"Baudos taškai","fairness_scope":"Apimtis","fairness_metric":"Komponentas","fairness_spread":"Skirtumas (didž.−maž.)","fairness_history":"Teisingumo istorija","fairness_history_help":"Mėnesio teisingumas rodo balansą vieno mėnesio viduje; kaupiamasis teisingumas rodo, ar ilgainiui sistema artėja prie vienodo bendro krūvio.","fairness_ledger":"Sistemos teisingumo apskaita","actual_ledger":"Faktinio darbo apskaita","fairness_swap_neutral":"Abipusis savanoriškas apsikeitimas nekeičia sistemos teisingumo apskaitos: faktinis darbas pasikeičia, tačiau algoritmo paskirstymo balansas lieka tas pats.","fairness_forced_change":"Pateisinamas pakeitimas po paskelbimo (liga, atostogos, nenumatytas įvykis ar kritinės SPS vietos padengimas) registruojamas faktinio grafiko audite, tačiau nekeičia pradinio paskirstymo teisingumo istorijos. Savanoriški apsikeitimai taip pat keičia tik faktinį grafiką ir galutinį pageidavimų išpildymą.","fairness_no_history":"Dar nėra pakankamai paskelbtų mėnesių teisingumo istorijai.","fairness_priority_table":"Kaip skaityti hierarchiją","fairness_level":"Lygis","fairness_goal":"Tikslas","fairness_interpretation":"Kaip interpretuoti","fairness_hard_goal":"Privaloma: 0 saugos ir fiziškai neįmanomų paskyrimų","voluntary_unpopular_goal":"Vykdyti aiškiai savanoriškai pasirinktą nepopuliarų darbą tik išlaikant aukštesnes SYSTEM struktūrines taisykles, įskaitant Friday eligibility-aware water-fill","voluntary_unpopular_explain":"Pageidautas penktadienis yra SOFT: generatorius jį vykdo tik tada, kai išlaiko penktadienių structural floor/ceil raw spread 0–1 ir aukštesnes HARD taisykles. Po publikavimo abipusis ACTUAL swapas gali šį balansą pakeisti neperrašydamas SYSTEM fairness.","other_preferences_goal":"Pageidavimai: pirmiausia apsaugomi svarbesni norai, tada maksimaliai didinamas bendras įmanomas išpildymas","other_preferences_explain":"Pageidavimai optimizuojami tik po privalomų saugos, darbo krūvio ir teisingo paskirstymo taisyklių. Sistema visada siekia 100% pageidavimų išpildymo; jei dėl realių konfliktų tai neįmanoma, išsaugo geriausią bendrą rezultatą ir tik tada vienodai geriems likusiems variantams taiko pateikimo eilę.","fairness_cumulative_goal":"Ilgalaikė suvestinė: stebėti, kaip laikui bėgant išsilaiko grupės darbo krūvio lygumas","fairness_monthly_goal":"SPS RO, SPS UG ir savaitgaliai SYSTEM grafike siekia raw spread 0–1. Penktadieniai water-fill'inami pagal HARD tinkamumą: rezidentas niekada neverčiamas virš jo realiai galimos penktadienių talpos; likęs krūvis lyginamas tarp tinkamų rezidentų. Visos ne-Onko darbo vietos taip pat water-fill'inamos iki raw spread 0–1 prieš SOFT; platesnis postų koridorius leidžiamas tik jei siauresnis įrodytas neįmanomas.","preference_avg":"Vidutinis pageidavimų išpildymas","weekend_spread":"Savaitgalių skirtumas",
"published_schedule":"Current published schedule","not_published":"No official grafikas has been published for this month.","colors":"Permanent resident colors","download_xlsx":"DOWNLOAD FORMATTED SCHEDULE (.xlsx)","download_csv":"Download data list (.csv)",
"summary_title":"Resident summary","frozen_fairness":"Publication fairness","current_after_changes":"Current state after voluntary changes","fairness_frozen_note":"SYSTEM fairness, workplace spread, and future catch-up accounting are frozen from the publication baseline. Bilateral voluntary swaps and justified post-publication repairs (sickness, leave, force majeure, SPS pull-down) change the ACTUAL grafikas but are EXCLUDED from fairness/spread/debt. Actual work and retrospective request satisfaction may be shown separately.","person":"Person","name":"Name","target":"Target","workload":"Workload","weekday_assignments":"Weekday assignments","weekday_days":"Distinct weekdays","weekend_assignments":"Weekend assignments","saturday_assignments":"Saturday assignments","sunday_assignments":"Sunday assignments","prior_weekends":"Prior weekends","cumulative_weekends":"Cumulative weekends","fridays":"Fridays","double_shifts":"12h workdays (AM+PM)","max_consecutive":"Max consecutive days","max_rolling7_hours":"Max hours / rolling 7d","max_calendar_week_hours":"Max calendar-week hours","free_days":"Free days","preference_score":"Preference fulfillment, %","planned_backups":"AUTO backup duties","effective_backups":"Current / effective backup duties",
"transparency_title":"Transparency","validity_heading":"1. Privalomų taisyklių patikra","validity_text":"0 klaidų reiškia, kad paskelbtas pradinis grafikas nepažeidė nė vienos privalomos taisyklės. Tai atitikties, o ne teisingumo procentas.","fairness_heading":"2. Grupės teisingumas","fairness_text":"Sistema skiria mėnesio ir kaupiamąjį teisingumą. Kaupiamasis teisingumas yra pagrindinis ilgalaikio balanso rodiklis, o mėnesio teisingumas apibūdina pasirinktą mėnesį.","fair_formula":"Abiem įverčiams naudojama ta pati formulė: 100 − 18× savaitgalių skirtumas − 7× penktadienių skirtumas − 4× dvigubų pamainų skirtumas − 2× darbo dienų skirtumas. Skiriasi tik apimtis: vienas mėnuo arba visų paskelbtų mėnesių suma.","metric_weekend":"Savaitgalių skirtumas","metric_friday":"Penktadienių skirtumas","metric_double":"Dvigubų pamainų skirtumas","metric_weekday":"Darbo dienų skirtumas",
"personal_vs_group":"Personal preference fulfillment versus group fairness","balance_ratio":"Balance ratio","ratio_help":"Balance ratio = smaller percentage / larger percentage. 1.00 means the two scores are at the same level; it is not an absolute quality measure.","baseline_personal":"Personal at publication","current_personal":"Personal now","not_applicable":"N/A","all_resident_scores":"All resident preference scores",
"backup_title":"Backup cover","backup_self_select":"Choose my monthly backup slots","backup_self_select_help":"Reservable mandatory groups are position-based: SPS RO on any day/block, SPS UG on any day/block, Centro UG 120 morning, and full 9h Onko RO. CENTRO RO is planned automatically as best-effort. Multiple slots may be selected; a reserved backup slot blocks overlapping normal work.","backup_claim_deadline":"Backup-choice deadline","backup_claim_saved":"Backup slots reserved.","backup_claim_released":"Backup choice released.","backup_claim_taken":"Another resident just took that slot. Please choose another.","backup_claim_locked":"The selection deadline has passed or the grafikas is already published. Further backup-slot changes use the Swaps tab.","backup_claim_missing_penalty":"You have not selected any backup slot yet. The engine will still AUTO-assign backups using tolygus paskirstymas; self-selection cannot create an unfair backup load.","backup_claim_yours":"Your reserved backups","backup_claim_board":"Backup reservations","backup_claim_free":"Free","backup_claim_auto_queue":"Automatic-assignment priority pool","backup_claim_auto_queue_help":"Residents who did not self-select any backup slot may enter the automatic-assignment pool first, but claims are only a tie-break. AUTO backups are water-filled by total backup load and never violate Cannot-work / RESIDENT HARD or ABSOLUTE HARD.","release_backup_claim":"RELEASE MY SELECTION","backup_claim_reminder_kind":"Backup-choice reminder","backup_swap_title":"Backup swaps","backup_swap_help":"After publication, you may propose swapping any planned mandatory backup slot. The swap is applied only if both remain eligible for the new slots.","my_backup_duty":"My backup slot","their_backup_duty":"Other resident's backup slot","request_backup_swap":"PROPOSE BACKUP SWAP","backup_swap_sent":"Backup swap proposal sent.","backup_swap_invalid":"This swap cannot be applied because at least one resident would be ineligible for the new backup slot.","backup_swap_accepted":"Backup swap accepted and applied.","backup_swap_rejected":"Backup swap rejected.","backup_definition":"Mandatory named backup is position-based: SPS RO on every day/block, SPS UG on every day/block, Centro UG 120 morning, and full 9h Onko RO. CENTRO RO is covered as widely as safe remaining capacity allows; missing CENTRO RO backup does not block publication. ABSOLUTE HARD and overlapping normal work are never allowed.","my_backup_schedule":"My backup schedule","no_backups":"This resident has no backup duties this month.","covered_assignment":"Covered resident and schedule","covered_person":"Covered resident","covered_schedule":"Covered shift","planned_backup":"Planned backup","actual_backup":"Actual backup","effective_backup":"Effective backup","backup_note":"Note","manage_backups":"Senior backup control","backup_coverage":"Backup coverage","working_person_days":"Required covered shifts","covered_person_days":"Shifts with named backup","backup_complete":"Every mandatory covered shift has a named backup.","backup_incomplete":"At least one mandatory covered shift lacks an eligible backup. The grafikas cannot be published.","resync_backups":"REFRESH BACKUPS FROM CURRENT SCHEDULE","backup_synced":"Backups recalculated automatically from the current schedule.","backup_capacity_block":"The draft cannot be published if at least one mandatory covered shift has no ABSOLUTE-HARD-safe resident who is free during that block. Missing CENTRO RO best-effort coverage does not block publication. Any RESIDENT HARD / Unavailable violation blocks SYSTEM publication. V2.5.107 requires zero such violations in a generated SYSTEM draft.","cover_credit_type":"Automatically derived cover type","cover_6h":"MORNING 08:00–14:00 = 6h","cover_12h":"DAY 08:00–20:00 = 12h","cover_night12h":"NIGHT 20:00–08:00 = 12h","cover_credit_note":"The cover credit is derived automatically from the actual covered shift and its tariff coefficient. From October a weekend DAY is one 12h event. NIGHT credit logic is prepared for the future, but night duties are not activated in the operational schedule until their start model is confirmed.","actual_override":"Manual actual-backup override","mark_backup_completed":"MARK ACTUAL COVER COMPLETED","backup_completed":"Actual cover recorded. A rest credit was awarded to the covering resident; no debt is created for the covered resident.","undo_backup_completed":"UNDO ACTUAL COVER AND ITS CREDIT","backup_completion_undone":"Actual cover and the covering resident’s credit were reversed.","completed_backup":"Completed","credit_balances":"Rest credits","bonus_units":"Credits","bonus_shift_value":"Available shift reduction","rest_credit_bank":"Rest-credit bank","credit_type":"Credit type","credit_am":"MORNING — 6h","credit_pm":"AFTERNOON — 6h","credit_night":"NIGHT — 12h","use_credit_am":"Redeem MORNING rest credits","use_credit_pm":"Redeem AFTERNOON rest credits","credit_month_cap":"At most 2 daytime rest credits in total may be used in one month.","night_bank_only":"NIGHT credits are bank-only for now; they cannot reduce the current PGY1 daytime target.","netting_explain":"A credit is a one-way benefit for the resident who actually covers. The covered resident receives no debt and keeps any existing rest credits.","cover_effect_rest":"A new rest credit was awarded to the covering resident.","max_credit_error":"At most 2 daytime rest credits in total may be selected for one month.","backup_record":"Backup record","record_actual":"RECORD ACTUAL BACKUP","actual_saved":"Actual backup recorded. Backup statistics will use this resident.","clear_actual":"RESTORE PLANNED BACKUP","actual_cleared":"Actual override removed; the planned backup is effective again.","no_eligible_backup":"No eligible resident is available for this shift. The backup must be free during the same time block and ABSOLUTE-HARD-safe; RESIDENT HARD / Unavailable is mandatory for SYSTEM generation; a blocked resident is not eligible for that backup slot.",
"swap_title":"Voluntary swaps","swap_note":"Voluntary swaps change only the ACTUAL schedule. Before consent, each affected resident sees a consequence table. The swap is blocked by ABSOLUTE/operational and labour-time guardrails, exact monthly workload equality, and even Onko pairing (0/2/4...). Consecutive Onko may be an explicit ACK consequence, but parity may never be overridden. SYSTEM fairness remains frozen. Workplace/post fairness, modality mix, US exposure and diversity never block a mutually accepted ACTUAL swap.","repair_title":"Unplanned post-publication repairs","repair_help":"Sickness, leave, another justified absence, or force majeure changes only the ACTUAL schedule. The SYSTEM fairness baseline frozen at publication and fairness_history remain unchanged; the absent resident receives no fairness debt. V2.5.57: if the absent resident covered SPS RO / SPS UG, critical coverage is preserved first by pulling a same-block resident from a lower-priority NON-MANDATORY post; the optional donor post may remain empty. Only when no safe donor transfer exists is a resident free in that target block used as fallback. ABSOLUTE safety, overlap and mandatory coverage remain hard. Pull-downs and other justified repairs are EXCLUDED from SYSTEM fairness, workplace spread, and future catch-up accounting.","repair_assignment":"Assignment to replace","repair_replacement":"Covering resident","repair_reason":"Reason category","repair_reason_sickness":"Sickness","repair_reason_leave":"Leave","repair_reason_approved":"Other justified absence","repair_reason_force":"Force majeure / unexpected event","repair_note":"Internal note (optional)","apply_repair":"APPLY UNPLANNED REPAIR","repair_applied":"Repair applied to the ACTUAL schedule. SYSTEM fairness, workplace spread, and future catch-up remain tied to the publication baseline; the repair is excluded from them. Actual grafikas and request satisfaction were recalculated.","repair_invalid":"This repair cannot be applied because of an operational safety / HARD rule","repair_no_candidate":"No safely eligible covering resident is available for this shift.","repair_history":"Unplanned repair history","repair_load":"Additional repair load this month","repair_load_help":"This is an operational audit counter only. It is NOT used in fairness, workplace spread, future catch-up, or future compensation. A critical pull-down is a station change during an already scheduled work block, not an extra fairness burden.","repair_fairness_neutral":"NEKEIČIA PRADINIO TEISINGUMO","repair_from":"Absent resident","repair_to":"Covered by","repair_date":"Date / shift","my_assignment":"My assignment","their_assignment":"Other person's assignment","request_swap":"PROPOSE SWAP","request_sent":"Swap request sent.","incoming":"Incoming requests","accept":"ACCEPT","reject":"REJECT","accepted":"Swap approved and applied.","accepted_pending":"Both residents accepted the swap. In the beta, the senior scheduler performs the final hard-rule validation and applies it.","finalize_swap":"APPLY APPROVED SWAP","swap_applied":"Swap applied, hard rules revalidated, and backups recalculated.","swap_finalize_failed":"The swap could not be applied because final validation would violate a hard rule.","rejected":"Swap rejected.","hard_reject":"Swap rejected because it would violate a hard rule.","history":"Swap history","pending":"Laukia","approved":"Approved","rejected_status":"Rejected",
"calendar_title":"My calendar schedule","calendar_help":"Download a one-time .ics snapshot or subscribe once to a private calendar feed. The feed is refreshed after a new grafikas is published and after important ACTUAL grafikas changes. Backups are included when enabled in Settings.","download_ics":"DOWNLOAD MY SCHEDULE (.ics)","calendar_feed":"Private calendar subscription URL","calendar_feed_private":"Treat this URL like a password to your schedule; do not share it. It contains a long random token and is not shown to other residents.","calendar_google":"GOOGLE CALENDAR","calendar_apple":"APPLE CALENDAR","calendar_other":"OUTLOOK CALENDAR","calendar_google_help":"On a computer in Google Calendar: Add other calendars → From URL → paste the private URL shown below. This is a one-time setup.","calendar_apple_help":"Apple Calendar can subscribe directly. The button should open the Calendar subscription prompt.","calendar_other_help":"Outlook can subscribe to the same private iCalendar URL (Add calendar → Subscribe from web). For another app, use the .ics file or subscription URL if supported.",
"proof_title":"My grafikas proof","proof_intro":"This visual check shows exactly what matched your needs and where mismatches remain. It displays final results rather than program code.","matches":"MATCHES","partial":"PARTIAL","mismatch":"DOES NOT MATCH","baseline":"At publication","current":"Now","hard_ok":"Hard unavailability respected","hard_bad":"Hard rule violated","soft_off_ok":"Requested days off","preferred_ok":"Preferred work dates","workload_ok":"Monthly workload target","style_component":"Work-style criterion","missed_dates":"Mismatched dates","criterion":"Criterion","result":"Result","score":"Fulfillment","explanation":"Explanation","proof_all_good":"Based on the submitted data, hard rules are respected and active soft preferences have no major mismatch.","proof_soft_issues":"Hard rules are respected, but some soft preferences were not fully fulfilled.","proof_hard_issue":"A hard-rule mismatch was detected and the grafikas requires review.","no_active_preferences":"No active preference was submitted for this category.","swap_suggestion":"If no hard rule is violated but a soft preference remains unmet, you can look for a voluntary solution in the Swaps tab.",
"rules_title":"Schedule rules","read":"Read","edit":"Edit","save_rules":"SAVE RULE CHANGES","rules_saved":"Rules updated.","edit_senior_only":"Only the senior scheduler can edit the rules.","yes":"YES","no":"NO","reminder_kind":"Reminder","publication_kind":"Schedule publication","date":"Date","day":"Day","time":"Time","department":"Department","shift":"Shift","morning":"Morning","afternoon":"Afternoon","full_day":"Full day","night":"Night","status":"Status","details":"Details","sent":"Sent","failed":"Failed","skipped":"Skipped"
}}

TR["LT"].update({
"research":"Tyrimas","research_title":"Tyrimo langas","research_survey":"Anketa","research_dashboard":"Tyrimo skydas","research_phase":"Etapas","research_baseline":"Prieš naudojimą","research_followup":"Po naudojimo","research_likert_help":"1 = visiškai nesutinku · 5 = visiškai sutinku","research_submit":"IŠSAUGOTI ANKETĄ","research_saved":"Tyrimo anketa išsaugota.","research_privacy":"Atsakymai analizei saugomi atskirai nuo grafiko. Seniūnė SP mato tik grupės suvestines ir anoniminius komentarus; ŠR tyrimo lange gali matyti deidentifikuotus atsakymus. Individualūs vardai šiame lange nerodomi.","research_response_count":"Atsakymų skaičius","research_mean":"Vidurkis","research_change":"Pokytis","research_operational":"Operaciniai mėnesio rodikliai","research_survey_results":"Anketos rezultatai","research_deidentified":"Deidentifikuoti atsakymai","research_comments":"Anoniminiai komentarai","research_gm_note":"Seniūnės vaizde rodomi tik grupės lygio rezultatai, kad individualūs atsakymai nebūtų naudojami personalo vertinimui.","research_rs_note":"ŠR tyrėjo vaizde papildomai rodomi deidentifikuoti individualūs įrašai kokybės kontrolei ir vėlesnei analizei.","research_no_data":"Dar nėra tyrimo duomenų.","research_month_note":"Operaciniai rodikliai skaičiuojami pasirinktam mėnesiui; anketų suvestinė apima visus pateiktus įrašus.","research_stress":"Kiek stresą kelia grafiko sudarymo / keitimo procesas? (0–10)","research_changes":"Kiek kartų per mėnesį paprastai prašote ar atliekate grafiko pakeitimą?","research_contact":"Kaip dažnai reikia kreiptis į seniūnę dėl neaiškaus ar neteisingo grafiko?","research_problem":"Didžiausia dabartinio proceso problema","research_improve":"Ką labiausiai reikėtų pagerinti?","research_easy":"Sistema lengva naudotis","research_mobile":"Mobilioji versija lengva naudotis","research_actual":"Sistema rodo realų aktualų grafiką po pakeitimų","research_system_actual":"Naudingas skirtumas tarp sistemos pradinio ir faktinio grafiko","research_continue":"Norėčiau tęsti šios sistemos naudojimą vietoje ankstesnio metodo","research_access_denied":"Tyrimo skydas prieinamas tik ŠR ir SP","research_hard_errors":"Privalomų taisyklių klaidos","research_changed_assignments":"Pakeistos normalios pamainos","research_normal_swaps":"Normalių apsikeitimų","research_backup_swaps":"Dublių apsikeitimų","research_completed_covers":"Realiai įvykdyti pavadavimai"
})
TR["EN"].update({
"research":"Research","research_title":"Radiology Scheduler research window","research_survey":"Research survey","research_dashboard":"Research dashboard","research_phase":"Phase","research_baseline":"Before use","research_followup":"After use","research_likert_help":"1 = strongly disagree · 5 = strongly agree","research_submit":"SAVE RESEARCH SURVEY","research_saved":"Research survey saved.","research_privacy":"Research answers are stored separately from scheduling data. The current senior SP sees group summaries and anonymous comments only; the ŠR research view can inspect de-identified responses. Individual names are not shown in this window.","research_response_count":"Response count","research_mean":"Mean","research_change":"Change","research_operational":"Monthly operational metrics","research_survey_results":"Survey results","research_deidentified":"De-identified responses","research_comments":"Anonymous comments","research_gm_note":"The senior view shows group-level results only so individual responses are not used for personnel evaluation.","research_rs_note":"The ŠR researcher view additionally shows de-identified individual records for quality control and later analysis.","research_no_data":"No research data yet.","research_month_note":"Operational metrics use the selected month; survey summaries include all submitted responses.","research_stress":"How stressful is the scheduling / change process? (0–10)","research_changes":"How many grafikas changes do you usually request or participate in per month?","research_contact":"How often do you need to contact the senior because the grafikas is unclear or incorrect?","research_problem":"Biggest problem with the current process","research_improve":"What should be improved most?","research_easy":"The platform is easy to use","research_mobile":"The mobile version is easy to use","research_actual":"The platform reflects the real current grafikas after changes","research_system_actual":"The SYSTEM versus ACTUAL distinction is useful","research_continue":"I would prefer to continue using this platform rather than return to the previous method","research_access_denied":"The research dashboard is available only to ŠR and SP","research_hard_errors":"HARD errors","research_changed_assignments":"Changed normal assignments","research_normal_swaps":"Normal swaps","research_backup_swaps":"Backup swaps","research_completed_covers":"Completed actual covers"
})

# V2.5.53 — wording aligned with critical exposure + weekly recovery constitution.
# The legacy 0–100 summary score remains visible for continuity, but it is NOT
# the optimizer hierarchy and never overrules the explicit lexicographic locks.
TR["LT"].update({
    "fairness_100_note":"100 % yra suvestinis diagnostinis rodiklis, o ne solverio prioritetų formulė. Pirmame mėnesyje be ankstesnės savaitgalių istorijos aiškiai pasirinktas savaitgalio „Pageidauju dirbti“ laikomas savanoriška nepopuliaria pamaina: įvykdytas savanoriškas vienetas gali būti išimtas iš DABARTINIO savaitgalio / SPS RO fairness skaičiaus, o likęs nesavanoriškas krūvis lieka 0–1 water-fill. Tikras RAW dirbtas savaitgalio krūvis vis tiek išsaugomas istorijoje ir veikia vėlesnių mėnesių balansą.",
    "fairness_formula_month":"Rodoma 0–100 formulė yra tęstinis suvestinis indikatorius, bet ji NĖRA solverio prioritetų hierarchija. SPS UG ir penktadienių exposure išlieka raw 0–1 struktūriniai guardrail. Pirmame mėnesyje su savaitgalio savanoriais SPS RO / savaitgalio 0–1 fairness taikomas likusiam NESAVANORIŠKAM krūviui; RAW matomas skirtumas rodomas atskirai ir nėra paslepiamas.",
    "fairness_formula_cumulative":"Kaupiamasis 0–100 indikatorius naudoja paskelbtų mėnesių sukauptą istoriją. Papildomai postų lygybė sekama atskirai per cumulative exposure ir FUTURE CATCH-UP, kad laikinas necritical nukrypimas būtų kompensuotas ateityje.",
    "voluntary_unpopular_goal":"Savaitgalio „Pageidauju dirbti“ pirmame mėnesyje be istorijos gauna atskirą savanoriškos nepopuliarios pamainos sluoksnį: po ABSOLUTE HARD ir RESIDENT HARD sistema pirmiausia bando išpildyti savanorius, o likusį nesavanorišką savaitgalių krūvį water-fillina 0–1.",
    "voluntary_unpopular_explain":"Visa diena „Pageidauju dirbti“ savaitgalį reiškia vieną savanorišką tos dienos vienetą, o ne automatiškai AM+PM. Jei grafikas nepriklausomai skiria ir antrą pusdienį, papildomas vienetas lieka fairness apskaitoje. RAW realiai dirbtos pamainos išsaugomos ir kitą mėnesį grįžta į cumulative balansą.",
    "other_preferences_explain":"Įprastas SOFT vis dar optimizuojamas tik aukštesniuose užraktuose ir negali pralaužti saugos, RESIDENT HARD, SPS UG, penktadienių ar kitų struktūrinių guardrail. Vienintelė aiški išimtis — pirmo mėnesio savanoriškas savaitgalio „Pageidauju dirbti“: savanoriškas vienetas gali būti išimtas iš dabartinio SPS RO / savaitgalio fairness skaičiaus, o likęs nesavanoriškas krūvis privalo likti 0–1.",
})
TR["EN"].update({
    "fairness_100_note":"100% is a summary diagnostic, not the solver priority formula. In the first month with no prior weekend history, an explicit weekend “prefer to work” is treated as volunteering for unpopular duty: an honored volunteer unit may sit outside the CURRENT weekend / SPS RO fairness count, while the remaining non-voluntary burden stays at 0–1 water-fill. The real RAW weekend workload is still saved to history and affects later-month balancing.",
    "fairness_formula_month":"The displayed 0–100 formula is a continuity summary indicator, NOT the solver hierarchy. SPS UG and Friday remain raw 0–1 structural guardrails. In a first-month volunteer case, SPS RO / weekend 0–1 fairness is applied to the remaining NON-voluntary burden; the RAW visible spread is reported separately rather than hidden.",
    "fairness_formula_cumulative":"The cumulative 0–100 indicator uses published-month history. Post equality is also tracked separately through cumulative exposure and FUTURE CATCH-UP so temporary noncritical imbalance is repaid later.",
    "voluntary_unpopular_goal":"A weekend “prefer to work” in the first no-history month gets a dedicated unpopular-duty volunteer layer: after ABSOLUTE HARD and RESIDENT HARD, the engine first tries to honor willing residents and water-fills the remaining non-voluntary weekend burden at 0–1.",
    "voluntary_unpopular_explain":"A whole-day weekend “prefer to work” means one voluntary day unit, not an automatic AM+PM double. If the grafikas independently needs a second half-day, that extra unit remains in the fairness count. RAW worked exposure is retained in history and returns to cumulative balancing in later months.",
    "other_preferences_explain":"Ordinary SOFT is still optimized only inside higher safety, Resident-HARD, SPS UG, Friday and structural guardrails. The one explicit exception is the first-month weekend-work volunteer rule: an honored volunteer unit may sit outside current SPS RO / weekend fairness, while the remaining non-voluntary burden must stay at 0–1.",
})

# V2.5.55 — voluntary swap consequence/ACK layer with labour-time reality guardrails.
TR["LT"].update({
    "swap_48_warning":"Šis savanoriškas swapas turi pasekmių tavo krūviui / poilsiui. Peržiūrėk lentelę ir patvirtink tik jei sąmoningai sutinki.",
    "swap_48_ack":"Peržiūrėjau visas šio swapo pasekmes lentelėje, suprantu jas ir savanoriškai sutinku su šiuo konkrečiu apsikeitimu.",
    "swap_48_other":"Šis swapas turi pasekmių ir kitam rezidentui. Jis / ji jas matys savo lentelėje ir turės patvirtinti atskirai.",
    "swap_48_only_exception":"ACK galioja tik šiam konkrečiam savanoriškam swapui. Jis neapeina ABSOLUTE HARD, patvirtinto neatvykimo, overlap/coverage, ≤12 h/d., ≥11 h tarp darbo dienų, ≤6 darbo dienų/7 d. ar ≤60 h/7 d. Post-double recovery ir naujas savo RESIDENT HARD konfliktas swape gali būti sąmoningai priimti ir todėl rodomi kaip ACK, o ne automatinis blokas.",
    "swap_preview_invalid":"Šio apsikeitimo negalima siūlyti / priimti dėl kitos privalomos taisyklės: {reason}",
    "swap_48_reaccept":"Swapo pasekmės nuo pasiūlymo sukūrimo pasikeitė. Reikia naujo aiškaus rezidento patvirtinimo; pasiūlymą sukurkite iš naujo.",
    "swap_note":"Savanoriškas swapas keičia tik FAKTINĮ grafiką. Prieš sutikdamas kiekvienas paveiktas rezidentas mato pasekmių lentelę. Swapas blokuojamas dėl ABSOLUTE / operacinių ir darbo-laiko guardrailų: overlap, pateisinamas neatvykimas, >12 h/d., <11 h poilsio, >6 darbo dienų/7 d. ar aktyvaus swapo hard-cap viršijimo (iki 60 h/7 d.). 12 h double, >40/>48 h, 6 dienų seka, post-double recovery ir savo RESIDENT HARD override rodomi kaip ACK. SYSTEM fairness baseline nesikeičia.",
    "labour_hard_summary":"Generuojant: ≤12 val./d.; ≥11 val. tarp darbo dienų; bent 1 visiškai laisva diena per slenkančias 7 d.; ≤48 žinomų darbo valandų/7 d.; tikslas ~40 val./7 d.; po 2 iš eilės double kita diena PM arba poilsis. Po publikavimo voluntary swapui taikomas atskiras consequence + ACK režimas: >48 h nebėra automatinis blokas, tačiau >12 h/d., <11 h poilsio, >6 darbo dienų/7 d., aktyvus swap hard-cap ir ABSOLUTE/overlap/coverage lieka blokai.",
    "fairness_hierarchy_intro":"Generuojant pirmiausia saugomos absoliučios saugos ir darbo taisyklės. Tada SPS RO, SPS UG ir savaitgaliai paskirstomi kuo lygiau, saugomi rezidentų privalomi negalėjimai, poilsis ir darbo krūvis, o po to tenkinami kiti pageidavimai. Po publikavimo savanoriški apsikeitimai turi atskirą pasekmių lentelę ir aiškų patvirtinimą.",
})
TR["EN"].update({
    "swap_48_warning":"This voluntary swap changes your workload/rest pattern. Review the consequence table and confirm only if you knowingly accept it.",
    "swap_48_ack":"I reviewed all consequences in the table, understand them, and voluntarily agree to this specific swap.",
    "swap_48_other":"This swap also has consequences for the other resident. They will see their own table and must acknowledge it separately.",
    "swap_48_only_exception":"The acknowledgement applies only to this specific voluntary swap. It never bypasses ABSOLUTE HARD, approved absence, overlap/coverage, ≤12h/day, ≥11h daily rest, ≤6 workdays/7d or ≤60h/7d. Post-double recovery and a self-overridden Resident-HARD request may be knowingly accepted in a swap and are therefore shown as ACK warnings rather than automatic blocks.",
    "swap_preview_invalid":"This swap cannot be proposed / accepted because another mandatory rule would be violated: {reason}",
    "swap_48_reaccept":"The swap consequences changed after the request was created. A fresh explicit acknowledgement is required; recreate the swap request.",
    "swap_note":"Voluntary swaps change only the ACTUAL schedule. Each affected resident sees a consequence table before consent. The swap is blocked by ABSOLUTE/operational and labour-time guardrails: overlap, approved absence, >12h/day, <11h rest, >6 workdays/7d or the active swap hard cap (up to 60h/7d). New 12h doubles, >40/>48h load, six-day streaks, post-double recovery patterns and self-overridden Resident-HARD requests are ACK warnings. SYSTEM fairness remains frozen. Workplace/post fairness, modality mix, US exposure and diversity never block a mutually accepted ACTUAL swap.",
    "labour_hard_summary":"Generation: ≤12h/day; ≥11h between workdays; at least 1 fully free day per rolling 7d; ≤48 known hours/7d; target ~40h/7d; after 2 consecutive doubles the next day is PM-only or off. Post-publication voluntary swaps use a separate consequence + ACK mode: >48h is not an automatic blocker, while >12h/day, <11h rest, >6 workdays/7d, the active swap hard cap and ABSOLUTE/overlap/coverage remain blockers.",
    "fairness_hierarchy_intro":"During generation: ABSOLUTE safety/work rules → Cannot-work / RESIDENT HARD with zero violations → ADMIN RAW Saturday/Sunday/weekend water-fill at the tightest feasible spread (weekend preferences cannot bypass it) → Dream Team SP+ŠR+GE together on CENTRO RO at least once per represented workweek when mathematically feasible → SPS RO/SPS UG and every other workplace water-filled as tightly as feasible → recovery/workload fairness → remaining SOFT wishes. After publication, ACTUAL swaps may disturb SYSTEM fairness only after both residents consent and SP gives final approval.",
})

# V2.5.66 — multiple swaps are allowed, but one concrete shift can have only
# one active future offer at a time. Plain-language UX; DB trigger is the
# authoritative concurrency guard.
TR["LT"].update({
    "swap_shift_busy":"Ši pamaina jau įtraukta į kitą laukiantį apsikeitimą. Galite turėti kelis apsikeitimus vienu metu, tačiau kiekviena konkreti pamaina gali būti tik viename aktyviame pasiūlyme. Pirmiausia užbaikite arba atšaukite esamą pasiūlymą.",
    "backup_swap_shift_busy":"Šis dublio slotas jau įtrauktas į kitą laukiantį dublių apsikeitimą. Pasirinkite kitą slotą arba pirmiausia atšaukite / užbaikite esamą pasiūlymą.",
    "my_outgoing_swaps":"Mano laukiantys pasiūlymai",
    "cancel_my_swap":"ATŠAUKTI MANO PASIŪLYMĄ",
    "swap_cancelled":"Apsikeitimo pasiūlymas atšauktas.",
    "swap_cancel_failed":"Šio pasiūlymo atšaukti nepavyko — jis galėjo būti ką tik priimtas arba pakeistas.",
    "multiple_swap_help":"Galite turėti kelis aktyvius apsikeitimus, jei jie liečia skirtingas pamainas. Ta pati konkreti pamaina vienu metu gali būti tik viename aktyviame pasiūlyme.",
})
TR["EN"].update({
    "swap_shift_busy":"This shift is already part of another pending swap. You may have several swaps at the same time, but each concrete shift can be in only one active offer. Finish or cancel the existing offer first.",
    "backup_swap_shift_busy":"This backup duty is already part of another pending backup swap. Choose another duty or finish/cancel the existing offer first.",
    "my_outgoing_swaps":"My pending offers",
    "cancel_my_swap":"CANCEL MY OFFER",
    "swap_cancelled":"Swap offer cancelled.",
    "swap_cancel_failed":"This offer could not be cancelled — it may already have been accepted or changed.",
    "multiple_swap_help":"You may have several active swaps when they involve different shifts. The same concrete shift can be in only one active offer at a time.",
})


# V2.5.11 — role-specific 6-month research workflow
TR["LT"].update({
"research_role_resident":"Rezidentas · tyrimo dalyvis","research_role_researcher":"Rezidentas · tyrėjas","research_role_senior":"Rezidentė · seniūnė / grafikų sudarytoja",
"research_study_plan":"6 mėn. tyrimo planas","research_study_period":"Prospektyvus naudojimas: 2026 m. spalis – 2027 m. kovas","research_primary_outcomes":"Pagrindiniai rodikliai: privalomų taisyklių laikymasis, grafiko sudarymo laikas ir rankinių korekcijų skaičius.",
"research_checkpoint":"Tyrimo matavimo taškas","research_baseline_checkpoint":"Pradinis vertinimas · prieš paleidimą (2026 rugsėjis)","research_month3_checkpoint":"3 mėn. pakartotinis vertinimas (2026 gruodis)","research_month6_checkpoint":"6 mėn. pakartotinis vertinimas (2027 kovas)",
"research_checkpoint_done":"Užpildyta","research_checkpoint_locked":"Dar neaktyvuota","research_checkpoint_pending":"Neužpildyta","research_next_task":"Kitas tyrimo veiksmas","research_resident_note":"Rezidentui reikia tik trijų trumpų anketų per visą tyrimą: pradinio vertinimo, po ~3 mėn. ir po ~6 mėn.",
"research_completion":"Anketų užpildymas","research_expected":"Numatyta","research_export":"Eksportas analizei","research_download_surveys":"ATSISIŲSTI DEIDENTIFIKUOTAS ANKETAS (.csv)","research_download_monthly":"ATSISIŲSTI MĖNESIO RODIKLIUS (.csv)",
"research_monthly_table":"Spalis–kovas: automatiniai operaciniai rodikliai","research_scheduler_section":"SP / Seniūnės grafikų sudarymo darbo krūvis","research_scheduler_intro":"SP kaip dabartinė Seniūnė pildo du trumpus įrašus kiekvienam tyrimo mėnesiui: iškart paruošus grafiką ir mėnesiui pasibaigus. Operacinių apsikeitimų ir pavadavimų skaičius sistema renka automatiškai.",
"research_scheduler_month":"Tyrimo mėnuo","research_scheduler_checkpoint":"Seniūnės SP matavimo taškas","research_after_creation":"Iškart paruošus grafiką","research_after_month":"Mėnesiui pasibaigus",
"research_workflow_method":"Kaip šį mėnesį buvo sudarytas grafikas?","research_method_tool":"Tik sistema","research_method_excel":"Tik Excel","research_method_shadow":"Excel + sistema: lygiagretus palyginimas",
"research_total_minutes":"Bendras tavo aktyvus laikas grafikui paruošti (min.)","research_corrections":"Rankinių korekcijų / iteracijų skaičius","research_resident_contacts":"Kiek rezidentų kontaktų / derinimų reikėjo?","research_communication_minutes":"Kiek laiko užėmė komunikacija dėl grafiko? (min.)",
"research_scheduler_stress":"Grafiko sudarymo stresas (0–10)","research_fairness_confidence":"Pasitikėjimas, kad paskirstymas teisingas (1–5)","research_hard_confidence":"Pasitikėjimas, kad privalomos taisyklės išlaikytos (1–5)","research_scheduler_satisfaction":"Pasitenkinimas galutiniu grafiku (1–5)",
"research_excel_minutes":"Excel laikas (min.)","research_tool_minutes":"Sistemos laikas (min.)","research_excel_corrections":"Excel korekcijų sk.","research_tool_corrections":"Sistemos korekcijų / pakartotinių generavimų sk.",
"research_post_minutes":"Laikas po publikavimo pakeitimams / problemoms (min.)","research_post_interventions":"Kiek pakeitimų reikėjo tavo tiesioginio įsikišimo?","research_post_contacts":"Kiek žinučių / skambučių dėl grafiko gavai per mėnesį?",
"research_actual_confidence":"Pasitikėjimas, kad portalas rodė realų faktinį grafiką (1–5)","research_use_next":"Ar rinktumeisi sistemą kitam mėnesiui?","research_yes":"Taip","research_unsure":"Neaišku","research_no":"Ne",
"research_scheduler_notes":"Pastabos / kas užėmė daugiausia laiko","research_scheduler_saved":"Seniūnės SP tyrimo įrašas išsaugotas.","research_scheduler_status":"Seniūnės SP duomenų užpildymas",
"research_generation_telemetry":"Automatiniai generavimo rodikliai","research_generation_attempts":"Generavimo bandymų","research_solver_seconds":"Skaičiavimo laikas, s","research_generation_success":"Sėkmingų generavimų",
"research_observer_tab":"Tyrimo atsiliepimai","research_observer_intro":"Tik peržiūros teisės grafikui nesikeičia. Šiame lange galima tik pateikti tyrimo atsiliepimą apie stebėsenos patogumą.","research_observer_checkpoint":"Administratorės vertinimas",
"research_obs_actual":"Lengva nustatyti, kas realiai dirba kiekvieną pamainą.","research_obs_changes":"Lengva peržiūrėti pakeitimus po publikavimo.","research_obs_system_actual":"Sistemos pradinio ir faktinio grafiko skirtumas yra naudingas.","research_obs_privacy":"Sistema suteikia pakankamai matomumo neatskleisdama nereikalingų privačių rezidentų duomenų.","research_obs_log":"Pakeitimų žurnalas yra suprantamas.","research_obs_fairness":"Teisingumo informacija yra suprantama.","research_obs_trust":"Pasitikiu portale rodoma operacine informacija.","research_obs_missing":"Kokios informacijos trūksta, kai reikia suprasti realią skyriaus situaciją?","research_observer_saved":"Administratorės tyrimo feedback išsaugotas.",
"research_data_quality":"Duomenų pilnumas","research_missing_scheduler":"Trūksta Seniūnės SP įrašo","research_complete":"Pilna","research_researcher_only":"Ši išsami skiltis matoma tik ŠR tyrėjo paskyroje."
})
TR["EN"].update({
"research_role_resident":"Resident · study participant","research_role_researcher":"Resident · researcher","research_role_senior":"Resident · senior scheduler",
"research_study_plan":"6-month research plan","research_study_period":"Prospective use: October 2026 – March 2027","research_primary_outcomes":"Primary outcomes: HARD-rule compliance, scheduler time, and number of manual corrections.",
"research_checkpoint":"Research checkpoint","research_baseline_checkpoint":"Baseline · pre-launch (September 2026)","research_month3_checkpoint":"3-month follow-up (December 2026)","research_month6_checkpoint":"6-month follow-up (March 2027)",
"research_checkpoint_done":"Completed","research_checkpoint_locked":"Not active yet","research_checkpoint_pending":"Not completed","research_next_task":"Next research task","research_resident_note":"Residents complete only three short surveys during the whole study: baseline, ~3 months, and ~6 months.",
"research_completion":"Survey completion","research_expected":"Expected","research_export":"Analysis export","research_download_surveys":"DOWNLOAD DE-IDENTIFIED SURVEYS (.csv)","research_download_monthly":"DOWNLOAD MONTHLY METRICS (.csv)",
"research_monthly_table":"October–March: automatic operational metrics","research_scheduler_section":"SP / senior scheduler workload","research_scheduler_intro":"SP as the current senior completes two short records per study month: immediately after preparing the grafikas and after the month ends. Operational swap / cover counts are collected automatically.",
"research_scheduler_month":"Study month","research_scheduler_checkpoint":"Senior SP checkpoint","research_after_creation":"Immediately after grafikas preparation","research_after_month":"After the month is complete",
"research_workflow_method":"How was this month's grafikas prepared?","research_method_tool":"Tool only","research_method_excel":"Excel only","research_method_shadow":"Excel + Tool parallel comparison",
"research_total_minutes":"Total active time you spent preparing the grafikas (min)","research_corrections":"Manual corrections / iterations","research_resident_contacts":"Resident contacts / coordination episodes","research_communication_minutes":"Time spent on grafikas communication (min)",
"research_scheduler_stress":"Schedule-preparation stress (0–10)","research_fairness_confidence":"Confidence allocation is fair (1–5)","research_hard_confidence":"Confidence HARD rules are respected (1–5)","research_scheduler_satisfaction":"Satisfaction with final grafikas (1–5)",
"research_excel_minutes":"Excel time (min)","research_tool_minutes":"Tool time (min)","research_excel_corrections":"Excel corrections","research_tool_corrections":"Tool corrections / regenerations",
"research_post_minutes":"Time spent on post-publication changes/problems (min)","research_post_interventions":"Changes requiring your direct intervention","research_post_contacts":"Schedule-related messages/calls received during month",
"research_actual_confidence":"Confidence portal reflected the true ACTUAL grafikas (1–5)","research_use_next":"Would you choose the Tool next month?","research_yes":"Yes","research_unsure":"Unsure","research_no":"No",
"research_scheduler_notes":"Notes / what consumed the most time","research_scheduler_saved":"Senior SP research record saved.","research_scheduler_status":"Senior SP data completion",
"research_generation_telemetry":"Automatic generation telemetry","research_generation_attempts":"Generation attempts","research_solver_seconds":"Solver time, s","research_generation_success":"Successful generations",
"research_observer_tab":"Research feedback","research_observer_intro":"Read-only scheduling rights remain unchanged. This tab only allows research feedback about the monitoring experience.","research_observer_checkpoint":"Administrator evaluation",
"research_obs_actual":"It is easy to determine who is actually working each shift.","research_obs_changes":"It is easy to review changes made after publication.","research_obs_system_actual":"The SYSTEM baseline versus ACTUAL distinction is useful.","research_obs_privacy":"The platform provides enough visibility without exposing unnecessary private resident information.","research_obs_log":"The change log is understandable.","research_obs_fairness":"The fairness information is understandable.","research_obs_trust":"I trust the operational information shown in the portal.","research_obs_missing":"What information is missing when you need to understand the real departmental staffing situation?","research_observer_saved":"Administrator research feedback saved.",
"research_data_quality":"Data completeness","research_missing_scheduler":"Missing senior SP record","research_complete":"Complete","research_researcher_only":"This detailed section is visible only to the ŠR researcher account."
})

# V2.5.96 — monthly baseline fairness + live ACTUAL ledger; no future catch-up.
TR["LT"].update({
    "metric_saturday":"Šeštadienių skirtumas",
    "metric_sunday":"Sekmadienių skirtumas",
    "fairness_hierarchy_intro":"Kiekvienas mėnuo prasideda nuo švaraus SYSTEM baseline: ABSOLUTE HARD → kritinis struktūrinis water-fill (SPS RO, SPS UG, ŠEŠTADIENIAI, SEKMADIENIAI ir penktadieniai) → RESIDENT HARD / poilsis / tikslus workload → aktyvūs pageidavimai ir darbo pobūdžio nustatymai → likusių postų optimizavimas. 12 val. darbo dienos pageidavimas gali perskirstyti jau reikalingas dvigubas pamainas ir dėl to išplėsti dublių skirtumą, jei HARD ir kritinis water-fill lieka validūs. Po publikavimo leidžiami ACTUAL pakeitimai gali water-fill pakeisti. Ankstesnių mėnesių fairness kitam mėnesiui catch-up nesukuria.",
    "fairness_monthly_explain":"SYSTEM mėnesio fairness rodo algoritmo baseline publikavimo momentu. ACTUAL mėnesio fairness perskaičiuojamas iš realaus dabartinio darbo po manual override'ų, swapų, repair ir realiai įvykdytų dublių. Platesnis ACTUAL spread leidžiamas ir rodomas, bet nėra perkeliamas kaip skola į kitą mėnesį.",
    "fairness_cumulative_explain":"Istorija yra tik auditas / stebėjimas. Ji NENAUDOJAMA kito mėnesio solverio kompensacijai ar catch-up paskyrimams.",
    "fairness_100_note":"Fairness procentas yra diagnostinis mėnesio balanso rodiklis. SYSTEM baseline turi laikytis generatoriaus water-fill; ACTUAL gali nukrypti po leidžiamų žmogaus sprendimų ir tada rodomas toks, koks yra realybėje.",
    "fairness_formula_cumulative":"Istoriniai mėnesių rodikliai rodomi palyginimui, tačiau nėra solverio įvestis ir nesukuria ateities future catch-up / catch-up.",
    "fairness_swap_neutral":"SYSTEM baseline lieka užšaldytas auditui, tačiau swapas ar manual override pakeičia ACTUAL fairness statistiką pagal realų darbą. Tai nėra ateities fairness skola.",
    "fairness_forced_change":"Post-publication repair ir realiai įvykdytas dublio cover keičia ACTUAL realaus darbo fairness statistiką. SYSTEM publikavimo baseline lieka nepakeistas auditui. Jokio future catch-up nėra.",
    "fairness_frozen_note":"SYSTEM = publikavimo momento algoritmo water-fill baseline. ACTUAL = realus dabartinis pasiskirstymas po override'ų, swapų, repair ir completed cover. Abu rodomi atskirai; ACTUAL istorija yra tik stebėjimui ir niekada nevaldo kito mėnesio generatoriaus.",
    "fairness_cumulative_goal":"Nėra fairness catch-up sluoksnio. Kiekvienas mėnuo vėl pradedamas nuo neutralaus water-fill baseline.",
    "voluntary_unpopular_goal":"Kritiniai nesavanoriško krūvio komponentai pirmiausia water-fill'inami. Tada aktyvūs individualūs pageidavimai ir darbo pobūdžio nustatymai tenkinami maksimaliai, kol nepažeidžiamos privalomos taisyklės ir kritiniai struktūriniai guardrailai.",
    "voluntary_unpopular_explain":"Aktyvus pageidavimas nėra lyginamas su neutraliu N/A kaip konkuruojančiu noru. Pvz., jei tik vienas rezidentas pasirenka dažniausiai 12 val. darbo dienas, sistema turi jam skirti kuo daugiau jau matematiškai reikalingų AM+PM dienų, jei tai nepažeidžia HARD ir kritinio water-fill. Po publikavimo abipusis swapas gali keisti ACTUAL balansą dar plačiau.",
    "other_preferences_explain":"Po privalomų taisyklių ir kritinio struktūrinio water-fill sistema aktyviai maksimalizuoja realiai pateiktų pageidavimų bei darbo pobūdžio nustatymų išpildymą. Neutralūs žmonės nekonkuruoja su aiškiai išreikštu pageidavimu. Darbo dienos trukmės pageidavimas gali perskirstyti dvigubas pamainas, tačiau negali kurti papildomo bendro dublių poreikio ar pažeisti ABSOLUTE/HARD bei kritinių šeštadienio/sekmadienio/SPS guardrailų.",
    "swap_note":"Savanoriškas swapas keičia ACTUAL grafiką ir ACTUAL fairness statistiką. SYSTEM baseline auditui neperrašomas. Water-fill nėra post-publication swapo blokatorius, todėl leidžiamas ACTUAL spread padidėjimas aiškiai atsispindi statistikoje. Jokio kito mėnesio catch-up dėl to nėra.",
    "repair_help":"Liga, atostogos ar force majeure keičia ACTUAL grafiką. Realaus darbo fairness perskaičiuojamas pagal tai, kas iš tikrųjų dirba; SYSTEM publikavimo baseline lieka auditui. Šis skirtumas niekada nekuria fairness skolos ar kito mėnesio catch-up.",
    "repair_applied":"Pakeitimas pritaikytas ACTUAL grafikui. ACTUAL fairness perskaičiuotas pagal realų darbą; SYSTEM baseline liko nepakeistas auditui. Future catch-up nėra.",
    "repair_load_help":"Operacinis audito skaitiklis. Realiai pakeistas darbas įeina į ACTUAL mėnesio statistiką, tačiau nėra paverčiamas ateities fairness skola.",
    "repair_fairness_neutral":"ACTUAL FAIRNESS PERSKAIČIUOTA",
})
TR["EN"].update({
    "metric_saturday":"Saturday spread",
    "metric_sunday":"Sunday spread",
    "fairness_hierarchy_intro":"Every month starts from a clean SYSTEM baseline: ABSOLUTE HARD → critical structural water-fill (SPS RO, SPS UG, SATURDAYS, SUNDAYS and Fridays) → RESIDENT HARD / rest / exact workload → active preferences and work-style settings → remaining workplace optimization. A 12-hour workday preference may redistribute the already-needed double-shift pool and widen double spread when HARD and critical water-fill remain valid. Allowed ACTUAL changes may diverge after publication. Prior-month fairness never creates future catch-up.",
    "fairness_monthly_explain":"SYSTEM monthly fairness is the algorithmic publication baseline. ACTUAL monthly fairness is recalculated from real current work after manual overrides, swaps, repairs and completed backup covers. A wider ACTUAL spread is allowed and shown, but never carried forward as a debt.",
    "fairness_cumulative_explain":"History is audit/monitoring only. It is NOT used by the next month's solver for compensation or catch-up assignments.",
    "fairness_100_note":"The fairness percentage is a diagnostic monthly balance indicator. SYSTEM must satisfy the generator water-fill baseline; ACTUAL may diverge after allowed human decisions and is shown exactly as reality stands.",
    "fairness_formula_cumulative":"Historical monthly metrics are displayed for comparison only; they are not solver input and create no future future catch-up/catch-up.",
    "fairness_swap_neutral":"SYSTEM remains frozen for audit, but a swap or manual override changes ACTUAL fairness statistics according to real work. This never becomes a future fairness debt.",
    "fairness_forced_change":"Post-publication repair and a completed backup cover change ACTUAL real-work fairness statistics. The SYSTEM publication baseline remains unchanged for audit. There is no future catch-up.",
    "fairness_frozen_note":"SYSTEM = the publication-time algorithmic water-fill baseline. ACTUAL = the real current distribution after overrides, swaps, repairs and completed covers. Both are shown separately; ACTUAL history is monitoring-only and never controls the next month's generator.",
    "fairness_cumulative_goal":"There is no fairness catch-up layer. Every month starts again from a neutral water-fill baseline.",
    "voluntary_unpopular_goal":"Critical involuntary burden is water-filled first. Active individual preferences and work-style settings are then fulfilled as much as possible while mandatory rules and critical structural guardrails remain valid.",
    "voluntary_unpopular_explain":"An active preference is not treated as competing with a neutral N/A. For example, if only one resident prefers mostly 12-hour days, the system should allocate as many of the already-required AM+PM days to that resident as feasible while preserving HARD and critical water-fill. Accepted post-publication swaps may alter ACTUAL balance further.",
    "other_preferences_explain":"After mandatory rules and critical structural water-fill are protected, the system actively maximizes fulfillment of expressed preferences and work-style settings. Neutral residents do not compete with an explicit preference. Workday-length preferences may redistribute double shifts, but cannot create extra total double demand or violate ABSOLUTE/HARD or critical Saturday/Sunday/SPS guardrails.",
    "swap_note":"A voluntary swap changes the ACTUAL grafikas and ACTUAL fairness statistics. The SYSTEM baseline remains frozen for audit. Water-fill is not a post-publication swap blocker, so an allowed ACTUAL spread increase is visible in the statistics. No later-month catch-up is created.",
    "repair_help":"Sickness, leave or force majeure changes ACTUAL. Real-work fairness is recalculated from who actually works; SYSTEM remains the frozen publication baseline. The difference never creates a fairness debt or next-month catch-up.",
    "repair_applied":"Repair applied to ACTUAL. ACTUAL fairness was recalculated from real work; SYSTEM baseline remains frozen for audit. No future catch-up is created.",
    "repair_load_help":"Operational audit counter. Changed real work enters ACTUAL monthly statistics but is never converted into a future fairness debt.",
    "repair_fairness_neutral":"ACTUAL FAIRNESS UPDATED",
})

RESEARCH_ITEMS = {
"fair_undesirable":"The scheduling process distributes undesirable shifts fairly across residents.",
"fair_weekend":"Weekend duties are distributed fairly over time.",
"fair_friday":"Friday duties are distributed fairly over time.",
"fair_longitudinal":"The process accounts fairly for workload accumulated in previous months.",
"transparent_why":"I understand why I receive the shifts that I receive.",
"transparent_group":"It is easy to see whether the grafikas is fair across the whole group.",
"control":"I have enough influence over my monthly schedule.",
"hard_respected":"My unavailable dates are reliably respected.",
"prefs_used":"My scheduling preferences are taken into account when feasible.",
"prefs_balance":"The process balances my preferences with fairness to other residents.",
"swap_easy":"It is easy to arrange a shift swap when I need one.",
"swap_clear":"After swaps, it is clear who is actually responsible for each shift.",
"backup_clear":"The backup / cover process is clear.",
"trust":"I trust the scheduling process.",
"satisfaction":"Overall, I am satisfied with the way our monthly grafikas is created.",
"burden":"Schedule-related communication and corrections take too much of my time."
}
RESEARCH_ITEMS_LT = {
"fair_undesirable":"Nepatogios pamainos tarp rezidentų paskirstomos teisingai.",
"fair_weekend":"Savaitgalių budėjimai laikui bėgant paskirstomi teisingai.",
"fair_friday":"Penktadienių pamainos laikui bėgant paskirstomos teisingai.",
"fair_longitudinal":"Sistema teisingai atsižvelgia į ankstesnių mėnesių darbo krūvį.",
"transparent_why":"Suprantu, kodėl gaunu man paskirtas pamainas.",
"transparent_group":"Lengva matyti, ar grafikas teisingas visos grupės mastu.",
"control":"Turiu pakankamai įtakos savo mėnesio grafikui.",
"hard_respected":"Mano nurodytos datos, kai negaliu dirbti, patikimai išlaikomos.",
"prefs_used":"Kai įmanoma, į mano pageidavimus atsižvelgiama.",
"prefs_balance":"Mano pageidavimai subalansuojami su teisingumu kitiems rezidentams.",
"swap_easy":"Kai reikia, lengva susitarti dėl pamainos apsikeitimo.",
"swap_clear":"Po apsikeitimų aišku, kas realiai atsakingas už kiekvieną pamainą.",
"backup_clear":"Dublių / pavadavimo procesas yra aiškus.",
"trust":"Pasitikiu grafiko sudarymo procesu.",
"satisfaction":"Apskritai esu patenkintas(-a), kaip sudaromas mūsų mėnesio grafikas.",
"burden":"Su grafiku susijusi komunikacija ir taisymai užima per daug mano laiko."
}

STUDY_MONTHS = [(2026,10),(2026,11),(2026,12),(2027,1),(2027,2),(2027,3)]
RESIDENT_RESEARCH_CHECKPOINTS = [
    ("baseline", "baseline", 2026, 9),
    ("month3", "followup", 2026, 12),
    ("month6", "followup", 2027, 3),
]
OBSERVER_RESEARCH_CHECKPOINTS = [("month3", 2026, 12),("month6", 2027, 3)]
RESEARCH_EXPECTED_RESIDENTS = 16

def research_checkpoint_label(code):
    return {
        "baseline":tr("research_baseline_checkpoint"),
        "month3":tr("research_month3_checkpoint"),
        "month6":tr("research_month6_checkpoint"),
    }.get(code,code)

def research_checkpoint_for_storage(code):
    for c,phase,y,m in RESIDENT_RESEARCH_CHECKPOINTS:
        if c==code:
            return phase,y,m
    return "baseline",2026,9

def study_month_label(y,m):
    return f"{MONTHS[lang][m-1]} {y}"

MONTHS={"LT":["Sausis","Vasaris","Kovas","Balandis","Gegužė","Birželis","Liepa","Rugpjūtis","Rugsėjis","Spalis","Lapkritis","Gruodis"],"EN":list(calendar.month_name)[1:]}
WEEKDAYS={"LT":["Pr","An","Tr","Kt","Pn","Št","Sk"],"EN":["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]}
WEEKDAY_FULL={"LT":["Pirmadienis","Antradienis","Trečiadienis","Ketvirtadienis","Penktadienis","Šeštadienis","Sekmadienis"],"EN":list(calendar.day_name)}

# Language must be resolved before translating the rest of the interface.
lang = "LT"
st.sidebar.caption("Kalba: lietuvių")
# V2.5.112 FINAL ADMIN POLICY OVERRIDES — these intentionally supersede older
# V2.5.104 volunteer-weekend wording retained in historical source comments.
TR["LT"].update({
    "fairness_hierarchy_intro":"Grafikas sudaromas tokia seka: 1) sauga, įmanomumas ir privalomas padengimas; 2) 0 „Dirbti negaliu“ pažeidimų; 3) struktūrinis krūvis dalijamas kuo tolygiau, įskaitant savaitgalius ir penktadienius; 4) šių ribų viduje sistema maksimaliai pildo konkrečius rezidentų pageidavimus – tikslas 100 %, kai tai įmanoma; 5) jei lieka keli vienodai geri variantai, konfliktą išsprendžia pateikimo vieta. Prašyti visų penktadienių laisvų galima, tačiau sistema suteiks tiek, kiek leidžia sąžiningas visos grupės penktadienių balansas. Po paskelbimo apsikeitimas įsigalioja tik sutikus abiem rezidentams ir patvirtinus seniūnei.",
    "fairness_100_note":"Tikslas yra 100 % pageidavimų išpildymas, bet ne kitų rezidentų sąskaita. Jei visi norai kartu neįmanomi, sistema išpildo maksimalų skaičių jų nepažeisdama saugos, privalomo padengimo ir sąžiningo penktadienių / savaitgalių krūvio paskirstymo.",
    "fairness_monthly_goal":"Savaitgaliai, SPS RO, SPS UG ir kitos darbo vietos paskirstomos kuo tolygiau, nepažeidžiant „Dirbti negaliu“, saugos ir privalomo padengimo taisyklių.",
    "voluntary_unpopular_goal":"Pageidavimas dirbti savaitgalį yra noras, į kurį sistema stengiasi atsižvelgti, tačiau privalomas savaitgalių krūvis visai grupei išlieka paskirstomas kuo tolygiau.",
    "voluntary_unpopular_explain":"Pažymėjus „Pageidauju dirbti“ sistema stengiasi tą norą įvykdyti, jei tai neprieštarauja saugos, padengimo ir tolygaus paskirstymo taisyklėms. Po preliminaraus paskelbimo faktinį pasiskirstymą gali pakeisti savanoriški apsikeitimai.",
    "weekend_help":"Savaitgalių krūvis visai grupei paskirstomas kuo tolygiau. „Dirbti negaliu“ žymėkite tik tada, kai tuo metu iš tikrųjų negalite dirbti.",
    "preferred_help":"Sistema stengiasi įvykdyti kiekvieną „Pageidauju dirbti“ pasirinkimą. Jei keli pageidavimai susikerta, pirmiausia ieškoma geriausio bendro rezultato; pateikimo vieta svarbi tik likusiam neišsprendžiamam konfliktui.",
    "backup_swap_help":"Po preliminaraus grafiko paskelbimo galima siūlyti dublio apsikeitimą. Jis įsigalioja tik sutikus abiem rezidentams, praėjus saugos patikrą ir patvirtinus seniūnei.",
})
TR["EN"].update({
    "fairness_hierarchy_intro":"NORMAL SYSTEM schedule: TRUE ABSOLUTE / safety → zero Cannot-work violations → tightest mathematically feasible RAW Saturday, Sunday and total-weekend water-fill → SPS RO / SPS UG and all-post water-fill → Dream Team SP+ŠR+GE at CENTRO RO once per week → SOFT-1 → SOFT-2 → SOFT-3. Within each SOFT tier the horizontal water-fill and maximum total fulfilment are locked first; only then do immutable first-submission points (#1=16 … #16=1) resolve conflicts between equally fair alternatives. From October, weekend backups are a separate post-publication 12h FULL layer and never change the normal SYSTEM schedule. ACTUAL swaps require both residents plus SP final approval.",
    "fairness_100_note":"100% is a diagnostic ideal-balance score. SYSTEM weekend allocation uses RAW administrative water-fill, not resident willingness to take extra weekends. If 0–1 is mathematically impossible because of HARD availability and exact workload, the tightest proven feasible spread is shown.",
    "fairness_monthly_goal":"SYSTEM first searches for the tightest feasible RAW Saturday, Sunday and total-weekend spread. SPS RO / SPS UG and every other workplace are also water-filled as evenly as possible, while zero Cannot-work violations remain above fairness. Weekly Dream Team CENTRO RO co-location is a high administrative priority in the workplace-placement phase.",
    "voluntary_unpopular_goal":"Weekend willingness is informational/audit-only and does not change SYSTEM weekend water-fill.",
    "voluntary_unpopular_explain":"A resident cannot buy extra Saturdays or Sundays by selecting Prefer to work. SYSTEM allocates weekends by the tightest feasible RAW spread. After publication a bilateral swap may change the balance only after SP final approval.",
    "weekend_help":"ADMIN WATER-FILL: resident weekend-direction selection is disabled for SYSTEM generation. Use Cannot-work only for genuine unavailability.",
    "preferred_help":"Weekday requests are SOFT. Weekend requests are recorded for audit, but SYSTEM cannot use them to give extra Saturdays or Sundays beyond the tightest feasible RAW water-fill.",
    "backup_swap_help":"After publication a backup swap may be proposed, but it is applied only after both residents consent, HARD validation passes, and SP gives final APPROVE; SP may DECLINE.",
})

def tr(k): return TR[lang][k]

def contrast_text(hex_color):
    h=hex_color.lstrip("#"); r,g,b=int(h[0:2],16),int(h[2:4],16),int(h[4:6],16)
    return "#111111" if (0.299*r+0.587*g+0.114*b)>160 else "#FFFFFF"

def badge(initials, include_name=True):
    p=next((x for x in DEFAULT_PEOPLE if x["initials"]==initials),None); c=PERSON_COLORS.get(initials,"#DDD")
    label=initials+(f" — {p['name']}" if include_name and p else "")
    return f'<span style="display:inline-block;background:{c};color:{contrast_text(c)};padding:5px 10px;border-radius:8px;font-weight:700;margin:2px 4px 2px 0;">{html.escape(label)}</span>'


def _person_name(initials):
    p=next((x for x in DEFAULT_PEOPLE if x["initials"]==initials),None)
    return p["name"] if p else initials


def _swap_shift_text(slot):
    if slot is None:
        return "—"
    return (
        f"{slot.day:02d} {WEEKDAYS[lang][slot.weekday]} · "
        f"{slot.department} · {block_label(slot.block)}"
    )


def _render_swap_people_line(person_a, person_b, arrow="↔"):
    st.markdown(
        f'<div style="font-size:1.08rem;display:flex;align-items:center;gap:10px;'
        f'flex-wrap:wrap;margin:4px 0 10px 0;">'
        f'{badge(person_a,include_name=True)}'
        f'<span style="font-size:1.45rem;font-weight:800;color:#666;">{html.escape(arrow)}</span>'
        f'{badge(person_b,include_name=True)}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_shift_tile(title, person, slot, accent=None):
    c=accent or PERSON_COLORS.get(person,"#777777")
    st.markdown(
        f'<div style="border:2px solid {c};border-radius:14px;padding:12px 14px;'
        f'min-height:112px;background:linear-gradient(180deg,{c}18,rgba(255,255,255,0.03));">'
        f'<div style="font-size:.76rem;font-weight:800;letter-spacing:.04em;opacity:.72;'
        f'text-transform:uppercase;margin-bottom:7px;">{html.escape(title)}</div>'
        f'{badge(person,include_name=False)}'
        f'<div style="font-size:1.02rem;font-weight:700;margin-top:8px;">'
        f'{html.escape(_swap_shift_text(slot))}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_swap_request_card(req, idx, total, slot_map, incoming=False):
    a=str(req.get("person_a") or "")
    b=str(req.get("person_b") or "")
    sa=slot_map.get(int(req.get("slot_a") or -1))
    sb=slot_map.get(int(req.get("slot_b") or -1))
    c=PERSON_COLORS.get(a,"#777777")
    title=(
        f"GAUTA UŽKLAUSA {idx}/{total} · DB #{req.get('id')}"
        if incoming and lang=="LT" else
        f"INCOMING REQUEST {idx}/{total} · DB #{req.get('id')}"
        if incoming else
        f"MANO PASIŪLYMAS {idx}/{total} · DB #{req.get('id')}"
        if lang=="LT" else
        f"MY OFFER {idx}/{total} · DB #{req.get('id')}"
    )
    st.markdown(
        f'<div style="border-left:8px solid {c};border-radius:16px;padding:12px 16px;'
        f'background:rgba(127,127,127,.07);margin:8px 0 10px 0;">'
        f'<div style="font-size:.82rem;font-weight:900;letter-spacing:.055em;'
        f'text-transform:uppercase;">{html.escape(title)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    _render_swap_people_line(a,b,"→")
    c1,c2=st.columns(2)
    with c1:
        _render_shift_tile(
            ("SIŪLO" if lang=="LT" else "OFFERS"),
            a,sa,PERSON_COLORS.get(a)
        )
    with c2:
        _render_shift_tile(
            ("PRAŠO" if lang=="LT" else "REQUESTS"),
            b,sb,PERSON_COLORS.get(b)
        )



def _swap_hard_user_explanation(code, details=""):
    """Plain-language explanation for a true ACTUAL swap blocker."""
    lt={
        "ONKO_EVEN_PARITY":(
            "Onko porų taisyklė",
            "Po apsikeitimo bent vieno rezidento Onko skaičius taptų nelyginis. Onko ACTUAL grafike turi likti 0 / 2 / 4 / …"
        ),
        "ONKO_COVERAGE":(
            "Privalomas Onko padengimas",
            "Apsikeitimas sugadintų reikiamą bendrą Onko padengimą."
        ),
        "OVERLAPPING_ASSIGNMENTS":(
            "Persidengiančios pamainos",
            "Po apsikeitimo tam pačiam rezidentui tuo pačiu metu būtų paskirtos dvi persidengiančios pamainos."
        ),
        "MAX_HOURS_PER_DAY":(
            "Maksimali darbo trukmė per dieną",
            "Po apsikeitimo būtų viršyta ACTUAL swapo maksimali 12 val. darbo trukmė per vieną dieną."
        ),
        "MAX_WORKDAYS_7D":(
            "Maksimalus darbo dienų skaičius per 7 dienas",
            "Po apsikeitimo rezidentas dirbtų daugiau nei leidžiamos 6 darbo dienos per slenkantį 7 dienų langą."
        ),
        "MAX_HOURS_7D":(
            "Maksimali darbo trukmė per 7 dienas",
            "Po apsikeitimo būtų viršytas absoliutus darbo valandų limitas per slenkantį 7 dienų laikotarpį (iki 60 val.)."
        ),
        "MIN_DAILY_REST":(
            "Minimalus 11 val. paros poilsis",
            "Po apsikeitimo tarp dviejų darbo dienų liktų mažiau nei 11 val. nepertraukiamo poilsio."
        ),
        "POST_DUTY_REST":(
            "Privalomas poilsis po budėjimo",
            "Apsikeitimas paskirtų darbą dieną, kuri turi likti laisva po ilgo budėjimo."
        ),
        "ABSOLUTE_UNAVAILABILITY":(
            "Absoliutus nebuvimas",
            "Apsikeitimas paskirtų darbą per atostogas ar kitą absoliučiai pateisintą nebuvimą."
        ),
        "BLOCKED_SLOT":(
            "Uždaryta / neegzistuojanti pamaina",
            "Apsikeitimas bandytų užpildyti pamainą, kuri pagal klinikos modelį tuo metu yra uždaryta."
        ),
        "MANDATORY_COVERAGE":(
            "Privalomas klinikos padengimas",
            "Po apsikeitimo liktų neužpildyta privaloma klinikos pamaina."
        ),
        "MANDATORY_BACKUP_AVAILABILITY":(
            "Privalomas dublio padengimas",
            "Po apsikeitimo kritinei pamainai neliktų nė vieno galinčio dirbti ir tuo metu neužimto dublio rezidento."
        ),
        "OTHER_OPERATIONAL_HARD":(
            "Kita privaloma veiklos taisyklė",
            "Šis apsikeitimas pažeistų kitą privalomą saugos, darbo laiko ar klinikos padengimo taisyklę."
        ),
    }
    en={
        "ONKO_EVEN_PARITY":("Even Onko parity","The swap would leave an odd Onko count. ACTUAL Onko must remain 0 / 2 / 4 / …"),
        "ONKO_COVERAGE":("Required Onko coverage","The swap would break required overall Onko coverage."),
        "OVERLAPPING_ASSIGNMENTS":("No overlapping shifts","The swap would give a resident overlapping assignments at the same time."),
        "MAX_HOURS_PER_DAY":("Maximum hours per day","The swap would exceed the ACTUAL 12-hour daily maximum."),
        "MAX_WORKDAYS_7D":("Maximum workdays in 7 days","The swap would exceed 6 working days in a rolling 7-day window."),
        "MAX_HOURS_7D":("Maximum hours in 7 days","The swap would exceed the ACTUAL absolute rolling-7-day limit (up to 60 hours)."),
        "MIN_DAILY_REST":("Minimum 11-hour daily rest","The swap would leave less than 11 uninterrupted hours of rest between workdays."),
        "POST_DUTY_REST":("Mandatory post-duty rest","The swap would assign work on a required post-duty rest day."),
        "ABSOLUTE_UNAVAILABILITY":("Absolute unavailability","The swap would assign work during vacation or another absolute justified absence."),
        "BLOCKED_SLOT":("Closed / blocked shift","The swap would fill a shift that is closed in the clinic model."),
        "MANDATORY_COVERAGE":("Mandatory clinical coverage","The swap would leave a mandatory clinical shift unfilled."),
        "MANDATORY_BACKUP_AVAILABILITY":("Required backup availability","The swap would leave a critical shift without any HARD-available non-overlapping backup resident."),
        "OTHER_OPERATIONAL_HARD":("Other operational HARD rule","The swap would violate another non-relaxable safety, work-time or clinical-coverage rule."),
    }
    table=lt if lang=="LT" else en
    return table.get(str(code),table["OTHER_OPERATIONAL_HARD"])


def _render_swap_hard_block(preview_stats, fallback_reason=""):
    rows=((preview_stats or {}).get("global",{}) or {}).get("swap_hard_block_rows") or []
    if not rows:
        st.error(
            ("Apsikeitimas negalimas: " if lang=="LT" else "Swap cannot be completed: ")
            + str(fallback_reason or "unknown reason")
        )
        return

    pretty=[]
    for r in rows:
        code=str(r.get("code") or "OTHER_OPERATIONAL_HARD")
        title,why=_swap_hard_user_explanation(code,r.get("details",""))
        pretty.append({
            ("Privaloma taisyklė" if lang=="LT" else "HARD rule"):title,
            ("Kodėl negalima" if lang=="LT" else "Why blocked"):why,
            ("Techninė detalė" if lang=="LT" else "Technical detail"):str(r.get("details") or ""),
        })

    first=pretty[0]
    st.error(
        (
            f"APSIKEITIMAS NEGALIMAS — pažeidžiama privaloma taisyklė: {first['Privaloma taisyklė']}"
            if lang=="LT" else
            f"SWAP BLOCKED — HARD rule violated: {first['HARD rule']}"
        )
    )
    st.dataframe(pd.DataFrame(pretty),use_container_width=True,hide_index=True)


def _friday_waterfill_proof(stats):
    pdata=((stats or {}).get("people") or {})
    counts={i:int((d or {}).get("friday_assignments",0) or 0) for i,d in pdata.items()}
    vals=list(counts.values())
    total=int(sum(vals))
    n=len(vals)
    lo=int(total//n) if n else 0
    hi=int((total+n-1)//n) if n else 0
    spread=(max(vals)-min(vals)) if vals else 0
    passed=bool(vals and spread<=1 and all(lo<=v<=hi for v in vals))
    return {"counts":counts,"total":total,"n":n,"floor":lo,"ceil":hi,"spread":spread,"passed":passed}


def _delete_confirm(token, applied=False):
    state_key="_confirm_delete_schedule_action"
    label=("ANULIUOTI" if lang=="LT" else "DELETE / UNDO") if applied else ("IŠTRINTI" if lang=="LT" else "DELETE")
    if st.button(label,key=f"delete_open_{token}",use_container_width=True):
        st.session_state[state_key]=token
    if st.session_state.get(state_key)!=token:
        return False
    st.warning(
        ("Patvirtinkite. Jei veiksmas jau pakeitė faktinį grafiką, sistema bandys saugiai grąžinti ankstesnę būseną. Jei tos vietos vėliau buvo pakeistos dar kartą, anuliavimas bus atmestas, kad nesugadintų naujesnio grafiko."
         if lang=="LT" else
         "Confirm. If this action already changed ACTUAL, the system will safely restore the previous state. If those slots changed again later, DELETE will be refused to protect newer changes.")
    )
    c1,c2=st.columns(2)
    with c1:
        yes=st.button("PATVIRTINTI IŠTRYNIMĄ" if lang=="LT" else "CONFIRM DELETE",type="primary",key=f"delete_yes_{token}",use_container_width=True)
    with c2:
        no=st.button("ATŠAUKTI" if lang=="LT" else "CANCEL",key=f"delete_no_{token}",use_container_width=True)
    if no:
        st.session_state.pop(state_key,None)
        st.rerun()
    if yes:
        st.session_state.pop(state_key,None)
        return True
    return False


def _prepare_swap_action_undo(row,y,m):
    meta=_swap_meta_decode(row.get("reason"))
    kind=str(meta.get("kind") or "")
    phase=str(meta.get("phase") or "")
    applied=bool(kind=="emergency_rescue" or phase=="applied")
    if not applied:
        return None,None

    fresh=refresh_result_payload(db.load_schedule(y,m,"current"),y,m)
    candidate=deepcopy(fresh)
    candidate.assignments=dict(fresh.assignments)
    sa=int(row["slot_a"]); sb=int(row["slot_b"])

    if kind=="emergency_rescue":
        if sa in candidate.assignments:
            raise RuntimeError("Emergency Rescue source slotas nebėra tuščias — po Rescue jis jau buvo pakeistas." if lang=="LT" else "Emergency Rescue source is no longer vacant; it changed after the Rescue.")
        if candidate.assignments.get(sb)!=row.get("person_a"):
            raise RuntimeError("Emergency Rescue target slotas po Rescue jau buvo pakeistas." if lang=="LT" else "Emergency Rescue target changed after the Rescue.")
        candidate.assignments[sa]=row.get("person_a")
        candidate.assignments[sb]=row.get("person_b")
        mode="voluntary_swap_actual"
    else:
        if candidate.assignments.get(sa)!=row.get("person_b") or candidate.assignments.get(sb)!=row.get("person_a"):
            raise RuntimeError("Šio apsikeitimo vietos po pritaikymo jau buvo pakeistos dar kartą — automatinis anuliavimas nebesaugus." if lang=="LT" else "These swap slots changed again after application; automatic UNDO is no longer safe.")
        candidate.assignments[sa]=row.get("person_a")
        candidate.assignments[sb]=row.get("person_b")
        mode="voluntary_swap_actual"

    candidate=revalidate_loaded_result(
        y,m,people_for_stored_result(candidate,y,m),candidate,
        backup_assignments=None,validation_mode=mode,
    )
    desired,backup_errors=plan_backups(y,m,candidate)
    if backup_errors:
        raise RuntimeError(("UNDO negalimas: nepavyksta atkurti privalomo backup plano: " if lang=="LT" else "UNDO blocked: required backup plan cannot be rebuilt: ")+str(backup_errors[0]))
    candidate=revalidate_loaded_result(
        y,m,people_for_stored_result(candidate,y,m),candidate,
        backup_assignments=desired,validation_mode=mode,
    )
    errs=list(((candidate.stats or {}).get("global") or {}).get("errors") or [])
    if errs:
        raise RuntimeError(("Anuliavimas negalimas dėl privalomos taisyklės: " if lang=="LT" else "UNDO blocked by operational HARD: ")+str(errs[0]))
    return candidate,desired


def _delete_swap_row(row,y,m):
    candidate,desired=_prepare_swap_action_undo(row,y,m)
    saved=db.delete_swap_action_v2586(
        int(row["id"]),
        serialize_result(candidate) if candidate is not None else None,
        desired if desired is not None else None,
    )
    if saved.get("undone_actual"):
        try: persist_actual_satisfaction(y,m)
        except Exception: pass
        try: refresh_calendar_subscription_feeds([row.get("person_a"),row.get("person_b")])
        except Exception: pass
    return saved


def month_label(y,m): return f"{MONTHS[lang][m-1]} {y}"
def block_label(b): return {"AM":tr("morning"),"PM":tr("afternoon"),"FULL":tr("full_day"),"NIGHT":tr("night")}.get(b,str(b))
def slot_time_text(sl):
    if sl.block=="AM": return "08:00–14:00"
    if sl.block=="PM": return "14:00–20:00"
    if sl.block=="NIGHT": return "20:00–08:00"
    if sl.block=="FULL": return "08:00–17:00" if is_onko_slot(sl) else "08:00–20:00"
    return block_label(sl.block)


def slot_department_text(y,m,sl,grid=False):
    """Human-facing station label, including the Oct-13 Skopijos room exception."""
    if str(sl.department).startswith("Skopijos"):
        if grid:
            if int(y)==2026 and int(m)==10:
                return "Skopijos · Centras 0153 (10-13 → KP 209)"
            return "Skopijos · Centras 0153"
        if int(y)==2026 and int(m)==10 and int(sl.day)==13:
            return "Skopijos · Konsultacinė poliklinika 209 · žarnų skopijos"
        return "Skopijos · Centras 0153 · skrandžio skopijos"
    return sl.department

def slot_datetime_bounds(y,m,sl,tz):
    d0=date(y,m,sl.day)
    if sl.block=="NIGHT":
        return datetime.combine(d0,time(20),tzinfo=tz), datetime.combine(d0+timedelta(days=1),time(8),tzinfo=tz)
    if sl.block=="AM": return datetime.combine(d0,time(8),tzinfo=tz),datetime.combine(d0,time(14),tzinfo=tz)
    if sl.block=="PM": return datetime.combine(d0,time(14),tzinfo=tz),datetime.combine(d0,time(20),tzinfo=tz)
    endt=time(17) if is_onko_slot(sl) else time(20)
    return datetime.combine(d0,time(8),tzinfo=tz),datetime.combine(d0,endt,tzinfo=tz)
def pretty_day(y,m,d): return f"{d:02d} {WEEKDAYS[lang][date(y,m,d).weekday()]}"

# V2.5.162 resident anti-gaming guardrails. These protect scarce shared weekend
# burden without penalizing legitimate weekday requests (e.g. every Friday off).
def preference_guardrail_violations_v25162(y,m,hard_full,hard_am,hard_pm,soft_full,soft_am,soft_pm,pref_full,pref_am,pref_pm):
    """Block obvious self-service gaming patterns without weakening genuine wishes.

    The resident form is intentionally permissive for ordinary isolated wishes. Only
    patterns that effectively reserve a long run or an entire weekend weekday are
    rejected from self-service. A genuine exception can still be entered by SP with
    an audit reason, or recorded through the appropriate official absence workflow.
    """
    nd=calendar.monthrange(y,m)[1]
    norm=lambda xs:{int(d) for d in xs if 1<=int(d)<=nd}
    hf,ha,hp=norm(hard_full),norm(hard_am),norm(hard_pm)
    sf,sfa,sfp=norm(soft_full),norm(soft_am),norm(soft_pm)
    pr,pra,prp=norm(pref_full),norm(pref_am),norm(pref_pm)
    violations=[]

    # A day is effectively requested fully OFF if both halves are blocked by any
    # combination of resident-HARD and SOFT-free inputs. Four days can be a normal
    # long weekend; five consecutive days is a work-week sized reservation and must
    # go through SP / official absence so it cannot be used to game the generator.
    off_am=hf|sf|ha|sfa
    off_pm=hf|sf|hp|sfp
    effective_full_off=off_am & off_pm
    run=[]
    for d in range(1,nd+2):
        if d<=nd and d in effective_full_off:
            run.append(d)
        else:
            if len(run)>=5:
                violations.append(
                    f"Negalima savarankiškai rezervuoti {len(run)} pilnų dienų iš eilės ({run[0]}–{run[-1]} d.). "
                    "Jei tai realus neatvykimas / išvykimas / atostogos, naudokite atitinkamą funkciją arba kreipkitės į Seniūnę."
                )
            run=[]

    # A 12 h weekend duty overlaps either half of the day. Blocking every Saturday
    # or every Sunday would transfer the shared duty burden to colleagues, so that
    # pattern requires SP review rather than self-service acceptance.
    weekend_blocked={d for d in range(1,nd+1) if date(y,m,d).weekday()>=5 and (d in off_am or d in off_pm)}
    sats=[d for d in range(1,nd+1) if date(y,m,d).weekday()==5]
    suns=[d for d in range(1,nd+1) if date(y,m,d).weekday()==6]
    if sats and set(sats).issubset(weekend_blocked):
        violations.append("Negalima savarankiškai užblokuoti visų mėnesio šeštadienių. Jei tam yra reali priežastis, parašykite Seniūnei.")
    if suns and set(suns).issubset(weekend_blocked):
        violations.append("Negalima savarankiškai užblokuoti visų mėnesio sekmadienių. Jei tam yra reali priežastis, parašykite Seniūnei.")

    # Residents get at most one weekend duty preference. Multiple weekend work
    # requests would let a resident steer a scarce shared-duty resource.
    weekend_work={d for d in (pr|pra|prp) if date(y,m,d).weekday()>=5}
    if len(weekend_work)>1:
        violations.append("Savaitgaliui galima pasirinkti tik vieną „Pageidauju dirbti“ datą per mėnesį.")
    return violations
def safe_filename(s): return "".join(ch for ch in unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode() if ch.isalnum() or ch in "_-")
def ics_escape(s): return str(s).replace("\\","\\\\").replace(";","\\;").replace(",","\\,").replace("\n","\\n")

def deadline_day():
    return int(rule_value("deadline_day"))


def deadline_for(y,m):
    dd=deadline_day()
    if m==1: return date(y-1,12,dd)
    return date(y,m-1,dd)

def preference_open_for(y,m):
    """Resident input opens at 00:00 on day 1 of the preceding month."""
    if m==1:
        oy,om=y-1,12
    else:
        oy,om=y,m-1
    return datetime(oy,om,1,0,0,tzinfo=ZoneInfo("Europe/Vilnius"))

def preference_cutoff_for(y,m):
    """Exact cutoff: immediately after the configured last full submission day."""
    last_full_day=deadline_for(y,m)
    return datetime.combine(last_full_day+timedelta(days=1),time(0,0),tzinfo=ZoneInfo("Europe/Vilnius"))

def swap_window_close_for(y,m):
    """Automatic resident swap/dublis self-service close: previous month day 16 00:00 Lithuania time."""
    if m==1:
        cy,cm=y-1,12
    else:
        cy,cm=y,m-1
    return datetime(cy,cm,16,0,0,tzinfo=ZoneInfo("Europe/Vilnius"))

def weekend_backup_fcfs_window(y,m):
    # V2.5.146: dubliai are an operational post-publication layer.
    # Self-selection becomes available only after a preliminary SYSTEM/ACTUAL
    # schedule exists and remains open through the target month.
    if m==12:
        close_at=datetime(y+1,1,1,0,0,tzinfo=ZoneInfo("Europe/Vilnius"))
    else:
        close_at=datetime(y,m+1,1,0,0,tzinfo=ZoneInfo("Europe/Vilnius"))
    return None, close_at

def _fcfs_weekend_slot_pool(y,m):
    """Selectable weekend dublis positions for the active cohort model."""
    return list(weekend_fcfs_backup_slots(y,m))

def render_fcfs_weekend_backup_selector(y,m,initials):
    if not weekend_fcfs_backup_mode(y,m):
        return
    _open_at,close_at=weekend_backup_fcfs_window(y,m)
    now_lt=datetime.now(ZoneInfo("Europe/Vilnius"))
    _published=bool(db.get_schedule_state(y,m).get("has_published")) and bool(db.load_schedule(y,m,"current"))
    claims=db.list_backup_claims(y,m)
    by_slot={int(r.get("covered_slot")):r for r in claims}
    mine=next((r for r in claims if str(r.get("initials"))==str(initials)),None)
    slots=_fcfs_weekend_slot_pool(y,m); smap={s.idx:s for s in slots}

    _pool_n=len(slots)
    _is12=cohort_october_model(y,m)
    st.markdown("### DUBLIS — savaitgalio 12 h" if (lang=="LT" and _is12) else "### DUBLIS — savaitgalio 6 h" if lang=="LT" else "### BACKUP — weekend 12h" if _is12 else "### BACKUP — weekend 6h")
    st.caption(
        ((f"{_pool_n} savaitgalio dienų · po 1 dublį kiekvienai 12 h budėjimo dienai. Dubliai atsirakina tik paskelbus grafiką ir nekeičia pageidavimų reitingo." if _is12 else f"{_pool_n} vietų. Dubliai atsirakina tik paskelbus grafiką ir nekeičia pageidavimų reitingo.")
         if lang=="LT" else
         (f"{_pool_n} weekend-day backup positions. Selection unlocks only after publication and does not affect preference ranking."))
    )
    c1,c2=st.columns(2)
    c1.metric("Užpildyta" if lang=="LT" else "Filled",f"{len(claims)}/{_pool_n}")
    if mine:
        ms=smap.get(int(mine.get("covered_slot") or 0))
        c2.metric("Mano dublis" if lang=="LT" else "My backup",
                  (f"{ms.day:02d} · {block_label(ms.block)}" if ms else str(mine.get("covered_slot"))))
    else:
        c2.metric("Mano dublis" if lang=="LT" else "My backup","—")

    if not _published:
        st.info("Dubliai atsirakins tik paskelbus preliminarų grafiką." if lang=="LT" else "Backups unlock only after the preliminary schedule is published.")
        return
    if now_lt >= close_at:
        st.caption((f"Šio mėnesio dublių savitarna uždaryta {close_at.strftime('%Y-%m-%d %H:%M')}." if lang=="LT" else f"This month's backup self-service closed {close_at.strftime('%Y-%m-%d %H:%M')}."))
        return
    if len(claims)>=16 and mine is None:
        st.warning("Visi 16 dublių jau pasirinkti. Kreipkis į seniūnę." if lang=="LT" else "All 16 FCFS backup places are already taken. Contact SP.")
        return

    selectable=[]
    for sl in slots:
        owner=by_slot.get(sl.idx)
        if owner is None or str(owner.get("initials"))==str(initials):
            selectable.append(sl.idx)
    options=[None]+selectable
    current_sid=int(mine.get("covered_slot")) if mine else None
    idx=options.index(current_sid) if current_sid in options else 0
    def fmt(sid):
        if sid is None: return "— pasirink —" if lang=="LT" else "— choose —"
        sl=smap[int(sid)]
        return f"{sl.day:02d} {WEEKDAYS[lang][sl.weekday]} · {block_label(sl.block)}"
    choice=st.selectbox(
        "Pasirink 1 dublį" if lang=="LT" else "Choose 1 backup",
        options,index=idx,format_func=fmt,key=f"fcfs_backup_choice_{y}_{m}_{initials}"
    )
    b1,b2=st.columns(2)
    with b1:
        if st.button("PATVIRTINTI DUBLĮ" if lang=="LT" else "CONFIRM BACKUP",type="primary",use_container_width=True,key=f"fcfs_backup_save_{y}_{m}_{initials}",disabled=(choice is None)):
            sl=smap[int(choice)]
            try:
                db.claim_weekend_backup_fcfs_v25118(y,m,sl.idx,sl.day,sl.block)
                _cp=db.load_schedule(y,m,"current")
                if _cp:
                    try:
                        _rr=refresh_result_payload(_cp,y,m,use_actual_backups=False)
                        sync_backup_plan(y,m,_rr)
                    except Exception:
                        pass
                st.success("Dublis išsaugotas." if lang=="LT" else "Backup saved.")
                st.rerun()
            except Exception as e:
                msg=str(e)
                if "BACKUP_SLOT_ALREADY_CLAIMED" in msg:
                    st.error("Šią dublio vietą ką tik pasirinko kitas žmogus. Pasirink kitą." if lang=="LT" else "Someone just took this slot. Choose another.")
                elif "BACKUP_FCFS_FULL" in msg:
                    st.error("Visi 16 dubliai jau užpildyti." if lang=="LT" else "All 16 backups are already filled.")
                elif "weekend_backup_claims_source_check" in msg or "23514" in msg:
                    st.error("Dublių duomenų bazės schema neatnaujinta. Įdiek V2.5.122 migraciją ir bandyk dar kartą." if lang=="LT" else "Backup database schema is out of date. Apply the V2.5.122 migration and try again.")
                else:
                    st.error(msg)
    with b2:
        if mine and st.button("ATLAISVINTI / KEISTI" if lang=="LT" else "RELEASE / CHANGE",use_container_width=True,key=f"fcfs_backup_release_{y}_{m}_{initials}"):
            try:
                db.release_weekend_backup_fcfs_v25118(y,m)
                _cp=db.load_schedule(y,m,"current")
                if _cp:
                    try:
                        _rr=refresh_result_payload(_cp,y,m,use_actual_backups=False)
                        sync_backup_plan(y,m,_rr)
                    except Exception:
                        pass
                st.rerun()
            except Exception as e:
                st.error(str(e))

def _sp_private_scope_label(pref: dict, y: int, m: int) -> str:
    scope=str(pref.get("scope_type") or "month")
    if scope=="month":
        return "Visas mėnuo" if lang=="LT" else "Whole month"
    raw=str(pref.get("scope_start_date") or "")[:10]
    try:
        d0=date.fromisoformat(raw)
    except Exception:
        return raw or "—"
    if scope=="day":
        return pretty_day(y,m,d0.day) if d0.year==y and d0.month==m else d0.isoformat()
    days=_scheduler_engine.private_pair_scope_days(pref,y,m)
    if not days: return d0.isoformat()
    return (f"Savaitė {min(days):02d}–{max(days):02d}" if lang=="LT" else f"Week {min(days):02d}–{max(days):02d}")


def _sp_private_workplace_label(value: str) -> str:
    return ("Bet kur" if lang=="LT" else "Anywhere") if str(value or "ANY")=="ANY" else str(value)


def _sp_private_block_label(value: str) -> str:
    v=str(value or "ANY").upper()
    if v=="ANY": return "Bet kuris laikas" if lang=="LT" else "Any time"
    return block_label(v)


def _get_sp_dream_team_config_v25130() -> dict:
    fn=getattr(db,"get_sp_dream_team_config_v25125",None)
    if callable(fn):
        try:
            return dict(fn() or {})
        except Exception:
            pass
    try:
        resp=(db.client().table("sp_dream_team_config_v25125").select("*").eq("id",1).limit(1).execute())
        rows=getattr(resp,"data",None) or []
        return dict(rows[0]) if rows else {}
    except Exception:
        return {}


def _get_sp_dream_team_month_v25130(y: int, m: int) -> dict:
    fn=getattr(db,"get_sp_dream_team_month_v25125",None)
    if callable(fn):
        try:
            return dict(fn(y,m) or {})
        except Exception:
            pass
    try:
        resp=(db.client().table("sp_dream_team_monthly_v25125").select("*")
              .eq("year",int(y)).eq("month",int(m)).limit(1).execute())
        rows=getattr(resp,"data",None) or []
        return dict(rows[0]) if rows else {}
    except Exception:
        return {}


def _save_sp_dream_team_v25130(y: int, m: int, centro_members, adc_members, centro_target: int, adc_target: int) -> None:
    save_cfg=getattr(db,"save_sp_dream_team_config_v25125",None)
    save_mon=getattr(db,"save_sp_dream_team_month_v25125",None)
    if callable(save_cfg) and callable(save_mon):
        save_cfg(centro_members,adc_members)
        save_mon(y,m,centro_target,adc_target)
        return
    try:
        db.client().table("sp_dream_team_config_v25125").upsert({
            "id":1,"centro_members":list(centro_members or []),"adc_members":list(adc_members or [])
        },on_conflict="id").execute()
        db.client().table("sp_dream_team_monthly_v25125").upsert({
            "year":int(y),"month":int(m),"centro_target":int(centro_target),"adc_target":int(adc_target)
        },on_conflict="year,month").execute()
    except Exception as exc:
        raise RuntimeError("Komandos nustatymams reikia paleisti V2.5.125/V2.5.128 duomenų bazės migraciją.") from exc


def render_sp_dream_team_settings_v25125(y: int, m: int):
    """Dream Team block visible and editable to SP and ŠR only."""
    if active_user not in (SENIOR_INITIALS,RESEARCHER_INITIALS):
        return
    can_edit=(active_user in (SENIOR_INITIALS,RESEARCHER_INITIALS))
    try:
        cfg=_get_sp_dream_team_config_v25130() or {}
        mon=_get_sp_dream_team_month_v25130(y,m) or {}
    except Exception as exc:
        st.warning(f"Komandos nustatymai dar neparuošti duomenų bazėje: {exc}")
        return
    state=db.get_schedule_state(y,m); lifecycle=db.get_schedule_lifecycle(y,m)
    frozen=bool(state.get("has_published")) or str(lifecycle.get("state") or "") in ("working","swap_open","swap_closed","final")
    all_ini=[p["initials"] for p in DEFAULT_PEOPLE]
    centro_default=[x for x in (cfg.get("centro_members") or ["SP","ŠR","GE"]) if x in all_ini]
    adc_default=[x for x in (cfg.get("adc_members") or ["SP","ŠR"]) if x in all_ini]
    st.markdown("### Dream Team")
    c1,c2=st.columns(2)
    with c1:
        st.markdown("#### CENTRO RO")
        centro=st.multiselect("Nariai (2–4)",all_ini,default=centro_default,key=f"dream_centro_members_{y}_{m}",disabled=(frozen or not can_edit))
        ct=int(st.number_input("Kiek kartų šį mėnesį norėtum šią komandą turėti kartu?",0,6,int(mon.get("centro_target",4) or 0),1,key=f"dream_centro_target_{y}_{m}",disabled=(frozen or not can_edit)))
    with c2:
        st.markdown("#### ADC 144/145")
        adc=st.multiselect("Nariai (tiksliai 2)",all_ini,default=adc_default,key=f"dream_adc_members_{y}_{m}",disabled=(frozen or not can_edit))
        at=int(st.number_input("Kiek kartų šį mėnesį norėtum šią porą turėti kartu?",0,12,int(mon.get("adc_target",0) or 0),1,key=f"dream_adc_target_{y}_{m}",disabled=(frozen or not can_edit)))
    if not can_edit:
        return
    if frozen:
        st.info("Šio mėnesio pradinis grafikas jau užfiksuotas, todėl komandos nustatymai šiam mėnesiui neberedaguojami.")
        return
    if st.button("IŠSAUGOTI",type="primary",use_container_width=True,key=f"save_dream_team_{y}_{m}"):
        if not (2<=len(centro)<=4):
            st.error("CENTRO RO komandą turi sudaryti 2–4 žmonės.")
        elif len(adc)!=2:
            st.error("ADC 144/145 komandą turi sudaryti tiksliai 2 žmonės.")
        else:
            try:
                _save_sp_dream_team_v25130(y,m,centro,adc,ct,at)
                st.success("Išsaugota.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def _operator_private_group_rows_v25134(rows) -> list[dict]:
    """Sujungia vieno pageidavimo žmones į vieną UI / audito grupę."""
    buckets={}
    order=[]
    for raw in (rows or []):
        row=dict(raw)
        gid=str(row.get("group_id") or f"legacy-{row.get('id')}")
        if gid not in buckets:
            buckets[gid]={"group_id":gid,"rows":[],"pref":row,"targets":[]}
            order.append(gid)
        buckets[gid]["rows"].append(row)
        target=str(row.get("target_initials") or "")
        if target and target not in buckets[gid]["targets"]:
            buckets[gid]["targets"].append(target)
    return [buckets[x] for x in order]


def _list_operator_private_pair_preferences_v25130(y: int, m: int, owner: str | None = None) -> list[dict]:
    """Suderinamumo skaitytuvas: V2.5.134 grupės + senesnės vieno žmogaus eilutės."""
    fn=getattr(db,"list_operator_private_pair_preferences_v25128",None)
    if callable(fn):
        try:
            return [dict(x) for x in (fn(y,m,owner) or [])]
        except Exception:
            pass
    # Pirmiausia bandome V2.5.134 schemą su group_id; jei migracija dar nepaleista,
    # skaitome seną schemą be group_id, kad pats Pageidavimų langas nenulūžtų.
    for select_cols in (
        "id,group_id,owner_initials,year,month,preference_type,target_initials,scope_type,scope_start_date,block,workplace,created_at,updated_at",
        "id,owner_initials,year,month,preference_type,target_initials,scope_type,scope_start_date,block,workplace,created_at,updated_at",
    ):
        try:
            q=(db.client().table("operator_private_pair_preferences_v25128")
               .select(select_cols).eq("year",int(y)).eq("month",int(m)))
            if owner:
                q=q.eq("owner_initials",str(owner))
            resp=q.order("created_at").execute()
            return [dict(x) for x in (getattr(resp,"data",None) or [])]
        except Exception:
            continue
    if str(owner or "")=="SP":
        legacy=getattr(db,"list_sp_private_pair_preferences_v25123",None)
        if callable(legacy):
            try:
                return [dict(x,owner_initials="SP") for x in (legacy(y,m) or [])]
            except Exception:
                pass
    return []


def _create_operator_private_group_preference_v25134(y: int, m: int, owner: str, preference_type: str, target_initials, scope_type: str, scope_start_date, block: str, workplace: str) -> list[dict]:
    targets=[str(x) for x in (target_initials or []) if str(x) and str(x)!=str(owner)]
    targets=list(dict.fromkeys(targets))
    if not targets:
        raise ValueError("Pasirink bent vieną žmogų.")
    fn=getattr(db,"create_operator_private_group_preference_v25134",None)
    if callable(fn):
        return [dict(x) for x in (fn(y,m,preference_type,targets,scope_type,scope_start_date,block,workplace) or [])]
    # V2.5.134 grupių semantikai reikalingas group_id ir ADC 144/145 jungtinės zonos
    # apribojimas, todėl tyčia neimituojame grupės senoje DB schemoje.
    raise RuntimeError("Paleisk SUPABASE_MIGRATION_V2_5_134_GROUPED_PEOPLE_WISHES.sql ir perkrauk programą.")


def _delete_operator_private_group_preference_v25134(group: dict, owner: str) -> bool:
    gid=str(group.get("group_id") or "")
    if gid and not gid.startswith("legacy-"):
        fn=getattr(db,"delete_operator_private_group_preference_v25134",None)
        if callable(fn):
            return bool(fn(gid))
    # Senoms vieno žmogaus eilutėms paliekame saugų ištrynimą po vieną.
    ok=True
    for row in (group.get("rows") or []):
        pref_id=int(row.get("id"))
        fn=getattr(db,"delete_operator_private_pair_preference_v25128",None)
        if callable(fn):
            ok=bool(fn(pref_id)) and ok
        else:
            try:
                db.client().table("operator_private_pair_preferences_v25128").delete().eq("id",pref_id).eq("owner_initials",str(owner)).execute()
            except Exception:
                ok=False
    return ok


def operator_private_pair_preference_summary(owner_initials: str, y: int, m: int, result: SolveResult, prefs=None) -> dict:
    """SP/ŠR grupinių pageidavimų auditas; viena žmonių grupė = vienas pageidavimas."""
    owner=str(owner_initials or "")
    raw=[dict(x) for x in (prefs if prefs is not None else _list_operator_private_pair_preferences_v25130(y,m,owner))]
    groups=_operator_private_group_rows_v25134(raw)
    if not groups or result is None:
        return {"total":len(groups),"honored":0,"missed":len(groups),"rate":None,"rows":[]}
    slots=make_slots(y,m)
    assignments=dict(getattr(result,"assignments",{}) or {})
    by_person={}
    for sl in slots:
        who=assignments.get(sl.idx)
        if who:
            by_person.setdefault(str(who),[]).append(sl)

    def active_in(sl: Slot, d: int, block: str) -> bool:
        return int(sl.day)==int(d) and blocks_overlap(str(sl.block),str(block))

    def in_zone(sl: Slot, workplace: str) -> bool:
        cat=rotation_category(sl)
        if workplace=="ADC 144/145":
            return cat in ("ADC 144","ADC 145")
        return cat==workplace

    rows=[]; honored=0
    for group in groups:
        pref=dict(group["pref"])
        targets=list(group["targets"])
        ptype=str(pref.get("preference_type") or "").lower()
        workplace=_scheduler_engine.private_pair_workplace(pref)
        days=_scheduler_engine.private_pair_scope_days(pref,y,m)
        blocks=_scheduler_engine.private_pair_scope_blocks(pref)
        matches=[]
        for d in days:
            for b in blocks:
                own_here=[sl for sl in by_person.get(owner,[]) if active_in(sl,d,b) and in_zone(sl,workplace)]
                if not own_here:
                    continue
                target_here=[]
                for target in targets:
                    target_here.append(any(active_in(sl,d,b) and in_zone(sl,workplace) for sl in by_person.get(target,[])))
                if ptype=="together":
                    if targets and all(target_here):
                        matches.append((d,b))
                else:
                    if any(target_here):
                        matches.append((d,b))
        ok=(len(matches)>0) if ptype=="together" else (len(matches)==0)
        honored+=int(ok)
        match_txt="; ".join(f"{d:02d} {block_label(b)}" for d,b in matches[:4])
        if len(matches)>4: match_txt+="; …"
        rows.append({
            "Tipas":"Dirbti su" if ptype=="together" else "Dirbti be",
            "Žmonės":", ".join(targets) or "—",
            "Laikotarpis":_sp_private_scope_label(pref,y,m),
            "Laikas":_sp_private_block_label(pref.get("block")),
            "Vieta":_sp_private_workplace_label(pref.get("workplace")),
            "Rezultatas":"Įvykdyta" if ok else "Neįvykdyta",
            "Rasta kartu":match_txt or "—",
        })
    total=len(groups)
    return {"total":total,"honored":honored,"missed":total-honored,"rate":round(100.0*honored/total,1) if total else None,"rows":rows}


def render_operator_private_pair_preferences(y: int, m: int, owner_initials: str):
    """SP/ŠR grupiniai „Dirbti su / Dirbti be“ pageidavimai tiesiai Pageidavimuose."""
    owner=str(owner_initials or "")
    if active_user not in (SENIOR_INITIALS,RESEARCHER_INITIALS) or owner!=active_user:
        return
    raw=_list_operator_private_pair_preferences_v25130(y,m,owner)
    groups=_operator_private_group_rows_v25134(raw)
    state=db.get_schedule_state(y,m)
    lifecycle=db.get_schedule_lifecycle(y,m)
    frozen=bool(state.get("has_published")) or str(lifecycle.get("state") or "") in ("working","swap_open","swap_closed","final")

    name_map={p["initials"]:p["name"] for p in DEFAULT_PEOPLE}
    for group in groups:
        pref=dict(group["pref"]); targets=list(group["targets"])
        together=str(pref.get("preference_type"))=="together"
        border="#22c55e" if together else "#ef4444"
        bg="rgba(34,197,94,.07)" if together else "rgba(239,68,68,.07)"
        title="Dirbti su" if together else "Dirbti be"
        people_txt=", ".join(f"{ini} — {name_map.get(ini,ini)}" for ini in targets)
        st.markdown(
            f'<div style="border-left:4px solid {border};border-top:1px solid {border}33;border-right:1px solid {border}33;border-bottom:1px solid {border}33;'
            f'background:{bg};border-radius:10px;padding:9px 12px;margin:7px 0;">'
            f'<b>{html.escape(title)}</b> &nbsp; {html.escape(people_txt)}<br>'
            f'<span style="opacity:.72">{html.escape(_sp_private_scope_label(pref,y,m))} · {html.escape(_sp_private_block_label(pref.get("block")))} · {html.escape(_sp_private_workplace_label(pref.get("workplace")))}</span>'
            f'</div>',unsafe_allow_html=True
        )
        if not frozen and st.button("Pašalinti",key=f"op_group_del_{owner}_{group['group_id']}"):
            try:
                _delete_operator_private_group_preference_v25134(group,owner)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    if frozen:
        st.caption("Šio mėnesio nustatymai jau užfiksuoti.")
        return

    all_targets=[p["initials"] for p in DEFAULT_PEOPLE if p["initials"]!=owner]
    c1,c2=st.columns(2)
    with c1:
        ptype_label=st.radio("",["Dirbti su","Dirbti be"],horizontal=True,label_visibility="collapsed",key=f"op_group_type_{owner}_{y}_{m}")
        ptype="together" if ptype_label=="Dirbti su" else "apart"
    with c2:
        workplace=st.selectbox("Vieta",["CENTRO RO","ADC 144/145"],key=f"op_group_wp_{owner}_{y}_{m}")

    max_people=(3 if workplace=="CENTRO RO" else 1) if ptype=="together" else None
    selected=st.multiselect(
        "Žmonės",all_targets,format_func=lambda i:f"{i} — {name_map.get(i,i)}",
        max_selections=max_people,key=f"op_group_targets_{owner}_{y}_{m}_{ptype}_{workplace}"
    )
    c3,c4=st.columns(2)
    with c3:
        scope_label=st.selectbox("Laikotarpis",["Visas mėnuo","Visa savaitė","Viena diena"],key=f"op_group_scope_{owner}_{y}_{m}")
        scope={"Visas mėnuo":"month","Visa savaitė":"week","Viena diena":"day"}[scope_label]
    with c4:
        block_label_ui=st.selectbox("Laikas",["Bet kuris laikas","Rytas","Popietė"],key=f"op_group_block_{owner}_{y}_{m}")
        block={"Bet kuris laikas":"ANY","Rytas":"AM","Popietė":"PM"}[block_label_ui]

    scope_date=None
    if scope=="week":
        seen=[]; opts=[]
        for d in range(1,calendar.monthrange(y,m)[1]+1):
            dd=date(y,m,d); monday=dd-timedelta(days=dd.weekday())
            if monday not in seen:
                seen.append(monday); opts.append(dd)
        scope_date=st.selectbox("Savaitė",opts,format_func=lambda dd:_sp_private_scope_label({"scope_type":"week","scope_start_date":dd.isoformat()},y,m),key=f"op_group_week_{owner}_{y}_{m}")
    elif scope=="day":
        d=st.selectbox("Diena",list(range(1,calendar.monthrange(y,m)[1]+1)),format_func=lambda x:pretty_day(y,m,x),key=f"op_group_day_{owner}_{y}_{m}")
        scope_date=date(y,m,int(d))

    if st.button("PRIDĖTI PAGEIDAVIMĄ",type="primary",use_container_width=True,key=f"op_group_add_{owner}_{y}_{m}"):
        try:
            if not selected:
                raise ValueError("Pasirink bent vieną žmogų.")
            _create_operator_private_group_preference_v25134(
                y,m,owner,ptype,selected,scope,scope_date.isoformat() if scope_date else None,block,workplace
            )
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def render_operator_private_pair_stats(y: int, m: int, owner_initials: str, result: SolveResult | None):
    owner=str(owner_initials or "")
    if active_user not in (SENIOR_INITIALS,RESEARCHER_INITIALS) or owner!=active_user:
        return
    prefs=_list_operator_private_pair_preferences_v25130(y,m,owner)
    if not prefs:
        return
    sm=operator_private_pair_preference_summary(owner,y,m,result,prefs) if result is not None else None
    with st.expander("Rezultatas",expanded=False):
        if sm is None:
            st.caption("Grafikas dar nesugeneruotas.")
            return
        a,b,c,d=st.columns(4)
        a.metric("Pateikta",sm["total"]); b.metric("Įvykdyta",sm["honored"]); c.metric("Neįvykdyta",sm["missed"])
        d.metric("Įvykdymas",("—" if sm["rate"] is None else f"{sm['rate']}%"))
        if sm["rows"]:
            st.dataframe(pd.DataFrame(sm["rows"]),use_container_width=True,hide_index=True)

def deadline_message(y,m):
    dl=deadline_for(y,m); today=date.today(); diff=(dl-today).days
    if diff>0: msg=tr("deadline_future").format(n=diff)
    elif diff==0: msg=tr("deadline_today")
    else: msg=tr("deadline_passed").format(n=abs(diff))
    return dl,msg,diff

def ensure_zero_preference_submissions_if_due(y,m):
    """Operator-side automatic completion of missing preference forms after cutoff.

    Missing residents become submitted with exactly zero monthly requests. This never
    creates HARD/SOFT wishes and is transparent via submission_source=deadline_zero.
    """
    cutoff=preference_cutoff_for(y,m)
    now_lt=datetime.now(ZoneInfo("Europe/Vilnius"))
    if now_lt < cutoff:
        return {"ok":True,"due":False,"count":0,"initials":[]}
    try:
        return db.auto_submit_zero_preferences_v2594(y,m,cutoff.isoformat())
    except Exception as e:
        # Do not break the whole app if a transient DB call fails; senior dashboard
        # will still show any genuinely missing rows and generation stays inspectable.
        return {"ok":False,"due":True,"count":0,"initials":[],"error":str(e)}

_SMTP_SECRET_KEYS={
    "SCHEDULER_SMTP_HOST":"host",
    "SCHEDULER_SMTP_PORT":"port",
    "SCHEDULER_SMTP_USER":"user",
    "SCHEDULER_SMTP_PASSWORD":"password",
    "SCHEDULER_SMTP_USE_TLS":"use_tls",
    "SCHEDULER_SMTP_USE_SSL":"use_ssl",
    "SCHEDULER_EMAIL_FROM":"from_email",
    "SCHEDULER_SMTP_PROVIDER":"provider",
}

def config_value(name, default=""):
    """Read deployment configuration from root Streamlit secrets, nested [smtp], or environment.

    V2.5.93 accepts both the historical SCHEDULER_* secret names and a simpler
    nested [smtp] block without ever exposing the password in the UI.
    """
    try:
        if name in st.secrets:
            return str(st.secrets[name])
        key=_SMTP_SECRET_KEYS.get(name)
        if key and "smtp" in st.secrets:
            block=st.secrets["smtp"]
            if key in block:
                return str(block[key])
    except Exception:
        pass
    return os.environ.get(name, default)

def get_supabase_client():
    if "supabase_client" not in st.session_state:
        url=config_value("SUPABASE_URL",DEFAULT_SUPABASE_URL)
        key=config_value("SUPABASE_PUBLISHABLE_KEY",DEFAULT_SUPABASE_PUBLISHABLE_KEY)
        st.session_state["supabase_client"]=create_client(url,key)
    return st.session_state["supabase_client"]


# V2.5.160 — Streamlit session state is tied to a WebSocket and is lost on a
# browser reload. Keep the Supabase session in Secure/SameSite browser cookies
# and restore it into a fresh supabase-py client on the next Streamlit session.
_AUTH_COOKIE_ACCESS="rapa_sb_access_v1"
_AUTH_COOKIE_REFRESH="rapa_sb_refresh_v1"
_AUTH_COOKIE_MAX_AGE=60*60*24*30


def _auth_cookie_value(name: str) -> str:
    try:
        raw=st.context.cookies.get(name,"")
    except Exception:
        return ""
    try:
        return urllib.parse.unquote(str(raw or ""))
    except Exception:
        return str(raw or "")


def _auth_session_tokens(sb):
    try:
        session=sb.auth.get_session()
    except Exception:
        return "",""
    session=getattr(session,"session",session)
    access=str(getattr(session,"access_token","") or "")
    refresh=str(getattr(session,"refresh_token","") or "")
    return access,refresh


def _render_auth_cookie_script(*, access: str="", refresh: str="", clear: bool=False):
    """Write/delete persistent auth cookies in the browser without URL tokens."""
    if clear:
        payload=f'''<script>(()=>{{
          const expire=(doc,name)=>{{doc.cookie=name+'=; Path=/; Max-Age=0; SameSite=Lax; Secure';}};
          const run=(doc)=>{{expire(doc,{json.dumps(_AUTH_COOKIE_ACCESS)});expire(doc,{json.dumps(_AUTH_COOKIE_REFRESH)});}};
          try{{run(window.parent.document);}}catch(e){{try{{run(document);}}catch(_){{}}}}
        }})();</script>'''
        components.html(payload,height=0,scrolling=False)
        st.session_state.pop("_auth_cookie_fingerprint",None)
        return
    if not access or not refresh:
        return
    fp=hashlib.sha256((access+"\0"+refresh).encode()).hexdigest()
    if st.session_state.get("_auth_cookie_fingerprint")==fp:
        return
    payload=f'''<script>(()=>{{
      const maxAge={int(_AUTH_COOKIE_MAX_AGE)};
      const put=(doc,name,value)=>{{doc.cookie=name+'='+encodeURIComponent(value)+'; Path=/; Max-Age='+maxAge+'; SameSite=Lax; Secure';}};
      const run=(doc)=>{{put(doc,{json.dumps(_AUTH_COOKIE_ACCESS)},{json.dumps(access)});put(doc,{json.dumps(_AUTH_COOKIE_REFRESH)},{json.dumps(refresh)});}};
      try{{run(window.parent.document);}}catch(e){{try{{run(document);}}catch(_){{}}}}
    }})();</script>'''
    components.html(payload,height=0,scrolling=False)
    st.session_state["_auth_cookie_fingerprint"]=fp


def _restore_persistent_auth_session(sb) -> bool:
    """Restore a Supabase session after browser reload from RAPA cookies."""
    if st.session_state.get("_auth_cookie_restore_attempted"):
        return bool(st.session_state.get("_auth_cookie_restore_ok"))
    st.session_state["_auth_cookie_restore_attempted"]=True
    access=_auth_cookie_value(_AUTH_COOKIE_ACCESS)
    refresh=_auth_cookie_value(_AUTH_COOKIE_REFRESH)
    if not access or not refresh:
        st.session_state["_auth_cookie_restore_ok"]=False
        return False
    try:
        sb.auth.set_session(access,refresh)
        # set_session refreshes automatically when necessary. Persist the
        # rotated pair so the next reload does not reuse an obsolete token.
        new_access,new_refresh=_auth_session_tokens(sb)
        if new_access and new_refresh:
            _render_auth_cookie_script(access=new_access,refresh=new_refresh)
        st.session_state["_auth_cookie_restore_ok"]=True
        return True
    except Exception:
        st.session_state["_auth_cookie_restore_ok"]=False
        st.session_state["_auth_cookie_clear_needed"]=True
        return False


def _sync_persistent_auth_session(sb):
    access,refresh=_auth_session_tokens(sb)
    if access and refresh:
        _render_auth_cookie_script(access=access,refresh=refresh)


def authenticated_user(sb):
    try:
        r=sb.auth.get_user()
        return getattr(r,"user",None)
    except Exception:
        return None


def _auth_uid(user):
    return str(getattr(user,"id","") or "").strip()


def clear_cross_account_session_state(*, keep_client=True):
    """Remove user-specific Streamlit state on logout/account switch.

    The Supabase client may be kept so its authenticated session survives the
    rerun. Everything else is rebuilt for the exact auth.uid().
    """
    keep={"supabase_client"} if keep_client else set()
    # Language is UI-only and carries no resident data.
    keep.add("language")
    for key in list(st.session_state.keys()):
        if key not in keep:
            st.session_state.pop(key,None)


def enforce_auth_session_identity(user):
    """Fail closed if Streamlit state belongs to another authenticated account."""
    uid=_auth_uid(user)
    if not uid:
        return
    previous=str(st.session_state.get("_identity_auth_uid") or "")
    if previous and previous!=uid:
        clear_cross_account_session_state(keep_client=True)
    st.session_state["_identity_auth_uid"]=uid


def _password_recovery_redirect_url():
    """Return the current clean public RAPA URL for password recovery.

    Prefer the explicit deployment secret, but do not depend on it: on modern
    Streamlit use st.context.url, and on older supported builds reconstruct the
    public URL from forwarded headers. This prevents recovery emails from
    falling back to a stale Supabase Site URL when the app URL changes.
    """
    public=config_value("SCHEDULER_PUBLIC_URL","").strip()
    if not public:
        try:
            public=str(getattr(st.context,"url","") or "").strip()
        except Exception:
            public=""
    if not public:
        try:
            headers=st.context.headers
            host=str(headers.get("host") or "").strip()
            proto=str(headers.get("x-forwarded-proto") or "https").split(",")[0].strip()
            if host:
                public=f"{proto}://{host}/"
        except Exception:
            public=""
    if not public:
        return ""
    try:
        u=urllib.parse.urlsplit(public)
        if u.scheme not in {"http","https"} or not u.netloc:
            return ""
        path=u.path or "/"
        return urllib.parse.urlunsplit((u.scheme,u.netloc,path,"",""))
    except Exception:
        return ""


def render_password_recovery_bridge():
    """Complete Supabase implicit password recovery entirely in the browser.

    Supabase returns recovery credentials in the URL fragment (#...), which is
    intentionally not sent to the Streamlit Python server. The browser form
    updates the password directly at Supabase, then signs in once with the new
    password and stores the fresh Supabase session in RAPA's Secure cookies.
    No access/refresh token is ever copied into Streamlit query parameters.
    """
    url=config_value("SUPABASE_URL",DEFAULT_SUPABASE_URL).rstrip("/")
    key=config_value("SUPABASE_PUBLISHABLE_KEY",DEFAULT_SUPABASE_PUBLISHABLE_KEY)
    lt=(lang=="LT")
    title="Nustatykite naują slaptažodį" if lt else "Choose a new password"
    intro=("Atkūrimo nuoroda patvirtinta. Įveskite naują slaptažodį du kartus. Išsaugojus RAPA jus prijungs automatiškai."
           if lt else "Recovery link verified. Enter the new password twice. RAPA will sign you in automatically after saving.")
    p1="Naujas slaptažodis" if lt else "New password"
    p2="Pakartokite naują slaptažodį" if lt else "Repeat new password"
    submit="IŠSAUGOTI IR PRISIJUNGTI" if lt else "SAVE AND SIGN IN"
    mismatch="Slaptažodžiai nesutampa arba yra trumpesni nei 8 simboliai." if lt else "Passwords do not match or are shorter than 8 characters."
    success="Slaptažodis pakeistas. Jūs prisijungėte automatiškai — tęsiame į RAPA." if lt else "Password changed. You are signed in automatically — continuing to RAPA."
    expired="Atkūrimo nuoroda negalioja arba jos laikas baigėsi. Grįžkite į RAPA ir užsakykite naują nuorodą." if lt else "This recovery link is invalid or expired. Return to RAPA and request a new link."
    failed="Slaptažodžio pakeisti nepavyko. Užsakykite naują atkūrimo nuorodą ir bandykite dar kartą." if lt else "Could not change the password. Request a new recovery link and try again."
    components.html(f'''<!doctype html><html><head><meta charset="utf-8"><style>
      body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:transparent;color:inherit}}
      #card{{display:none;border:1px solid rgba(128,128,128,.24);border-radius:12px;padding:18px 18px 16px;box-sizing:border-box;margin:0 0 12px}}
      h3{{margin:0 0 8px;font-size:20px}} .intro{{font-size:13px;line-height:1.45;margin:0 0 10px;opacity:.82}}
      label{{display:block;font-size:13px;font-weight:600;margin:10px 0 5px}}
      input{{width:100%;box-sizing:border-box;padding:10px 11px;border:1px solid rgba(128,128,128,.38);border-radius:8px;font-size:15px;background:transparent;color:inherit}}
      button{{width:100%;margin-top:14px;padding:10px 12px;border:0;border-radius:8px;font-size:14px;font-weight:700;cursor:pointer;background:#ff4b4b;color:white}}
      .msg{{margin-top:11px;font-size:13px;line-height:1.45}} .ok{{color:#1b7f3a}} .bad{{color:#b42318}}
    </style></head><body><div id="card"><h3>{html.escape(title)}</h3><div class="intro">{html.escape(intro)}</div><form id="f">
      <label>{html.escape(p1)}</label><input id="p1" type="password" autocomplete="new-password" minlength="8" required>
      <label>{html.escape(p2)}</label><input id="p2" type="password" autocomplete="new-password" minlength="8" required>
      <button type="submit">{html.escape(submit)}</button><div id="msg" class="msg"></div>
    </form></div><script>
    (() => {{
      let parentHash='';
      try {{ parentHash=window.parent.location.hash||''; }} catch(e) {{ parentHash=''; }}
      const hash=new URLSearchParams(parentHash.replace(/^#/,''));
      const access=hash.get('access_token')||'';
      const type=hash.get('type')||'';
      const err=hash.get('error')||hash.get('error_code')||'';
      const card=document.getElementById('card'); const msg=document.getElementById('msg');
      const show=() => {{card.style.display='block'; if(window.frameElement) window.frameElement.style.height='390px';}};
      if (err) {{ show(); document.getElementById('f').innerHTML='<div class="msg bad">'+{json.dumps(expired)}+'</div>'; return; }}
      if (!(type==='recovery' && access)) {{ if(window.frameElement) window.frameElement.style.height='0px'; return; }}
      show();
      document.getElementById('f').addEventListener('submit', async (ev) => {{
        ev.preventDefault(); const a=document.getElementById('p1').value; const b=document.getElementById('p2').value;
        if (a.length<8 || a!==b) {{ msg.className='msg bad'; msg.textContent={json.dumps(mismatch)}; return; }}
        msg.className='msg'; msg.textContent='...';
        try {{
          const me=await fetch({json.dumps(url + '/auth/v1/user')},{{headers:{{'apikey':{json.dumps(key)},'Authorization':'Bearer '+access}}}});
          if(!me.ok) throw new Error(await me.text());
          const user=await me.json(); const email=(user&&user.email)||'';
          if(!email) throw new Error('missing recovery email');
          const changed=await fetch({json.dumps(url + '/auth/v1/user')},{{method:'PUT',headers:{{'apikey':{json.dumps(key)},'Authorization':'Bearer '+access,'Content-Type':'application/json'}},body:JSON.stringify({{password:a}})}});
          if(!changed.ok) throw new Error(await changed.text());
          const login=await fetch({json.dumps(url + '/auth/v1/token?grant_type=password')},{{method:'POST',headers:{{'apikey':{json.dumps(key)},'Content-Type':'application/json'}},body:JSON.stringify({{email:email,password:a}})}});
          if(!login.ok) throw new Error(await login.text());
          const auth=await login.json();
          if(!auth.access_token || !auth.refresh_token) throw new Error('missing fresh session');
          const put=(doc,name,value)=>{{doc.cookie=name+'='+encodeURIComponent(value)+'; Path=/; Max-Age='+{int(_AUTH_COOKIE_MAX_AGE)}+'; SameSite=Lax; Secure';}};
          const save=(doc)=>{{put(doc,{json.dumps(_AUTH_COOKIE_ACCESS)},auth.access_token);put(doc,{json.dumps(_AUTH_COOKIE_REFRESH)},auth.refresh_token);}};
          try{{save(window.parent.document);}}catch(e){{try{{save(document);}}catch(_){{}}}}
          try{{window.parent.history.replaceState(null,'',window.parent.location.pathname+window.parent.location.search);}}catch(e){{}}
          document.getElementById('f').innerHTML='<div class="msg ok">'+{json.dumps(success)}+'</div>';
          if(window.frameElement) window.frameElement.style.height='160px';
          setTimeout(()=>{{
            try {{ const u=new URL(window.parent.location.href); u.hash=''; u.searchParams.set('password_reset_done','1'); window.parent.location.href=u.toString(); }} catch(e) {{}}
          }},700);
        }} catch(e) {{ msg.className='msg bad'; msg.textContent={json.dumps(failed)}; }}
      }});
    }})();
    </script></body></html>''',height=1,scrolling=False)


def _consume_password_reset_done():
    """Show a one-time success flash; do not sign the resident out again."""
    try:
        done=str(st.query_params.get("password_reset_done") or "")
    except Exception:
        done=""
    if done!="1":
        return
    st.session_state["_password_reset_success_flash"]=True
    try:
        del st.query_params["password_reset_done"]
    except Exception:
        pass


def render_auth_gate():
    sb=get_supabase_client()

    logout_cleanup=bool(st.session_state.pop("_logout_cookie_cleanup",False))
    if logout_cleanup:
        _render_auth_cookie_script(clear=True)
    else:
        if authenticated_user(sb) is None:
            _restore_persistent_auth_session(sb)

    if st.session_state.pop("_auth_cookie_clear_needed",False):
        _render_auth_cookie_script(clear=True)

    _consume_password_reset_done()
    render_password_recovery_bridge()
    user=authenticated_user(sb)
    if user is not None:
        enforce_auth_session_identity(user)
        _sync_persistent_auth_session(sb)
        if st.session_state.pop("_password_reset_success_flash",False):
            st.success("Slaptažodis sėkmingai pakeistas. Jūs jau prisijungę." if lang=="LT" else "Password changed successfully. You are already signed in.")
        return sb,user

    st.title(tr("login_title"))
    with st.form("login_form"):
        email=st.text_input(tr("auth_email"),key="login_email")
        password=st.text_input(tr("password"),type="password",key="login_password")
        go=st.form_submit_button(tr("login"),type="primary",use_container_width=True)
        if go:
            try:
                sb.auth.sign_in_with_password({"email":email.strip(),"password":password})
                st.rerun()
            except Exception:
                st.error(tr("auth_invalid"))

    with st.expander(tr("forgot_password"),expanded=False):
        if lang=="LT":
            st.caption("Įveskite paskyros el. paštą ir spauskite atkūrimo mygtuką. Tada atidarykite gautą RAPA laišką ir paspauskite nuorodą. Ji sugrąžins tiesiai į RAPA, kur iškart įvesite naują slaptažodį du kartus. Išsaugojus būsite prijungti automatiškai — papildomai jungtis nereikės.")
        else:
            st.caption("Enter the account email and send the recovery request. Open the RAPA email and follow its link. It returns directly to RAPA, where you enter the new password twice. After saving, you are signed in automatically — no second login is required.")
        with st.form("password_reset_request_form"):
            reset_email=st.text_input(tr("auth_email"),key="reset_email")
            reset_go=st.form_submit_button(tr("forgot_password_send"),use_container_width=True)
            if reset_go:
                clean=reset_email.strip().lower()
                if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$",clean):
                    st.error(tr("forgot_password_bad_email"))
                else:
                    try:
                        redirect=_password_recovery_redirect_url()
                        reset_fn=(getattr(sb.auth,"reset_password_for_email",None) or
                                  getattr(sb.auth,"reset_password_email",None))
                        if not callable(reset_fn):
                            raise RuntimeError("Supabase password recovery API unavailable")
                        if redirect:
                            reset_fn(clean,{"redirect_to":redirect})
                        else:
                            reset_fn(clean)
                        if lang=="LT":
                            st.success("Jei tokia paskyra egzistuoja, atkūrimo laiškas išsiųstas. Atidarykite jį ir spauskite atkūrimo nuorodą — RAPA pati atvers naujo slaptažodžio formą. Patikrinkite ir SPAM / Šlamšto aplanką.")
                        else:
                            st.success("If this account exists, the recovery email was sent. Open it and follow the recovery link — RAPA will open the new-password form automatically. Check spam too.")
                    except Exception as e:
                        low=str(e or "").lower()
                        if "rate limit" in low or "email rate" in low:
                            st.error(tr("forgot_password_rate_limit"))
                        else:
                            st.error(tr("forgot_password_error"))
    st.stop()

def require_linked_profile(sb,user):
    db.set_client(sb)
    auth_uid=_auth_uid(user)
    if not auth_uid:
        st.error("AUTH IDENTITY ERROR: authenticated user has no UID.")
        st.stop()

    profile=db.current_profile(auth_uid)
    if profile:
        if str(profile.get("user_id") or "")!=auth_uid:
            st.error(
                "IDENTITY SAFETY LOCK: prisijungusi paskyra neatitinka rezidento profilio. Prieiga sustabdyta."
                if lang=="LT" else
                "IDENTITY SAFETY LOCK: authenticated account does not match the resident profile. Access stopped."
            )
            st.stop()
        if profile.get("approved") and (
            profile.get("initials") or profile.get("access_role")=="observer"
        ):
            return profile

    directory=db.directory()
    st.title(tr("claim_title"))
    resident_tab,observer_tab=st.tabs([tr("resident_claim_tab"),tr("observer_claim_tab")])

    with resident_tab:
        st.info(tr("claim_help"))
        with st.form("claim_profile_form"):
            initials=st.selectbox(tr("user"),list(directory),format_func=lambda i:f"{i} — {directory[i]['full_name']}")
            code=st.text_input(tr("invite_code"),type="password")
            go=st.form_submit_button(tr("claim"),type="primary")
            if go:
                try:
                    db.claim_profile(initials,code.strip())
                    st.rerun()
                except Exception:
                    st.error(tr("claim_failed"))

    with observer_tab:
        st.info(tr("observer_claim_help"))
        with st.form("claim_observer_form"):
            observer_code=st.text_input(tr("observer_invite_code"),type="password")
            observer_go=st.form_submit_button(tr("observer_claim"),type="primary")
            if observer_go:
                try:
                    db.claim_observer_profile(observer_code.strip())
                    st.success(tr("observer_access_ready"))
                    st.rerun()
                except Exception:
                    st.error(tr("claim_failed"))
    st.stop()

def recurring_dates_for_month(y,m,rows):
    _,ndays=calendar.monthrange(y,m)
    out={"unavailable":set(),"unavailable_am":set(),"unavailable_pm":set(),"soft_free":set(),"preferred":set()}
    for r in rows:
        if not r.get("active",True): continue
        wd=int(r.get("weekday",0)); typ=r.get("preference_type"); block=r.get("block","FULL")
        days={d for d in range(1,ndays+1) if date(y,m,d).weekday()==wd}
        if typ=="hard_unavailable":
            if block=="AM": out["unavailable_am"] |= days
            elif block=="PM": out["unavailable_pm"] |= days
            else: out["unavailable"] |= days
        elif typ=="soft_free": out["soft_free"] |= days
        elif typ=="preferred": out["preferred"] |= days
    return out

# V2.5.159 — authoritative Onko cycle seed supplied by SP/warden on 2026-09-10.
# These residents completed their September Onko pair. The cycle is tracked in
# 2-day units: residents with the lower cumulative total are offered the next
# pair first; after everyone catches up, the cycle continues from the new floor.
OFFICIAL_ONKO_CYCLE_SEED = {
    (2026, 9): {
        "SE": 2, "KE": 2, "MR": 2, "ŠR": 2, "GB": 2, "GD": 2,
        "DU": 2, "SA": 2, "MŽ": 2, "GE": 2, "PV": 2,
    }
}

def historical_onko_cycle_counts_before(y,m):
    """Return cumulative Onko days before ``y,m`` for the dedicated Onko cycle.

    September-2026 is seeded from the warden's authoritative list. If a stored
    September baseline exists, the seed replaces that month's Onko contribution
    so it cannot be double-counted. Other published months are read normally.
    This history is used only for Onko-cycle ordering; it does not reactivate
    general future-month fairness debt.
    """
    out={p["initials"]:0 for p in DEFAULT_PEOPLE}
    monthly={}
    try:
        rows=db.published_baselines_before(y,m)
    except Exception:
        rows=[]
    for r in rows:
        try:
            yy=int(r["year"]); mm=int(r["month"])
            if (yy,mm) >= (int(y),int(m)):
                continue
            payload=r.get("baseline_json") or {}
            ass={int(k):v for k,v in (payload.get("assignments") or {}).items()}
            slot_map={s.idx:s for s in make_slots(yy,mm)}
            bucket={p["initials"]:0 for p in DEFAULT_PEOPLE}
            for sid,ini in ass.items():
                sl=slot_map.get(int(sid))
                if sl is not None and ini in bucket and is_onko_slot(sl):
                    bucket[ini]+=1
            monthly[(yy,mm)]=bucket
        except Exception:
            continue

    # The warden-supplied September list is the source of truth for that month.
    for smonth,seed in OFFICIAL_ONKO_CYCLE_SEED.items():
        if smonth < (int(y),int(m)):
            monthly[smonth]={p["initials"]:int(seed.get(p["initials"],0) or 0) for p in DEFAULT_PEOPLE}

    for bucket in monthly.values():
        for ini,n in bucket.items():
            if ini in out:
                out[ini]+=max(0,int(n or 0))
    return out

def historical_rotation_counts_before(y,m):
    """Count prior published SYSTEM workplace exposures for longitudinal catch-up."""
    out={p["initials"]:{cat:0 for cat in ROTATION_CATEGORIES} for p in DEFAULT_PEOPLE}
    try:
        rows=db.published_baselines_before(y,m)
    except Exception:
        return out
    for r in rows:
        try:
            yy=int(r["year"]); mm=int(r["month"])
            payload=r.get("baseline_json") or {}
            ass={int(k):v for k,v in (payload.get("assignments") or {}).items()}
            slot_map={s.idx:s for s in make_slots(yy,mm)}
            for sid,ini in ass.items():
                s=slot_map.get(int(sid))
                if s is None or ini not in out:
                    continue
                cat=rotation_category(s)
                if cat in out[ini]:
                    out[ini][cat]+=1
        except Exception:
            continue
    return out


def historical_holiday_counts_before(y,m):
    """Count prior published SYSTEM public-holiday assignments for longitudinal rotation."""
    out={p["initials"]:0 for p in DEFAULT_PEOPLE}
    try:
        rows=db.published_baselines_before(y,m)
    except Exception:
        return out
    for r in rows:
        try:
            yy=int(r["year"]); mm=int(r["month"])
            payload=r.get("baseline_json") or {}
            ass={int(k):v for k,v in (payload.get("assignments") or {}).items()}
            slot_map={sl.idx:sl for sl in make_slots(yy,mm)}
            for sid,ini in ass.items():
                sl=slot_map.get(int(sid))
                if sl is not None and ini in out and is_public_holiday(yy,mm,sl.day):
                    out[ini]+=1
        except Exception:
            continue
    return out


def _previous_month_effective_actual_assignments(y,m):
    """Immediately prior month's real/effective work for cross-boundary safety only."""
    py,pm=(y-1,12) if m==1 else (y,m-1)
    try:
        rows=db.list_published_schedules()
        row=next((r for r in reversed(rows) if int(r.get("year",0))==py and int(r.get("month",0))==pm),None)
        if not row or not row.get("current_json"):
            return py,pm,{}
        payload=row.get("current_json") or {}
        ass={int(k):v for k,v in (payload.get("assignments") or {}).items()}
        return py,pm,effective_actual_assignments(ass,db.list_backups(py,pm))
    except Exception:
        return py,pm,{}


def historical_weekend_tail_streak_before(y,m):
    """Prior-month ACTUAL weekend tail streak; spacing only, never catch-up."""
    out={p["initials"]:0 for p in DEFAULT_PEOPLE}
    py,pm,ass=_previous_month_effective_actual_assignments(y,m)
    if not ass:
        return out
    try:
        slot_map={s.idx:s for s in make_slots(py,pm)}
        anchors=sorted({(sl.day if sl.weekday==5 else sl.day-1) for sl in slot_map.values() if sl.weekday>=5})
        for ini in out:
            worked={(slot_map[sid].day if slot_map[sid].weekday==5 else slot_map[sid].day-1)
                    for sid,who in ass.items() if who==ini and sid in slot_map and slot_map[sid].weekday>=5}
            streak=0
            for a in reversed(anchors):
                if a in worked: streak+=1
                else: break
            out[ini]=streak
    except Exception:
        return {p["initials"]:0 for p in DEFAULT_PEOPLE}
    return out


def historical_previous_month_onko_counts(y,m):
    """Immediate prior-month ACTUAL Onko counts for explicit month-to-month eligibility rules."""
    out={p["initials"]:0 for p in DEFAULT_PEOPLE}
    py,pm,ass=_previous_month_effective_actual_assignments(y,m)
    if not ass:
        return out
    try:
        slot_map={s.idx:s for s in make_slots(py,pm)}
        for sid,ini in ass.items():
            sl=slot_map.get(int(sid))
            if sl is not None and ini in out and is_onko_slot(sl):
                out[ini]+=1
    except Exception:
        return {p["initials"]:0 for p in DEFAULT_PEOPLE}
    return out


def historical_previous_last_day_onko_before(y,m):
    """Prior-month ACTUAL last-day Onko state for cross-boundary safety only."""
    out={p["initials"]:False for p in DEFAULT_PEOPLE}
    py,pm,ass=_previous_month_effective_actual_assignments(y,m)
    if not ass:
        return out
    try:
        slot_map={s.idx:s for s in make_slots(py,pm)}
        last_day=calendar.monthrange(py,pm)[1]
        for sid,ini in ass.items():
            sl=slot_map.get(int(sid))
            if sl is not None and ini in out and sl.day==last_day and is_onko_slot(sl):
                out[ini]=True
    except Exception:
        return {p["initials"]:False for p in DEFAULT_PEOPLE}
    return out


def historical_previous_last_day_duty_before(y,m):
    """Prior-month ACTUAL last-day internal NIGHT duty for mandatory next-day OFF.

    Compatibility name retained; from V2.5.165 a daytime/weekend FULL duty does
    not automatically block the following day.
    """
    out={p["initials"]:False for p in DEFAULT_PEOPLE}
    py,pm,ass=_previous_month_effective_actual_assignments(y,m)
    if not ass:
        return out
    try:
        slot_map={s.idx:s for s in make_slots(py,pm)}
        last_day=calendar.monthrange(py,pm)[1]
        for sid,ini in ass.items():
            sl=slot_map.get(int(sid))
            if sl is not None and ini in out and sl.day==last_day and is_duty_slot(sl) and sl.block=="NIGHT":
                out[ini]=True
    except Exception:
        return {p["initials"]:False for p in DEFAULT_PEOPLE}
    return out


def historical_resident_hard_losses_before(y,m):
    """Legacy audit-only RESIDENT-HARD violation count from prior SYSTEM baselines. V2.5.107 never uses it as a generation input."""
    out={p["initials"]:0 for p in DEFAULT_PEOPLE}
    try:
        rows=db.published_baselines_before(y,m)
    except Exception:
        return out
    for r in rows:
        try:
            payload=r.get("baseline_json") or {}
            people_stats=((payload.get("stats") or {}).get("people") or {})
            for initials,d in people_stats.items():
                if initials in out:
                    out[initials]+=int((d or {}).get("resident_hard_losses",0) or 0)
        except Exception:
            continue
    return out


def _request_source(monthly_set, recurring_set, day):
    a=day in set(monthly_set or set()); b=day in set(recurring_set or set())
    if a and b: return "monthly+recurring"
    if a: return "monthly"
    if b: return "recurring"
    return "effective"


def _build_request_ledger(y,m,initials,p,s,rp,recurring_rows,claims,slot_lookup,
                          effective_unavail,effective_unavail_am,effective_unavail_pm,
                          effective_soft,effective_soft_am,effective_soft_pm,
                          effective_pref,effective_pref_am,effective_pref_pm):
    """One normalized resident-facing ledger across ALL structured input tables."""
    items=[]
    def add(kind,tier,day=None,block="FULL",source="monthly",value=None,score=True,**extra):
        rid=f"{source}:{kind}:{day if day is not None else '-'}:{block}:{len(items)}"
        row={"id":rid,"kind":kind,"tier":tier,"day":day,"block":block,"source":source,
             "value":value,"included_in_score":bool(score)}
        row.update(extra); items.append(row)

    # RESIDENT HARD: monthly and/or recurring `Negaliu dirbti`.
    monthly_u=set(p.get("unavailable",set())); monthly_am=set(p.get("unavailable_am",set())); monthly_pm=set(p.get("unavailable_pm",set()))
    for d in sorted(effective_unavail): add("resident_hard","RESIDENT_HARD",d,"FULL",_request_source(monthly_u,rp["unavailable"],d))
    for d in sorted(set(effective_unavail_am)-set(effective_unavail)): add("resident_hard","RESIDENT_HARD",d,"AM",_request_source(monthly_am,rp["unavailable_am"],d))
    for d in sorted(set(effective_unavail_pm)-set(effective_unavail)): add("resident_hard","RESIDENT_HARD",d,"PM",_request_source(monthly_pm,rp["unavailable_pm"],d))

    # Exact SOFT monthly/recurring wishes after the same override logic used by the engine.
    m_sf=set(p.get("soft_free",set())); m_sfa=set(p.get("soft_free_am",set())); m_sfp=set(p.get("soft_free_pm",set()))
    m_pr=set(p.get("preferred",set())); m_pra=set(p.get("preferred_am",set())); m_prp=set(p.get("preferred_pm",set()))
    for d in sorted(effective_soft): add("soft_free","SOFT1_TIME_PROTECTION",d,"FULL",_request_source(m_sf,rp["soft_free"],d))
    for d in sorted(effective_soft_am): add("soft_free","SOFT1_TIME_PROTECTION",d,"AM","monthly")
    for d in sorted(effective_soft_pm): add("soft_free","SOFT1_TIME_PROTECTION",d,"PM","monthly")
    for d in sorted(effective_pref): add("preferred","SOFT2_POSITIVE_PLACEMENT",d,"FULL",_request_source(m_pr,rp["preferred"],d))
    for d in sorted(effective_pref_am): add("preferred","SOFT2_POSITIVE_PLACEMENT",d,"AM","monthly")
    for d in sorted(effective_pref_pm): add("preferred","SOFT2_POSITIVE_PLACEMENT",d,"PM","monthly")

    # V2.5.140: Nustatymai describe HOW the resident prefers the system to shape
    # work, but they are not monthly wishes. The engine still uses them strongly,
    # while request statistics / "Ko prašei" remain limited to actual requests.

    # ABSOLUTE HARD / safety facts are audited but excluded from the preference % denominator.
    for d in sorted(set(p.get("vacation",set()))): add("vacation","ABSOLUTE_HARD",d,"FULL","monthly",score=False)
    for d in sorted(set(p.get("justified_absence",set()))): add("justified_absence","ABSOLUTE_HARD",d,"FULL","monthly",score=False)
    for d in sorted(set(p.get("long_duty",set()))): add("long_duty","ABSOLUTE_HARD",d,"FULL","monthly",score=False)

    # Self-selected backup commitments and valid rest-credit redemptions are structured resident choices.
    for claim in claims or []:
        cs=slot_lookup.get(int(claim.get("covered_slot")))
        if cs is not None:
            # V2.5.118: dublis selection is informational/theoretical only. It is
            # never part of normal-schedule preference scoring.
            add("backup_claim","THEORETICAL_BACKUP",cs.day,cs.block,"backup_claim",score=False,covered_slot=cs.idx,department=cs.department)
    _reward_units=max(0,int(p.get("reward_credit_units_to_use",0) or 0))
    for _ in range(_reward_units//6):
        add("rest_credit","ENTITLEMENT",source="reward_credit_v25136",value="0.50 kredito")

    note=str(p.get("note") or "").strip()
    if note:
        add("note","INFO",source="free_text",value=note,score=False)
    return items

def load_people(y,m):
    prefs=db.all_preferences(y,m); settings=db.all_account_settings(); recurring=db.all_recurring_preferences(); people=[]
    special_workdays=db.all_special_workdays_v25145(y,m)
    # Privatūs SP + ŠR planavimo pageidavimai perduodami tik generavimo metu ir
    # nepatenka į bendrą rezidentų pageidavimų auditą. V2.5.128 detales gali
    # perskaityti tik šios dvi patvirtintos operatorių paskyros.
    try:
        private_operator_pair_rows=_list_operator_private_pair_preferences_v25130(y,m)
    except Exception:
        private_operator_pair_rows=[]
    # Suderinamumas prieš paleidžiant V2.5.128 migraciją: senos SP eilutės vis dar
    # gali būti perskaitytos iš V2.5.123 lentelės SP paskyroje.
    if not private_operator_pair_rows:
        try:
            private_operator_pair_rows=[dict(x,owner_initials="SP") for x in db.list_sp_private_pair_preferences_v25123(y,m)]
        except Exception:
            private_operator_pair_rows=[]
    private_pairs_by_owner={}
    for _row in private_operator_pair_rows:
        _owner=str(_row.get("owner_initials") or "SP")
        private_pairs_by_owner.setdefault(_owner,[]).append(dict(_row))
    try:
        sp_dream_cfg=_get_sp_dream_team_config_v25130() or {}
        sp_dream_month=_get_sp_dream_team_month_v25130(y,m) or {}
    except Exception:
        sp_dream_cfg={}; sp_dream_month={}
    # Pateikimo eilė yra mėnesinė ir nekaupiama. Ji taikoma TAM PAČIAM grafikui
    # tik po to, kai bendras maksimaliai įmanomas pageidavimų išpildymas užrakinamas.
    priority_rows=db.all_applied_preference_priorities(y,m) if weekend_fcfs_backup_mode(y,m) else {}
    reward_redemptions=db.all_reward_credit_redemptions_v25136(y,m)
    # V2.5.96: fairness history is audit-only; never solver input for a new month.
    fairness_prior={}
    holiday_prior={}
    rotation_prior={}
    resident_hard_prior={}
    # Cross-month safety/spacing state remains because it is not fairness catch-up.
    weekend_tail=historical_weekend_tail_streak_before(y,m)
    previous_month_onko=historical_previous_month_onko_counts(y,m)
    previous_last_day_onko=historical_previous_last_day_onko_before(y,m)
    previous_last_day_duty=historical_previous_last_day_duty_before(y,m)
    onko_cycle_prior=historical_onko_cycle_counts_before(y,m)
    claim_rows=db.list_backup_claims(y,m)
    claims_by_initials={}
    for r in claim_rows:
        claims_by_initials.setdefault(r["initials"],[]).append(r)
    slot_lookup={s.idx:s for s in make_slots(y,m)}
    py,pm=(y-1,12) if m==1 else (y,m-1)
    prev_prefs=db.all_preferences(py,pm); prev_last=calendar.monthrange(py,pm)[1]
    for row in DEFAULT_PEOPLE:
        initials=row["initials"]; p=dict(prefs.get(initials,{}) or {}); s=settings.get(initials,{})
        special=dict(special_workdays.get(initials,{}) or {})
        reward_units=max(0,int(reward_redemptions.get(initials,0) or 0))
        # Current day scheduler works in 6h workload blocks. One 0.50-credit redemption
        # equals six ordinary tariff-hours and therefore removes one 6h target block.
        p["reward_credit_units_to_use"]=reward_units
        duty_days=set(p.get("long_duty",set()))
        if prev_last in set(prev_prefs.get(initials,{}).get("long_duty",set())):
            duty_days.add(0)
        rp=recurring_dates_for_month(y,m,recurring.get(initials,[]))
        short_soft=set(p.get("soft_free",set())); short_soft_am=set(p.get("soft_free_am",set())); short_soft_pm=set(p.get("soft_free_pm",set()))
        short_pref=set(p.get("preferred",set())); short_pref_am=set(p.get("preferred_am",set())); short_pref_pm=set(p.get("preferred_pm",set()))
        # Specific monthly requests override an opposite recurring whole-day pattern on that date.
        any_short_pref=short_pref|short_pref_am|short_pref_pm
        any_short_soft=short_soft|short_soft_am|short_soft_pm
        # V2.5.90 BASELINE WEEKEND VOLUNTEER OVERRIDE.
        # Recurring weekend "Noriu laisvos" remains blocked because it can dump
        # unavoidable weekend burden onto peers. The OPPOSITE signal is allowed:
        # recurring weekend "Pageidauju dirbti" is a voluntary unpopular-duty offer.
        recurring_soft_allowed={d for d in set(rp["soft_free"]) if date(y,m,d).weekday()<5}
        # V2.5.140: weekend positive work request is monthly-only and capped at
        # one concrete weekend date (Saturday OR Sunday) per resident.
        recurring_pref_allowed={d for d in set(rp["preferred"]) if date(y,m,d).weekday()<5}
        effective_soft=(recurring_soft_allowed-any_short_pref)|short_soft
        effective_pref=(recurring_pref_allowed-any_short_soft)|short_pref
        # Long-term RESIDENT HARD cannot be overridden by an opposite monthly SOFT
        # request. Whole-day resident hard subsumes same-day AM/PM rows.
        effective_unavail=set(rp["unavailable"])|set(p.get("unavailable",set()))
        effective_unavail_am=(set(rp["unavailable_am"])|set(p.get("unavailable_am",set())))-effective_unavail
        effective_unavail_pm=(set(rp["unavailable_pm"])|set(p.get("unavailable_pm",set())))-effective_unavail
        effective_soft_am=short_soft_am
        effective_soft_pm=short_soft_pm
        effective_pref_am=short_pref_am
        effective_pref_pm=short_pref_pm

        # V2.5.146: planned Specialios dienos are a separate official work-status
        # layer. They supersede same-date scheduling wishes without modifying the
        # resident's saved wish row or submission priority.
        _special_days=set(special.get("wellness_days",set())) | set(special.get("qualification_days",set()))
        effective_unavail=set(effective_unavail)-_special_days
        effective_unavail_am=set(effective_unavail_am)-_special_days
        effective_unavail_pm=set(effective_unavail_pm)-_special_days
        effective_soft=set(effective_soft)-_special_days
        effective_soft_am=set(effective_soft_am)-_special_days
        effective_soft_pm=set(effective_soft_pm)-_special_days
        effective_pref=set(effective_pref)-_special_days
        effective_pref_am=set(effective_pref_am)-_special_days
        effective_pref_pm=set(effective_pref_pm)-_special_days
        _weekend_pref_dates=sorted({
            d for d in (set(effective_pref)|set(effective_pref_am)|set(effective_pref_pm))
            if 1<=int(d)<=calendar.monthrange(y,m)[1] and date(y,m,int(d)).weekday()>=5
        })
        if len(_weekend_pref_dates)>1:
            # Legacy data may contain several weekend requests. Keep the earliest
            # concrete weekend date so old rows cannot distort the new one-per-month rule.
            _keep=_weekend_pref_dates[0]
            effective_pref={d for d in effective_pref if date(y,m,int(d)).weekday()<5 or int(d)==_keep}
            effective_pref_am={d for d in effective_pref_am if date(y,m,int(d)).weekday()<5 or int(d)==_keep}
            effective_pref_pm={d for d in effective_pref_pm if date(y,m,int(d)).weekday()<5 or int(d)==_keep}
        credits_day=reward_units//6
        credits_am=credits_day
        credits_pm=0
        prior=fairness_prior.get(initials,{})
        reserved=set()
        if not weekend_fcfs_backup_mode(y,m):
            for claim in claims_by_initials.get(initials,[]):
                cs=slot_lookup.get(int(claim["covered_slot"]))
                if cs is not None:
                    reserved.add((cs.day,cs.block))
        pri=priority_rows.get(initials,{})
        request_items=_build_request_ledger(
            y,m,initials,p,s,rp,recurring.get(initials,[]),claims_by_initials.get(initials,[]),slot_lookup,
            effective_unavail,effective_unavail_am,effective_unavail_pm,
            effective_soft,effective_soft_am,effective_soft_pm,
            effective_pref,effective_pref_am,effective_pref_pm
        )
        people.append(Person(initials=initials,name=row["name"],target_adjustment=row.get("target_adjustment",0)-credits_day,
            unavailable=effective_unavail,
            unavailable_am=effective_unavail_am,
            unavailable_pm=effective_unavail_pm,
            vacation=set(p.get("vacation",set()))-_special_days,
            justified_absence=set(p.get("justified_absence",set()))-_special_days,
            wellness_days=set(special.get("wellness_days",set())),
            qualification_days=set(special.get("qualification_days",set())),
            long_duty=duty_days,reserved_backup=reserved,
            soft_free=effective_soft,soft_free_am=effective_soft_am,soft_free_pm=effective_soft_pm,
            preferred=effective_pref,preferred_am=effective_pref_am,preferred_pm=effective_pref_pm,
            weekday_preference=max(-2,min(2,int(s.get("weekday_preference",0) or 0))),weekend_preference=0,holiday_preference=max(-1,min(1,int(s.get("holiday_preference",0) or 0))),spread_preference=int(s.get("spread_preference",0)),
            shift_length_preference=max(0,min(3,int(s.get("shift_length_preference",0) or 0))),
            avoid_doubles=(max(0,min(3,int(s.get("shift_length_preference",0) or 0)))==1 or bool(s.get("avoid_doubles",False))),note=p.get("note",""),
            request_items=request_items,
            preference_priority_points=int(pri.get("points_awarded") or 0),
            preference_priority_rank=int(pri.get("submission_order") or 0),
            privileged_pair_preferences=[dict(x) for x in private_pairs_by_owner.get(initials,[])],
            dream_team_centro_members=(tuple(sp_dream_cfg.get("centro_members") or ["SP","ŠR","GE"]) if initials=="SP" else tuple()),
            dream_team_centro_target=(int(sp_dream_month.get("centro_target",4) or 0) if initials=="SP" else 0),
            dream_team_adc_members=(tuple(sp_dream_cfg.get("adc_members") or ["SP","ŠR"]) if initials=="SP" else tuple()),
            dream_team_adc_target=(int(sp_dream_month.get("adc_target",0) or 0) if initials=="SP" else 0),
            rest_credit_am_to_use=credits_am,rest_credit_pm_to_use=credits_pm,
            prior_weekend_count=0,
            prior_holiday_count=0,
            prior_friday_count=0,
            prior_double_count=0,
            prior_weekday_day_count=0,
            # General historical post debt stays disabled, but Onko has a dedicated
            # longitudinal pair-cycle requested by SP. Carry only the active Onko
            # category into the engine so remaining residents catch up first.
            prior_rotation_counts={
                cat:(int(onko_cycle_prior.get(initials,0) or 0) if cat==("Onko/TBL" if cohort_october_model(y,m) else "Onko RO") else 0)
                for cat in ROTATION_CATEGORIES
            },
            prior_consecutive_weekend_streak=int(weekend_tail.get(initials,0)),
            prior_last_day_onko=bool(previous_last_day_onko.get(initials,False)),
            prior_last_day_duty=bool(previous_last_day_duty.get(initials,False)),
            prior_month_onko_count=int(previous_month_onko.get(initials,0) or 0),
            prior_resident_hard_loss_count=0))
    return people


def people_for_stored_result(result, y, m):
    """Use the immutable publication-time request snapshot whenever available.

    This is both semantically correct and operationally resilient: post-publication
    swap/revalidation must use the frozen request set, so it should not re-read
    preferences/account_settings/recurring_preferences on every Streamlit rerun.
    Legacy payloads without a snapshot fall back to live load_people().
    """
    frozen=people_from_request_snapshot(getattr(result,"request_snapshot",None))
    if frozen:
        return frozen
    return load_people(y,m)


def refresh_result_payload(payload, y, m, use_actual_backups=True):
    """Revalidate stored assignments against the CURRENT engine and ORIGINAL requests.

    SYSTEM/baseline views pass ``use_actual_backups=False`` so their publication-time
    backup snapshot stays frozen. ACTUAL/current views use the live backup table, so
    swaps and backup changes update realized request satisfaction without rewriting
    the original SYSTEM fairness ledger.
    """
    if not payload:
        return None
    stored=deserialize_result(payload)
    # V2.5.115 — theoretical backup duties are a separate standby layer.
    # SYSTEM/DRAFT request satisfaction is computed from NORMAL work only.
    # ACTUAL may pass live backup rows so a COMPLETED real-life cover can be
    # reflected as actual work; planned/activated-only standby still never counts.
    backup_override=[]
    if use_actual_backups:
        try:
            backup_override=db.list_backups(y,m)
        except Exception:
            backup_override=stored.backup_snapshot or []
    try:
        refreshed=revalidate_loaded_result(
            y,m,people_for_stored_result(stored,y,m),stored,
            backup_assignments=backup_override,
            validation_mode=("voluntary_swap_actual" if use_actual_backups else "generation"),
        )
    except TypeError as exc:
        # Deployment-safety guard: never let a mixed app/engine deployment crash
        # the whole Apsikeitimai page with a raw unexpected-keyword TypeError.
        if "validation_mode" in str(exc):
            raise RuntimeError(
                "APP_ENGINE_VERSION_MISMATCH: deployed app.py expects the V2.5.107 "
                "scheduler_engine.py API. Redeploy BOTH files from the same package."
            ) from exc
        raise
    if use_actual_backups:
        # V2.5.57: CURRENT stats are operational / satisfaction facts only.
        # All fairness, post spread, future catch-up and longitudinal catch-up remain
        # anchored to baseline_json/fairness_history and must not be inferred
        # from CURRENT after voluntary swaps or fairness-neutral repairs.
        gg=refreshed.stats.setdefault("global",{})
        gg["actual_operational_view"] = True
        gg["system_fairness_accounting_source"] = "PUBLISHED_BASELINE_JSON"
        gg["post_publication_changes_excluded_from_fairness"] = True
        gg["post_publication_changes_excluded_from_post_spread"] = True
        gg["post_publication_changes_excluded_from_post_debt"] = True
    return refreshed


def persist_actual_satisfaction(y,m,payload=None):
    """Persist the ACTUAL request/satisfaction snapshot after any post-publication change.

    The original request set remains frozen inside the grafikas payload. This helper
    only recalculates the CURRENT/ACTUAL realization against that original set and
    the live backup table; only COMPLETED covers can change ACTUAL work, so later retrospective month review can read the final
    satisfaction percentages without touching the immutable SYSTEM baseline.
    """
    payload=payload or db.load_schedule(y,m,"current")
    if not payload:
        return None
    refreshed=refresh_result_payload(payload,y,m,use_actual_backups=True)
    db.save_current(y,m,serialize_result(refreshed))
    return refreshed


def credit_selection_errors(y,m):
    """Validate V2.5.136 coefficient-credit reservations before SYSTEM freeze."""
    errors=[]
    reds=db.all_reward_credit_redemptions_v25136(y,m)
    for row in DEFAULT_PEOPLE:
        i=row["initials"]
        use_units=max(0,int(reds.get(i,0) or 0))
        available=db.reward_credit_available_for_month(i,y,m)
        if use_units % 6 != 0:
            errors.append({tr("person"):i,tr("details"):"Kreditų panaudojimas šiam dieniniam grafikui turi būti 0,50 kredito žingsniais."})
        if use_units>available:
            errors.append({tr("person"):i,tr("details"):f"Pasirinkta {use_units/12:.2f} kred., galima {available/12:.2f} kred."})
    return errors

def _parse_iso_dt(value):
    if not value: return None
    try: return datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except Exception: return None



def schedule_grid(y,m,result,status_rows=None):
    _,ndays=calendar.monthrange(y,m); rows={}
    for s in make_slots(y,m):
        if not slot_visible_in_schedule(s,y,m):
            continue
        key=f"{slot_department_text(y,m,s,grid=True)} [{block_label(s.block)}]"
        rows.setdefault(key,{d:"" for d in range(1,ndays+1)})
        rows[key][s.day]=result.assignments.get(s.idx,"")

    # V2.5.145: paid workdays outside the clinical rota are visible directly in
    # the schedule calendar as an away/status row, while remaining separate from
    # resident wish statistics.
    try:
        special_all=db.all_special_workdays_v25145(y,m)
    except Exception:
        special_all={}
    for ini,special in special_all.items():
        for label,dayset in (("Sveikatinimas" if lang=="LT" else "Wellness",special.get("wellness_days",set())),
                             ("Kvalifikacijos kėlimas" if lang=="LT" else "Qualification",special.get("qualification_days",set()))):
            key=(f"IŠVYKĘS · {ini} · {label}" if lang=="LT" else f"AWAY · {ini} · {label}")
            rows.setdefault(key,{d:"" for d in range(1,ndays+1)})
            for day in dayset:
                try: di=int(day)
                except Exception: continue
                if 1<=di<=ndays: rows[key][di]=ini

    # SP 2026-09-10 asked for a dedicated night SPS RO row in the visual schedule.
    # Operational dates/hours were not supplied, so V2.5.158 shows the row as a
    # presentation scaffold only; it does not create fake NIGHT assignments or workload.
    if cohort_october_model(y,m):
        _night_key=("SPS RO naktiniai budėjimai [Naktis]" if lang=="LT" else "SPS RO night duties [Night]")
        rows.setdefault(_night_key,{d:"" for d in range(1,ndays+1)})

    for r in (status_rows or []):
        ini=str(r.get("initials") or "")
        try: day=int(r.get("day"))
        except Exception: continue
        if not ini or not (1<=day<=ndays): continue
        _kind=str(r.get("status_kind") or "")
        if lang=="LT":
            _status_label={"sick_leave":"PATEISINAMAS NEATVYKIMAS","qualification":"KVALIFIKACIJOS KĖLIMAS","wellness":"SVEIKATINIMAS"}.get(_kind,"NEDIRBA")
        else:
            _status_label={"sick_leave":"JUSTIFIED ABSENCE","qualification":"QUALIFICATION","wellness":"WELLNESS"}.get(_kind,"NOT WORKING")
        key=f"{_status_label} · {ini}"
        rows.setdefault(key,{d:"" for d in range(1,ndays+1)})
        rows[key][day]=ini
    def _row_order(k):
        s=str(k)
        block_rank=0 if ("[Rytas]" in s or "[Morning]" in s) else 1 if ("[Visa diena]" in s or "[Full day]" in s) else 2 if ("[Popietė]" in s or "[Afternoon]" in s) else 3
        if s.startswith("CENTRO RO"):
            try: num=int(re.search(r"CENTRO RO (\d+)",s).group(1))
            except Exception: num=9
            return (10,block_rank,num,s)
        if s.startswith("Onkologinė/TBL") or s.startswith("Onko/TBL"): return (20,block_rank,0,s)
        if s.startswith("Centro UG 120"): return (30,block_rank,0,s)
        if s.startswith("SPS RO d.d."): return (40,block_rank,0,s)
        if s.startswith("SPS RO nakt") or s.startswith("SPS RO night"): return (41,3,0,s)
        if s.startswith("SPS UG 1035"): return (50,block_rank,0,s)
        if s.startswith("ADC 144"): return (60,block_rank,0,s)
        if s.startswith("145") or s.startswith("ADC 145"): return (61,block_rank,0,s)
        if s.startswith("Vaikų UG"): return (70,block_rank,0,s)
        if s.startswith("Skopijos"): return (80,block_rank,0,s)
        if s.startswith("SPS RO budėjimai"): return (90,block_rank,0,s)
        if s.startswith("IŠVYKĘS") or s.startswith("AWAY") or s.startswith("PATEISINAMAS") or s.startswith("JUSTIFIED"): return (1000,block_rank,0,s)
        return (500,block_rank,0,s)
    rows=dict(sorted(rows.items(),key=lambda kv:_row_order(kv[0])))
    df=pd.DataFrame.from_dict(rows,orient="index"); df.columns=[f"{d:02d}\n{WEEKDAYS[lang][date(y,m,d).weekday()]}" for d in range(1,ndays+1)]
    return df

def style_schedule(df):
    def cs(v):
        c=PERSON_COLORS.get(str(v))
        # SP/admin aesthetics: one consistent white text color on all resident cells.
        return "" if not c else f"background-color:{c};color:#FFFFFF;font-weight:700;text-align:center;text-shadow:0 1px 2px rgba(0,0,0,.45);"
    return df.style.map(cs)

def style_rows(df):
    pc=tr("person")
    def rowstyle(row):
        c=PERSON_COLORS.get(str(row.get(pc,""))); css="" if not c else f"background-color:{c};color:{contrast_text(c)};"
        return [css]*len(row)
    return df.style.apply(rowstyle,axis=1)

def _stable_rank(*parts):
    raw="|".join(map(str,parts)).encode("utf-8")
    return int(hashlib.sha1(raw).hexdigest()[:12],16)


def _assignments_for_person_day(y,m,result,initials,day):
    rows=[]
    for s in make_slots(y,m):
        if s.day==day and result.assignments.get(s.idx)==initials:
            rows.append(s)
    return sorted(rows,key=lambda s:{"AM":0,"FULL":1,"PM":2}.get(s.block,9))


def _covered_shift_text(y,m,result,slot_id):
    slots={s.idx:s for s in make_slots(y,m)}
    s=slots.get(int(slot_id))
    if s is None:
        return "—"
    return f"{s.department} ({block_label(s.block)})"


def _eligible_backup_candidates(y,m,result,covered_slot,people=None,allow_resident_hard=False):
    """Residents who can cover one specific shift.

    Default is strict zero-RESIDENT-HARD-loss eligibility. The planner may invoke
    ``allow_resident_hard=True`` only as a last-resort fallback; ABSOLUTE HARD and
    overlapping normal work remain unbreakable in both modes.
    """
    if people is None:
        people=load_people(y,m)
    slots=make_slots(y,m)
    assigned=result.assignments.get(covered_slot.idx)
    candidates=[]
    for p in people:
        if p.initials==assigned:
            continue
        unavailable=(
            absolute_unavailable_for_block(p,covered_slot.day,covered_slot.block)
            if allow_resident_hard else
            hard_unavailable_for_block(p,covered_slot.day,covered_slot.block)
        )
        if unavailable:
            continue
        own=[
            sl for sl in slots
            if sl.day==covered_slot.day and result.assignments.get(sl.idx)==p.initials
        ]
        if any(blocks_overlap(sl.block,covered_slot.block) for sl in own):
            continue
        candidates.append(p.initials)
    return candidates




def _backup_override_note_decode(note):
    prefix="V2561_BACKUP_OVERRIDE:"
    raw=str(note or "")
    if raw.startswith(prefix):
        try:
            data=json.loads(raw[len(prefix):])
            return data if isinstance(data,dict) else {}
        except Exception:
            return {}
    return {"legacy_note":raw} if raw else {}


def _backup_override_note_encode(meta, legacy_note=""):
    prefix="V2561_BACKUP_OVERRIDE:"
    payload=dict(meta or {})
    if legacy_note and not payload.get("legacy_note"):
        payload["legacy_note"]=str(legacy_note)
    return prefix+json.dumps(payload,ensure_ascii=False,separators=(",",":"))


def _backup_shift_hours(slot):
    return 9.0 if slot and slot.block=="FULL" else 6.0


def _backup_block_hours(block):
    return ({"AM":(8.0,14.0),"FULL":(8.0,17.0),"PM":(14.0,20.0),"NIGHT":(20.0,32.0)}.get(str(block), (8.0,14.0)))


def _preview_manual_backup_takeover(y,m,result,covered_slot,initials,exclude_backup_id=None):
    """Preview the *actual work* created if ``initials`` is called to cover this backup.

    Generator fatigue targets are warnings here. True ABSOLUTE/operational and
    statutory-style safety guardrails stay blocking: justified absence / mandatory
    post-duty rest, overlap, >12h/day, <11h daily rest, >6 workdays/7d, <35h
    continuous weekly rest, and >60h/7d. 48h remains a visible warning because the
    exact legal interpretation depends on the active work-time regime/accounting period.
    """
    people=people_for_stored_result(result,y,m)
    byinit={p.initials:p for p in people}
    p=byinit.get(str(initials))
    rows=[]; blockers=[]; warnings=[]
    if covered_slot is None or p is None:
        msg="Nerastas dublio slotas arba rezidentas."
        return {"ok":False,"blockers":[msg],"warnings":[],"rows":[],"fingerprint":""}
    if result.assignments.get(covered_slot.idx)==p.initials:
        msg="Rezidentas negali dubliuoti savo paties pamainos."
        return {"ok":False,"blockers":[msg],"warnings":[],"rows":[],"fingerprint":""}

    # ABSOLUTE no-work state remains non-overrideable.
    if absolute_unavailable_for_block(p,covered_slot.day,covered_slot.block):
        blockers.append("Šią dieną rezidentui taikomas ABSOLUTE HARD nedarbo / privalomo poilsio apribojimas.")

    # Build actual-work intervals from SYSTEM/CURRENT normal assignments plus already
    # activated/completed backup cover, then add the proposed takeover once.
    slots=make_slots(y,m)
    normal=[s for s in slots if result.assignments.get(s.idx)==p.initials]
    intervals=[]
    def add_interval(day,block,label,hours=None):
        start,end=_backup_block_hours(block)
        # NIGHT may cross midnight; ordinary current PGY1 backup slots are AM/PM.
        abs_start=(int(day)-1)*24.0+start
        abs_end=(int(day)-1)*24.0+end
        intervals.append({"day":int(day),"block":str(block),"start":abs_start,"end":abs_end,
                          "hours":float(hours if hours is not None else (end-start)),"label":label})
    for s in normal:
        add_interval(s.day,s.block,f"NORMAL {s.department}",_backup_shift_hours(s))

    # Only activated/completed backup rows count as already-realized work.
    for br in db.list_backups(y,m):
        if exclude_backup_id is not None and int(br.get("id") or -1)==int(exclude_backup_id):
            continue
        eff=str(br.get("actual_backup") or br.get("planned_backup") or "")
        if eff!=p.initials or not (br.get("activated_at") or br.get("completed_at")):
            continue
        sid=int(br.get("covered_slot") or -1)
        bs=next((s for s in slots if s.idx==sid),None)
        if bs is not None:
            add_interval(bs.day,bs.block,f"AKTYVUOTAS DUBLIS {bs.department}",_backup_shift_hours(bs))

    # Snapshot the currently-realized work before adding the proposed backup.
    base_intervals=list(intervals)

    # Proposed backup may not overlap work already known to the system.
    ps,pe=_backup_block_hours(covered_slot.block)
    pstart=(covered_slot.day-1)*24.0+ps; pend=(covered_slot.day-1)*24.0+pe
    overlaps=[x for x in intervals if max(x["start"],pstart) < min(x["end"],pend)-1e-9]
    if overlaps:
        blockers.append("Dublis persidengtų su jau esančia darbo pamaina / aktyvuotu dubliu tuo pačiu metu.")
    else:
        add_interval(covered_slot.day,covered_slot.block,f"SIŪLOMAS DUBLIS {covered_slot.department}",_backup_shift_hours(covered_slot))

    # Voluntary self-override of RESIDENT HARD is a warning, not ABSOLUTE block.
    if resident_hard_unavailable_for_block(p,covered_slot.day,covered_slot.block):
        warnings.append("Rezidentas savo noru perimtų pamainą per anksčiau pateiktą „Negaliu dirbti“ laiką.")
        rows.append({"Rodiklis":"RESIDENT HARD","Dabar":"Prašė nedirbti","Po dublio":"Dirbtų šią pamainą",
                     "Taisyklė / paaiškinimas":"Galima tik aiškiai savanoriškai patvirtinus; ORIGINAL pageidavimas istorijoje lieka.","Būsena":"PERSPĖJIMAS"})

    base_byday={}
    for x in base_intervals:
        base_byday.setdefault(x["day"],[]).append(x)
    byday={}
    for x in intervals:
        byday.setdefault(x["day"],[]).append(x)
    before_normal_hours=sum(x["hours"] for x in base_byday.get(covered_slot.day,[]))
    after_day_hours=sum(x["hours"] for x in byday.get(covered_slot.day,[]))
    if after_day_hours>12.0+1e-9:
        blockers.append(f"Po dublio būtų {after_day_hours:g} val. darbo per dieną (maksimali darbo dienos / pamainos trukmė šiame saugos profilyje: 12 val.).")
        status="BLOKUOJA"
    elif after_day_hours>=12.0-1e-9 and after_day_hours>before_normal_hours+1e-9:
        warnings.append(f"Diena taptų 12 val. darbo diena ({after_day_hours:g} val.).")
        status="PERSPĖJIMAS"
    else:
        status="GERAI"
    rows.append({"Rodiklis":f"{covered_slot.day:02d} d. darbo valandos","Dabar":f"{before_normal_hours:g} val.","Po dublio":f"{after_day_hours:g} val.",
                 "Taisyklė / paaiškinimas":"Ne daugiau kaip 12 val. per darbo dieną / pamainą.","Būsena":status})

    # Rolling 7-day hours + workday counts.
    _,ndays=calendar.monthrange(y,m)
    base_hours_by_day={d:sum(x["hours"] for x in base_byday.get(d,[])) for d in range(1,ndays+1)}
    hours_by_day={d:sum(x["hours"] for x in byday.get(d,[])) for d in range(1,ndays+1)}
    worked={d for d,h in hours_by_day.items() if h>1e-9}
    max7=0.0; max7range=(1,min(7,ndays)); maxdays=0; maxdaysrange=max7range
    before_max7=0.0
    legal_rolling_cap=min(float(rule_value("swap_max_hours_rolling7")),60.0)
    bad60=[]; bad7days=[]
    for start in range(1,max(2,ndays-6+1)):
        end=min(ndays,start+6)
        h=sum(hours_by_day.get(d,0.0) for d in range(start,end+1))
        bh=sum(base_hours_by_day.get(d,0.0) for d in range(start,end+1))
        wd=sum(1 for d in range(start,end+1) if d in worked)
        before_max7=max(before_max7,bh)
        if h>max7: max7=h; max7range=(start,end)
        if wd>maxdays: maxdays=wd; maxdaysrange=(start,end)
        if h>legal_rolling_cap+1e-9: bad60.append((start,end,h))
        if wd>6: bad7days.append((start,end,wd))
    before_max=float(before_max7)
    if bad60:
        s,e,h=bad60[0]
        blockers.append(f"Po dublio būtų {h:g} val. per 7 dienas ({s}–{e} d.; aktyvi šio swapo/dublio saugos riba: {legal_rolling_cap:g} val.).")
        hstatus="BLOKUOJA"
    elif max7>48.0+1e-9:
        warnings.append(f"Po dublio didžiausias 7 dienų krūvis būtų {max7:g} val. ({max7range[0]}–{max7range[1]} d.).")
        hstatus="PERSPĖJIMAS"
    elif max7>40.0+1e-9:
        warnings.append(f"Po dublio didžiausias 7 dienų krūvis būtų {max7:g} val.; tai viršija ~40 val. planavimo tikslą.")
        hstatus="PERSPĖJIMAS"
    else:
        hstatus="GERAI"
    rows.append({"Rodiklis":"Didžiausias krūvis per 7 d.","Dabar":f"{before_max:g} val.","Po dublio":f"{max7:g} val. ({max7range[0]}–{max7range[1]} d.)",
                 "Taisyklė / paaiškinimas":f"~40 val. yra planavimo tikslas; >48 val. rodoma kaip aiškus įspėjimas; aktyvi manual swapo/dublio riba: {legal_rolling_cap:g} val./7 d.","Būsena":hstatus})
    if bad7days:
        s,e,wd=bad7days[0]
        blockers.append(f"Po dublio būtų dirbama {wd} dienas per {s}–{e} d. laikotarpį (leidžiama ne daugiau kaip 6 darbo dienas per 7 paeiliui einančias dienas).")
        dstatus="BLOKUOJA"
    elif maxdays==6:
        warnings.append(f"Susidarytų 6 darbo dienų seka / 6 darbo dienos per 7 d. ({maxdaysrange[0]}–{maxdaysrange[1]} d.).")
        dstatus="PERSPĖJIMAS"
    else:
        dstatus="GERAI"
    rows.append({"Rodiklis":"Darbo dienos per 7 d.","Dabar":str(((result.stats or {}).get("people",{}).get(p.initials,{}) or {}).get("max_consecutive_days",0) or 0),
                 "Po dublio":f"iki {maxdays} d. ({maxdaysrange[0]}–{maxdaysrange[1]} d.)",
                 "Taisyklė / paaiškinimas":"Ne daugiau kaip 6 darbo dienos per 7 paeiliui einančias dienas.","Būsena":dstatus})

    # Daily rest: only between separate calendar workdays; same-day AM+PM is one 12h day.
    intervals_sorted=sorted(intervals,key=lambda x:(x["start"],x["end"]))
    min_rest=999.0; min_pair=None
    for a,b in zip(intervals_sorted,intervals_sorted[1:]):
        if a["day"]==b["day"]:
            continue
        gap=b["start"]-a["end"]
        if gap<min_rest:
            min_rest=gap; min_pair=(a,b)
    if min_pair is not None and min_rest<11.0-1e-9:
        blockers.append(f"Tarp pamainų liktų tik {min_rest:g} val. poilsio (minimalus nepertraukiamas paros poilsis: 11 val.).")
        rstatus="BLOKUOJA"
    else:
        rstatus="GERAI"
    rows.append({"Rodiklis":"Trumpiausias poilsis tarp darbo dienų","Dabar":"—","Po dublio":("—" if min_pair is None else f"{min_rest:g} val."),
                 "Taisyklė / paaiškinimas":"Minimalus nepertraukiamas paros poilsis: 11 val.","Būsena":rstatus})

    # Weekly-rest legal note: with the current AM/PM model, the tool enforces the
    # operational proxy of no more than 6 workdays in any 7 plus >=11h daily rest.
    # The exact 35h statutory weekly-rest interpretation can depend on the active
    # work-time regime / accounting period and remains an employer-level legal check.

    # Fatigue patterns are warnings if the true safety blockers above remain satisfied.
    double_days=sorted(d for d,h in hours_by_day.items() if h>=12.0-1e-9)
    if covered_slot.day in double_days:
        if covered_slot.day-1 in double_days or covered_slot.day+1 in double_days:
            warnings.append("Dublis sudarytų dviejų 12 val. darbo dienų seką; generatorius to vengia, bet savanoriškai galima patvirtinti, jei absoliučios ribos išlaikytos.")
        if covered_slot.day-1 in double_days and covered_slot.day-2 in double_days:
            warnings.append("Tai būtų darbo diena po dviejų 12 val. dienų iš eilės; rodoma kaip nuovargio perspėjimas.")

    ok=not blockers
    fp_raw="|".join([p.initials,str(covered_slot.idx)]+sorted(blockers)+sorted(warnings)+[str(r) for r in rows])
    fp=hashlib.sha256(fp_raw.encode("utf-8")).hexdigest()[:16]
    return {"ok":ok,"blockers":blockers,"warnings":warnings,"rows":rows,"fingerprint":fp,
            "max_rolling7_hours":round(max7,1),"day_hours":round(after_day_hours,1),"max_workdays7":int(maxdays)}

def _operational_repair_validation(y,m,result,new_assignments):
    """Validate an emergency/admin repair without rewriting the published fairness baseline.

    Publication-time workload targets, Onko pair-evenness and weekend uniqueness are planning
    constraints. They must not prevent a justified post-publication repair. Safety, coverage,
    overlap, HARD unavailability, rest and known-hours rules remain enforced.
    """
    people=people_for_stored_result(result,y,m)
    slots=make_slots(y,m)
    # V2.5.85: use the published SYSTEM targets as the immutable workload-credit
    # ledger. Emergency Rescue changes placement only; no target units move.
    stats=validate_schedule(
        y,m,people,slots,new_assignments,result.targets,
        satisfaction_people=people,
        backup_assignments=(result.backup_snapshot or []),
        validation_mode="emergency_rescue",
    )
    errs=list(stats.get("global",{}).get("errors",[]))
    planning_only=[]; blocking=[]
    for e in errs:
        # Emergency post-publication repairs are allowed to create a new OPTIONAL
        # gap when a lower-priority resident is pulled into a mandatory SPS slot.
        # The published SYSTEM gap pattern / fairness baseline stays frozen; only
        # ABSOLUTE safety, mandatory coverage, overlap and operational feasibility
        # remain blocking here.
        gap_planning_only=(
            e.startswith("Gap dispersion violated")
            or e.startswith("Gap workplace dispersion violated")
            or e.startswith("Gap-day dispersion pattern outdated")
        )
        if (
            e.endswith("odd Onko count")
            or (e.startswith("Weekend ") and (
                "must have exactly 4 different people" in e
                or "resident weekend cap exceeded" in e
            ))
            or gap_planning_only
        ):
            planning_only.append(e)
        else:
            blocking.append(e)
    stats.setdefault("global",{})["planning_exceptions_after_publication"]=planning_only
    stats["global"]["errors"]=blocking
    stats["global"]["hard_errors"]=len(blocking)
    return stats


def _repair_candidate_check(y,m,result,slot_id,replacement,source_slot_id=None):
    """Validate one post-publication repair candidate.

    V2.5.56 supports a critical-cover *transfer*: for SPS RO / SPS UG, a resident
    already working an overlapping lower-priority optional post may be moved into
    the critical slot and the optional source slot is intentionally vacated.
    """
    slots={s.idx:s for s in make_slots(y,m)}
    target=slots.get(int(slot_id))
    if target is None or int(slot_id) not in result.assignments:
        return False,"Pamaina neužpildyta.",None
    if result.assignments[int(slot_id)]==replacement:
        return False,"Tas pats rezidentas jau paskirtas.",None
    source=None
    if source_slot_id is not None:
        source=slots.get(int(source_slot_id))
        if source is None:
            return False,"Nerasta donorinė neprivaloma pamaina.",None
    try:
        fresh_assign=(
            apply_emergency_critical_transfer(result.assignments,target,replacement,source)
            if is_emergency_critical_slot(target)
            else dict(result.assignments)
        )
        if not is_emergency_critical_slot(target):
            if source is not None:
                return False,"Donorinis perkėlimas taikomas tik kritiniam SPS postui.",None
            fresh_assign[int(slot_id)]=replacement
    except Exception as exc:
        return False,str(exc),None
    stats=_operational_repair_validation(y,m,result,fresh_assign)
    errs=stats.get("global",{}).get("errors",[])
    return (not errs, "" if not errs else errs[0], stats)


def _critical_repair_candidate_rows(y,m,result,target_slot,repair_load):
    """Rank critical-cover candidates using the V2.5.56 rescue hierarchy.

    1) same-block residents are pulled from lower-priority OPTIONAL posts;
    2) only if no such ABSOLUTE-safe transfer exists do we expose residents who
       are free in that block as fallback cover.
    Within a tier, reject any new Resident-HARD conflict during SYSTEM generation. V2.5.57 deliberately does NOT
    rank same-block pull-down donors by post spread or future catch-up: they were already
    scheduled to work that block, so changing station for emergency coverage is
    fairness-neutral and must not create a new structural fairness burden.
    """
    from_person=result.assignments.get(target_slot.idx)
    base_rh=int((result.stats or {}).get("global",{}).get("resident_hard_total_losses",0) or 0)
    slots=make_slots(y,m)
    pull_rows=[]; free_rows=[]
    for prow in DEFAULT_PEOPLE:
        cand=prow["initials"]
        if cand==from_person:
            continue
        sources=emergency_donor_source_slots(slots,result.assignments,target_slot,cand)
        source_options=sources or [None]
        for source in source_options:
            # If the resident is already working an overlapping non-donor post,
            # this is not a free fallback and must not create an overlap. Validation
            # below will reject it.
            ok,why,cstats=_repair_candidate_check(
                y,m,result,target_slot.idx,cand,(source.idx if source else None)
            )
            if not ok:
                continue
            cg=(cstats or {}).get("global",{})
            row={
                "initials":cand,
                "source_slot":(source.idx if source else None),
                "source_department":(source.department if source else ""),
                "source_block":(source.block if source else ""),
                "mode":"PULL_OPTIONAL" if source else "FREE_FALLBACK",
                "rh_total":int(cg.get("resident_hard_total_losses",0) or 0),
                "rh_delta":int(cg.get("resident_hard_total_losses",0) or 0)-base_rh,
                "rh_max":int(cg.get("resident_hard_max_loss_per_resident",0) or 0),
                "rh_cum_spread":int(cg.get("resident_hard_cumulative_spread",0) or 0),
                "stats":cstats,
            }
            (pull_rows if source else free_rows).append(row)
    rows=pull_rows if pull_rows else free_rows
    zero_rh=[r for r in rows if r["rh_delta"]<=0]
    rows=zero_rh or rows
    return sorted(rows,key=lambda r:(
        r["rh_total"],r["rh_max"],r["rh_cum_spread"],r["initials"]
    ))


def plan_backups(y,m,result):
    """Build the theoretical backup layer.

    From Oct-2026: weekend FCFS claims follow the active duty catalog (one 12 h
    position per weekend day). They are a separate theoretical layer and never
    influence normal-schedule feasibility or preference scoring. Historical months
    keep the legacy auto-waterfill planner for reproducibility.
    """
    if weekend_fcfs_backup_mode(y,m):
        slots={s.idx:s for s in weekend_fcfs_backup_slots(y,m)}
        claims=sorted(db.list_backup_claims(y,m),key=lambda r:(r.get("claimed_at") or "",int(r.get("covered_slot") or 0)))
        desired=[]; errors=[]; seen_people=set(); seen_slots=set()
        for r in claims:
            sid=int(r.get("covered_slot") or 0); sl=slots.get(sid); ini=str(r.get("initials") or "")
            if not sl:
                errors.append({"initials":ini,"covered_slot":sid,"reason":"FCFS dublis is outside the active weekend catalog"})
                continue
            if ini in seen_people or sid in seen_slots:
                errors.append({"initials":ini,"covered_slot":sid,"reason":"duplicate FCFS claim"})
                continue
            seen_people.add(ini); seen_slots.add(sid)
            desired.append({
                "covered_slot":sid,
                "covered_person":result.assignments.get(sid),
                "day":sl.day,"block":sl.block,"department":sl.department,
                "planned_backup":ini,"actual_backup":None,
                "resident_hard_relaxed":False,
                "coverage_priority":"weekend_fcfs_theoretical",
                "note":"FCFS WEEKEND THEORETICAL",
            })
        required=len(slots)
        if len(desired)!=required:
            errors.append({
                "reason":f"FCFS weekend dubliai incomplete: {len(desired)}/{required} selected",
                "selected":len(desired),"required":required,
            })
        return desired,errors

    people=people_for_stored_result(result,y,m)
    initials=[p.initials for p in people]
    claims=db.list_backup_claims(y,m)
    claim_by_slot={int(r["covered_slot"]):r for r in claims}
    backup_load={i:0 for i in initials}; pair_load={}; same_time_load={}
    desired=[]; errors=[]; slots=make_slots(y,m)
    required=sorted(
        [sl for sl in slots if backup_required_slot(sl) and result.assignments.get(sl.idx)],
        key=lambda sl:(sl.day,{"AM":0,"FULL":1,"PM":2}.get(sl.block,9),sl.idx)
    )
    best_effort=sorted(
        [sl for sl in slots if backup_best_effort_slot(sl) and result.assignments.get(sl.idx) and sl not in required],
        key=lambda sl:(sl.day,{"AM":0,"FULL":1,"PM":2}.get(sl.block,9),sl.idx)
    )

    def assign_one(sl,is_required,optional_ceiling=None):
        covered=result.assignments.get(sl.idx)
        strict=list(_eligible_backup_candidates(y,m,result,sl,people,allow_resident_hard=False))
        if not strict:
            if is_required:
                errors.append({
                    "day":sl.day,"shift":block_label(sl.block),"department":sl.department,
                    "covered_person":covered,"covered_slot":sl.idx,
                    "reason":"no strict-eligible backup without mandatory-unavailability / overlap violation",
                })
            return False
        # Prefer a different person for simultaneous cover whenever possible.
        fresh=[b for b in strict if same_time_load.get((sl.day,sl.block,b),0)==0]
        eligible=fresh or strict
        claimed=(claim_by_slot.get(sl.idx) or {}).get("initials")
        def rank(b):
            return (
                backup_load.get(b,0),
                same_time_load.get((sl.day,sl.block,b),0),
                pair_load.get((b,covered),0),
                0 if claimed==b else 1,   # claim = tie-break, never fairness override
                _stable_rank(y,m,sl.day,sl.block,sl.idx,b,covered),
            )
        backup=min(eligible,key=rank)
        if optional_ceiling is not None and backup_load.get(backup,0)>=int(optional_ceiling):
            return False
        desired.append({
            "covered_slot":sl.idx,"covered_person":covered,"day":sl.day,"block":sl.block,
            "department":sl.department,"planned_backup":backup,"actual_backup":None,
            "resident_hard_relaxed":False,
            "claim_overridden_by_higher_priority":bool(claimed and claimed!=backup),
            "coverage_priority":"required" if is_required else "best_effort_fairness_filler",
            "note":"AUTO SYSTEM WATERFILL",
        })
        same_time_load[(sl.day,sl.block,backup)]=same_time_load.get((sl.day,sl.block,backup),0)+1
        backup_load[backup]=backup_load.get(backup,0)+1
        pair_load[(backup,covered)]=pair_load.get((backup,covered),0)+1
        return True

    # Phase 1: all important positions must have a named backup.
    for sl in required:
        assign_one(sl,True)

    # Phase 2: use CENTRO RO only as a low-load lift. Freeze the highest burden
    # created by required cover and do not let optional duties push anyone above it.
    required_ceiling=max(backup_load.values()) if backup_load else 0
    for sl in best_effort:
        assign_one(sl,False,optional_ceiling=required_ceiling)

    return desired,errors


def sync_backup_plan(y,m,result):
    desired,errors=plan_backups(y,m,result)
    db.sync_backups(y,m,desired)
    return desired,errors


def _backup_rows_for_result(y,m,result=None,override=None):
    """Return the operational backup rows, falling back to the generated draft snapshot.

    Before SYSTEM publication the database intentionally has no backup_assignments rows.
    V2.5.112 therefore treats result.backup_snapshot as the authoritative draft-time
    plan so Summary / Excel / personal grafikas do not incorrectly show zero backups.
    """
    if override is not None:
        return [dict(x) for x in override]
    try:
        rows=db.list_backups(y,m)
    except Exception:
        rows=[]
    if rows:
        return [dict(x) for x in rows]
    snap=list(getattr(result,"backup_snapshot",None) or []) if result is not None else []
    return [dict(x) for x in snap]


def backup_counts(y,m,result=None):
    planned={p["initials"]:0 for p in DEFAULT_PEOPLE}
    effective={p["initials"]:0 for p in DEFAULT_PEOPLE}
    for r in _backup_rows_for_result(y,m,result):
        pb=r.get("planned_backup")
        if not pb:
            continue
        planned[pb]=planned.get(pb,0)+1
        eff=r.get("actual_backup") or pb
        effective[eff]=effective.get(eff,0)+1
    return planned,effective


def display_rotation_categories(y,m):
    """Return only workplace categories that actually exist in this month's visible cohort model.

    This prevents retired/future post columns from appearing as misleading all-zero columns
    (e.g. legacy Onko RO in Oct-2026+, or Onko/TBL before Oct-2026).
    """
    active=set()
    for s in make_slots(y,m):
        if s.blocked or not slot_visible_in_schedule(s,y,m):
            continue
        cat=rotation_category(s)
        if cat in ROTATION_CATEGORIES:
            active.add(cat)
    return [cat for cat in ROTATION_CATEGORIES if cat in active]


def summary_df(result,y,m):
    planned,effective=backup_counts(y,m,result); rows=[]
    for i,d in result.stats.get("people",{}).items():
        row={
            tr("person"):i,tr("name"):d.get("name",""),tr("target"):d.get("target"),
            tr("workload"):d.get("workload_credit",d.get("workload")),
            tr("weekday_assignments"):d.get("weekday_assignments"),
            tr("weekday_days"):d.get("weekday_days"),
            tr("weekend_assignments"):d.get("weekend_assignments"),
            tr("saturday_assignments"):d.get("saturdays"),
            tr("sunday_assignments"):d.get("sundays"),
            tr("prior_weekends"):d.get("prior_weekend_count"),
            ("Šventės" if lang=="LT" else "Holidays"):d.get("holiday_assignments",0),
            ("Ankstesnės šventės" if lang=="LT" else "Prior holidays"):d.get("prior_holiday_count",0),
            tr("cumulative_weekends"):d.get("cumulative_weekend_count"),
            tr("fridays"):d.get("friday_assignments"),
            tr("double_shifts"):d.get("doubles"),
            tr("max_consecutive"):d.get("max_consecutive_days"),
            tr("max_rolling7_hours"):d.get("max_rolling7_hours"),
            tr("max_calendar_week_hours"):d.get("max_calendar_week_hours"),
            tr("free_days"):d.get("fully_free_days"),
            ("Skirtingos darbo vietos" if lang=="LT" else "Distinct workplaces"):d.get("distinct_rotations"),
            tr("preference_score"):d.get("preference_score"),
            tr("planned_backups"):planned.get(i,0),
            tr("effective_backups"):effective.get(i,0),
        }
        if d.get("workload_credit_policy")=="FROZEN_SYSTEM_LEDGER":
            row[("ACTUAL slotų svoris (ne target)" if lang=="LT" else "ACTUAL placement workload (not target)")]=d.get("actual_assignment_workload",d.get("workload"))
        # V2.5.15: exact monthly number of assignments in every workplace.
        rotation_counts=d.get("rotation_counts") or {}
        for cat in display_rotation_categories(y,m):
            row[cat]=int(rotation_counts.get(cat,0) or 0)
        # V2.5.159 dedicated Onko cycle ledger in Suvestinė. This makes the
        # carry-in and post-month cumulative position visible instead of hiding
        # the longitudinal rule inside the solver.
        _onko_cat=("Onko/TBL" if cohort_october_model(y,m) else "Onko RO")
        _prior_onko=int((d.get("prior_rotation_counts") or {}).get(_onko_cat,0) or 0)
        _month_onko=int(rotation_counts.get(_onko_cat,0) or 0)
        row[("Onko iki mėnesio" if lang=="LT" else "Onko before month")]=_prior_onko
        row[("Onko šį mėnesį" if lang=="LT" else "Onko this month")]=_month_onko
        row[("Onko ciklas iš viso" if lang=="LT" else "Onko cycle total")]=_prior_onko+_month_onko
        rows.append(row)
    return pd.DataFrame(rows)


def preference_scores_df(result):
    return pd.DataFrame([
        {
            tr("person"):i,
            tr("name"):d.get("name",""),
            ("RESIDENT HARD %" if lang=="LT" else "RESIDENT HARD %"):d.get("resident_hard_score"),
            ("SOFT %" if lang=="LT" else "SOFT %"):d.get("soft_preference_score"),
            tr("preference_score"):d.get("preference_score"),
            ("RESIDENT HARD pažeidimai" if lang=="LT" else "RESIDENT HARD violations"):d.get("resident_hard_losses",0),
        }
        for i,d in result.stats.get("people",{}).items()
    ])


def _is_actual_wish_row(r):
    """Only concrete resident wishes belong in wish-satisfaction statistics.

    Account work-style settings, backup commitments and credit redemptions are
    operational/scheduling inputs and must never inflate or reduce wish %.
    """
    if not bool((r or {}).get("included_in_score")):
        return False
    kind=str((r or {}).get("kind") or "")
    source=str((r or {}).get("source") or "")
    if source=="account_settings":
        return False
    if kind in {"weekday_preference","weekend_preference","spread_preference",
                "shift_length_preference","avoid_doubles","holiday_preference",
                "backup_claim","rest_credit"}:
        return False
    return kind in {"resident_hard","soft_free","preferred"}


def resident_wishes_audit_df(result):
    """Senior-facing pre-publication request audit for every resident.

    Uses the CURRENT candidate's own validated request ledger, so the senior can
    inspect exactly what the generated DRAFT would satisfy before publication.
    """
    rows=[]
    for initials,d in (result.stats.get("people",{}) or {}).items():
        details=list(d.get("request_detail_rows") or [])
        included=[r for r in details if _is_actual_wish_row(r)]
        preferred=[r for r in included if r.get("kind")=="preferred"]
        soft_free=[r for r in included if r.get("kind")=="soft_free"]
        missed=[r for r in included if not r.get("fulfilled")]
        components=d.get("preference_components") or {}
        rotation_counts=d.get("rotation_counts") or {}
        theoretical_backup_count=sum(
            1 for br in (getattr(result,"backup_snapshot",None) or [])
            if str(br.get("actual_backup") or br.get("planned_backup") or "")==initials
        )

        def ratio(items):
            if not items:
                return "—"
            return f"{sum(1 for r in items if r.get('fulfilled'))}/{len(items)}"

        hard_req=int(d.get("resident_hard_requested",0) or 0)
        hard_ok=int(d.get("resident_hard_honored",0) or 0)
        hard_txt=(f"{hard_ok}/{hard_req}" if hard_req else "—")
        missed_preview=[]
        for r in missed[:3]:
            missed_preview.append(f"{r.get('date','—')} {r.get('block','—')} · {r.get('type','—')}")
        if len(missed)>3:
            missed_preview.append(f"+{len(missed)-3}")

        overall=d.get("overall_request_score")
        soft_score=d.get("soft_preference_score")
        rows.append({
            ("Žmogus" if lang=="LT" else "Person"):initials,
            ("Vardas" if lang=="LT" else "Name"):d.get("name",""),
            ("Target" if lang=="LT" else "Target"):d.get("target"),
            ("Krūvis" if lang=="LT" else "Workload"):d.get("workload_credit",d.get("workload")),
            ("RESIDENT HARD" if lang=="LT" else "RESIDENT HARD"):hard_txt,
            ("Noriu laisvos" if lang=="LT" else "Requested off"):ratio(soft_free),
            ("Pageidauju dirbti" if lang=="LT" else "Prefer to work"):ratio(preferred),
            ("SOFT %" if lang=="LT" else "SOFT %"):("—" if soft_score is None else soft_score),
            ("Bendras išpildymas %" if lang=="LT" else "Overall satisfaction %"):("—" if overall is None else overall),
            ("Šeštadieniai" if lang=="LT" else "Saturdays"):int(d.get("saturdays",0) or 0),
            ("Sekmadieniai" if lang=="LT" else "Sundays"):int(d.get("sundays",0) or 0),
            ("12h dienos (AM+PM)" if lang=="LT" else "12h workdays (AM+PM)"):int(d.get("doubles",0) or 0),
            (("Teoriniai savaitgalio dubliai" if lang=="LT" else "Theoretical weekend backups") if weekend_fcfs_backup_mode(year,month) else ("Teoriniai AUTO dubliai" if lang=="LT" else "Theoretical AUTO backups")):int(theoretical_backup_count),
            (("Onko/TBL" if cohort_october_model(year,month) else "Onko RO")):int(rotation_counts.get(("Onko/TBL" if cohort_october_model(year,month) else "Onko RO"),0) or 0),
            "SPS RO":int(rotation_counts.get("SPS RO",0) or 0),
            "SPS UG":int(rotation_counts.get("SPS UG",0) or 0),
            ("Neįvykdyta" if lang=="LT" else "Missed"):len(missed),
            ("Neįvykdytų santrauka" if lang=="LT" else "Missed summary"):"; ".join(missed_preview) if missed_preview else "—",
            "__hard_losses":int(d.get("resident_hard_losses",0) or 0),
            "__score_sort":101.0 if overall is None else float(overall),
        })
    if not rows:
        return pd.DataFrame()
    rows.sort(key=lambda r:(-r["__hard_losses"], r["__score_sort"], -r[("Neįvykdyta" if lang=="LT" else "Missed")], r[("Žmogus" if lang=="LT" else "Person")]))
    for r in rows:
        r.pop("__hard_losses",None); r.pop("__score_sort",None)
    return pd.DataFrame(rows)



def generation_wish_summary(result):
    """Return explicit all-resident wish totals + a flat table of misses."""
    total=honored=missed=0
    hard_total=hard_missed=0
    rows=[]
    for initials,d in (result.stats.get("people",{}) or {}).items():
        details=[r for r in (d.get("request_detail_rows") or []) if _is_actual_wish_row(r)]
        for r in details:
            total+=1
            ok=bool(r.get("fulfilled"))
            honored+=int(ok); missed+=int(not ok)
            if r.get("kind")=="resident_hard":
                hard_total+=1; hard_missed+=int(not ok)
            if ok:
                continue
            base=request_details_df([r],initials)
            if base.empty:
                continue
            rec=base.iloc[0].to_dict()
            rec={(("Žmogus" if lang=="LT" else "Person")):initials,
                 (("Vardas" if lang=="LT" else "Name")):d.get("name","")} | rec
            rows.append(rec)
    return {
        "total":int(total),"honored":int(honored),"missed":int(missed),
        "hard_total":int(hard_total),"hard_missed":int(hard_missed),
        "table":pd.DataFrame(rows),
    }




def stamp_generation_provenance(result, source="generate"):
    """Stamp a newly verified SYSTEM candidate with immutable release provenance.

    V2.5.150 makes the generating app/engine explicit so a future release can tell
    a genuinely current draft from a legacy row that merely still exists in DB.
    """
    if result is None:
        return result
    now=datetime.now(timezone.utc).isoformat()
    previous=dict(getattr(result,"provenance",None) or {})
    previous.update({
        "app_version":APP_VERSION,
        "engine_api_version":str(ENGINE_API_VERSION),
        "draft_compatibility_version":DRAFT_COMPATIBILITY_VERSION,
        "generated_at_utc":now,
        "generation_source":str(source or "generate"),
    })
    result.provenance=previous
    g=(result.stats or {}).setdefault("global",{})
    g["generated_by_app_version"]=APP_VERSION
    g["generated_by_engine_api_version"]=str(ENGINE_API_VERSION)
    g["draft_compatibility_version"]=DRAFT_COMPATIBILITY_VERSION
    g["generated_at_utc"]=now
    g["generation_source"]=str(source or "generate")
    return result


def draft_compatibility_status(payload, y, m):
    """Fail-closed CURRENT-engine assessment of a stored draft.

    A DB row existing is not the same thing as a publishable draft.  We revalidate
    assignments against the current engine and also require the frozen request/target
    snapshot to still match today's inputs.  Invalid/outdated rows remain available
    for audit, but they are never a quality baseline and never enable publication.
    """
    info={
        "exists":bool(payload),"publishable":False,"valid_for_improve":False,
        "kind":"missing","hard_errors":None,"hard_missed":None,"outdated_inputs":False,
        "result":None,"rows":[],"provenance":{},"stored_engine":None,"stored_solve_stage":None,
        "error":None,
    }
    if not payload:
        return info
    try:
        stored=deserialize_result(payload)
        provenance=dict(getattr(stored,"provenance",None) or {})
        info["provenance"]=provenance
        info["stored_engine"]=(
            provenance.get("engine_api_version")
            or provenance.get("stored_engine_api_version")
            or payload.get("engine_api_version")
            or provenance.get("stored_engine_stats_version")
            or payload.get("engine_stats_version")
            or "LEGACY / UNKNOWN"
        )
        info["stored_solve_stage"]=((stored.stats or {}).get("global",{}) or {}).get("solve_stage")
        current_people=load_people(y,m)
        expected_targets=calculate_targets(y,m,current_people)
        current_snapshot=serialize_people_request_snapshot(current_people)
        snapshot_matches=(
            expected_targets==stored.targets
            and (not stored.request_snapshot or current_snapshot==stored.request_snapshot)
        )
        info["outdated_inputs"]=not snapshot_matches
        refreshed=revalidate_loaded_result(
            y,m,people_for_stored_result(stored,y,m),stored,
            backup_assignments=[],validation_mode="generation",
        )
        info["result"]=refreshed
        g=((refreshed.stats or {}).get("global",{}) or {})
        hard=int(g.get("hard_errors",9999) or 0)
        wishes=generation_wish_summary(refreshed)
        hard_missed=int(wishes.get("hard_missed",0) or 0)
        info["hard_errors"]=hard
        info["hard_missed"]=hard_missed
        info["rows"]=list(g.get("errors") or [])
        zero_hard=(hard==0 and hard_missed==0 and bool(refreshed.ok))
        if not zero_hard:
            info["kind"]="invalid_current_engine"
        elif not snapshot_matches:
            info["kind"]="outdated_inputs"
        else:
            current_provenance=(
                str(provenance.get("draft_compatibility_version") or "")==DRAFT_COMPATIBILITY_VERSION
                and str(provenance.get("engine_api_version") or "")==str(ENGINE_API_VERSION)
            )
            info["kind"]="valid_current" if current_provenance else "valid_legacy_provenance"
            info["publishable"]=True
            info["valid_for_improve"]=True
        return info
    except Exception as exc:
        info["kind"]="unreadable"
        info["error"]=str(exc)
        return info


def render_invalid_draft_guard(health, *, compact=False):
    """Visible fail-closed warning for legacy/outdated draft rows."""
    if not health or not health.get("exists") or health.get("publishable"):
        return
    hard=health.get("hard_errors")
    hard_missed=health.get("hard_missed")
    engine=health.get("stored_engine") or "LEGACY / UNKNOWN"
    stage=health.get("stored_solve_stage") or "—"
    if lang=="LT":
        if health.get("kind")=="outdated_inputs":
            msg=("NEGALIOJANTIS / PASENĘS JUODRAŠTIS — SKELBTI NEGALIMA. Po jo sugeneravimo pasikeitė "
                 "rezidentų inputai arba darbo targetai. Jis paliktas tik auditui; GENERUOTI / PERKURTI turi sukurti naują 0-HARD kandidatą.")
        elif health.get("kind")=="unreadable":
            msg="NEGALIOJANTIS JUODRAŠTIS — dabartinis engine negali jo saugiai perskaityti / patikrinti. Skelbimas ir gerinimas užblokuoti."
        else:
            msg=(f"LEGACY / INVALID DRAFT — SKELBTI NEGALIMA. Dabartinis engine rado {hard if hard is not None else '—'} "
                 f"privalomų taisyklių klaidų ir {hard_missed if hard_missed is not None else '—'} „Negaliu dirbti“ pažeidimų. "
                 "Šis DB įrašas paliktas tik istorinei peržiūrai ir NEGALI būti naudojamas kaip GERINTI bazė.")
        st.error(msg)
        if not compact:
            st.caption(f"Stored engine: {engine} · solve stage: {stage} · current engine: {ENGINE_API_VERSION}")
    else:
        if health.get("kind")=="outdated_inputs":
            msg=("INVALID / OUTDATED DRAFT — PUBLICATION BLOCKED. Resident inputs or workload targets changed after generation. "
                 "The row is retained for audit only; GENERATE / REBUILD must create a new zero-HARD candidate.")
        elif health.get("kind")=="unreadable":
            msg="INVALID DRAFT — the current engine cannot safely read/revalidate it. Publication and improvement are blocked."
        else:
            msg=(f"LEGACY / INVALID DRAFT — PUBLICATION BLOCKED. Current engine found {hard if hard is not None else '—'} HARD errors "
                 f"and {hard_missed if hard_missed is not None else '—'} Cannot-work violations. The row is audit-only and cannot be an improvement baseline.")
        st.error(msg)
        if not compact:
            st.caption(f"Stored engine: {engine} · solve stage: {stage} · current engine: {ENGINE_API_VERSION}")
    if (not compact) and health.get("rows"):
        with st.expander("Dabartinio engine HARD klaidos" if lang=="LT" else "Current-engine HARD errors",expanded=False):
            st.dataframe(pd.DataFrame(health["rows"]),use_container_width=True,hide_index=True)


def resident_group_satisfaction_df(result):
    """Privacy-safe group view for ordinary residents.

    Only initials, name and overall fulfillment percentage are exposed.
    Peer HARD/SOFT counts, request dates/blocks, workstyle details, missed counts
    and request-level rows are deliberately not serialized to the resident UI.
    """
    rows=[]
    for initials,d in (result.stats.get("people",{}) or {}).items():
        overall=d.get("overall_request_score")
        rows.append({
            ("Žmogus" if lang=="LT" else "Person"):initials,
            ("Vardas" if lang=="LT" else "Name"):d.get("name",""),
            ("Bendras išpildymas %" if lang=="LT" else "Overall satisfaction %"):(
                "—" if overall is None else overall
            ),
        })
    return pd.DataFrame(rows)


def render_resident_wishes_audit(
    result, *, draft_mode=False, key_suffix="", senior_view=False
):
    """Role-aware request audit.

    Senior: full all-resident category + request-level audit.
    Resident: only group overall satisfaction percentages.
    """
    if senior_view:
        if draft_mode:
            st.markdown("### JUODRAŠČIO PAGEIDAVIMŲ AUDITAS" if lang=="LT" else "### DRAFT REQUEST AUDIT")
            st.caption(
                "Tai yra būtent dabar sugeneruoto JUODRAŠČIO rezultatas. Seniūnė gali įvertinti, ar pageidavimai maksimaliai išpildyti, prieš paspausdama PASKELBTI / PATVIRTINTI. Regeneravus lentelė persiskaičiuos iš naujo."
                if lang=="LT" else
                "This is the currently generated DRAFT. The senior can inspect whether requests are maximized before pressing PUBLISH / CONFIRM. Regeneration recalculates this table."
            )
        else:
            st.markdown("### Pradinio grafiko pageidavimų auditas" if lang=="LT" else "### SYSTEM request audit")
            st.caption(
                "Ši lentelė rodo publikavimo momento pradinio grafiko rezultatą ir tik konkrečius tuo metu pateiktus rezidentų pageidavimus. "
                "Nustatymuose pasirinktas darbo režimas (pvz., 6 h / 12 h) čia neskaičiuojamas kaip pageidavimas ir į procentą neįeina."
                if lang=="LT" else
                "This table shows the publication-time initial schedule result and only concrete resident wishes submitted for that run. "
                "Account work-style settings (for example 6 h / 12 h) are not wishes and are excluded from the percentage."
            )

        st.info(
            "V2.5.115: DUBLIAI = ATSKIRAS TEORINIS STANDBY SLUOKSNIS. Planuotas ar tik aktyvuotas dublis NĖRA darbo pamaina ir NIEKADA nemažina „Noriu laisvos“, „Negaliu dirbti“ ar kitų SYSTEM pageidavimų score. Tik COMPLETED realus pavadavimas gali atsirasti ACTUAL darbo audite."
            if lang=="LT" else
            "V2.5.115: BACKUPS are a separate theoretical standby layer. A planned or merely activated backup is NOT a work shift and NEVER reduces SYSTEM request satisfaction. Only a COMPLETED real-life cover may appear in ACTUAL work audit."
        )
        audit_df=resident_wishes_audit_df(result)
        if audit_df.empty:
            st.caption("Nėra rezidentų audito duomenų." if lang=="LT" else "No resident audit data.")
            return
        st.dataframe(audit_df,use_container_width=True,hide_index=True,height=610)

        people=list((result.stats.get("people",{}) or {}).keys())
        if not people:
            return
        selected=st.selectbox(
            "Detaliai patikrinti rezidentą" if lang=="LT" else "Inspect resident in detail",
            people,
            key=f"summary_request_person_{key_suffix}",
        )
        pdict=(result.stats.get("people",{}).get(selected,{}) or {})
        misses=list(pdict.get("unhonored_request_details") or [])
        if misses:
            st.markdown("#### Ko nepavyko išpildyti" if lang=="LT" else "#### What could not be honored")
            render_missed_requests_scandi(misses,selected,key_suffix=f"senior_{key_suffix}_{selected}")
        else:
            st.success(
                "Šiam rezidentui į score įtrauktų neįvykdytų prašymų nėra."
                if lang=="LT" else
                "This resident has no scored missed requests."
            )
        with st.expander(
            "Rodyti įvykdytus prašymus" if lang=="LT" else "Show honored requests",
            expanded=False
        ):
            honored=list(pdict.get("honored_request_details") or [])
            if honored:
                st.dataframe(
                    request_details_df(honored,selected),
                    use_container_width=True,hide_index=True
                )
            else:
                st.caption(
                    "Nėra score įtrauktų struktūruotų prašymų."
                    if lang=="LT" else
                    "No scored structured requests."
                )
        return

    # Resident profile: privacy-safe group view only.
    st.markdown(
        "### Grupės pageidavimų išpildymas"
        if lang=="LT" else
        "### Group request satisfaction"
    )
    st.caption(
        "Privatumo sumetimais čia rodoma tik kiekvieno rezidento bendra pageidavimų išpildymo procentinė reikšmė. Kitų rezidentų pageidavimų detalės, datos ir konkretūs prašymai nėra rodomi. Savo detalų auditą matai savo asmeninėje patikroje."
        if lang=="LT" else
        "For confidentiality, this table shows only each resident's overall request-satisfaction percentage. Other residents' request details, dates and individual requests are not shown. Your own detailed audit remains available in your personal proof view."
    )
    safe_df=resident_group_satisfaction_df(result)
    if safe_df.empty:
        st.caption("Nėra grupės statistikos." if lang=="LT" else "No group statistics.")
        return
    st.dataframe(safe_df,use_container_width=True,hide_index=True,height=610)



def _plain_request_sentence(r, initials=""):
    """Human-readable single-sentence explanation of one request result.

    V2.5.60 deliberately avoids the unexplained English word ``claim`` in the
    resident/senior UI.  The sentence states: what was requested, what the
    SYSTEM/ACTUAL grafikas actually contains, and why the request is counted as
    honored or missed.
    """
    typ=str(r.get("type") or "Pageidavimas")
    date_txt=str(r.get("date") or "—")
    block=str(r.get("block") or "FULL")
    station=str(r.get("station") or "—")
    fulfilled=bool(r.get("fulfilled"))
    who=(f"{initials}: " if initials else "")
    if lang=="LT":
        if r.get("kind") in ("shift_length_preference","avoid_doubles") and r.get("workstyle_proof"):
            wp=r.get("workstyle_proof") or {}
            mode=int(wp.get("mode") or 0)
            if mode==3:
                threshold=int(wp.get("fulfilled_threshold_min") or 0)
                cohort=int(wp.get("prefer12_cohort_size") or 0)
                return (
                    f"{who}SYSTEM generavimo metu buvo užšaldytas pageidavimas „prefer 12 h“. "
                    f"Grafike skirta {int(wp.get('double_days') or 0)} 12 h dienų ir "
                    f"{int(wp.get('single_days') or 0)} 6 h dienų; Onko 9 h dienų — {int(wp.get('onko_9h_days') or 0)}. "
                    f"Visos grupės dublių intervalas šiame SYSTEM yra {int(wp.get('group_double_min') or 0)}–{int(wp.get('group_double_max') or 0)}. "
                    f"Kad 12 h workstyle būtų laikomas išpildytu, šiam run pakanka būti viršutiniame intervalo krašte: ≥{threshold} 12 h dienų. "
                    f"12 h pageidavimą turėjo {cohort} rezidentas(-ai). "
                    + ("Todėl pageidavimas ĮVYKDYTAS." if fulfilled else "Todėl pageidavimas NEĮVYKDYTAS ir reikia peržiūrėti solverio workstyle paskirstymą.")
                )
            if mode==1:
                return (
                    f"{who}SYSTEM generavimo metu buvo užšaldytas pageidavimas „prefer 6 h“. "
                    f"Skirta {int(wp.get('double_days') or 0)} 12 h dienų ir {int(wp.get('single_days') or 0)} 6 h dienų. "
                    f"Šio run 6 h workstyle riba yra ≤{int(wp.get('fulfilled_threshold_max') or 0)} 12 h dienų. "
                    + ("Pageidavimas ĮVYKDYTAS." if fulfilled else "Pageidavimas NEĮVYKDYTAS.")
                )
        if fulfilled:
            if r.get("kind")=="preferred":
                return f"{who}{date_txt} {block}: „{typ}“ — ĮVYKDYTA, nes grafike yra tinkama darbo pamaina ({station})."
            if r.get("kind") in ("resident_hard","soft_free"):
                return f"{who}{date_txt} {block}: „{typ}“ — ĮVYKDYTA, nes šiame bloke nėra persidengiančios normalios darbo pamainos."
            return f"{who}{date_txt} {block}: „{typ}“ — ĮVYKDYTA."
        if r.get("kind") in ("resident_hard","soft_free"):
            return (
                f"{who}{date_txt} {block}: „{typ}“ — NEĮVYKDYTA po optimizavimo. "
                f"Pageidavimas buvo įvestis PRIEŠ grafiką ir RAPA pirmiausia bandė jį išlaikyti; "
                f"galutiniame variante šiame bloke liko paskyrimas: {station}. "
                "Tai nėra priežastis savaime — tai galutinis aukštesnių HARD / privalomo padengimo / tikslaus krūvio apribojimų rezultatas."
            )
        if r.get("kind")=="preferred":
            if r.get("unmet_reason_code")=="PREFERRED_CONFLICT_ASSIGNED_TO_OTHER":
                owners=", ".join(sorted({str(x.get("assigned_to")) for x in (r.get("competing_assignments") or []) if x.get("assigned_to")}))
                return (
                    f"{who}{date_txt} {block}: „{typ}“ — NEĮVYKDYTA. Tinkama darbo pamaina šiame bloke EGZISTUOJA, "
                    f"bet šiame SYSTEM variante ji paskirta {owners or 'kitam rezidentui'}. Tai pageidavimų paskirstymo konfliktas, ne pamainos nebuvimas."
                )
            return f"{who}{date_txt} {block}: „{typ}“ — NEĮVYKDYTA, nes šiame bloke nėra aktyvios darbo pamainos, kuri galėtų išpildyti prašymą."
        return f"{who}{date_txt} {block}: „{typ}“ — NEĮVYKDYTA pagal parodytą rezultatą ({station})."
    if r.get("kind") in ("shift_length_preference","avoid_doubles") and r.get("workstyle_proof"):
        wp=r.get("workstyle_proof") or {}
        mode=int(wp.get("mode") or 0)
        if mode==3:
            return (
                f"{who}The frozen SYSTEM input was 'prefer 12 h'. "
                f"The grafikas contains {int(wp.get('double_days') or 0)} 12 h days and "
                f"{int(wp.get('single_days') or 0)} 6 h days; Onko 9 h days: {int(wp.get('onko_9h_days') or 0)}. "
                f"Group double-day range is {int(wp.get('group_double_min') or 0)}–{int(wp.get('group_double_max') or 0)}; "
                f"this run counts the 12 h preference as honored at ≥{int(wp.get('fulfilled_threshold_min') or 0)} double-days. "
                + ("HONORED." if fulfilled else "NOT HONORED.")
            )
    if fulfilled:
        if r.get("kind")=="preferred":

            return f"{who}{date_txt} {block}: '{typ}' — HONORED because the grafikas contains an eligible assignment ({station})."
        if r.get("kind") in ("resident_hard","soft_free"):
            return f"{who}{date_txt} {block}: '{typ}' — HONORED because no overlapping normal work shift exists in that block."
        return f"{who}{date_txt} {block}: '{typ}' — HONORED."
    if r.get("kind") in ("resident_hard","soft_free"):
        return (f"{who}{date_txt} {block}: '{typ}' — NOT HONORED after optimization. "
                f"The request was an input BEFORE the schedule and was protected first; the final assignment is {station}. "
                "That assignment is the outcome, not the cause: higher HARD / mandatory coverage / exact-workload constraints prevented full honoring.")
    if r.get("kind")=="preferred":
        if r.get("unmet_reason_code")=="PREFERRED_CONFLICT_ASSIGNED_TO_OTHER":
            owners=", ".join(sorted({str(x.get("assigned_to")) for x in (r.get("competing_assignments") or []) if x.get("assigned_to")}))
            return f"{who}{date_txt} {block}: '{typ}' — NOT HONORED. A matching shift exists, but this SYSTEM solution assigned it to {owners or 'another resident'}; this is a preference-allocation conflict, not a missing shift."
        return f"{who}{date_txt} {block}: '{typ}' — NOT HONORED because no active scheduled shift exists in that block."
    return f"{who}{date_txt} {block}: '{typ}' — NOT HONORED ({station})."


def _plain_verify_instruction(r, initials=""):
    date_txt=str(r.get("date") or "—")
    block=str(r.get("block") or "FULL")
    station=str(r.get("station") or "—")
    typ=str(r.get("type") or "request")
    if lang=="LT":
        if r.get("kind") in ("resident_hard","soft_free") and not r.get("fulfilled"):
            return f"Atverk {date_txt}, rask {initials or 'rezidentą'} ir {block} bloką. Ten turi matytis {station}. Jei tokio paskyrimo nėra, įrankio teiginys klaidingas."
        if r.get("kind")=="preferred" and not r.get("fulfilled"):
            if r.get("unmet_reason_code")=="PREFERRED_CONFLICT_ASSIGNED_TO_OTHER":
                return f"Atverk {date_txt} {block} bloką. Patikrink, kad tinkama pamaina egzistuoja, bet ji paskirta kitam rezidentui; tada tai yra pageidavimų konfliktas."
            return f"Atverk {date_txt} {block} bloką ir patikrink, kad jame tikrai nėra aktyvios tinkamos darbo pamainos."
        if r.get("fulfilled"):
            return f"Atverk {date_txt}, rask {initials or 'rezidentą'} ir {block} bloką ir patikrink, ar grafikas atitinka sakinį kairėje."
        return "Patikrink konkretų nurodytą įrašą prieš SYSTEM grafiką / Post Matrix."
    if r.get("kind") in ("resident_hard","soft_free") and not r.get("fulfilled"):
        return f"Open {date_txt}, find {initials or 'the resident'} and the {block} block. {station} must be present; otherwise the tool statement is wrong."
    if r.get("kind")=="preferred" and not r.get("fulfilled"):
        if r.get("unmet_reason_code")=="PREFERRED_CONFLICT_ASSIGNED_TO_OTHER":
            return f"Open {date_txt} {block}. Verify that a matching shift exists but is assigned to another resident; that confirms a preference-allocation conflict."
        return f"Open {date_txt} {block} and verify that no active matching shift exists."
    return "Verify the specific statement against the SYSTEM grid / Post Matrix."



def _workstyle_request_text(r):
    wp=r.get("workstyle_proof") or {}
    mode=int(wp.get("mode") or r.get("requested_value") or 0)
    if lang=="LT":
        return {
            1:"Prefer 6 h darbo dienas — FROZEN SYSTEM input",
            2:"Mišrus 6 h / 12 h darbo stilius — FROZEN SYSTEM input",
            3:"Prefer 12 h darbo dienas — FROZEN SYSTEM input",
        }.get(mode,"Darbo dienos trukmės pageidavimas — FROZEN SYSTEM input")
    return {
        1:"Prefer 6 h workdays — FROZEN SYSTEM input",
        2:"Mixed 6 h / 12 h workstyle — FROZEN SYSTEM input",
        3:"Prefer 12 h workdays — FROZEN SYSTEM input",
    }.get(mode,"Workday-length preference — FROZEN SYSTEM input")


def _workstyle_schedule_text(r):
    wp=r.get("workstyle_proof") or {}
    if not wp:
        return r.get("station","—")
    mode=int(wp.get("mode") or 0)
    base=(
        f"12 h: {int(wp.get('double_days') or 0)} d.; "
        f"6 h: {int(wp.get('single_days') or 0)} d.; "
        f"Onko 9 h: {int(wp.get('onko_9h_days') or 0)} d."
    )
    if mode==3:
        base+=(
            f"; grupės 12 h dienų intervalas {int(wp.get('group_double_min') or 0)}–"
            f"{int(wp.get('group_double_max') or 0)}; išpildymo riba ≥"
            f"{int(wp.get('fulfilled_threshold_min') or 0)}"
        )
    elif mode==1:
        base+=f"; išpildymo riba ≤{int(wp.get('fulfilled_threshold_max') or 0)} 12 h dienų"
    return base


def _workstyle_verify_text(r, initials=""):
    wp=r.get("workstyle_proof") or {}
    mode=int(wp.get("mode") or 0)
    if lang=="LT":
        if mode==3:
            return (
                f"Grafike suskaičiuok {initials or 'rezidento'} dienas, kur yra ir AM, ir PM normalios pamainos: "
                f"jų turi būti {int(wp.get('double_days') or 0)}. Šio SYSTEM grupės max yra "
                f"{int(wp.get('group_double_max') or 0)}, o 12 h pageidavimo išpildymo riba ≥"
                f"{int(wp.get('fulfilled_threshold_min') or 0)}. Onko 9 h į 12 h dublių skaičių neįtraukiamas."
            )
        return "Patikrink 6 h / 12 h dienų skaičių prieš frozen SYSTEM grafiką; Onko 9 h skaičiuojamas atskirai."
    if mode==3:
        return (
            f"Count {initials or 'the resident'} days with both AM and PM normal assignments: "
            f"there should be {int(wp.get('double_days') or 0)}. Group maximum is "
            f"{int(wp.get('group_double_max') or 0)} and the 12 h fulfillment threshold is ≥"
            f"{int(wp.get('fulfilled_threshold_min') or 0)}. Onko 9 h does not count as a 12 h double-day."
        )
    return "Verify the 6 h / 12 h day counts against the frozen SYSTEM schedule."



def _friendly_block_text(block):
    b=str(block or "FULL").upper()
    if lang=="LT":
        return {"AM":"rytas","PM":"vakaras","FULL":"visa diena","NIGHT":"naktis"}.get(b,b.lower())
    return {"AM":"morning","PM":"evening","FULL":"full day","NIGHT":"night"}.get(b,b.lower())


def _friendly_date_text(value):
    raw=str(value or "")
    try:
        dt=date.fromisoformat(raw)
    except Exception:
        return raw or "—"
    if lang=="LT":
        return f"{MONTHS['LT'][dt.month-1]} {dt.day} d."
    return dt.strftime("%b %-d") if os.name!="nt" else dt.strftime("%b %d").replace(" 0"," ")


def _friendly_station_text(text):
    txt=str(text or "—")
    if txt=="—":
        return txt
    if lang=="LT":
        txt=(txt.replace("CENTRO RO","Centro RO")
                .replace(" (AM)"," · rytas")
                .replace(" (PM)"," · vakaras")
                .replace(" (FULL)"," · visa diena")
                .replace(" (NIGHT)"," · naktis")
                .replace("1035kab","1035 kab.")
                .replace("120kab","120 kab.")
                .replace("144kab","144 kab.")
                .replace("145kab","145 kab."))
    return txt


def _friendly_resident_label(initials, name):
    parts=[x for x in str(name or "").split() if x]
    short=parts[-1] if parts else str(initials or "")
    return f"{short} · {initials}" if initials else short


def _missed_outcome_short(r):
    kind=str(r.get("kind") or "")
    station=_friendly_station_text(r.get("station") or "—")
    if kind in ("resident_hard","soft_free"):
        return (f"Paskirta: {station}" if lang=="LT" else f"Assigned: {station}") if station!="—" else ("Vis tiek atsirado darbas" if lang=="LT" else "Work was still assigned")
    if kind=="preferred":
        if r.get("unmet_reason_code")=="NO_ACTIVE_SHIFT_IN_BLOCK":
            return "Tuo metu nėra tinkamos pamainos" if lang=="LT" else "No matching shift exists then"
        owners=sorted({str(x.get("assigned_to")) for x in (r.get("competing_assignments") or []) if x.get("assigned_to")})
        if owners:
            return ("Tinkama pamaina atiteko " + ", ".join(owners)) if lang=="LT" else ("Matching shift went to " + ", ".join(owners))
        return "Tinkama pamaina atiteko kitam" if lang=="LT" else "Matching shift went to someone else"
    return station


def _missed_reason_scandi(r, initials=""):
    """Short, non-technical explanation for a missed resident wish.

    Deliberately avoids solver jargon. The resident sees the governing human rule,
    not implementation details such as variables, objective tiers or water-fill.
    """
    kind=str(r.get("kind") or "")
    raw_date=str(r.get("date") or "")
    try:
        dt=date.fromisoformat(raw_date)
    except Exception:
        dt=None
    wd=(dt.weekday() if dt else None)

    if lang=="LT":
        if kind=="resident_hard":
            return "Klaida. „Negaliu dirbti“ negali būti pažeistas — grafiką reikia taisyti."
        if kind=="soft_free":
            if wd==4:
                return "Penktadienių balansas. Jei paliktume ir šį penktadienį laisvą, daugiau penktadienių tektų kitiems."
            if wd in (5,6):
                return "Savaitgalio balansas. Šią dieną reikėjo palikti darbui, kad savaitgaliai pasiskirstytų tolygiai."
            return "Reikėjo padengti darbą. Kitu atveju ši pamaina būtų likusi neuždengta arba krūvis persikeltų kitam."
        if kind=="preferred":
            if r.get("unmet_reason_code")=="NO_ACTIVE_SHIFT_IN_BLOCK":
                return "Tuo metu nėra pamainos, kuri atitiktų šį norą."
            _comp=list(r.get("competing_assignments") or [])
            _is_duty=any("budėj" in str(x.get("department") or "").lower() for x in _comp)
            if wd==4:
                return "Penktadienių balansas. Šią pamainą skyrus tau, penktadienių krūvis taptų nelygesnis."
            if wd in (5,6) and _is_duty:
                return "Budėjimų balansas. Šis budėjimas skirtas kitam, kad kiekvienas gautų savo sąžiningą dalį."
            if wd in (5,6):
                return "Savaitgalio balansas. Ši pamaina skirta kitam, kad savaitgaliai pasiskirstytų tolygiai."
            return "Šią pamainą reikėjo skirti kitam, kad būtų išlaikytos svarbesnės taisyklės ir bendras balansas."
        return "Šis noras susikirto su svarbesne grafiko taisykle."

    if kind=="resident_hard":
        return "This should not happen. Cannot-work is mandatory and the schedule must be fixed."
    if kind=="soft_free":
        if wd==4:
            return "Friday balance — the engine tried to keep this Friday free, but Friday work cannot all be shifted to other residents."
        if wd in (5,6):
            return "Weekend balance — this free-day wish conflicted with required weekend coverage and a fair weekend split."
        return "Required coverage — this block had to be filled without shifting too much work to others."
    if kind=="preferred":
        if r.get("unmet_reason_code")=="NO_ACTIVE_SHIFT_IN_BLOCK":
            return "No active matching shift exists at that time."
        if wd==4:
            return "Friday balance — assigning the matching shift here would have made Friday workload less fair across the group."
        if wd in (5,6):
            return "Weekend balance — the matching shift had to go elsewhere to preserve the required duty/weekend split."
        return "A matching shift existed, but it went to another resident to preserve higher rules and a better overall request result."
    return "This wish conflicted with a higher scheduling rule."


def missed_requests_scandi_df(rows, initials=""):
    """Minimal four-column table for missed wishes only."""
    out=[]
    for r in rows or []:
        if not _is_actual_wish_row(r) or bool(r.get("fulfilled")):
            continue
        out.append({
            ("Data" if lang=="LT" else "Date"):_friendly_date_text(r.get("date")),
            ("Pageidavimas" if lang=="LT" else "Wish"):(
                f"{r.get('type','—')} · {_friendly_block_text(r.get('block'))}"
            ),
            ("Kas gavosi" if lang=="LT" else "Outcome"):_missed_outcome_short(r),
            ("Kodėl" if lang=="LT" else "Why"):_missed_reason_scandi(r,initials),
        })
    return pd.DataFrame(out)


def all_missed_requests_scandi_df(result):
    """One calm, readable table for every missed scored wish in a generated schedule."""
    out=[]
    for initials,d in (result.stats.get("people",{}) or {}).items():
        name=d.get("name","")
        for r in (d.get("request_detail_rows") or []):
            if not _is_actual_wish_row(r) or bool(r.get("fulfilled")):
                continue
            out.append({
                ("Rezidentas" if lang=="LT" else "Resident"):_friendly_resident_label(initials,name),
                ("Data" if lang=="LT" else "Date"):_friendly_date_text(r.get("date")),
                ("Noras" if lang=="LT" else "Wish"):f"{r.get('type','—')} · {_friendly_block_text(r.get('block'))}",
                ("Kas gavosi" if lang=="LT" else "Outcome"):_missed_outcome_short(r),
                ("Kodėl" if lang=="LT" else "Why"):_missed_reason_scandi(r,initials),
            })
    return pd.DataFrame(out)


def render_all_missed_requests_scandi(result):
    df=all_missed_requests_scandi_df(result)
    if df.empty:
        st.success("Visi aktyvūs pageidavimai įvykdyti." if lang=="LT" else "All active wishes were honored.")
        return
    st.caption(
        "Tik neįvykdyti norai. Viena eilutė = vienas noras. Be kodų, lygių ir techninių paaiškinimų."
        if lang=="LT" else
        "Missed wishes only. One row = one wish. No codes, levels, or technical explanations."
    )
    if lang=="LT":
        cfg={
            "Rezidentas":st.column_config.TextColumn("Rezidentas",width="small"),
            "Data":st.column_config.TextColumn("Data",width="small"),
            "Noras":st.column_config.TextColumn("Noras",width="medium"),
            "Kas gavosi":st.column_config.TextColumn("Kas gavosi",width="large"),
            "Kodėl":st.column_config.TextColumn("Kodėl",width="large"),
        }
    else:
        cfg={
            "Resident":st.column_config.TextColumn("Resident",width="small"),
            "Date":st.column_config.TextColumn("Date",width="small"),
            "Wish":st.column_config.TextColumn("Wish",width="medium"),
            "Outcome":st.column_config.TextColumn("Outcome",width="large"),
            "Why":st.column_config.TextColumn("Why",width="large"),
        }
    st.dataframe(
        df,use_container_width=True,hide_index=True,
        height=min(620,74+82*max(1,len(df))),column_config=cfg,
    )


def render_missed_requests_scandi(rows, initials="", *, key_suffix=""):
    df=missed_requests_scandi_df(rows,initials)
    if df.empty:
        st.caption("Neįvykdytų pageidavimų nėra." if lang=="LT" else "No missed wishes.")
        return
    st.caption(
        "Tik esmė: ko prašei, kas gavosi ir kodėl. Be techninių kodų ir be solverio žargono."
        if lang=="LT" else
        "Only the essentials: what you asked for, what happened, and why. No solver jargon."
    )
    if lang=="LT":
        cfg={
            "Data":st.column_config.TextColumn("Data",width="small"),
            "Pageidavimas":st.column_config.TextColumn("Pageidavimas",width="medium"),
            "Kas gavosi":st.column_config.TextColumn("Kas gavosi",width="large"),
            "Kodėl":st.column_config.TextColumn("Kodėl",width="large"),
        }
    else:
        cfg={
            "Date":st.column_config.TextColumn("Date",width="small"),
            "Wish":st.column_config.TextColumn("Wish",width="medium"),
            "Outcome":st.column_config.TextColumn("Outcome",width="large"),
            "Why":st.column_config.TextColumn("Why",width="large"),
        }
    st.dataframe(
        df,use_container_width=True,hide_index=True,
        height=min(560,74+76*max(1,len(df))),
        column_config=cfg,
    )

def request_details_df(rows, initials=""):
    """Plain-language resident/senior request audit table.

    V2.5.87: workstyle rows are rendered from the FROZEN SYSTEM request snapshot
    and contain concrete 6 h / 12 h / Onko counts rather than a generic FULL row.
    """
    out=[]
    for r in rows or []:
        if not _is_actual_wish_row(r):
            continue
        fulfilled=bool(r.get("fulfilled"))
        is_workstyle=bool(
            r.get("kind") in ("shift_length_preference","avoid_doubles")
            and r.get("workstyle_proof")
        )
        requested=(
            _workstyle_request_text(r)
            if is_workstyle else
            f"{r.get('type','—')} · {r.get('date','—')} · {r.get('block','—')}"
        )
        if is_workstyle:
            shown=_workstyle_schedule_text(r)
        elif r.get("station","—")!="—":
            shown=r.get("station","—")
        elif r.get("unmet_reason_code")=="PREFERRED_CONFLICT_ASSIGNED_TO_OTHER":
            _parts=[]
            for _x in (r.get("competing_assignments") or []):
                _parts.append(f"{_x.get('department')} ({_x.get('block')}) → {_x.get('assigned_to')}")
            shown="; ".join(_parts) or ("Tinkama pamaina paskirta kitam rezidentui" if lang=="LT" else "Matching shift assigned to another resident")
        elif r.get("kind")=="preferred" and not fulfilled:
            shown=("Nėra aktyvios tinkamos pamainos" if lang=="LT" else "No active matching shift")
        else:
            shown=("Nėra persidengiančio paskyrimo" if lang=="LT" else "No overlapping assignment")
        verify=(
            _workstyle_verify_text(r,initials)
            if is_workstyle else
            _plain_verify_instruction(r,initials)
        )
        fix_hint=(r.get("swap_hint","—") if not fulfilled else "—")
        if not fulfilled and r.get("kind")=="preferred":
            try:
                _rd=str(r.get("date") or "")
                _dt=date.fromisoformat(_rd) if _rd and _rd!="—" else None
            except Exception:
                _dt=None
            if _dt is not None and _dt.weekday()>=5:
                fix_hint=(
                    "Sistema pirmiausia bandė įvykdyti tavo savanorišką savaitgalio pasirinkimą, bet aukštesnės grafiko taisyklės to neleido. "
                    "Sugeneravus grafiką gali pasiūlyti asmeninį apsikeitimą Apsikeitimų lange."
                    if lang=="LT" else
                    "The engine first tried to honor your voluntary weekend choice, but higher scheduling rules prevented it. "
                    "After generation you can propose a personal swap in the Swaps window."
                )
        out.append({
            ("Lygis" if lang=="LT" else "Level"):r.get("priority","—"),
            ("Ko prašei" if lang=="LT" else "What was requested"):requested,
            ("Ką rodo grafikas" if lang=="LT" else "What the grafikas shows"):shown,
            ("Rezultatas" if lang=="LT" else "Result"):("ĮVYKDYTA" if fulfilled else "NEĮVYKDYTA") if lang=="LT" else ("ĮVYKDYTA" if fulfilled else "NOT HONORED"),
            ("Aiškus paaiškinimas" if lang=="LT" else "Plain-language explanation"):_plain_request_sentence(r,initials),
            ("Kaip patikrinti" if lang=="LT" else "How to verify"):verify,
            ("Jei nori taisyti" if lang=="LT" else "If you want to fix it"):fix_hint,
        })
    return pd.DataFrame(out)


def workplace_exposure_df(y,m,result):
    """Exact monthly assignment counts per workplace, computed directly from assignments.

    This intentionally does not trust stored stats so historical schedules created
    before the rotation-fairness feature still show correct workplace counts.
    """
    slots={s.idx:s for s in make_slots(y,m)}
    names={p["initials"]:p["name"] for p in DEFAULT_PEOPLE}
    rows=[]
    for i in [p["initials"] for p in DEFAULT_PEOPLE]:
        _display_cats=display_rotation_categories(y,m)
        counts={cat:0 for cat in _display_cats}
        for sid,who in result.assignments.items():
            if who!=i:
                continue
            s=slots.get(int(sid))
            if s is None:
                continue
            cat=rotation_category(s)
            if cat in counts:
                counts[cat]+=1
        row={
            tr("person"):i,
            tr("name"):names.get(i,""),
        }
        for cat in _display_cats:
            row[cat]=int(counts[cat])
        row[("Skirtingi postai" if lang=="LT" else "Distinct workplaces")]=sum(1 for v in counts.values() if v>0)
        rows.append(row)
    return pd.DataFrame(rows)


def schedule_list_df(y,m,result):
    out=[]
    for s in make_slots(y,m):
        if not slot_visible_in_schedule(s,y,m):
            continue
        who=result.assignments.get(s.idx,"")
        if not who and not s.blocked:
            continue
        out.append({
            tr("date"):f"{y}-{m:02d}-{s.day:02d}",
            tr("day"):WEEKDAY_FULL[lang][s.weekday],
            tr("department"):slot_department_text(y,m,s),
            tr("shift"):block_label(s.block),
            tr("workload"):s.workload2/2,
            tr("person"):who if who else "—",
        })
    return pd.DataFrame(out)


def backup_table(y,m,result,backup_rows_override=None):
    slots={s.idx:s for s in make_slots(y,m)}
    rows=[]
    backup_rows=_backup_rows_for_result(y,m,result,backup_rows_override)
    for r in backup_rows:
        sid=int(r["covered_slot"])
        s=slots.get(sid)
        if s is None:
            continue
        covered=result.assignments.get(sid,"")
        rows.append({
            "ID":r.get("id","DRAFT"),
            tr("date"):f"{y}-{m:02d}-{s.day:02d}",
            tr("covered_person"):covered,
            tr("department"):s.department,
            tr("shift"):block_label(s.block),
            tr("covered_schedule"):_covered_shift_text(y,m,result,sid),
            tr("planned_backup"):r["planned_backup"],
            tr("actual_backup"):r.get("actual_backup") or "",
            tr("effective_backup"):r.get("actual_backup") or r.get("planned_backup",""),
            tr("backup_note"):r.get("note",("AUTO SYSTEM" if lang=="EN" else "AUTO SYSTEM")),
        })
    return pd.DataFrame(rows)


def backup_grid(y,m,result,initials):
    _,ndays=calendar.monthrange(y,m)
    slots={s.idx:s for s in make_slots(y,m)}
    by_day={d:[] for d in range(1,ndays+1)}
    for r in _backup_rows_for_result(y,m,result):
        eff=r.get("actual_backup") or r.get("planned_backup")
        if eff!=initials:
            continue
        sid=int(r["covered_slot"])
        s=slots.get(sid)
        if s is None:
            continue
        covered=result.assignments.get(sid,"")
        by_day[s.day].append((s.block,covered,s.department))

    for d in by_day:
        by_day[d]=sorted(
            by_day[d],
            key=lambda x:({"AM":0,"FULL":1,"PM":2}.get(x[0],9),x[1],x[2])
        )

    max_rows=max([len(v) for v in by_day.values()] or [0])
    if max_rows==0:
        vals={d:"" for d in range(1,ndays+1)}
        df=pd.DataFrame([vals],index=[tr("backups")])
    else:
        rows=[]; idx=[]
        for k in range(max_rows):
            vals={}
            for d in range(1,ndays+1):
                if k<len(by_day[d]):
                    block,covered,dept=by_day[d][k]
                    vals[d]=f"{covered}\n{block_label(block)} · {dept}"
                else:
                    vals[d]=""
            rows.append(vals)
            idx.append(f"{tr('backups')} {k+1}" if max_rows>1 else tr("backups"))
        df=pd.DataFrame(rows,index=idx)

    df.columns=[
        f"{d:02d}\n{WEEKDAYS[lang][date(y,m,d).weekday()]}"
        for d in range(1,ndays+1)
    ]
    def cs(v):
        if not v:
            return ""
        ini=str(v).split("\n")[0]
        c=PERSON_COLORS.get(ini)
        return "" if not c else (
            f"background-color:{c};color:{contrast_text(c)};"
            "font-weight:700;text-align:center;white-space:pre-wrap;"
        )
    return df.style.map(cs)



def backup_overview_grid(y,m,result):
    """Senior pre-publication matrix for the generated theoretical backup layer.

    Rows are backup residents and columns are calendar days. This is deliberately
    read from the DRAFT ``backup_snapshot`` before publication, so the senior can
    inspect the entire standby plan in Sudarymas without creating operational
    backup_assignments in the database.
    """
    _,ndays=calendar.monthrange(y,m)
    slots={s.idx:s for s in make_slots(y,m)}
    day_cols=[f"{d:02d} {WEEKDAYS[lang][date(y,m,d).weekday()]}" for d in range(1,ndays+1)]
    rows=[]
    backup_rows=_backup_rows_for_result(y,m,result)
    for prow in DEFAULT_PEOPLE:
        initials=prow["initials"]
        by_day={d:[] for d in range(1,ndays+1)}
        for r in backup_rows:
            eff=str(r.get("actual_backup") or r.get("planned_backup") or "")
            if eff!=initials:
                continue
            sid=int(r.get("covered_slot"))
            sl=slots.get(sid)
            if sl is None:
                continue
            covered=str(result.assignments.get(sid,"") or r.get("covered_person") or "")
            by_day[sl.day].append((sl.block,covered,sl.department))
        row={("Dublis" if lang=="LT" else "Backup"):initials}
        for d,col in enumerate(day_cols,start=1):
            vals=sorted(by_day[d],key=lambda x:({"AM":0,"FULL":1,"PM":2}.get(x[0],9),x[1],x[2]))
            row[col]=" | ".join(f"{covered} · {block_label(block)} · {dept}" for block,covered,dept in vals)
        rows.append(row)
    return pd.DataFrame(rows)

def personal_schedule_df(y,m,result,initials):
    """Personal NORMAL-WORK ledger only.

    V2.5.115 deliberately does not mix theoretical backup/standby duties into the
    resident's actual work table. Backups are rendered immediately below in their
    own dedicated backup layer/grid and only become real work after COMPLETED cover.
    """
    rows=[]
    slots=make_slots(y,m)
    for sl in slots:
        if result.assignments.get(sl.idx)!=initials:
            continue
        rows.append({
            tr("date"):f"{y}-{m:02d}-{sl.day:02d}",
            tr("day"):WEEKDAY_FULL[lang][sl.weekday],
            tr("time"):slot_time_text(sl),
            tr("department"):slot_department_text(y,m,sl),
            tr("shift"):block_label(sl.block),
        })
    special=db.get_special_workdays_v25145(y,m,initials)
    for d in sorted(special.get("wellness_days",set())):
        rows.append({
            tr("date"):f"{y}-{m:02d}-{int(d):02d}",
            tr("day"):WEEKDAY_FULL[lang][date(y,m,int(d)).weekday()],
            tr("time"):("Visa diena" if lang=="LT" else "All day"),
            tr("department"):("Sveikatinimosi diena" if lang=="LT" else "Wellness day"),
            tr("shift"):("Darbo diena ne klinikoje" if lang=="LT" else "Paid workday outside clinical rota"),
        })
    for d in sorted(special.get("qualification_days",set())):
        rows.append({
            tr("date"):f"{y}-{m:02d}-{int(d):02d}",
            tr("day"):WEEKDAY_FULL[lang][date(y,m,int(d)).weekday()],
            tr("time"):("Visa diena" if lang=="LT" else "All day"),
            tr("department"):("Kvalifikacijos kėlimo diena" if lang=="LT" else "Qualification day"),
            tr("shift"):("Darbo diena ne klinikoje" if lang=="LT" else "Paid workday outside clinical rota"),
        })
    if not rows:
        return pd.DataFrame(rows)
    df=pd.DataFrame(rows)
    df["__sort_date"]=pd.to_datetime(df[tr("date")],errors="coerce")
    df=df.sort_values(["__sort_date",tr("time")],kind="stable").drop(columns=["__sort_date"])
    return df.reset_index(drop=True)


def build_ics(y,m,result,initials):
    slots={s.idx:s for s in make_slots(y,m)}
    p=next((x for x in DEFAULT_PEOPLE if x["initials"]==initials),None)
    name=p["name"] if p else initials
    color=PERSON_COLORS.get(initials,"#777777")
    tz=ZoneInfo("Europe/Vilnius")
    generated=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    calname=f"{name} — Radiologija" if lang=="LT" else f"{name} — Radiology"
    lines=[
        "BEGIN:VCALENDAR","VERSION:2.0",
        "PRODID:-//Radiology Scheduler//V2.5.68//EN",
        "CALSCALE:GREGORIAN","METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_escape(calname)}",
        "X-WR-TIMEZONE:Europe/Vilnius",
        f"COLOR:{color}",f"X-APPLE-CALENDAR-COLOR:{color}"
    ]

    # Normal assignments.
    for sid,who in sorted(
        result.assignments.items(),
        key=lambda kv:(slots[kv[0]].day,{"AM":0,"FULL":1,"PM":2}.get(slots[kv[0]].block,9),kv[0])
    ):
        if who!=initials:
            continue
        s=slots[sid]
        _start_dt,_end_dt=slot_datetime_bounds(y,m,s,tz)
        start=_start_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        end=_end_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        title=("Radiologija — " if lang=="LT" else "Radiology — ")+slot_department_text(y,m,s)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{y}{m:02d}{s.day:02d}-{sid}-{safe_filename(initials)}@radiology-scheduler",
            f"DTSTAMP:{generated}",f"DTSTART:{start}",f"DTEND:{end}",
            f"SUMMARY:{ics_escape(title)}",
            f"DESCRIPTION:{ics_escape(name+' | '+block_label(s.block))}",
            "TRANSP:OPAQUE",f"COLOR:{color}","STATUS:CONFIRMED","END:VEVENT"
        ]

    # V2.5.145 paid special workdays are shown as all-day calendar entries.
    special=db.get_special_workdays_v25145(y,m,initials)
    for kind,dayset in (("wellness",special.get("wellness_days",set())),("qualification",special.get("qualification_days",set()))):
        for d in sorted(dayset):
            start_date=date(y,m,int(d))
            end_date=start_date+timedelta(days=1)
            if kind=="wellness":
                title=("Sveikatinimosi diena" if lang=="LT" else "Wellness day")
            else:
                title=("Kvalifikacijos kėlimo diena" if lang=="LT" else "Qualification day")
            desc=("Apmokama darbo diena ne klinikoje." if lang=="LT" else "Paid workday outside the clinical rota.")
            lines += [
                "BEGIN:VEVENT",
                f"UID:special-{kind}-{y}{m:02d}{int(d):02d}-{safe_filename(initials)}@radiology-scheduler",
                f"DTSTAMP:{generated}",
                f"DTSTART;VALUE=DATE:{start_date.strftime('%Y%m%d')}",
                f"DTEND;VALUE=DATE:{end_date.strftime('%Y%m%d')}",
                f"SUMMARY:{ics_escape(title)}",f"DESCRIPTION:{ics_escape(desc)}",
                "TRANSP:OPAQUE","STATUS:CONFIRMED","END:VEVENT"
            ]

    # Shift-level backup duties are optional in the personal calendar.
    include_backups = bool(db.get_account_settings(initials).get("include_backups_in_calendar", False))
    if include_backups:
        for r in db.list_backups(y,m):
            eff=r.get("actual_backup") or r.get("planned_backup")
            if eff!=initials:
                continue
            sid=int(r["covered_slot"])
            s=slots.get(sid)
            covered=result.assignments.get(sid,"")
            if s is None or not covered:
                continue
            _start_dt,_end_dt=slot_datetime_bounds(y,m,s,tz)
            start=_start_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            end=_end_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            if lang=="LT":
                title=f"Dublis — {covered} — {s.department}"
                desc=f"Jei prireiktų, pavaduojate {covered}: {s.department}, {block_label(s.block)}."
            else:
                title=f"Backup — {covered} — {s.department}"
                desc=f"If cover is needed, you back up {covered}: {s.department}, {block_label(s.block)}."
            lines += [
                "BEGIN:VEVENT",
                f"UID:backup-{y}{m:02d}{s.day:02d}-{sid}-{safe_filename(initials)}@radiology-scheduler",
                f"DTSTAMP:{generated}",f"DTSTART:{start}",f"DTEND:{end}",
                f"SUMMARY:{ics_escape(title)}",f"DESCRIPTION:{ics_escape(desc)}",
                "TRANSP:TRANSPARENT","STATUS:TENTATIVE","END:VEVENT"
            ]
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines)+"\r\n").encode("utf-8")



def build_calendar_subscription_ics(initials, published_rows=None):
    """Build one stable subscription calendar from every published ACTUAL month.

    A subscription must not lose the previous month when a new month is published.
    Therefore the feed is assembled from all published current_json payloads, not
    merely the month currently open in the UI.
    """
    rows = published_rows if published_rows is not None else db.list_published_schedules()
    month_blobs=[]
    seen=set()
    for row in rows:
        try:
            yy=int(row.get("year")); mm=int(row.get("month"))
            if (yy,mm) in seen or not row.get("current_json"):
                continue
            rr=deserialize_result(row["current_json"])
            month_blobs.append((yy,mm,rr))
            seen.add((yy,mm))
        except Exception:
            continue
    month_blobs.sort(key=lambda x:(x[0],x[1]))

    p=next((x for x in DEFAULT_PEOPLE if x["initials"]==initials),None)
    name=p["name"] if p else initials
    color=PERSON_COLORS.get(initials,"#777777")
    settings=db.get_account_settings(initials)
    cal_lang=str(settings.get("preferred_language") or "LT").upper()
    if cal_lang not in ("LT","EN"):
        cal_lang="LT"
    generated=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    calname=f"{name} — Radiologija" if cal_lang=="LT" else f"{name} — Radiology"
    lines=[
        "BEGIN:VCALENDAR","VERSION:2.0",
        "PRODID:-//Radiology Scheduler//V2.5.68//EN",
        "CALSCALE:GREGORIAN","METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_escape(calname)}",
        "X-WR-TIMEZONE:Europe/Vilnius",
        f"COLOR:{color}",f"X-APPLE-CALENDAR-COLOR:{color}"
    ]
    tz=ZoneInfo("Europe/Vilnius")
    include_backups=bool(settings.get("include_backups_in_calendar",False))
    block_txt_lt={"AM":"Rytas","PM":"Popietė","FULL":"Visa diena","NIGHT":"Naktis"}
    block_txt_en={"AM":"Morning","PM":"Afternoon","FULL":"Full day","NIGHT":"Night"}

    for yy,mm,result in month_blobs:
        slots={sl.idx:sl for sl in make_slots(yy,mm)}
        for sid,who in sorted(result.assignments.items(),key=lambda kv:(slots[kv[0]].day,{"AM":0,"FULL":1,"PM":2}.get(slots[kv[0]].block,9),kv[0])):
            if who!=initials:
                continue
            sl=slots[sid]
            _start_dt,_end_dt=slot_datetime_bounds(yy,mm,sl,tz)
            start=_start_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            end=_end_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            block_txt=(block_txt_lt if cal_lang=="LT" else block_txt_en).get(sl.block,sl.block)
            title=("Radiologija — " if cal_lang=="LT" else "Radiology — ")+slot_department_text(yy,mm,sl)
            lines += [
                "BEGIN:VEVENT",
                f"UID:{yy}{mm:02d}{sl.day:02d}-{sid}-{safe_filename(initials)}@radiology-scheduler",
                f"DTSTAMP:{generated}",f"DTSTART:{start}",f"DTEND:{end}",
                f"SUMMARY:{ics_escape(title)}",f"DESCRIPTION:{ics_escape(name+' | '+block_txt)}",
                "TRANSP:OPAQUE",f"COLOR:{color}","STATUS:CONFIRMED","END:VEVENT"
            ]
        special=db.get_special_workdays_v25145(yy,mm,initials)
        for kind,dayset in (("wellness",special.get("wellness_days",set())),("qualification",special.get("qualification_days",set()))):
            for d in sorted(dayset):
                start_date=date(yy,mm,int(d)); end_date=start_date+timedelta(days=1)
                if kind=="wellness":
                    title=("Sveikatinimosi diena" if cal_lang=="LT" else "Wellness day")
                else:
                    title=("Kvalifikacijos kėlimo diena" if cal_lang=="LT" else "Qualification day")
                desc=("Apmokama darbo diena ne klinikoje." if cal_lang=="LT" else "Paid workday outside the clinical rota.")
                lines += [
                    "BEGIN:VEVENT",f"UID:special-{kind}-{yy}{mm:02d}{int(d):02d}-{safe_filename(initials)}@radiology-scheduler",
                    f"DTSTAMP:{generated}",f"DTSTART;VALUE=DATE:{start_date.strftime('%Y%m%d')}",f"DTEND;VALUE=DATE:{end_date.strftime('%Y%m%d')}",
                    f"SUMMARY:{ics_escape(title)}",f"DESCRIPTION:{ics_escape(desc)}",
                    "TRANSP:OPAQUE","STATUS:CONFIRMED","END:VEVENT"
                ]
        if include_backups:
            for br in db.list_backups(yy,mm):
                eff=br.get("actual_backup") or br.get("planned_backup")
                if eff!=initials:
                    continue
                sid=int(br["covered_slot"]); sl=slots.get(sid); covered=result.assignments.get(sid,"")
                if sl is None or not covered:
                    continue
                _start_dt,_end_dt=slot_datetime_bounds(yy,mm,sl,tz)
                start=_start_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                end=_end_dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                block_txt=(block_txt_lt if cal_lang=="LT" else block_txt_en).get(sl.block,sl.block)
                if cal_lang=="LT":
                    title=f"Dublis — {covered} — {sl.department}"; desc=f"Jei prireiktų, pavaduojate {covered}: {sl.department}, {block_txt}."
                else:
                    title=f"Backup — {covered} — {sl.department}"; desc=f"If cover is needed, you back up {covered}: {sl.department}, {block_txt}."
                lines += [
                    "BEGIN:VEVENT",f"UID:backup-{yy}{mm:02d}{sl.day:02d}-{sid}-{safe_filename(initials)}@radiology-scheduler",
                    f"DTSTAMP:{generated}",f"DTSTART:{start}",f"DTEND:{end}",
                    f"SUMMARY:{ics_escape(title)}",f"DESCRIPTION:{ics_escape(desc)}",
                    "TRANSP:TRANSPARENT","STATUS:TENTATIVE","END:VEVENT"
                ]
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines)+"\r\n").encode("utf-8")


def refresh_calendar_subscription_feeds(initials_list=None):
    """Best-effort refresh of private subscription feeds after grafikas changes.

    Publication must never fail only because a third-party calendar service is
    unavailable, so errors are returned for UI/audit instead of being raised.
    """
    people=list(initials_list) if initials_list is not None else [p["initials"] for p in DEFAULT_PEOPLE]
    rows=db.list_published_schedules()
    out=[]
    for ini in dict.fromkeys(people):
        try:
            feed=build_calendar_subscription_ics(ini,published_rows=rows)
            url=db.publish_calendar_feed(ini,feed)
            out.append({"initials":ini,"ok":True,"url":url,"error":""})
        except Exception as exc:
            out.append({"initials":ini,"ok":False,"url":"","error":str(exc)})
    return out



def build_xlsx(y,m,result,document_status=None,backup_rows_override=None):
    out=BytesIO(); wb=xlsxwriter.Workbook(out,{"in_memory":True}); ws=wb.add_worksheet("Grafikas" if lang=="LT" else "Schedule"); sm=wb.add_worksheet("Suvestinė" if lang=="LT" else "Summary"); bk=wb.add_worksheet("Dubliai" if lang=="LT" else "Backups")
    dark="#1F2937"; light="#F3F4F6"; weekend="#E5E7EB"; border="#D1D5DB"; title=wb.add_format({"bold":True,"font_size":16,"font_color":"#FFFFFF","bg_color":dark}); header=wb.add_format({"bold":True,"bg_color":light,"border":1,"border_color":border,"align":"center","valign":"vcenter","text_wrap":True}); wh=wb.add_format({"bold":True,"bg_color":weekend,"border":1,"border_color":border,"align":"center","valign":"vcenter","text_wrap":True}); cell=wb.add_format({"border":1,"border_color":border,"text_wrap":True}); blocked=wb.add_format({"border":1,"border_color":border,"bg_color":"#BFC4CA","align":"center"})
    pf={i:wb.add_format({"bold":True,"bg_color":c,"font_color":contrast_text(c),"border":1,"border_color":border,"align":"center","valign":"vcenter","text_wrap":True}) for i,c in PERSON_COLORS.items()}
    schedule_pf={i:wb.add_format({"bold":True,"bg_color":c,"font_color":"#FFFFFF","border":1,"border_color":border,"align":"center","valign":"vcenter","text_wrap":True}) for i,c in PERSON_COLORS.items()}
    _,nd=calendar.monthrange(y,m); last=1+nd; status_prefix=(str(document_status).strip()+" — ") if document_status else ""
    ws.merge_range(0,0,0,last,status_prefix+("Rezidentų grafikas — " if lang=="LT" else "Resident grafikas — ")+month_label(y,m),title); ws.write(1,0,tr("department"),header); ws.write(1,1,tr("shift"),header)
    for d in range(1,nd+1): ws.write(1,1+d,f"{d:02d}\n{WEEKDAYS[lang][date(y,m,d).weekday()]}",wh if date(y,m,d).weekday()>=5 else header)
    rowkeys=[]; slots=[s for s in make_slots(y,m) if slot_visible_in_schedule(s,y,m)]
    for s in slots:
        k=(slot_department_text(y,m,s,grid=True),s.block)
        if k not in rowkeys: rowkeys.append(k)
    if cohort_october_model(y,m):
        _night_row=("SPS RO naktiniai budėjimai" if lang=="LT" else "SPS RO night duties","NIGHT")
        if _night_row not in rowkeys: rowkeys.append(_night_row)
    def _rk(k):
        dept,block=k; br={"AM":0,"FULL":1,"PM":2,"NIGHT":3}.get(block,9); s=str(dept)
        if s.startswith("CENTRO RO"):
            try: num=int(re.search(r"CENTRO RO (\d+)",s).group(1))
            except Exception: num=9
            return (10,br,num,s)
        if s.startswith("Onkologinė/TBL") or s.startswith("Onko/TBL"): return (20,br,0,s)
        if s.startswith("Centro UG 120"): return (30,br,0,s)
        if s.startswith("SPS RO d.d."): return (40,br,0,s)
        if s.startswith("SPS RO nakt") or s.startswith("SPS RO night"): return (41,br,0,s)
        if s.startswith("SPS UG 1035"): return (50,br,0,s)
        if s.startswith("ADC 144"): return (60,br,0,s)
        if s.startswith("145") or s.startswith("ADC 145"): return (61,br,0,s)
        if s.startswith("Vaikų UG"): return (70,br,0,s)
        if s.startswith("Skopijos"): return (80,br,0,s)
        if s.startswith("SPS RO budėjimai"): return (90,br,0,s)
        return (500,br,0,s)
    rowkeys.sort(key=_rk)
    by={(slot_department_text(y,m,s,grid=True),s.block,s.day):s for s in slots}
    for r,(dept,block) in enumerate(rowkeys,start=2):
        ws.write(r,0,dept,cell); ws.write(r,1,block_label(block),cell)
        for d in range(1,nd+1):
            s=by.get((dept,block,d))
            if not s: ws.write_blank(r,1+d,None,cell)
            else:
                who=result.assignments.get(s.idx,""); ws.write(r,1+d,who,schedule_pf[who] if who else cell)
    ws.set_column(0,0,23); ws.set_column(1,1,13); ws.set_column(2,last,7); ws.freeze_panes(2,2)
    sdf=summary_df(result,y,m)
    for c,col in enumerate(sdf.columns): sm.write(0,c,col,header)
    for rr,(_,row) in enumerate(sdf.iterrows(),start=1):
        fmt=pf.get(str(row[tr("person")]),cell)
        for c,v in enumerate(row): sm.write(rr,c,"" if pd.isna(v) else v,fmt)
    sm.set_column(0,1,20); sm.set_column(2,len(sdf.columns)-1,17); sm.freeze_panes(1,0)

    # Shift-level backup sheet: rows are backup residents, days are columns.
    # Each cell states the exact covered colleague, block and department.
    bk.merge_range(0,0,0,nd,("Dublių grafikas — " if lang=="LT" else "Backup grafikas — ")+month_label(y,m),title)
    bk.write(1,0,tr("person"),header)
    for d in range(1,nd+1):
        bk.write(1,d,f"{d:02d}\n{WEEKDAYS[lang][date(y,m,d).weekday()]}",wh if date(y,m,d).weekday()>=5 else header)
    effective_map={}
    slot_map={s.idx:s for s in slots}
    backup_rows=_backup_rows_for_result(y,m,result,backup_rows_override)
    for r in backup_rows:
        sid=int(r["covered_slot"]); s=slot_map.get(sid)
        if s is None: continue
        eff=r["actual_backup"] or r["planned_backup"]
        covered=result.assignments.get(sid,"")
        effective_map.setdefault((eff,s.day),[]).append((s.block,covered,s.department))
    rr=2
    for p in DEFAULT_PEOPLE:
        i=p["initials"]
        max_rows=max([len(effective_map.get((i,d),[])) for d in range(1,nd+1)] or [0])
        max_rows=max(1,max_rows)
        for k in range(max_rows):
            label=i if max_rows==1 else f"{i} {k+1}"
            bk.write(rr,0,label,pf[i])
            for d in range(1,nd+1):
                vals=sorted(effective_map.get((i,d),[]),key=lambda x:({"AM":0,"FULL":1,"PM":2}.get(x[0],9),x[1],x[2]))
                if k>=len(vals):
                    bk.write_blank(rr,d,None,cell)
                else:
                    block,covered,dept=vals[k]
                    bk.write(rr,d,f"{covered}\n{block_label(block)} · {dept}",pf.get(covered,cell))
            rr+=1
    bk.set_column(0,0,10); bk.set_column(1,nd,20); bk.freeze_panes(2,1)

    detail_start=rr+2; bdf=backup_table(y,m,result,backup_rows_override=backup_rows)
    if not bdf.empty:
        bk.write(detail_start,0,tr("details"),title)
        for c,col in enumerate(bdf.columns): bk.write(detail_start+1,c,col,header)
        for rr,(_,row) in enumerate(bdf.iterrows(),start=detail_start+2):
            for c,v in enumerate(row): bk.write(rr,c,"" if pd.isna(v) else v,cell)
    wb.close(); out.seek(0); return out.getvalue()

def build_preferences_xlsx(y,m,rows,priority_visible=False):
    """Beautiful live export of the currently saved preference table.

    The export is deliberately independent from the preference-window status:
    the senior/researcher can download the current snapshot at any time. The
    priority column itself is only present after the preference deadline, just
    like in the UI.
    """
    df=pd.DataFrame(rows).copy()
    out=BytesIO()
    wb=xlsxwriter.Workbook(out,{"in_memory":True})
    wb.set_properties({
        "title":f"Pageidavimai {y}-{m:02d}",
        "subject":"Rezidentų pageidavimų eksportas",
        "author":"Shift Happens",
        "comments":"Eksportas atspindi tuo momentu sistemoje išsaugotus pageidavimus.",
    })
    ws=wb.add_worksheet("Pageidavimai")
    sm=wb.add_worksheet("Suvestinė")

    dark="#20242F"; accent="#FF4B4B"; white="#FFFFFF"; border="#D9DDE5"
    pale="#F7F8FA"; pale_red="#FDECEC"; pale_blue="#EAF3FF"; pale_yellow="#FFF6DD"
    pale_green="#EAF7EF"; pale_purple="#F3EEFF"; pale_gray="#F1F3F6"
    title=wb.add_format({"bold":True,"font_size":18,"font_color":white,"bg_color":dark,"align":"left","valign":"vcenter"})
    subtitle=wb.add_format({"font_size":10,"font_color":"#6B7280","bg_color":white})
    metric_label=wb.add_format({"bold":True,"font_color":"#6B7280","bg_color":pale,"border":1,"border_color":border})
    metric_value=wb.add_format({"bold":True,"font_size":12,"font_color":dark,"bg_color":pale,"border":1,"border_color":border})
    header_default=wb.add_format({"bold":True,"font_color":dark,"bg_color":"#E8EBF0","border":1,"border_color":border,"align":"center","valign":"vcenter","text_wrap":True})
    header_hard=wb.add_format({"bold":True,"font_color":"#8B1E1E","bg_color":"#F7D8D8","border":1,"border_color":border,"align":"center","valign":"vcenter","text_wrap":True})
    header_rest=wb.add_format({"bold":True,"font_color":"#7A5A00","bg_color":"#F9E8AF","border":1,"border_color":border,"align":"center","valign":"vcenter","text_wrap":True})
    header_work=wb.add_format({"bold":True,"font_color":"#17633A","bg_color":"#CFEAD9","border":1,"border_color":border,"align":"center","valign":"vcenter","text_wrap":True})
    header_absence=wb.add_format({"bold":True,"font_color":"#24568A","bg_color":"#DCEBFA","border":1,"border_color":border,"align":"center","valign":"vcenter","text_wrap":True})
    header_long=wb.add_format({"bold":True,"font_color":"#5A3E85","bg_color":"#E8DFF7","border":1,"border_color":border,"align":"center","valign":"vcenter","text_wrap":True})
    cell=wb.add_format({"font_color":dark,"border":1,"border_color":border,"valign":"top","text_wrap":True})
    cell_center=wb.add_format({"font_color":dark,"border":1,"border_color":border,"align":"center","valign":"vcenter","text_wrap":True})
    yes_fmt=wb.add_format({"bold":True,"font_color":"#17633A","bg_color":pale_green,"border":1,"border_color":border,"align":"center"})
    no_fmt=wb.add_format({"bold":True,"font_color":"#9B2C2C","bg_color":pale_red,"border":1,"border_color":border,"align":"center"})
    priority_fmt=wb.add_format({"bold":True,"font_color":"#7A4B00","bg_color":pale_yellow,"border":1,"border_color":border,"align":"center"})
    group_fmts={
        "hard":wb.add_format({"bg_color":pale_red,"border":1,"border_color":border,"valign":"top","text_wrap":True}),
        "absence":wb.add_format({"bg_color":pale_blue,"border":1,"border_color":border,"valign":"top","text_wrap":True}),
        "rest":wb.add_format({"bg_color":pale_yellow,"border":1,"border_color":border,"valign":"top","text_wrap":True}),
        "work":wb.add_format({"bg_color":pale_green,"border":1,"border_color":border,"valign":"top","text_wrap":True}),
        "long":wb.add_format({"bg_color":pale_purple,"border":1,"border_color":border,"valign":"top","text_wrap":True}),
        "neutral":wb.add_format({"bg_color":pale_gray,"border":1,"border_color":border,"valign":"top","text_wrap":True}),
    }
    person_fmts={i:wb.add_format({"bold":True,"bg_color":c,"font_color":contrast_text(c),"border":1,"border_color":border,"align":"center","valign":"vcenter"}) for i,c in PERSON_COLORS.items()}

    ncols=max(1,len(df.columns))
    ws.merge_range(0,0,0,ncols-1,f"Pageidavimai · {month_label(y,m)}",title)
    ws.set_row(0,30)
    export_time=datetime.now(ZoneInfo("Europe/Vilnius")).strftime("%Y-%m-%d %H:%M")
    ws.merge_range(1,0,1,ncols-1,f"Gyvas sistemos eksportas · {export_time}",subtitle)

    submitted_col=tr("submitted")
    person_col=tr("person")
    submitted_count=int((df[submitted_col].astype(str)==str(tr("yes"))).sum()) if submitted_col in df.columns else 0
    missing=[]
    if person_col in df.columns and submitted_col in df.columns:
        missing=df.loc[df[submitted_col].astype(str)!=str(tr("yes")),person_col].astype(str).tolist()
    ws.write(3,0,"Pateikta",metric_label); ws.write(3,1,f"{submitted_count}/{len(DEFAULT_PEOPLE)}",metric_value)
    ws.write(3,2,"Dar nepateikė",metric_label); ws.merge_range(3,3,3,min(ncols-1,7),", ".join(missing) if missing else "—",metric_value)
    if priority_visible:
        ws.write(3,min(ncols-1,8),"Prioritetas",metric_label)
        if min(ncols-1,9)>=min(ncols-1,8):
            ws.write(3,min(ncols-1,9),"Galutinis po 14 d. 00:00",metric_value)

    header_row=5
    def col_group(name):
        n=str(name).lower()
        if "dirbti negaliu" in n or "unavailable" in n: return "hard"
        if "atostog" in n or "neatvyk" in n or "budėjimo" in n: return "absence"
        if "noriu laisv" in n or "time off" in n: return "rest"
        if "pageidauju dirbti" in n or "prefer work" in n: return "work"
        if "ilgalaik" in n or "long-term" in n: return "long"
        if "komentar" in n or "el. pašt" in n or "šven" in n: return "neutral"
        return "default"
    header_fmt={"hard":header_hard,"absence":header_absence,"rest":header_rest,"work":header_work,"long":header_long}.get
    for c,name in enumerate(df.columns):
        grp=col_group(name)
        ws.write(header_row,c,name,header_fmt(grp,header_default))
    ws.set_row(header_row,42)

    priority_name="Pateikimo vieta"
    for r_idx,(_,row) in enumerate(df.iterrows(),start=header_row+1):
        ini=str(row.get(person_col,"")) if person_col in df.columns else ""
        for c,name in enumerate(df.columns):
            value=row.get(name,"")
            if pd.isna(value): value=""
            grp=col_group(name)
            fmt=cell
            if name==person_col:
                fmt=person_fmts.get(ini,cell_center)
            elif name==submitted_col:
                fmt=yes_fmt if str(value)==str(tr("yes")) else no_fmt
            elif name==priority_name and priority_visible:
                fmt=priority_fmt
            elif grp in group_fmts:
                fmt=group_fmts[grp]
            elif c<=3:
                fmt=cell_center
            ws.write(r_idx,c,value,fmt)
        ws.set_row(r_idx,38)

    if len(df.columns):
        ws.autofilter(header_row,0,header_row+len(df),len(df.columns)-1)
    ws.freeze_panes(header_row+1,2)
    # Compact but readable widths; long request fields wrap instead of creating a giant sheet.
    for c,name in enumerate(df.columns):
        n=str(name).lower()
        width=14
        if name==tr("name"): width=24
        elif name==tr("person"): width=10
        elif "komentar" in n: width=32
        elif "ilgalaik" in n: width=30
        elif "el. pašt" in n: width=27
        elif any(k in n for k in ["dirbti negaliu","noriu laisv","pageidauju dirbti","atostog","neatvyk","budėjimo"]): width=20
        elif "pateikimo būdas" in n: width=22
        elif "pageidavimų apimtis" in n: width=18
        ws.set_column(c,c,width)

    # A clean summary sheet for a quick senior overview.
    sm.merge_range("A1:F1",f"Suvestinė · {month_label(y,m)}",title)
    sm.set_row(0,30)
    sm.write("A3","Pateikta",metric_label); sm.write("B3",submitted_count,metric_value)
    sm.write("C3","Iš viso",metric_label); sm.write("D3",len(DEFAULT_PEOPLE),metric_value)
    sm.write("E3","Dar nepateikė",metric_label); sm.write("F3",len(missing),metric_value)
    sm.write("A5","Dar nepateikė",header_default)
    if missing:
        for rr,ini in enumerate(missing,start=5):
            sm.write(rr,0,ini,person_fmts.get(ini,cell_center))
    else:
        sm.write("A6","Visi pateikė",yes_fmt)
    sm.write("C5","Pastaba",header_default)
    sm.merge_range("C6:F8","Excel failą galima atsisiųsti bet kuriuo pageidavimų teikimo etapu. Iki 14 d. 00:00 prioritetinė vieta nerodoma; po termino eksportuojama galutinė eilė.",cell)
    sm.set_column("A:A",18); sm.set_column("B:B",3); sm.set_column("C:F",22)
    sm.freeze_panes(5,0)

    wb.close(); out.seek(0); return out.getvalue()


def render_schedule_download_buttons(y,m,result,*,status_label,file_prefix,key_prefix,backup_rows_override=None):
    """Explicit grafikas exports next to every operational grafikas view.

    Streamlit's dataframe toolbar exposes CSV only. This helper makes the same
    displayed grafikas downloadable as a formatted Excel failas as well, while
    retaining an explicit CSV option for users who prefer flat data.
    """
    if result is None:
        return
    excel_label=("ATSISIŲSTI EXCEL (.xlsx)" if lang=="LT" else "DOWNLOAD EXCEL (.xlsx)")
    csv_label=("ATSISIŲSTI CSV (.csv)" if lang=="LT" else "DOWNLOAD CSV (.csv)")
    c_excel,c_csv=st.columns(2)
    with c_excel:
        st.download_button(
            excel_label,
            build_xlsx(y,m,result,document_status=status_label,backup_rows_override=backup_rows_override),
            file_name=f"{file_prefix}_{y}_{m:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"{key_prefix}_xlsx_{y}_{m}",
        )
    with c_csv:
        st.download_button(
            csv_label,
            schedule_list_df(y,m,result).to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{file_prefix}_{y}_{m:02d}.csv",
            mime="text/csv",
            use_container_width=True,
            key=f"{key_prefix}_csv_{y}_{m}",
        )


def _truthy_cfg(value,default=False):
    if value is None or str(value).strip()=="": return bool(default)
    return str(value).strip().lower() in ("1","true","yes","on","y")

def smtp_config():
    return _smtp_config_core(config_value)

def smtp_diagnostics():
    cfg=smtp_config()
    return cfg,_smtp_missing_core(cfg)

def smtp_ready():
    _cfg,missing=smtp_diagnostics()
    return not missing

def smtp_probe():
    cfg,missing=smtp_diagnostics()
    if missing:
        return False,("Trūksta konfigūracijos: " if lang=="LT" else "Missing configuration: ")+", ".join(missing)
    return _smtp_probe_core(cfg)

def send_email(to_addr,subject,body,ics_bytes=None,ics_name=None):
    if not EMAIL_LIFECYCLE_ENABLED:
        return True,("EMAIL_DISABLED_V2_5_119" if lang=="EN" else "EMAIL_IŠJUNGTAS_V2_5_119")
    cfg,missing=smtp_diagnostics()
    if missing:
        detail=("El. pašto kanalas nesukonfigūruotas: " if lang=="LT" else "Email channel is not configured: ")+", ".join(missing)
        return False,detail
    return _send_email_core(cfg,to_addr,subject,body,ics_text=ics_bytes,ics_name=ics_name)

def deliver_lifecycle_notification(event_key,event_type,initials,y,m,to_email,subject,body,ics_bytes=None,ics_name=None):
    """Idempotent lifecycle delivery: durable DB outbox first, immediate SMTP second.

    If SMTP fails, the row remains FAILED and the background worker can retry it.
    If the event was already sent, reruns do not duplicate the email.
    """
    ics_text=None
    if ics_bytes is not None:
        ics_text=ics_bytes.decode("utf-8") if isinstance(ics_bytes,(bytes,bytearray)) else str(ics_bytes)
    row=db.enqueue_notification_v25100(
        event_key,event_type,initials,y,m,to_email,subject,body,
        scheduled_for=datetime.now(timezone.utc).isoformat(),ics_text=ics_text,ics_name=ics_name
    )
    if str(row.get("status") or "")=="sent":
        return True,"already sent"
    if not str(to_email or "").strip():
        return False,tr("missing_email")
    ok,detail=send_email(to_email,subject,body,ics_bytes,ics_name)
    try:
        db.mark_notification_delivery_v25100(int(row.get("id")),ok,detail)
    except Exception:
        pass
    return ok,detail

def retry_failed_lifecycle_notifications(y,m,event_types=None):
    if isinstance(event_types,str): event_types={event_types}
    elif event_types is not None: event_types=set(event_types)
    rows=db.failed_notification_outbox_v25100(y,m,100)
    if event_types is not None:
        rows=[r for r in rows if str(r.get("event_type") or "") in event_types]
    results=[]
    for row in rows:
        email=str(row.get("to_email") or "").strip()
        if not email:
            # Refresh from current resident settings before declaring it blocked.
            email=str((db.get_account_settings(str(row.get("initials") or "")) or {}).get("email") or "").strip()
            if email:
                row=db.enqueue_notification_v25100(
                    row.get("event_key"),row.get("event_type"),row.get("initials"),y,m,email,
                    row.get("subject") or "",row.get("body") or "",
                    scheduled_for=datetime.now(timezone.utc).isoformat(),ics_text=row.get("ics_text"),ics_name=row.get("ics_name")
                )
        if not email:
            results.append((row.get("initials"),"blocked",tr("missing_email"))); continue
        ics=(row.get("ics_text") or None)
        ok,detail=send_email(email,row.get("subject") or "",row.get("body") or "",ics,row.get("ics_name"))
        try: db.mark_notification_delivery_v25100(int(row.get("id")),ok,detail)
        except Exception: pass
        results.append((row.get("initials"),"sent" if ok else "failed",detail))
    return results

def send_backup_activation_email(y,m,result,backup_row):
    eff=backup_row.get("actual_backup") or backup_row.get("planned_backup")
    settings=db.get_account_settings(eff)
    if not settings.get("backup_email_alerts", True):
        return True, "alerts disabled"
    email=(settings.get("email") or "").strip()
    if not email:
        return False, tr("missing_email")
    slots={s.idx:s for s in make_slots(y,m)}
    sid=int(backup_row["covered_slot"]); s=slots.get(sid)
    covered=result.assignments.get(sid,"") if s else ""
    if not s:
        return False, "slot not found"
    subject=(f"Dublis aktyvuotas — {covered} — {s.department}" if lang=="LT" else f"Backup activated — {covered} — {s.department}")
    when=f"{y}-{m:02d}-{s.day:02d} · {block_label(s.block)}"
    body=(f"Sveiki,\n\nJūsų dublio pareiga aktyvuota.\n{when}\nDubliuojate: {covered}\nPadalinys: {s.department}\n\nPrašome susisiekti su seniūne / skyriumi ir patvirtinti veiksmus.\n"
          if lang=="LT" else
          f"Hello,\n\nYour backup duty has been activated.\n{when}\nCovered resident: {covered}\nDepartment: {s.department}\n\nPlease contact the senior scheduler / department and confirm next steps.\n")
    return send_email(email,subject,body)



def send_swap_request_email(y,m,request_row):
    """Best-effort operational email. DB request already exists before this runs."""
    target=str(request_row.get("person_b") or "")
    proposer=str(request_row.get("person_a") or "")
    request_id=int(request_row.get("id") or 0)
    settings=db.get_account_settings(target)
    email=(settings.get("email") or "").strip()
    kind=f"swap_request_{request_id}"
    send_date=date.today().isoformat()

    if not email:
        detail=tr("missing_email")
        try: db.record_email(target,kind,y,m,send_date,"failed",detail)
        except Exception: pass
        return False,detail

    slot_map={s.idx:s for s in make_slots(y,m)}
    sa=slot_map.get(int(request_row.get("slot_a") or -1))
    sb=slot_map.get(int(request_row.get("slot_b") or -1))
    subject=(
        f"Naujas apsikeitimo prašymas nuo {proposer}"
        if lang=="LT" else
        f"New swap request from {proposer}"
    )
    body=(
        f"Sveiki,\n\nGavote naują apsikeitimo prašymą nuo {proposer} ({_person_name(proposer)}).\n\n"
        f"Jis/ji siūlo: {_swap_shift_text(sa)}\n"
        f"Mainais prašo jūsų pamainos: {_swap_shift_text(sb)}\n\n"
        f"Prašymo DB numeris: #{request_id}\n"
        f"Prisijunkite prie Shift Happens → Apsikeitimai ir PRIIMKITE arba ATMESKITE prašymą.\n"
        if lang=="LT" else
        f"Hello,\n\nYou received a new swap request from {proposer} ({_person_name(proposer)}).\n\n"
        f"They offer: {_swap_shift_text(sa)}\n"
        f"They request your shift: {_swap_shift_text(sb)}\n\n"
        f"Database request number: #{request_id}\n"
        f"Open Shift Happens → Swaps and ACCEPT or REJECT the request.\n"
    )
    public=config_value("SCHEDULER_PUBLIC_URL","").strip()
    if public:
        body += (f"\nPortalas: {public}\n" if lang=="LT" else f"\nPortal: {public}\n")
    ok,detail=send_email(email,subject,body)
    try:
        db.record_email(target,kind,y,m,send_date,"sent" if ok else "failed",detail)
    except Exception:
        pass
    return ok,detail



def send_backup_swap_request_email(y,m,request_row):
    target=str(request_row.get("target") or "")
    proposer=str(request_row.get("requester") or "")
    request_id=int(request_row.get("id") or 0)
    settings=db.get_account_settings(target)
    email=(settings.get("email") or "").strip()
    kind=f"backup_swap_request_{request_id}"
    send_date=date.today().isoformat()

    if not email:
        detail=tr("missing_email")
        try: db.record_email(target,kind,y,m,send_date,"failed",detail)
        except Exception: pass
        return False,detail

    subject=(
        f"Naujas dublio apsikeitimo prašymas nuo {proposer}"
        if lang=="LT" else
        f"New backup swap request from {proposer}"
    )
    body=(
        f"Sveiki,\n\nGavote naują DUBLIO apsikeitimo prašymą nuo {proposer} ({_person_name(proposer)}).\n"
        f"Prašymo DB numeris: #{request_id}.\n\n"
        f"Prisijunkite prie Shift Happens → Apsikeitimai ir priimkite arba atmeskite prašymą.\n"
        if lang=="LT" else
        f"Hello,\n\nYou received a new BACKUP swap request from {proposer} ({_person_name(proposer)}).\n"
        f"Database request number: #{request_id}.\n\n"
        f"Open Shift Happens → Swaps and accept or reject the request.\n"
    )
    public=config_value("SCHEDULER_PUBLIC_URL","").strip()
    if public:
        body += (f"\nPortalas: {public}\n" if lang=="LT" else f"\nPortal: {public}\n")
    ok,detail=send_email(email,subject,body)
    try:
        db.record_email(target,kind,y,m,send_date,"sent" if ok else "failed",detail)
    except Exception:
        pass
    return ok,detail


def publication_emails(y,m,result):
    settings=db.all_account_settings(); results=[]; public=config_value("SCHEDULER_PUBLIC_URL","").strip()
    for p in DEFAULT_PEOPLE:
        i=p["initials"]; email=settings.get(i,{}).get("email","").strip(); send_date=date.today().isoformat()
        if not email: results.append((i,"skipped",tr("missing_email"))); continue
        subject=f"{month_label(y,m)} grafikas patvirtintas" if lang=="LT" else f"{month_label(y,m)} grafikas approved"
        body=(f"Sveiki,\n\nKito mėnesio tvarkaraštis patvirtintas. Prisegtame .ics faile yra jūsų normalios pamainos; dubliai įtraukiami tik jei tai įjungėte Nustatymuose. Atidarykite failą ir įsidėkite grafiką į savo kalendorių.\n" if lang=="LT" else f"Hello,\n\nThe next-month grafikas has been approved. The attached .ics file contains your normal shifts; backup duties are included only if you enabled them in Settings. Open it to add the grafikas to your calendar.\n")
        if public: body += (f"\nPortalas: {public}\n" if lang=="LT" else f"\nPortal: {public}\n")
        ok,detail=send_email(email,subject,body,build_ics(y,m,result,i),f"{safe_filename(i)}_{y}_{m:02d}.ics"); status="sent" if ok else "failed"; db.record_email(i,"publication",y,m,send_date,status,detail); results.append((i,status,detail))
    return results

def _parse_iso_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except Exception:
        return None


def _vilnius_now():
    return datetime.now(ZoneInfo("Europe/Vilnius"))


def render_live_cycle_countdown(y: int, m: int, *, operator: bool=False):
    """Minimalus automatinio ciklo laikmatis.

    Rodo tik dabartinio etapo pavadinimą ir likusį laiką. Leidimai ir etapai
    vis tiek valdomi duomenų bazėje; JavaScript naudojamas tik laikmačiui.
    """
    if not weekend_fcfs_backup_mode(y,m):
        return
    try:
        info=db.scheduler_cycle_phase_v25119(y,m) or {}
        lifecycle=db.get_schedule_lifecycle(y,m) or {}
    except Exception:
        return

    phase=str(info.get("phase") or "")
    if str(lifecycle.get("state") or "")=="final":
        components.html("""<!doctype html><html><head><meta charset=\"utf-8\"><style>
          body{margin:0;font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",Roboto,Helvetica,Arial,sans-serif;color:inherit;background:transparent}
          .box{border:1px solid rgba(128,128,128,.18);border-radius:9px;padding:12px 16px;box-sizing:border-box}
          .title{font-size:13px;font-weight:600;letter-spacing:.01em;opacity:.72}
        </style></head><body><div class=\"box\"><div class=\"title\">Galutinis grafikas paskelbtas</div></div></body></html>""",height=52,scrolling=False)
        return

    p_open=_parse_iso_dt(info.get("preference_open"))
    p_close=_parse_iso_dt(info.get("preference_close"))
    s_close=_parse_iso_dt(info.get("swap_close"))
    target=None
    if phase=="not_open":
        target=p_open
        title="Pageidavimų teikimas prasidės"
    elif phase=="preferences":
        target=p_close
        title="1 etapas · Pageidavimų teikimas"
    elif phase=="senior_build":
        target=_parse_iso_dt(info.get("swap_open"))
        title="2 etapas · Preliminaraus grafiko rengimas"
    elif phase=="swaps":
        target=s_close
        title="3 etapas · Apsikeitimai"
    else:
        components.html("""<!doctype html><html><head><meta charset=\"utf-8\"><style>
          body{margin:0;font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",Roboto,Helvetica,Arial,sans-serif;color:inherit;background:transparent}
          .box{border:1px solid rgba(128,128,128,.18);border-radius:9px;padding:12px 16px;box-sizing:border-box}
          .title{font-size:13px;font-weight:600;letter-spacing:.01em;opacity:.72}
        </style></head><body><div class=\"box\"><div class=\"title\">4 etapas · Galutinė peržiūra</div></div></body></html>""",height=52,scrolling=False)
        return

    if not target:
        return
    if target.tzinfo is None:
        target=target.replace(tzinfo=timezone.utc)
    target_iso=target.astimezone(timezone.utc).isoformat()
    uid=f"cycle_countdown_{y}_{m}_{phase}_{'op' if operator else 'res'}"
    components.html(f"""<!doctype html><html><head><meta charset=\"utf-8\"><style>
      body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",Roboto,Helvetica,Arial,sans-serif;color:inherit;background:transparent}}
      .box{{border:1px solid rgba(128,128,128,.18);border-radius:9px;padding:12px 16px 13px;box-sizing:border-box}}
      .title{{font-size:13px;font-weight:600;letter-spacing:.01em;opacity:.66;margin-bottom:5px}}
      .time{{font-size:30px;font-weight:650;letter-spacing:-.025em;line-height:1.03;font-variant-numeric:tabular-nums}}
    </style></head><body><div class=\"box\"><div class=\"title\">{html.escape(title)}</div><div id=\"{uid}\" class=\"time\">—</div></div>
    <script>
      const target = new Date({json.dumps(target_iso)}).getTime();
      const el = document.getElementById({json.dumps(uid)});
      function tick() {{
        let ms = Math.max(0, target - Date.now());
        const d = Math.floor(ms/86400000); ms %= 86400000;
        const h = Math.floor(ms/3600000); ms %= 3600000;
        const min = Math.floor(ms/60000); ms %= 60000;
        const sec = Math.floor(ms/1000);
        el.textContent = (d>0 ? d+' d. ' : '') + String(h).padStart(2,'0') + ':' + String(min).padStart(2,'0') + ':' + String(sec).padStart(2,'0');
      }}
      tick(); setInterval(tick,1000);
    </script></body></html>""",height=78,scrolling=False)


def _workflow_card(title,body,state="draft"):
    palette={
        "draft":("#E8F0FE","#174EA6","#8AB4F8"),
        "swap_open":("#FFF4E5","#8A4B08","#F6B26B"),
        "expired":("#FDECEC","#9C1C1C","#E57373"),
        "swap_closed":("#FFF8D9","#6B5600","#E4C441"),
        "final":("#E6F4EA","#176B36","#81C995"),
    }
    bg,fg,border=palette.get(state,palette["draft"])
    st.markdown(
        f"""<div style=\"border:2px solid {border};background:{bg};color:{fg};border-radius:16px;padding:16px 18px;margin:8px 0 14px 0;\">
        <div style=\"font-weight:800;font-size:1.05rem;letter-spacing:.02em;\">{html.escape(str(title))}</div>
        <div style=\"margin-top:6px;line-height:1.45;\">{html.escape(str(body))}</div></div>""",
        unsafe_allow_html=True,
    )


def _resident_email_preflight():
    settings=db.all_account_settings()
    missing=[]
    for pp in DEFAULT_PEOPLE:
        ini=pp["initials"]
        if not str((settings.get(ini,{}) or {}).get("email") or "").strip():
            missing.append(ini)
    return missing


def render_operator_email_smtp_admin(current_operator):
    """Compact operator email readiness UI; technical detail stays in Advanced mode."""
    settings=db.all_account_settings()
    missing=_resident_email_preflight()
    cfg,smtp_missing=smtp_diagnostics()
    ready=bool(not missing and not smtp_missing)

    with st.expander(
        "El. pašto kanalas" if lang=="LT" else "Email channel",
        expanded=not ready,
    ):
        if ready:
            st.success("El. pašto konfigūracija paruošta, o visi 16 rezidentų turi gavėjo adresą." if lang=="LT" else "Email configuration is present and all 16 residents have recipient addresses.")
        else:
            problems=[]
            if smtp_missing: problems.append("siuntėjo konfigūracija" if lang=="LT" else "sender configuration")
            if missing: problems.append(("gavėjo adresai: "+", ".join(missing)) if lang=="LT" else ("recipient addresses: "+", ".join(missing)))
            st.warning(("Dar neparuošta: " if lang=="LT" else "Not ready yet: ")+"; ".join(problems))

        if missing:
            if st.button(
                "UŽPILDYTI TRŪKSTAMUS IŠ PRISIJUNGIMO PASKYRŲ" if lang=="LT" else "FILL MISSING FROM LOGIN ACCOUNTS",
                use_container_width=True,key="autofill_notification_emails_v25100"
            ):
                try:
                    res=db.autofill_notification_emails_v2593()
                    st.success((f"Užpildyta: {int(res.get('filled',0))}." if lang=="LT" else f"Filled: {int(res.get('filled',0))}."))
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

            people_options=[pp["initials"] for pp in DEFAULT_PEOPLE]
            default_ini=missing[0] if missing else people_options[0]
            c1,c2=st.columns([1,2])
            with c1:
                email_ini=st.selectbox("Rezidentas" if lang=="LT" else "Resident",people_options,index=people_options.index(default_ini),key="operator_email_ini_v25100")
            with c2:
                existing_email=str((settings.get(email_ini,{}) or {}).get("email") or "").strip()
                email_value=st.text_input("Pranešimų el. paštas" if lang=="LT" else "Notification email",value=existing_email,key=f"operator_email_value_v25100_{email_ini}")
            if st.button("IŠSAUGOTI ADRESĄ" if lang=="LT" else "SAVE ADDRESS",use_container_width=True,key="operator_save_email_v25100"):
                if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+",email_value.strip()):
                    st.error("Neteisingas el. pašto formatas." if lang=="LT" else "Invalid email format.")
                else:
                    try:
                        db.set_resident_notification_email_v2593(email_ini,email_value.strip())
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))

        c1,c2=st.columns(2)
        with c1:
            if st.button("PATIKRINTI KANALĄ" if lang=="LT" else "CHECK CHANNEL",use_container_width=True,disabled=bool(smtp_missing),key="smtp_probe_v25100"):
                ok,detail=smtp_probe()
                st.session_state["_smtp_probe_v25100"]=(ok,detail,datetime.now().isoformat(timespec="seconds"))
        with c2:
            operator_email=str((settings.get(current_operator,{}) or {}).get("email") or "").strip()
            if st.button("SIŲSTI TESTĄ MAN" if lang=="LT" else "SEND TEST TO ME",use_container_width=True,disabled=bool(smtp_missing or not operator_email),key="smtp_test_v25100"):
                ok,detail=send_email(
                    operator_email,
                    "Shift Happens — el. pašto testas" if lang=="LT" else "Shift Happens — email test",
                    "Testas sėkmingas. Shift Happens gali siųsti realius grafiko pranešimus." if lang=="LT" else "Test successful. Shift Happens can send real grafikas notifications."
                )
                st.session_state["_smtp_probe_v25100"]=(ok,detail or "test email sent",datetime.now().isoformat(timespec="seconds"))

        probe=st.session_state.get("_smtp_probe_v25100")
        if probe:
            ok,detail,when=probe
            if ok: st.success(("Kanalas veikia ✓ · " if lang=="LT" else "Channel works ✓ · ")+when)
            else: st.error(("Kanalo patikra nepavyko: " if lang=="LT" else "Channel check failed: ")+str(detail))

        if advanced_mode:
            st.caption("Techninė konfigūracija" if lang=="LT" else "Technical configuration")
            smtp_rows=[
                {"Parametras" if lang=="LT" else "Setting":"Host","Reikšmė" if lang=="LT" else "Value":cfg.get("host") or "—"},
                {"Parametras" if lang=="LT" else "Setting":"Port","Reikšmė" if lang=="LT" else "Value":cfg.get("port")},
                {"Parametras" if lang=="LT" else "Setting":"From","Reikšmė" if lang=="LT" else "Value":cfg.get("from_email") or "—"},
                {"Parametras" if lang=="LT" else "Setting":"Login","Reikšmė" if lang=="LT" else "Value":cfg.get("user") or "—"},
                {"Parametras" if lang=="LT" else "Setting":"Security","Reikšmė" if lang=="LT" else "Value":"SSL" if cfg.get("use_ssl") else "STARTTLS" if cfg.get("use_tls") else "plain"},
            ]
            st.dataframe(pd.DataFrame(smtp_rows),use_container_width=True,hide_index=True)
            st.caption("Slaptažodis niekada nerodomas. Naudokite Streamlit Secrets [smtp] bloką; Gmail atveju — App Password, ne įprastą paskyros slaptažodį." if lang=="LT" else "The password is never displayed. Use the Streamlit Secrets [smtp] block; for Gmail use an App Password, not the normal account password.")

            try:
                audit=db.list_resident_email_admin_audit_v2593(30)
                if audit:
                    with st.expander("Adresų pakeitimų auditas" if lang=="LT" else "Address change audit",expanded=False):
                        rows=[]
                        for r in audit:
                            rows.append({
                                "Laikas" if lang=="LT" else "Time":r.get("created_at"),
                                "Rezidentas" if lang=="LT" else "Resident":r.get("initials"),
                                "Senas" if lang=="LT" else "Old":r.get("old_email"),
                                "Naujas" if lang=="LT" else "New":r.get("new_email"),
                                "Šaltinis" if lang=="LT" else "Source":r.get("source"),
                                "Operatorius" if lang=="LT" else "Operator":r.get("actor_initials"),
                            })
                        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
            except Exception:
                pass


def preferences_open_emails(y,m):
    settings=db.all_account_settings(); results=[]; public=config_value("SCHEDULER_PUBLIC_URL","").strip()
    cutoff_text=preference_cutoff_for(y,m).strftime("%Y-%m-%d %H:%M")
    for pp in DEFAULT_PEOPLE:
        i=pp["initials"]; email=str((settings.get(i,{}) or {}).get("email") or "").strip()
        subject=(f"{month_label(y,m)} pageidavimai atidaryti" if lang=="LT" else f"{month_label(y,m)} preferences are open")
        body=(
            f"Sveiki,\n\nAtidarytas {month_label(y,m)} grafiko pageidavimų etapas. "
            f"Pageidavimus pateikite iki {cutoff_text} Lietuvos laiku.\n"
            if lang=="LT" else
            f"Hello,\n\nThe {month_label(y,m)} preference stage is open. "
            f"Please submit your preferences by {cutoff_text} Lithuania time.\n"
        )
        if public: body += f"\nShift Happens: {public}\n"
        ok,detail=deliver_lifecycle_notification(
            f"preferences_open:{y}-{m:02d}","preferences_open",i,y,m,email,subject,body
        )
        results.append((i,"sent" if ok else "failed",detail))
    return results


def render_notification_delivery_status(y,m):
    """Lifecycle delivery dashboard: one compact table + retry only failures."""
    try:
        rows=db.notification_summary_v25100(y,m)
    except Exception as exc:
        if advanced_mode:
            st.caption(("Pranešimų outbox dar nepasiekiamas: " if lang=="LT" else "Notification outbox unavailable: ")+str(exc))
        return
    labels={
        "preferences_open":"Pageidavimai atidaryti" if lang=="LT" else "Preferences open",
        "preferences_reminder":"Pageidavimų priminimai" if lang=="LT" else "Preference reminders",
        "swap_open":"Apsikeitimų etapas" if lang=="LT" else "Swap stage",
        "final":"Galutinis grafikas paskelbtas" if lang=="LT" else "Done / FINAL",
    }
    st.markdown("#### Pranešimų etapai" if lang=="LT" else "#### Notification stages")
    if not rows:
        st.caption("Šiam mėnesiui dar nėra išsiųstų etapų pranešimų." if lang=="LT" else "No lifecycle notifications have been sent for this month yet.")
    else:
        view=[]
        for r in rows:
            view.append({
                "Etapas" if lang=="LT" else "Stage":labels.get(r.get("event_type"),r.get("event_type")),
                "Išsiųsta" if lang=="LT" else "Sent":int(r.get("sent",0)),
                "Laukia" if lang=="LT" else "Laukia":int(r.get("pending",0)),
                "Nepavyko" if lang=="LT" else "Failed":int(r.get("failed",0))+int(r.get("blocked",0)),
                "Iš viso" if lang=="LT" else "Total":int(r.get("total",0)),
            })
        st.dataframe(pd.DataFrame(view),use_container_width=True,hide_index=True)

    failed=db.failed_notification_outbox_v25100(y,m,100)
    if failed:
        st.warning((f"Nepavykusių / užblokuotų pranešimų: {len(failed)}." if lang=="LT" else f"Failed / blocked notifications: {len(failed)}."))
        failed_types=sorted({str(r.get("event_type") or "other") for r in failed})
        chosen=st.selectbox(
            "Kurį etapą kartoti" if lang=="LT" else "Stage to retry",failed_types,
            format_func=lambda x:labels.get(x,x),key=f"retry_notification_type_{y}_{m}"
        )
        if st.button("PAKARTOTI TIK ŠIO ETAPO NEPAVYKUSIEMS" if lang=="LT" else "RETRY FAILED RECIPIENTS FOR THIS STAGE",use_container_width=True,key=f"retry_notifications_{y}_{m}"):
            res=retry_failed_lifecycle_notifications(y,m,chosen)
            if res: st.dataframe(localized_delivery_rows(res),use_container_width=True,hide_index=True)
            else: st.success("Nebėra ką kartoti." if lang=="LT" else "Nothing left to retry.")

def _manual_override_diff_rows(record,y,m):
    slots={s.idx:s for s in make_slots(y,m)}
    before=deserialize_result(record.get("before_json")) if record.get("before_json") else None
    after=deserialize_result(record.get("after_json")) if record.get("after_json") else None
    rows=[]
    for sid in (int(record.get("slot_a",0)),int(record.get("slot_b",0))):
        sl=slots.get(sid)
        if not sl: continue
        rows.append({
            "Data / postas" if lang=="LT" else "Date / post":f"{y}-{m:02d}-{sl.day:02d} · {sl.department} · {block_label(sl.block)}",
            "Prieš" if lang=="LT" else "Before":(before.assignments.get(sid) if before else "—"),
            "Po" if lang=="LT" else "After":(after.assignments.get(sid) if after else "—"),
        })
    return rows


def render_manual_override_review_checkpoint(y,m):
    """Persistent checkpoint: manual changes must be reviewed before PRELIMINARY or FINAL."""
    pending=db.list_unreviewed_manual_overrides_v2593(y,m)
    if not pending:
        return 0
    _workflow_card(
        "REIKIA PERŽIŪRĖTI RANKINIUS PAKEITIMUS" if lang=="LT" else "MANUAL CHANGES REQUIRE REVIEW",
        (f"Neperžiūrėtų pakeitimų: {len(pending)}. Kitas etapas ir FINAL užblokuoti, kol patvirtinsite pokyčių peržiūrą." if lang=="LT" else f"Unreviewed changes: {len(pending)}. The next phase and FINAL are blocked until the changes are reviewed."),
        "expired"
    )
    current_payload=db.load_schedule(y,m,"current")
    current_result=refresh_result_payload(current_payload,y,m,use_actual_backups=True) if current_payload else None
    hard=int(((current_result.stats or {}).get("global",{}) if current_result else {}).get("hard_errors",999))
    if hard==0:
        st.success("Dabartinis ACTUAL po korekcijų: HARD klaidų 0." if lang=="LT" else "Current ACTUAL after corrections: 0 HARD errors.")
    else:
        st.error((f"Dabartinis ACTUAL po korekcijų turi HARD klaidų: {hard}." if lang=="LT" else f"Current ACTUAL after corrections has HARD errors: {hard}."))
    for r in pending:
        with st.container(border=True):
            st.markdown(f"**#{r.get('id')} · {r.get('person_a')} ↔ {r.get('person_b')}**")
            st.caption(f"{r.get('created_at')} · {r.get('actor_initials')} · {r.get('reason')}")
            diff=_manual_override_diff_rows(r,y,m)
            if diff: st.dataframe(pd.DataFrame(diff),use_container_width=True,hide_index=True)
            ack=st.checkbox(
                "Peržiūrėjau pakeitimą ir dabartinį ACTUAL rezultatą." if lang=="LT" else "I reviewed this change and the current ACTUAL result.",
                key=f"review_override_ack_{r.get('id')}"
            )
            if st.button(
                "PATVIRTINTI POKYČIO PERŽIŪRĄ" if lang=="LT" else "CONFIRM CHANGE REVIEW",
                use_container_width=True,disabled=not ack,key=f"review_override_btn_{r.get('id')}"
            ):
                try:
                    db.review_manual_override_v2593(int(r["id"]))
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
    return len(pending)


def swap_window_open_emails(y,m,result,deadline,window_days):
    settings=db.all_account_settings(); results=[]; public=config_value("SCHEDULER_PUBLIC_URL","").strip()
    local_deadline=deadline.astimezone(ZoneInfo("Europe/Vilnius")) if deadline.tzinfo else deadline.replace(tzinfo=ZoneInfo("Europe/Vilnius"))
    deadline_text=local_deadline.strftime("%Y-%m-%d %H:%M")
    for pp in DEFAULT_PEOPLE:
        i=pp["initials"]; email=str((settings.get(i,{}) or {}).get("email") or "").strip(); send_date=date.today().isoformat(); kind=f"preliminary_swap_window_{y}_{m:02d}"
        if not email:
            detail=tr("missing_email")
            try: db.record_email(i,kind,y,m,send_date,"failed",detail)
            except Exception: pass
            results.append((i,"failed",detail)); continue
        subject=(f"Preliminarus {month_label(y,m)} grafikas paskelbtas" if lang=="LT" else f"Preliminary {month_label(y,m)} grafikas published")
        body=(
            f"Sveiki,\n\nPreliminarus {month_label(y,m)} grafikas paskelbtas. "
            f"Individualius apsikeitimo prašymus galite pateikti sistemoje iki {deadline_text} Lietuvos laiku.\n\n"
            f"Po termino naujų apsikeitimo prašymų teikti nebus galima, išskyrus individualų administratoriaus suteiktą leidimą. "
            f"Galutinė versija bus paskelbta atskiru pranešimu.\n"
            if lang=="LT" else
            f"Hello,\n\nThe preliminary {month_label(y,m)} grafikas has been published. "
            f"Individual swap requests may be submitted in the system until {deadline_text} Lithuania time.\n\n"
            f"After the deadline, new swap requests are closed unless individual late access is granted by an operator. "
            f"The final version will be announced separately.\n"
        )
        if public: body += (f"\nPortalas: {public}\n" if lang=="LT" else f"\nPortal: {public}\n")
        ok,detail=deliver_lifecycle_notification(
            f"swap_open:{y}-{m:02d}","swap_open",i,y,m,email,subject,body,
            build_ics(y,m,result,i),f"PRELIMINARUS_{safe_filename(i)}_{y}_{m:02d}.ics"
        )
        try: db.record_email(i,kind,y,m,send_date,"sent" if ok else "failed",detail)
        except Exception: pass
        results.append((i,"sent" if ok else "failed",detail))
    return results


def late_swap_access_email(y,m,grant):
    initials=str(grant.get("initials") or ""); settings=db.get_account_settings(initials); email=str(settings.get("email") or "").strip()
    if not email: return False,tr("missing_email")
    exp=_parse_iso_dt(grant.get("expires_at")); exp_local=exp.astimezone(ZoneInfo("Europe/Vilnius")) if exp else None
    exp_text=exp_local.strftime("%Y-%m-%d %H:%M") if exp_local else str(grant.get("expires_at") or "")
    remaining=max(0,int(grant.get("max_requests",1) or 1)-int(grant.get("requests_used",0) or 0))
    subject=(f"Suteikta papildoma apsikeitimo prieiga — iki {exp_text}" if lang=="LT" else f"Additional swap access granted — until {exp_text}")
    body=(f"Sveiki,\n\nJums suteikta individuali papildoma apsikeitimo prieiga {month_label(y,m)} grafikui.\nGalioja iki: {exp_text}.\nGalite sukurti iki {remaining} naujo(-ų) apsikeitimo prašymo(-ų).\nPrisijunkite į Shift Happens → Apsikeitimai.\n" if lang=="LT" else f"Hello,\n\nYou have been granted individual additional swap access for the {month_label(y,m)} schedule.\nValid until: {exp_text}.\nYou may create up to {remaining} new swap request(s).\nOpen Shift Happens → Swaps.\n")
    public=config_value("SCHEDULER_PUBLIC_URL","").strip()
    if public: body += (f"\nPortalas: {public}\n" if lang=="LT" else f"\nPortal: {public}\n")
    ok,detail=send_email(email,subject,body)
    try: db.record_email(initials,f"late_swap_access_{grant.get('id','')}",y,m,date.today().isoformat(),"sent" if ok else "failed",detail)
    except Exception: pass
    return ok,detail


def final_schedule_emails(y,m,result):
    settings=db.all_account_settings(); results=[]; public=config_value("SCHEDULER_PUBLIC_URL","").strip()
    for pp in DEFAULT_PEOPLE:
        i=pp["initials"]; email=str((settings.get(i,{}) or {}).get("email") or "").strip(); kind=f"final_schedule_{y}_{m:02d}"; send_date=date.today().isoformat()
        if not email:
            results.append((i,"failed",tr("missing_email"))); continue
        subject=(f"Galutinis {month_label(y,m)} grafikas paskelbtas" if lang=="LT" else f"Final {month_label(y,m)} grafikas published")
        body=(
            f"Sveiki,\n\nGalutinis {month_label(y,m)} tvarkaraštis paskelbtas ir pateiktas administracijai. "
            f"Įprasti ir pavėluoti apsikeitimai uždaryti.\n\nPrisegtas jūsų galutinis .ics grafikas.\n"
            if lang=="LT" else
            f"Hello,\n\nThe final {month_label(y,m)} grafikas has been published and submitted to administration. "
            f"Ordinary and late swaps are now closed.\n\nYour final .ics grafikas is attached.\n"
        )
        if public: body += (f"\nPortalas: {public}\n" if lang=="LT" else f"\nPortal: {public}\n")
        ok,detail=deliver_lifecycle_notification(
            f"final:{y}-{m:02d}","final",i,y,m,email,subject,body,
            build_ics(y,m,result,i),f"FINAL_{safe_filename(i)}_{y}_{m:02d}.ics"
        )
        try: db.record_email(i,kind,y,m,send_date,"sent" if ok else "failed",detail)
        except Exception: pass
        results.append((i,"sent" if ok else "failed",detail))
    return results


def preliminary_swap_window_for(y,m):
    """Rezidentų apsikeitimų langas: ankstesnio mėnesio 15 d. 00:00 → 16 d. 00:00."""
    if m==1:
        cy,cm=y-1,12
    else:
        cy,cm=y,m-1
    return datetime(cy,cm,15,0,0,tzinfo=ZoneInfo("Europe/Vilnius")), swap_window_close_for(y,m)


def manual_override_emails(y,m,result,initials_list):
    settings=db.all_account_settings(); results=[]; public=config_value("SCHEDULER_PUBLIC_URL","").strip()
    for i in dict.fromkeys(str(x) for x in initials_list if x):
        email=str((settings.get(i,{}) or {}).get("email") or "").strip(); kind=f"manual_schedule_override_{y}_{m:02d}"; send_date=date.today().isoformat()
        if not email:
            results.append((i,"failed",tr("missing_email"))); continue
        subject=(f"{month_label(y,m)} grafiko korekcija" if lang=="LT" else f"{month_label(y,m)} grafikas correction")
        body=(
            f"Sveiki,\n\nTvarkaraščio administratorius atliko rankinę {month_label(y,m)} grafiko korekciją, kuri palietė jūsų pamainas. "
            f"Patikrinkite atnaujintą grafiką sistemoje. Prisegtas atnaujintas .ics failas.\n"
            if lang=="LT" else
            f"Hello,\n\nA grafikas operator made a manual correction to the {month_label(y,m)} grafikas affecting your shifts. "
            f"Please review the updated grafikas in the system. An updated .ics file is attached.\n"
        )
        if public: body += (f"\nPortalas: {public}\n" if lang=="LT" else f"\nPortal: {public}\n")
        ok,detail=send_email(email,subject,body,build_ics(y,m,result,i),f"ATNAUJINTAS_{safe_filename(i)}_{y}_{m:02d}.ics")
        try: db.record_email(i,kind,y,m,send_date,"sent" if ok else "failed",detail)
        except Exception: pass
        results.append((i,"sent" if ok else "failed",detail))
    return results


def publish_system_baseline_for_swap_window(y,m):
    """Validate the draft, freeze SYSTEM/ACTUAL, backups and fairness history. No email is sent here."""
    draft_payload=db.load_schedule(y,m,"draft")
    if not draft_payload:
        return {"ok":False,"error":tr("no_draft")}
    credit_err=credit_selection_errors(y,m)
    if credit_err:
        return {"ok":False,"error":tr("bonus_insufficient"),"rows":credit_err}
    # V2.5.150: existence in DB is never enough. Publication starts with the
    # same fail-closed CURRENT-engine compatibility gate used by the generation UI.
    draft_health=draft_compatibility_status(draft_payload,y,m)
    if not draft_health.get("publishable"):
        return {
            "ok":False,
            "error":(
                "NEGALIOJANTIS / LEGACY JUODRAŠTIS — dabartinis engine jo skelbti neleidžia. Sugeneruokite naują 0-HARD juodraštį."
                if lang=="LT" else
                "INVALID / LEGACY DRAFT — the current engine blocks publication. Generate a new zero-HARD draft."
            ),
            "rows":draft_health.get("rows") or [],
            "draft_health":draft_health.get("kind"),
        }
    draft_result=draft_health.get("result") or refresh_result_payload(draft_payload,y,m,use_actual_backups=False)
    current_people=load_people(y,m); expected_targets=calculate_targets(y,m,current_people)
    current_snapshot=serialize_people_request_snapshot(current_people)
    if expected_targets!=draft_result.targets or (draft_result.request_snapshot and current_snapshot!=draft_result.request_snapshot):
        return {"ok":False,"error":tr("draft_outdated")}
    frozen_people=people_from_request_snapshot(draft_result.request_snapshot) or current_people
    # V2.5.115: validate the NORMAL grafikas independently of theoretical backups.
    revalidated=validate_schedule(y,m,current_people,make_slots(y,m),draft_result.assignments,expected_targets,satisfaction_people=frozen_people,backup_assignments=[])
    if revalidated["global"].get("hard_errors",0):
        return {"ok":False,"error":tr("draft_outdated"),"rows":revalidated["global"].get("errors",[])}
    draft_result.targets=expected_targets
    desired,backup_errors=plan_backups(y,m,draft_result)
    # V2.5.119: dubliai are an independent mandatory standby layer. During the
    # 14→16 swap phase that layer may still be incomplete because residents can
    # keep choosing their one FCFS slot. This must NEVER block publishing the
    # NORMAL preliminary grafikas or its swaps. Missing dubliai are auto-randomized
    # at day 16 and then reviewed by SP.
    draft_result.backup_snapshot=[dict(x) for x in desired]
    draft_result=revalidate_loaded_result(y,m,current_people,draft_result,backup_assignments=[])
    _pgg=draft_result.stats.setdefault("global",{})
    _pgg["theoretical_backup_layer"]=True
    _pgg["theoretical_backup_layer_errors"]=list(backup_errors)
    _pgg["theoretical_backup_layer_complete"]=(len(backup_errors)==0)
    if draft_result.stats.get("global",{}).get("hard_errors",0):
        return {"ok":False,"error":tr("draft_outdated"),"rows":draft_result.stats["global"].get("errors",[])}
    db.save_draft(y,m,serialize_result(draft_result))
    if not db.publish_draft(y,m):
        return {"ok":False,"error":tr("no_draft")}
    db.sync_backups(y,m,desired)
    payload=db.load_schedule(y,m,"current"); result=refresh_result_payload(payload,y,m,use_actual_backups=True)
    db.save_current(y,m,serialize_result(result))
    baseline=deserialize_result(db.load_schedule(y,m,"baseline"))
    db.sync_fairness_history(y,m,baseline.stats["people"])
    feeds=refresh_calendar_subscription_feeds()
    return {"ok":True,"result":result,"feeds":feeds}


def render_operator_manual_override(y,m,current_payload,lifecycle_state):
    """Direct SP/ŠR pre-FINAL ACTUAL correction tool.

    Resident consent is not required, but ACTUAL safety/coverage HARD checks remain
    mandatory. SYSTEM is never rewritten by this tool.
    """
    st.markdown("### Seniūnės / administratoriaus rankinis koregavimas" if lang=="LT" else "### Operator manual correction")
    st.caption(
        "Galima naudoti bet kuriuo metu iki FINAL. Keičiama tik ACTUAL versija; užšaldytas SYSTEM lieka nepakeistas tyrimui. "
        "Rezidentų sutikimas šiam administraciniam veiksmui nereikalingas, tačiau saugos ir operacinės HARD taisyklės neapeinamos."
        if lang=="LT" else
        "Available at any time before FINAL. Only ACTUAL changes; the frozen SYSTEM baseline remains unchanged for research. "
        "Resident consent is not required for this administrative action, but safety and operational HARD rules cannot be bypassed."
    )
    if lifecycle_state=="final":
        st.info("FINAL versija užrakinta — rankinis koregavimas nebegalimas." if lang=="LT" else "The FINAL version is locked — manual correction is no longer available.")
        return
    if not current_payload:
        st.info(
            "Norint pradėti rankinį koregavimą, pirmiausia reikia užšaldyti sugeneruotą SYSTEM kaip pradinę ACTUAL versiją. El. laiškai šiame žingsnyje nesiunčiami."
            if lang=="LT" else
            "To begin manual correction, first freeze the generated SYSTEM as the initial ACTUAL version. No email is sent at this step."
        )
        return

    fresh=refresh_result_payload(current_payload,y,m)
    slots={s.idx:s for s in make_slots(y,m)}
    assigned=[sid for sid in fresh.assignments if sid in slots]
    assigned.sort(key=lambda sid:(slots[sid].day,{"AM":0,"FULL":1,"PM":2}.get(slots[sid].block,9),slots[sid].department,sid))
    if len(assigned)<2:
        st.warning("Nepakanka dviejų užpildytų pamainų apsikeitimui." if lang=="LT" else "At least two filled shifts are required.")
        return

    def slot_label(sid):
        sl=slots[int(sid)]; who=fresh.assignments.get(int(sid),"—")
        return f"{sl.day:02d} · {sl.department} · {block_label(sl.block)} · {who}"

    c1,c2=st.columns(2)
    with c1:
        sid_a=int(st.selectbox("Pirma pamaina" if lang=="LT" else "First shift",assigned,format_func=slot_label,key=f"op_manual_a_{y}_{m}"))
    with c2:
        choices_b=[x for x in assigned if int(x)!=sid_a]
        sid_b=int(st.selectbox("Antra pamaina" if lang=="LT" else "Second shift",choices_b,format_func=slot_label,key=f"op_manual_b_{y}_{m}"))
    person_a=str(fresh.assignments.get(sid_a) or "")
    person_b=str(fresh.assignments.get(sid_b) or "")
    reason=st.text_input("Koregavimo priežastis (privaloma auditui)" if lang=="LT" else "Correction reason (required for audit)",key=f"op_manual_reason_{y}_{m}")

    ok,msg,pstats,needed=preview_swap(
        y,m,people_for_stored_result(fresh,y,m),fresh,sid_a,sid_b,
        backup_assignments=db.list_backups(y,m)
    )
    if not ok:
        st.error(("Koregavimas negalimas: " if lang=="LT" else "Correction blocked: ")+str(msg))
        block_rows=((pstats or {}).get("global",{}) or {}).get("swap_hard_block_rows") or []
        if block_rows:
            st.dataframe(pd.DataFrame(block_rows),use_container_width=True,hide_index=True)
        return

    p1,p2=st.columns(2)
    with p1:
        st.markdown(f"**{person_a} → {slot_label(sid_b).rsplit(' · ',1)[0]}**")
    with p2:
        st.markdown(f"**{person_b} → {slot_label(sid_a).rsplit(' · ',1)[0]}**")
    warnings=((pstats or {}).get("global",{}) or {}).get("swap_warning_rows") or {}
    warning_rows=[]
    for who,rows in warnings.items():
        for row in (rows or []):
            rr=dict(row); rr.setdefault("resident",who); warning_rows.append(rr)
    if warning_rows:
        st.warning("Yra pasekmių įspėjimų. Administratorius gali tęsti tik aiškiai juos patvirtinęs." if lang=="LT" else "There are consequence warnings. The operator may continue only after explicit acknowledgement.")
        st.dataframe(pd.DataFrame(warning_rows),use_container_width=True,hide_index=True)

    ack=st.checkbox(
        "Patvirtinu šią rankinę korekciją ir jos parodytas pasekmes." if lang=="LT" else "I confirm this manual correction and the displayed consequences.",
        key=f"op_manual_ack_{y}_{m}_{sid_a}_{sid_b}"
    )
    affected_settings=db.all_account_settings()
    affected_missing=[who for who in (person_a,person_b) if not str((affected_settings.get(who,{}) or {}).get("email") or "").strip()]
    can_apply=bool(reason.strip() and ack)
    # Email is not an operational dependency. In-app/push will replace it in RAPA.
    if st.button("PRITAIKYTI RANKINĘ KOREKCIJĄ" if lang=="LT" else "APPLY MANUAL CORRECTION",type="primary",use_container_width=True,disabled=not can_apply,key=f"op_manual_apply_{y}_{m}_{sid_a}_{sid_b}"):
        try:
            apply_result=refresh_result_payload(db.load_schedule(y,m,"current"),y,m)
            if apply_result.assignments.get(sid_a)!=person_a or apply_result.assignments.get(sid_b)!=person_b:
                st.error("Grafikas pasikeitė po peržiūros. Pasirinkite pamainas iš naujo." if lang=="LT" else "The grafikas changed after preview. Select the shifts again.")
                st.stop()
            ok2,msg2,_=attempt_swap(
                y,m,people_for_stored_result(apply_result,y,m),apply_result,sid_a,sid_b,
                backup_assignments=db.list_backups(y,m),acknowledged_fingerprints=needed
            )
            if not ok2:
                st.error(("Koregavimas nebetaikomas: " if lang=="LT" else "Correction no longer applies: ")+str(msg2)); st.stop()
            db.apply_manual_schedule_override_v2592(
                y,m,serialize_result(apply_result),sid_a,sid_b,person_a,person_b,reason.strip()
            )
            sync_backup_plan(y,m,apply_result)
            persist_actual_satisfaction(y,m)
            refresh_calendar_subscription_feeds([person_a,person_b])
            mails=manual_override_emails(y,m,apply_result,[person_a,person_b])
            failed=[x for x in mails if x[1]!="sent"]
            st.session_state["_finalization_flash"]=(
                "warning" if failed else "success",
                (f"Rankinė korekcija pritaikyta. Pranešimai: {len(mails)-len(failed)}/{len(mails)} išsiųsta."
                 if lang=="LT" else
                 f"Manual correction applied. Notifications: {len(mails)-len(failed)}/{len(mails)} sent.")
            )
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    history=db.list_manual_schedule_overrides_v2592(y,m)
    if history:
        with st.expander("Rankinių korekcijų auditas" if lang=="LT" else "Manual correction audit",expanded=False):
            rows=[]
            for r in history[:20]:
                rows.append({
                    ("Laikas" if lang=="LT" else "Time"):r.get("created_at"),
                    ("Operatorius" if lang=="LT" else "Operator"):r.get("actor_initials"),
                    ("Pakeitimas" if lang=="LT" else "Change"):f"{r.get('person_a')} ↔ {r.get('person_b')}",
                    ("Slotai" if lang=="LT" else "Slots"):f"#{r.get('slot_a')} ↔ #{r.get('slot_b')}",
                    ("Priežastis" if lang=="LT" else "Reason"):r.get("reason"),
                })
            st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)


def _lt_days_left_phrase(n: int) -> str:
    n=int(n)
    if n==1:
        return "1 diena"
    if 2<=n<=9:
        return f"{n} dienos"
    return f"{n} dienų"


def send_due_reminders(y,m):
    """Manual fallback for today's preference reminder queue.

    The background worker performs the same check automatically. One consolidated
    reminder replaces the old duplicate preference + backup-claim reminder pair.
    """
    dl=deadline_for(y,m); today=date.today(); prefs=db.all_preferences(y,m); settings=db.all_account_settings(); results=[]
    for p in DEFAULT_PEOPLE:
        i=p["initials"]; s=settings.get(i,{})
        if i in prefs or not s.get("notifications_on",True):
            continue
        start_day=max(1,min(deadline_day(),int(s.get("reminder_start_day",8) or 8)))
        start=date(dl.year,dl.month,start_day)
        if not (start<=today<=dl):
            continue
        email=str(s.get("email") or "").strip()
        left=max(0,(dl-today).days)
        cutoff_text=preference_cutoff_for(y,m).strftime("%Y-%m-%d %H:%M")
        subject=(
            f"Šiandien paskutinė diena pateikti {month_label(y,m)} pageidavimus"
            if lang=="LT" and left==0 else
            f"Liko {_lt_days_left_phrase(left)} iki {month_label(y,m)} pageidavimų pateikimo pabaigos"
            if lang=="LT" else
            f"Today is the last day to submit {month_label(y,m)} preferences"
            if left==0 else
            f"{left} day(s) left to submit {month_label(y,m)} preferences"
        )
        body=(
            f"Sveiki,\n\nJūsų {month_label(y,m)} pageidavimai dar nepateikti. Tikslus terminas: {cutoff_text} Lietuvos laiku.\n"
            if lang=="LT" else
            f"Hello,\n\nYour {month_label(y,m)} preferences have not been submitted. Exact deadline: {cutoff_text} Lithuania time.\n"
        )
        public=config_value("SCHEDULER_PUBLIC_URL","").strip()
        if public:
            body += (f"\nShift Happens: {public}\n")
        ok,detail=deliver_lifecycle_notification(
            f"preferences_reminder:{y}-{m:02d}:{today.isoformat()}",
            "preferences_reminder",i,y,m,email,subject,body
        )
        try:
            db.record_email(i,"reminder",y,m,today.isoformat(),"sent" if ok else "failed",detail)
        except Exception:
            pass
        results.append((i,"sent" if ok else "failed",detail))
    return results


def balance_ratio(a,b):
    if a is None or b is None: return None
    a=float(a); b=float(b)
    if max(a,b)==0: return 1.0
    return round(min(a,b)/max(a,b),2)

def _fairness_from_spreads(w,f,d,wd):
    return max(0.0,100.0-18.0*w-7.0*f-4.0*d-2.0*wd)


def fairness_trend_df(rows):
    """Build monthly and cumulative fairness history from finalized monthly ledger rows."""
    if not rows:
        return pd.DataFrame()
    periods=sorted({(int(r["year"]),int(r["month"])) for r in rows})
    initials=sorted({r["initials"] for r in rows})
    cumulative={i:{"weekend":0,"friday":0,"double":0,"weekday_day":0} for i in initials}
    out=[]
    for y,m in periods:
        month_rows=[r for r in rows if int(r["year"])==y and int(r["month"])==m]
        by={r["initials"]:r for r in month_rows}
        monthly_vals={k:[] for k in ("weekend","friday","double","weekday_day")}
        for i in initials:
            r=by.get(i,{})
            vals={
                "weekend":int(r.get("weekend_assignments",0)),
                "friday":int(r.get("friday_assignments",0)),
                "double":int(r.get("doubles",0)),
                "weekday_day":int(r.get("weekday_days",0)),
            }
            for k,v in vals.items():
                monthly_vals[k].append(v)
                cumulative[i][k]+=v
        def spread(vals): return max(vals)-min(vals) if vals else 0
        mw,mf,md,mwd=[spread(monthly_vals[k]) for k in ("weekend","friday","double","weekday_day")]
        cw=spread([cumulative[i]["weekend"] for i in initials])
        cf=spread([cumulative[i]["friday"] for i in initials])
        cd=spread([cumulative[i]["double"] for i in initials])
        cwd=spread([cumulative[i]["weekday_day"] for i in initials])
        out.append({
            "Period":f"{y}-{m:02d}",
            "Monthly fairness":round(_fairness_from_spreads(mw,mf,md,mwd),1),
            "Cumulative fairness":round(_fairness_from_spreads(cw,cf,cd,cwd),1),
        })
    return pd.DataFrame(out)


def live_fairness_snapshot(y,m,result,include_completed_covers=True):
    """Live monthly real-work fairness; never used as future solver input."""
    if result is None:
        return {"people":{},"effective_assignments":{},"global":{}}
    backups=[]
    if include_completed_covers:
        try:
            backups=db.list_backups(y,m)
        except Exception:
            backups=[]
    return calculate_live_fairness_snapshot(
        y,m,result.assignments,
        people_initials=[p["initials"] for p in DEFAULT_PEOPLE],
        backup_assignments=backups,
    )


def system_actual_fairness_trend_df(up_to_year=None,up_to_month=None):
    """Monthly SYSTEM vs ACTUAL fairness history; descriptive only."""
    try:
        rows=db.list_published_schedules()
    except Exception:
        return pd.DataFrame()
    limit=(int(up_to_year)*12+int(up_to_month)) if up_to_year is not None and up_to_month is not None else None
    out=[]
    ids=[p["initials"] for p in DEFAULT_PEOPLE]
    for r in rows:
        y=int(r.get("year",0)); m=int(r.get("month",0))
        if limit is not None and y*12+m>limit:
            continue
        try:
            cp=r.get("current_json") or {}
            bp=r.get("baseline_json") or cp
            cr=deserialize_result(cp); br=deserialize_result(bp)
            backups=db.list_backups(y,m)
            sg=calculate_live_fairness_snapshot(y,m,br.assignments,people_initials=ids,backup_assignments=[])["global"]
            ag=calculate_live_fairness_snapshot(y,m,cr.assignments,people_initials=ids,backup_assignments=backups)["global"]
            out.append({
                "Period":f"{y}-{m:02d}",
                "SYSTEM monthly fairness":float(sg.get("monthly_fairness_score",0.0)),
                "ACTUAL monthly fairness":float(ag.get("monthly_fairness_score",0.0)),
                "Delta (ACTUAL-SYSTEM)":round(float(ag.get("monthly_fairness_score",0.0))-float(sg.get("monthly_fairness_score",0.0)),1),
                "SYSTEM post imbalance":int(sg.get("rotation_monthly_imbalance",0)),
                "ACTUAL post imbalance":int(ag.get("rotation_monthly_imbalance",0)),
                "Completed covers":int(ag.get("completed_cover_transfers",0)),
            })
        except Exception:
            continue
    return pd.DataFrame(out)


def actual_workplace_exposure_df(y,m,result):
    snap=live_fairness_snapshot(y,m,result,include_completed_covers=True)
    view=deepcopy(result)
    view.assignments=dict(snap.get("effective_assignments") or result.assignments)
    return workplace_exposure_df(y,m,view)


def component_status(score):
    if score is None: return tr("not_applicable")
    if score>=80: return tr("matches")
    if score>=50: return tr("partial")
    return tr("mismatch")

def localized_delivery_rows(rows):
    smap={"sent":tr("sent"),"failed":tr("failed"),"skipped":tr("skipped")}
    return pd.DataFrame([(i,smap.get(status,status),detail) for i,status,detail in rows], columns=[tr("person"),tr("status"),tr("details")])

def localized_email_log(rows):
    smap={"sent":tr("sent"),"failed":tr("failed"),"skipped":tr("skipped")}
    kmap={"reminder":tr("reminder_kind"),"publication":tr("publication_kind"),"backup_claim_reminder":tr("backup_claim_reminder_kind")}
    return pd.DataFrame([{
        "ID":r["id"], tr("person"):r["initials"], tr("details"):kmap.get(r["kind"],r["kind"]),
        tr("date"):r["send_date"], tr("status"):smap.get(r["status"],r["status"]),
        tr("comment"):r["detail"], tr("updated"):r["sent_at"]
    } for r in rows])

# --- Identity, role and month ---
st.sidebar.title("Shift Happens"); st.sidebar.caption("PGY-1 Radiology")

def observer_assignment_changes_df(y,m,baseline,current):
    if baseline is None or current is None:
        return pd.DataFrame()
    slots={s.idx:s for s in make_slots(y,m)}
    rows=[]
    all_ids=sorted(set(baseline.assignments)|set(current.assignments))
    for sid in all_ids:
        before=baseline.assignments.get(sid,"")
        after=current.assignments.get(sid,"")
        if before==after:
            continue
        s=slots.get(sid)
        if s is None:
            continue
        rows.append({
            tr("date"):f"{y}-{m:02d}-{s.day:02d}",
            tr("department"):s.department,
            tr("shift"):block_label(s.block),
            tr("observer_from"):before or "—",
            tr("observer_to"):after or "—",
        })
    return pd.DataFrame(rows)


def observer_swap_df(rows, backup=False):
    out=[]
    for r in rows:
        if backup:
            pair=f"{r.get('requester','')} ↔ {r.get('target','')}"
            slots=f"#{r.get('requester_slot')} ↔ #{r.get('target_slot')}"
        else:
            pair=f"{r.get('person_a','')} ↔ {r.get('person_b','')}"
            slots=f"#{r.get('slot_a')} ↔ #{r.get('slot_b')}"
        out.append({
            "ID":r.get("id"),
            tr("person"):pair,
            tr("shift"):slots,
            tr("status"):r.get("status",""),
            tr("updated"):r.get("responded_at") or r.get("created_at") or "",
        })
    return pd.DataFrame(out)


def observer_backup_df(y,m,current):
    slots={s.idx:s for s in make_slots(y,m)}
    rows=[]
    for r in db.list_backups(y,m):
        s=slots.get(int(r.get("covered_slot",0)))
        if s is None:
            continue
        rows.append({
            tr("date"):f"{y}-{m:02d}-{s.day:02d}",
            tr("shift"):block_label(s.block),
            tr("covered_person"):(current.assignments.get(s.idx,"") if current else r.get("covered_person","")),
            tr("observer_planned_backup"):r.get("planned_backup") or "—",
            tr("observer_actual_backup"):r.get("actual_backup") or "—",
            tr("observer_activated"):tr("yes") if r.get("activated_at") else tr("no"),
            tr("observer_completed"):tr("yes") if r.get("completed_at") else tr("no"),
        })
    return pd.DataFrame(rows)


def render_observer_portal(profile,auth_user):
    st.sidebar.markdown(
        f'<div style="padding:10px 12px;border:1px solid #d1d5db;border-radius:10px;'
        f'font-weight:700;">{html.escape(tr("observer_read_only"))} · '
        f'{html.escape(tr("observer_role"))}</div>',
        unsafe_allow_html=True
    )
    st.sidebar.caption(getattr(auth_user,"email",profile.get("email","")))
    if st.sidebar.button(tr("logout"),use_container_width=True,key="observer_logout"):
        try: st.session_state["supabase_client"].auth.sign_out()
        except Exception: pass
        clear_cross_account_session_state(keep_client=False)
        st.session_state["_logout_cookie_cleanup"]=True
        st.rerun()

    default_y,default_m=next_month(date.today())
    y=int(st.sidebar.number_input(tr("year"),2026,2100,default_y,1,key="observer_year"))
    m=int(st.sidebar.selectbox(
        tr("month"),list(range(1,13)),index=default_m-1,
        format_func=lambda x:MONTHS[lang][x-1],key="observer_month"
    ))

    st.title(tr("observer_portal"))
    st.warning(f"{tr('observer_read_only')} — {tr('observer_scope_note')}")
    st.caption(tr("observer_privacy_note"))

    tab_overview,tab_schedule,tab_changes,tab_fairness,tab_backups,tab_research,tab_rules=st.tabs([
        tr("observer_overview"),tr("observer_schedule"),tr("observer_changes"),
        tr("observer_fairness"),tr("observer_backups"),tr("research_observer_tab"),tr("observer_rules")
    ])

    current_payload=db.load_schedule(y,m,"current")
    baseline_payload=db.load_schedule(y,m,"baseline")
    current=refresh_result_payload(current_payload,y,m) if current_payload else None
    baseline=refresh_result_payload(baseline_payload or current_payload,y,m,use_actual_backups=False) if current_payload else None
    normal_swaps=db.list_swap_requests(y,m,None)
    backup_swaps=db.list_backup_swap_requests(y,m,None)
    changes=observer_assignment_changes_df(y,m,baseline,current) if current else pd.DataFrame()

    with tab_overview:
        if not current:
            st.info(tr("observer_no_schedule"))
        else:
            g=baseline.stats.get("global",{})
            sl=live_fairness_snapshot(y,m,baseline,include_completed_covers=False)["global"]
            al=live_fairness_snapshot(y,m,current,include_completed_covers=True)["global"]
            approved=sum(1 for r in normal_swaps+backup_swaps if r.get("status")=="approved")
            pending=sum(1 for r in normal_swaps+backup_swaps if r.get("status")=="pending")
            c1,c2,c3,c4,c5=st.columns(5)
            c1.metric(tr("hard_errors"),g.get("hard_errors",0))
            c2.metric("Pradinio grafiko balansas",f"{sl.get('monthly_fairness_score',0)}%")
            c3.metric("Faktinio grafiko balansas",f"{al.get('monthly_fairness_score',0)}%",delta=f"{al.get('monthly_fairness_score',0)-sl.get('monthly_fairness_score',0):+.1f}")
            c4.metric(tr("observer_change_count"),len(changes))
            c5.metric(tr("observer_pending_swaps"),pending)
            st.caption(tr("observer_change_log_help"))
            if changes.empty:
                st.success(tr("observer_no_changes"))
            else:
                st.dataframe(changes,use_container_width=True,hide_index=True)
            st.markdown(f"### {tr('fairness_hierarchy')}")
            st.dataframe(pd.DataFrame([
                {tr("fairness_level"):"1. Saugumas ir padengimas",tr("fairness_goal"):"Saugus, įmanomas ir pilnai padengtas grafikas."},
                {tr("fairness_level"):"2. „Dirbti negaliu“",tr("fairness_goal"):"0 pažeidimų."},
                {tr("fairness_level"):"3. Tolygus privalomas paskirstymas",tr("fairness_goal"):tr("fairness_monthly_goal")},
                {tr("fairness_level"):"4. Visų rezidentų pageidavimai",tr("fairness_goal"):tr("other_preferences_goal")},
                {tr("fairness_level"):"5. Pateikimo vieta 1–16",tr("fairness_goal"):"Tik paskutinis kriterijus, kai lieka keli vienodai geri, bet tarpusavyje nesuderinami variantai."},
            ]),use_container_width=True,hide_index=True)

    with tab_schedule:
        if not current:
            st.info(tr("observer_no_schedule"))
        else:
            st.markdown(f"### {tr('observer_baseline_schedule')}")
            st.caption(tr("fairness_swap_neutral"))
            st.dataframe(style_schedule(schedule_grid(y,m,baseline)),use_container_width=True,height=560)
            st.divider()
            st.markdown(f"### {tr('observer_actual_schedule')}")
            st.caption(tr("observer_change_log_help"))
            st.dataframe(style_schedule(schedule_grid(y,m,current)),use_container_width=True,height=560)

    with tab_changes:
        if not current:
            st.info(tr("observer_no_schedule"))
        else:
            st.markdown(f"### {tr('observer_normal_swaps')}")
            if normal_swaps:
                st.dataframe(observer_swap_df(normal_swaps),use_container_width=True,hide_index=True)
            else:
                st.caption("—")
            st.markdown(f"### {tr('observer_backup_swaps')}")
            if backup_swaps:
                st.dataframe(observer_swap_df(backup_swaps,backup=True),use_container_width=True,hide_index=True)
            else:
                st.caption("—")
            st.markdown(f"### {tr('observer_change_count')}")
            if changes.empty:
                st.success(tr("observer_no_changes"))
            else:
                st.dataframe(changes,use_container_width=True,hide_index=True)

    with tab_fairness:
        if not current:
            st.info(tr("observer_no_schedule"))
        else:
            g=baseline.stats.get("global",{})
            sl=live_fairness_snapshot(y,m,baseline,include_completed_covers=False)["global"]
            al=live_fairness_snapshot(y,m,current,include_completed_covers=True)["global"]
            c1,c2,c3=st.columns(3)
            c1.metric(tr("hard_validity"),tr("hard_validity_pass") if g.get("hard_errors",0)==0 else tr("hard_validity_fail"))
            c2.metric("Pradinio grafiko balansas",f"{sl.get('monthly_fairness_score',0)}%")
            c3.metric("Faktinio grafiko balansas",f"{al.get('monthly_fairness_score',0)}%",delta=f"{al.get('monthly_fairness_score',0)-sl.get('monthly_fairness_score',0):+.1f}")
            st.caption(tr("fairness_swap_neutral"))
            breakdown=[
                ("SYSTEM",tr("metric_saturday"),sl.get("saturday_monthly_spread",0)),
                ("ACTUAL",tr("metric_saturday"),al.get("saturday_monthly_spread",0)),
                ("SYSTEM",tr("metric_sunday"),sl.get("sunday_monthly_spread",0)),
                ("ACTUAL",tr("metric_sunday"),al.get("sunday_monthly_spread",0)),
                ("SYSTEM",tr("metric_friday"),sl.get("friday_monthly_spread",0)),
                ("ACTUAL",tr("metric_friday"),al.get("friday_monthly_spread",0)),
                ("SYSTEM",tr("metric_double"),sl.get("double_monthly_spread",0)),
                ("ACTUAL",tr("metric_double"),al.get("double_monthly_spread",0)),
                ("SYSTEM",tr("metric_weekday"),sl.get("weekday_day_monthly_spread",0)),
                ("ACTUAL",tr("metric_weekday"),al.get("weekday_day_monthly_spread",0)),
            ]
            st.dataframe(pd.DataFrame([{tr("fairness_scope"):scope,tr("fairness_metric"):metric,tr("fairness_spread"):spread} for scope,metric,spread in breakdown]),use_container_width=True,hide_index=True)
            trend=system_actual_fairness_trend_df(y,m)
            if not trend.empty:
                chart=trend.set_index("Period")
                st.line_chart(chart[["SYSTEM monthly fairness","ACTUAL monthly fairness"]],height=300)
                st.dataframe(trend,use_container_width=True,hide_index=True)
                st.caption("Tik auditas — jokio future catch-up." if lang=="LT" else "Audit only — no future catch-up.")
            else:
                st.caption(tr("fairness_no_history"))

    with tab_backups:
        if not current:
            st.info(tr("observer_no_schedule"))
        else:
            bdf=observer_backup_df(y,m,current)
            if bdf.empty:
                st.caption("—")
            else:
                st.dataframe(bdf,use_container_width=True,hide_index=True)

    with tab_research:
        st.info(tr("research_observer_intro"))
        cp_options=[c for c,_,_ in OBSERVER_RESEARCH_CHECKPOINTS]
        cp=st.selectbox(tr("research_observer_checkpoint"),cp_options,format_func=research_checkpoint_label,key="observer_research_cp")
        yy,mm=next((yy,mm) for c,yy,mm in OBSERVER_RESEARCH_CHECKPOINTS if c==cp)
        existing=db.get_my_observer_research_checkpoint(yy,mm,cp) or {}
        olda=existing.get("answers") or {}; oldf=existing.get("free_text") or {}
        obs_items={
            "actual":tr("research_obs_actual"),"changes":tr("research_obs_changes"),
            "system_actual":tr("research_obs_system_actual"),"privacy":tr("research_obs_privacy"),
            "change_log":tr("research_obs_log"),"fairness":tr("research_obs_fairness"),"trust":tr("research_obs_trust")
        }
        with st.form(f"observer_research_{cp}"):
            ans={}
            for key,label in obs_items.items():
                ans[key]=st.slider(label,1,5,int(olda.get(key,3) or 3),1,key=f"obs_{cp}_{key}")
            missing=st.text_area(tr("research_obs_missing"),value=oldf.get("missing","") or "")
            if st.form_submit_button(tr("research_submit"),type="primary"):
                db.submit_observer_research_checkpoint(yy,mm,cp,ans,{"missing":missing})
                st.success(tr("research_observer_saved"))

    with tab_rules:
        st.markdown(db.get_manual(lang))


sb,auth_user=render_auth_gate()
profile=require_linked_profile(sb,auth_user)
if profile.get("access_role")=="observer":
    render_observer_portal(profile,auth_user)
    st.stop()

active_user=profile["initials"]
resident_ok=True

# V2.5.34: install the ACTIVE versioned Rule Profile before any month calculations,
# scheduling, backup planning or rule-dependent UI is rendered.
try:
    _active_rule_row=db.get_active_rule_profile()
    if _active_rule_row:
        st.session_state["_last_good_rule_profile"]=dict(_active_rule_row)
except Exception as exc:
    _active_rule_row=st.session_state.get("_last_good_rule_profile")
    if not _active_rule_row:
        st.error(
            "Laikinas ryšio su duomenų baze sutrikimas. Aktyvių taisyklių nepavyko saugiai perskaityti. "
            "Jokio swapo / grafiko pakeitimo neįvykdžiau. Atnaujinkite puslapį po kelių sekundžių."
            if lang=="LT" else
            "Temporary database connection problem. The active rule profile could not be read safely. "
            "No swap/schedule change was performed. Refresh the page in a few seconds."
        )
        st.caption(f"{exc.__class__.__name__}: {exc}")
        st.stop()

if (_active_rule_row or {}).get("_read_fallback")=="memory_cache":
    st.warning(
        "Trumpam nutrūko DB ryšys — naudojama paskutinė šiame procese sėkmingai perskaityta aktyvi taisyklių versija."
        if lang=="LT" else
        "Database connection briefly dropped — using the last successfully read active rule profile from this process."
    )

_active_rule_config=(_active_rule_row or {}).get("config") or DEFAULT_RULE_PROFILE
try:
    ACTIVE_RULES=set_runtime_rules(_active_rule_config)
    ACTIVE_RULE_PROFILE_VERSION=int((_active_rule_row or {}).get("version_no") or 1)
except Exception:
    # Safety fallback: invalid DB config can never silently corrupt scheduling.
    ACTIVE_RULES=set_runtime_rules(DEFAULT_RULE_PROFILE)
    ACTIVE_RULE_PROFILE_VERSION=0

try:
    directory_map=db.directory()
    if directory_map:
        st.session_state["_last_good_directory"]=directory_map
except Exception as exc:
    directory_map=st.session_state.get("_last_good_directory")
    if not directory_map:
        st.error(
            "Laikinas DB ryšio sutrikimas. Rezidentų sąrašo nepavyko perskaityti; atnaujinkite puslapį."
            if lang=="LT" else
            "Temporary database connection problem. The resident directory could not be read; refresh the page."
        )
        st.caption(f"{exc.__class__.__name__}: {exc}")
        st.stop()
people_map={p["initials"]:p for p in DEFAULT_PEOPLE}
st.sidebar.markdown(badge(active_user),unsafe_allow_html=True)
research_role = "researcher" if active_user==RESEARCHER_INITIALS else "senior" if active_user==SENIOR_INITIALS else "resident"
role_key={"researcher":"research_role_researcher","senior":"research_role_senior","resident":"research_role_resident"}[research_role]
st.sidebar.caption(tr(role_key))
st.sidebar.caption(getattr(auth_user,"email",profile.get("email","")))
if st.sidebar.button(tr("logout"),use_container_width=True):
    try: sb.auth.sign_out()
    except Exception: pass
    clear_cross_account_session_state(keep_client=False)
    st.session_state["_logout_cookie_cleanup"]=True
    st.rerun()

# V2.5.90: one visible interface per account. There is no profile switch.
# SP = operational Seniūnė.
# ŠR = resident-facing account with embedded researcher + senior/admin capabilities.
# MG and all others = resident-only.
is_seniune_account=(active_user==SENIOR_INITIALS)
is_researcher_account=(active_user==RESEARCHER_INITIALS)
has_senior_functions=(is_seniune_account or is_researcher_account)
admin_ok=has_senior_functions
# Legacy name retained as a capability flag for existing protected senior-only blocks.
senior_mode=has_senior_functions

ui_simple=("Paprastas" if lang=="LT" else "Simple")
ui_advanced=("Išplėstinis" if lang=="LT" else "Advanced")
ui_mode=st.sidebar.radio(
    ("Sąsajos režimas" if lang=="LT" else "Interface mode"),
    [ui_simple,ui_advanced],
    index=0,
    key="ui_mode_v2530",
    help=("Paprastas: kasdieniai veiksmai ir tik svarbiausi rezultatai. Išplėstinis: išsami grafiko sudarymo, teisingumo ir tyrimo diagnostika."
          if lang=="LT" else
          "Simple: daily actions and only the most important results. Advanced: full fairness, guardrail and solver diagnostics.")
)
advanced_mode=(ui_mode==ui_advanced)
# V2.5.117 — SP remains the primary senior, but ŠR retains the explicitly
# granted lifecycle/operator contingency controls in BOTH Simple and Advanced
# modes. Interface complexity must never remove Grafikas → Grafiko tvirtinimas.
# Backend RPCs still authorize and audit the real ŠR identity; no SP impersonation.
lifecycle_operator_ui=(is_seniune_account or is_researcher_account)
st.sidebar.caption(
    ("Paprastas režimas yra numatytasis." if not advanced_mode and lang=="LT" else
     "Simple mode is the default." if not advanced_mode else
     "Rodoma pilna techninė informacija." if lang=="LT" else
     "Full technical information is visible.")
)

default_y,default_m=next_month(date.today()); year=int(st.sidebar.number_input(tr("year"),2026,2100,default_y,1)); month=int(st.sidebar.selectbox(tr("month"),list(range(1,13)),index=default_m-1,format_func=lambda x:MONTHS[lang][x-1]))
wd=weekday_count(year,month); bt=standard_target(year,month)
if advanced_mode:
    st.sidebar.metric(tr("weekdays"),wd)
    st.sidebar.metric(tr("base_target"),bt)
    st.sidebar.caption(
        f"{wd} × {float(rule_value('target_daily_hours')):g} / "
        f"{float(rule_value('target_shift_hours')):g} → {bt}"
    )
    st.sidebar.caption(
        ("Aktyvus taisyklių profilis" if lang=="LT" else "Active Rule Profile")
        + f": v{ACTIVE_RULE_PROFILE_VERSION}"
    )

st.title(tr("app_title"))
if advanced_mode:
    st.caption(tr("app_caption"))
    st.info(
        ("IŠPLĖSTINIS REŽIMAS — rodoma išsami grafiko sudarymo, teisingumo ir tyrimo diagnostika."
         if lang=="LT" else
         "ADVANCED MODE — full fairness, guardrail, solver and research diagnostics are visible.")
    )
else:
    st.caption("Paprastas režimas" if lang=="LT" else "Simple mode")

# V2.5.120: every account sees the same server-authoritative lifecycle phase,
# with a browser-side clock that visibly ticks every second.
render_live_cycle_countdown(year,month,operator=lifecycle_operator_ui)

# V2.5.94: after the exact cutoff, SP/ŠR views automatically materialize
# every still-missing active resident as a submitted zero-request form.
_zero_pref_autosubmit={"ok":True,"due":False,"count":0,"initials":[]}
if lifecycle_operator_ui:
    _zero_pref_autosubmit=ensure_zero_preference_submissions_if_due(year,month)
    if int(_zero_pref_autosubmit.get("count",0) or 0)>0:
        names=", ".join(_zero_pref_autosubmit.get("initials") or [])
        st.info(
            (f"Po pageidavimų termino automatiškai užfiksuotos 0 pageidavimų anketos: {names}."
             if lang=="LT" else
             f"After the preference deadline, zero-request submissions were recorded automatically for: {names}.")
        )

if advanced_mode:
    with st.expander(("IŠPLĖSTINIS LANGAS" if lang=="LT" else "ADVANCED WINDOW"), expanded=True):
        adv_state=db.get_schedule_state(year,month)
        adv_payload=db.load_schedule(year,month,"baseline") or db.load_schedule(year,month,"draft")
        a1,a2,a3,a4=st.columns(4)
        a1.metric(("Būsena" if lang=="LT" else "State"),
                  ("Paskelbtas" if adv_state.get("has_published") else "Juodraštis" if adv_state.get("has_draft") else "Nesukurtas"))
        if adv_payload:
            adv_res=refresh_result_payload(adv_payload,year,month,use_actual_backups=False)
            adv_g=(adv_res.stats or {}).get("global",{})
            a2.metric("Privalomų taisyklių klaidos",adv_g.get("hard_errors","—"))
            a3.metric(("Mėnesio teisingumas" if lang=="LT" else "Monthly fairness"),f"{adv_g.get('monthly_fairness_score',adv_g.get('fairness_score','—'))}%")
            a4.metric(("Skaičiavimo etapas" if lang=="LT" else "Solver stage"),adv_g.get("solve_stage","—"))
            st.caption(
                (f"Apsauginės sąlygos: {len(adv_g.get('fairness_guardrails') or {})} · Pageidavimų pirminė patikra: {adv_g.get('preference_normalization_count',0)}"
                 if lang=="LT" else
                 f"Apsauginės sąlygos: {len(adv_g.get('fairness_guardrails') or {})} · Pageidavimų pirminė patikra: {adv_g.get('preference_normalization_count',0)}")
            )
        else:
            a2.metric("HARD","—"); a3.metric(("Mėnesio teisingumas" if lang=="LT" else "Monthly fairness"),"—"); a4.metric(("Skaičiavimo etapas" if lang=="LT" else "Solver stage"),"—")

names=[]
names += [tr("preferences"),tr("settings"),tr("special_days")]
if senior_mode:
    names.append(tr("generation"))
names.append(tr("schedule"))
if advanced_mode:
    names += [tr("summary"),tr("transparency")]
# Credits are operational, not merely diagnostic: every resident can see the
# rest-credit bank; SP/ŠR additionally see their mirrored WESTON balance here.
names.append(tr("credits_debts"))
# V2.5.154: the resident research questionnaire is a first-class operational tab.
# It is visible to every resident in both simple and advanced modes. Advanced
# ŠR/SP users still receive their additional research tools inside the same tab.
research_nav_label = tr("research_survey")
names += [tr("backups"),tr("swaps"),tr("calendar"),research_nav_label]
# V2.5.161 — dedicated isolated audit workbench only in ŠR/Rapolas account.
# It is intentionally separate from the resident questionnaire and is visible
# in both Simple and Advanced modes so research uploads are easy to find.
if is_researcher_account:
    names.append("RESEARCH")
if advanced_mode:
    names.append(tr("proof"))
names.append(tr("rules"))

# Research-only scheduling experiments now live inside the single Tyrimas window.
# V2.5.166: Streamlit tabs normally reopen the FIRST tab after a forced rerun.
# For SP/ŠR that used to mean getting thrown back to Pageidavimai during schedule
# iteration. Make Sudarymas the first VISIBLE operator tab, while remapping the
# returned containers back to the original logical order so all existing `pos`
# blocks keep rendering into the correct tab without a large navigation rewrite.
_logical_names=list(names)
if senior_mode and tr("generation") in _logical_names:
    _generation_label=tr("generation")
    _visible_names=[_generation_label]+[n for n in _logical_names if n!=_generation_label]
    _visible_tabs=st.tabs(_visible_names)
    _tab_by_name={name:_visible_tabs[i] for i,name in enumerate(_visible_names)}
    tabs=[_tab_by_name[name] for name in _logical_names]
else:
    tabs=st.tabs(_logical_names)
research_shadow_tab_index=None

# Navigacija visoms paskyroms prasideda nuo pirmojo realaus lango.
pos=0
if active_user==RESEARCHER_INITIALS:
    st.sidebar.caption("RESEARCH — izoliuotas OPTO / RAPA / RANKA auditas; production grafiko nekeičia.")
if st.session_state.get("_save_flash"):
    st.success("✓ " + str(st.session_state.pop("_save_flash")))


def flash_saved(message):
    """Store a one-shot success message and rerun safely."""
    st.session_state["_save_flash"] = str(message)
    st.rerun()


def render_recurring_preferences_editor(initials: str):
    """Persistent recurring preferences live in the Preferences tab, not Settings."""
    st.divider()
    st.markdown(f"### {tr('long_term')}")
    st.caption(tr("long_term_help"))
    st.caption(
        "Ši dalis nėra pririšta prie vieno mėnesio: taisyklės automatiškai persikelia į visus būsimus dar neužšaldytus grafikus, kol jas pakeisite arba išjungsite. Jau paskelbto pradinio grafiko jos atgaline data nekeičia."
        if lang=="LT" else
        "This section is not tied to one month: the rules automatically carry into every future grafikas that is not yet frozen until you change or disable them. They never rewrite an already published SYSTEM schedule."
    )
    st.caption(
        "Savaitgalio „Pageidauju dirbti“ galima pasirinkti tik vienai konkrečiai šeštadienio ARBA sekmadienio datai per mėnesį. Todėl savaitgalio darbo pageidavimas nėra ilgalaikė pasikartojanti taisyklė — konkrečią datą pasirinkite mėnesio pageidavimuose."
        if lang=="LT" else
        "Weekend 'prefer to work' may be selected for only one concrete Saturday OR Sunday date per month. It is therefore not a recurring long-term rule; choose the concrete date in monthly preferences."
    )
    existing_rec={int(r["weekday"]):r for r in db.get_recurring_preferences(initials)}
    rule_to_label={"hard_unavailable":tr("rec_hard"),"soft_free":tr("rec_soft"),"preferred":tr("rec_preferred"),"none":tr("rec_none")}
    label_to_rule={v:k for k,v in rule_to_label.items()}
    block_to_label={"FULL":tr("full_day"),"AM":tr("morning"),"PM":tr("afternoon")}
    label_to_block={v:k for k,v in block_to_label.items()}
    rec_rows=[]
    for wd_i in range(7):
        rr=existing_rec.get(wd_i,{}); typ=rr.get("preference_type","none"); block=rr.get("block","FULL")
        rec_rows.append({tr("weekday_name"):WEEKDAY_FULL[lang][wd_i],tr("recurring_rule"):rule_to_label.get(typ,tr("rec_none")),tr("recurring_time"):block_to_label.get(block,tr("full_day")),"_weekday":wd_i})
    rec_df=pd.DataFrame(rec_rows)
    edited=st.data_editor(rec_df,column_config={tr("recurring_rule"):st.column_config.SelectboxColumn(options=list(rule_to_label.values())),tr("recurring_time"):st.column_config.SelectboxColumn(options=list(block_to_label.values())),"_weekday":None},disabled=[tr("weekday_name")],hide_index=True,use_container_width=True,key=f"recurring_{initials}_{lang}")
    if st.button(tr("save_long_term"),type="primary",key=f"save_recurring_{initials}_{lang}"):
        payload=[]; invalid_weekend_soft=[]; invalid_weekend_preferred=[]
        for _,r in edited.iterrows():
            wd=int(r["_weekday"]); typ=label_to_rule.get(r[tr("recurring_rule")],"none"); block=label_to_block.get(r[tr("recurring_time")],"FULL")
            if wd>=5 and typ=="soft_free":
                invalid_weekend_soft.append(WEEKDAY_FULL[lang][wd]); continue
            if wd>=5 and typ=="preferred":
                invalid_weekend_preferred.append(WEEKDAY_FULL[lang][wd]); continue
            payload.append({"weekday":wd,"preference_type":typ,"block":block})
        if invalid_weekend_soft or invalid_weekend_preferred:
            st.error(
                "Savaitgalio ilgalaikė taisyklė čia nenaudojama: „Noriu laisvos“ savaitgaliui nepriimamas, o „Pageidauju dirbti“ nuo šiol galima pasirinkti tik vienai konkrečiai šeštadienio arba sekmadienio datai per mėnesį. Konkrečią datą pasirinkite mėnesio pageidavimuose."
                if lang=="LT" else
                "Recurring weekend rules are not used here: weekend 'want off' is blocked, and weekend 'prefer to work' may now be selected for only one concrete Saturday or Sunday date per month. Choose that date in monthly preferences."
            )
        else:
            db.save_recurring_preferences(initials,payload); flash_saved(tr("long_term_saved"))

# --- Preferences ---
with tabs[pos]:
    st.subheader(f"{tr('my_preferences')} — {month_label(year,month)}")
    dl,dlmsg,dldiff=deadline_message(year,month); cutoff_exact=preference_cutoff_for(year,month)
    st.markdown(f'<div class="deadline-card"><b>{tr("deadline")}: {cutoff_exact.strftime("%Y-%m-%d %H:%M")}</b><br>{html.escape(dlmsg)}<br><span style="color:#6b7280">{html.escape(tr("deadline_note"))}</span></div>',unsafe_allow_html=True)
    st.caption(
        "Šio mėnesio konkretūs pageidavimai galioja tik pasirinktam grafikui. Kito mėnesio forma pildoma iš naujo; ilgalaikiai pasikartojantys pageidavimai žemiau išlieka, kol juos pakeisite."
        if lang=="LT" else
        "Month-specific requests apply only to the selected schedule. The next month starts with a new monthly form; long-term recurring preferences below persist until you change them."
    )
    if not resident_ok:
        st.error(tr("bad_pin"))
    else:
        pref_open=preference_open_for(year,month)
        cutoff_pref=preference_cutoff_for(year,month)
        now_lt=datetime.now(ZoneInfo("Europe/Vilnius"))
        own_deadline_open=(now_lt >= pref_open and now_lt < cutoff_pref)
        pref_state=db.get_schedule_state(year,month)
        pref_system_frozen=bool(pref_state.get("has_published"))

        preference_target=active_user
        operator_manual_mode=False
        operator_reason_kind=""
        operator_reason_detail=""

        if lifecycle_operator_ui:
            st.markdown(
                """<div style="border:2px solid #7C9BFF;background:rgba(79,112,255,.08);
                border-radius:16px;padding:14px 16px;margin:4px 0 12px 0;">
                <b>Operatoriaus pageidavimų įvedimas</b><br>
                <span style="opacity:.82">Numatyta — jūsų pačių anketa. Jei rezidentas negalėjo pateikti pats,
                pasirinkite jo inicialus ir suveskite informaciją jo vardu. Paskyros identitetas nekeičiamas,
                veiksmas audituojamas.</span></div>""",
                unsafe_allow_html=True,
            )
            target_order=[active_user]+[p["initials"] for p in DEFAULT_PEOPLE if p["initials"]!=active_user]
            name_map={p["initials"]:p["name"] for p in DEFAULT_PEOPLE}
            preference_target=st.selectbox(
                "Pildyti už:",
                target_order,
                index=0,
                format_func=lambda i:f"{i} — {name_map.get(i,i)}",
                key=f"pref_target_{year}_{month}_{active_user}",
            )
            st.markdown(
                f'<div style="border:1px solid rgba(124,155,255,.55);border-radius:12px;padding:10px 12px;">'
                f'<b>Pasirinktas rezidentas:</b> {badge(preference_target,include_name=True)}</div>',
                unsafe_allow_html=True,
            )
            operator_manual_mode=(preference_target!=active_user) or (not own_deadline_open)
            if pref_system_frozen:
                st.error(
                    "Pradinis grafikas jau užfiksuotas. Pageidavimų keisti nebegalima; jei reikia pakeitimo, naudokite grafiko koregavimo arba apsikeitimo funkciją."
                    if lang=="LT" else
                    "SYSTEM is already frozen. Preferences can no longer be changed; use Schedule → manual correction for operational changes."
                )
        else:
            st.markdown(badge(active_user),unsafe_allow_html=True)
            if now_lt < pref_open:
                st.info(
                    f"Pageidavimų langas atsidarys {pref_open.strftime('%Y-%m-%d %H:%M')} Lietuvos laiku."
                    if lang=="LT" else
                    f"The preference window opens {pref_open.strftime('%Y-%m-%d %H:%M')} Lithuania time."
                )
            elif now_lt >= cutoff_pref:
                st.warning(
                    f"Pageidavimų terminas baigėsi {cutoff_pref.strftime('%Y-%m-%d %H:%M')} Lietuvos laiku. "
                    "Anketos po termino rezidentas pats keisti nebegali. Jei būtina pataisa, kreipkitės į Seniūnę."
                    if lang=="LT" else
                    f"The preference deadline closed at {cutoff_pref.strftime('%Y-%m-%d %H:%M')} Lithuania time. "
                    "Residents can no longer edit the form themselves; contact the senior scheduler if a correction is required."
                )

        cur=db.get_preference(year,month,preference_target) or {}
        special_cur=db.get_special_workdays_v25145(year,month,preference_target)
        _existing_guardrail=preference_guardrail_violations_v25162(
            year,month,
            set(cur.get("unavailable",set())),set(cur.get("unavailable_am",set())),set(cur.get("unavailable_pm",set())),
            set(cur.get("soft_free",set())),set(cur.get("soft_free_am",set())),set(cur.get("soft_free_pm",set())),
            set(cur.get("preferred",set())),set(cur.get("preferred_am",set())),set(cur.get("preferred_pm",set())),
        ) if cur else []
        if _existing_guardrail and preference_target==active_user and not lifecycle_operator_ui:
            st.warning("Šioje senoje anketoje yra pasirinkimų, kurių naujas anti-gaming guardrail nebeleis išsaugoti. Pataisykite juos arba kreipkitės į Seniūnę.\n\n"+"\n".join(f"• {x}" for x in _existing_guardrail))
        source=cur.get("submission_source","")
        submitter=cur.get("submitted_by_initials","")
        if cur:
            if source=="deadline_zero":
                st.info("Pateikta: TAIP — automatiškai užfiksuota 0 pageidavimų anketa po termino." if lang=="LT" else "Submitted: YES — automatic zero-request form after the deadline.")
            elif source=="operator_manual":
                st.info((f"Pateikta: TAIP — manualiai įvedė {submitter or 'operatorius'}." if lang=="LT" else f"Submitted: YES — manually entered by {submitter or 'operator'}."))
            else:
                st.success("Pateikta: TAIP — rezidento anketa." if lang=="LT" else "Submitted: YES — resident submission.")

        if weekend_fcfs_backup_mode(year,month):
            # Pateikimo vieta rodoma tik po termino. Dubliai nuo V2.5.146 nebėra
            # Pageidavimų dalis ir atsirakina tik paskelbus preliminarų grafiką.
            if now_lt >= cutoff_pref:
                pri=db.get_preference_priority(year,month,preference_target)
                if pri and pri.get("submission_order"):
                    st.info(f"Pateikimo vieta: {int(pri['submission_order'])} iš 16")
                elif cur:
                    st.caption("Pateikimo vieta netaikoma — nėra mėnesio pageidavimų, kuriems reikėtų konflikto prioriteto.")

        # SP / ŠR papildomi planavimo blokai yra tiesiai Pageidavimuose ir
        # rodomi tiek Paprastame, tiek Išplėstiniame režime.
        if preference_target==active_user and active_user in (SENIOR_INITIALS,RESEARCHER_INITIALS):
            st.divider()
            render_sp_dream_team_settings_v25125(year,month)
            st.divider()
            render_operator_private_pair_preferences(year,month,active_user)
            st.divider()

        days=list(range(1,calendar.monthrange(year,month)[1]+1))
        st.markdown(f"### {tr('short_term')}")
        st.caption("RAPA validžius pageidavimus bando išpildyti 100 %. Savitarnoje blokuojami tik aiškūs sistemos išnaudojimo raštai: ≥5 pilnos dienos iš eilės, visi mėnesio šeštadieniai / sekmadieniai arba >1 savaitgalio „Pageidauju dirbti“. Jei poreikis realus, rašykite Seniūnei — ji gali įvesti išimtį su audito priežastimi.")
        with st.form(f"prefs_{year}_{month}_{active_user}_{preference_target}"):
            if lifecycle_operator_ui and operator_manual_mode:
                st.markdown("#### Manualaus įvedimo auditas" if lang=="LT" else "#### Manual-entry audit")
                operator_reason_kind=st.selectbox(
                    "Priežastis" if lang=="LT" else "Reason",
                    [
                        "Pateikta telefonu" if lang=="LT" else "Submitted by phone",
                        "Techninė / ryšio problema" if lang=="LT" else "Technical / connectivity issue",
                        "Sveikatos / neatvykimo situacija" if lang=="LT" else "Health / absence situation",
                        "Pavėluotas operatoriaus įvedimas" if lang=="LT" else "Late operator entry",
                        "Kita" if lang=="LT" else "Other",
                    ],
                    key=f"pref_operator_reason_{year}_{month}_{active_user}_{preference_target}",
                )
                operator_reason_detail=st.text_input(
                    "Trumpa pastaba (nebūtina)" if lang=="LT" else "Short note (optional)",
                    key=f"pref_operator_reason_detail_{year}_{month}_{active_user}_{preference_target}",
                )
            st.markdown(f"### {tr('hard_unavailable')}")
            st.caption(tr("hard_help"))
            h1,h2,h3=st.columns(3)
            with h1:
                unavailable=st.multiselect(
                    tr("hard_all_day"),days,default=sorted(cur.get("unavailable",set())),
                    format_func=lambda d:pretty_day(year,month,d)
                )
            with h2:
                unavailable_am=st.multiselect(
                    tr("hard_morning"),days,default=sorted(cur.get("unavailable_am",set())),
                    format_func=lambda d:pretty_day(year,month,d)
                )
            with h3:
                unavailable_pm=st.multiselect(
                    tr("hard_afternoon"),days,default=sorted(cur.get("unavailable_pm",set())),
                    format_func=lambda d:pretty_day(year,month,d)
                )
            st.caption(tr("hard_partial_note"))
            st.markdown(f"### {tr('soft_free')}")
            st.caption(tr("soft_help"))
            sf1,sf2,sf3=st.columns(3)
            with sf1:
                soft=st.multiselect(tr("hard_all_day"),days,default=sorted(cur.get("soft_free",set())),format_func=lambda d:pretty_day(year,month,d),key=f"soft_full_{year}_{month}_{active_user}_{preference_target}")
            with sf2:
                soft_am=st.multiselect(tr("hard_morning"),days,default=sorted(cur.get("soft_free_am",set())),format_func=lambda d:pretty_day(year,month,d),key=f"soft_am_{year}_{month}_{active_user}_{preference_target}")
            with sf3:
                soft_pm=st.multiselect(tr("hard_afternoon"),days,default=sorted(cur.get("soft_free_pm",set())),format_func=lambda d:pretty_day(year,month,d),key=f"soft_pm_{year}_{month}_{active_user}_{preference_target}")

            st.markdown(f"### {tr('preferred')}")
            st.caption(tr("preferred_help"))
            pf1,pf2,pf3=st.columns(3)
            with pf1:
                pref=st.multiselect(tr("hard_all_day"),days,default=sorted(cur.get("preferred",set())),format_func=lambda d:pretty_day(year,month,d),key=f"pref_full_{year}_{month}_{active_user}_{preference_target}")
            with pf2:
                pref_am=st.multiselect(tr("hard_morning"),days,default=sorted(cur.get("preferred_am",set())),format_func=lambda d:pretty_day(year,month,d),key=f"pref_am_{year}_{month}_{active_user}_{preference_target}")
            with pf3:
                pref_pm=st.multiselect(tr("hard_afternoon"),days,default=sorted(cur.get("preferred_pm",set())),format_func=lambda d:pretty_day(year,month,d),key=f"pref_pm_{year}_{month}_{active_user}_{preference_target}")

            st.markdown(f"### {tr('vacation')}")
            st.caption(tr("vacation_help"))
            vacation=st.multiselect(
                tr("vacation"),days,default=sorted(cur.get("vacation",set())),
                format_func=lambda d:pretty_day(year,month,d),key=f"vacation_{year}_{month}_{active_user}_{preference_target}"
            )

            note=st.text_area(tr("note"),value=cur.get("note",""),placeholder=tr("note_ph"))
            # V2.5.136: reward credits are a separate wallet and are no longer
            # mixed into the monthly preference form. Legacy typed fields stay zero.
            bonus_am_use=0
            bonus_pm_use=0
            st.divider()
            with st.container(border=True):
                st.markdown(f"#### {tr('legal_safety_inputs')}")
                st.caption(tr("labour_hard_summary"))
                long_duty=st.multiselect(
                    tr("long_duty"),days,default=sorted(cur.get("long_duty",set())),
                    format_func=lambda d:pretty_day(year,month,d),help=tr("long_duty_help"),
                    key=f"outside_work_{year}_{month}_{active_user}_{preference_target}",
                )
                st.caption(tr("labour_scope_note"))
            resident_edit_blocked=(not lifecycle_operator_ui and not own_deadline_open)
            resident_edit_blocked=(not lifecycle_operator_ui and not own_deadline_open)
            operator_edit_blocked=False  # operator manual entry never follows resident phase locks
            submitted=st.form_submit_button(
                ("IŠSAUGOTI UŽ " + preference_target if lifecycle_operator_ui and operator_manual_mode and lang=="LT"
                 else "SAVE FOR " + preference_target if lifecycle_operator_ui and operator_manual_mode
                 else tr("save")),
                type="primary",
                disabled=resident_edit_blocked or operator_edit_blocked,
            )
            if submitted:
                # V2.5.146: Specialios dienos are edited in their own window.
                # Preserve the current separate values in the compatibility payload
                # so an installation that has V2.5.145 but not yet V2.5.146 migration
                # cannot accidentally erase them when a resident saves wishes.
                wellness_set=set(special_cur.get("wellness_days",set()))
                qualification_set=set(special_cur.get("qualification_days",set()))
                special_days=wellness_set|qualification_set
                special_type_conflict=False

                # Special paid workdays supersede same-date scheduling wishes at
                # solver/statistics level. The wish row itself is not silently edited.
                whole=set(unavailable); am=set(unavailable_am); pm=set(unavailable_pm)
                sf=set(soft); sf_am=set(soft_am); sf_pm=set(soft_pm)
                pr=set(pref); pr_am=set(pref_am); pr_pm=set(pref_pm)
                vacation_set=set(vacation)
                justified_set=set(cur.get("justified_absence",set()))  # legacy pre-V2.5.146 rows only
                long_duty_set=set(long_duty)
                absence=justified_set|vacation_set
                hard_pref_conflict = bool(
                    (whole|absence) & (pr|pr_am|pr_pm) or
                    am & (pr|pr_am) or
                    pm & (pr|pr_pm)
                )
                soft_pref_conflict = bool(
                    sf & (pr|pr_am|pr_pm) or
                    pr & (sf|sf_am|sf_pm) or
                    sf_am & pr_am or sf_pm & pr_pm
                )
                weekend_work_wish_dates={
                    int(d) for d in (pr|pr_am|pr_pm)
                    if date(year,month,int(d)).weekday()>=5
                }
                _guardrail_violations=preference_guardrail_violations_v25162(
                    year,month,whole,am,pm,sf,sf_am,sf_pm,pr,pr_am,pr_pm
                )
                _guardrail_operator_override=bool(lifecycle_operator_ui and operator_manual_mode)
                if whole & (am|pm):
                    st.error(tr("hard_overlap"))
                elif sf & (sf_am|sf_pm):
                    st.error(tr("soft_overlap"))
                elif pr & (pr_am|pr_pm):
                    st.error(tr("preferred_overlap"))
                elif _guardrail_violations and not _guardrail_operator_override:
                    st.error("Šio pageidavimų rinkinio RAPA neišsaugojo dėl anti-gaming guardrail. Jei tai realus poreikis, kreipkitės į Seniūnę — ji gali įvesti išimtį su audito priežastimi.\n\n"+"\n".join(f"• {x}" for x in _guardrail_violations))
                elif hard_pref_conflict:
                    st.error(tr("hard_conflict"))
                elif soft_pref_conflict:
                    st.error(tr("soft_conflict"))
                else:
                    pref_payload={
                        "unavailable":whole,
                        "unavailable_am":am,
                        "unavailable_pm":pm,
                        "justified_absence":justified_set,
                        "vacation":vacation_set,
                        "wellness_days":wellness_set,
                        "qualification_days":qualification_set,
                        "long_duty":long_duty_set,
                        "soft_free":sf,
                        "soft_free_am":sf_am,
                        "soft_free_pm":sf_pm,
                        "preferred":pr,
                        "preferred_am":pr_am,
                        "preferred_pm":pr_pm,
                        "note":note,
                        "backup_credits_am_to_use":int(bonus_am_use),
                        "backup_credits_pm_to_use":int(bonus_pm_use),
                        "backup_credits_night_to_use":0,
                    }
                    try:
                        if lifecycle_operator_ui and operator_manual_mode:
                            audit_reason=operator_reason_kind.strip()
                            if operator_reason_detail.strip():
                                audit_reason += " — " + operator_reason_detail.strip()
                            if _guardrail_violations:
                                audit_reason += " — ANTI-GAMING GUARDRAIL OVERRIDE: " + " | ".join(_guardrail_violations)
                            db.save_preference_for_resident_v2595(
                                year,month,preference_target,pref_payload,audit_reason
                            )
                            draft_note=(
                                " Jei šiam mėnesiui jau buvo sugeneruotas DRAFT, jį reikia regeneruoti."
                                if db.get_schedule_state(year,month).get("has_draft") else ""
                            )
                            flash_saved(
                                (f"{preference_target} pageidavimai įvesti operatoriaus vardu ir audituoti.{draft_note}"
                                 if lang=="LT" else
                                 f"{preference_target} preferences were entered by the operator and audited."
                                 + (" Regenerate the existing DRAFT." if draft_note else ""))
                            )
                        else:
                            db.save_preference(year,month,active_user,pref_payload)
                            flash_saved(tr("saved"))
                    except Exception as e:
                        msg=str(e)
                        if "PREFERENCE_WINDOW_NOT_OPEN" in msg:
                            st.error("Pageidavimų langas dar neatsidarė." if lang=="LT" else "The preference window is not open yet.")
                        elif "PREFERENCE_DEADLINE_CLOSED" in msg:
                            st.error("Pageidavimų terminas jau uždarytas. Susisiekite su Seniūne." if lang=="LT" else "The preference deadline is closed. Contact the senior scheduler.")
                        elif "PREFERENCE_INPUT_FROZEN_AFTER_SYSTEM" in msg:
                            st.error("Pradinis grafikas jau užfiksuotas — pageidavimų keisti nebegalima." if lang=="LT" else "SYSTEM is frozen — preferences can no longer be changed.")
                        elif "WEEKEND_WORK_WISH_LIMIT_ONE_DATE" in msg:
                            st.error("Savaitgaliui galima pasirinkti tik vieną „Pageidauju dirbti“ datą per mėnesį — vieną šeštadienį arba vieną sekmadienį." if lang=="LT" else "Only one weekend 'Prefer to work' date may be selected per month — one Saturday or one Sunday.")
                        elif "SPECIAL_WORKDAY_TYPE_CONFLICT" in msg:
                            st.error("Ta pati data negali būti ir sveikatinimosi, ir kvalifikacijos kėlimo diena." if lang=="LT" else "The same date cannot be both a wellness day and a qualification day.")
                        elif "SPECIAL_WORKDAY_INVALID_DATE" in msg:
                            st.error("Pasirinkta netinkama specialios darbo dienos data." if lang=="LT" else "Invalid special workday date.")
                        else:
                            st.error(msg)
        if preference_target==active_user:
            render_recurring_preferences_editor(active_user)
        elif lifecycle_operator_ui:
            st.divider()
            st.caption(
                "Ilgalaikius pasikartojančius pageidavimus kiekvienas rezidentas valdo savo Pageidavimų lange. Operatorinis įvedimas aukščiau keičia tik pasirinktą konkretų mėnesį."
                if lang=="LT" else
                "Each resident manages long-term recurring preferences in their own Preferences tab. The operator entry above changes only the selected month."
            )
    if senior_mode:
        st.divider(); st.markdown(f"### {tr('all_preferences')}"); prefs=db.all_preferences(year,month); sets=db.all_account_settings(); recurring_all=db.all_recurring_preferences(); special_all=db.all_special_workdays_v25145(year,month); nd=calendar.monthrange(year,month)[1]; rows=[]
        _priority_visible=bool(weekend_fcfs_backup_mode(year,month) and now_lt>=cutoff_pref)
        priority_rows=db.all_preference_priorities(year,month) if _priority_visible else {}
        applied_priority_rows=db.all_applied_preference_priorities(year,month) if _priority_visible else {}
        if weekend_fcfs_backup_mode(year,month) and lang=="LT" and _priority_visible:
            st.caption("Pateikimo vieta galioja tam pačiam grafikui ir nustatoma pagal paskutinio reikšmingo pageidavimų pakeitimo laiką iki termino.")
        backup_claims=db.list_backup_claims(year,month) if weekend_fcfs_backup_mode(year,month) else []
        claims_by_person={str(r.get("initials")):r for r in backup_claims}
        slot_map_fcfs={s.idx:s for s in _fcfs_weekend_slot_pool(year,month)} if weekend_fcfs_backup_mode(year,month) else {}
        if weekend_fcfs_backup_mode(year,month):
            mc1,mc2=st.columns(2)
            mc1.metric("Pageidavimai pateikti" if lang=="LT" else "Preferences submitted",f"{len(prefs)}/16")
            mc2.metric("Dubliai užpildyti" if lang=="LT" else "Backups filled",f"{len(backup_claims)}/16")
            if _priority_visible:
                st.caption(
                    "Pateikimo eilė: 1–16. Ji nustatoma pagal paskutinį reikšmingą pageidavimų pakeitimą iki termino ir taikoma tik tada, kai keli pageidavimai realiai susikerta. Sistema visada pirmiausia siekia 100 % bendro pageidavimų išpildymo."
                    if lang=="LT" else
                    "Pateikimo eilė rodoma tik po termino ir naudojama tik likusiam konfliktui."
                )
        for p in DEFAULT_PEOPLE:
            x=prefs.get(p["initials"],{})
            sx=special_all.get(p["initials"],{})
            vol=(len(x.get("unavailable",set()))+len(x.get("unavailable_am",set()))+
                 len(x.get("unavailable_pm",set()))+len(x.get("vacation",set()))+
                 len(x.get("long_duty",set()))+len(x.get("soft_free",set()))+
                 len(x.get("soft_free_am",set()))+len(x.get("soft_free_pm",set()))+
                 len(x.get("preferred",set()))+len(x.get("preferred_am",set()))+len(x.get("preferred_pm",set())))
            flag=tr("review") if vol>=max(10,round(nd/3)) else tr("normal")
            rows.append({
                tr("person"):p["initials"],tr("name"):p["name"],
                tr("submitted"):tr("yes") if x else tr("no"),
                ("Pateikimo būdas" if lang=="LT" else "Submission source"):(
                    ("Automatiškai — 0 pageidavimų" if lang=="LT" else "Automatic — 0 requests")
                    if x and x.get("submission_source")=="deadline_zero"
                    else ((f"Manualiai — {x.get('submitted_by_initials') or 'operatorius'}" if lang=="LT"
                           else f"Manual — {x.get('submitted_by_initials') or 'operator'}")
                          if x and x.get("submission_source")=="operator_manual"
                          else ("Rezidentas" if lang=="LT" else "Resident")
                          if x else "—")
                ),
                **(({"Pateikimo vieta":(priority_rows.get(p["initials"],{}).get("submission_order") or "—")}) if _priority_visible else {}),
                ("Dublis" if lang=="LT" else "Backup"):(
                    (lambda rr: (
                        f"{slot_map_fcfs[int(rr['covered_slot'])].day:02d} {WEEKDAYS[lang][slot_map_fcfs[int(rr['covered_slot'])].weekday]} · {block_label(slot_map_fcfs[int(rr['covered_slot'])].block)}"
                        if rr and int(rr.get('covered_slot') or 0) in slot_map_fcfs else "—"
                    ))(claims_by_person.get(p["initials"]))
                    if weekend_fcfs_backup_mode(year,month) else "legacy"
                ),
                tr("preference_load"):f"{vol} — {flag}",
                tr("hard_dates"):", ".join(map(str,sorted(x.get("unavailable",set())))),
                tr("hard_am_dates"):", ".join(map(str,sorted(x.get("unavailable_am",set())))),
                tr("hard_pm_dates"):", ".join(map(str,sorted(x.get("unavailable_pm",set())))),
                tr("vacation"):", ".join(map(str,sorted(x.get("vacation",set())))),
                tr("long_duty"):", ".join(map(str,sorted(x.get("long_duty",set())))),
                tr("soft_dates"):", ".join(map(str,sorted(x.get("soft_free",set())))),
                tr("soft_am_dates"):", ".join(map(str,sorted(x.get("soft_free_am",set())))),
                tr("soft_pm_dates"):", ".join(map(str,sorted(x.get("soft_free_pm",set())))),
                tr("preferred_dates"):", ".join(map(str,sorted(x.get("preferred",set())))),
                tr("preferred_am_dates"):", ".join(map(str,sorted(x.get("preferred_am",set())))),
                tr("preferred_pm_dates"):", ".join(map(str,sorted(x.get("preferred_pm",set())))),
                tr("long_term"):"; ".join(f"{WEEKDAY_FULL[lang][int(r['weekday'])]}: {r['preference_type']} {r.get('block','FULL')}" for r in recurring_all.get(p["initials"],[])),
                tr("comment"):x.get("note",""),
                tr("holiday_pref"):({-1:tr("holiday_rest"),0:tr("holiday_neutral"),1:tr("holiday_work")}.get(int(sets.get(p["initials"],{}).get("holiday_preference",0) or 0),tr("holiday_neutral"))),
                tr("email"):sets.get(p["initials"],{}).get("email","")
            })
        _prefs_export_df=pd.DataFrame(rows)
        # Export actions stay above the table so they are always visible.
        _ex1,_ex2=st.columns(2)
        with _ex1:
            st.download_button(
                "ATSISIŲSTI EXCEL (.xlsx)",
                build_preferences_xlsx(year,month,rows,priority_visible=_priority_visible),
                file_name=f"Pageidavimai_{year}_{month:02d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                type="primary",
                key=f"preferences_xlsx_{year}_{month}",
            )
        with _ex2:
            st.download_button(
                "ATSISIŲSTI CSV (.csv)",
                _prefs_export_df.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"Pageidavimai_{year}_{month:02d}.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"preferences_csv_{year}_{month}",
            )
        st.dataframe(style_rows(_prefs_export_df),use_container_width=True,hide_index=True)
        st.caption(tr("visibility_flag"))
pos+=1

# --- Settings ---
with tabs[pos]:
    st.subheader(tr("settings_title")); st.markdown(badge(active_user),unsafe_allow_html=True)
    if not resident_ok: st.error(tr("bad_pin"))
    else:
        s=db.get_account_settings(active_user)
        st.caption(
            "Darbo pobūdžio nustatymai yra ilgalaikiai: jie automatiškai taikomi kiekvienam būsimam dar neužšaldytam mėnesiui, kol pats juos pakeisite. Jie nėra iš naujo nustatomi kiekvieną mėnesį. Tai nėra mėnesio pageidavimai, todėl jų atitikimas neįeina į pageidavimų išpildymo statistiką."
            if lang=="LT" else
            "Work-style settings are persistent and apply to future unfrozen schedules until changed. They are scheduling-mode guidance, not monthly wishes, so they are excluded from request-satisfaction statistics."
        )
        with st.form(f"settings_{active_user}"):
            shift_len_options=[tr("shift_length_6"),tr("shift_length_12"),tr("shift_length_mixed"),tr("shift_length_any")]
            shift_len_value_to_label={0:tr("shift_length_any"),1:tr("shift_length_6"),2:tr("shift_length_mixed"),3:tr("shift_length_12")}
            shift_len_label_to_value={v:k for k,v in shift_len_value_to_label.items()}
            current_shift_len=max(0,min(3,int(s.get("shift_length_preference",0) or 0)))
            shift_len_label=st.selectbox(
                tr("shift_length_pref"),shift_len_options,
                index=shift_len_options.index(shift_len_value_to_label.get(current_shift_len,tr("shift_length_any"))),
                help=tr("shift_length_help")
            )
            shift_len_pref=shift_len_label_to_value.get(shift_len_label,0)
            st.caption(tr("shift_length_help"))
            st.divider()
            # Account email and notification delivery settings remain backend-managed.
            # Resident-facing Settings intentionally do not expose email/SMS/reminder controls;
            # mobile push notifications will become the primary notification surface later.
            email=str(s.get("email","") or "")
            st.caption("Pageidavimuose paliekami konkretūs, aiškūs poreikiai. Bendras savaitgalių vengimas nekeičia privalomo lygaus savaitgalių paskirstymo visai grupei. Jei reikia konkrečios laisvos dienos, pažymėkite ją Pageidavimų lange.")
            holiday_options=[tr("holiday_rest"),tr("holiday_neutral"),tr("holiday_work")]
            holiday_value_to_label={-1:tr("holiday_rest"),0:tr("holiday_neutral"),1:tr("holiday_work")}
            holiday_label_to_value={v:k for k,v in holiday_value_to_label.items()}
            holiday_pref_label=st.selectbox(
                tr("holiday_pref"),holiday_options,
                index=holiday_options.index(holiday_value_to_label.get(max(-1,min(1,int(s.get("holiday_preference",0) or 0))),tr("holiday_neutral"))),
                help=tr("holiday_pref_help")
            )
            hp=holiday_label_to_value.get(holiday_pref_label,0)
            wp=st.slider(tr("weekday_pref"),-2,2,int(s.get("weekday_preference",0) or 0),help=tr("weekday_help"))
            wep=0
            st.info(
                "Savaitgaliai visai grupei paskirstomi kuo tolygiau. Rezidentui nereikia rinktis, kiek savaitgalių jis nori gauti. Jei konkrečią dieną dirbti negalite, pažymėkite ją pageidavimuose. Po grafiko paskelbimo pasiskirstymas gali pasikeisti tik per savanorišką abiejų rezidentų sutartą apsikeitimą ir seniūnės patvirtinimą."
                if lang=="LT" else
                "WEEKENDS — ADMIN WATER-FILL. Residents can no longer choose to receive more weekends/Sundays. SYSTEM searches for the tightest mathematically feasible Saturday, Sunday and total-weekend spread. Only genuine Cannot-work availability can block a specific date. A voluntary post-publication swap may alter ACTUAL balance, but only after both residents consent and SP gives final approval."
            )
            sp=st.slider(tr("spread_pref"),-2,2,int(s.get("spread_preference",0)),help=tr("spread_help"))
            # `avoid_doubles` is retained in the database for backward compatibility;
            # the new four-way workday-length selector is the resident-facing source of truth.
            avoid=(shift_len_pref==1)
            st.markdown(f"### {tr('calendar')}")
            include_bk=st.checkbox(tr("include_backups_calendar"),value=bool(s.get("include_backups_in_calendar",False)))

            # Notification preferences are intentionally hidden from resident Settings.
            # Keep their current backend values untouched until mobile push notifications
            # replace the legacy email/SMS controls.
            notif=bool(s.get("notifications_on",True))
            start=int(s.get("reminder_start_day",8) or 8)
            backup_email=bool(s.get("backup_email_alerts",True))
            phone=s.get("phone_e164",None)
            backup_sms=bool(s.get("backup_sms_alerts",False))

            if st.form_submit_button(tr("save"),type="primary"):
                try:
                    db.save_account_settings(active_user,{"email":email,"weekday_preference":wp,"weekend_preference":wep,"holiday_preference":hp,"spread_preference":sp,"shift_length_preference":shift_len_pref,"avoid_doubles":avoid,"notifications_on":notif,"reminder_start_day":int(start),"preferred_language":lang,"include_backups_in_calendar":include_bk,"backup_email_alerts":backup_email,"phone_e164":phone,"backup_sms_alerts":backup_sms})
                    refresh_calendar_subscription_feeds([active_user])
                except Exception as exc:
                    st.error(
                        "Nustatymų išsaugoti nepavyko. Duomenys nebuvo pakeisti. "
                        "Jei klaida kartojasi, administratorius turi patikrinti account_settings schemą."
                    )
                    if advanced_mode:
                        st.caption(f"{type(exc).__name__}: {exc}")
                else:
                    flash_saved(tr("settings_saved"))
pos+=1

# --- Special days ---
with tabs[pos]:
    st.subheader(("Specialios dienos" if lang=="LT" else "Special days"))
    st.caption(
        "Čia laikomos oficialios darbo ir neatvykimo dienos, o ne pageidavimai. Jos neįeina į pageidavimų išpildymo procentą, nekeičia pateikimo eilės ir kalendoriuje rodomos kaip atskira būsena."
        if lang=="LT" else
        "Administrative work/absence statuses live here, not in Preferences. They are excluded from request-satisfaction statistics and submission priority."
    )
    _sd_state=db.get_schedule_state(year,month)
    _sd_published=bool(_sd_state.get("has_published"))
    _sd_target=active_user
    if lifecycle_operator_ui:
        _sd_target=st.selectbox(
            "Rezidentas" if lang=="LT" else "Resident",
            [p["initials"] for p in DEFAULT_PEOPLE],
            index=[p["initials"] for p in DEFAULT_PEOPLE].index(active_user) if active_user in [p["initials"] for p in DEFAULT_PEOPLE] else 0,
            key=f"special_days_target_{year}_{month}_{active_user}",
            format_func=lambda i:f"{i} — {people_map[i]['name']}",
        )
    _sd_days=list(range(1,calendar.monthrange(year,month)[1]+1))
    _sd_cur=db.get_special_workdays_v25145(year,month,_sd_target)

    st.markdown("### Planuojamos" if lang=="LT" else "### Planned")
    st.caption(
        "Šios dienos yra oficiali darbo būsena, ne pageidavimas. Jas galima keisti iki preliminaraus grafiko paskelbimo."
        if lang=="LT" else
        "These days are an official work status, not a scheduling wish. They can be edited until the preliminary schedule is published."
    )
    if _sd_published:
        st.info(
            "Grafikas jau paskelbtas — planuotos specialios dienos užrakintos, kad neperrašytų pradinio paskelbto grafiko."
            if lang=="LT" else
            "The schedule is already published, so planned special days are locked to protect the SYSTEM baseline."
        )
    with st.form(f"special_paid_days_{year}_{month}_{_sd_target}"):
        _sc1,_sc2=st.columns(2)
        with _sc1:
            with st.container(border=True):
                st.markdown("#### Sveikatinimosi dienos" if lang=="LT" else "#### Wellness days")
                st.caption(
                    "Apmokama darbo diena ne klinikoje. Ji nėra laisvadienis; klinikinis mėnesio krūvis sumažinamas 12 val. ekvivalentu."
                    if lang=="LT" else
                    "A paid workday outside clinical posts. It is not a day off; the clinical monthly target is reduced by a 12-hour equivalent."
                )
                _wellness=st.multiselect(
                    "Datos" if lang=="LT" else "Dates",
                    _sd_days,default=sorted(_sd_cur.get("wellness_days",set())),
                    format_func=lambda d:pretty_day(year,month,d),
                    disabled=_sd_published,
                    key=f"special_wellness_{year}_{month}_{_sd_target}",
                )
        with _sc2:
            with st.container(border=True):
                st.markdown("#### Kvalifikacijos kėlimo dienos" if lang=="LT" else "#### Qualification days")
                st.caption(
                    "Kursai, mokymai, konferencijos ar kita patvirtinta kvalifikacijos veikla. Apmokama darbo diena; klinikinis mėnesio krūvis sumažinamas 12 val. ekvivalentu."
                    if lang=="LT" else
                    "Courses, training, conferences, or other approved qualification activity. A paid workday; the clinical target is reduced by a 12-hour equivalent."
                )
                _qualification=st.multiselect(
                    "Datos" if lang=="LT" else "Dates",
                    _sd_days,default=sorted(_sd_cur.get("qualification_days",set())),
                    format_func=lambda d:pretty_day(year,month,d),
                    disabled=_sd_published,
                    key=f"special_qualification_{year}_{month}_{_sd_target}",
                )
        _save_special=st.form_submit_button(
            "IŠSAUGOTI SPECIALIAS DIENAS" if lang=="LT" else "SAVE SPECIAL DAYS",
            type="primary",disabled=_sd_published,use_container_width=True,
        )
    if _save_special:
        if set(_wellness) & set(_qualification):
            st.error("Ta pati data negali būti ir sveikatinimosi, ir kvalifikacijos kėlimo diena." if lang=="LT" else "The same date cannot be both wellness and qualification.")
        else:
            try:
                if lifecycle_operator_ui and _sd_target!=active_user:
                    db.save_special_workdays_for_resident_v25145(year,month,_sd_target,_wellness,_qualification)
                else:
                    db.save_my_special_workdays_v25145(year,month,_wellness,_qualification)
                if _sd_state.get("has_draft"):
                    st.session_state["_save_flash"]=("Specialios dienos išsaugotos. Esamą juodraštį reikia sugeneruoti iš naujo." if lang=="LT" else "Special days saved. Regenerate the existing draft.")
                else:
                    st.session_state["_save_flash"]=("Specialios dienos išsaugotos." if lang=="LT" else "Special days saved.")
                try: refresh_calendar_subscription_feeds([_sd_target])
                except Exception: pass
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.divider()
    st.markdown("### Po grafiko paskelbimo" if lang=="LT" else "### After publication")
    with st.container(border=True):
        st.markdown("#### Pateisinamas neatvykimas" if lang=="LT" else "#### Justified absence")
        if not _sd_published:
            st.info(
                "Atsirakins tik paskelbus preliminarų grafiką ir tada liks aktyvu visą mėnesį."
                if lang=="LT" else
                "Unlocks only after the preliminary schedule is published and then remains available throughout the month."
            )
        else:
            st.caption(
                "Nenumatytas pakeitimas jau paskelbtame grafike. Pradinis paskelbtas grafikas neperrašomas — atnaujinamas tik faktinis grafikas."
                if lang=="LT" else
                "An unplanned change to an already published schedule. The original SYSTEM schedule and fairness are preserved; only ACTUAL changes."
            )
            if lifecycle_operator_ui:
                _cur_payload=db.load_schedule(year,month,"current")
                _status_rows=db.list_schedule_day_statuses_v2597(year,month)
                _existing_by={(str(r.get("initials")),int(r.get("day"))):r for r in _status_rows}
                with st.form(f"special_absence_{year}_{month}_{_sd_target}"):
                    _absence_days=st.multiselect(
                        "Neatvykimo dienos" if lang=="LT" else "Absence days",
                        _sd_days,
                        default=sorted({d for (ini,d),r in _existing_by.items() if ini==_sd_target and r.get("status_kind")=="sick_leave"}),
                        format_func=lambda d:pretty_day(year,month,d),
                        key=f"special_absence_days_{year}_{month}_{_sd_target}",
                    )
                    _absence_note=st.text_input("Pastaba (tik operatoriui)" if lang=="LT" else "Note (operator only)",key=f"special_absence_note_{year}_{month}_{_sd_target}")
                    _save_absence=st.form_submit_button("IŠSAUGOTI NEATVYKIMĄ" if lang=="LT" else "SAVE ABSENCE",type="primary",use_container_width=True)
                if _save_absence:
                    try:
                        if not _cur_payload: raise RuntimeError("ACTUAL grafikas dar nesukurtas")
                        wanted={int(d) for d in _absence_days}
                        existing={d for (ini,d),r in _existing_by.items() if ini==_sd_target and r.get("status_kind")=="sick_leave"}
                        # Remove obsolete markers first. Removed ACTUAL assignments are intentionally not auto-restored.
                        for d in sorted(existing-wanted):
                            db.clear_schedule_day_status_v2597(int(_existing_by[(_sd_target,d)]["id"]))
                        _cur=deserialize_result(_cur_payload)
                        _slots={sl.idx:sl for sl in make_slots(year,month)}
                        _removed=[]
                        for d in sorted(wanted):
                            db.set_schedule_day_status_v2597(year,month,d,_sd_target,"sick_leave",_absence_note)
                            if d not in existing:
                                for _sid,_who in list((_cur.assignments or {}).items()):
                                    _sl=_slots.get(int(_sid))
                                    if _who==_sd_target and _sl is not None and int(_sl.day)==d:
                                        _removed.append(int(_sid)); _cur.assignments.pop(int(_sid),None)
                        _fresh=revalidate_loaded_result(year,month,people_for_stored_result(_cur,year,month),_cur,backup_assignments=db.list_backups(year,month),validation_mode="voluntary_swap_actual")
                        db.save_current(year,month,serialize_result(_fresh))
                        sync_backup_plan(year,month,_fresh)
                        persist_actual_satisfaction(year,month)
                        try: refresh_calendar_subscription_feeds([_sd_target])
                        except Exception: pass
                        st.success((f"Pateisinamas neatvykimas išsaugotas. Iš ACTUAL pašalinta pamainų: {len(_removed)}." if lang=="LT" else f"Justified absence saved. ACTUAL assignments removed: {len(_removed)}."))
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
                _status_rows=db.list_schedule_day_statuses_v2597(year,month)
                _mine=[r for r in _status_rows if str(r.get("initials"))==_sd_target and r.get("status_kind")=="sick_leave"]
                if _mine:
                    st.dataframe(pd.DataFrame([{
                        ("Data" if lang=="LT" else "Date"):f"{year}-{month:02d}-{int(r.get('day')):02d}",
                        ("Būsena" if lang=="LT" else "Status"):("Pateisinamas neatvykimas" if lang=="LT" else "Justified absence"),
                        ("Pastaba" if lang=="LT" else "Note"):r.get("note") or "",
                    } for r in _mine]),use_container_width=True,hide_index=True)
            else:
                st.info(
                    "Pateisinamą neatvykimą faktiniame grafike pažymi seniūnė. Jei atsirado nenumatyta situacija, informuokite ją — pradinis paskelbtas grafikas nuo to nebus perrašytas."
                    if lang=="LT" else
                    "The senior scheduler records justified absence in ACTUAL. If an unplanned event occurs, notify the senior; the original schedule fairness will not be rewritten."
                )


    if lifecycle_operator_ui:
        st.divider()
        _all_special=db.all_special_workdays_v25145(year,month)
        _status_all=db.list_schedule_day_statuses_v2597(year,month) if _sd_published else []
        _abs_by={}
        for r in _status_all:
            if r.get("status_kind")=="sick_leave": _abs_by.setdefault(str(r.get("initials")),[]).append(int(r.get("day")))
        _rows=[]
        for p in DEFAULT_PEOPLE:
            ini=p["initials"]; z=_all_special.get(ini,{})
            _rows.append({
                ("Rezidentas" if lang=="LT" else "Resident"):ini,
                ("Sveikatinimosi" if lang=="LT" else "Wellness"):", ".join(map(str,sorted(z.get("wellness_days",set())))),
                ("Kvalifikacijos" if lang=="LT" else "Qualification"):", ".join(map(str,sorted(z.get("qualification_days",set())))),
                ("Pateisinamas neatvykimas" if lang=="LT" else "Justified absence"):", ".join(map(str,sorted(_abs_by.get(ini,[])))),
            })
        st.markdown("### Grupės suvestinė" if lang=="LT" else "### Group overview")
        st.dataframe(pd.DataFrame(_rows),use_container_width=True,hide_index=True)
pos+=1

def _hard_error_explanation(raw, lang="LT"):
    s=str(raw)
    lt=[
        ("Mandatory slot unfilled", "Neužpildytas administraciškai privalomas SPS RO / SPS UG / savaitgalio slotas."),
        ("Gap dispersion violated", "Tą pačią dieną liko daugiau nei 1 reali neužpildyta optional vieta."),
        ("Gap workplace dispersion violated", "Neužpildytos optional vietos per daug susikoncentravo vienoje postų grupėje."),
        ("Gap-day dispersion pattern outdated", "Skylės nėra išmėtytos per mėnesį pagal dabartinę tolygaus paskirstymo taisyklę."),
        ("workload", "Rezidento mėnesio darbo krūvis neatitinka jo tikslaus targeto."),
        ("odd Onko", "Onko skaičius turi būti lyginis kiekvienam rezidentui: 0, 2, 4... Nelyginis 1/3/5 yra ABSOLUTE HARD klaida."),
        ("overlapping assignments", "Tam pačiam žmogui paskirtos laike persidengiančios pamainos."),
        ("HARD-unavailable", "Pamaina paskirta tuo metu, kai žmogus pažymėtas kaip HARD negalintis dirbti."),
        ("backup resident", "Privalomai dubliuojamai pamainai nėra laisvo ir HARD-prieinamo dublio."),
        ("weekend cap exceeded", "Pažeistas savaitgalio maksimalaus krūvio / unikalumo limitas."),
        ("rest between days", "Pažeistas minimalus poilsio laikas tarp darbo dienų."),
        ("workdays/7d cap", "Viršytas maksimalus darbo dienų skaičius per slenkantį 7 dienų langą."),
        ("hours/7d cap", "Viršytas maksimalus darbo valandų skaičius per slenkantį 7 dienų langą."),
        ("hours/day", "Viršytas maksimalus darbo valandų skaičius per dieną."),
    ]
    en=[
        ("Mandatory slot unfilled", "A mandatory SPS RO / SPS UG / weekend slot is not filled."),
        ("Gap dispersion violated", "The number of optional unfilled rows on a day does not match the workload-adjusted monthly plan."),
        ("Gap workplace dispersion violated", "Optional gaps are too concentrated in one workplace group."),
        ("Gap-day dispersion pattern outdated", "Gap dates do not match the current evenly distributed monthly pattern."),
        ("workload", "A resident's monthly workload does not match the exact target."),
        ("odd Onko", "Each resident must have an even Onko count: 0, 2, 4... Odd 1/3/5 is an ABSOLUTE HARD error."),
        ("overlapping assignments", "A resident has overlapping assignments."),
        ("HARD-unavailable", "A shift is assigned during HARD unavailability."),
        ("backup resident", "A required covered shift has no free HARD-eligible backup."),
        ("weekend cap exceeded", "Weekend uniqueness / resident cap is violated."),
        ("rest between days", "Minimum rest between workdays is violated."),
        ("workdays/7d cap", "Maximum workdays in a rolling 7-day window is exceeded."),
        ("hours/7d cap", "Maximum hours in a rolling 7-day window is exceeded."),
        ("hours/day", "Maximum hours per day is exceeded."),
    ]
    for key,msg in (lt if lang=="LT" else en):
        if key.lower() in s.lower():
            return msg
    return s


def render_hard_error_explainer(g, lang="LT", key_suffix=""):
    errors=list(g.get("errors") or [])
    title=("* Privalomų taisyklių klaidų paaiškinimas" if lang=="LT"
           else "* HARD-rule error explanation")
    with st.expander(title, expanded=bool(errors)):
        if not errors:
            st.success(
                "0 = dabartinis grafikas praeina visas šiuo metu aktyvias HARD patikras."
                if lang=="LT" else
                "0 = the current grafikas passes all active HARD checks."
            )
        else:
            st.error(
                f"Rasta {len(errors)} HARD klaidų." if lang=="LT"
                else f"{len(errors)} HARD errors found."
            )
            for n,e in enumerate(errors,1):
                st.markdown(f"**{n}.** {_hard_error_explanation(e,lang)}")
                if advanced_mode:
                    st.caption(str(e))


def solve_schedule_isolated(year, month, people, time_limit=90.0):
    """Run the production generator in a disposable Python process.

    V2.5.106 safety/reliability boundary: SciPy/HiGHS normally respects its MILP
    time limit, but a native solver call cannot be force-cancelled safely from the
    Streamlit thread if the underlying library stalls. The operational Generate /
    Rebuild path therefore runs the engine in a fresh child process. A hard OS-level
    watchdog can terminate a stuck worker, and one clean-process retry is allowed.

    The worker receives only a frozen request snapshot + active rule profile; it
    does not connect to Supabase and cannot mutate the existing draft. The caller
    saves a new draft only after a verified SolveResult(ok=True) returns.
    """
    worker=BASE / "solver_runner.py"
    if not worker.exists():
        return SolveResult(False,"ISOLATED SOLVER WORKER MISSING — deploy solver_runner.py with this release.")

    frozen=serialize_people_request_snapshot(people)
    _operator_private_payload={}
    for _p in people:
        _rows=[dict(x) for x in (getattr(_p,"privileged_pair_preferences",[]) or [])]
        if _rows:
            _operator_private_payload[str(getattr(_p,"initials","") or "")]=_rows
    payload={
        "year":int(year),
        "month":int(month),
        "time_limit":float(time_limit),
        "rules":get_runtime_rules(),
        "people_snapshot":frozen,
        # Ephemeral SP/ŠR private solver input. Never copied into the frozen/public request snapshot.
        "operator_private_pair_preferences":_operator_private_payload,
        "expected_engine_api":EXPECTED_ENGINE_API_VERSION,
    }
    last_result=None
    attempt_log=[]
    # First run is deliberately bounded well above the real September regression
    # (~25-35 s on the direct regression; slower clean workers can take longer).
    # The second run is a clean process with additional room for cloud variance.
    watchdogs=(100.0,130.0)
    for attempt_no,watchdog in enumerate(watchdogs,1):
        with tempfile.TemporaryDirectory(prefix="shift_happens_solver_") as td:
            ip=Path(td)/"input.json"
            op=Path(td)/"output.json"
            ip.write_text(json.dumps(payload,ensure_ascii=False),encoding="utf-8")
            t0=perf_counter()
            proc=None
            try:
                proc=subprocess.Popen(
                    [sys.executable,str(worker),str(ip),str(op)],
                    cwd=str(BASE),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    start_new_session=True,
                )
                stdout_text,stderr_text=proc.communicate(timeout=watchdog)
                elapsed=perf_counter()-t0
            except subprocess.TimeoutExpired:
                elapsed=perf_counter()-t0
                try:
                    if proc is not None and proc.poll() is None:
                        if os.name=="posix":
                            os.killpg(proc.pid,signal.SIGKILL)
                        else:
                            proc.kill()
                    if proc is not None:
                        proc.communicate(timeout=5.0)
                except Exception:
                    try:
                        if proc is not None: proc.kill()
                    except Exception:
                        pass
                attempt_log.append({"attempt":attempt_no,"watchdog_seconds":watchdog,"elapsed_seconds":round(elapsed,3),"outcome":"WATCHDOG_TIMEOUT"})
                continue
            except Exception as exc:
                elapsed=perf_counter()-t0
                try:
                    if proc is not None and proc.poll() is None:
                        if os.name=="posix": os.killpg(proc.pid,signal.SIGKILL)
                        else: proc.kill()
                except Exception:
                    pass
                attempt_log.append({"attempt":attempt_no,"watchdog_seconds":watchdog,"elapsed_seconds":round(elapsed,3),"outcome":"PROCESS_ERROR","detail":str(exc)[:300]})
                continue

            if proc.returncode!=0 or not op.exists():
                attempt_log.append({
                    "attempt":attempt_no,"watchdog_seconds":watchdog,"elapsed_seconds":round(elapsed,3),
                    "outcome":"WORKER_EXIT","returncode":int(proc.returncode),
                    "stderr":str(stderr_text or "")[-500:],
                })
                continue
            try:
                raw=json.loads(op.read_text(encoding="utf-8"))
                if str(raw.get("engine_api"))!=EXPECTED_ENGINE_API_VERSION:
                    raise ValueError(f"worker engine {raw.get('engine_api')} != expected {EXPECTED_ENGINE_API_VERSION}")
                result=deserialize_result(raw.get("result") or {})
            except Exception as exc:
                attempt_log.append({"attempt":attempt_no,"watchdog_seconds":watchdog,"elapsed_seconds":round(elapsed,3),"outcome":"BAD_WORKER_OUTPUT","detail":str(exc)[:300]})
                continue

            attempt_log.append({"attempt":attempt_no,"watchdog_seconds":watchdog,"elapsed_seconds":round(elapsed,3),"outcome":"OK" if result.ok else "NO_VERIFIED_CANDIDATE"})
            last_result=result
            if result.ok:
                g=(result.stats or {}).setdefault("global",{})
                g["solver_process_mode"]="ISOLATED_SUBPROCESS"
                g["isolated_worker_attempts"]=attempt_no
                g["isolated_worker_attempt_log"]=attempt_log
                g["isolated_worker_watchdog_passed"]=True
                return result
            # Definitive model/validator errors should be shown immediately. Only
            # retry the explicit no-candidate/time-limit class in a clean process.
            retryable=("PREFERENCE-AWARE GENERATION DID NOT FINISH" in str(result.message or ""))
            if not retryable:
                return result

    if last_result is not None:
        last_result.message=(
            "ISOLATED GENERATION DID NOT RETURN A VERIFIED CANDIDATE AFTER CLEAN-PROCESS RETRY. "
            "The request set was not proven infeasible. The DB draft row is not replaced; if it fails "
            "current-engine validation it is audit-only and cannot be published or used as an improvement baseline."
        )
        return last_result
    return SolveResult(
        False,
        "ISOLATED GENERATION WATCHDOG STOPPED THE SOLVER ON BOTH CLEAN-PROCESS ATTEMPTS. "
        "No infeasibility was inferred. The DB draft row is not replaced; any row that fails current-engine "
        "validation remains audit-only and cannot be published or used as an improvement baseline.",
        request_snapshot=frozen,
    )


def _draft_quality_tuple(result):
    """Lexicographic V2.5.49 draft comparison — lower is better.

    V2.5.107 requires every candidate to have 0 RESIDENT-HARD misses. Within that
    mandatory zero-loss space, ordinary fairness/SOFT refinements decide the winner.
    """
    g=(result.stats or {}).get("global",{})
    hard=int(g.get("hard_errors",9999))
    rh_total=int(g.get("resident_hard_total_losses",9999))
    rh_max=int(g.get("resident_hard_max_loss_per_resident",9999))
    rh_cum=int(g.get("resident_hard_cumulative_spread",9999))
    worst_post=int(g.get("worst_monthly_post_spread",9999))
    soft_min=g.get("min_soft_preference_score")
    soft_mean=g.get("mean_soft_preference_score")
    overall_mean=g.get("mean_preference_score")
    monthly_fair=float(g.get("monthly_fairness_score",g.get("fairness_score",0)) or 0)
    cumulative_fair=float(g.get("cumulative_fairness_score",g.get("fairness_score",0)) or 0)
    return (
        hard,
        rh_total,
        rh_max,
        rh_cum,
        worst_post,
        -(float(soft_min) if soft_min is not None else 100.0),
        -(float(soft_mean) if soft_mean is not None else 100.0),
        -monthly_fair,
        -cumulative_fair,
        -(float(overall_mean) if overall_mean is not None else 100.0),
    )

# --- Generation ---
if senior_mode:
    with tabs[pos]:
        st.subheader(tr("generation_title")); state=db.get_schedule_state(year,month)
        _state_draft_payload=db.load_schedule(year,month,"draft") if state.get("has_draft") else None
        _state_draft_health=draft_compatibility_status(_state_draft_payload,year,month) if _state_draft_payload else None
        if state.get("has_published"):
            status=tr("published_state")
        elif _state_draft_payload and not (_state_draft_health or {}).get("publishable"):
            status=("NEGALIOJANTIS JUODRAŠTIS" if lang=="LT" else "INVALID DRAFT")
        elif state.get("has_draft"):
            status=tr("draft")
        else:
            status=tr("not_created")
        st.metric(tr("state"),status)
        if _state_draft_health and not _state_draft_health.get("publishable"):
            render_invalid_draft_guard(_state_draft_health,compact=True)
        if state.get("has_draft") and not state.get("has_published") and (_state_draft_health or {}).get("valid_for_improve"):
            st.info(
                "NORINT GERESNIO GRAFIKO JO TRINTI NEREIKIA. Spausk „BANDYTI GERESNĮ GRAFIKĄ“ žemiau. "
                "Sistema paliks dabartinį juodraštį, jei naujas variantas bus blogesnis arba nepraeis HARD patikros."
                if lang=="LT" else
                "YOU DO NOT NEED TO DELETE THE DRAFT TO TRY FOR A BETTER SCHEDULE. Press TRY A BETTER SCHEDULE below. "
                "The current draft is kept if the new candidate is worse or fails HARD validation."
            )
        lifecycle_generation=db.get_schedule_lifecycle(year,month)
        generation_locked=bool(state.get("has_published")) or str(lifecycle_generation.get("state") or "") in ("working","swap_open","swap_closed","final")
        # V2.5.128: SP ir ŠR generavimo metu gauna tą patį privatų refinemento
        # įvesties sluoksnį. Todėl ŠR nebereikia blokuoti vien dėl privačių tikslų.
        _sp_private_generation_gate=False
        if generation_locked:
            st.warning("SYSTEM jau užšaldytas šiame lifecycle etape. Operacinio juodraščio regeneruoti / gerinti nebegalima; swapai keičia tik ACTUAL, o FINAL nekeičia SYSTEM." if lang=="LT" else "SYSTEM is frozen at this lifecycle stage. The operational draft can no longer be regenerated/improved; swaps change ACTUAL only and FINAL does not rewrite SYSTEM.")
        prefs=db.all_preferences(year,month); missing=[p["initials"] for p in DEFAULT_PEOPLE if p["initials"] not in prefs]
        _submitted_count=len(DEFAULT_PEOPLE)-len(missing)
        st.caption(
            (f"{year}-{month:02d} · pateikė {_submitted_count}/{len(DEFAULT_PEOPLE)} · juodraštis: " + ("yra" if state.get("has_draft") else "nėra"))
            if lang=="LT" else
            (f"{year}-{month:02d} · submitted {_submitted_count}/{len(DEFAULT_PEOPLE)} · draft: " + ("present" if state.get("has_draft") else "none"))
        )
        if missing: st.warning(f"{tr('missing_preferences')}: {', '.join(missing)}")
        c1,c2=st.columns(2)
        with c1:
            if active_user==SENIOR_INITIALS:
                try:
                    _weston_now=db.weston_beer_stats_v25110(year,month)
                    st.caption(
                        f"1 click = 1 WESTON beer ŠR · tavo skola ŠR: {_weston_now.get('total_beers',0)}"
                        if lang=="LT" else
                        f"1 click = 1 WESTON beer owed to ŠR · your debt to ŠR: {_weston_now.get('total_beers',0)}"
                    )
                except Exception:
                    _weston_now={"total_beers":0,"month_beers":0}
            if st.button(tr("generate_draft"),type="primary",use_container_width=True,disabled=(generation_locked or _sp_private_generation_gate)):
                if active_user==SENIOR_INITIALS:
                    try:
                        _weston_after=db.record_weston_beer_click_v25110(year,month)
                        st.caption(
                            f"WESTON +1. Dabar ŠR esi skolinga: {_weston_after.get('total_beers',0)}."
                            if lang=="LT" else
                            f"WESTON +1. You now owe ŠR: {_weston_after.get('total_beers',0)}."
                        )
                    except Exception:
                        st.warning(
                            "WESTON skaitiklio nepavyko įrašyti; grafiko generavimas tęsiamas."
                            if lang=="LT" else
                            "The WESTON counter could not be recorded; grafikas generation will continue."
                        )
                credit_err=credit_selection_errors(year,month)
                if credit_err:
                    st.error(tr("bonus_insufficient")); st.dataframe(pd.DataFrame(credit_err),use_container_width=True,hide_index=True)
                else:
                    t0=perf_counter()
                    with st.spinner(tr("solver_wait")): result=solve_schedule_isolated(year,month,load_people(year,month),time_limit=90)
                    elapsed=perf_counter()-t0
                    try:
                        gg=(result.stats or {}).get("global",{}) if result.ok else {}
                        db.record_research_generation_event(
                            year,month,elapsed,result.ok,gg.get("hard_errors"),
                            gg.get("monthly_fairness_score",gg.get("fairness_score")),
                            gg.get("cumulative_fairness_score",gg.get("fairness_score")),
                            gg.get("mean_preference_score")
                        )
                    except Exception:
                        pass
                    if result.ok:
                        # V2.5.115: first freeze/revalidate the NORMAL grafikas by itself.
                        # The theoretical backup plan is built only afterwards as a separate
                        # standby layer and can never change wish scores or normal-schedule HARD.
                        result=revalidate_loaded_result(
                            year,month,people_for_stored_result(result,year,month),result,
                            backup_assignments=[]
                        )
                        if result.stats.get("global",{}).get("hard_errors",0):
                            st.error(tr("draft_outdated"))
                            _berr=result.stats.get("global",{}).get("errors",[])
                            if _berr: st.dataframe(pd.DataFrame(_berr),use_container_width=True,hide_index=True)
                        else:
                            desired,backup_errors=plan_backups(year,month,result)
                            result.backup_snapshot=[dict(x) for x in desired]
                            _gg=result.stats.setdefault("global",{})
                            _gg["theoretical_backup_layer"]=True
                            _gg["theoretical_backup_layer_errors"]=list(backup_errors)
                            _gg["theoretical_backup_layer_complete"]=(len(backup_errors)==0)
                            result=stamp_generation_provenance(result,"generate_rebuild")
                            db.save_draft(year,month,serialize_result(result))
                            # V2.5.120: GENERATE/REBUILD never publishes anything.
                            # SP/ŠR may generate repeatedly while searching for a better draft.
                            # Preliminary publication is a separate explicit operator action.
                            st.success(tr("draft_saved"))
                            if weekend_fcfs_backup_mode(year,month):
                                try:
                                    _phase=(db.scheduler_cycle_phase_v25119(year,month) or {}).get("phase")
                                except Exception:
                                    _phase=None
                                if _phase=="swaps":
                                    st.info("Juodraštis paruoštas. Jei tinka, eikite į Grafikas → Grafiko tvirtinimas ir spauskite PASKELBTI PRELIMINARŲ. Iki tol rezidentai jo nemato ir swapų pradėti negali." if lang=="LT" else "Draft ready. If acceptable, go to Schedule → Confirmation and press PUBLISH PRELIMINARY. Until then residents cannot see it or start swaps.")
                                elif _phase=="senior_review":
                                    st.info("Rezidentų langai jau uždaryti. Juodraštį dar galite perdaryti; kai pasirinksite versiją, Grafikas → Grafiko tvirtinimas paruoškite ACTUAL ir atlikite FINAL review." if lang=="LT" else "Resident windows are already closed. You may still rebuild the draft; once you choose a version, prepare ACTUAL in Schedule → Confirmation and complete FINAL review.")
                            if backup_errors:
                                st.warning(
                                    "NORMALUS grafikas išsaugotas ir jo pageidavimų auditas lieka validus. Atskirame teorinių dublių sluoksnyje dar trūksta kelių standby paskyrimų; tai nėra darbo grafiko ar pageidavimų pažeidimas."
                                    if lang=="LT" else
                                    "The NORMAL grafikas was saved and its request audit remains valid. The separate theoretical backup layer still has standby gaps; these are not work-schedule or preference violations."
                                )
                                st.dataframe(pd.DataFrame(backup_errors),use_container_width=True,hide_index=True)
                            _bc=backup_counts(year,month,result)[0]
                            _vals=list(_bc.values())
                            st.caption(
                                (f"TEORINIS savaitgalio FCFS dublių sluoksnis: {sum(_vals)} standby pareigų · rezidentų spread {max(_vals)-min(_vals) if _vals else 0}. Jos NĖRA darbo pamainos."
                                 if lang=="LT" else
                                 f"THEORETICAL weekend FCFS backup layer: {sum(_vals)} standby duties · resident spread {max(_vals)-min(_vals) if _vals else 0}. They are NOT work shifts.")
                            )
                            norm=(result.stats or {}).get("global",{}).get("preference_normalization",[])
                            if norm:
                                st.caption(
                                    f"Preference pre-check: {len(norm)} redundant / impossible / engine-covered SOFT signalai "
                                    "nebuvo antrą kartą įtraukti į optimizerį."
                                )
                            if "fallback" in (result.message or "").lower():
                                st.warning(
                                    "Globalus fairness MILP nespėjo pilnai užsibaigti, bet sistema prieš išsaugodama pritaikė local fairness repair loop. "
                                    "Grafikas yra HARD-valid; „BANDYTI GERESNĮ GRAFIKĄ“ gali bandyti jį dar pagerinti."
                                )
                            # V2.5.166: do NOT force a second rerun here. Streamlit tabs otherwise
                            # jump back to Pageidavimai after every successful generation. The code
                            # below reloads the just-saved draft during this same run.
                    else:
                        _msg=result.message if getattr(result,"message",None) else tr("no_solution")
                        if ("PREFERENCE-AWARE GENERATION DID NOT FINISH" in str(_msg) or "ISOLATED GENERATION" in str(_msg)):
                            _after_fail_payload=db.load_schedule(year,month,"draft")
                            _after_fail_health=draft_compatibility_status(_after_fail_payload,year,month) if _after_fail_payload else None
                            if _after_fail_health and not _after_fail_health.get("publishable"):
                                st.error(
                                    "NAUJAS GRAFIKAS NESUGENERUOTAS. Solveris neįrodė neįmanomumo, bet ir negavo patvirtinto 0-HARD kandidato. "
                                    "Esamas DB juodraštis yra NEGALIOJANTIS pagal dabartinį engine, todėl jis paliktas tik auditui — jo skelbti ar gerinti negalima. "
                                    "Spausk GENERUOTI / PERKURTI dar kartą."
                                    if lang=="LT" else
                                    "NEW SCHEDULE NOT GENERATED. The solver did not prove infeasibility, but it also did not return a verified zero-HARD candidate. "
                                    "The stored DB draft is INVALID under the current engine and is retained for audit only — it cannot be published or improved. "
                                    "Run GENERATE / REBUILD again."
                                )
                                render_invalid_draft_guard(_after_fail_health,compact=True)
                            else:
                                st.warning(
                                    "Solveris neįrodė, kad grafikas neįmanomas — jis tiesiog negavo patvirtinto kandidato net po automatinio retry. "
                                    "Esamas CURRENT-engine validus juodraštis, jei yra, nepakeistas. Galima spausti GENERUOTI / PERKURTI dar kartą."
                                    if lang=="LT" else
                                    "The solver did not prove the schedule infeasible; it simply did not obtain a verified candidate even after automatic retry. "
                                    "Any CURRENT-engine-valid draft is preserved. You can run GENERATE / REBUILD again."
                                )
                        else:
                            st.error(_msg)
        draft_for_improve=db.load_schedule(year,month,"draft")
        if draft_for_improve:
            _improve_health=draft_compatibility_status(draft_for_improve,year,month)
            current_draft=_improve_health.get("result")
            if not _improve_health.get("valid_for_improve"):
                render_invalid_draft_guard(_improve_health)
                st.caption(
                    "PERTIKRINTI / GERINTI išjungtas: negaliojantis ar pasenęs juodraštis negali būti kokybės baseline. Pirmiausia sukurkite naują 0-HARD juodraštį su GENERUOTI / PERKURTI."
                    if lang=="LT" else
                    "IMPROVE is disabled: an invalid/outdated draft cannot be a quality baseline. First create a new zero-HARD draft with GENERATE / REBUILD."
                )
            else:
                st.caption(
                    "Dabartinis juodraštis saugus: 0 HARD / 0 „Negaliu dirbti“ pažeidimų. Gali bandyti dar kartą — dabartinis variantas lieka, kol randamas tikrai geresnis."
                    if lang=="LT" else
                    "The current draft is safe: 0 HARD / 0 Cannot-work violations. You can try again — the current version stays unless a genuinely better one is found."
                )
            if st.button(
                ("BANDYTI GERESNĮ GRAFIKĄ — SAUGOTI TIK JEI GERESNIS" if lang=="LT" else "TRY A BETTER SCHEDULE — KEEP ONLY IF BETTER"),
                type="primary",use_container_width=True,key=f"improve_{year}_{month}",
                disabled=(generation_locked or _sp_private_generation_gate or not _improve_health.get("valid_for_improve"))
            ):
                t0=perf_counter()
                with st.spinner("Ieškau geresnio varianto pagal nustatytą prioritetų tvarką: privalomos taisyklės → validūs pageidavimai (100 % tikslas) → fairness / darbo vietų paskirstymas..."):
                    candidate=solve_schedule_isolated(year,month,load_people(year,month),time_limit=90)
                elapsed=perf_counter()-t0
                if not candidate.ok:
                    st.warning(("Esamas CURRENT-engine validus juodraštis paliktas nepakeistas. Naujo geresnio kandidato rasti nepavyko: " if lang=="LT" else "The existing CURRENT-engine-valid draft was preserved. No better candidate was found: ")+str(candidate.message))
                else:
                    candidate=revalidate_loaded_result(year,month,people_for_stored_result(candidate,year,month),candidate,backup_assignments=[])
                    _cand_backups,_cand_backup_errors=plan_backups(year,month,candidate)
                    candidate.backup_snapshot=[dict(x) for x in _cand_backups]
                    _cgg=candidate.stats.setdefault("global",{})
                    _cgg["theoretical_backup_layer"]=True
                    _cgg["theoretical_backup_layer_errors"]=list(_cand_backup_errors)
                    _cgg["theoretical_backup_layer_complete"]=(len(_cand_backup_errors)==0)
                    old_q=_draft_quality_tuple(current_draft)
                    new_q=_draft_quality_tuple(candidate)
                    _replace_candidate=(new_q < old_q)
                    # Privatus SP + ŠR palyginimas leidžiamas tik tada, kai VISAS
                    # viešas kokybės tuple yra identiškas. Taip privatus refinementas
                    # niekada nepablogina fairness ar jokio rezidento pageidavimo.
                    if (not _replace_candidate) and new_q==old_q:
                        _priv_rows=_list_operator_private_pair_preferences_v25130(year,month)
                        if _priv_rows:
                            _old_honored=0; _new_honored=0
                            for _owner in (SENIOR_INITIALS,RESEARCHER_INITIALS):
                                _owner_rows=[r for r in _priv_rows if str(r.get("owner_initials") or "")==_owner]
                                if not _owner_rows:
                                    continue
                                _old_priv=operator_private_pair_preference_summary(_owner,year,month,current_draft,_owner_rows)
                                _new_priv=operator_private_pair_preference_summary(_owner,year,month,candidate,_owner_rows)
                                _old_honored+=int(_old_priv.get("honored",0))
                                _new_honored+=int(_new_priv.get("honored",0))
                            _replace_candidate=(_new_honored > _old_honored)
                    if _replace_candidate:
                        candidate=stamp_generation_provenance(candidate,"improve_recheck")
                        db.save_draft(year,month,serialize_result(candidate))
                        st.success(
                            "Rastas geresnis NORMALUS grafikas ir juodraštis pakeistas. "
                            "Teorinis dublių sluoksnis vertinamas atskirai ir niekada nekeičia pageidavimų score."
                            if lang=="LT" else
                            "A better NORMAL grafikas was found and saved. The theoretical backup layer is evaluated separately and never changes request scores."
                        )
                        if _cand_backup_errors:
                            st.warning("Atskirame standby dublių sluoksnyje liko neuždengtų vietų." if lang=="LT" else "The separate standby backup layer still has uncovered duties.")
                        # V2.5.166: stay in Sudarymas; the fresh draft is reloaded below.
                    else:
                        st.success(
                            "Pertikrinta. Naujas normalus grafikas nebuvo geresnis pagal užfiksuotą hierarchiją, todėl esamas juodraštis paliktas."
                            if lang=="LT" else
                            "Rechecked. The new normal grafikas was not better under the locked hierarchy, so the existing draft was kept."
                        )

        with c2:
            st.info(
                "SYSTEM patvirtinimas ir apsikeitimų lango atidarymas perkeltas į Grafikas → Grafiko tvirtinimas. "
                "Taip visas mėnesio lifecycle valdomas vienoje Grafiko tvirtinimo vietoje."
                if lang=="LT" else
                "SYSTEM confirmation and opening the swap window moved to Schedule → Finalization. "
                "This keeps the whole monthly lifecycle in one Schedule control center."
            )
            st.caption(("Sugeneruok / pagerink juodraštį čia, tada eik į Grafikas." if lang=="LT" else "Generate/improve the draft here, then open Schedule."))
        draftp=db.load_schedule(year,month,"draft")
        if draftp:
            _display_health=draft_compatibility_status(draftp,year,month)
            dr=_display_health.get("result") or refresh_result_payload(draftp,year,month,use_actual_backups=False)
            if not _display_health.get("publishable"):
                render_invalid_draft_guard(_display_health)
            elif _display_health.get("kind")=="valid_legacy_provenance":
                st.warning(
                    "LEGACY PROVENANCE, BET CURRENT ENGINE VALIDUS — 0 HARD / 0 „Negaliu dirbti“. Juodraštis gali būti skelbiamas, tačiau pirmas naujas GENERUOTI / GERINTI jį perrašys su dabartinio V2.5.153 engine provenance."
                    if lang=="LT" else
                    "LEGACY PROVENANCE, BUT CURRENT-ENGINE VALID — 0 HARD / 0 Cannot-work. It can be published; the next GENERATE / IMPROVE will restamp it with current V2.5.153 engine provenance."
                )
            _prov=dict(getattr(deserialize_result(draftp),"provenance",None) or {})
            if _prov:
                st.caption(
                    f"Draft provenance: app={_prov.get('app_version') or 'legacy'} · engine={_prov.get('engine_api_version') or _display_health.get('stored_engine') or 'legacy'} · generated={_prov.get('generated_at_utc') or 'unknown'}"
                )
            g=dr.stats["global"]
            c1,c2,c3,c4=st.columns(4)
            c1.metric(tr("hard_errors")+" *",g["hard_errors"])
            fair_valid=(int(g.get("hard_errors",0))==0)
            c2.metric(tr("cumulative_fairness"),f"{g.get('cumulative_fairness_score',g['fairness_score'])}%" if fair_valid else "—")
            c3.metric(tr("monthly_fairness"),f"{g.get('monthly_fairness_score',g['fairness_score'])}%" if fair_valid else "—")
            c4.metric(tr("preference_avg"),tr("not_applicable") if g["mean_preference_score"] is None else f"{g['mean_preference_score']}%")

            # V2.5.107: every generation result immediately explains what wishes
            # were and were not achieved. Senior users should never need to infer
            # misses from a percentage alone.
            _wish=generation_wish_summary(dr)
            wa,wb,wc,wd=st.columns(4)
            wa.metric(("Aktyvūs pageidavimai" if lang=="LT" else "Active wishes"),_wish["total"])
            wb.metric(("Įvykdyta" if lang=="LT" else "Honored"),_wish["honored"])
            wc.metric(("Neįvykdyta" if lang=="LT" else "Missed"),_wish["missed"])
            wd.metric(("Negaliu dirbti pažeidimai" if lang=="LT" else "Cannot-work violations"),_wish["hard_missed"])
            if _wish["hard_missed"]:
                st.error(
                    "KRITINĖ KLAIDA: sugeneruotas juodraštis turi „Negaliu dirbti“ pažeidimą. V2.5.153 tokio juodraščio skelbti negalima."
                    if lang=="LT" else
                    "CRITICAL ERROR: the generated draft contains a Cannot-work violation. V2.5.153 must not publish such a draft."
                )
            elif _wish["missed"]==0:
                st.success(
                    "VISI AKTYVŪS PAGEIDAVIMAI ĮVYKDYTI — „Negaliu dirbti“ pažeidimų: 0."
                    if lang=="LT" else
                    "ALL ACTIVE WISHES MET — Cannot-work violations: 0."
                )
            else:
                st.warning(
                    f"Neįvykdyta {_wish['missed']} iš {_wish['total']} aktyvių pageidavimų. „Negaliu dirbti“ pažeidimų: 0. Žemiau tiksliai parodyta, kas neįvykdyta."
                    if lang=="LT" else
                    f"{_wish['missed']} of {_wish['total']} active wishes were not met. Cannot-work violations: 0. The exact misses are shown below."
                )
                st.markdown("#### Neįvykdyti pageidavimai" if lang=="LT" else "#### Unmet wishes")
                render_all_missed_requests_scandi(dr)

            # Privataus operatorių refinemento detalės sąmoningai nerodomos bendrame
            # Sudarymo lange. Jos redaguojamos tiesiai „Pageidavimai“ lange.
            _wcap=g.get("admin_weekend_spread_cap_used")
            _bp,_be=backup_counts(year,month,dr)
            _bvals=list(_bp.values())
            _bspread=(max(_bvals)-min(_bvals)) if _bvals else 0
            _ga,_gb=st.columns(2)
            _ga.metric("Savaitgalių paskirstymo skirtumas",_wcap if _wcap is not None else "—")
            _gb.metric(("Dublių užpildymas" if weekend_fcfs_backup_mode(year,month) else "Dublių pasiskirstymo skirtumas"),(_bspread if not weekend_fcfs_backup_mode(year,month) else f"{sum(_bvals)}/16"))
            if weekend_fcfs_backup_mode(year,month):
                st.caption(
                    (f"FCFS savaitgalio dubliai ateina tiesiai iš Pageidavimų pasirinkimų: {sum(_bvals)}/16. Jie nėra generuojami solverio ir nekeičia normalaus SYSTEM grafiko."
                     if lang=="LT" else
                     f"FCFS weekend backups come directly from Preferences selections: {sum(_bvals)}/16. They are not generated by the solver and never change the normal SYSTEM schedule.")
                )
            else:
                st.caption(
                    (f"AUTO dubliai sukurti visoms svarbioms pozicijoms kartu su SYSTEM juodraščiu. Iš viso {sum(_bvals)} pareigų; rezidentų skaičiai: " + ", ".join(f"{i}={_bp.get(i,0)}" for i in sorted(_bp)))
                    if lang=="LT" else
                    (f"AUTO backups were created for the important positions together with the SYSTEM draft. Total {sum(_bvals)} duties; resident counts: " + ", ".join(f"{i}={_bp.get(i,0)}" for i in sorted(_bp)))
                )

            # V2.5.116 — senior sees the entire theoretical backup plan immediately
            # in Sudarymas, before publication. The snapshot remains non-operational
            # until SYSTEM is published; this is oversight only, not real work.
            st.markdown("### TEORINIS DUBLIŲ PLANAS — SENIŪNĖS PATIKRA" if lang=="LT" else "### THEORETICAL BACKUP PLAN — SENIOR REVIEW")
            st.info(
                (("Šiame juodraštyje rodomas tuo metu jau pasirinktas FCFS savaitgalio dublių snapshotas. Solveris jų negeneruoja ir jie nekeičia normalaus grafiko. SP gali prieš tvirtinimą patikrinti, ar turime 16/16 ir ar nėra akivaizdžių nesąmonių."
                  if lang=="LT" else
                  "This draft shows the FCFS weekend-backup snapshot already selected at that moment. The solver does not generate these backups and they never change the normal schedule. SP can verify 16/16 and inspect the plan before confirmation.")
                 if weekend_fcfs_backup_mode(year,month) else
                 ("Šis dublių planas sugeneruotas tuo pačiu GENERUOTI paspaudimu ir yra SYSTEM juodraščio dalis peržiūrai. Jis dar NĖRA realus darbas ir iki paskelbimo nėra operacinis. Patikrink pasiskirstymą, datas ir dengiamas pozicijas prieš tvirtindama grafiką."
                  if lang=="LT" else
                  "This backup plan is generated by the same GENERATE click and is part of the SYSTEM draft for review. It is NOT real work and remains non-operational until publication. Review distribution, dates and covered positions before confirming the schedule."))
            )
            _bo=backup_overview_grid(year,month,dr)
            st.dataframe(_bo,use_container_width=True,height=520,hide_index=True)
            with st.expander(("Visas dublių sąrašas — kiekviena dengiama pamaina" if lang=="LT" else "Full backup list — every covered shift"),expanded=False):
                _bt=backup_table(year,month,dr)
                st.dataframe(_bt,use_container_width=True,hide_index=True,height=520)
            _draft_backup_errors=list(g.get("theoretical_backup_layer_errors") or [])
            if _draft_backup_errors:
                st.warning(
                    "Teoriniame dublių sluoksnyje yra neuždengtų standby vietų. Normalus darbo grafikas dėl to nėra klaidingas, bet prieš paskelbiant seniūnė turi tai matyti ir įvertinti."
                    if lang=="LT" else
                    "The theoretical backup layer has uncovered standby duties. The normal work grafikas remains valid, but the senior should review these before publication."
                )
                st.dataframe(pd.DataFrame(_draft_backup_errors),use_container_width=True,hide_index=True)
            else:
                st.success(
                    "TEORINIS DUBLIŲ PLANAS PILNAS — visos privalomos standby pozicijos turi vardinį dublį."
                    if lang=="LT" else
                    "THEORETICAL BACKUP PLAN COMPLETE — every mandatory standby position has a named backup."
                )

            render_hard_error_explainer(g,lang,key_suffix=f"gen_{year}_{month}")
            st.caption(
                ("Teisingumas: 100% = idealus / beveik idealus balansas pagal postus, savaitgalius, penktadienius, doubles ir darbo dienų spread. "
                 "Rodomas score perskaičiuojamas gyvai pagal dabartinį engine."
                 if lang=="LT" else
                 "Fairness: 100% = ideal / near-ideal balance across workplaces, weekends, Fridays, doubles and weekday spread. "
                 "The score is recalculated live by the current engine.")
            )
            st.dataframe(style_schedule(schedule_grid(year,month,dr)),use_container_width=True,height=520)
            st.caption(
                "Lentelės viršuje Streamlit siūlo CSV. Žemiau visada pateikiamas ir pilnas spalvotas Excel failas."
                if lang=="LT" else
                "Streamlit offers CSV in the table toolbar. A full formatted Excel failas is always available below as well."
            )
            _export_valid=bool(_display_health.get("publishable"))
            render_schedule_download_buttons(
                year,month,dr,
                status_label=(("SYSTEM JUODRAŠTIS" if lang=="LT" else "SYSTEM DRAFT") if _export_valid else ("INVALID LEGACY DRAFT — TIK AUDITUI" if lang=="LT" else "INVALID LEGACY DRAFT — AUDIT ONLY")),
                file_prefix=("SYSTEM_juodrastis" if lang=="LT" else "SYSTEM_draft") if _export_valid else "INVALID_DRAFT_AUDIT_ONLY",
                key_prefix="generation_draft_export",
            )

        # V2.5.166 — generation UX: a normal draft never needs the destructive
        # month reset just to try another candidate. Draft-only discard is one-click
        # and keeps all inputs; published SYSTEM still requires the guarded full reset.
        state_now=db.get_schedule_state(year,month)
        if state_now.get("has_draft") and not state_now.get("has_published"):
            st.divider()
            with st.expander(("Juodraščio valdymas" if lang=="LT" else "Draft controls"), expanded=False):
                st.caption(
                    "Geresniam variantui šito naudoti nereikia — spausk „BANDYTI GERESNĮ GRAFIKĄ“. "
                    "Šis mygtukas tik išmeta dabartinį juodraštį; pageidavimai, HARD ir credit pasirinkimai lieka."
                    if lang=="LT" else
                    "You do not need this to search for a better version — use TRY A BETTER SCHEDULE. "
                    "This only discards the current draft; preferences, HARD inputs and credit selections remain."
                )
                if st.button(
                    ("IŠMESTI TIK JUODRAŠTĮ" if lang=="LT" else "DISCARD DRAFT ONLY"),
                    use_container_width=True,key=f"discard_draft_{year}_{month}"
                ):
                    try:
                        db.discard_draft_only(year,month)
                        st.session_state.pop("shadow_result",None)
                        st.success(
                            "Juodraštis išmestas. Visi inputai liko. Šiame lange gali iškart spausti GENERUOTI / PERKURTI."
                            if lang=="LT" else
                            "Draft discarded. All inputs remain. You can immediately GENERATE / REBUILD in this same window."
                        )
                        # V2.5.166 operator navigation opens Sudarymas first, so this
                        # refresh no longer throws the user back to Pageidavimai.
                        st.rerun()
                    except Exception as e:
                        st.error(("Juodraščio išmesti nepavyko: " if lang=="LT" else "Could not discard draft: ")+str(e))

        if state_now.get("has_published"):
            st.divider()
            with st.expander("PAVOJINGA ZONA — ištrinti PASKELBTĄ mėnesio grafiką", expanded=False):
                st.warning(
                    "Čia tik PASKELBTAM grafikui. Jei nori tik geresnio juodraščio, šios zonos nenaudok. "
                    "Pilnas reset pašalins draft, paskelbtą SYSTEM/ACTUAL grafiką, šio mėnesio fairness_history, suplanuotus dublius, "
                    "apsikeitimų užklausas ir administracinius repair įrašus. Pageidavimai, HARD, recurring ir credit redemptions LIEKA."
                )
                st.caption(
                    "Jei šiame grafike jau buvo realiai užbaigtas dublio/pavadavimo įvykis, reset bus blokuojamas."
                )
                reset_ack=st.checkbox(
                    "Suprantu: bus ištrintas paskelbtas šio mėnesio grafikas ir jo operacinė istorija, bet pageidavimai / HARD inputai liks.",
                    key=f"reset_confirm_{year}_{month}"
                )
                if st.button(
                    "IŠTRINTI PASKELBTĄ GRAFIKĄ IR GRĮŽTI Į SUDARYMĄ",
                    type="primary",disabled=not reset_ack,use_container_width=True,
                    key=f"reset_month_{year}_{month}"
                ):
                    try:
                        db.reset_month_schedule(year,month)
                        st.session_state.pop("shadow_result",None)
                        st.success(
                            f"{year}-{month:02d} paskelbtas grafikas ištrintas. Pageidavimai ir HARD inputai išsaugoti. "
                            "Kitas veiksmas — GENERUOTI / PERKURTI."
                        )
                        # The operator's first visible tab is now Sudarymas, so a refresh
                        # immediately returns here with generation unlocked.
                        st.rerun()
                    except Exception as e:
                        msg=str(e)
                        if "RESET_BLOCKED_FINAL_SCHEDULE" in msg:
                            st.error("RESET BLOKUOTAS: šio mėnesio grafikas jau patvirtintas kaip FINAL administracijai. FINAL snapshotas yra nekeičiamas.")
                        elif "RESET_BLOCKED_COMPLETED_BACKUP_ACTIVITY" in msg:
                            st.error(
                                "RESET BLOKUOTAS: šiame mėnesyje jau yra realiai užbaigtas dublio/pavadavimo įvykis. "
                                "Tokio mėnesio automatiškai trinti nesaugu."
                            )
                        elif "SENIOR_ONLY" in msg:
                            st.error("Šią funkciją gali naudoti tik seniūnės/senior paskyra.")
                        else:
                            st.error(f"Reset nepavyko: {e}")
    pos+=1
elif active_user=="ŠR":
    # ŠR has the same Sudarymas tab position, but it is rendered later as a
    # completely isolated RESEARCH SHADOW generator after the research import
    # helpers are defined.
    pos+=1

# --- Schedule ---
with tabs[pos]:
    st.subheader(f"{tr('published_schedule')} — {month_label(year,month)}")
    payload=db.load_schedule(year,month,"current")
    draft_payload=db.load_schedule(year,month,"draft")
    _schedule_draft_health=draft_compatibility_status(draft_payload,year,month) if draft_payload else None
    _schedule_draft_publishable=bool((_schedule_draft_health or {}).get("publishable"))
    # V2.5.119 clock-authoritative lifecycle. No operator button opens/closes phases.
    try:
        if weekend_fcfs_backup_mode(year,month):
            db.sync_schedule_cycle_v25119(year,month)
            lifecycle=db.get_schedule_lifecycle(year,month)
    except Exception:
        pass

    if lifecycle_operator_ui:
        st.markdown("## GRAFIKO TVIRTINIMAS" if lang=="LT" else "## SCHEDULE CONTROL")
        if draft_payload and not payload and not _schedule_draft_publishable:
            render_invalid_draft_guard(_schedule_draft_health)
            st.info(
                "Publikavimo veiksmai lieka užblokuoti, kol GENERUOTI / PERKURTI sukuria naują 0-HARD juodraštį."
                if lang=="LT" else
                "Publication actions remain blocked until GENERATE / REBUILD creates a new zero-HARD draft."
            )
        if is_researcher_account:
            st.info(
                "Kontingencinis valdymas aktyvus Išplėstiniame režime. Veiksmai atliekami ir audituojami kaip ŠR; SP paskyra niekada neperimama."
                if lang=="LT" else
                "Contingency control is active in Advanced mode. Actions are performed and audited as ŠR; the SP account is never impersonated."
            )

        state=str(lifecycle.get("state") or ("working" if payload else "draft"))
        now_lt=_vilnius_now()
        deadline=_parse_iso_dt(lifecycle.get("swap_deadline"))
        deadline_lt=deadline.astimezone(ZoneInfo("Europe/Vilnius")) if deadline else None
        expired=bool(state=="swap_open" and deadline_lt and now_lt>=deadline_lt)
        blockers=db.finalization_blockers_v2591(year,month)
        smtp_ok=True; missing_mail=[]
        prelim_start,prelim_end=preliminary_swap_window_for(year,month)
        render_operator_email_smtp_admin(active_user)
        # Refresh readiness after the operator email/SMTP panel (a successful edit reruns).
        smtp_ok=True; missing_mail=[]

        if state=="final":
            _workflow_card(
                "FINAL — PATEIKTA ADMINISTRACIJAI" if lang=="LT" else "FINAL — SUBMITTED TO ADMINISTRATION",
                "Administracijai skirta versija užrakinta. Įprasti, pavėluoti ir rankiniai prieš-FINAL pakeitimai uždaryti."
                if lang=="LT" else
                "The administration version is locked. Ordinary, late and pre-FINAL manual changes are closed.",
                "final"
            )
            fp=lifecycle.get("final_json")
            if fp:
                fr=refresh_result_payload(fp,year,month,use_actual_backups=True)
                _fc1,_fc2=st.columns(2)
                with _fc1:
                    st.download_button(
                        "ATSISIŲSTI FINAL EXCEL ADMINISTRACIJAI" if lang=="LT" else "DOWNLOAD FINAL EXCEL FOR ADMINISTRATION",
                        build_xlsx(year,month,fr,document_status="FINAL — ADMINISTRACIJAI" if lang=="LT" else "FINAL — FOR ADMINISTRATION",backup_rows_override=lifecycle.get("final_backups") or []),
                        file_name=f"FINAL_grafikas_{year}_{month:02d}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary",use_container_width=True,key=f"final_xlsx_{year}_{month}"
                    )
                with _fc2:
                    st.download_button(
                        "ATSISIŲSTI FINAL CSV" if lang=="LT" else "DOWNLOAD FINAL CSV",
                        schedule_list_df(year,month,fr).to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"FINAL_grafikas_{year}_{month:02d}.csv",
                        mime="text/csv",use_container_width=True,key=f"final_csv_{year}_{month}"
                    )
                if smtp_ready() and st.button("PAKARTOTI TIK NEPAVYKUSIUS FINAL PRANEŠIMUS" if lang=="LT" else "RETRY FAILED FINAL NOTIFICATIONS",use_container_width=True,key=f"resend_final_mail_{year}_{month}"):
                    mailres=retry_failed_lifecycle_notifications(year,month,"final")
                    if mailres: st.dataframe(localized_delivery_rows(mailres),use_container_width=True,hide_index=True)
                    else: st.success("Visi FINAL pranešimai jau pristatyti." if lang=="LT" else "All FINAL notifications are already delivered.")
        else:
            if state=="draft":
                _workflow_card(
                    "JUODRAŠTIS — MATOMAS TIK SENIŪNEI" if lang=="LT" else "SYSTEM DRAFT — PRIVATE",
                    "Sugeneruotas grafikas dar nepaskelbtas rezidentams. Generavimas pats el. laiškų nesiunčia."
                    if lang=="LT" else
                    "The generated grafikas has not been published to residents. Generation itself sends no email.",
                    "draft"
                )
            elif state=="working":
                _workflow_card(
                    "PRELIMINARUS PAGRINDAS UŽFIKSUOTAS — DAR GALIMA KOREGUOTI" if lang=="LT" else "SYSTEM FROZEN — ACTUAL EDITABLE",
                    "SYSTEM išsaugotas tyrimui. SP arba ŠR gali koreguoti ACTUAL iki FINAL; rezidentams preliminarus grafikas dar nebūtinai paskelbtas."
                    if lang=="LT" else
                    "SYSTEM is preserved for research. SP or ŠR may correct ACTUAL until FINAL; the preliminary grafikas does not have to be published to residents.",
                    "draft"
                )
            elif state=="swap_open":
                _workflow_card(
                    ("PRELIMINARUS GRAFIKAS PASKELBTAS — VYKSTA APSIKEITIMAI" if not expired else "APSIKEITIMŲ LAIKOTARPIS BAIGĖSI") if lang=="LT" else ("PRELIMINARY PUBLISHED — SWAPS OPEN" if not expired else "RESIDENT SWAP DEADLINE PASSED"),
                    ((f"Rezidentai gali kurti naujus apsikeitimo prašymus iki {deadline_lt:%Y-%m-%d %H:%M} Lietuvos laiku." if not expired else f"Nuo {deadline_lt:%Y-%m-%d %H:%M} nauji rezidentų prašymai automatiškai blokuojami. Operatorius vis dar gali koreguoti ACTUAL arba suteikti individualią pavėluotą prieigą.") if lang=="LT" else (f"Residents may create new swap requests until {deadline_lt:%Y-%m-%d %H:%M} Lithuania time." if not expired else f"New resident requests are automatically blocked after {deadline_lt:%Y-%m-%d %H:%M}. The operator may still correct ACTUAL or grant individual late access.")),
                    "swap_open" if not expired else "expired"
                )
            elif state=="swap_closed":
                _workflow_card(
                    "REZIDENTŲ APSIKEITIMŲ LAIKOTARPIS BAIGTAS" if lang=="LT" else "RESIDENT SWAPS CLOSED",
                    "Naujų rezidentų prašymų kurti negalima. SP/ŠR rankinis ACTUAL koregavimas lieka aktyvus iki FINAL."
                    if lang=="LT" else
                    "Residents cannot create new requests. SP/ŠR manual ACTUAL correction remains available until FINAL.",
                    "swap_closed"
                )

            # Legacy/manual cycles may freeze SYSTEM directly for operator correction.
            # V2.5.120 automatic FCFS cycles use one explicit PRELIMINARY publication action
            # below, so SP sees a clean two-publication workflow: PRELIMINARY → FINAL.
            if not weekend_fcfs_backup_mode(year,month) and not payload and draft_payload:
                if not _schedule_draft_publishable:
                    st.error("SYSTEM užšaldymas užblokuotas — DB juodraštis nepraeina dabartinio engine 0-HARD patikros." if lang=="LT" else "SYSTEM freeze blocked — the DB draft fails current-engine zero-HARD validation.")
                if st.button(
                    "UŽŠALDYTI SYSTEM IR ATIDARYTI ACTUAL KOREGAVIMĄ (BE EMAIL)" if lang=="LT" else "FREEZE SYSTEM AND OPEN ACTUAL CORRECTION (NO EMAIL)",
                    use_container_width=True,disabled=not _schedule_draft_publishable,key=f"prepare_working_{year}_{month}"
                ):
                    try:
                        published=publish_system_baseline_for_swap_window(year,month)
                        if not published.get("ok"):
                            st.error(str(published.get("error"))); rows=published.get("rows")
                            if rows: st.dataframe(pd.DataFrame(rows if isinstance(rows,list) else [rows]),use_container_width=True,hide_index=True)
                            st.stop()
                        db.ensure_working_schedule_v2592(year,month)
                        st.session_state["_finalization_flash"]=("success","SYSTEM užšaldytas. ACTUAL paruoštas rankiniam koregavimui; email nesiųsti." if lang=="LT" else "SYSTEM frozen. ACTUAL is ready for manual correction; no email was sent.")
                        st.rerun()
                    except Exception as exc: st.error(str(exc))

            # Operator manual correction is permanently available until FINAL.
            if payload:
                render_operator_manual_override(year,month,payload,state)

            # V2.5.93 persistent post-override review checkpoint.
            unreviewed_manual=render_manual_override_review_checkpoint(year,month) if payload else 0

            if weekend_fcfs_backup_mode(year,month):
                st.divider()
                st.markdown("### Mėnesio grafiko eiga" if lang=="LT" else "### AUTOMATIC MONTH CYCLE")
                phase_info=db.scheduler_cycle_phase_v25119(year,month) or {}
                phase=str(phase_info.get("phase") or "")
                p_open=_parse_iso_dt(phase_info.get("preference_open")); p_close=_parse_iso_dt(phase_info.get("preference_close")); s_open=_parse_iso_dt(phase_info.get("swap_open")); s_close=_parse_iso_dt(phase_info.get("swap_close"))
                if p_open: p_open=p_open.astimezone(ZoneInfo("Europe/Vilnius"))
                if p_close: p_close=p_close.astimezone(ZoneInfo("Europe/Vilnius"))
                if s_open: s_open=s_open.astimezone(ZoneInfo("Europe/Vilnius"))
                if s_close: s_close=s_close.astimezone(ZoneInfo("Europe/Vilnius"))
                st.caption(
                    f"Automatinė eiga: pageidavimai iki {p_close:%Y-%m-%d %H:%M}; seniūnės parengimas iki {s_open:%Y-%m-%d %H:%M}; apsikeitimai iki {s_close:%Y-%m-%d %H:%M}."
                    if p_close and s_open and s_close else "Etapai valdomi automatiškai pagal Lietuvos laiką."
                )
                st.info(
                    "Seniūnės eiga: 14 d. 00:00 užsidaro pageidavimai → iki 15 d. 00:00 generuojamas, tikrinamas ir prireikus taisomas preliminarus grafikas → ne vėliau kaip 15 d. 00:00 preliminarus grafikas paskelbiamas rezidentams → 15 d. 00:00–16 d. 00:00 vyksta 24 val. apsikeitimų langas → 16 d. 00:00 rezidentų savitarna užsirakina → seniūnė atlieka galutinę rankinę patikrą, prireikus perkelia paskyrimus ir paspaudžia „Paskelbti galutinį grafiką“."
                )
                if phase=="preferences":
                    _workflow_card(
                        "1 etapas · Pageidavimų teikimas" if lang=="LT" else "PREFERENCES OPEN",
                        "Rezidentai pildo tik grafiko pageidavimus. Dubliai dar neaktyvūs — jie atsirakins paskelbus preliminarų grafiką." if lang=="LT" else "Residents submit schedule preferences only. Backups are still locked and unlock after preliminary publication.",
                        "draft"
                    )
                elif phase=="senior_build":
                    _workflow_card(
                        "2 etapas · Seniūnė rengia preliminarų grafiką",
                        f"Pageidavimai uždaryti. Iki {s_open:%Y-%m-%d %H:%M} galima generuoti grafiką iš naujo, tikrinti problemas ir pasirinkti geriausią variantą. Preliminarus grafikas turi būti paskelbtas iki šio termino.",
                        "draft"
                    )
                    if draft_payload and not payload:
                        if not _schedule_draft_publishable:
                            st.error("PRELIMINARUS PUBLIKAVIMAS UŽBLOKUOTAS — reikia naujo CURRENT-engine 0-HARD juodraščio." if lang=="LT" else "PRELIMINARY PUBLICATION BLOCKED — a new CURRENT-engine zero-HARD draft is required.")
                        if st.button("1/2 — Paskelbti preliminarų grafiką",type="primary",use_container_width=True,disabled=not _schedule_draft_publishable,key=f"publish_preliminary_build_{year}_{month}"):
                            try:
                                _pub=publish_system_baseline_for_swap_window(year,month)
                                if not _pub.get("ok"):
                                    st.error(str(_pub.get("error"))); rows=_pub.get("rows")
                                    if rows: st.dataframe(pd.DataFrame(rows if isinstance(rows,list) else [rows]),use_container_width=True,hide_index=True)
                                    st.stop()
                                db.ensure_working_schedule_v2592(year,month)
                                db.open_swap_window_v2591(year,month,prelim_end.astimezone(timezone.utc).isoformat())
                                st.session_state["_finalization_flash"]=("success","Preliminarus grafikas paskelbtas. Rezidentai jį matys, o naujų apsikeitimų prašymų langas automatiškai atsivers 15 d. 00:00 ir veiks iki 16 d. 00:00.")
                                st.rerun()
                            except Exception as exc: st.error(str(exc))
                elif phase=="swaps":
                    if payload:
                        _workflow_card(
                            "2 etapas · Apsikeitimų laikotarpis" if lang=="LT" else "PRELIMINARY PUBLISHED — SWAPS ACTIVE",
                            f"Rezidentai mato preliminarų grafiką ir gali siūlyti apsikeitimus iki {s_close:%Y-%m-%d %H:%M}. Dublių pasirinkimas lieka atskira viso mėnesio savitarna." if lang=="LT" else f"Residents can see the preliminary schedule and create pre-FINAL swaps until {s_close:%Y-%m-%d %H:%M}. Backup selection remains a separate all-month self-service.",
                            "swap_open"
                        )
                    elif draft_payload:
                        _workflow_card(
                            "3 etapas · Preliminarus grafikas dar nepaskelbtas",
                            "15 d. 00:00 jau prasidėjo apsikeitimų laikas, todėl preliminarų grafiką reikia paskelbti nedelsiant. Kuo vėliau jis paskelbiamas, tuo mažiau iš 24 valandų lieka rezidentams.",
                            "draft"
                        )
                        if not _schedule_draft_publishable:
                            st.error("PRELIMINARUS PUBLIKAVIMAS UŽBLOKUOTAS — DB juodraštis nepraeina dabartinio engine 0-HARD patikros." if lang=="LT" else "PRELIMINARY PUBLICATION BLOCKED — the DB draft fails current-engine zero-HARD validation.")
                        if st.button("1/2 — Paskelbti preliminarų grafiką" if lang=="LT" else "PUBLISH PRELIMINARY AND OPEN RESIDENT SWAPS",type="primary",use_container_width=True,disabled=not _schedule_draft_publishable,key=f"publish_preliminary_{year}_{month}"):
                            try:
                                _pub=publish_system_baseline_for_swap_window(year,month)
                                if not _pub.get("ok"):
                                    st.error(str(_pub.get("error")))
                                    rows=_pub.get("rows")
                                    if rows: st.dataframe(pd.DataFrame(rows if isinstance(rows,list) else [rows]),use_container_width=True,hide_index=True)
                                    st.stop()
                                db.ensure_working_schedule_v2592(year,month)
                                db.sync_schedule_cycle_v25119(year,month)
                                db.open_swap_window_v2591(year,month,prelim_end.astimezone(timezone.utc).isoformat())
                                st.session_state["_finalization_flash"]=("success","Preliminarus grafikas paskelbtas. Rezidentų apsikeitimai aktyvūs iki 16 d. 00:00. Pradinis grafikas užfiksuotas, o seniūnė iki galutinio patvirtinimo gali atlikti rankines korekcijas.")
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))
                    else:
                        st.warning("Apsikeitimų laikotarpio laikas jau skaičiuojamas, tačiau galiojantis preliminarus grafikas dar nepaskelbtas. Seniūnė gali generuoti juodraštį iš naujo tiek kartų, kiek reikia; paskelbimas yra atskiras veiksmas." if lang=="LT" else "The swap clock is running, but no valid draft exists yet. The senior may GENERATE / REBUILD as many times as needed; publication is a separate action.")
                else:
                    try:
                        fill=db.auto_fill_weekend_backups_v25119(year,month)
                    except Exception as exc:
                        fill={"ok":False,"error":str(exc)}
                    # V2.5.120: time closes resident self-service automatically, but it never
                    # silently publishes a draft. If PRELIMINARY was skipped, SP/ŠR may still
                    # choose/freeze the desired draft during senior review before FINAL.
                    if payload:
                        try:
                            _rr=refresh_result_payload(db.load_schedule(year,month,"current"),year,month,use_actual_backups=False)
                            sync_backup_plan(year,month,_rr)
                        except Exception:
                            pass
                    if not payload and draft_payload:
                        st.warning("Preliminarus grafikas nebuvo paskelbtas iki apsikeitimų laikotarpio pabaigos. Rezidentų savitarna jau uždaryta, tačiau seniūnė gali pasirinkti norimą juodraštį galutinei peržiūrai. Tai apsikeitimų laikotarpio iš naujo neatidaro." if lang=="LT" else "PRELIMINARY was not published before the swap window ended. Resident self-service is already closed, but the senior may freeze the chosen SYSTEM as the ACTUAL review version; this does not reopen resident swaps.")
                        if not _schedule_draft_publishable:
                            st.error("Šio juodraščio užšaldyti seniūnės peržiūrai negalima — pirmiausia reikia naujo CURRENT-engine 0-HARD juodraščio." if lang=="LT" else "This draft cannot be frozen for senior review — first generate a new CURRENT-engine zero-HARD draft.")
                        if st.button("Paruošti pasirinktą juodraštį seniūnės peržiūrai" if lang=="LT" else "FREEZE CHOSEN SYSTEM FOR SENIOR REVIEW",use_container_width=True,disabled=not _schedule_draft_publishable,key=f"freeze_for_review_{year}_{month}"):
                            try:
                                _pub=publish_system_baseline_for_swap_window(year,month)
                                if not _pub.get("ok"):
                                    st.error(str(_pub.get("error")))
                                    rows=_pub.get("rows")
                                    if rows: st.dataframe(pd.DataFrame(rows if isinstance(rows,list) else [rows]),use_container_width=True,hide_index=True)
                                    st.stop()
                                db.ensure_working_schedule_v2592(year,month)
                                db.sync_schedule_cycle_v25119(year,month)
                                st.session_state["_finalization_flash"]=("success","Pasirinktas juodraštis paruoštas seniūnės galutinei peržiūrai. Rezidentų apsikeitimai lieka uždaryti." if lang=="LT" else "SYSTEM frozen for senior FINAL review. The resident swap window remains closed.")
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))
                    claims_now=db.list_backup_claims(year,month)
                    auto_n=sum(1 for r in claims_now if str(r.get("source") or "")=="auto_random")
                    fcfs_n=sum(1 for r in claims_now if str(r.get("source") or "") in ("self_fcfs","self"))
                    q1,q2,q3=st.columns(3)
                    q1.metric("Dubliai" if lang=="LT" else "Backups",f"{len(claims_now)}/16")
                    q2.metric("Pasirinkti savarankiškai" if lang=="LT" else "Self-selected",fcfs_n)
                    q3.metric("Paskirstyti automatiškai" if lang=="LT" else "AUTO random",auto_n)
                    _workflow_card(
                        "3 etapas · Seniūnės galutinė peržiūra" if lang=="LT" else "RESIDENT WINDOWS CLOSED — SENIOR REVIEW",
                        "Nuo 16 d. 00:00 uždaromi nauji grafiko pageidavimai ir apsikeitimai. Dubliai yra atskiras po-publikacinis standby sluoksnis ir lieka valdomi Dubliai lange; aktyvuoto ar atlikto dublio tyliai perkelti negalima." if lang=="LT" else "From day 16 00:00 new schedule preferences and swaps close. Backups remain a separate post-publication standby layer in the Backups tab; an activated or completed backup cannot be silently moved.",
                        "swap_closed"
                    )
            else:
                st.divider()
                st.markdown("### Preliminarus paskelbimas ir rezidentų apsikeitimai" if lang=="LT" else "### Preliminary publication and resident swaps")
                st.caption(
                    (f"Standartinis langas: {prelim_start:%Y-%m-%d %H:%M} → {prelim_end:%Y-%m-%d %H:%M} Lietuvos laiku. Pageidavimai renkami iki {prelim_start:%Y-%m-%d} 00:00 (ankstesnė diena imtinai)."
                     if lang=="LT" else
                     f"Standard window: {prelim_start:%Y-%m-%d %H:%M} → {prelim_end:%Y-%m-%d %H:%M} Lithuania time. Preferences are collected until 00:00 on {prelim_start:%Y-%m-%d} (the preceding day is the last full day).")
                )
                if not smtp_ok:
                    st.error("SMTP nesukonfigūruotas — preliminaraus ar FINAL etapo aktyvuoti negalima, nes nebūtų realių pranešimų." if lang=="LT" else "SMTP is not configured — preliminary or FINAL activation is blocked because real notifications could not be sent.")
                if missing_mail:
                    st.error(("Trūksta rezidentų el. pašto adresų: " if lang=="LT" else "Missing resident email addresses: ")+", ".join(missing_mail))

                if state in ("draft","working"):
                    within_prelim=bool(prelim_start<=now_lt<prelim_end)
                    if now_lt<prelim_start:
                        st.info((f"Preliminarų etapą bus galima aktyvuoti nuo {prelim_start:%Y-%m-%d %H:%M}." if lang=="LT" else f"The preliminary phase can be activated from {prelim_start:%Y-%m-%d %H:%M}."))
                    elif now_lt>=prelim_end:
                        st.warning((f"Standartinis apsikeitimų langas šiam mėnesiui jau pasibaigė ({prelim_end:%Y-%m-%d %H:%M}). Galite pereiti tiesiai į FINAL." if lang=="LT" else f"The standard swap window for this month has already ended ({prelim_end:%Y-%m-%d %H:%M}). You may proceed directly to FINAL."))
                    can_prelim=bool((payload or (draft_payload and _schedule_draft_publishable)) and smtp_ok and not missing_mail and within_prelim and int(unreviewed_manual)==0)
                    if unreviewed_manual:
                        st.warning("Preliminarus etapas užblokuotas, kol peržiūrėsite rankinius pakeitimus." if lang=="LT" else "Preliminary publication is blocked until manual changes are reviewed.")
                    if st.button(
                        "PASKELBTI PRELIMINARŲ GRAFIKĄ IR LEISTI APSIKEITIMUS" if lang=="LT" else "PUBLISH PRELIMINARY SCHEDULE AND OPEN SWAPS",
                        type="primary",use_container_width=True,disabled=not can_prelim,key=f"open_prelim_{year}_{month}"
                    ):
                        try:
                            if not payload:
                                published=publish_system_baseline_for_swap_window(year,month)
                                if not published.get("ok"):
                                    st.error(str(published.get("error"))); rows=published.get("rows")
                                    if rows: st.dataframe(pd.DataFrame(rows if isinstance(rows,list) else [rows]),use_container_width=True,hide_index=True)
                                    st.stop()
                                result_open=published["result"]
                            else:
                                result_open=refresh_result_payload(payload,year,month)
                            db.ensure_working_schedule_v2592(year,month)
                            db.open_swap_window_v2591(year,month,prelim_end.astimezone(timezone.utc).isoformat())
                            mailres=swap_window_open_emails(year,month,result_open,prelim_end,max(1,(prelim_end.date()-now_lt.date()).days))
                            failed=[x for x in mailres if x[1]!="sent"]
                            st.session_state["_finalization_flash"]=("warning" if failed else "success",(f"Preliminarus grafikas paskelbtas. Pranešimai: {len(mailres)-len(failed)}/{len(mailres)} išsiųsta." if lang=="LT" else f"Preliminary grafikas published. Notifications: {len(mailres)-len(failed)}/{len(mailres)} sent."))
                            st.rerun()
                        except Exception as exc: st.error(str(exc))
                elif state=="swap_open":
                    m1,m2,m3,m4=st.columns(4)
                    m1.metric("Laukia",blockers.get("pending_normal",0)); m2.metric("Laukia seniūnės",blockers.get("waiting_senior_apply",0)); m3.metric("Laukia dublio",blockers.get("pending_backup",0)); m4.metric("Papildoma prieiga",blockers.get("active_late_grants",0))
                    if smtp_ready() and deadline_lt and st.button("PAKARTOTI TIK NEPAVYKUSIUS PRELIMINARIUS PRANEŠIMUS" if lang=="LT" else "RETRY FAILED PRELIMINARY NOTIFICATIONS",use_container_width=True,key=f"resend_prelim_{year}_{month}"):
                        mailres=retry_failed_lifecycle_notifications(year,month,"swap_open")
                        if mailres: st.dataframe(localized_delivery_rows(mailres),use_container_width=True,hide_index=True)
                        else: st.success("Visi preliminarūs pranešimai jau pristatyti." if lang=="LT" else "All preliminary notifications are already delivered.")
                    if not expired:
                        with st.expander("Uždaryti rezidentų apsikeitimus anksčiau" if lang=="LT" else "Close resident swaps early",expanded=False):
                            if st.button("UŽDARYTI DABAR" if lang=="LT" else "CLOSE NOW",use_container_width=True,key=f"close_swaps_{year}_{month}"):
                                try: db.close_swap_window_v2591(year,month); st.rerun()
                                except Exception as exc: st.error(str(exc))

                # Late access is an exception after the ordinary deadline / explicit close.
                if (state=="swap_open" and expired) or state=="swap_closed":
                    st.markdown("#### Individuali pavėluota prieiga" if lang=="LT" else "#### Individual late access")
                    settings_all=db.all_account_settings(); options=[pp["initials"] for pp in DEFAULT_PEOPLE]
                    l1,l2,l3=st.columns(3)
                    with l1: late_ini=st.selectbox("Rezidentas" if lang=="LT" else "Resident",options,key=f"late_ini_{year}_{month}")
                    with l2: late_hours=int(st.number_input("Galioja valandų" if lang=="LT" else "Valid hours",min_value=1,max_value=168,value=24,step=1,key=f"late_hours_{year}_{month}"))
                    with l3: late_limit=int(st.number_input("Naujų prašymų limitas" if lang=="LT" else "New-request limit",min_value=1,max_value=5,value=1,step=1,key=f"late_limit_{year}_{month}"))
                    late_reason=st.text_input("Priežastis (auditui)" if lang=="LT" else "Reason (audit)",key=f"late_reason_{year}_{month}")
                    late_email=str((settings_all.get(late_ini,{}) or {}).get("email") or "").strip()
                    if not late_email: st.warning((f"{late_ini} neturi email nustatymuose." if lang=="LT" else f"{late_ini} has no email in settings."))
                    if st.button("SUTEIKTI INDIVIDUALIĄ PRIEIGĄ" if lang=="LT" else "GRANT INDIVIDUAL ACCESS",use_container_width=True,disabled=(not smtp_ready() or not late_email or not late_reason.strip()),key=f"grant_late_{year}_{month}"):
                        try:
                            exp=_vilnius_now()+timedelta(hours=late_hours); grant=db.grant_late_swap_access_v2591(year,month,late_ini,exp.astimezone(timezone.utc).isoformat(),late_limit,late_reason); ok,detail=late_swap_access_email(year,month,grant); st.session_state["_finalization_flash"]=("success" if ok else "warning",("Prieiga suteikta ir pranešimas išsiųstas." if ok and lang=="LT" else "Access granted and notification sent." if ok else f"Prieiga suteikta, bet email nepavyko: {detail}")); st.rerun()
                        except Exception as exc: st.error(str(exc))
                    grants=db.list_late_swap_access_v2591(year,month)
                    for gr in grants:
                        exp=_parse_iso_dt(gr.get("expires_at")); active=bool(not gr.get("revoked_at") and exp and exp>datetime.now(timezone.utc) and int(gr.get("requests_used",0))<int(gr.get("max_requests",0)))
                        if not active: continue
                        exp_txt=exp.astimezone(ZoneInfo("Europe/Vilnius")).strftime("%Y-%m-%d %H:%M")
                        with st.container(border=True):
                            st.markdown(f"**{gr.get('initials')}** · iki {exp_txt} · {gr.get('requests_used',0)}/{gr.get('max_requests',1)}")
                            if gr.get("reason"): st.caption(str(gr.get("reason")))
                            if st.button("ATŠAUKTI PRIEIGĄ" if lang=="LT" else "REVOKE ACCESS",key=f"revoke_late_{gr.get('id')}"):
                                try: db.revoke_late_swap_access_v2591(int(gr["id"])); st.rerun()
                                except Exception as exc: st.error(str(exc))

            # FINAL is always an explicit option; the preliminary phase may be skipped.
            st.divider()
            st.markdown("### Galutinio grafiko patvirtinimas" if lang=="LT" else "### Final confirmation")
            candidate_payload=payload or draft_payload
            _candidate_source_valid=bool(payload or (draft_payload and _schedule_draft_publishable))
            candidate_result=refresh_result_payload(candidate_payload,year,month,use_actual_backups=bool(payload)) if candidate_payload else None
            if draft_payload and not payload and not _schedule_draft_publishable:
                st.error("FINAL blokuotas: vienintelis kandidatas yra negaliojantis / pasenęs DB juodraštis. Pirmiausia GENERUOTI / PERKURTI naują 0-HARD versiją." if lang=="LT" else "FINAL blocked: the only candidate is an invalid/outdated DB draft. GENERATE / REBUILD a new zero-HARD version first.")
            if candidate_result is not None:
                candidate_is_actual=bool(payload)
                render_schedule_download_buttons(
                    year,month,candidate_result,
                    status_label=(("ACTUAL — PRIEŠ FINAL" if lang=="LT" else "ACTUAL — BEFORE FINAL") if candidate_is_actual else ("SYSTEM JUODRAŠTIS — PRIEŠ TVIRTINIMĄ" if lang=="LT" else "SYSTEM DRAFT — BEFORE CONFIRMATION")),
                    file_prefix=("ACTUAL_pries_FINAL" if candidate_is_actual else "SYSTEM_juodrastis_pries_tvirtinima"),
                    key_prefix="finalization_candidate_export",
                )
            hard=int(((candidate_result.stats or {}).get("global",{}) if candidate_result else {}).get("hard_errors",999))
            blockers=db.finalization_blockers_v2591(year,month)
            unresolved=(int(blockers.get("pending_normal",0))+int(blockers.get("waiting_senior_apply",0))+int(blockers.get("pending_backup",0))+int(blockers.get("active_late_grants",0))+int(blockers.get("unreviewed_manual_overrides",0)))
            if hard!=0 or unresolved:
                st.error((f"FINAL blokuotas: HARD={hard}; pending={blockers.get('pending_normal',0)}; waiting operator={blockers.get('waiting_senior_apply',0)}; pending backup={blockers.get('pending_backup',0)}; active late={blockers.get('active_late_grants',0)}; neperžiūrėti rankiniai={blockers.get('unreviewed_manual_overrides',0)}." if lang=="LT" else f"FINAL blocked: HARD={hard}; pending={blockers.get('pending_normal',0)}; waiting operator={blockers.get('waiting_senior_apply',0)}; pending backup={blockers.get('pending_backup',0)}; active late={blockers.get('active_late_grants',0)}; unreviewed manual={blockers.get('unreviewed_manual_overrides',0)}."))
            if state=="swap_open" and not expired:
                st.warning("Galutinio grafiko patvirtinimas dabar iš karto uždarytų dar aktyvų rezidentų apsikeitimų laikotarpį." if lang=="LT" else "Confirming FINAL now will immediately close the still-active resident swap window.")
            confirm=st.checkbox("Patvirtinu, kad dabartinis grafikas yra galutinė administracijai teikiama versija." if lang=="LT" else "I confirm that the current ACTUAL grafikas is the final version for administration.",key=f"final_confirm_{year}_{month}")
            _fcfs_cycle=weekend_fcfs_backup_mode(year,month)
            _cycle_phase=(db.scheduler_cycle_phase_v25119(year,month) or {}).get("phase") if _fcfs_cycle else None
            if _fcfs_cycle and _cycle_phase!="senior_review":
                st.info("Galutinio patvirtinimo mygtukas atsirakins automatiškai pasibaigus rezidentų apsikeitimų laikui (16 d. 00:00 Lietuvos laiku). Seniūnės rankinės korekcijos visą laiką lieka aktyvios." if lang=="LT" else "FINAL unlocks automatically after the resident swap window ends (day 16 at 00:00 Lithuania time). Senior manual corrections remain available in the meantime once PRELIMINARY is published.")
            _notification_gate=(True if _fcfs_cycle else (smtp_ok and not missing_mail))
            final_ready=bool(candidate_payload and _candidate_source_valid and hard==0 and unresolved==0 and _notification_gate and confirm and (not _fcfs_cycle or _cycle_phase=="senior_review"))
            if st.button("2/2 — Patvirtinti galutinį grafiką" if lang=="LT" else "CONFIRM FINAL, SUBMIT AND PREPARE EXCEL",type="primary",use_container_width=True,disabled=not final_ready,key=f"make_final_{year}_{month}"):
                try:
                    if not payload:
                        published=publish_system_baseline_for_swap_window(year,month)
                        if not published.get("ok"):
                            st.error(str(published.get("error"))); rows=published.get("rows")
                            if rows: st.dataframe(pd.DataFrame(rows if isinstance(rows,list) else [rows]),use_container_width=True,hide_index=True)
                            st.stop()
                    db.ensure_working_schedule_v2592(year,month)
                    payload_now=db.load_schedule(year,month,"current")
                    rr=refresh_result_payload(payload_now,year,month)
                    hard_now=int((rr.stats or {}).get("global",{}).get("hard_errors",999))
                    if hard_now!=0:
                        st.error(f"FINAL validacija nepraėjo: HARD={hard_now}"); st.stop()
                    db.finalize_schedule_v2592(year,month,serialize_result(rr))
                    # V2.5.136: reserved reward credits become consumed only when FINAL is locked.
                    # If this bookkeeping call ever fails, the reservation still remains unavailable
                    # for double-spending and can be reconciled safely later.
                    try:
                        db.consume_reward_credit_redemptions_v25136(year,month)
                    except Exception:
                        pass
                    if weekend_fcfs_backup_mode(year,month):
                        st.session_state["_finalization_flash"]=("success","Galutinis grafikas patvirtintas ir paruoštas administracijai. Rezidentų savitarna lieka uždaryta; vėlesni realaus darbo pasikeitimai registruojami atskirame faktiniame grafike." if lang=="LT" else "FINAL locked and prepared for administration. Resident self-service remains closed; post-FINAL operational changes belong to the separate ACTUAL layer.")
                    else:
                        mails=final_schedule_emails(year,month,rr); failed=[x for x in mails if x[1]!="sent"]
                        st.session_state["_finalization_flash"]=("warning" if failed else "success",(f"FINAL užrakintas ir paruoštas administracijai. Pranešimai: {len(mails)-len(failed)}/{len(mails)} išsiųsta." if lang=="LT" else f"FINAL locked and prepared for administration. Notifications: {len(mails)-len(failed)}/{len(mails)} sent."))
                    st.rerun()
                except Exception as exc: st.error(str(exc))

        flash=st.session_state.pop("_finalization_flash",None)
        if flash:
            level,msg=flash
            if level=="success": st.success(msg)
            else: st.warning(msg)
        st.divider()

    if not payload:
        if draft_payload and not lifecycle_operator_ui: st.info(tr("not_published"))
        elif not draft_payload: st.info(tr("not_published"))
    else:
        state=str(lifecycle.get("state") or "")
        display_payload=(lifecycle.get("final_json") if state=="final" and lifecycle.get("final_json") else payload)
        result=refresh_result_payload(display_payload,year,month,use_actual_backups=(state!="final"))
        _status_rows=[]
        if lifecycle_operator_ui:
            try: _status_rows=db.list_schedule_day_statuses_v2597(year,month)
            except Exception: _status_rows=[]
        st.markdown(f"### {tr('colors')}")
        st.markdown("".join(badge(p["initials"],False) for p in DEFAULT_PEOPLE),unsafe_allow_html=True)
        st.dataframe(style_schedule(schedule_grid(year,month,result,status_rows=_status_rows if lifecycle_operator_ui else None)),use_container_width=True,height=720)
        if state=="final": st.success("Rodomas administracijai patvirtintas galutinis grafikas." if lang=="LT" else "Showing the administration-locked FINAL snapshot.")

        if state!="final":
            st.caption("Tai dabartinis ACTUAL grafikas. Administracijai skirtas FINAL Excel atsiras tik po galutinio operatoriaus patvirtinimo." if lang=="LT" else "This is the current ACTUAL schedule. The administration FINAL Excel appears only after final operator confirmation.")
            render_schedule_download_buttons(
                year,month,result,
                status_label="ACTUAL",
                file_prefix="ACTUAL_grafikas",
                key_prefix="actual_schedule_export",
            )
pos+=1

# --- Summary ---
if advanced_mode:
    with tabs[pos]:
        st.subheader(tr("summary_title"))
        currentp=db.load_schedule(year,month,"current")
        basep=db.load_schedule(year,month,"baseline")
        draftp=db.load_schedule(year,month,"draft")
        # A published row keeps draft_json. Treat it as a pending candidate only
        # when it differs from the frozen publication baseline. This lets a senior
        # generate a new candidate while an older grafikas is still published and
        # inspect the NEW draft before replacing the operational baseline.
        pending_draft=bool(draftp and (not basep or draftp!=basep))
        draft_mode=bool(draftp and (not currentp or pending_draft))

        if draft_mode:
            base=refresh_result_payload(draftp,year,month,use_actual_backups=False)
            current=base
            g=base.stats["global"]
            system_live=live_fairness_snapshot(year,month,base,include_completed_covers=False)
            actual_live=None
            st.warning(
                "JUODRAŠČIO SUVESTINĖ — DAR NEPASKELBTA. Visi žemiau esantys rodikliai priklauso naujausiam sugeneruotam kandidatui; PASKELBTAS GRAFIKAS dar nepakeistas."
                if lang=="LT" else
                "DRAFT SUMMARY — NOT PUBLISHED. All metrics below belong to the newest generated candidate; the PUBLISHED grafikas has not been replaced yet."
            )
        elif currentp:
            current=refresh_result_payload(currentp,year,month)
            base=refresh_result_payload(basep or currentp,year,month,use_actual_backups=False)
            g=base.stats["global"]
            system_live=live_fairness_snapshot(year,month,base,include_completed_covers=False)
            actual_live=live_fairness_snapshot(year,month,current,include_completed_covers=True)
            st.success("SYSTEM + ACTUAL SUVESTINĖ — PASKELBTA" if lang=="LT" else "SYSTEM + ACTUAL SUMMARY — PUBLISHED")
        else:
            st.info(
                "Dar nėra nei sugeneruoto juodraščio, nei paskelbto grafiko. Pirmiausia Sudarymas lange paspausk GENERUOTI."
                if lang=="LT" else
                "There is no generated draft or published grafikas yet. First press GENERATE in the Generation tab."
            )
            base=None; current=None; g=None; system_live=None; actual_live=None

        if base is not None:
            if active_user in (SENIOR_INITIALS,WESTON_CREDITOR_INITIALS):
                try:
                    _weston_personal=db.weston_beer_stats_v25110(year,month)
                    st.markdown("### WESTON beer ledger")
                    _wb1,_wb2=st.columns(2)
                    if active_user==SENIOR_INITIALS:
                        _wb1.metric(("Tavo WESTON skola ŠR" if lang=="LT" else "Your WESTON debt to ŠR"),int(_weston_personal.get("total_beers",0)))
                        _wb2.metric(("Šio mėnesio skola" if lang=="LT" else "Debt this month"),int(_weston_personal.get("month_beers",0)))
                        st.caption("1 GENERUOTI / PERKURTI paspaudimas = +1 WESTON, kurį esi skolinga ŠR. Rosita, matematikos neapgausi." if lang=="LT" else "1 GENERATE / REGENERATE click = +1 WESTON you owe ŠR. Rosita, mathematics keeps receipts.")
                    else:
                        _wb1.metric(("SP tau skolinga WESTON" if lang=="LT" else "WESTONs SP owes you"),int(_weston_personal.get("total_beers",0)))
                        _wb2.metric(("Šį mėnesį uždirbai" if lang=="LT" else "Earned this month"),int(_weston_personal.get("month_beers",0)))
                        st.caption("Kiekvienas SP GENERUOTI / PERKURTI paspaudimas = +1 WESTON tau. Skola ir tavo laimėjimas skaičiuojami iš to paties nekintamo ledgerio." if lang=="LT" else "Every SP GENERATE / REGENERATE click = +1 WESTON owed to you. Her debt and your gain are the same persistent ledger.")
                except Exception:
                    pass
            if advanced_mode:
                if draft_mode:
                    c1,c2,c3,c4=st.columns(4)
                    c1.metric(tr("hard_errors")+" *",g["hard_errors"])
                    c2.metric(("JUODRAŠČIO fairness" if lang=="LT" else "DRAFT fairness"),f"{system_live['global'].get('monthly_fairness_score',0)}%")
                    c3.metric(("Postų disbalansas" if lang=="LT" else "Post imbalance"),system_live["global"].get("rotation_monthly_imbalance",0))
                    c4.metric(tr("preference_avg"),tr("not_applicable") if g["mean_preference_score"] is None else f"{g['mean_preference_score']}%")
                else:
                    sg=system_live["global"]; ag=actual_live["global"]
                    c1,c2,c3,c4,c5,c6=st.columns(6)
                    c1.metric(tr("hard_errors")+" *",g["hard_errors"])
                    c2.metric("Pradinio grafiko balansas",f"{sg.get('monthly_fairness_score',0)}%")
                    c3.metric("Faktinio grafiko balansas",f"{ag.get('monthly_fairness_score',0)}%",delta=f"{ag.get('monthly_fairness_score',0)-sg.get('monthly_fairness_score',0):+.1f}")
                    c4.metric(("SYSTEM postų disbalansas" if lang=="LT" else "SYSTEM post imbalance"),sg.get("rotation_monthly_imbalance",0))
                    c5.metric(("ACTUAL postų disbalansas" if lang=="LT" else "ACTUAL post imbalance"),ag.get("rotation_monthly_imbalance",0))
                    c6.metric(("Realiai pavadavo" if lang=="LT" else "Completed covers"),ag.get("completed_cover_transfers",0))
                if draft_mode:
                    st.caption(
                        "JUODRAŠTIS: fairness, postų spread ir pageidavimų score yra pre-publication auditui. Jie taps SYSTEM baseline tik paspaudus PASKELBTI / PATVIRTINTI."
                        if lang=="LT" else
                        "DRAFT: fairness, workplace spread and request scores are pre-publication audit metrics. They become the SYSTEM baseline only after PUBLISH / CONFIRM."
                    )
                else:
                    st.caption(tr("fairness_frozen_note"))
            else:
                s1,s2,s3=st.columns(3)
                s1.metric(("Grafikas" if lang=="LT" else "Schedule"),("VALIDUS" if g["hard_errors"]==0 else "REIKIA PATIKROS"))
                s2.metric(("Pageidavimai" if lang=="LT" else "Preferences"),tr("not_applicable") if g["mean_preference_score"] is None else f"{g['mean_preference_score']}%")
                s3.metric(("Mėnesio fairness" if lang=="LT" else "Monthly fairness"),f"{g.get('monthly_fairness_score',g['fairness_score'])}%")
                st.caption(
                    ("Techninius spread, cumulative ir guardrail rodiklius rasi Išplėstiniame režime."
                     if lang=="LT" else
                     "Technical spread, cumulative and guardrail metrics are available in Advanced mode.")
                )

            render_resident_wishes_audit(
                base,
                draft_mode=draft_mode,
                key_suffix=f"{year}_{month}_{'draft' if draft_mode else 'system'}",
                senior_view=bool(senior_mode),
            )
            st.divider()

            st.markdown(
                ("### JUODRAŠČIO postų pasiskirstymas per mėnesį" if draft_mode else "### SYSTEM postų pasiskirstymas per mėnesį")
                if lang=="LT" else
                ("### DRAFT monthly workplace distribution" if draft_mode else "### SYSTEM monthly workplace distribution")
            )
            st.caption(
                (
                    "Tai naujausio JUODRAŠČIO postų matrica. Ji leidžia prieš publikavimą patikrinti structural water-fill, SPS/Onko ir diversity. Regeneravus ji gali pasikeisti; fairness_history dar neįrašoma."
                    if draft_mode else
                    "SYSTEM matrica yra publikavimo momento algoritmo water-fill baseline. Ji lieka užšaldyta auditui; realus pasiskirstymas rodomas ACTUAL matricoje žemiau."
                )
                if lang=="LT" else
                (
                    "This is the newest DRAFT workplace matrix. It can be audited for structural water-fill, SPS/Onko and diversity before publication. Regeneration may change it; fairness_history is not written yet."
                    if draft_mode else
                    "The SYSTEM matrix is the publication-time algorithmic water-fill baseline. It stays frozen for audit; the real distribution is shown in the ACTUAL matrix below."
                )
            )
            st.dataframe(
                style_rows(workplace_exposure_df(year,month,base)),
                use_container_width=True,
                hide_index=True,
                height=650,
            )

            if not draft_mode:
                st.markdown("### ACTUAL realus postų pasiskirstymas" if lang=="LT" else "### ACTUAL real-work workplace distribution")
                st.caption(
                    "Tai gyva fairness statistika: manual override'ai, swapai ir repair keičia ACTUAL iškart; backup cover perskiriamas dubliui tik pažymėjus COMPLETED. Šie skirtumai niekada nekuria kito mėnesio catch-up."
                    if lang=="LT" else
                    "This is the live fairness ledger: manual overrides, swaps and repairs change ACTUAL immediately; backup exposure transfers only when cover is marked COMPLETED. These differences never create next-month catch-up."
                )
                st.dataframe(style_rows(actual_workplace_exposure_df(year,month,current)),use_container_width=True,hide_index=True,height=650)

            if advanced_mode:
                spread_rows=[]
                sys_spreads=(system_live.get("global",{}).get("rotation_monthly_spreads") or {})
                act_spreads=((actual_live or system_live).get("global",{}).get("rotation_monthly_spreads") or {})
                for cat in display_rotation_categories(year,month):
                    spread_rows.append({
                        ("Postas" if lang=="LT" else "Workplace"):cat,
                        "SYSTEM spread":sys_spreads.get(cat,0),
                        "ACTUAL spread":act_spreads.get(cat,0),
                        ("Pokytis" if lang=="LT" else "Delta"):int(act_spreads.get(cat,0))-int(sys_spreads.get(cat,0)),
                    })
                st.markdown("#### SYSTEM → ACTUAL postų spread" if lang=="LT" else "#### SYSTEM → ACTUAL workplace spread")
                st.caption(
                    "SYSTEM yra mėnesio water-fill baseline. ACTUAL gali nukrypti po leidžiamų pakeitimų; nukrypimas rodomas, bet kitą mėnesį nekompensuojamas."
                    if lang=="LT" else
                    "SYSTEM is the monthly water-fill baseline. ACTUAL may diverge after allowed changes; the divergence is shown but never compensated next month."
                )
                st.dataframe(pd.DataFrame(spread_rows),use_container_width=True,hide_index=True)

                guardrails=(g.get("fairness_guardrails") or {})
                if guardrails:
                    gr_rows=[]
                    for key,val in guardrails.items():
                        gr_rows.append({
                            ("Guardrail" if lang=="LT" else "Guardrail"):key,
                            ("Fairness baseline spread" if lang=="LT" else "Fairness baseline spread"):val.get("baseline_spread"),
                            ("Leistinas pablogėjimas" if lang=="LT" else "Allowed degradation"):val.get("tolerance"),
                            ("Maksimalus spread po SOFT" if lang=="LT" else "Max spread after SOFT"):val.get("ceiling"),
                        })
                    st.markdown("#### Fairness guardrails")
                    st.dataframe(pd.DataFrame(gr_rows),use_container_width=True,hide_index=True)
                    st.caption(
                        ("Šios ribos realiai įdėtos į solverio modelį prieš TRUE SOFT optimizavimą."
                         if lang=="LT" else
                         "These limits are real solver constraints added before TRUE SOFT optimization.")
                    )

                with st.expander(
                    ("Juodraščio krūvio rodikliai" if draft_mode else "Pradinio grafiko krūvio rodikliai")
                    if lang=="LT" else
                    ("DRAFT workload metrics" if draft_mode else "SYSTEM fairness workload metrics"),
                    expanded=False,
                ):
                    st.caption(
                        ("Šie skaičiai priklauso dabartiniam juodraščiui ir skirti auditui prieš publikavimą." if draft_mode else "Šie skaičiai priklauso publikavimo SYSTEM bazei; post-publication ACTUAL pakeitimai jų nekeičia, nes tai yra būtent SYSTEM publikavimo baseline.")
                        if lang=="LT" else
                        ("These figures belong to the current draft and are for pre-publication audit." if draft_mode else "These figures belong to the publication SYSTEM baseline; post-publication ACTUAL changes do not change them because these figures are the publication-time SYSTEM baseline.")
                    )
                    _summary_stats=summary_df(base,year,month)
                    if draft_mode:
                        # Backup obligations are finalized at publish time; hide DB-backed
                        # backup columns here so an older published month's backup rows
                        # cannot be mistaken for draft data.
                        _drop=[tr("planned_backups"),tr("effective_backups")]
                        _summary_stats=_summary_stats.drop(columns=[c for c in _drop if c in _summary_stats.columns],errors="ignore")
                    st.dataframe(style_rows(_summary_stats),use_container_width=True,hide_index=True)
                if (not draft_mode) and current.assignments != base.assignments:
                    with st.expander("FAKTINIAI operaciniai krūvio rodikliai (NE fairness)" if lang=="LT" else "ACTUAL operational workload metrics (NOT fairness)", expanded=False):
                        st.dataframe(style_rows(summary_df(current,year,month)),use_container_width=True,hide_index=True)
            else:
                with st.expander(("Rodyti paprastą mėnesio krūvio santrauką" if lang=="LT" else "Show simple monthly workload summary"), expanded=False):
                    simple_df=summary_df(base,year,month)
                    keep=[c for c in simple_df.columns if c in ["Žmogus","Vardas","Pamainos","Tikslas","Person","Name","Assignments","Target"]]
                    st.dataframe(simple_df[keep] if keep else simple_df,use_container_width=True,hide_index=True)
            if draft_mode:
                st.info(
                    "Jei šita Suvestinė netenkina: grįžk į Sudarymas → PERTIKRINTI / GERINTI arba GENERUOTI iš naujo. PASKELBTAS GRAFIKAS nepasikeis, kol aiškiai nepaspausi PASKELBTI / PATVIRTINTI."
                    if lang=="LT" else
                    "If this Summary is not satisfactory: return to Generation → IMPROVE / RECHECK or GENERATE again. The PUBLISHED grafikas does not change until you explicitly press PUBLISH / CONFIRM."
                )
    pos+=1

# --- Transparency ---
if advanced_mode:
    with tabs[pos]:
        st.subheader(tr("transparency_title")); currentp=db.load_schedule(year,month,"current"); basep=db.load_schedule(year,month,"baseline")
        if not currentp: st.info(tr("not_published"))
        else:
            current=refresh_result_payload(currentp,year,month); base=refresh_result_payload(basep or currentp,year,month,use_actual_backups=False)
            g=base.stats["global"]; gb=base.stats["global"]
            system_live=live_fairness_snapshot(year,month,base,include_completed_covers=False)
            actual_live=live_fairness_snapshot(year,month,current,include_completed_covers=True)
            sg=system_live["global"]; ag=actual_live["global"]

            # V2.5.114 — one persistent WESTON ledger, mirrored as debt for SP
            # and receivable/gain for ŠR so both sides see the same running total.
            if active_user in (SENIOR_INITIALS,WESTON_CREDITOR_INITIALS):
                try:
                    _weston_mirror=db.weston_beer_stats_v25110(year,month)
                    st.markdown("### WESTON")
                    _wm1,_wm2=st.columns(2)
                    if active_user==SENIOR_INITIALS:
                        _wm1.metric(("Skola ŠR — iš viso" if lang=="LT" else "Debt to ŠR — lifetime"),int(_weston_mirror.get("total_beers",0)))
                        _wm2.metric(("Skola ŠR — šį mėnesį" if lang=="LT" else "Debt to ŠR — this month"),int(_weston_mirror.get("month_beers",0)))
                        st.caption("SP: kiekvienas tavo GENERUOTI / PERKURTI paspaudimas prideda +1 WESTON skolą ŠR." if lang=="LT" else "SP: every GENERATE / REGENERATE click adds +1 WESTON owed to ŠR.")
                    else:
                        _wm1.metric(("SP tau skolinga — iš viso" if lang=="LT" else "SP owes you — lifetime"),int(_weston_mirror.get("total_beers",0)))
                        _wm2.metric(("Tavo WESTON prieaugis — šį mėnesį" if lang=="LT" else "Your WESTON gain — this month"),int(_weston_mirror.get("month_beers",0)))
                        st.caption("ŠR: SP paspaudžia GENERUOTI / PERKURTI → tau +1 WESTON. Tas pats skaičius rodomas SP kaip skola." if lang=="LT" else "ŠR: SP presses GENERATE / REGENERATE → +1 WESTON owed to you. The same number is shown to SP as debt.")
                except Exception:
                    pass

            st.markdown(f"### {tr('fairness_hierarchy')}")
            st.caption(tr("fairness_hierarchy_intro"))
            h1,h2,h3,h4=st.columns(4)
            h1.metric(tr("hard_validity"),tr("hard_validity_pass") if g["hard_errors"]==0 else tr("hard_validity_fail"))
            h2.metric("Pradinio grafiko balansas",f"{sg.get('monthly_fairness_score',0)}%")
            h3.metric("Faktinio grafiko balansas",f"{ag.get('monthly_fairness_score',0)}%",delta=f"{ag.get('monthly_fairness_score',0)-sg.get('monthly_fairness_score',0):+.1f}")
            h4.metric("Faktinio grafiko darbo vietų disbalansas",ag.get("rotation_monthly_imbalance",0))

            if advanced_mode:
                hierarchy_df=pd.DataFrame([
                    {tr("fairness_level"):"1. Saugumas ir padengimas",tr("fairness_goal"):"Saugus, įmanomas ir pilnai padengtas grafikas.",tr("fairness_interpretation"):tr("hard_validity_pass") if g["hard_errors"]==0 else tr("hard_validity_fail")},
                    {tr("fairness_level"):"2. „Dirbti negaliu“",tr("fairness_goal"):"0 pažeidimų.",tr("fairness_interpretation"):f"Šį mėnesį pažeidimų: {g.get('resident_hard_total_losses',0)}."},
                    {tr("fairness_level"):"3. Tolygus privalomas paskirstymas",tr("fairness_goal"):tr("fairness_monthly_goal"),tr("fairness_interpretation"):tr("fairness_monthly_explain")},
                    {tr("fairness_level"):"4. Visų rezidentų pageidavimai",tr("fairness_goal"):tr("other_preferences_goal"),tr("fairness_interpretation"):tr("other_preferences_explain")},
                    {tr("fairness_level"):"5. Pateikimo vieta 1–16",tr("fairness_goal"):"Tik paskutinis kriterijus likusiam vienodai geram konfliktui.",tr("fairness_interpretation"):"Jeigu visų pageidavimus galima įvykdyti, pateikimo vieta nieko nekeičia."},
                ])
                st.dataframe(hierarchy_df,use_container_width=True,hide_index=True)
                st.caption(tr("fairness_100_note"))
                ledger_df=pd.DataFrame([
                    {tr("fairness_scope"):tr("fairness_ledger"),tr("fairness_interpretation"):tr("fairness_swap_neutral")},
                    {tr("fairness_scope"):tr("actual_ledger"),tr("fairness_interpretation"):tr("swap_note")},
                ])
                st.dataframe(ledger_df,use_container_width=True,hide_index=True)

                st.divider(); st.markdown(f"### {tr('fairness_breakdown')}")
                breakdown=[
                    ("SYSTEM",tr("metric_saturday"),sg.get("saturday_monthly_spread",0)),
                    ("ACTUAL",tr("metric_saturday"),ag.get("saturday_monthly_spread",0)),
                    ("SYSTEM",tr("metric_sunday"),sg.get("sunday_monthly_spread",0)),
                    ("ACTUAL",tr("metric_sunday"),ag.get("sunday_monthly_spread",0)),
                    ("SYSTEM",tr("metric_friday"),sg.get("friday_monthly_spread",0)),
                    ("ACTUAL",tr("metric_friday"),ag.get("friday_monthly_spread",0)),
                    ("SYSTEM",tr("metric_double"),sg.get("double_monthly_spread",0)),
                    ("ACTUAL",tr("metric_double"),ag.get("double_monthly_spread",0)),
                    ("SYSTEM",tr("metric_weekday"),sg.get("weekday_day_monthly_spread",0)),
                    ("ACTUAL",tr("metric_weekday"),ag.get("weekday_day_monthly_spread",0)),
                ]
                st.dataframe(pd.DataFrame([{tr("fairness_scope"):scope,tr("fairness_metric"):metric,tr("fairness_spread"):spread} for scope,metric,spread in breakdown]),use_container_width=True,hide_index=True)
                st.caption(tr("fairness_monthly_explain"))
                st.caption(tr("fairness_cumulative_explain"))

                st.divider(); st.markdown(f"### {tr('fairness_history')}")
                st.caption(tr("fairness_history_help"))
                trend=system_actual_fairness_trend_df(year,month)
                if trend.empty:
                    st.caption(tr("fairness_no_history"))
                else:
                    chart=trend.set_index("Period")
                    st.line_chart(chart[["SYSTEM monthly fairness","ACTUAL monthly fairness"]],height=280)
                    st.dataframe(trend,use_container_width=True,hide_index=True)
                    st.caption("Istorija tik stebėjimui — solveris jos nenaudoja kitam mėnesiui." if lang=="LT" else "History is monitoring-only — the solver never uses it for the next month.")

                st.divider(); st.markdown(f"### {tr('personal_vs_group')}")
                bp=base.stats["people"].get(active_user,{}).get("preference_score"); cp=current.stats["people"].get(active_user,{}).get("preference_score")
                ratio=balance_ratio(cp,ag.get("monthly_fairness_score"))
                a,b,c=st.columns(3); a.metric(tr("baseline_personal"),tr("not_applicable") if bp is None else f"{bp}%"); b.metric(tr("current_personal"),tr("not_applicable") if cp is None else f"{cp}%"); c.metric(tr("balance_ratio"),tr("not_applicable") if ratio is None else f"{ratio:.2f}")
                st.caption(tr("ratio_help")); st.markdown(f"### {tr('all_resident_scores')}"); st.dataframe(style_rows(preference_scores_df(current)),use_container_width=True,hide_index=True)

                # V2.5.49 resident request ledger: exact missed type/date/block/station,
                # so the resident immediately knows what kind of swap could repair it.
                pd_base=(base.stats.get("people",{}).get(active_user,{}) or {})
                pd_now=(current.stats.get("people",{}).get(active_user,{}) or {})
                st.divider()
                st.markdown("### Mano pageidavimų išpildymas — detalės" if lang=="LT" else "### My request satisfaction — details")
                st.caption(
                    ("SYSTEM = paskelbimo momentas ir užšaldytas ORIGINAL pageidavimų rinkinys. ACTUAL = dabartinis realus grafikas po apsikeitimų; pageidavimų išpildymas perskaičiuojamas prieš tą patį ORIGINAL rinkinį, todėl vėliau galima patikimai palyginti paskelbtą ir galutinį mėnesio rezultatą."
                     if lang=="LT" else
                     "SYSTEM uses the frozen ORIGINAL request set at publication. ACTUAL is the current real grafikas after swaps; satisfaction is recalculated against that same ORIGINAL set, allowing a valid published-versus-final retrospective comparison.")
                )
                r1,r2,r3,r4=st.columns(4)
                r1.metric("RESIDENT HARD — SYSTEM",tr("not_applicable") if pd_base.get("resident_hard_score") is None else f"{pd_base.get('resident_hard_score')}%")
                r2.metric("RESIDENT HARD — ACTUAL",tr("not_applicable") if pd_now.get("resident_hard_score") is None else f"{pd_now.get('resident_hard_score')}%")
                r3.metric("SOFT — ACTUAL",tr("not_applicable") if pd_now.get("soft_preference_score") is None else f"{pd_now.get('soft_preference_score')}%")
                r4.metric(("VISI PRAŠYMAI — ACTUAL" if lang=="LT" else "ALL REQUESTS — ACTUAL"),tr("not_applicable") if pd_now.get("overall_request_score") is None else f"{pd_now.get('overall_request_score')}%")

                hard_misses=pd_now.get("resident_hard_conflicts") or []
                soft_misses=pd_now.get("soft_request_misses") or []
                if hard_misses:
                    st.error(
                        f"„Negaliu dirbti“ pažeidimų: {len(hard_misses)}. Tai neturėtų nutikti — šias vietas reikia pataisyti prieš tvirtinant grafiką."
                        if lang=="LT" else
                        f"Cannot-work violations: {len(hard_misses)}. This should not happen; these must be fixed before confirmation."
                    )
                    render_missed_requests_scandi(hard_misses,active_user,key_suffix=f"personal_hard_{active_user}")
                else:
                    st.success("Visi tavo RESIDENT HARD prašymai išpildyti." if lang=="LT" else "All of your RESIDENT HARD requests are honored.")

                if soft_misses:
                    st.markdown("#### Ko nepavyko išpildyti" if lang=="LT" else "#### What could not be honored")
                    render_missed_requests_scandi(soft_misses,active_user,key_suffix=f"personal_soft_{active_user}")
                else:
                    st.caption("Neįvykdytų struktūruotų SOFT pageidavimų nėra." if lang=="LT" else "There are no unhonored structured SOFT requests.")

                with st.expander("Išpildyti pageidavimai" if lang=="LT" else "Honored requests"):
                    honored=pd_now.get("honored_request_details") or []
                    if honored:
                        st.dataframe(request_details_df(honored,active_user),use_container_width=True,hide_index=True)
                    else:
                        st.caption(tr("not_applicable"))

                st.markdown("#### Grupės RESIDENT HARD našta" if lang=="LT" else "#### Group RESIDENT HARD burden")
                rr1,rr2,rr3,rr4=st.columns(4)
                rr1.metric(("Pažeidimų iš viso" if lang=="LT" else "Total violations"),g.get("resident_hard_total_losses",0))
                rr2.metric(("Paveikta rezidentų" if lang=="LT" else "Residents affected"),g.get("resident_hard_residents_affected",0))
                rr3.metric(("Max pažeidimų vienam" if lang=="LT" else "Max violations per resident"),g.get("resident_hard_max_loss_per_resident",0))
                rr4.metric(("Cumulative spread" if lang=="LT" else "Cumulative spread"),g.get("resident_hard_cumulative_spread",0))
            else:
                bp=base.stats["people"].get(active_user,{}).get("preference_score")
                cp=current.stats["people"].get(active_user,{}).get("preference_score")
                st.caption(
                    ("Čia rodoma tik trumpa santrauka. Pilnas fairness breakdown, istorija ir visų rezidentų palyginimas yra Išplėstiniame režime."
                     if lang=="LT" else
                     "Only a short summary is shown here. Full fairness breakdown, history and all-resident comparison are in Advanced mode.")
                )
                p1,p2=st.columns(2)
                p1.metric(("Tavo pageidavimų išpildymas" if lang=="LT" else "Your preference fulfillment"),tr("not_applicable") if cp is None else f"{cp}%")
                p2.metric(("Mėnesio fairness" if lang=="LT" else "Monthly fairness"),f"{g.get('monthly_fairness_score',g['fairness_score'])}%")
    pos+=1

# --- Credits ---
with tabs[pos]:
    st.subheader("Kreditai")

    if active_user in (SENIOR_INITIALS,WESTON_CREDITOR_INITIALS):
        try:
            _weston_credit=db.weston_beer_stats_v25110(year,month)
            _w_total=int(_weston_credit.get("total_beers",0) or 0)
            with st.expander("WESTON",expanded=False):
                st.metric("Balansas",(f"−{_w_total}" if active_user==SENIOR_INITIALS else f"+{_w_total}"))
        except Exception:
            pass

    earned_units=db.reward_credit_earned_units(active_user)
    current_use_units=db.reward_credit_redemption_units(active_user,year,month)
    available_for_month=db.reward_credit_available_for_month(active_user,year,month)
    other_reserved=max(0,earned_units-available_for_month)
    free_units=max(0,available_for_month-current_use_units)

    c1,c2,c3=st.columns(3)
    c1.metric("Sukaupta",f"{earned_units/12:.2f}")
    c2.metric("Šiam grafikui",f"{current_use_units/12:.2f}")
    c3.metric("Laisvas likutis",f"{free_units/12:.2f}")
    st.caption("1,00 kreditas = 12 bazinių tarifinių valandų · 1× / 2× / 3× · galiojimo pabaigos nėra. Uždirbtas kreditas naudojamas nuo kito mėnesio.")

    _sched_state=db.get_schedule_state(year,month)
    _lifecycle=db.get_schedule_lifecycle(year,month)
    _credit_locked=bool(_sched_state.get("has_published")) or str(_lifecycle.get("state") or "")=="final"
    st.markdown("### Panaudoti šiam grafikui")
    max_redeem_units=(available_for_month//6)*6
    _redeem_value=st.number_input(
        "Kreditai",min_value=0.0,max_value=float(max_redeem_units)/12.0,
        value=min(float(current_use_units)/12.0,float(max_redeem_units)/12.0),step=0.5,format="%.2f",
        disabled=_credit_locked,key=f"reward_credit_use_{year}_{month}_{active_user}"
    )
    if _credit_locked:
        st.caption("Pagrindinis grafikas jau paskelbtas — šio mėnesio kreditų panaudojimas užrakintas. Nepanaudotas likutis persikelia į kitus mėnesius.")
    elif st.button("IŠSAUGOTI KREDITŲ PANAUDOJIMĄ",type="primary",use_container_width=True,key=f"reward_credit_save_{year}_{month}_{active_user}"):
        try:
            _units=int(round(float(_redeem_value)*12))
            if _units%6:
                raise ValueError("Šiam dieniniam grafikui kreditai naudojami 0,50 žingsniais.")
            db.set_my_reward_credit_redemption_v25136(year,month,_units)
            st.success("Išsaugota. Jei juodraštis jau buvo sugeneruotas, jį reikia sugeneruoti iš naujo.")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    if lifecycle_operator_ui:
        with st.expander("Registruoti ekstra pavadavimą",expanded=False):
            _target=st.selectbox("Rezidentas",[p["initials"] for p in DEFAULT_PEOPLE],key=f"reward_manual_person_{year}_{month}")
            _event_date=st.date_input("Data",value=date.today(),key=f"reward_manual_date_{year}_{month}")
            _kind_label=st.selectbox("Pamaina",["Rytas 08–14","Popietė 14–20","Diena 08–20","Naktis 20–08"],key=f"reward_manual_kind_{year}_{month}")
            _kind={"Rytas 08–14":"AM","Popietė 14–20":"PM","Diena 08–20":"FULL","Naktis 20–08":"NIGHT"}[_kind_label]
            _units=reward_credit_units_for_shift(_event_date.year,_event_date.month,_event_date.day,_kind)
            st.metric("Kreditas",f"{reward_credit_value(_units):.2f}")
            _detail=st.text_input("Pastaba",key=f"reward_manual_detail_{year}_{month}")
            if st.button("REGISTRUOTI",use_container_width=True,key=f"reward_manual_add_{year}_{month}"):
                try:
                    db.award_manual_reward_credit_v25136(_target,_event_date.isoformat(),_kind,_units,_detail)
                    st.success("Kreditas pridėtas.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    with st.expander("Kreditų istorija",expanded=False):
        _ledger=db.reward_credit_ledger(active_user)
        if _ledger:
            _rows=[]
            for r in _ledger:
                _rows.append({
                    "Data":r.get("event_date") or str(r.get("created_at") or "")[:10],
                    "Šaltinis":r.get("source"),
                    "Pamaina":r.get("shift_kind"),
                    "Kreditas":round(int(r.get("units",0) or 0)/12.0,2),
                    "Pastaba":r.get("detail") or "",
                })
            st.dataframe(pd.DataFrame(_rows),use_container_width=True,hide_index=True)
        else:
            st.caption("Kreditų operacijų dar nėra.")

    if senior_mode:
        with st.expander("Grupės balansai",expanded=False):
            _all=db.all_reward_credit_balances_v25136()
            st.dataframe(pd.DataFrame([{
                "Rezidentas":p["initials"],
                "Likutis":round(max(0,int(_all.get(p["initials"],0) or 0))/12.0,2),
            } for p in DEFAULT_PEOPLE]),use_container_width=True,hide_index=True)
    pos+=1

# --- Backups ---
with tabs[pos]:
    st.subheader(tr("backup_title")); currentp=db.load_schedule(year,month,"current")
    if weekend_fcfs_backup_mode(year,month):
        _bk_published=bool(db.get_schedule_state(year,month).get("has_published")) and bool(currentp)
        st.write(
            "Dubliai = atskiras atsarginių pamainų sluoksnis po grafiko paskelbimo. Nuo spalio savaitgalio dublis yra viena pilna 12 h diena. Jis nėra pageidavimas ir nekeičia pagrindinio grafiko darbo krūvio ar pageidavimų statistikos."
            if lang=="LT" else
            "BACKUPS = a separate post-publication standby layer. From October, a weekend backup is one full 12-hour day. It is not a preference and does not enter normal-schedule workload or fairness calculations."
        )
        if not _bk_published:
            with st.container(border=True):
                st.markdown("#### Dubliai dar neaktyvūs" if lang=="LT" else "#### Backups are not active yet")
                st.info(
                    "Dubliai atsirakins tik paskelbus preliminarų grafiką. Iki tol jų rinktis nereikia ir jie nedalyvauja grafiko sudaryme."
                    if lang=="LT" else
                    "Backups unlock only after the preliminary schedule is published. Before then, no selection is needed and backups do not participate in schedule generation."
                )
                st.caption("Nuo spalio savaitgalio dublis = viena pilna 12 h FULL diena." if lang=="LT" else "From October, a weekend backup = one full 12h FULL day.")
            claims=[]
            slot_map_fcfs={s.idx:s for s in _fcfs_weekend_slot_pool(year,month)}
        else:
            if resident_ok:
                render_fcfs_weekend_backup_selector(year,month,active_user)
                st.divider()
            claims=db.list_backup_claims(year,month)
            slot_map_fcfs={s.idx:s for s in _fcfs_weekend_slot_pool(year,month)}
            st.info(
                "Dubliai aktyvūs visą likusį mėnesį. Nuo spalio savaitgalio pasirinkimas yra 12 h FULL diena."
                if lang=="LT" else
                "Backups remain active for the rest of the month. From October, each weekend selection is a 12h FULL day."
            )
        board=[]
        for r in claims:
            sl=slot_map_fcfs.get(int(r.get("covered_slot") or 0))
            board.append({
                tr("person"):r.get("initials"),
                tr("date"):(f"{year}-{month:02d}-{sl.day:02d}" if sl else "—"),
                tr("shift"):(block_label(sl.block) if sl else "—"),
                tr("department"):(sl.department if sl else "—"),
                tr("submitted"):r.get("claimed_at") or "",
            })
        if _bk_published:
            cfc1,cfc2=st.columns(2)
            cfc1.metric("Dubliai" if lang=="LT" else "Backups",f"{len(claims)}/16")
            cfc2.metric("Dar trūksta" if lang=="LT" else "Missing",max(0,16-len(claims)))
            if board:
                st.dataframe(pd.DataFrame(board),use_container_width=True,hide_index=True)
            else:
                st.caption("Dar niekas nepasirinko dublio." if lang=="LT" else "No backup has been selected yet.")

        if lifecycle_operator_ui and _bk_published:
            st.markdown("#### Seniūnės/operatoriaus dublio korekcija" if lang=="LT" else "#### Senior/operator backup override")
            st.caption(
                "Šis įrankis aktyvus tik paskelbus preliminarų grafiką. Jei pasirinktas slotas jau priklauso kitam žmogui ir abu turi po dublį, sistema juos sukeičia vietomis; veiksmas audituojamas."
                if lang=="LT" else
                "This tool is active only after the preliminary schedule is published. If the selected slot belongs to someone else and both residents already have a backup, their backup slots are swapped; the action is audited."
            )
            _op_people=[pp["initials"] for pp in DEFAULT_PEOPLE]
            _op_target=st.selectbox("Rezidentas" if lang=="LT" else "Resident",_op_people,key=f"op_backup_person_{year}_{month}")
            _op_slots=list(slot_map_fcfs.keys())
            def _op_slot_label(sid):
                _s=slot_map_fcfs[int(sid)]
                _owner=next((str(r.get("initials")) for r in claims if int(r.get("covered_slot") or 0)==int(sid)),"laisvas" if lang=="LT" else "free")
                return f"{_s.day:02d} {WEEKDAYS[lang][_s.weekday]} · {block_label(_s.block)} · {_owner}"
            _op_sid=st.selectbox("Dublio vieta" if lang=="LT" else "Backup slot",_op_slots,format_func=_op_slot_label,key=f"op_backup_slot_{year}_{month}")
            _op_reason=st.text_input("Priežastis (auditui)" if lang=="LT" else "Reason (audit)",key=f"op_backup_reason_{year}_{month}")
            if st.button("PERRASYTI DUBLĮ" if lang=="LT" else "OVERRIDE BACKUP",type="primary",use_container_width=True,disabled=not _op_reason.strip(),key=f"op_backup_apply_{year}_{month}"):
                try:
                    db.operator_set_weekend_backup_v25119(year,month,_op_target,int(_op_sid),_op_reason.strip())
                    if currentp:
                        _rr=refresh_result_payload(currentp,year,month,use_actual_backups=False)
                        sync_backup_plan(year,month,_rr)
                    st.success("Dublis pakeistas ir audituotas." if lang=="LT" else "Backup changed and audited.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
    else:
        st.write(tr("backup_definition"))
        all_backup_slots=[s for s in make_slots(year,month) if backup_required_slot(s)]
        weekend_slots=[s for s in all_backup_slots if s.weekday >= 5]
        centro120_slots=[s for s in all_backup_slots if s.weekday < 5 and s.department.startswith("Centro UG 120") and s.block=="AM"]
        onko_slots=[s for s in all_backup_slots if s.weekday < 5 and is_onko_slot(s)]
        sps_ro_slots=[s for s in all_backup_slots if s.weekday < 5 and s.department.startswith("SPS RO")]
        sps_ug_slots=[s for s in all_backup_slots if s.weekday < 5 and s.department.startswith("SPS UG")]

        claims=db.list_backup_claims(year,month)
        claim_by_slot={int(r["covered_slot"]):r for r in claims}
        my_claims=[r for r in claims if r["initials"]==active_user]
        my_claim_ids={int(r["covered_slot"]) for r in my_claims}
        claim_deadline=deadline_for(year,month)
        can_self_claim=(date.today() <= claim_deadline and not currentp and resident_ok)

        st.markdown("### Mano dublių rezervacijos" if lang=="LT" else "### My backup reservations")
        st.caption(
            ("Rezervuojami privalomo dengimo dubliai pagal poziciją: SPS RO bet kurią dieną / bloką, SPS UG bet kurią dieną / bloką, Centro UG 120 rytas ir Onko RO pilna diena. "
             "CENTRO RO dengiama automatiškai best-effort ir jos rezervuoti nereikia. Gali pasirinkti kelis slotus; rezervacija blokuoja persidengiančią normalią pamainą."
             if lang=="LT" else
             "Reservable mandatory backup groups are position-based: SPS RO on any day/block, SPS UG on any day/block, Centro UG 120 morning, and full-day Onko RO. "
             "CENTRO RO is planned automatically as best-effort and does not need self-reservation. You may choose multiple slots; a reservation blocks overlapping normal work.")
        )
        st.metric(tr("backup_claim_deadline"),claim_deadline.isoformat())

        slot_lookup={s.idx:s for s in all_backup_slots}
        def claim_label(sid):
            s=slot_lookup[int(sid)]
            owner=claim_by_slot.get(int(sid),{}).get("initials")
            status=owner if owner else tr("backup_claim_free")
            return f"{s.day:02d} {WEEKDAYS[lang][s.weekday]} · {s.department} · {block_label(s.block)} · {status}"

        if my_claim_ids:
            st.success(
                ("Rezervuota: " if lang=="LT" else "Reserved: ")
                + str(len(my_claim_ids))
                + (" dublių slotų" if lang=="LT" else " backup slots")
            )
        else:
            st.warning(
                "Dar nepasirinkai nė vieno dublio sloto." if lang=="LT"
                else "You have not selected any backup slot yet."
            )

        if can_self_claim:
            own_person=next(p for p in load_people(year,month) if p.initials==active_user)

            def selectable_ids(group):
                return [
                    s.idx for s in group
                    if (
                        (not claim_by_slot.get(s.idx) or claim_by_slot[s.idx]["initials"]==active_user)
                        and not hard_unavailable_for_block(own_person,s.day,s.block)
                    )
                ]

            selected=[]
            group_specs=[
                ("Savaitgaliai · SPS RO budėjimai" if lang=="LT" else "Weekends · SPS RO duty",weekend_slots,"weekend"),
                ("Centro UG 120 · rytas" if lang=="LT" else "Centro UG 120 · morning",centro120_slots,"centro120"),
                ("Onko RO · pilna 9 val. pamaina" if lang=="LT" else "Onko RO · full 9h shift",onko_slots,"onko"),
                ("Darbo dienos · SPS RO" if lang=="LT" else "Weekdays · SPS RO",sps_ro_slots,"spsro"),
                ("Darbo dienos · SPS UG" if lang=="LT" else "Weekdays · SPS UG",sps_ug_slots,"spsug"),
            ]
            for title,group,key in group_specs:
                ids=selectable_ids(group)
                defaults=[sid for sid in ids if sid in my_claim_ids]
                with st.expander(title,expanded=(key=="weekend")):
                    picked=st.multiselect(
                        ("Pasirink dublių slotus" if lang=="LT" else "Choose backup slots"),
                        ids,
                        default=defaults,
                        format_func=claim_label,
                        key=f"backup_claims_{key}_{year}_{month}_{active_user}",
                    )
                    selected.extend(picked)

            if st.button(
                "IŠSAUGOTI DUBLIŲ PASIRINKIMUS" if lang=="LT" else "SAVE BACKUP SELECTIONS",
                type="primary",use_container_width=True,key="save_backup_claims_v2532"
            ):
                try:
                    db.replace_backup_claims(year,month,active_user,selected)
                    st.success("Dublių pasirinkimai išsaugoti." if lang=="LT" else "Backup selections saved.")
                    st.rerun()
                except Exception:
                    st.error(
                        "Bent vieną pasirinktą slotą ką tik rezervavo kitas rezidentas. Atnaujinau sąrašą — pasirink iš naujo."
                        if lang=="LT" else
                        "At least one selected slot was just claimed by another resident. The list has been refreshed; choose again."
                    )
                    st.rerun()
        else:
            st.caption(tr("backup_claim_locked"))

        if advanced_mode:
            board=[]
            for s in all_backup_slots:
                r=claim_by_slot.get(s.idx)
                group=("Centro 120" if s.department.startswith("Centro UG 120") else "Onko/TBL" if is_onko_slot(s) else "SPS RO" if s.department.startswith("SPS RO") else "SPS UG")
                board.append({
                    ("Grupė" if lang=="LT" else "Group"):group,
                    tr("date"):f"{year}-{month:02d}-{s.day:02d}",
                    tr("department"):s.department,
                    tr("shift"):block_label(s.block),
                    tr("person"):(r["initials"] if r else tr("backup_claim_free")),
                    tr("updated"):(r["claimed_at"] if r else "")
                })
            st.markdown("### Visų dublių rezervacijų lenta" if lang=="LT" else "### All backup reservations")
            st.dataframe(pd.DataFrame(board),use_container_width=True,hide_index=True)

        if senior_mode:
            nonclaimers=[p["initials"] for p in DEFAULT_PEOPLE if p["initials"] not in {r["initials"] for r in claims}]
            st.markdown(f"### {tr('backup_claim_auto_queue')}"); st.caption(tr("backup_claim_auto_queue_help")); st.write(", ".join(nonclaimers) if nonclaimers else "—")
    if not currentp:
        st.info(tr("not_published"))
    else:
        result=refresh_result_payload(currentp,year,month)
        if senior_mode:
            desired,backup_errors=sync_backup_plan(year,month,result)
        else:
            desired=[]; backup_errors=[]
        current_rows=db.list_backups(year,month)
        _slot_map_all={s.idx:s for s in make_slots(year,month)}
        if weekend_fcfs_backup_mode(year,month):
            expected=16
            required_actual=sum(1 for r in current_rows if int(r.get("covered_slot") or 0) in {s.idx for s in _fcfs_weekend_slot_pool(year,month)})
            centro_total=centro_covered=0
        else:
            expected=sum(1 for s in _slot_map_all.values() if backup_required_slot(s) and result.assignments.get(s.idx))
            required_actual=sum(1 for r in current_rows if (int(r.get("covered_slot")) in _slot_map_all and backup_required_slot(_slot_map_all[int(r.get("covered_slot"))])))
            centro_total=sum(1 for s in _slot_map_all.values() if backup_best_effort_slot(s) and result.assignments.get(s.idx))
            centro_covered=sum(1 for r in current_rows if (int(r.get("covered_slot")) in _slot_map_all and backup_best_effort_slot(_slot_map_all[int(r.get("covered_slot"))])))
        st.markdown(f"### {tr('backup_coverage')}")
        c1,c2,c3=st.columns(3)
        c1.metric(("Reikalingi FCFS dubliai" if lang=="LT" else "Required FCFS backups") if weekend_fcfs_backup_mode(year,month) else tr("working_person_days"),expected)
        c2.metric(tr("covered_person_days"),required_actual)
        c3.metric(("Trūksta" if lang=="LT" else "Missing") if weekend_fcfs_backup_mode(year,month) else "CENTRO RO best-effort",max(0,16-required_actual) if weekend_fcfs_backup_mode(year,month) else f"{centro_covered}/{centro_total}")
        if backup_errors:
            st.error(tr("backup_incomplete")); st.dataframe(pd.DataFrame(backup_errors),use_container_width=True,hide_index=True)
        elif required_actual==expected:
            st.success(tr("backup_complete"))
        else:
            st.warning(tr("backup_incomplete"))

        st.markdown(f"### {tr('my_backup_schedule')}"); st.dataframe(backup_grid(year,month,result,active_user),use_container_width=True)
        bdf=backup_table(year,month,result); my=bdf[bdf[tr("effective_backup")]==active_user] if not bdf.empty else bdf
        if my.empty: st.caption(tr("no_backups"))
        else: st.dataframe(my,use_container_width=True,hide_index=True)

        if senior_mode:
            st.divider(); st.markdown(f"### {tr('manage_backups')}")
            if st.button(tr("resync_backups"),type="primary"):
                desired,errs=sync_backup_plan(year,month,result)
                if errs: st.error(tr("backup_incomplete"))
                else: st.success(tr("backup_synced")); st.rerun()
            allb=db.list_backups(year,month)
            if allb:
                st.markdown(f"### {tr('actual_override')}"); lookup={r["id"]:r for r in allb}; ids=list(lookup)
                slot_map={s.idx:s for s in make_slots(year,month)}
                def ridlabel(rid):
                    r=lookup[rid]; sid=int(r["covered_slot"]); s=slot_map.get(sid); covered=result.assignments.get(sid,"")
                    if s is None: return f"#{rid}"
                    return f"#{rid} · {s.day:02d} {WEEKDAYS[lang][s.weekday]} · {covered} · {s.department} · {block_label(s.block)} · {r['planned_backup']}"
                rid=st.selectbox(tr("backup_record"),ids,format_func=ridlabel); rr=lookup[rid]; sid=int(rr["covered_slot"]); covered_slot=slot_map.get(sid)
                people=people_for_stored_result(result,year,month); byinit={p.initials:p for p in people}
                # V2.5.61: manual/actual backup selection is broader than the automatic plan.
                # A resident may voluntarily take the backup even when this creates a fatigue / >48 h
                # warning or self-overrides RESIDENT HARD. ABSOLUTE unavailability and overlap remain
                # excluded from the candidate list.
                eligible=_eligible_backup_candidates(year,month,result,covered_slot,people,allow_resident_hard=True) if covered_slot is not None else []
                actual_opts=[""]+eligible
                current_actual=rr["actual_backup"] or ""
                if current_actual and current_actual not in actual_opts: actual_opts.append(current_actual)
                actual=st.selectbox(tr("actual_backup"),actual_opts,index=actual_opts.index(current_actual) if current_actual in actual_opts else 0,format_func=lambda i:"—" if i=="" else f"{i} — {people_map[i]['name']}",disabled=bool(rr.get("completed_at")))

                preview=None
                if actual and covered_slot is not None:
                    preview=_preview_manual_backup_takeover(year,month,result,covered_slot,actual,exclude_backup_id=rid)
                    st.markdown("#### Dublio perėmimo pasekmės" if lang=="LT" else "#### Backup takeover consequences")
                    if preview.get("rows"):
                        st.dataframe(pd.DataFrame(preview["rows"]),use_container_width=True,hide_index=True)
                    for msg in preview.get("blockers",[]):
                        st.error(("Negalima patvirtinti: " if lang=="LT" else "Cannot confirm: ")+msg)
                    if preview.get("warnings"):
                        st.warning(("Galima tik po aiškaus savanoriško patvirtinimo:\n- " if lang=="LT" else "Allowed only after explicit voluntary acknowledgement:\n- ")+"\n- ".join(preview["warnings"]))
                        st.caption(
                            "40/48 val. ir recovery perspėjimai nėra automatinis draudimas savanoriškam dubliui. Tačiau >12 val./d., aktyvios 7 d. ribos viršijimas, <11 val. paros poilsio, >6 darbo dienos/7 d., pateisinamas neatvykimas ar persidengimas lieka blokuojami."
                            if lang=="LT" else
                            "40/48h and recovery warnings do not automatically block a voluntary backup takeover. >12h/day, breach of the active 7-day cap, <11h daily rest, >6 workdays/7d, justified absence or overlap remain blocking."
                        )

                c1,c2=st.columns(2)
                with c1:
                    if actual and preview and preview.get("warnings") and preview.get("ok"):
                        confirm_manual=st.checkbox(
                            "Rezidentas supranta parodytas pasekmes ir SAVANORIŠKAI sutinka perimti šį dublį." if lang=="LT" else "The resident understands the shown consequences and VOLUNTARILY agrees to take this backup.",
                            key=f"backup_override_ack_{rid}_{actual}_{preview.get('fingerprint')}"
                        )
                        if st.button("PATVIRTINTI VIS TIEK" if lang=="LT" else "CONFIRM ANYWAY",type="primary",use_container_width=True,disabled=(not confirm_manual or bool(rr.get("completed_at")))):
                            meta={"version":"2.5.61","kind":"MANUAL_BACKUP_OVERRIDE","resident":actual,"covered_slot":int(sid),"fingerprint":preview.get("fingerprint"),"warnings":preview.get("warnings",[]),"rows":preview.get("rows",[]),"acknowledged_at":datetime.now(timezone.utc).isoformat()}
                            oldmeta=_backup_override_note_decode(rr.get("note"))
                            db.set_actual_backup(rid,actual or None,note=_backup_override_note_encode(meta,oldmeta.get("legacy_note","")))
                            persist_actual_satisfaction(year,month)
                            refresh_calendar_subscription_feeds([x for x in [rr.get("planned_backup"),current_actual,actual] if x])
                            st.success("Dublio perėmimas patvirtintas su perspėjimo ACK." if lang=="LT" else "Backup takeover confirmed with warning acknowledgement."); st.rerun()
                    else:
                        if st.button(tr("record_actual"),use_container_width=True,disabled=(bool(rr.get("completed_at")) or bool(actual and preview and not preview.get("ok")))):
                            db.set_actual_backup(rid,actual or None); persist_actual_satisfaction(year,month)
                            refresh_calendar_subscription_feeds([x for x in [rr.get("planned_backup"),current_actual,actual] if x])
                            st.success(tr("actual_saved")); st.rerun()
                with c2:
                    if actual and preview and preview.get("warnings") and preview.get("ok"):
                        if st.button("ATŠAUKTI" if lang=="LT" else "CANCEL",use_container_width=True,key=f"cancel_backup_override_{rid}"):
                            st.info("Nepatvirtinta — dublio perėmimas nepakeistas." if lang=="LT" else "Not confirmed — backup takeover unchanged.")
                    else:
                        if st.button(tr("clear_actual"),use_container_width=True,disabled=bool(rr.get("completed_at"))):
                            db.clear_actual_backup(rid); persist_actual_satisfaction(year,month)
                            refresh_calendar_subscription_feeds([x for x in [rr.get("planned_backup"),current_actual] if x])
                            st.success(tr("actual_cleared")); st.rerun()
                rr_fresh=next((x for x in db.list_backups(year,month) if int(x["id"])==int(rid)),rr)
                st.markdown(f"### {tr('backup_activation')}")
                effective_for_activation=str(rr_fresh.get("actual_backup") or rr_fresh.get("planned_backup") or "")
                activation_preview=(_preview_manual_backup_takeover(year,month,result,covered_slot,effective_for_activation,exclude_backup_id=rid) if effective_for_activation and covered_slot is not None else None)
                if rr_fresh.get("activated_at"):
                    st.success(f"{tr('backup_activated')}: {rr_fresh.get('activated_at')}")
                    if st.button(tr("undo_activation"),use_container_width=True):
                        db.clear_backup_activation(rid); st.success(tr("activation_undone")); st.rerun()
                else:
                    if activation_preview and activation_preview.get("blockers"):
                        st.error("Dublio aktyvuoti negalima, kol išlieka aukščiau parodytas absoliutus / teisinis blokatorius." if lang=="LT" else "Backup cannot be activated while an absolute/legal blocker remains.")
                    elif activation_preview and activation_preview.get("warnings"):
                        st.warning("Aktyvavus šį dublį perspėjimai taps realaus darbo pasekmėmis." if lang=="LT" else "Activating this backup will turn the warnings into actual-work consequences.")
                        activation_ack=st.checkbox("Patvirtinu, kad perimantis rezidentas sutiko su šiomis pasekmėmis." if lang=="LT" else "I confirm the covering resident agreed to these consequences.",key=f"backup_activation_ack_{rid}_{activation_preview.get('fingerprint')}")
                        if st.button("AKTYVUOTI IR PATVIRTINTI VIS TIEK" if lang=="LT" else "ACTIVATE AND CONFIRM ANYWAY",type="primary",use_container_width=True,disabled=not activation_ack):
                            oldmeta=_backup_override_note_decode(rr_fresh.get("note"))
                            oldmeta.update({"activation_ack_fingerprint":activation_preview.get("fingerprint"),"activation_ack_at":datetime.now(timezone.utc).isoformat(),"activation_warnings":activation_preview.get("warnings",[])})
                            db.set_backup_note(rid,_backup_override_note_encode(oldmeta,oldmeta.get("legacy_note","")))
                            db.activate_backup(rid)
                            rr_alert=next((x for x in db.list_backups(year,month) if int(x["id"])==int(rid)),rr_fresh)
                            ok_mail,detail_mail=send_backup_activation_email(year,month,result,rr_alert)
                            if ok_mail: st.success(tr("backup_email_sent"))
                            else: st.warning(f"{tr('backup_email_failed')} {detail_mail}")
                            st.rerun()
                    else:
                        if st.button(tr("activate_backup"),type="primary",use_container_width=True):
                            db.activate_backup(rid)
                            rr_alert=next((x for x in db.list_backups(year,month) if int(x["id"])==int(rid)),rr_fresh)
                            ok_mail,detail_mail=send_backup_activation_email(year,month,result,rr_alert)
                            if ok_mail: st.success(tr("backup_email_sent"))
                            else: st.warning(f"{tr('backup_email_failed')} {detail_mail}")
                            st.rerun()
                if rr_fresh.get("completed_at"):
                    st.success(f"{tr('completed_backup')}: {rr_fresh.get('completed_at')}")
                    if st.button(tr("undo_backup_completed"),use_container_width=True):
                        try:
                            db.undo_backup_credit_v25136(rid); st.success(tr("backup_completion_undone")); st.rerun()
                        except Exception as exc:
                            st.error(str(exc))
                else:
                    auto_type=("NIGHT" if covered_slot and covered_slot.block=="NIGHT" else covered_slot.block if covered_slot else "")
                    _credit_units=(reward_credit_units_for_shift(year,month,covered_slot.day,auto_type) if covered_slot is not None and auto_type in ("AM","PM","FULL","NIGHT") else 0)
                    if _credit_units:
                        st.info(f"Už realiai atliktą pavadavimą: +{reward_credit_value(_credit_units):.2f} kredito")
                    if st.button(tr("mark_backup_completed"),type="primary",use_container_width=True,disabled=not _credit_units):
                        try:
                            db.complete_backup_cover_v25136(rid,_credit_units,auto_type,date(year,month,covered_slot.day).isoformat())
                            st.success(f"Realus pavadavimas užregistruotas: +{reward_credit_value(_credit_units):.2f} kredito.")
                        except Exception as exc:
                            st.error(str(exc))
                _all_credit=db.all_reward_credit_balances_v25136()
                with st.expander("Kreditų balansai",expanded=False):
                    st.dataframe(pd.DataFrame([{
                        "Rezidentas":i,
                        "Kreditai":round(max(0,int(_all_credit.get(i,0) or 0))/12.0,2),
                    } for i in sorted(_all_credit)]),use_container_width=True,hide_index=True)
                st.dataframe(backup_table(year,month,result),use_container_width=True,hide_index=True)
pos+=1

# --- Swaps ---
with tabs[pos]:
    SWAP_META_PREFIX="V2555_SWAP_META:"
    def _swap_meta_decode(reason):
        raw=str(reason or "")
        if raw.startswith(SWAP_META_PREFIX):
            try:
                data=json.loads(raw[len(SWAP_META_PREFIX):])
                return data if isinstance(data,dict) else {}
            except Exception:
                return {}
        if raw.startswith("V2554_SWAP_META:"):
            try:
                old=json.loads(raw[len("V2554_SWAP_META:"):])
                return {"phase":old.get("phase","pending"),"impact_ack":{}}
            except Exception:
                pass
        if raw=="accepted_pending_senior_apply":
            return {"phase":"accepted_pending_senior_apply","impact_ack":{}}
        return {"phase":"pending","impact_ack":{}}
    def _swap_meta_encode(meta):
        return SWAP_META_PREFIX+json.dumps(meta,ensure_ascii=False,separators=(",",":"))
    def _impact_acks(meta):
        return {str(k):str(v) for k,v in ((meta or {}).get("impact_ack") or {}).items()}
    def _is_swap_slot_conflict(exc):
        msg=str(exc or "")
        return "SWAP_SLOT_ALREADY_PENDING" in msg or "BACKUP_SWAP_SLOT_ALREADY_PENDING" in msg
    def _impact_rows(stats,initials):
        return list((((stats or {}).get("global",{}) or {}).get("swap_warning_rows") or {}).get(initials,[]) or [])
    def _render_impact_table(stats,initials,title=None):
        rows=_impact_rows(stats,initials)
        if title:
            st.markdown(f"**{title}**")
        if not rows:
            st.caption("Papildomų swapo perspėjimų nėra." if lang=="LT" else "No additional swap warnings.")
            return
        df=pd.DataFrame([{
            ("Lygis" if lang=="LT" else "Level"):r.get("severity","ACK"),
            ("Kas keičiasi" if lang=="LT" else "Impact"):r.get("kind",""),
            ("Data / langas" if lang=="LT" else "Date / window"):r.get("date",""),
            ("Prieš" if lang=="LT" else "Before"):r.get("before",""),
            ("Po" if lang=="LT" else "After"):r.get("after",""),
            ("Paaiškinimas" if lang=="LT" else "Explanation"):r.get("explanation",""),
        } for r in rows])
        st.dataframe(df,use_container_width=True,hide_index=True)

    st.subheader(tr("swap_title")); st.write(tr("swap_note")); st.caption(tr("multiple_swap_help"))
    swap_flash=st.session_state.pop("_swap_response_flash",None)
    if swap_flash:
        level,msg=swap_flash
        if level=="success": st.success(msg)
        elif level=="warning": st.warning(msg)
        else: st.info(msg)
    refresh_col,_=st.columns([1,4])
    with refresh_col:
        if st.button("↻ ATNAUJINTI SWAP STATUSĄ" if lang=="LT" else "↻ REFRESH SWAP STATUS",key=f"swap_refresh_{year}_{month}",use_container_width=True):
            st.rerun()
    st.caption(
        "Swap statusas visada perskaitomas iš DB. Kito rezidento jau atidarytas langas gali rodyti seną būseną iki refresh/rerun."
        if lang=="LT" else
        "Swap status is always read from the database. Another resident's already-open page may show stale state until refresh/rerun."
    )
    currentp=db.load_schedule(year,month,"current")
    swap_perm=db.get_swap_permission_v2591(year,month) if currentp else {"allowed":False,"source":"not_open"}
    swap_create_allowed=bool(swap_perm.get("allowed",False))
    if currentp:
        src=str(swap_perm.get("source") or "")
        if swap_create_allowed and src=="window":
            dl=_parse_iso_dt(swap_perm.get("deadline")); txt=(dl.astimezone(ZoneInfo("Europe/Vilnius")).strftime("%Y-%m-%d %H:%M") if dl else "—")
            _workflow_card("APSIKEITIMŲ LANGAS ATIDARYTAS" if lang=="LT" else "SWAP WINDOW OPEN", (f"Naujus apsikeitimus galite kurti iki {txt}." if lang=="LT" else f"New swap requests may be created until {txt}."),"swap_open")
        elif swap_create_allowed and src=="late":
            exp=_parse_iso_dt(swap_perm.get("expires_at")); txt=(exp.astimezone(ZoneInfo("Europe/Vilnius")).strftime("%Y-%m-%d %H:%M") if exp else "—")
            _workflow_card("INDIVIDUALUS PAVĖLUOTAS LEIDIMAS" if lang=="LT" else "INDIVIDUAL LATE ACCESS", (f"Suteikta individuali prieiga iki {txt}; liko {swap_perm.get('remaining','—')} naujų prašymų." if lang=="LT" else f"Individual access is active until {txt}; {swap_perm.get('remaining','—')} new request(s) remain."),"swap_closed")
        else:
            state_name="FINAL" if src=="final" else ("TERMINAS PASIBAIGĖ" if src=="expired" else "NAUJI APSIKEITIMAI UŽDARYTI")
            _workflow_card(state_name if lang=="LT" else ("FINAL" if src=="final" else "NEW SWAPS CLOSED"), ("Naujų apsikeitimo prašymų kurti negalite. Jau egzistuojančius prašymus dar galima priimti / atmesti, kol operatorius užbaigs priežiūrą." if src!="final" and lang=="LT" else "Nauji apsikeitimai uždaryti." if lang=="LT" else "No new swap requests can be created. Existing requests may still be responded to until an operator completes oversight." if src!="final" else "The grafikas is FINAL; new swaps are closed."),"final" if src=="final" else "expired")
    if not currentp: st.info(tr("not_published"))
    elif not resident_ok: st.error(tr("bad_pin"))
    else:
        st.markdown(
            "### ↔ NORMALŪS APSIKEITIMAI"
            if lang=="LT" else
            "### ↔ NORMAL SWAPS"
        )
        st.caption(
            "Tai dvišalis request → accept/reject → seniūnės apply srautas. ONE-WAY emergency rescue yra atskiras uždarytas blokas žemiau ir niekada nėra automatiškai atidaromas po REQUEST SWAP."
            if lang=="LT" else
            "This is the bilateral request → accept/reject → senior apply flow. ONE-WAY emergency rescue is a separate collapsed section below and is never opened automatically after REQUEST SWAP."
        )
        result=refresh_result_payload(currentp,year,month)
        slots={s.idx:s for s in make_slots(year,month)}
        mine=[sid for sid,w in result.assignments.items() if w==active_user]
        theirs=[sid for sid,w in result.assignments.items() if w!=active_user]
        def sl(sid):
            s=slots[sid]
            return f"#{sid} · {s.day:02d} {WEEKDAYS[lang][s.weekday]} · {s.department} · {block_label(s.block)} · {result.assignments[sid]}"
        if mine and theirs:
            a,b=st.columns(2)
            with a:
                sa=st.selectbox(
                    tr("my_assignment"),mine,format_func=sl,key="swap_a"
                )
            with b:
                sb=st.selectbox(
                    tr("their_assignment"),theirs,format_func=sl,key="swap_b"
                )

            target_person=result.assignments[sb]

            # V2.5.80: same structured colored selection UI as Emergency Rescue.
            st.markdown(
                "#### Apsikeitimas"
                if lang=="LT" else
                "#### Swap"
            )
            _render_swap_people_line(active_user,target_person,"↔")
            sv1,sv2=st.columns(2)
            with sv1:
                _render_shift_tile(
                    "MANO PAMAINA"
                    if lang=="LT" else
                    "MY CURRENT SHIFT",
                    active_user,slots.get(sa),PERSON_COLORS.get(active_user)
                )
            with sv2:
                _render_shift_tile(
                    "KITO REZIDENTO PAMAINA"
                    if lang=="LT" else
                    "OTHER RESIDENT'S SHIFT",
                    target_person,slots.get(sb),PERSON_COLORS.get(target_person)
                )

            swap_people=people_for_stored_result(result,year,month)
            preview_ok,preview_reason,preview_stats,preview_needed=preview_swap(
                year,month,swap_people,result,sa,sb,backup_assignments=db.list_backups(year,month)
            )
            my_fp=preview_needed.get(active_user) if preview_ok else None
            their_fp=preview_needed.get(target_person) if preview_ok else None
            my_ack=True
            if not preview_ok:
                block_rows=((preview_stats or {}).get("global",{}) or {}).get("swap_hard_block_rows") or []
                if block_rows:
                    _render_swap_hard_block(preview_stats,preview_reason)
                else:
                    st.error(tr("swap_preview_invalid").format(reason=preview_reason))
            else:
                _render_impact_table(preview_stats,active_user,("Tavo swapo pasekmės" if lang=="LT" else "Your swap consequences"))
                if my_fp:
                    st.warning(tr("swap_48_warning"))
                    st.caption(tr("swap_48_only_exception"))
                    my_ack=st.checkbox(tr("swap_48_ack"),key=f"swapimpact_proposer_{sa}_{sb}")
                if their_fp:
                    st.info(tr("swap_48_other"))
                    _render_impact_table(preview_stats,target_person,("Kito rezidento pasekmės" if lang=="LT" else "Other resident consequences"))
            if st.button(tr("request_swap"),type="primary",disabled=(not preview_ok or not my_ack or not swap_create_allowed)):
                meta={"phase":"pending","impact_ack":{}}
                if my_fp and my_ack:
                    meta["impact_ack"][active_user]=str(my_fp)
                try:
                    inserted=db.create_swap_request(
                        year,month,sa,sb,active_user,target_person,
                        reason=_swap_meta_encode(meta)
                    )
                    saved=(inserted[0] if inserted else {})
                    email_ok,email_detail=send_swap_request_email(year,month,saved) if saved else (False,"request row missing")
                    request_msg=(
                        f"SWAP REQUEST #{saved.get('id','—')} išsaugotas. "
                        + ("El. laiškas gavėjui išsiųstas." if email_ok else f"DB išsaugota, bet email nepavyko: {email_detail}")
                        if lang=="LT" else
                        f"SWAP REQUEST #{saved.get('id','—')} saved. "
                        + ("Email notification sent." if email_ok else f"DB saved, but email failed: {email_detail}")
                    )
                    if email_ok:
                        st.success(request_msg)
                    else:
                        st.warning(request_msg)
                    # Deliberately NO st.rerun(): the request list below re-reads DB
                    # in the same Streamlit pass. This prevents scroll restoration
                    # from landing the user in the separate Emergency Rescue block.
                except Exception as exc:
                    if "SWAP_WINDOW_CLOSED" in str(exc):
                        st.warning("Naujų apsikeitimų langas uždarytas. Jei pavėlavote, kreipkitės į tvarkaraščio operatorių dėl individualaus leidimo." if lang=="LT" else "New swaps are closed. If you are late, ask a grafikas operator for individual late access.")
                    elif _is_swap_slot_conflict(exc):
                        st.warning(tr("swap_shift_busy"))
                    else:
                        st.error(tr("swap_preview_invalid").format(reason=("Nepavyko išsaugoti pasiūlymo." if lang=="LT" else "Could not save the offer.")))

        reqs=db.list_swap_requests(year,month,active_user)
        outgoing=[
            r for r in reqs
            if r["person_a"]==active_user
            and r["status"]=="pending"
            and _swap_meta_decode(r.get("reason")).get("kind") not in {"emergency_actual","emergency_rescue"}
        ]
        if outgoing:
            st.markdown(
                f"### {tr('my_outgoing_swaps')} · {len(outgoing)}"
            )
            for idx,r in enumerate(outgoing,start=1):
                with st.container(border=True):
                    _render_swap_request_card(r,idx,len(outgoing),slots,incoming=False)
                    if st.button(
                        tr("cancel_my_swap"),
                        key=f"cancel_swap_{r['id']}",
                        use_container_width=True
                    ):
                        try:
                            saved=db.cancel_swap_request(r["id"])
                            if saved.get("status")!="rejected":
                                raise RuntimeError(f"Unexpected saved status: {saved.get('status')}")
                            st.session_state["_swap_response_flash"]=(
                                "success",
                                ("Pasiūlymas atšauktas ir DB būsena patvirtinta: REJECTED."
                                 if lang=="LT" else
                                 "Offer cancelled; authoritative DB status confirmed: REJECTED.")
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error((f"Nepavyko atšaukti swapo: {exc}" if lang=="LT" else f"Could not cancel swap: {exc}"))
        incoming=[
            r for r in reqs
            if r["person_b"]==active_user
            and r["status"]=="pending"
            and _swap_meta_decode(r.get("reason")).get("kind") not in {"emergency_actual","emergency_rescue"}
        ]
        st.markdown(f"### {tr('incoming')} · {len(incoming)}")
        if not incoming:
            st.caption("Naujų apsikeitimo prašymų nėra." if lang=="LT" else "No new swap requests.")
        for idx,r in enumerate(incoming,start=1):
            with st.container(border=True):
                _render_swap_request_card(r,idx,len(incoming),slots,incoming=True)
                fresh=refresh_result_payload(db.load_schedule(year,month,"current"),year,month)
                stale=(fresh.assignments.get(r["slot_a"])!=r["person_a"] or fresh.assignments.get(r["slot_b"])!=r["person_b"])
                meta=_swap_meta_decode(r.get("reason")); acks=_impact_acks(meta)
                pv_ok,pv_reason,pv_stats,pv_needed=(False,"stale",None,{}) if stale else preview_swap(
                    year,month,people_for_stored_result(fresh,year,month),fresh,r["slot_a"],r["slot_b"],backup_assignments=db.list_backups(year,month)
                )
                proposer_fp=pv_needed.get(r["person_a"]) if pv_ok else None
                proposer_missing=bool(proposer_fp and acks.get(r["person_a"])!=proposer_fp)
                target_fp=pv_needed.get(active_user) if pv_ok else None
                target_ack=True
                if stale:
                    st.error(
                        "Šis requestas paseno, nes ACTUAL grafikas nuo jo sukūrimo jau pasikeitė."
                        if lang=="LT" else
                        "This request is stale because ACTUAL changed after it was created."
                    )
                elif not pv_ok:
                    block_rows=((pv_stats or {}).get("global",{}) or {}).get("swap_hard_block_rows") or []
                    if block_rows:
                        _render_swap_hard_block(pv_stats,pv_reason)
                    else:
                        st.error(tr("swap_preview_invalid").format(reason=pv_reason))
                elif proposer_missing:
                    st.warning(tr("swap_48_reaccept"))
                else:
                    _render_impact_table(pv_stats,active_user,("Tavo swapo pasekmės" if lang=="LT" else "Your swap consequences"))
                    if target_fp:
                        st.warning(tr("swap_48_warning"))
                        st.caption(tr("swap_48_only_exception"))
                        target_ack=st.checkbox(tr("swap_48_ack"),key=f"swapimpact_target_{r['id']}")
                c1,c2=st.columns(2)
                with c1:
                    if st.button(tr("accept"),key=f"ac{r['id']}",use_container_width=True,disabled=(stale or not pv_ok or proposer_missing or not target_ack)):
                        if target_fp and target_ack:
                            meta.setdefault("impact_ack",{})[active_user]=str(target_fp)
                        meta["phase"]="accepted_pending_senior_apply"
                        try:
                            saved=db.respond_swap_request_v2578(
                                r["id"],"accept",_swap_meta_encode(meta)
                            )
                            if saved.get("status")!="approved":
                                raise RuntimeError(f"Unexpected saved status: {saved.get('status')}")
                            st.session_state["_swap_response_flash"]=(
                                "success",
                                ("SWAP PRIIMTAS — DB būsena APPROVED. Dabar laukia seniūnės galutinio pritaikymo."
                                 if lang=="LT" else
                                 "SWAP ACCEPTED — authoritative DB status APPROVED. It now awaits senior application.")
                            )
                            st.rerun()
                        except Exception as exc:
                            if _is_swap_slot_conflict(exc):
                                st.warning(tr("swap_shift_busy"))
                            else:
                                st.error((f"Nepavyko išsaugoti ACCEPT: {exc}" if lang=="LT" else f"Could not save ACCEPT: {exc}"))
                with c2:
                    if st.button(tr("reject"),key=f"rj{r['id']}",use_container_width=True):
                        try:
                            saved=db.respond_swap_request_v2578(r["id"],"reject","declined")
                            if saved.get("status")!="rejected":
                                raise RuntimeError(f"Unexpected saved status: {saved.get('status')}")
                            st.session_state["_swap_response_flash"]=(
                                "success",
                                ("SWAP ATMESTAS — DB būsena patvirtinta: REJECTED."
                                 if lang=="LT" else
                                 "SWAP REJECTED — authoritative DB status confirmed: REJECTED.")
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error((f"Nepavyko išsaugoti REJECT: {exc}" if lang=="LT" else f"Could not save REJECT: {exc}"))
        # V2.5.148: one-way shift handoff registry lives in the same Swap window,
        # but is deliberately an audit/registration layer. It never mutates ACTUAL by itself.
        st.divider()
        st.markdown("### → Atiduoti pamainą" if lang=="LT" else "### → Give away a shift")
        st.caption(
            "Čia registruojamas vienpusis pamainos atidavimas. „Noriu atiduoti“ pažymi pasiūlymą, o „Atidaviau pamainą“ užfiksuoja, kam ją perdavėte. Pats įrašas ACTUAL grafiko automatiškai nekeičia — faktinis grafikas turi būti pakeistas per patvirtintą operacinį procesą."
            if lang=="LT" else
            "This is the one-way shift handoff registry. 'Want to give away' records an offer; 'Shift handed off' records the recipient. The registry never changes ACTUAL automatically; the actual schedule must be updated through an approved operational process."
        )
        giveaway_rows=[]
        giveaway_error=None
        try:
            giveaway_rows=db.list_shift_giveaway_records_v25148(year,month)
        except Exception as exc:
            giveaway_error=exc
            if advanced_mode:
                st.caption(f"Giveaway registry DB: {type(exc).__name__}: {exc}")
        if giveaway_error:
            st.info(
                "Atidavimo registras bus aktyvus pritaikius V2.5.148 Supabase migraciją."
                if lang=="LT" else
                "The handoff registry becomes active after applying the V2.5.148 Supabase migration."
            )
        else:
            future_mine=[sid for sid in mine if slots.get(sid)]
            if future_mine:
                g1,g2=st.columns(2)
                with g1:
                    give_slot=st.selectbox(
                        "Mano pamaina" if lang=="LT" else "My shift",
                        future_mine,format_func=sl,key=f"giveaway_slot_{year}_{month}"
                    )
                with g2:
                    give_kind=st.radio(
                        "Registruoti" if lang=="LT" else "Register",
                        ["offer","handed_off"],horizontal=True,
                        format_func=lambda x:("Noriu atiduoti" if x=="offer" else "Atidaviau pamainą") if lang=="LT" else ("Want to give away" if x=="offer" else "Shift handed off"),
                        key=f"giveaway_kind_{year}_{month}"
                    )
                recipient=None
                if give_kind=="handed_off":
                    recipient=st.selectbox(
                        "Kam atidaviau" if lang=="LT" else "Handed off to",
                        [p["initials"] for p in DEFAULT_PEOPLE if p["initials"]!=active_user],
                        format_func=lambda x:f"{x} — {_person_name(x)}",
                        key=f"giveaway_recipient_{year}_{month}"
                    )
                    st.markdown(badge(recipient,include_name=True),unsafe_allow_html=True)
                give_note=st.text_input(
                    "Pastaba (nebūtina)" if lang=="LT" else "Note (optional)",
                    key=f"giveaway_note_{year}_{month}"
                )
                if st.button(
                    "REGISTRUOTI" if lang=="LT" else "REGISTER",
                    type="primary",use_container_width=True,key=f"register_giveaway_{year}_{month}"
                ):
                    try:
                        db.create_shift_giveaway_record_v25148(
                            year,month,active_user,int(give_slot),give_kind,recipient,give_note
                        )
                        st.session_state["_swap_response_flash"]=(
                            "success",
                            "Pamainos atidavimo įrašas užregistruotas." if lang=="LT" else "Shift handoff record registered."
                        )
                        st.rerun()
                    except Exception as exc:
                        st.error(
                            ("Nepavyko užregistruoti. Patikrinkite, ar pamaina vis dar priklauso jums ir ar nėra aktyvaus įrašo tai pačiai pamainai."
                             if lang=="LT" else
                             "Could not register. Check that the shift is still yours and has no active registry entry.")
                        )
                        if advanced_mode:
                            st.caption(str(exc))
            else:
                st.caption("Šį mėnesį neturite pamainos, kurią būtų galima registruoti." if lang=="LT" else "You have no shift available for registration this month.")

            st.markdown("#### Atidavimo registras" if lang=="LT" else "#### Handoff registry")
            st.caption(
                "SP ir ŠR mato visos grupės įrašus. Kiekvienas kitas rezidentas mato tik įrašus, kuriuose pats yra atiduodantis arba gavėjas."
                if lang=="LT" else
                "SP and ŠR see the group registry. Every other resident sees only records where they are the donor or recipient."
            )
            if not giveaway_rows:
                st.caption("Įrašų dar nėra." if lang=="LT" else "No records yet.")
            for gr in giveaway_rows:
                donor=str(gr.get("donor_initials") or "")
                rec=str(gr.get("recipient_initials") or "")
                kind=str(gr.get("record_type") or "offer")
                sid=int(gr.get("slot_id") or -1)
                sslot=slots.get(sid)
                created=_parse_iso_dt(gr.get("registered_at"))
                if created:
                    created=created.astimezone(ZoneInfo("Europe/Vilnius"))
                    created_txt=created.strftime("%Y-%m-%d %H:%M")
                else:
                    created_txt=str(gr.get("registered_at") or "—")
                with st.container(border=True):
                    top1,top2=st.columns([3,1])
                    with top1:
                        st.markdown(badge(donor,include_name=True),unsafe_allow_html=True)
                        if rec:
                            st.markdown(
                                '<div style="font-size:1.2rem;font-weight:800;margin:2px 0 6px 0;">→</div>'+badge(rec,include_name=True),
                                unsafe_allow_html=True,
                            )
                    with top2:
                        st.caption("Registruota" if lang=="LT" else "Registered")
                        st.markdown(f"**{html.escape(created_txt)}**")
                    st.markdown(
                        f"**{('Noriu atiduoti' if kind=='offer' else 'Atidaviau pamainą') if lang=='LT' else ('Want to give away' if kind=='offer' else 'Shift handed off')}** · {html.escape(_swap_shift_text(sslot))}"
                    )
                    if gr.get("note"):
                        st.caption(str(gr.get("note")))
                    if str(gr.get("status") or "active")!="cancelled" and (donor==active_user or active_user in (SENIOR_INITIALS,RESEARCHER_INITIALS)):
                        if st.button(
                            "ATŠAUKTI ĮRAŠĄ" if lang=="LT" else "CANCEL RECORD",
                            key=f"cancel_giveaway_{gr.get('id')}",use_container_width=True
                        ):
                            try:
                                db.cancel_shift_giveaway_record_v25148(int(gr.get("id")))
                                st.rerun()
                            except Exception as exc:
                                st.error(str(exc))

        st.divider(); st.markdown(f"### {tr('backup_swap_title')}"); st.caption(tr("backup_swap_help"))
        all_backups=[r for r in db.list_backups(year,month) if not r.get("activated_at") and not r.get("completed_at")]
        slot_map_b={s.idx:s for s in make_slots(year,month)}
        my_b=[r for r in all_backups if (r.get("actual_backup") or r.get("planned_backup"))==active_user]
        other_b=[r for r in all_backups if (r.get("actual_backup") or r.get("planned_backup"))!=active_user]
        def blabel(r):
            s=slot_map_b.get(int(r["covered_slot"])); who=r.get("actual_backup") or r.get("planned_backup")
            return f"{s.day:02d} {WEEKDAYS[lang][s.weekday]} · {block_label(s.block)} · {who}" if s else str(r["covered_slot"])
        if my_b and other_b:
            ba,bb=st.columns(2)
            with ba:
                my_br=st.selectbox(
                    tr("my_backup_duty"),my_b,format_func=blabel,key="backup_swap_my"
                )
            with bb:
                other_br=st.selectbox(
                    tr("their_backup_duty"),other_b,format_func=blabel,key="backup_swap_other"
                )

            target=other_br.get("actual_backup") or other_br.get("planned_backup")
            my_backup_person=my_br.get("actual_backup") or my_br.get("planned_backup") or active_user
            my_backup_slot=slot_map_b.get(int(my_br["covered_slot"]))
            other_backup_slot=slot_map_b.get(int(other_br["covered_slot"]))

            # V2.5.80: same colored structured visual language as normal swaps/rescue.
            st.markdown(
                "#### Dublių apsikeitimas"
                if lang=="LT" else
                "#### Backup swap"
            )
            _render_swap_people_line(my_backup_person,target,"↔")
            bv1,bv2=st.columns(2)
            with bv1:
                _render_shift_tile(
                    "MANO DUBLIO VIETA"
                    if lang=="LT" else
                    "MY BACKUP DUTY",
                    my_backup_person,my_backup_slot,PERSON_COLORS.get(my_backup_person)
                )
                covered_a=str(my_br.get("covered_person") or "")
                if covered_a:
                    st.markdown(
                        ("**DENGIAMAS REZIDENTAS:** " if lang=="LT" else "**RESIDENT COVERED:** ")
                        + badge(covered_a,include_name=True),
                        unsafe_allow_html=True,
                    )
            with bv2:
                _render_shift_tile(
                    "KITO REZIDENTO DUBLIO VIETA"
                    if lang=="LT" else
                    "OTHER RESIDENT'S BACKUP DUTY",
                    target,other_backup_slot,PERSON_COLORS.get(target)
                )
                covered_b=str(other_br.get("covered_person") or "")
                if covered_b:
                    st.markdown(
                        ("**DENGIAMAS REZIDENTAS:** " if lang=="LT" else "**RESIDENT COVERED:** ")
                        + badge(covered_b,include_name=True),
                        unsafe_allow_html=True,
                    )

            if st.button(tr("request_backup_swap"),key="request_backup_swap_btn",use_container_width=True,disabled=(not swap_create_allowed)):
                try:
                    inserted=db.create_backup_swap_request(
                        year,month,active_user,int(my_br["covered_slot"]),
                        target,int(other_br["covered_slot"])
                    )
                    saved=(inserted[0] if inserted else {})
                    email_ok,email_detail=send_backup_swap_request_email(year,month,saved) if saved else (False,"request row missing")
                    backup_msg=(
                        f"Dublio swap request #{saved.get('id','—')} išsaugotas. "
                        + ("Email gavėjui išsiųstas." if email_ok else f"DB išsaugota, bet email nepavyko: {email_detail}")
                        if lang=="LT" else
                        f"Backup swap request #{saved.get('id','—')} saved. "
                        + ("Email sent." if email_ok else f"DB saved, but email failed: {email_detail}")
                    )
                    if email_ok:
                        st.success(backup_msg)
                    else:
                        st.warning(backup_msg)
                    # Same no-rerun rule as normal swaps: keep the user in the swap UI.
                except Exception as exc:
                    if _is_swap_slot_conflict(exc): st.warning(tr("backup_swap_shift_busy"))
                    else: st.error(tr("backup_swap_invalid"))
        breqs=db.list_backup_swap_requests(year,month,None if is_seniune_account else active_user)
        backup_outgoing=[r for r in breqs if r.get("requester")==active_user and r.get("status")=="pending"]
        if backup_outgoing:
            st.markdown(f"#### {tr('my_outgoing_swaps')} · {tr('backup_swap_title')} · {len(backup_outgoing)}")
            for idx,r in enumerate(backup_outgoing,start=1):
                with st.container(border=True):
                    st.markdown(
                        f"**{'DUBLIO PASIŪLYMAS' if lang=='LT' else 'BACKUP OFFER'} {idx}/{len(backup_outgoing)} · DB #{r['id']}**"
                    )
                    _render_swap_people_line(r["requester"],r["target"],"→")
                    st.caption(
                        f"{blabel({'covered_slot':r['requester_slot'],'actual_backup':r['requester']})} "
                        f"↔ {blabel({'covered_slot':r['target_slot'],'actual_backup':r['target']})}"
                    )
                    if st.button(tr("cancel_my_swap"),key=f"cancel_backup_swap_{r['id']}",use_container_width=True):
                        try:
                            db.cancel_backup_swap_request(r["id"])
                            st.session_state["_swap_response_flash"]=(
                                "success",
                                ("Backup swapo pasiūlymas atšauktas."
                                 if lang=="LT" else
                                 "Backup swap offer cancelled.")
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error((f"Nepavyko atšaukti backup swapo: {exc}" if lang=="LT" else f"Could not cancel backup swap: {exc}"))
        backup_incoming=[x for x in breqs if x["target"]==active_user and x["status"]=="pending" and not x.get("participant_accepted_at")]
        if backup_incoming:
            st.markdown(
                f"#### {'GAUTI DUBLIŲ REQUESTAI' if lang=='LT' else 'INCOMING BACKUP REQUESTS'} · {len(backup_incoming)}"
            )
        for idx,r in enumerate(backup_incoming,start=1):
            with st.container(border=True):
                st.markdown(
                    f"**{'GAUTAS DUBLIO REQUESTAS' if lang=='LT' else 'INCOMING BACKUP REQUEST'} {idx}/{len(backup_incoming)} · DB #{r['id']}**"
                )
                _render_swap_people_line(r["requester"],r["target"],"→")
                st.caption(
                    f"{blabel({'covered_slot':r['requester_slot'],'actual_backup':r['requester']})} "
                    f"↔ {blabel({'covered_slot':r['target_slot'],'actual_backup':r['target']})}"
                )
                bc1,bc2=st.columns(2)
                with bc1:
                    if st.button(tr("accept"),key=f"bac{r['id']}",use_container_width=True):
                        fresh=refresh_result_payload(db.load_schedule(year,month,"current"),year,month); smap_b={s.idx:s for s in make_slots(year,month)}
                        s_a=smap_b.get(int(r["requester_slot"])); s_b=smap_b.get(int(r["target_slot"])); people_now=people_for_stored_result(fresh,year,month)
                        elig_a=_eligible_backup_candidates(year,month,fresh,s_a,people_now) if s_a else []; elig_b=_eligible_backup_candidates(year,month,fresh,s_b,people_now) if s_b else []
                        if r["target"] not in elig_a or r["requester"] not in elig_b:
                            st.error(tr("backup_swap_invalid"))
                        else:
                            try:
                                db.accept_backup_swap_participant_v25111(r["id"])
                                st.session_state["_swap_response_flash"]=(
                                    "success",
                                    ("Abu rezidentai sutiko dėl dublio swapo. Jis DAR NEPRITAIKYTAS — laukia SP galutinio patvirtinimo."
                                     if lang=="LT" else
                                     "Both residents consented to the backup swap. It is NOT applied yet — awaiting SP final approval.")
                                )
                                st.rerun()
                            except Exception:
                                st.error(tr("backup_swap_invalid"))
                with bc2:
                    if st.button(tr("reject"),key=f"bar{r['id']}",use_container_width=True):
                        try:
                            db.reject_backup_swap_request(r["id"])
                            st.session_state["_swap_response_flash"]=(
                                "success",
                                ("Backup swapas atmestas." if lang=="LT" else "Backup swap rejected.")
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error((f"Nepavyko atmesti backup swapo: {exc}" if lang=="LT" else f"Could not reject backup swap: {exc}"))
        if is_seniune_account:
            _sr_backup_waiting=[r for r in breqs if r.get("status")=="pending" and r.get("participant_accepted_at") and not r.get("senior_decision")]
            if _sr_backup_waiting:
                st.markdown("#### SP GALUTINIS DUBLIŲ SWAPŲ PATVIRTINIMAS" if lang=="LT" else "#### SP FINAL BACKUP-SWAP APPROVAL")
                st.caption("Abu rezidentai jau sutiko. ACTUAL dar nepakeistas. Tik tavo APPROVE pritaiko swapą." if lang=="LT" else "Both residents already consented. ACTUAL is still unchanged. Only your APPROVE applies the swap.")
                for r in _sr_backup_waiting:
                    with st.container(border=True):
                        st.markdown(f"**DB #{r['id']} · {r['requester']} ↔ {r['target']}**")
                        _render_swap_people_line(r["requester"],r["target"],"↔")
                        ac,dc=st.columns(2)
                        with ac:
                            if st.button("SP APPROVE + APPLY",key=f"sr_backup_approve_{r['id']}",use_container_width=True,type="primary"):
                                try:
                                    db.approve_backup_swap_by_sr_v25111(r["id"])
                                    persist_actual_satisfaction(year,month)
                                    refresh_calendar_subscription_feeds([r["requester"],r["target"]])
                                    st.session_state["_swap_response_flash"]=("success","SP patvirtino dublio swapą — ACTUAL atnaujintas." if lang=="LT" else "SP approved the backup swap — ACTUAL updated.")
                                    st.rerun()
                                except Exception as exc: st.error(str(exc))
                        with dc:
                            if st.button("SP DECLINE",key=f"sr_backup_decline_{r['id']}",use_container_width=True):
                                try:
                                    db.reject_backup_swap_by_sr_v25111(r["id"])
                                    st.session_state["_swap_response_flash"]=("success","SP atmetė dublio swapą." if lang=="LT" else "SP declined the backup swap.")
                                    st.rerun()
                                except Exception as exc: st.error(str(exc))

        if breqs:
            st.markdown("#### Dublių apsikeitimų istorija" if lang=="LT" else "#### Backup swap history")
            for idx,r in enumerate(breqs,start=1):
                with st.container(border=True):
                    applied=bool(r.get("status")=="accepted")
                    st.markdown(f"**DUBLIO SWAP #{idx} · DB #{r.get('id')} · {str(r.get('status','')).upper()}**")
                    _render_swap_people_line(str(r.get("requester") or ""),str(r.get("target") or ""),"↔")
                    st.caption(
                        ("Jei statusas ACCEPTED, DELETE kartu bandys saugiai grąžinti ankstesnius dublio turėtojus." if lang=="LT" else
                         "If status is ACCEPTED, DELETE will also safely restore the previous backup holders.")
                        if applied else
                        ("DELETE pašalins šį request/history įrašą; ACTUAL backup planas nuo jo dar nepakeistas." if lang=="LT" else
                         "DELETE removes this request/history row; it has not changed the ACTUAL backup plan.")
                    )
                    if _delete_confirm(f"backup_swap_{r['id']}",applied=applied):
                        try:
                            saved=db.delete_backup_swap_v2586(int(r["id"]))
                            st.session_state["_swap_response_flash"]=(
                                "success",
                                ("Dublio swapas ištrintas"+(" ir ankstesnis backup planas atkurtas." if saved.get("undone_actual") else ".")
                                 if lang=="LT" else
                                 "Backup swap deleted"+(" and previous backup holders restored." if saved.get("undone_actual") else "."))
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error(("DELETE nepavyko: " if lang=="LT" else "DELETE failed: ")+str(exc))
        hist=db.list_swap_requests(year,month,None if is_seniune_account else active_user)
        if is_seniune_account:
            pending_apply=[]
            for r in hist:
                if r.get("status")!="approved": continue
                meta=_swap_meta_decode(r.get("reason"))
                if meta.get("phase")=="accepted_pending_senior_apply" or r.get("reason")=="accepted_pending_senior_apply":
                    pending_apply.append(r)
            for r in pending_apply:
                meta=_swap_meta_decode(r.get("reason")); acks=_impact_acks(meta)
                st.info(f"{r['person_a']} ↔ {r['person_b']} · #{r['slot_a']} ↔ #{r['slot_b']}")
                if acks:
                    st.caption(("Swapo pasekmių ACK: " if lang=="LT" else "Swap consequence ACK: ")+", ".join(sorted(acks)))
                _sra,_srd=st.columns(2)
                with _sra:
                    _sr_apply=st.button(tr("finalize_swap"),key=f"finalize_{r['id']}",use_container_width=True,type="primary")
                with _srd:
                    _sr_decline=st.button("SP — DECLINE",key=f"decline_{r['id']}",use_container_width=True)
                if _sr_decline:
                    try:
                        db.mark_normal_swap_sr_decision_v25111(r["id"],"declined")
                        st.session_state["_swap_response_flash"]=("success","SP atmetė swapą — ACTUAL nepakeistas." if lang=="LT" else "SP declined the swap — ACTUAL unchanged.")
                        st.rerun()
                    except Exception as exc: st.error(str(exc))
                if _sr_apply:
                    fresh=refresh_result_payload(db.load_schedule(year,month,"current"),year,month)
                    if fresh.assignments.get(r["slot_a"])!=r["person_a"] or fresh.assignments.get(r["slot_b"])!=r["person_b"]:
                        db.update_swap_request(r["id"],"rejected","stale"); st.error(tr("hard_reject")); st.rerun()
                    pv_ok,pv_reason,pv_stats,pv_needed=preview_swap(
                        year,month,people_for_stored_result(fresh,year,month),fresh,r["slot_a"],r["slot_b"],backup_assignments=db.list_backups(year,month)
                    )
                    if not pv_ok:
                        db.update_swap_request(r["id"],"rejected",pv_reason)
                        block_rows=((pv_stats or {}).get("global",{}) or {}).get("swap_hard_block_rows") or []
                        if block_rows:
                            _render_swap_hard_block(pv_stats,pv_reason)
                        else:
                            st.error(
                                ("Swapo pritaikyti nepavyko: " if lang=="LT" else "Could not apply swap: ")
                                + str(pv_reason)
                            )
                        st.stop()
                    missing=[who for who,fp in pv_needed.items() if acks.get(who)!=fp]
                    if missing:
                        who=missing[0]
                        db.update_swap_request(r["id"],"rejected",f"impact_ack_missing:{who}")
                        st.error(tr("swap_48_reaccept")); st.rerun()
                    ok,reason,_=attempt_swap(
                        year,month,people_for_stored_result(fresh,year,month),fresh,r["slot_a"],r["slot_b"],
                        backup_assignments=db.list_backups(year,month),acknowledged_fingerprints=acks
                    )
                    if ok:
                        # Bilateral voluntary swap changes ACTUAL only. Consequence ACKs are
                        # fingerprinted so a changed preview forces fresh resident consent.
                        if acks:
                            audit=list((fresh.stats.get("global",{}) or {}).get("swap_ack_audit") or [])
                            audit.append({"swap_id":int(r["id"]),"people":dict(acks),"applied_at":datetime.now(timezone.utc).isoformat()})
                            fresh.stats["global"]["swap_ack_audit"]=audit
                        db.save_current(year,month,serialize_result(fresh))
                        sync_backup_plan(year,month,fresh)
                        persist_actual_satisfaction(year,month)
                        refresh_calendar_subscription_feeds([r["person_a"],r["person_b"]])
                        meta["phase"]="applied"
                        db.update_swap_request(r["id"],"approved",_swap_meta_encode(meta))
                        try: db.mark_normal_swap_sr_decision_v25111(r["id"],"approved")
                        except Exception: pass
                        st.success(tr("swap_applied")); st.rerun()
                    else:
                        db.update_swap_request(r["id"],"rejected",reason)
                        st.error(
                            ("Swapo pritaikyti nepavyko: " if lang=="LT" else "Could not apply swap: ")
                            + str(reason)
                        )
                        st.stop()
        regular_hist=[r for r in hist if _swap_meta_decode(r.get("reason")).get("kind") not in {"emergency_actual","emergency_rescue"}]
        if regular_hist:
            smap={"pending":tr("pending"),"approved":tr("approved"),"rejected":tr("rejected_status")}
            st.markdown(f"### {tr('history')}")
            for idx,r in enumerate(regular_hist,start=1):
                meta=_swap_meta_decode(r.get("reason"))
                applied=bool(meta.get("phase")=="applied")
                with st.container(border=True):
                    st.markdown(f"**SWAP #{idx} · DB #{r.get('id')} · {smap.get(r.get('status'),r.get('status'))}**")
                    _render_swap_people_line(str(r.get("person_a") or ""),str(r.get("person_b") or ""),"↔")
                    sa=slots.get(int(r.get("slot_a") or -1)); sb=slots.get(int(r.get("slot_b") or -1))
                    hc1,hc2=st.columns(2)
                    with hc1: _render_shift_tile("A",str(r.get("person_a") or ""),sa,PERSON_COLORS.get(str(r.get("person_a") or "")))
                    with hc2: _render_shift_tile("B",str(r.get("person_b") or ""),sb,PERSON_COLORS.get(str(r.get("person_b") or "")))
                    st.caption(
                        ("Šis swapas jau pritaikytas ACTUAL. DELETE bandys atlikti UNDO tik jei abu slotai po to nebuvo pakeisti dar kartą." if lang=="LT" else
                         "This swap is already applied to ACTUAL. DELETE will UNDO it only if neither slot changed again afterwards.")
                        if applied else
                        ("Šis įrašas ACTUAL dar nepakeitė; DELETE pašalins request/history įrašą." if lang=="LT" else
                         "This row has not changed ACTUAL; DELETE removes the request/history row.")
                    )
                    if _delete_confirm(f"normal_swap_{r['id']}",applied=applied):
                        try:
                            saved=_delete_swap_row(r,year,month)
                            st.session_state["_swap_response_flash"]=(
                                "success",
                                ("Swapas ištrintas"+(" ir ACTUAL grąžintas į būseną prieš šį swapą." if saved.get("undone_actual") else ".")
                                 if lang=="LT" else
                                 "Swap deleted"+(" and ACTUAL restored to its pre-swap state." if saved.get("undone_actual") else "."))
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error(("DELETE / UNDO nepavyko: " if lang=="LT" else "DELETE / UNDO failed: ")+str(exc))

        # V2.5.81 — always-visible EMERGENCY RESCUE operational panel.
        # The logged-in resident is pulled from their own lower-priority optional
        # post into an overlapping critical SPS post. The source becomes vacant;
        # SYSTEM fairness remains frozen.
        st.divider()
        with st.container(border=True):
            st.markdown(
                """
                <div style="display:flex;align-items:center;gap:16px;margin:2px 0 10px 0;">
                    <span style="font-size:3.1rem;line-height:1;">🚨</span>
                    <div>
                        <div style="font-size:1.55rem;font-weight:900;letter-spacing:.025em;">EMERGENCY RESCUE</div>
                        <div style="font-size:.88rem;opacity:.72;font-weight:650;">CURRENT LOCATION → MOVING TO → RESCUED PERSON</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.info(
                "Naudok, kai realiai dirbdamas savo poste esi skubiai perkeltas į svarbesnį SPS RO / SPS UG postą. "
                "CURRENT LOCATION lieka tuščias; RESCUED PERSON atleidžiamas nuo kritinio posto. "
                "Keičiamas ACTUAL grafikas ir iškart perskaičiuojama ACTUAL fairness statistika; SYSTEM publikavimo baseline lieka užšaldytas auditui. Jokio future catch-up / future catch-up nėra."
                if lang=="LT" else
                "Use this when, while working your assigned post, you are urgently moved into a more important SPS RO / SPS UG post. "
                "CURRENT LOCATION becomes vacant; the RESCUED PERSON is released from the critical post. "
                "ACTUAL changes and ACTUAL fairness statistics are recalculated immediately; the publication-time SYSTEM baseline stays frozen for audit. There is no future catch-up or future catch-up."
            )

            rescue_current=refresh_result_payload(
                db.load_schedule(year,month,"current"),year,month
            )
            rescue_slots={s.idx:s for s in make_slots(year,month)}

            # The constitutional workflow is self-recording: the resident who was
            # actually moved records the rescue from their own account.
            mover=active_user
            source_options=[]
            for sid,who in (rescue_current.assignments or {}).items():
                sl=rescue_slots.get(int(sid))
                if who!=mover or sl is None:
                    continue
                if not is_emergency_lower_priority_donor_slot(sl):
                    continue
                target_exists=any(
                    t.idx!=sl.idx
                    and is_emergency_critical_slot(t)
                    and t.day==sl.day
                    and t.block==sl.block
                    and rescue_current.assignments.get(t.idx)
                    and rescue_current.assignments.get(t.idx)!=mover
                    for t in rescue_slots.values()
                )
                if target_exists:
                    source_options.append(sl.idx)

            source_options=sorted(
                source_options,
                key=lambda sid:(
                    rescue_slots[sid].day,
                    {"AM":0,"PM":1,"FULL":2}.get(rescue_slots[sid].block,9),
                    rescue_slots[sid].department,
                    sid,
                )
            )

            if not source_options:
                st.info(
                    "Šiuo metu tavo ACTUAL grafike nėra tinkamos žemesnio prioriteto pamainos, kurią tuo pačiu laiku būtų galima perkelti į kritinį SPS RO / SPS UG postą."
                    if lang=="LT" else
                    "Your ACTUAL grafikas currently has no eligible lower-priority assignment that can be moved at the same time into a critical SPS RO / SPS UG post."
                )
            else:
                source_sid=st.selectbox(
                    "CURRENT LOCATION — iš kur mane perkelia"
                    if lang=="LT" else
                    "CURRENT LOCATION — where I am being moved from",
                    source_options,
                    format_func=lambda sid:_swap_shift_text(rescue_slots[sid]),
                    key="emergency_rescue_source",
                )
                source_slot=rescue_slots[source_sid]

                target_options=[
                    t.idx for t in rescue_slots.values()
                    if t.idx!=source_sid
                    and is_emergency_critical_slot(t)
                    and t.day==source_slot.day
                    and t.block==source_slot.block
                    and rescue_current.assignments.get(t.idx)
                    and rescue_current.assignments.get(t.idx)!=mover
                ]
                target_options=sorted(
                    target_options,
                    key=lambda sid:(
                        rescue_slots[sid].department,
                        rescue_current.assignments.get(sid,""),
                        sid,
                    )
                )

                if not target_options:
                    st.info(
                        "Šiai CURRENT LOCATION pamainai nėra to paties laiko kritinio SPS targeto."
                        if lang=="LT" else
                        "There is no same-time critical SPS target for this CURRENT LOCATION."
                    )
                else:
                    target_sid=st.selectbox(
                        "MOVING TO — į kurį svarbesnį postą mane perkelia"
                        if lang=="LT" else
                        "MOVING TO — critical post I am moving to",
                        target_options,
                        format_func=lambda sid:(
                            f"{_swap_shift_text(rescue_slots[sid])} · "
                            f"RESCUED: {rescue_current.assignments.get(sid,'—')}"
                        ),
                        key="emergency_rescue_target",
                    )
                    target_slot=rescue_slots[target_sid]
                    rescued_person=str(rescue_current.assignments.get(target_sid) or "")

                    st.markdown("#### Emergency Rescue" if lang=="LT" else "#### Emergency Rescue")
                    _render_swap_people_line(mover,rescued_person,"→")
                    rc1,rc2=st.columns(2)
                    with rc1:
                        _render_shift_tile(
                            "CURRENT LOCATION — BUS PALIKTA TUŠČIA"
                            if lang=="LT" else
                            "CURRENT LOCATION — WILL BECOME VACANT",
                            mover,source_slot,PERSON_COLORS.get(mover)
                        )
                    with rc2:
                        _render_shift_tile(
                            "MOVING TO — KRITINIS POSTAS"
                            if lang=="LT" else
                            "MOVING TO — CRITICAL POST",
                            mover,target_slot,PERSON_COLORS.get(mover)
                        )
                    st.markdown(
                        (
                            '<div style="margin:12px 0;padding:12px 14px;border-radius:14px;'
                            'border:2px dashed #777;background:rgba(127,127,127,.08);">'
                            '<b>RESCUED PERSON:</b> '
                            + badge(rescued_person,include_name=True)
                            + '<br><span style="opacity:.82;">'
                            + html.escape(
                                "Šis žmogus atleidžiamas nuo pasirinkto kritinio posto ir NĖRA perkeliamas į tavo CURRENT LOCATION."
                                if lang=="LT" else
                                "This person is released from the selected critical post and is NOT moved to your CURRENT LOCATION."
                            )
                            + '</span></div>'
                        ),
                        unsafe_allow_html=True,
                    )

                    rescue_note=st.text_input(
                        "Trumpa operational pastaba"
                        if lang=="LT" else
                        "Short operational note",
                        key="emergency_rescue_note",
                    )
                    rescue_confirm=st.checkbox(
                        (
                            "PATVIRTINU: tai realiai įvykęs ONE-WAY emergency rescue. "
                            "Aš pereinu iš CURRENT LOCATION į MOVING TO; mano senas optional postas lieka tuščias; "
                            f"{rescued_person} yra rescued ir neina į mano seną vietą."
                        )
                        if lang=="LT" else
                        (
                            "I CONFIRM: this is an already-occurred ONE-WAY emergency rescue. "
                            "I move from CURRENT LOCATION to MOVING TO; my old optional post becomes vacant; "
                            f"{rescued_person} is rescued and does not move to my old post."
                        ),
                        key=f"emergency_rescue_confirm_{source_sid}_{target_sid}",
                    )

                    if st.button(
                        "🚨 ĮRAŠYTI ONE-WAY RESCUE Į ACTUAL"
                        if lang=="LT" else
                        "🚨 RECORD ONE-WAY RESCUE IN ACTUAL",
                        type="primary",
                        use_container_width=True,
                        disabled=not rescue_confirm,
                        key="emergency_rescue_apply",
                    ):
                        fresh_rescue=refresh_result_payload(
                            db.load_schedule(year,month,"current"),year,month
                        )
                        if (
                            fresh_rescue.assignments.get(source_sid)!=mover
                            or fresh_rescue.assignments.get(target_sid)!=rescued_person
                        ):
                            st.error(
                                "ACTUAL grafikas jau pasikeitė. Atnaujink puslapį ir pasirink CURRENT LOCATION / MOVING TO iš naujo."
                                if lang=="LT" else
                                "ACTUAL changed. Refresh and select CURRENT LOCATION / MOVING TO again."
                            )
                        elif (
                            source_slot.day!=target_slot.day
                            or source_slot.block!=target_slot.block
                            or not is_emergency_lower_priority_donor_slot(source_slot)
                            or not is_emergency_critical_slot(target_slot)
                        ):
                            st.error(
                                "Rescue neatitinka vienpusio same-time lower-priority → critical SPS modelio."
                                if lang=="LT" else
                                "Rescue no longer matches the same-time lower-priority → critical SPS model."
                            )
                        else:
                            repaired=apply_emergency_critical_transfer(
                                fresh_rescue.assignments,
                                target_slot,
                                mover,
                                source_slot=source_slot,
                            )
                            fresh_rescue.assignments=repaired
                            # Revalidate in-memory under ACTUAL operational rules so the
                            # stored payload carries refreshed stats + frozen workload credit.
                            fresh_rescue=revalidate_loaded_result(
                                year,month,people_for_stored_result(fresh_rescue,year,month),fresh_rescue,
                                backup_assignments=None,
                                validation_mode="emergency_rescue",
                            )
                            desired_backups,backup_errors=plan_backups(year,month,fresh_rescue)
                            if backup_errors:
                                st.error(
                                    ("Emergency Rescue negalimas, nes po perkėlimo nepavyksta sudaryti privalomo backup plano: " if lang=="LT" else
                                     "Emergency Rescue cannot be applied because required backup coverage cannot be rebuilt: ")
                                    + "; ".join(map(str,backup_errors[:3]))
                                )
                                st.stop()
                            # Final payload is validated against the NEW backup plan that
                            # will be committed in the same DB transaction.
                            fresh_rescue=revalidate_loaded_result(
                                year,month,people_for_stored_result(fresh_rescue,year,month),fresh_rescue,
                                backup_assignments=desired_backups,
                                validation_mode="emergency_rescue",
                            )
                            final_rescue_errors=list((fresh_rescue.stats or {}).get("global",{}).get("errors",[]) or [])
                            if final_rescue_errors:
                                st.error(
                                    ("Emergency Rescue negalimas dėl operational HARD taisyklės: " if lang=="LT" else
                                     "Emergency Rescue is blocked by an operational HARD rule: ")
                                    + str(final_rescue_errors[0])
                                )
                                st.stop()

                            meta={
                                "kind":"emergency_rescue",
                                "phase":"applied",
                                "mover":mover,
                                "rescued_person":rescued_person,
                                "source_slot":int(source_sid),
                                "target_slot":int(target_sid),
                                "source_department":source_slot.department,
                                "target_department":target_slot.department,
                                "day":int(source_slot.day),
                                "block":source_slot.block,
                                "source_vacated":True,
                                "bilateral_swap":False,
                                "fairness_neutral":True,
                                "workload_credit_neutral":True,
                                "workload_credit_source":"PUBLISHED_SYSTEM",
                                
                                "rescued_person_absence_outcome":"OUTSIDE_SCHEDULER_HR",
                                "recorded_by":active_user,
                                "recorded_at":datetime.now(timezone.utc).isoformat(),
                                "note":str(rescue_note or ""),
                            }
                            try:
                                saved=db.apply_emergency_rescue_atomic_v2585(
                                    year,month,source_sid,target_sid,mover,rescued_person,
                                    serialize_result(fresh_rescue),desired_backups,
                                    reason=_swap_meta_encode(meta),
                                )
                            except Exception as exc:
                                st.error(
                                    ("Emergency Rescue NEĮRAŠYTAS — transakcija atšaukta, ACTUAL grafikas ir backup planas nepakeisti. " if lang=="LT" else
                                     "Emergency Rescue NOT recorded — transaction rolled back; ACTUAL and backup plan were left unchanged. ")
                                    + str(exc)
                                )
                                st.stop()
                            refresh_calendar_subscription_feeds([mover,rescued_person])

                            st.session_state["_swap_response_flash"]=(
                                "success",
                                (
                                    f"ONE-WAY RESCUE įrašytas: {mover} "
                                    f"{source_slot.department} → {target_slot.department}; "
                                    f"RESCUED {rescued_person}. CURRENT source paliktas tuščias. Workload credit visiems nepakitęs."
                                )
                                if lang=="LT" else
                                (
                                    f"ONE-WAY RESCUE recorded: {mover} "
                                    f"{source_slot.department} → {target_slot.department}; "
                                    f"RESCUED {rescued_person}. Source post left vacant. Workload credit unchanged for everyone."
                                )
                            )
                            st.rerun()

            rescue_all=[
                r for r in db.list_swap_requests(
                    year,month,None if senior_mode else active_user
                )
                if _swap_meta_decode(r.get("reason")).get("kind") in {"emergency_rescue","emergency_actual"}
            ]
            if rescue_all:
                st.markdown(
                    "#### ONE-WAY rescue žurnalas"
                    if lang=="LT" else
                    "#### ONE-WAY rescue log"
                )
                for idx,r in enumerate(rescue_all,start=1):
                    meta=_swap_meta_decode(r.get("reason"))
                    with st.container(border=True):
                        if meta.get("kind")=="emergency_rescue":
                            mover_i=str(r.get("person_a") or "")
                            rescued_i=str(meta.get("rescued_person") or r.get("person_b") or "")
                            st.markdown(
                                f"**RESCUE #{idx} · DB #{r.get('id')}**"
                            )
                            _render_swap_people_line(mover_i,rescued_i,"→")
                            lc1,lc2=st.columns(2)
                            with lc1:
                                st.markdown(
                                    f"**CURRENT LOCATION**  \n{meta.get('source_department','—')} · "
                                    f"{meta.get('day','—')} · {meta.get('block','—')}"
                                )
                            with lc2:
                                st.markdown(
                                    f"**MOVING TO**  \n{meta.get('target_department','—')} · "
                                    f"{meta.get('day','—')} · {meta.get('block','—')}"
                                )
                            st.markdown(
                                "**RESCUED PERSON:** "+badge(rescued_i,include_name=True),
                                unsafe_allow_html=True,
                            )
                            st.caption(
                                (
                                    "Source postas paliktas tuščias; rescued person neperkeltas atgal. "
                                    + (f"Pastaba: {meta.get('note')}" if meta.get("note") else "")
                                )
                                if lang=="LT" else
                                (
                                    "Source post left vacant; rescued person was not moved back. "
                                    + (f"Note: {meta.get('note')}" if meta.get("note") else "")
                                )
                            )
                            st.caption(
                                "DELETE / UNDO atkurs mover į CURRENT LOCATION ir RESCUED PERSON į ankstesnį kritinį postą tik jei šie slotai po Rescue nebuvo pakeisti dar kartą."
                                if lang=="LT" else
                                "DELETE / UNDO restores the mover to CURRENT LOCATION and the RESCUED PERSON to the prior critical post only if those slots have not changed again."
                            )
                            if _delete_confirm(f"emergency_rescue_{r['id']}",applied=True):
                                try:
                                    saved=_delete_swap_row(r,year,month)
                                    st.session_state["_swap_response_flash"]=(
                                        "success",
                                        ("Emergency Rescue ištrintas ir ACTUAL saugiai atkurtas." if lang=="LT" else
                                         "Emergency Rescue deleted and ACTUAL safely restored.")
                                    )
                                    st.rerun()
                                except Exception as exc:
                                    st.error(("Emergency Rescue DELETE / UNDO nepavyko: " if lang=="LT" else "Emergency Rescue DELETE / UNDO failed: ")+str(exc))
                        else:
                            st.warning(
                                (
                                    f"LEGACY emergency_actual #{r.get('id')}: "
                                    f"{r.get('person_a')} ↔ {r.get('person_b')}. "
                                    "Tai senas bilateralinis įrašas iš ankstesnės, klaidingai pavadintos Emergency logikos."
                                )
                                if lang=="LT" else
                                (
                                    f"LEGACY emergency_actual #{r.get('id')}: "
                                    f"{r.get('person_a')} ↔ {r.get('person_b')}. "
                                    "This is a historical bilateral record from the old misnamed Emergency flow."
                                )
                            )

        # V2.5.13 — senior-only fairness-neutral post-publication repair workflow.
        if senior_mode:
            st.divider(); st.markdown(f"### {tr('repair_title')}"); st.caption(tr("repair_help"))
            fresh=refresh_result_payload(db.load_schedule(year,month,"current"),year,month)
            slots_by_id={s.idx:s for s in make_slots(year,month)}
            assigned_slots=[s for s in make_slots(year,month) if fresh.assignments.get(s.idx)]
            assigned_slots=sorted(assigned_slots,key=lambda x:(x.day,x.department,x.block,x.idx))
            def _repair_slot_label(sl):
                return f"{sl.day:02d} · {sl.department} · {block_label(sl.block)} · {fresh.assignments.get(sl.idx,'—')}"
            repair_rows=db.list_schedule_repairs(year,month)
            repair_load={}
            for rr in repair_rows:
                to_i=rr.get("to_person")
                if to_i: repair_load[to_i]=repair_load.get(to_i,0)+1
            if assigned_slots:
                chosen=st.selectbox(tr("repair_assignment"),assigned_slots,format_func=_repair_slot_label,key="repair_slot")
                from_person=fresh.assignments.get(chosen.idx)
                target_critical=is_emergency_critical_slot(chosen)
                candidate_rows=[]
                base_rh=int(fresh.stats.get("global",{}).get("resident_hard_total_losses",0) or 0)
                if target_critical:
                    # V2.5.56: critical sickness/absence rescue hierarchy. Keep SPS
                    # RO / SPS UG covered by moving a resident out of an overlapping
                    # lower-priority OPTIONAL post first. Only if no safe transfer
                    # exists do we expose a free-resident fallback.
                    shown_candidates=_critical_repair_candidate_rows(year,month,fresh,chosen,repair_load)
                else:
                    for prow in DEFAULT_PEOPLE:
                        cand=prow["initials"]
                        if cand==from_person: continue
                        ok,why,cstats=_repair_candidate_check(year,month,fresh,chosen.idx,cand)
                        if ok:
                            cg=(cstats or {}).get("global",{})
                            candidate_rows.append({
                                "initials":cand,
                                "source_slot":None,
                                "source_department":"",
                                "source_block":"",
                                "mode":"DIRECT",
                                "rh_total":int(cg.get("resident_hard_total_losses",0) or 0),
                                "rh_delta":int(cg.get("resident_hard_total_losses",0) or 0)-base_rh,
                                "rh_max":int(cg.get("resident_hard_max_loss_per_resident",0) or 0),
                                "rh_cum_spread":int(cg.get("resident_hard_cumulative_spread",0) or 0),
                                "critical_spread":int(cg.get("critical_worst_spread",0) or 0),
                                "noncritical_spread":int(cg.get("noncritical_worst_spread",0) or 0),
                            })
                    # Post-publication repairs follow the same RESIDENT-HARD
                    # constitution when this is not a critical pull-down repair.
                    strict_candidates=[r for r in candidate_rows if r["rh_delta"]<=0]
                    shown_candidates=strict_candidates or candidate_rows
                    shown_candidates=sorted(shown_candidates,key=lambda r:(
                        r["rh_total"],r["rh_max"],r["rh_cum_spread"],repair_load.get(r["initials"],0),r["initials"]
                    ))
                if shown_candidates:
                    c1,c2=st.columns(2)
                    with c1:
                        repl_row=st.selectbox(
                            tr("repair_replacement"),shown_candidates,
                            format_func=lambda r:(
                                f"{r['initials']} · "
                                + (f"PULL iš {r['source_department']} {block_label(r['source_block'])} · " if r.get('source_slot') is not None else ("BLOCK-FREE fallback · " if r.get('mode')=="FREE_FALLBACK" else ""))
                                + f"RH Δ {r['rh_delta']:+d} · repair {repair_load.get(r['initials'],0)}"
                            ),
                            key="repair_replacement"
                        )
                        repl=repl_row["initials"]
                        if target_critical and repl_row.get("source_slot") is not None:
                            st.success(
                                f"CRITICAL COVER: {repl} bus perkeltas iš neprivalomo posto "
                                f"{repl_row['source_department']} ({block_label(repl_row['source_block'])}) į "
                                f"{chosen.department} ({block_label(chosen.block)}). Donorinis optional postas lieka tuščias."
                            )
                        elif target_critical and repl_row.get("mode")=="FREE_FALLBACK":
                            st.warning(
                                "Nerasta saugaus tos pačios pamainos donorinio rezidento iš žemesnės hierarchijos optional posto; "
                                "todėl rodomas tame laiko bloke laisvo rezidento fallback."
                            )
                        if repl_row["rh_delta"]>0:
                            st.warning("RESIDENT HARD conflict: this candidate is invalid under V2.5.107 and must not be used for SYSTEM generation.")
                    with c2:
                        reason_options=[("sickness",tr("repair_reason_sickness")),("leave",tr("repair_reason_leave")),("approved_absence",tr("repair_reason_approved")),("force_majeure",tr("repair_reason_force"))]
                        reason=st.selectbox(tr("repair_reason"),reason_options,format_func=lambda x:x[1],key="repair_reason")[0]
                    note=st.text_input(tr("repair_note"),key="repair_note")
                    st.caption(tr("repair_load_help"))
                    if st.button(tr("apply_repair"),type="primary",key="apply_repair_btn"):
                        source_sid=repl_row.get("source_slot")
                        ok,why,stats=_repair_candidate_check(year,month,fresh,chosen.idx,repl,source_sid)
                        if not ok:
                            st.error(f"{tr('repair_invalid')}: {why}")
                        else:
                            old_person=fresh.assignments[chosen.idx]
                            source_sl=slots_by_id.get(int(source_sid)) if source_sid is not None else None
                            if target_critical:
                                fresh.assignments=apply_emergency_critical_transfer(
                                    fresh.assignments,chosen,repl,source_sl
                                )
                            else:
                                fresh.assignments[chosen.idx]=repl
                            fresh.stats=stats
                            auto_note=""
                            if source_sl is not None:
                                auto_note=(
                                    f"V2.5.56 CRITICAL PULL-DOWN: {repl} moved from optional "
                                    f"{source_sl.department} {source_sl.block} to mandatory {chosen.department} {chosen.block}; "
                                    f"source slot #{source_sl.idx} intentionally left unfilled."
                                )
                            final_note=(auto_note + (" | " + note if note else "")).strip(" |")
                            # ACTUAL changes; baseline_json and fairness_history are deliberately untouched.
                            db.apply_schedule_repair(year,month,serialize_result(fresh),chosen.idx,chosen.day,chosen.department,chosen.block,old_person,repl,reason,final_note)
                            sync_backup_plan(year,month,fresh)
                            persist_actual_satisfaction(year,month)
                            refresh_calendar_subscription_feeds([old_person,repl])
                            st.success(tr("repair_applied")); st.rerun()
                else:
                    st.warning(tr("repair_no_candidate"))
            if repair_rows:
                st.markdown(f"#### {tr('repair_history')}")
                rlabels={"sickness":tr("repair_reason_sickness"),"leave":tr("repair_reason_leave"),"approved_absence":tr("repair_reason_approved"),"force_majeure":tr("repair_reason_force")}
                rdf=pd.DataFrame([{tr("repair_date"):f"{int(r['day']):02d} · {r['department']} · {block_label(r['block'])}",tr("repair_from"):r['from_person'],tr("repair_to"):r['to_person'],tr("repair_reason"):rlabels.get(r.get('reason'),r.get('reason','')),tr("repair_note"):r.get('note') or "—",tr("status"):tr("repair_fairness_neutral")} for r in repair_rows])
                st.dataframe(rdf,use_container_width=True,hide_index=True)
                ldf=pd.DataFrame([{tr("person"):i,tr("repair_load"):n} for i,n in sorted(repair_load.items(),key=lambda kv:(-kv[1],kv[0]))])
                if not ldf.empty: st.dataframe(ldf,use_container_width=True,hide_index=True)
pos+=1

# --- Calendar ---
with tabs[pos]:
    st.subheader(tr("calendar_title")); currentp=db.load_schedule(year,month,"current")
    if not currentp: st.info(tr("not_published"))
    elif not resident_ok: st.error(tr("bad_pin"))
    else:
        result=refresh_result_payload(currentp,year,month)
        st.markdown(badge(active_user),unsafe_allow_html=True)
        if active_user in (SENIOR_INITIALS,WESTON_CREDITOR_INITIALS):
            try:
                _weston_calendar=db.weston_beer_stats_v25110(year,month)
                if active_user==SENIOR_INITIALS:
                    st.metric(("WESTON skola ŠR" if lang=="LT" else "WESTON debt to ŠR"),int(_weston_calendar.get("total_beers",0)),help=("Kiekvienas SP Generate/Rebuild paspaudimas = +1." if lang=="LT" else "Every SP Generate/Rebuild click = +1."))
                else:
                    st.metric(("WESTON, kuriuos SP tau skolinga" if lang=="LT" else "WESTONs SP owes you"),int(_weston_calendar.get("total_beers",0)),help=("Tas pats persistent skaičius, kurį SP mato kaip skolą." if lang=="LT" else "The same persistent total SP sees as debt."))
            except Exception:
                pass
        st.markdown("### Mano normalios darbo pamainos" if lang=="LT" else "### My normal work shifts")
        st.caption(
            "Tai vienintelis darbo grafiko sluoksnis. Teoriniai dubliai čia NĖRA skaičiuojami kaip darbas."
            if lang=="LT" else
            "This is the actual work-schedule layer. Theoretical backup duties are NOT counted as work here."
        )
        st.dataframe(personal_schedule_df(year,month,result,active_user),use_container_width=True,hide_index=True)
        st.markdown("### Teorinis dublių / pavadavimo sluoksnis" if lang=="LT" else "### Theoretical backup / standby layer")
        st.caption(
            "Dublis yra tik standby planas: jis nekeičia pageidavimų, darbo krūvio, poilsio, water-fill ar normalios pamainos statistikos. Tik pažymėtas COMPLETED realus pavadavimas tampa ACTUAL darbu."
            if lang=="LT" else
            "A backup is standby only: it does not change preferences, workload, rest, water-fill or normal-shift statistics. Only a COMPLETED real-life cover becomes ACTUAL work."
        )
        st.dataframe(backup_grid(year,month,result,active_user),use_container_width=True)
        ics_bytes=build_ics(year,month,result,active_user)
        st.download_button(tr("download_ics"),ics_bytes,file_name=f"{safe_filename(active_user)}_{year}_{month:02d}.ics",mime="text/calendar",type="primary")
        st.caption(tr("calendar_help"))
        try:
            feed_ics=build_calendar_subscription_ics(active_user)
            feed_url=db.publish_calendar_feed(active_user,feed_ics)
            st.markdown(f"### {tr('calendar_feed')}")
            st.warning(tr("calendar_feed_private"))
            st.code(feed_url,language=None)
            cga,cap,coth=st.columns(3)
            with cga:
                st.link_button(tr("calendar_google"),"https://calendar.google.com/calendar/u/0/r/settings/addbyurl",use_container_width=True)
                st.caption(tr("calendar_google_help"))
            with cap:
                apple_url="webcal://"+feed_url.split("://",1)[-1]
                st.markdown(f'<a href="{html.escape(apple_url,quote=True)}" style="display:block;text-align:center;padding:.55rem .75rem;border:1px solid rgba(128,128,128,.35);border-radius:.5rem;text-decoration:none;font-weight:600;">{html.escape(tr("calendar_apple"))}</a>',unsafe_allow_html=True)
                st.caption(tr("calendar_apple_help"))
            with coth:
                st.link_button(tr("calendar_other"),"https://outlook.live.com/calendar/0/addcalendar",use_container_width=True)
                st.caption(tr("calendar_other_help"))
                st.download_button(("ATSISIŲSTI .ics" if lang=="LT" else "DOWNLOAD .ics"),ics_bytes,file_name=f"{safe_filename(active_user)}_{year}_{month:02d}.ics",mime="text/calendar",use_container_width=True,key=f"ics_fallback_{year}_{month}_{active_user}")
        except Exception as exc:
            st.caption(("Kalendoriaus prenumeratos nuorodos dar nepavyko atnaujinti; .ics atsisiuntimas veikia." if lang=="LT" else "Could not refresh the subscription feed yet; .ics download still works.")+f" ({exc})")
pos+=1



# ===== V2.5.41 RESEARCH: Grafikų sudarymo metodų palyginimas =====

_RESEARCH_PREF_COLUMNS = [
    "initials","name","unavailable","unavailable_am","unavailable_pm","vacation","justified_absence","long_duty",
    "soft_free","soft_free_am","soft_free_pm","preferred","preferred_am","preferred_pm",
    "spread_preference","holiday_preference","shift_length_preference","avoid_doubles","target_adjustment",
    "prior_weekend_count","prior_friday_count","prior_double_count","prior_weekday_day_count",
] + [f"prior_rotation__{cat}" for cat in ROTATION_CATEGORIES]

def _research_norm(x):
    s="" if x is None else str(x)
    s=unicodedata.normalize("NFKD",s).encode("ascii","ignore").decode("ascii").lower().strip()
    s=re.sub(r"\s+"," ",s)
    s=re.sub(r"[^a-z0-9]+","",s)
    return s

def _research_colmap(df):
    aliases={
        "initials":["initials","inic","inicialai","rezidentas","person","zmogus"],
        "name":["name","vardas","vardaspavarde"],
        "unavailable":["unavailable","negaliudirbti","hardoff","negaliu"],
        "unavailable_am":["unavailableam","negaliuryte","negaliuam"],
        "unavailable_pm":["unavailablepm","negaliupopiete","negaliupm"],
        "vacation":["vacation","atostogos","atostogauja","leave"],
        "justified_absence":["justifiedabsence","pateisinamasneatvykimas","liga","absence"],
        "long_duty":["longduty","24h","budėjimas24h","budejimas24h"],
        "soft_free":["softfree","noriulaisvos","pageidaujalaisvos","preferredoff"],
        "soft_free_am":["softfreeam","noriulaisvoryto"],
        "soft_free_pm":["softfreepm","noriulaisvospopietes"],
        "preferred":["preferred","pageidaujadirbti","pageidaujudirbti","pageidauju","noriudirbti","preferredwork"],
        "preferred_am":["preferredam","pageidaujadirbtiryte"],
        "preferred_pm":["preferredpm","pageidaujadirbtipopiete"],
        "weekday_preference":["weekdaypreference","darbdienupreference"],
        "weekend_preference":["weekendpreference","savaitgaliupreference"],
        "spread_preference":["spreadpreference","issklaidymas","koncentracija"],
        "holiday_preference":["holidaypreference","svenciupreference","sventes","publicholidays"],
        "shift_length_preference":["shiftlengthpreference","darbotrukme","pamainustrukme","workdaylength"],
        "avoid_doubles":["avoiddoubles","vengtidubliu","vengtidvigubu"],
        "target_adjustment":["targetadjustment","targetokorekcija"],
        "prior_weekend_count":["priorweekendcount","ankstesnisavaitgaliai"],
        "prior_friday_count":["priorfridaycount","ankstesnipenktadieniai"],
        "prior_double_count":["priordoublecount","ankstesnidubliai"],
        "prior_weekday_day_count":["priorweekdaydaycount","ankstesnesdarbdienos"],
    }
    actual={_research_norm(c):c for c in df.columns}
    out={}
    for key,opts in aliases.items():
        for opt in opts:
            n=_research_norm(opt)
            if n in actual:
                out[key]=actual[n]; break
    return out

def _research_days(v, ndays, y=None, m=None):
    """Parse day lists from real-world monthly wishes Excel cells.

    Supports single days, comma lists, Lithuanian/English ranges (22-24, 5 iki 14),
    and the phrase "Visi savaitgaliai šio mėnesio". Clock times are stripped before
    day parsing so e.g. "6 d 08:00-14:00" becomes day 6 rather than 6/8/14.
    """
    if v is None or (isinstance(v,float) and pd.isna(v)):
        return set()
    if isinstance(v,(int,float)) and not isinstance(v,bool):
        d=int(v)
        return {d} if 1 <= d <= ndays else set()

    raw=str(v).strip()
    ascii_text=unicodedata.normalize("NFKD",raw).encode("ascii","ignore").decode("ascii").lower()
    out=set()

    # Natural-language month shortcut used by the original August workbook.
    if y is not None and m is not None and (
        "visi savaitgaliai" in ascii_text
        or "all weekends" in ascii_text
        or "kiekviena savaitgali" in ascii_text
    ):
        out |= {
            d for d in range(1,ndays+1)
            if date(int(y),int(m),d).weekday() >= 5
        }

    # Remove clock expressions before interpreting day numbers.
    cleaned=re.sub(
        r"(?<!\d)\d{1,2}[:.]\d{2}\s*(?:-|–|—|iki|to)\s*\d{1,2}[:.]\d{2}(?!\d)",
        " ",ascii_text,flags=re.I
    )
    cleaned=re.sub(r"(?<!\d)\d{1,2}[:.]\d{2}(?!\d)"," ",cleaned)

    # Expand day ranges first, including Lithuanian "iki".
    spans=[]
    for mt in re.finditer(r"(?<!\d)([0-3]?\d)\s*(?:-|–|—|iki|to)\s*([0-3]?\d)(?!\d)",cleaned,re.I):
        a,b=int(mt.group(1)),int(mt.group(2))
        if 1 <= a <= ndays and 1 <= b <= ndays:
            lo,hi=sorted((a,b))
            out.update(range(lo,hi+1))
            spans.append(mt.span())

    # Blank matched spans so their endpoints are not handled twice (harmless but cleaner).
    chars=list(cleaned)
    for a,b in spans:
        for i in range(a,b):
            chars[i]=" "
    remainder="".join(chars)
    out |= {
        int(x) for x in re.findall(r"(?<!\d)([0-3]?\d)(?!\d)",remainder)
        if 1 <= int(x) <= ndays
    }
    return out

def _research_int(v, default=0):
    if v is None or (isinstance(v,float) and pd.isna(v)):
        return default
    try: return int(float(v))
    except Exception: return default

def _research_bool(v):
    if isinstance(v,bool): return v
    return _research_norm(v) in {"1","true","yes","taip","y","t"}

def research_preferences_template(y,m):
    rows=[]
    for p in DEFAULT_PEOPLE:
        rows.append({c:"" for c in _RESEARCH_PREF_COLUMNS})
        rows[-1]["initials"]=p["initials"]; rows[-1]["name"]=p["name"]
        rows[-1]["target_adjustment"]=p.get("target_adjustment",0)
    guide=pd.DataFrame([
        ["Date lists","Use day numbers separated by commas, e.g. 2, 5, 17. Leave blank = N/A / no preference."],
        ["HARD","unavailable / vacation / other justified absence / long duty are HARD."],
        ["SOFT","soft_free and preferred fields are active SOFT preferences; blank means N/A."],
        ["SOFT-3 month shape","spread_preference: -2..+2 (clustered ↔ dispersed); blank/0 = N/A. Broad weekday/weekend direction is deprecated and ignored in V2.5.52."],
        ["Prior fairness","prior_* columns are optional. Leave 0 if historical carry-in is unavailable."],
        ["Prior workplace exposure","prior_rotation__* columns are optional cumulative SYSTEM counts from earlier months. Leave blank/0 if unavailable."],
        ["Month",f"{y}-{m:02d}"],
    ],columns=["Field","Instruction"])
    bio=BytesIO()
    with pd.ExcelWriter(bio,engine="xlsxwriter") as w:
        pd.DataFrame(rows).to_excel(w,index=False,sheet_name="preferences")
        guide.to_excel(w,index=False,sheet_name="README")
    return bio.getvalue()

def research_schedule_template(y,m):
    rows=[]
    for s in make_slots(y,m):
        if s.blocked: continue
        rows.append({
            "slot_id":s.idx,
            "date":f"{y}-{m:02d}-{s.day:02d}",
            "department":s.department,
            "shift":s.block,
            "person":"",
        })
    guide=pd.DataFrame([
        ["person","Enter initials exactly as roster uses them, e.g. ŠR / MG"],
        ["Rows","Leave unfilled/unused optional slots blank. Do not delete slot_id if using this template."],
        ["Existing Excel","Long-format schedules are also accepted if columns equivalent to date/day, department, shift, person exist."],
        ["Month",f"{y}-{m:02d}"],
    ],columns=["Field","Instruction"])
    bio=BytesIO()
    with pd.ExcelWriter(bio,engine="xlsxwriter") as w:
        pd.DataFrame(rows).to_excel(w,index=False,sheet_name="schedule")
        guide.to_excel(w,index=False,sheet_name="README")
    return bio.getvalue()


_RESEARCH_LT_MONTHS={
    1:["sausis","sausio"],2:["vasaris","vasario"],3:["kovas","kovo"],4:["balandis","balandzio"],
    5:["geguze","geguzes"],6:["birzelis","birzelio"],7:["liepa","liepos"],8:["rugpjutis","rugpjucio"],
    9:["rugsejis","rugsejo"],10:["spalis","spalio"],11:["lapkritis","lapkricio"],12:["gruodis","gruodzio"],
}
_RESEARCH_EN_MONTHS={
    1:["january","jan"],2:["february","feb"],3:["march","mar"],4:["april","apr"],
    5:["may"],6:["june","jun"],7:["july","jul"],8:["august","aug"],
    9:["september","sep","sept"],10:["october","oct"],11:["november","nov"],12:["december","dec"],
}

def _research_file_bytes(uploaded):
    if hasattr(uploaded,"getvalue"):
        return uploaded.getvalue()
    if isinstance(uploaded,(bytes,bytearray)):
        return bytes(uploaded)
    pos=None
    try:
        pos=uploaded.tell()
    except Exception:
        pass
    raw=uploaded.read()
    if pos is not None:
        try: uploaded.seek(pos)
        except Exception: pass
    return raw


def _research_workbook_hash(uploaded):
    return hashlib.sha256(_research_file_bytes(uploaded)).hexdigest()


def _research_sheet_month_hint(sheet_name):
    n=unicodedata.normalize("NFKD",str(sheet_name or "")).encode("ascii","ignore").decode("ascii").lower()
    n=re.sub(r"[^a-z0-9]+"," ",n)
    found=set()
    for mm,toks in _RESEARCH_LT_MONTHS.items():
        if any(re.search(rf"\b{re.escape(t)}\w*\b",n) for t in toks):
            found.add(mm)
    for mm,toks in _RESEARCH_EN_MONTHS.items():
        if any(re.search(rf"\b{re.escape(t)}\w*\b",n) for t in toks):
            found.add(mm)
    # Numeric hints only when clearly month-like.
    for mm in range(1,13):
        if re.search(rf"(?:^|[\s_\-./])0?{mm}(?:$|[\s_\-./])",str(sheet_name or "")):
            found.add(mm)
    return sorted(found)


def _research_make_unique_headers(values):
    out=[]; seen={}
    for idx,v in enumerate(values):
        if v is None or (isinstance(v,float) and pd.isna(v)):
            base=f"__col_{idx+1}"
        else:
            base=str(v).strip() or f"__col_{idx+1}"
        count=seen.get(base,0)
        seen[base]=count+1
        out.append(base if count==0 else f"{base}__{count+1}")
    return out


def _research_table_candidate(raw,header_row,kind):
    if header_row<0 or header_row>=len(raw):
        return None
    headers=_research_make_unique_headers(raw.iloc[header_row].tolist())
    df=raw.iloc[header_row+1:].copy()
    df.columns=headers
    df=df.dropna(axis=0,how="all").dropna(axis=1,how="all")
    if df.empty:
        return None

    if kind=="preferences":
        cmap=_research_colmap(df)
        mapped=set(cmap)
        # prior_rotation columns are valid preference metadata too.
        prior_cols=[]
        for cat in ROTATION_CATEGORIES:
            target=_research_norm(f"prior_rotation__{cat}")
            for c in df.columns:
                if _research_norm(c)==target:
                    prior_cols.append(c); break
        # Original clinic wishes workbooks commonly identify residents by full name only.
        # Either initials OR a name column is therefore a valid identity field.
        if "initials" not in cmap and "name" not in cmap:
            return None
        nonidentity=mapped-{"initials","name"}
        score=10+len(nonidentity)*3+len(prior_cols)
        # A resident-directory/helper sheet with only initials/name is not enough.
        if not nonidentity and not prior_cols:
            return None
        return {"df":df,"cmap":cmap,"score":score,"prior_cols":prior_cols}

    if kind=="schedule":
        cmap=_research_schedule_colmap(df)
        if "person" not in cmap:
            return None
        has_locator=("slot_id" in cmap) or (
            ("date" in cmap or "day" in cmap)
            and "department" in cmap and "shift" in cmap
        )
        if not has_locator:
            return None
        score=10+len(cmap)*3
        return {"df":df,"cmap":cmap,"score":score}

    return None


def _research_scan_workbook(uploaded,kind,y,m):
    """Scan every worksheet and detect the best compatible table per sheet."""
    raw_bytes=_research_file_bytes(uploaded)
    wb_hash=hashlib.sha256(raw_bytes).hexdigest()
    xls=pd.ExcelFile(BytesIO(raw_bytes))
    tables=[]; audit=[]
    for sheet in xls.sheet_names:
        month_hints=_research_sheet_month_hint(sheet)
        if month_hints and int(m) not in month_hints:
            audit.append({
                "sheet":sheet,"status":"skipped_other_month",
                "reason":f"sheet name suggests month(s) {month_hints}, selected month is {m}",
            })
            continue
        try:
            raw=pd.read_excel(xls,sheet_name=sheet,header=None,dtype=object)
        except Exception as exc:
            audit.append({"sheet":sheet,"status":"read_error","reason":str(exc)})
            continue
        # Keep original row indices intact for exact Excel row provenance.
        raw=raw.dropna(axis=1,how="all")
        if raw.dropna(axis=0,how="all").empty:
            audit.append({"sheet":sheet,"status":"ignored_empty","reason":"empty worksheet"})
            continue

        candidates=[]
        max_header=min(len(raw)-1,60)
        for hr in range(max_header+1):
            cand=_research_table_candidate(raw,hr,kind)
            if cand is not None:
                candidates.append((cand["score"],-hr,hr,cand))
        if not candidates and kind=="schedule":
            grid=_research_grid_schedule_candidate(raw,y,m)
            if grid is not None:
                rec={
                    "sheet":sheet,
                    "header_row":grid["header_row"]+1,
                    "score":grid["score"],
                    "rows":len(grid["recognized_rows"]),
                    "mode":"grid",
                    "raw":raw,
                    "day_cols":grid["day_cols"],
                    "recognized_rows":grid["recognized_rows"],
                    "workbook_hash":wb_hash,
                }
                tables.append(rec)
                audit.append({
                    "sheet":sheet,"status":"used_grid_schedule",
                    "header_row":grid["header_row"]+1,
                    "rows":len(grid["recognized_rows"]),
                    "score":grid["score"],
                })
                continue

        if not candidates:
            audit.append({
                "sheet":sheet,"status":"ignored_unrecognized",
                "reason":f"no compatible {kind} table detected in first {max_header+1} rows",
            })
            continue
        _score,_neg_hr,hr,cand=max(candidates,key=lambda x:(x[0],x[1]))
        rec={
            "sheet":sheet,"header_row":hr+1,"score":cand["score"],
            "rows":len(cand["df"]),"df":cand["df"],"cmap":cand["cmap"],
            "workbook_hash":wb_hash,"mode":"long",
        }
        if "prior_cols" in cand:
            rec["prior_cols"]=cand["prior_cols"]
        tables.append(rec)
        audit.append({
            "sheet":sheet,"status":"used_long_table","header_row":hr+1,
            "rows":len(cand["df"]),"score":cand["score"],
        })
    return tables,{
        "kind":kind,
        "workbook_hash":wb_hash,
        "sheet_count":len(xls.sheet_names),
        "used_sheet_count":len(tables),
        "sheets":audit,
    }


def _research_nonempty(v):
    if v is None:
        return False
    if isinstance(v,float) and pd.isna(v):
        return False
    return bool(str(v).strip()) and str(v).strip().lower()!="nan"


def _research_scalar_conflict_key(field,value):
    if field=="name":
        return _research_norm(value)
    if field=="avoid_doubles":
        return str(bool(_research_bool(value)))
    if field in {
        "weekday_preference","weekend_preference","holiday_preference","spread_preference","target_adjustment",
        "prior_weekend_count","prior_friday_count","prior_double_count","prior_weekday_day_count",
    }:
        return str(_research_int(value,0))
    return str(value).strip()


def _research_explicit_shift(v):
    """Return AM/PM/FULL only when the cell explicitly contains shift/time information.

    Plain day numbers like "15 d" must never be mistaken for a 15:00 PM shift.
    """
    if not _research_nonempty(v):
        return ""
    raw=str(v).strip()
    n=_research_norm(raw)
    times=[(int(h),int(mm)) for h,mm in re.findall(r"(?<!\d)([0-2]?\d)[:.]([0-5]\d)(?!\d)",raw)]
    if len(times)>=2:
        start=times[0][0]+times[0][1]/60.0
        end=times[1][0]+times[1][1]/60.0
        if start <= 9 and end >= 16.5:
            return "FULL"
        if start <= 9 and end <= 14.5:
            return "AM"
        if start >= 13:
            return "PM"
    if re.search(r"(?:^|[^a-z])(am)(?:$|[^a-z])",raw,re.I) or "ryt" in n:
        return "AM"
    if re.search(r"(?:^|[^a-z])(pm)(?:$|[^a-z])",raw,re.I) or "popiet" in n or "vakar" in n:
        return "PM"
    if "visadiena" in n or "pilnadiena" in n or "full" in n:
        return "FULL"
    return ""


def _research_resolve_resident(raw_value, exact_initials, known_names):
    """Resolve initials or a full name to the canonical roster initials.

    Exact matches are preferred. A conservative fuzzy fallback handles harmless source
    spelling differences such as Stašinskas/Strašinskas without silently matching
    genuinely different people.
    """
    if not _research_nonempty(raw_value):
        return None, None
    raw_text=str(raw_value).strip()
    direct=exact_initials.get(raw_text.casefold()) or known_names.get(_research_norm(raw_text))
    if direct:
        return direct, None

    import difflib
    target=_research_norm(raw_text)
    ranked=sorted(
        ((difflib.SequenceMatcher(None,target,nm).ratio(),ini,nm) for nm,ini in known_names.items()),
        reverse=True
    )
    if ranked and ranked[0][0] >= 0.92 and (len(ranked)==1 or ranked[0][0]-ranked[1][0] >= 0.05):
        return ranked[0][1], f"fuzzy name match '{raw_text}' -> {ranked[0][1]} ({ranked[0][0]:.2f})"
    return None, None


def research_people_from_excel(uploaded,y,m,return_audit=False):
    tables,audit=_research_scan_workbook(uploaded,"preferences",y,m)
    if not tables:
        raise ValueError(
            "No compatible preferences/HARD table was found anywhere in the workbook. "
            "The importer scanned every worksheet. A compatible table may identify residents "
            "by initials OR by full name and should contain at least one preference/HARD column."
        )

    ndays=calendar.monthrange(y,m)[1]
    exact_initials={p["initials"].casefold():p["initials"] for p in DEFAULT_PEOPLE}
    exact_initials.update({"sk":"SŠ","sr":"SP"})  # V2.5.113 historical-import compatibility
    known_names={_research_norm(p["name"]):p["initials"] for p in DEFAULT_PEOPLE}
    set_fields={
        "unavailable","unavailable_am","unavailable_pm","vacation","justified_absence","long_duty",
        "soft_free","soft_free_am","soft_free_pm","preferred","preferred_am","preferred_pm",
    }
    scalar_fields={
        "name","weekday_preference","weekend_preference","holiday_preference","spread_preference",
        "avoid_doubles","target_adjustment","prior_weekend_count","prior_friday_count",
        "prior_double_count","prior_weekday_day_count",
    }

    collected={p["initials"]:{
        "sets":{k:set() for k in set_fields},
        "scalars":{},
        "prior_rotation":{cat:[] for cat in ROTATION_CATEGORIES},
        "sources":[],
    } for p in DEFAULT_PEOPLE}
    warnings=[]; conflicts=[]

    for table in tables:
        if table.get("mode")=="grid":
            raw=table["raw"]
            local_used=set()
            day_cols=table["day_cols"]
            recognized_rows=sorted(table["recognized_rows"],key=lambda x:x[0])

            for ridx,fam,descriptor in recognized_rows:
                explicit_block=_research_shift(descriptor)
                for col_idx,day in day_cols:
                    if col_idx>=raw.shape[1]:
                        continue
                    cell=raw.iloc[ridx,col_idx]
                    persons,unknown_parts=_research_cell_people(
                        cell,exact_initials,known_names
                    )
                    for unknown in unknown_parts:
                        warnings.append(
                            f"{table['sheet']} row {int(ridx)+1}, day {day}: "
                            f"unknown resident/cell value '{unknown}'."
                        )
                    if not persons:
                        continue

                    candidates=[
                        s for s in slots
                        if s.day==day
                        and not s.blocked
                        and _research_slot_family(s)==fam
                        and s.idx not in local_used
                    ]
                    if explicit_block:
                        candidates=[s for s in candidates if s.block==explicit_block]

                    for person in persons:
                        if not candidates:
                            warnings.append(
                                f"{table['sheet']} row {int(ridx)+1}, day {day}: "
                                f"no remaining slot for {fam}"
                                + (f" {explicit_block}" if explicit_block else "")
                                + f" while reading '{cell}'."
                            )
                            break
                        s=sorted(candidates,key=lambda x:x.idx)[0]
                        candidates=[x for x in candidates if x.idx!=s.idx]
                        local_used.add(s.idx)
                        sid=s.idx
                        src={
                            "workbook_hash":table["workbook_hash"],
                            "sheet":table["sheet"],
                            "source_row":int(ridx)+1,
                            "source_column":int(col_idx)+1,
                            "day":int(day),
                            "header_row":table["header_row"],
                            "mode":"grid",
                        }
                        if sid in assignments:
                            previous=assignments[sid]
                            prev_src=provenance[sid]
                            if previous==person:
                                duplicates.append({
                                    "slot_id":sid,"person":person,
                                    "first_source":prev_src,"duplicate_source":src,
                                })
                            else:
                                conflicts.append({
                                    "slot_id":sid,
                                    "existing_person":previous,
                                    "new_person":person,
                                    "existing_source":prev_src,
                                    "new_source":src,
                                })
                            continue
                        assignments[sid]=person
                        provenance[sid]=src
            continue

        df=table["df"]; cmap=table["cmap"]
        for ridx,r in df.iterrows():
            # Prefer initials when present, otherwise use the full-name column from the
            # original clinic worksheet.
            raw_identity=None
            if "initials" in cmap and _research_nonempty(r.get(cmap["initials"])):
                raw_identity=r.get(cmap["initials"])
            elif "name" in cmap and _research_nonempty(r.get(cmap["name"])):
                raw_identity=r.get(cmap["name"])
            if not _research_nonempty(raw_identity):
                continue
            raw_text=str(raw_identity).strip()
            ini,match_note=_research_resolve_resident(raw_identity,exact_initials,known_names)
            if not ini:
                warnings.append(
                    f"{table['sheet']} row {int(ridx)+1}: unknown resident '{raw_text}'."
                )
                continue
            if match_note:
                warnings.append(f"{table['sheet']} row {int(ridx)+1}: {match_note}.")
            src={
                "workbook_hash":table["workbook_hash"],
                "sheet":table["sheet"],
                "source_row":int(ridx)+1,
                "header_row":table["header_row"],
            }
            collected[ini]["sources"].append(src)

            for field in set_fields:
                if field not in cmap:
                    continue
                raw=r.get(cmap[field])
                if not _research_nonempty(raw):
                    continue
                days=_research_days(raw,ndays,y,m)
                target_field=field
                # Original sheets sometimes encode half-day wishes as a time range in
                # the ordinary column, e.g. "6 d 08:00-14:00". Route that date to AM/PM.
                if field in {"unavailable","soft_free","preferred"}:
                    shift=_research_explicit_shift(raw)
                    if shift=="AM":
                        target_field=f"{field}_am"
                    elif shift=="PM":
                        target_field=f"{field}_pm"
                collected[ini]["sets"][target_field] |= days

            for field in scalar_fields:
                if field not in cmap:
                    continue
                raw=r.get(cmap[field])
                if not _research_nonempty(raw):
                    continue
                norm_val=_research_scalar_conflict_key(field,raw)
                collected[ini]["scalars"].setdefault(field,[]).append(
                    {"value":raw,"norm":norm_val,"source":src}
                )

            for cat in ROTATION_CATEGORIES:
                target=_research_norm(f"prior_rotation__{cat}")
                matching=next((c for c in df.columns if _research_norm(c)==target),None)
                if matching is None:
                    continue
                raw=r.get(matching)
                if _research_nonempty(raw):
                    collected[ini]["prior_rotation"][cat].append(
                        {"value":raw,"source":src}
                    )

    # True scalar conflicts block official lock rather than silently overwriting.
    for ini,data in collected.items():
        for field,vals in data["scalars"].items():
            distinct={}
            for rec in vals:
                distinct.setdefault(rec["norm"],rec)
            if len(distinct)>1:
                conflicts.append({
                    "resident":ini,"field":field,
                    "values":[str(v["value"]) for v in distinct.values()],
                    "sources":[v["source"] for v in distinct.values()],
                })
        for cat,vals in data["prior_rotation"].items():
            parsed={_research_int(v["value"],0) for v in vals}
            if len(parsed)>1:
                conflicts.append({
                    "resident":ini,"field":f"prior_rotation__{cat}",
                    "values":sorted(parsed),
                    "sources":[v["source"] for v in vals],
                })

    audit["conflicts"]=conflicts
    audit["warnings"]=warnings
    if conflicts:
        preview="; ".join(
            f"{c['resident']} {c['field']}={c['values']}" for c in conflicts[:6]
        )
        raise ValueError(
            "Whole-workbook preference import found conflicting scalar values. "
            "Official lock is blocked until resolved: "+preview
        )

    people=[]
    for base in DEFAULT_PEOPLE:
        ini=base["initials"]; data=collected[ini]
        def scalar(field,default):
            vals=data["scalars"].get(field) or []
            return default if not vals else vals[0]["value"]
        people.append(Person(
            initials=ini,
            name=str(scalar("name",base["name"]) or base["name"]),
            unavailable=set(data["sets"]["unavailable"]),
            unavailable_am=set(data["sets"]["unavailable_am"]),
            unavailable_pm=set(data["sets"]["unavailable_pm"]),
            vacation=set(data["sets"].get("vacation",set())),
            justified_absence=set(data["sets"]["justified_absence"]),
            long_duty=set(data["sets"]["long_duty"]),
            soft_free=set(data["sets"]["soft_free"]),
            soft_free_am=set(data["sets"]["soft_free_am"]),
            soft_free_pm=set(data["sets"]["soft_free_pm"]),
            preferred=set(data["sets"]["preferred"]),
            preferred_am=set(data["sets"]["preferred_am"]),
            preferred_pm=set(data["sets"]["preferred_pm"]),
            weekday_preference=max(-2,min(2,_research_int(scalar("weekday_preference",0),0))),
            weekend_preference=max(-2,min(2,_research_int(scalar("weekend_preference",0),0))),
            holiday_preference=max(-1,min(1,_research_int(scalar("holiday_preference",0),0))),
            spread_preference=max(-2,min(2,_research_int(scalar("spread_preference",0),0))),
            shift_length_preference=max(0,min(3,_research_int(scalar("shift_length_preference",0),0))),
            avoid_doubles=_research_bool(scalar("avoid_doubles",False)),
            target_adjustment=_research_int(
                scalar("target_adjustment",base.get("target_adjustment",0)),
                base.get("target_adjustment",0)
            ),
            prior_weekend_count=max(0,_research_int(scalar("prior_weekend_count",0),0)),
            prior_friday_count=max(0,_research_int(scalar("prior_friday_count",0),0)),
            prior_double_count=max(0,_research_int(scalar("prior_double_count",0),0)),
            prior_weekday_day_count=max(0,_research_int(scalar("prior_weekday_day_count",0),0)),
            prior_rotation_counts={
                cat:max(0,_research_int(
                    (data["prior_rotation"][cat][0]["value"] if data["prior_rotation"][cat] else 0),0
                ))
                for cat in ROTATION_CATEGORIES
            },
        ))

    audit["resident_sources"]={
        ini:data["sources"] for ini,data in collected.items() if data["sources"]
    }
    return (people,audit,warnings) if return_audit else people



def _research_shift(v):
    """Normalize historical shift labels/times to AM / PM / FULL."""
    raw="" if v is None else str(v)
    n=_research_norm(raw)
    compact=re.sub(r"[^0-9]","",raw)

    if (
        "full" in n or "visadiena" in n or "pilnadiena" in n
        or "0817" in compact or "817" in compact
    ):
        return "FULL"
    if (
        "pm" in n or "popiet" in n or "vak" in n
        or "1420" in compact or "14002000" in compact
    ):
        return "PM"
    if (
        "am" in n or "ryt" in n
        or "0814" in compact or "814" in compact or "08001400" in compact
    ):
        return "AM"
    # Exact common clock starts.
    mt=re.search(r"(?<!\d)(\d{1,2})[:.]?(\d{2})?(?!\d)",raw)
    if mt:
        hour=int(mt.group(1))
        if hour>=13:
            return "PM"
        if hour<=9:
            return "AM"
    return ""


def _research_grid_day_value(v,y,m):
    if v is None or (isinstance(v,float) and pd.isna(v)):
        return None
    ndays=calendar.monthrange(y,m)[1]
    if isinstance(v,(pd.Timestamp,datetime,date)):
        if int(v.year)==int(y) and int(v.month)==int(m):
            return int(v.day)
        return None
    if isinstance(v,(int,np.integer)):
        d=int(v)
        return d if 1<=d<=ndays else None
    if isinstance(v,float) and float(v).is_integer():
        d=int(v)
        return d if 1<=d<=ndays else None
    s=str(v).strip()
    mt=re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})",s)
    if mt:
        yy,mm,dd=map(int,mt.groups())
        return dd if yy==y and mm==m and 1<=dd<=ndays else None
    # Header cells like "1", "01", "1 d.", "01 Mon".
    mt=re.match(r"^\s*([0-3]?\d)(?:\s*(?:d\.?|diena|mon|tue|wed|thu|fri|sat|sun|pr|an|tr|kt|pn|st|sk))?\s*$",s,re.I)
    if mt:
        d=int(mt.group(1))
        return d if 1<=d<=ndays else None
    return None


def _research_grid_dept_family(v):
    n=_research_norm(v)
    if not n:
        return None
    if "centroro" in n:
        return "CENTRO RO"
    if "onkoro" in n or ("onko" in n and "ro" in n):
        return "Onko RO"
    if "centroug" in n:
        return "Centro UG"
    if "spsug" in n:
        return "SPS UG"
    if "spsro" in n:
        return "SPS RO"
    if "144" in n:
        return "ADC 144"
    if re.search(r"(?:^|adc)145",n) or n.startswith("145"):
        return "ADC 145"
    if "vaik" in n and "ug" in n:
        return "Vaikų UG"
    if "mamograf" in n:
        return "Mamografijos"
    return None


def _research_grid_schedule_candidate(raw,y,m):
    """Detect classic grafikas matrix: department rows × calendar-day columns."""
    best=None
    max_header=min(len(raw)-1,60)
    for hr in range(max_header+1):
        day_cols=[]
        for col_idx,v in enumerate(raw.iloc[hr].tolist()):
            day=_research_grid_day_value(v,y,m)
            if day is not None:
                day_cols.append((col_idx,day))
        unique_days={d for _,d in day_cols}
        if len(unique_days)<3:
            continue

        recognized=[]
        for ridx in range(hr+1,len(raw)):
            vals=raw.iloc[ridx].tolist()
            descriptor=" | ".join(
                str(vals[c]).strip()
                for c in range(min([x[0] for x in day_cols]+[len(vals)]))
                if c<len(vals) and _research_nonempty(vals[c])
            )
            fam=_research_grid_dept_family(descriptor)
            if fam:
                recognized.append((ridx,fam,descriptor))
        if len(recognized)<2:
            continue
        score=20+len(unique_days)+len(recognized)*2
        cand={
            "score":score,"header_row":hr,
            "day_cols":day_cols,"recognized_rows":recognized,
            "raw":raw,
        }
        if best is None or score>best["score"]:
            best=cand
    return best


def _research_schedule_colmap(df):
    aliases={
        "slot_id":["slot_id","slotid","id"],
        "date":["date","data"],
        "day":["day","diena"],
        "department":["department","skyrius","vieta","padalinys"],
        "shift":["shift","pamaina","block","laikas"],
        "person":["person","zmogus","rezidentas","initials","inic"],
    }
    actual={_research_norm(c):c for c in df.columns}
    out={}
    for k,opts in aliases.items():
        for opt in opts:
            if _research_norm(opt) in actual:
                out[k]=actual[_research_norm(opt)]; break
    return out

def _research_day_from_value(v,y,m):
    if isinstance(v,(pd.Timestamp,datetime,date)):
        return int(v.day)
    s=str(v)
    mt=re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})",s)
    if mt:
        yy,mm,dd=map(int,mt.groups())
        if yy!=y or mm!=m: raise ValueError(f"Date {s} is outside selected month {y}-{m:02d}.")
        return dd
    nums=re.findall(r"(?<!\d)([0-3]?\d)(?!\d)",s)
    if nums: return int(nums[-1])
    raise ValueError(f"Could not read date/day value: {v}")

def _research_dept_key(v):
    n=_research_norm(v)
    n=n.replace("kabinetas","").replace("kab","")
    return n

def _research_slot_family(slot):
    return _research_grid_dept_family(slot.department)


def _research_cell_people(v,exact_initials,known_names):
    if not _research_nonempty(v):
        return [],[]
    raw=str(v).strip()
    whole=exact_initials.get(raw.casefold()) or known_names.get(_research_norm(raw))
    if whole:
        return [whole],[]
    parts=[
        p.strip()
        for p in re.split(r"[\n,;/|]+",raw)
        if p and p.strip()
    ]
    found=[]; unknown=[]
    for part in parts:
        person=exact_initials.get(part.casefold()) or known_names.get(_research_norm(part))
        if person:
            found.append(person)
        else:
            unknown.append(part)
    return found,unknown


def research_assignments_from_excel(uploaded,y,m,return_audit=False):
    tables,audit=_research_scan_workbook(uploaded,"schedule",y,m)
    if not tables:
        raise ValueError(
            "No compatible grafikas table was found anywhere in the workbook. "
            "The importer scanned every worksheet."
        )

    slots=make_slots(y,m)
    slot_by_id={s.idx:s for s in slots}
    assignments={}
    provenance={}
    warnings=[]
    duplicates=[]
    conflicts=[]
    exact_initials={p["initials"].casefold():p["initials"] for p in DEFAULT_PEOPLE}
    exact_initials.update({"sk":"SŠ","sr":"SP"})  # V2.5.113 historical-import compatibility
    known_names={_research_norm(p["name"]):p["initials"] for p in DEFAULT_PEOPLE}

    for table in tables:
        if table.get("mode")=="grid":
            raw=table["raw"]
            local_used=set()
            day_cols=table["day_cols"]
            recognized_rows=sorted(table["recognized_rows"],key=lambda x:x[0])

            for ridx,fam,descriptor in recognized_rows:
                explicit_block=_research_shift(descriptor)
                for col_idx,day in day_cols:
                    if col_idx>=raw.shape[1]:
                        continue
                    cell=raw.iloc[ridx,col_idx]
                    persons,unknown_parts=_research_cell_people(cell,exact_initials,known_names)
                    for unknown in unknown_parts:
                        warnings.append(
                            f"{table['sheet']} row {int(ridx)+1}, day {day}: "
                            f"unknown resident/cell value '{unknown}'."
                        )
                    if not persons:
                        continue

                    candidates=[
                        s for s in slots
                        if s.day==day
                        and not s.blocked
                        and _research_slot_family(s)==fam
                        and s.idx not in local_used
                    ]
                    if explicit_block:
                        candidates=[s for s in candidates if s.block==explicit_block]

                    for person in persons:
                        if not candidates:
                            warnings.append(
                                f"{table['sheet']} row {int(ridx)+1}, day {day}: "
                                f"no remaining slot for {fam}"
                                + (f" {explicit_block}" if explicit_block else "")
                                + f" while reading '{cell}'."
                            )
                            break
                        s=sorted(candidates,key=lambda x:x.idx)[0]
                        candidates=[x for x in candidates if x.idx!=s.idx]
                        local_used.add(s.idx)
                        sid=s.idx
                        src={
                            "workbook_hash":table["workbook_hash"],
                            "sheet":table["sheet"],
                            "source_row":int(ridx)+1,
                            "source_column":int(col_idx)+1,
                            "day":int(day),
                            "header_row":table["header_row"],
                            "mode":"grid",
                        }
                        if sid in assignments:
                            previous=assignments[sid]
                            prev_src=provenance[sid]
                            if previous==person:
                                duplicates.append({
                                    "slot_id":sid,"person":person,
                                    "first_source":prev_src,"duplicate_source":src,
                                })
                            else:
                                conflicts.append({
                                    "slot_id":sid,
                                    "existing_person":previous,
                                    "new_person":person,
                                    "existing_source":prev_src,
                                    "new_source":src,
                                })
                            continue
                        assignments[sid]=person
                        provenance[sid]=src
            continue

        df=table["df"]; cmap=table["cmap"]
        for ridx,r in df.iterrows():
            raw_person=r.get(cmap["person"])
            if not _research_nonempty(raw_person):
                continue
            raw_person_text=str(raw_person).strip()
            person=exact_initials.get(raw_person_text.casefold()) or known_names.get(_research_norm(raw_person_text))
            src={
                "workbook_hash":table["workbook_hash"],
                "sheet":table["sheet"],
                "source_row":int(ridx)+1,
                "header_row":table["header_row"],
            }
            if not person:
                warnings.append(
                    f"{table['sheet']} row {int(ridx)+1}: unknown resident '{raw_person_text}'."
                )
                continue

            sid=None
            if "slot_id" in cmap:
                raw=r.get(cmap["slot_id"])
                try:
                    candidate=int(float(raw))
                    if candidate in slot_by_id:
                        sid=candidate
                except Exception:
                    pass

            if sid is None:
                if "date" in cmap:
                    day=_research_day_from_value(r.get(cmap["date"]),y,m)
                elif "day" in cmap:
                    day=_research_day_from_value(r.get(cmap["day"]),y,m)
                else:
                    warnings.append(
                        f"{table['sheet']} row {int(ridx)+1}: no usable slot_id/date/day."
                    )
                    continue
                if day is None:
                    warnings.append(
                        f"{table['sheet']} row {int(ridx)+1}: date/day does not belong to {y}-{m:02d}."
                    )
                    continue
                if "department" not in cmap or "shift" not in cmap:
                    warnings.append(
                        f"{table['sheet']} row {int(ridx)+1}: grafikas row needs department and shift."
                    )
                    continue
                dep=_research_dept_key(r.get(cmap["department"]))
                block=_research_shift(r.get(cmap["shift"]))
                candidates=[
                    s for s in slots
                    if s.day==day and s.block==block and not s.blocked
                ]
                exact=[s for s in candidates if _research_dept_key(s.department)==dep]
                if not exact and dep.startswith("centroro"):
                    exact=[s for s in candidates if _research_dept_key(s.department).startswith("centroro")]
                if not exact:
                    warnings.append(
                        f"{table['sheet']} row {int(ridx)+1}: no matching slot for day {day}, "
                        f"department '{r.get(cmap['department'])}', shift '{block}'."
                    )
                    continue

                # If a generic department label maps to several identical CENTRO rows,
                # choose the first still-unused slot. This preserves every assignment
                # instead of collapsing repeated rows onto one slot.
                unused=[s for s in sorted(exact,key=lambda s:s.idx) if s.idx not in assignments]
                sid=(unused[0] if unused else sorted(exact,key=lambda s:s.idx)[0]).idx

            if sid in assignments:
                previous=assignments[sid]
                prev_src=provenance[sid]
                if previous==person:
                    duplicates.append({
                        "slot_id":sid,"person":person,
                        "first_source":prev_src,"duplicate_source":src,
                    })
                    continue
                conflicts.append({
                    "slot_id":sid,
                    "existing_person":previous,
                    "new_person":person,
                    "existing_source":prev_src,
                    "new_source":src,
                })
                continue

            assignments[sid]=person
            provenance[sid]=src

    audit["warnings"]=warnings
    audit["duplicates"]=duplicates
    audit["conflicts"]=conflicts
    audit["assignment_count"]=len(assignments)
    audit["assignment_provenance"]={str(k):v for k,v in provenance.items()}

    if conflicts:
        preview="; ".join(
            f"slot {c['slot_id']}: {c['existing_person']} vs {c['new_person']} "
            f"({c['existing_source']['sheet']} / {c['new_source']['sheet']})"
            for c in conflicts[:6]
        )
        raise ValueError(
            "Whole-workbook grafikas import found conflicting assignments for the same slot. "
            "Official lock is blocked until resolved: "+preview
        )

    if return_audit:
        return assignments,warnings,audit
    return assignments,warnings



def research_manual_result(y,m,people,assignments):
    targets=_research_targets(y,m,people)
    stats=validate_schedule(y,m,people,make_slots(y,m),assignments,targets)
    return SolveResult(ok=stats["global"]["hard_errors"]==0,
                       message="Imported Bendrinis DI + seniūnė schedule",assignments=assignments,targets=targets,stats=stats)


def _research_json_safe(value):
    """Convert engine/research structures into stable JSON-compatible primitives."""
    if value is None or isinstance(value,(str,bool,int)):
        return value
    if isinstance(value,float):
        if pd.isna(value):
            return None
        return float(value)
    if isinstance(value,(date,datetime)):
        return value.isoformat()
    if isinstance(value,set):
        return sorted(_research_json_safe(v) for v in value)
    if isinstance(value,(list,tuple)):
        return [_research_json_safe(v) for v in value]
    if isinstance(value,dict):
        return {str(k):_research_json_safe(v) for k,v in value.items()}
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        return value.item()
    except Exception:
        return str(value)


def _research_people_snapshot(people):
    rows=[]
    for p in people:
        rows.append({
            "initials":p.initials,
            "name":p.name,
            "unavailable":sorted(p.unavailable),
            "unavailable_am":sorted(p.unavailable_am),
            "unavailable_pm":sorted(p.unavailable_pm),
            "vacation":sorted(p.vacation),
            "justified_absence":sorted(p.justified_absence),
            "long_duty":sorted(p.long_duty),
            "reserved_backup":[list(x) for x in sorted(p.reserved_backup)],
            "soft_free":sorted(p.soft_free),
            "soft_free_am":sorted(p.soft_free_am),
            "soft_free_pm":sorted(p.soft_free_pm),
            "preferred":sorted(p.preferred),
            "preferred_am":sorted(p.preferred_am),
            "preferred_pm":sorted(p.preferred_pm),
            "weekday_preference":p.weekday_preference,
            "weekend_preference":p.weekend_preference,
            "holiday_preference":p.holiday_preference,
            "spread_preference":p.spread_preference,
            "shift_length_preference":int(getattr(p,"shift_length_preference",0) or 0),
            "avoid_doubles":bool(p.avoid_doubles),
            "target_adjustment":p.target_adjustment,
            "prior_weekend_count":p.prior_weekend_count,
            "prior_friday_count":p.prior_friday_count,
            "prior_double_count":p.prior_double_count,
            "prior_weekday_day_count":p.prior_weekday_day_count,
            "prior_rotation_counts":dict(p.prior_rotation_counts or {}),
            "prior_consecutive_weekend_streak":int(getattr(p,"prior_consecutive_weekend_streak",0) or 0),
            "prior_last_day_onko":bool(getattr(p,"prior_last_day_onko",False)),
            "prior_resident_hard_loss_count":int(getattr(p,"prior_resident_hard_loss_count",0) or 0),
            "request_items":_research_json_safe(list(getattr(p,"request_items",[]) or [])),
            "rest_credit_am_to_use":int(getattr(p,"rest_credit_am_to_use",0) or 0),
            "rest_credit_pm_to_use":int(getattr(p,"rest_credit_pm_to_use",0) or 0),
            "note":str(getattr(p,"note","") or ""),
        })
    return _research_json_safe(rows)


def _research_people_from_snapshot(rows):
    people=[]
    for r in rows or []:
        people.append(Person(
            initials=str(r.get("initials","")),
            name=str(r.get("name","")),
            unavailable=set(r.get("unavailable") or []),
            unavailable_am=set(r.get("unavailable_am") or []),
            unavailable_pm=set(r.get("unavailable_pm") or []),
            vacation=set(r.get("vacation") or []),
            justified_absence=set(r.get("justified_absence") or []),
            long_duty=set(r.get("long_duty") or []),
            reserved_backup={tuple(x) for x in (r.get("reserved_backup") or [])},
            soft_free=set(r.get("soft_free") or []),
            soft_free_am=set(r.get("soft_free_am") or []),
            soft_free_pm=set(r.get("soft_free_pm") or []),
            preferred=set(r.get("preferred") or []),
            preferred_am=set(r.get("preferred_am") or []),
            preferred_pm=set(r.get("preferred_pm") or []),
            weekday_preference=int(r.get("weekday_preference") or 0),
            weekend_preference=int(r.get("weekend_preference") or 0),
            holiday_preference=max(-1,min(1,int(r.get("holiday_preference") or 0))),
            spread_preference=int(r.get("spread_preference") or 0),
            shift_length_preference=max(0,min(3,int(r.get("shift_length_preference") or 0))),
            avoid_doubles=bool(r.get("avoid_doubles",False)),
            target_adjustment=int(r.get("target_adjustment") or 0),
            prior_weekend_count=int(r.get("prior_weekend_count") or 0),
            prior_friday_count=int(r.get("prior_friday_count") or 0),
            prior_double_count=int(r.get("prior_double_count") or 0),
            prior_weekday_day_count=int(r.get("prior_weekday_day_count") or 0),
            prior_rotation_counts={str(k):int(v) for k,v in (r.get("prior_rotation_counts") or {}).items()},
            prior_consecutive_weekend_streak=int(r.get("prior_consecutive_weekend_streak") or 0),
            prior_last_day_onko=bool(r.get("prior_last_day_onko",False)),
            prior_resident_hard_loss_count=int(r.get("prior_resident_hard_loss_count") or 0),
            request_items=list(r.get("request_items") or []),
            rest_credit_am_to_use=int(r.get("rest_credit_am_to_use") or 0),
            rest_credit_pm_to_use=int(r.get("rest_credit_pm_to_use") or 0),
            note=str(r.get("note") or ""),
        ))
    return people


def _research_hash(value):
    raw=json.dumps(
        _research_json_safe(value),
        ensure_ascii=False,sort_keys=True,separators=(",",":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _research_input_hash(y,m,people):
    # Rule Profile / engine version are stored separately and server-locked per case.
    return _research_hash({
        "cycle_year":int(y),
        "cycle_month":int(m),
        "people":_research_people_snapshot(people),
    })


def _research_schedule_hash(assignments):
    return _research_hash({str(k):v for k,v in sorted((assignments or {}).items())})


def _research_locked_comparator(case,people):
    assignments={int(k):v for k,v in (case.get("comparator_assignments") or {}).items()}
    return research_manual_result(int(case["cycle_year"]),int(case["cycle_month"]),people,assignments)


def _research_result_from_run(run,people,y,m):
    assignments={int(k):v for k,v in (run.get("assignments") or {}).items()}
    frozen_stats=run.get("raw_metrics") or {}
    if not isinstance(frozen_stats,dict) or "global" not in frozen_stats:
        # Old/partial data safety fallback; research runs created by V2.5.41 store full stats.
        frozen_stats=validate_schedule(y,m,people,make_slots(y,m),assignments,_research_targets(y,m,people))
    return SolveResult(
        ok=bool(run.get("success")),
        message=f"Frozen research run {run.get('run_no')}",
        assignments=assignments,
        targets=_research_targets(y,m,people),
        stats=frozen_stats,
        objective_value=None,
    )


def _research_metric_rows(comparator,engine_result,engine_label="Specializuotas variklis — 1 bandymas"):
    cg=comparator.stats.get("global",{})
    eg=engine_result.stats.get("global",{})
    defs=[
        ("Privalomų taisyklių klaidos","hard_errors",False),
        ("Mėnesio teisingumas %","monthly_fairness_score",True),
        ("Kaupiamasis teisingumas %","cumulative_fairness_score",True),
        ("Pageidavimų įvykdymas %","mean_preference_score",True),
        ("Mėnesio darbo vietų netolygumas","rotation_monthly_imbalance",False),
        ("Kaupiamasis darbo vietų netolygumas","rotation_cumulative_imbalance",False),
        ("Savaitgalių skirtumas","weekend_monthly_spread",False),
        ("Penktadienių skirtumas","friday_monthly_spread",False),
        ("Dublių skirtumas","double_monthly_spread",False),
        ("Darbo dienų skirtumas","weekday_day_monthly_spread",False),
        ("Vidutinis skirtingų darbo vietų skaičius","mean_distinct_rotations",True),
        ("Neužpildytų vietų skaičius","optional_gap_count",False),
        ("Neužpildytų darbo vietų skirtumas","optional_gap_category_spread",False),
    ]
    rows=[]
    for label,key,higher in defs:
        a=cg.get(key); b=eg.get(key)
        delta=None
        if isinstance(a,(int,float)) and isinstance(b,(int,float)):
            delta=round(float(b)-float(a),2)
        better=""
        if delta is not None and delta!=0:
            better=engine_label if (delta>0)==higher else "Bendrinis DI + seniūnė"
        elif delta==0:
            better="Vienoda"
        rows.append({
            "Rodiklis":label,
            "Bendrinis DI + seniūnė":a,
            engine_label:b,
            f"Pokytis: {engine_label} − Bendrinis DI + seniūnė":delta,
            "Geresnis rezultatas":better,
        })
    return pd.DataFrame(rows)



def _research_post_matrix_df(result,people,include_summary=True):
    """Resident × workplace assignment-count matrix for paper-ready export."""
    pdata=(result.stats or {}).get("people",{})
    rows=[]
    for p in people:
        d=pdata.get(p.initials,{})
        rc=d.get("rotation_counts") or {}
        row={
            "Inicialai":p.initials,
            "Vardas":p.name,
        }
        for cat in ROTATION_CATEGORIES:
            row[cat]=int(rc.get(cat,0) or 0)
        row["Skirtingų darbo vietų"]=int(d.get("distinct_rotations",0) or 0)
        row["Paskyrimų iš viso"]=int(d.get("assignments",0) or 0)
        row["Darbo krūvis"]=d.get("workload")
        rows.append(row)

    df=pd.DataFrame(rows)
    if not include_summary or df.empty:
        return df

    summary=[]
    for label,func in [
        ("MAX",lambda s:int(s.max())),
        ("MIN",lambda s:int(s.min())),
        ("SKIRTUMAS (DIDŽ.–MAŽ.)",lambda s:int(s.max()-s.min())),
    ]:
        r={"Inicialai":label,"Vardas":""}
        for cat in ROTATION_CATEGORIES:
            r[cat]=func(df[cat])
        r["Skirtingų darbo vietų"]=""
        r["Paskyrimų iš viso"]=""
        r["Darbo krūvis"]=""
        summary.append(r)
    return pd.concat([df,pd.DataFrame(summary)],ignore_index=True)


def _research_post_stats(result,people):
    """Per-workplace supply and resident spread."""
    matrix=_research_post_matrix_df(result,people,include_summary=False)
    rows={}
    for cat in ROTATION_CATEGORIES:
        vals=[int(v) for v in matrix[cat].tolist()] if not matrix.empty else []
        rows[cat]={
            "total":sum(vals),
            "mean":round(sum(vals)/len(vals),2) if vals else 0.0,
            "min":min(vals) if vals else 0,
            "max":max(vals) if vals else 0,
            "spread":(max(vals)-min(vals)) if vals else 0,
        }
    return rows


def _research_post_spread_comparison_df(
    comparator,people,run1_result=None,best_result=None,best_label="Best"
):
    arms=[
        ("Bendrinis DI + seniūnė",comparator),
        ("1 bandymas",run1_result),
        (best_label,best_result),
    ]
    arm_stats={
        label:_research_post_stats(result,people)
        for label,result in arms if result is not None
    }
    rows=[]
    for cat in ROTATION_CATEGORIES:
        row={"Darbo vieta":cat}
        for label,_result in arms:
            stt=(arm_stats.get(label) or {}).get(cat)
            if stt is None:
                row[f"{label} iš viso"]=None
                row[f"{label} min"]=None
                row[f"{label} max"]=None
                row[f"{label} skirtumas"]=None
            else:
                row[f"{label} iš viso"]=stt["total"]
                row[f"{label} min"]=stt["min"]
                row[f"{label} max"]=stt["max"]
                row[f"{label} skirtumas"]=stt["spread"]

        gh=(arm_stats.get("Bendrinis DI + seniūnė") or {}).get(cat)
        r1=(arm_stats.get("1 bandymas") or {}).get(cat)
        rb=(arm_stats.get(best_label) or {}).get(cat)
        row["Δ 1-ojo bandymo skirtumas vs Bendrinis DI + seniūnė"]=(
            None if gh is None or r1 is None else int(r1["spread"]-gh["spread"])
        )
        row[f"Δ {best_label} skirtumas vs Bendrinis DI + seniūnė"]=(
            None if gh is None or rb is None else int(rb["spread"]-gh["spread"])
        )
        rows.append(row)

    # Overall row = sum of the nine independent post spreads, matching the
    # engine's monthly workplace imbalance concept.
    total_row={"Darbo vieta":"BENDRAS DARBO VIETŲ NETOLYGUMAS (Σ skirtumų)"}
    for label,_result in arms:
        stats=arm_stats.get(label)
        total_row[f"{label} iš viso"]=None
        total_row[f"{label} min"]=None
        total_row[f"{label} max"]=None
        total_row[f"{label} skirtumas"]=(
            None if stats is None else sum(int(stats[c]["spread"]) for c in ROTATION_CATEGORIES)
        )
    gh_total=total_row.get("Bendrinis DI + seniūnė skirtumas")
    r1_total=total_row.get("1 bandymas skirtumas")
    best_total=total_row.get(f"{best_label} skirtumas")
    total_row["Δ 1-ojo bandymo skirtumas vs Bendrinis DI + seniūnė"]=(
        None if gh_total is None or r1_total is None else int(r1_total-gh_total)
    )
    total_row[f"Δ {best_label} skirtumas vs Bendrinis DI + seniūnė"]=(
        None if gh_total is None or best_total is None else int(best_total-gh_total)
    )
    rows.append(total_row)
    return pd.DataFrame(rows)


def _research_run_quality_key(run):
    """Transparent secondary best-of-run selector using the V2.5.49 constitution.

    Order is lexicographic: ABSOLUTE-HARD validity -> mandatory zero RESIDENT-HARD
    violations -> post equality ->
    MAX-MIN SOFT satisfaction -> mean SOFT satisfaction -> monthly fairness ->
    diversity. Overall request satisfaction is a final descriptive tie-breaker.
    """
    hard=run.get("hard_errors")
    hard=9999 if hard is None else int(hard)
    g=((run.get("full_stats") or {}).get("global",{}) if isinstance(run.get("full_stats"),dict) else {})
    rh_total=float(g.get("resident_hard_total_losses") if g.get("resident_hard_total_losses") is not None else 1e9)
    rh_max=float(g.get("resident_hard_max_loss_per_resident") if g.get("resident_hard_max_loss_per_resident") is not None else 1e9)
    rh_cum_spread=float(g.get("resident_hard_cumulative_spread") if g.get("resident_hard_cumulative_spread") is not None else 1e9)
    worst_post=float(g.get("worst_monthly_post_spread") if g.get("worst_monthly_post_spread") is not None else 1e9)
    imb=run.get("monthly_workplace_imbalance")
    imb=1e9 if imb is None else float(imb)
    soft_min=g.get("min_soft_preference_score")
    soft_min=-1e9 if soft_min is None else float(soft_min)
    soft_mean=g.get("mean_soft_preference_score")
    soft_mean=-1e9 if soft_mean is None else float(soft_mean)
    fair=run.get("monthly_fairness")
    fair=-1e9 if fair is None else float(fair)
    div=run.get("mean_distinct_workplaces")
    div=-1e9 if div is None else float(div)
    overall=g.get("mean_preference_score")
    overall=-1e9 if overall is None else float(overall)
    return (
        hard,rh_total,rh_max,rh_cum_spread,worst_post,imb,
        -soft_min,-soft_mean,-fair,-div,-overall,int(run.get("run_no") or 999)
    )


def _research_run_log_df(runs):
    rows=[]
    total=0.0
    for r in runs:
        total+=float(r.get("elapsed_seconds") or 0)
        rg=((r.get("full_stats") or {}).get("global",{}) if isinstance(r.get("full_stats"),dict) else {})
        rows.append({
            "Bandymas":int(r.get("run_no") or 0),
            "Paskirtis":"PIRMAS BANDYMAS (PAGRINDINIS)" if int(r.get("run_no") or 0)==1 else "TOBULINIMO BANDYMAS",
            "Sėkmė":bool(r.get("success")),
            "Laikas, s":round(float(r.get("elapsed_seconds") or 0),2),
            "Sukauptas laikas, s":round(total,2),
            "Variklio versija":r.get("app_version"),
            "Taisyklių profilis":r.get("rule_profile_version"),
            "Skaičiavimo etapas":r.get("solver_stage"),
            "Privalomų saugos taisyklių klaidos":r.get("hard_errors"),
            "„Dirbti negaliu“ pažeidimai":rg.get("resident_hard_total_losses"),
            "Didž. „Dirbti negaliu“ pažeidimų vienam":rg.get("resident_hard_max_loss_per_resident"),
            "Kaupiamasis „Dirbti negaliu“ skirtumas":rg.get("resident_hard_cumulative_spread"),
            "Mėnesio teisingumas %":r.get("monthly_fairness"),
            "Bendras pageidavimų įvykdymas %":rg.get("mean_preference_score"),
            "Mažiausias pageidavimų įvykdymas %":rg.get("min_soft_preference_score"),
            "Pageidavimų įvykdymo skirtumas, proc. p.":rg.get("soft_preference_score_spread"),
            "Didžiausias darbo vietos skirtumas":rg.get("worst_monthly_post_spread"),
            "Didžiausio darbo vietos skirtumo riba":rg.get("post_system_hard_worst_spread_lock"),
            "9 darbo vietų bendro skirtumo riba":rg.get("post_system_hard_total_spread_lock"),
            "Skirtingų darbo vietų skaičiaus skirtumas":rg.get("distinct_rotation_spread"),
            "Darbo vietų tolygumo patikra":rg.get("post_spread_quality_gate_passed"),
            "Mėnesio darbo vietų netolygumas":r.get("monthly_workplace_imbalance"),
            "Savaitgalių skirtumas":r.get("weekend_spread"),
            "Penktadienių skirtumas":r.get("friday_spread"),
            "Penktadienių 0–1 patikra":("ATITINKA" if (r.get("friday_spread") is not None and int(r.get("friday_spread") or 0)<=1) else "SENA / NETINKAMA"),
            "Dublių skirtumas":r.get("double_spread"),
            "Darbo dienų skirtumas":r.get("weekday_day_spread"),
            "Skirtingos darbo vietos":r.get("mean_distinct_workplaces"),
            "Neužpildytų vietų skaičius":r.get("gap_count"),
            "Neužpildytų darbo vietų skirtumas":r.get("gap_category_spread"),
        })
    return pd.DataFrame(rows)


def _research_result_wish_totals(result):
    """Comparable request totals from one validated result."""
    out={"active":0,"honored":0,"missed":0,"hard":0,"hard_missed":0,"exact_soft":0,"exact_soft_missed":0}
    for initials,d in ((result.stats or {}).get("people",{}) or {}).items():
        for r in (d.get("request_detail_rows") or []):
            if not r.get("included_in_score"):
                continue
            out["active"]+=1
            ok=bool(r.get("fulfilled"))
            out["honored"]+=int(ok); out["missed"]+=int(not ok)
            if r.get("kind")=="resident_hard":
                out["hard"]+=1; out["hard_missed"]+=int(not ok)
            if r.get("kind") in ("soft_free","preferred"):
                out["exact_soft"]+=1; out["exact_soft_missed"]+=int(not ok)
    out["percent"]=(None if out["active"]==0 else round(100.0*out["honored"]/out["active"],1))
    return out


def _research_wish_summary_comparison_df(comparator,engine_result,people):
    """Per-resident wish fulfilment using the SAME frozen input snapshot."""
    rows=[]
    cp=(comparator.stats or {}).get("people",{}) or {}
    ep=(engine_result.stats or {}).get("people",{}) or {}
    for p in people:
        c=cp.get(p.initials,{}) or {}; e=ep.get(p.initials,{}) or {}
        cdet=[r for r in (c.get("request_detail_rows") or []) if r.get("included_in_score")]
        edet=[r for r in (e.get("request_detail_rows") or []) if r.get("included_in_score")]
        active=max(len(cdet),len(edet))
        c_ok=sum(1 for r in cdet if r.get("fulfilled")); e_ok=sum(1 for r in edet if r.get("fulfilled"))
        rows.append({
            "Rezidentas":p.initials,
            "Vardas":p.name,
            "Aktyvūs pageidavimai":active,
            "Bendrinis DI + seniūnė — įvykdyta":c_ok,
            "Bendrinis DI + seniūnė — neįvykdyta":max(0,len(cdet)-c_ok),
            "Bendrinis DI + seniūnė — įvykdymas %":(None if not cdet else round(100*c_ok/len(cdet),1)),
            "Bendrinis DI + seniūnė — „Dirbti negaliu“ pažeidimai":int(c.get("resident_hard_losses",0) or 0),
            "Specializuotas variklis — įvykdyta":e_ok,
            "Specializuotas variklis — neįvykdyta":max(0,len(edet)-e_ok),
            "Specializuotas variklis — įvykdymas %":(None if not edet else round(100*e_ok/len(edet),1)),
            "Specializuotas variklis — „Dirbti negaliu“ pažeidimai":int(e.get("resident_hard_losses",0) or 0),
        })
    return pd.DataFrame(rows)


def _research_wish_request_comparison_df(comparator,engine_result,people):
    """Request-by-request paired outcomes; request_id is stable under one frozen snapshot."""
    rows=[]
    cp=(comparator.stats or {}).get("people",{}) or {}
    ep=(engine_result.stats or {}).get("people",{}) or {}
    for p in people:
        crows={str(r.get("request_id")):r for r in (cp.get(p.initials,{}).get("request_detail_rows") or []) if r.get("included_in_score")}
        erows={str(r.get("request_id")):r for r in (ep.get(p.initials,{}).get("request_detail_rows") or []) if r.get("included_in_score")}
        keys=list(dict.fromkeys(list(crows)+list(erows)))
        for key in keys:
            c=crows.get(key) or {}; e=erows.get(key) or {}
            base=c or e
            c_ok=(None if not c else bool(c.get("fulfilled")))
            e_ok=(None if not e else bool(e.get("fulfilled")))
            if c_ok is True and e_ok is True: verdict="Abu įvykdyti"
            elif c_ok is False and e_ok is True: verdict="Tik specializuotas variklis"
            elif c_ok is True and e_ok is False: verdict="Tik bendrinis DI + seniūnė"
            elif c_ok is False and e_ok is False: verdict="Abu neįvykdyti"
            else: verdict="Patikros neatitikimas"
            rows.append({
                "Rezidentas":p.initials,
                "Vardas":p.name,
                "Pageidavimo ID":key,
                "Pirmenybė":base.get("priority"),
                "Pageidavimas":base.get("type"),
                "Data":base.get("date") or "—",
                "Laikas":base.get("block") or "—",
                "Pageidauta reikšmė":base.get("requested_value"),
                "Bendrinis DI + seniūnė":("ĮVYKDYTA" if c_ok is True else "NEĮVYKDYTA" if c_ok is False else "TRŪKSTA"),
                "Specializuotas variklis — 1 bandymas":("ĮVYKDYTA" if e_ok is True else "NEĮVYKDYTA" if e_ok is False else "TRŪKSTA"),
                "Rezultatas":verdict,
            })
    return pd.DataFrame(rows)


def research_locked_comparison_xlsx(y,m,case,people,comparator,runs,questionnaires=None):
    bio=BytesIO()
    valid_runs=[r for r in runs if bool(r.get("success")) and int(r.get("hard_errors") or 0)==0]
    best=min(valid_runs,key=_research_run_quality_key) if valid_runs else None
    first=next((r for r in runs if int(r.get("run_no") or 0)==1),None)

    with pd.ExcelWriter(bio,engine="xlsxwriter") as w:
        # Method / audit trail.
        method_rows=[
            ["Tyrimo palyginimas","Grafikų sudarymo metodų palyginimas"],
            ["Laikotarpis",f"{y}-{m:02d}"],
            ["Primary engine endpoint","Immutable PIRMAS BANDYMAS — 1 bandymas"],
            ["Secondary endpoint","BEST-OF-5 after up to 4 additional tobulinimo bandymass"],
            ["Best-of-5 selector","ABSOLUTE-HARD-valid → zero RESIDENT-HARD violations → lower post imbalance → max-min SOFT → monthly fairness → diversity"],
            ["Max engine runs",case.get("engine_max_runs",5)],
            ["Locked input hash",case.get("input_hash")],
            ["Wish comparison rule","Both schedules are validated against the exact same frozen input snapshot"],
            ["Locked Bendrinis DI + seniūnė grafikas hash",case.get("comparator_schedule_hash")],
            ["Engine version at lock",case.get("app_version_at_lock")],
            ["Rule Profile at lock",case.get("rule_profile_version_at_lock")],
            ["Bendrinis DI + seniūnė iteration/rework count",case.get("gpt_human_iterations")],
            ["Bendrinis DI + seniūnė estimated total time, min",case.get("gpt_human_minutes")],
            ["Bendrinis DI + seniūnė method note",case.get("method_note")],
            ["Questionnaires stored",len(questionnaires or [])],
            ["Questionnaire respondents",", ".join(sorted(str(q.get("respondent_initials")) for q in (questionnaires or [])))],
            ["Case locked at",case.get("created_at")],
            ["Critical integrity rule","1 bandymas and all later run records are immutable; no cherry-picking replaces 1 bandymas."],
        ]
        pd.DataFrame(method_rows,columns=["Field","Value"]).to_excel(w,index=False,sheet_name="method")

        _research_run_log_df(runs).to_excel(w,index=False,sheet_name="run_log")
        snapshot_excel=[]
        for row in _research_people_snapshot(people):
            snapshot_excel.append({
                k:(json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(list,dict)) else v)
                for k,v in row.items()
            })
        pd.DataFrame(snapshot_excel).to_excel(w,index=False,sheet_name="input_snapshot")
        schedule_list_df(y,m,comparator).to_excel(w,index=False,sheet_name="gpt_human_schedule")

        # Comparator vs first shot / best.
        if first and first.get("success"):
            first_result=_research_result_from_run(first,people,y,m)
            _research_metric_rows(comparator,first_result,"Specializuotas variklis — 1 bandymas").to_excel(
                w,index=False,sheet_name="comparison_run1"
            )
            schedule_list_df(y,m,first_result).to_excel(w,index=False,sheet_name="engine_run1")
            _research_wish_summary_comparison_df(comparator,first_result,people).to_excel(
                w,index=False,sheet_name="wish_summary_run1"
            )
            _research_wish_request_comparison_df(comparator,first_result,people).to_excel(
                w,index=False,sheet_name="wish_request_compare"
            )
        if best:
            best_result=_research_result_from_run(best,people,y,m)
            _research_metric_rows(comparator,best_result,f"Specializuotas variklis — geriausias bandymas {best['run_no']}").to_excel(
                w,index=False,sheet_name="comparison_best"
            )
            schedule_list_df(y,m,best_result).to_excel(w,index=False,sheet_name="engine_best")

        # Every frozen engine run.
        for r in runs:
            if not r.get("assignments"):
                continue
            rr=_research_result_from_run(r,people,y,m)
            schedule_list_df(y,m,rr).to_excel(
                w,index=False,sheet_name=f"run_{int(r['run_no'])}_schedule"
            )

        # Per-resident comparator vs first and best.
        comp_people=comparator.stats.get("people",{})
        run1_result=_research_result_from_run(first,people,y,m) if first and first.get("success") else None
        best_result=_research_result_from_run(best,people,y,m) if best else None
        rows=[]
        for p in people:
            c=comp_people.get(p.initials,{})
            r1=(run1_result.stats.get("people",{}).get(p.initials,{}) if run1_result else {})
            rb=(best_result.stats.get("people",{}).get(p.initials,{}) if best_result else {})
            rows.append({
                "initials":p.initials,"name":p.name,
                "Bendrinis DI + seniūnė workload":c.get("workload"),
                "Run1 workload":r1.get("workload"),
                "Best workload":rb.get("workload"),
                "Bendrinis DI + seniūnė weekends":c.get("weekend_assignments"),
                "Run1 weekends":r1.get("weekend_assignments"),
                "Best weekends":rb.get("weekend_assignments"),
                "Bendrinis DI + seniūnė Fridays":c.get("friday_assignments"),
                "Run1 Fridays":r1.get("friday_assignments"),
                "Best Fridays":rb.get("friday_assignments"),
                "Bendrinis DI + seniūnė doubles":c.get("doubles"),
                "Run1 doubles":r1.get("doubles"),
                "Best doubles":rb.get("doubles"),
                "Bendrinis DI + seniūnė workplaces":c.get("distinct_rotations"),
                "Run1 workplaces":r1.get("distinct_rotations"),
                "Best workplaces":rb.get("distinct_rotations"),
                "Bendrinis DI + seniūnė pref %":c.get("preference_score"),
                "Run1 pref %":r1.get("preference_score"),
                "Best pref %":rb.get("preference_score"),
            })
        pd.DataFrame(rows).to_excel(w,index=False,sheet_name="per_resident")

        # Paper-ready resident × workplace matrices.
        _research_post_matrix_df(comparator,people).to_excel(
            w,index=False,sheet_name="post_matrix_gpt_human"
        )
        if run1_result is not None:
            _research_post_matrix_df(run1_result,people).to_excel(
                w,index=False,sheet_name="post_matrix_run1"
            )
        if best_result is not None:
            _research_post_matrix_df(best_result,people).to_excel(
                w,index=False,sheet_name="post_matrix_best"
            )

        spread_compare=_research_post_spread_comparison_df(
            comparator,people,
            run1_result=run1_result,
            best_result=best_result,
            best_label=("Geriausias" if best is None else f"Geriausias bandymas {best['run_no']}")
        )
        spread_compare.to_excel(
            w,index=False,sheet_name="post_spread_compare"
        )

        # Whole-workbook import audit / provenance.
        import_audit_rows=[]
        for item in case.get("import_warnings") or []:
            if not isinstance(item,dict) or item.get("type") not in ("WHOLE_WORKBOOK_IMPORT_AUDIT_V2544","LIVE_APP_SAME_INPUT_AUDIT_V25108"):
                continue
            if item.get("type")=="LIVE_APP_SAME_INPUT_AUDIT_V25108":
                pa=item.get("preferences") or {}
                import_audit_rows.append({
                    "Kind":"preferences",
                    "Workbook SHA-256":pa.get("snapshot_hash",""),
                    "Sheet":"Sistemos duomenys",
                    "Status":"frozen_live_snapshot",
                    "Header row":"",
                    "Rows":pa.get("resident_count",""),
                    "Reason":item.get("selected_cycle","")+" · SAME snapshot used for both schedules",
                })
            for kind in (("schedule",) if item.get("type")=="LIVE_APP_SAME_INPUT_AUDIT_V25108" else ("preferences","schedule")):
                audit=item.get(kind) or {}
                wb_hash=audit.get("workbook_hash")
                for sh in audit.get("sheets",[]) or []:
                    import_audit_rows.append({
                        "Kind":kind,
                        "Workbook SHA-256":wb_hash,
                        "Sheet":sh.get("sheet"),
                        "Status":sh.get("status"),
                        "Header row":sh.get("header_row"),
                        "Rows":sh.get("rows"),
                        "Reason":sh.get("reason",""),
                    })
                if kind=="schedule":
                    for sid,src in (audit.get("assignment_provenance") or {}).items():
                        import_audit_rows.append({
                            "Kind":"schedule_assignment_provenance",
                            "Workbook SHA-256":src.get("workbook_hash"),
                            "Sheet":src.get("sheet"),
                            "Status":f"slot_id={sid}",
                            "Header row":src.get("header_row"),
                            "Rows":src.get("source_row"),
                            "Reason":(
                                f"source_col={src.get('source_column','')} "
                                f"day={src.get('day','')} mode={src.get('mode','long')}"
                            ),
                        })
            import_audit_rows.append({
                "Kind":"case",
                "Workbook SHA-256":"",
                "Sheet":"",
                "Status":"same_workbook" if item.get("same_workbook") else "separate_workbooks",
                "Header row":"",
                "Rows":"",
                "Reason":item.get("selected_cycle",""),
            })
        pd.DataFrame(import_audit_rows or [{
            "Kind":"","Workbook SHA-256":"","Sheet":"","Status":"No whole-workbook audit stored",
            "Header row":"","Rows":"","Reason":""
        }]).to_excel(w,index=False,sheet_name="import_audit")

        # Retrospective klausimyno patikra trail.
        q_rows=[]
        for q in questionnaires or []:
            payload=q.get("parser_payload") or {}
            extracted=str(q.get("extracted_text") or "")
            if len(extracted)>30000:
                extracted=extracted[:30000]+"… [TRUNCATED IN XLSX; DB COPY RETAINED]"
            q_rows.append({
                "Respondentas":q.get("respondent_initials"),
                "Failas":q.get("file_name"),
                "File SHA-256":q.get("file_hash"),
                "MIME":q.get("mime_type"),
                "Bytes":q.get("file_size"),
                "Nuskaitytas bandymų skaičius":q.get("parsed_iterations"),
                "Nuskaitytas bendras laikas, min.":q.get("parsed_minutes"),
                "Iteration evidence":payload.get("iteration_evidence"),
                "Time evidence":payload.get("time_evidence"),
                "Locked at":q.get("created_at"),
                "Extracted text":extracted,
            })
        pd.DataFrame(q_rows or [{
            "Respondent":"","File":"","File SHA-256":"","MIME":"","Bytes":"",
            "Parsed iterations":"","Parsed total time, min":"",
            "Iteration evidence":"","Time evidence":"","Locked at":"",
            "Extracted text":"No questionnaires stored",
        }]).to_excel(w,index=False,sheet_name="questionnaires")

        # Frozen errors/findings.
        error_rows=[]
        for e in comparator.stats.get("global",{}).get("errors",[]) or []:
            error_rows.append({"Source":"Bendrinis DI + seniūnė","Finding":str(e)})
        for r in runs:
            raw=r.get("raw_metrics") or {}
            for e in (raw.get("global",{}).get("errors",[]) if isinstance(raw,dict) else []) or []:
                error_rows.append({"Source":f"ENGINE RUN {r.get('run_no')}","Finding":str(e)})
        for e in case.get("import_warnings") or []:
            error_rows.append({"Source":"IMPORT","Finding":str(e)})
        pd.DataFrame(error_rows or [{"Source":"","Finding":"No findings"}]).to_excel(
            w,index=False,sheet_name="errors_findings"
        )

    return bio.getvalue()


def _research_parse_optional_int(v):
    s=str(v or "").strip()
    if not s:
        return None
    return max(1,int(float(s)))


def _research_parse_optional_float(v):
    s=str(v or "").strip()
    if not s:
        return None
    return max(0.0,float(s))



def _questionnaire_extract_text(uploaded):
    """Extract text locally from research questionnaire uploads."""
    if uploaded is None:
        return {"ok":False,"text":"","error":"No file","file_name":"","file_hash":"","file_size":0,"mime_type":""}

    raw=uploaded.getvalue()
    name=str(getattr(uploaded,"name","questionnaire"))
    suffix=Path(name).suffix.lower()
    mime=str(getattr(uploaded,"type","") or "")
    file_hash=hashlib.sha256(raw).hexdigest()
    text=""
    error=""

    try:
        if suffix==".pdf":
            reader=PdfReader(BytesIO(raw))
            parts=[]
            for pageno,page in enumerate(reader.pages,1):
                page_text=page.extract_text() or ""
                if page_text.strip():
                    parts.append(f"[PAGE {pageno}]\n{page_text}")
            text="\n\n".join(parts)
            if not text.strip():
                error="PDF text extraction returned no text. If this is a scanned/image-only questionnaire, enter the values manually."
        elif suffix==".docx":
            doc=Document(BytesIO(raw))
            parts=[]
            for p in doc.paragraphs:
                if p.text.strip():
                    parts.append(p.text)
            for table in doc.tables:
                for row in table.rows:
                    vals=[cell.text.strip() for cell in row.cells]
                    if any(vals):
                        parts.append(" | ".join(vals))
            text="\n".join(parts)
        elif suffix in {".xlsx",".xls"}:
            xls=pd.ExcelFile(BytesIO(raw))
            parts=[]
            for sheet in xls.sheet_names:
                df=pd.read_excel(xls,sheet_name=sheet,header=None)
                parts.append(f"[SHEET {sheet}]")
                for _,row in df.iterrows():
                    vals=[
                        str(v).strip()
                        for v in row.tolist()
                        if v is not None and not (isinstance(v,float) and pd.isna(v))
                    ]
                    if vals:
                        parts.append(" | ".join(vals))
            text="\n".join(parts)
        elif suffix==".csv":
            try:
                text=raw.decode("utf-8")
            except UnicodeDecodeError:
                text=raw.decode("latin-1",errors="replace")
        elif suffix in {".txt",".md"}:
            try:
                text=raw.decode("utf-8")
            except UnicodeDecodeError:
                text=raw.decode("latin-1",errors="replace")
        else:
            error=f"Unsupported questionnaire type: {suffix or 'unknown'}"
    except Exception as exc:
        error=f"{type(exc).__name__}: {exc}"

    cleaned=re.sub(r"\r\n?","\n",text or "")
    cleaned=re.sub(r"[ \t]+"," ",cleaned)
    cleaned=re.sub(r"\n{3,}","\n\n",cleaned).strip()

    return {
        "ok":bool(cleaned),
        "text":cleaned,
        "error":error,
        "file_name":name,
        "file_hash":file_hash,
        "file_size":len(raw),
        "mime_type":mime,
    }


def _questionnaire_context(text,start,end,radius=130):
    lo=max(0,start-radius); hi=min(len(text),end+radius)
    return re.sub(r"\s+"," ",text[lo:hi]).strip()


def _questionnaire_parse_process_metrics(text):
    """Heuristic extraction of GPT-human iteration count and total time.

    It intentionally returns evidence/confidence rather than silently deciding.
    Final research metadata remains human-confirmed.
    """
    raw=str(text or "")
    norm=unicodedata.normalize("NFKD",raw).encode("ascii","ignore").decode("ascii").lower()

    iteration_candidates=[]
    iter_patterns=[
        r"(?:perdarym\w*|iteracij\w*|bandym\w*|generavim\w*|prompt\w*|atsakym\w*|iterations?|attempts?|regenerations?|revisions?)[^0-9]{0,45}(\d{1,3})",
        r"(\d{1,3})[^a-z0-9]{0,15}(?:kart\w*|iteracij\w*|bandym\w*|perdarym\w*|iterations?|attempts?|times?|revisions?)",
        r"(?:kiek\s+kart\w*|how\s+many\s+(?:times|iterations|attempts|revisions))[^0-9]{0,35}(\d{1,3})",
    ]
    for pat in iter_patterns:
        for m in re.finditer(pat,norm,flags=re.I):
            try:
                value=int(m.group(1))
            except Exception:
                continue
            if 1 <= value <= 100:
                iteration_candidates.append({
                    "value":value,
                    "context":_questionnaire_context(raw,m.start(),m.end()),
                    "pattern":pat,
                })

    time_candidates=[]
    time_patterns=[
        (r"(\d+(?:[.,]\d+)?)\s*(?:val(?:\.|and\w*)?|hours?|hrs?|h)\b",60.0,"hours"),
        (r"(\d+(?:[.,]\d+)?)\s*(?:min(?:\.|uc\w*)?|minutes?|mins?)\b",1.0,"minutes"),
        (r"(?:uztruk\w*|laik\w*|trukm\w*|duration|time)[^0-9]{0,45}(\d+(?:[.,]\d+)?)\s*(?:min(?:\.|uc\w*)?|minutes?|mins?)",1.0,"minutes"),
        (r"(?:uztruk\w*|laik\w*|trukm\w*|duration|time)[^0-9]{0,45}(\d+(?:[.,]\d+)?)\s*(?:val(?:\.|and\w*)?|hours?|hrs?|h)\b",60.0,"hours"),
    ]
    for pat,mult,unit in time_patterns:
        for m in re.finditer(pat,norm,flags=re.I):
            try:
                value=float(m.group(1).replace(",", "."))*mult
            except Exception:
                continue
            if 0 < value <= 24*60:
                time_candidates.append({
                    "minutes":round(value,2),
                    "context":_questionnaire_context(raw,m.start(),m.end()),
                    "unit":unit,
                    "pattern":pat,
                })

    # Prefer candidates whose local context explicitly mentions GPT/schedule/rework.
    def iter_rank(c):
        ctx=unicodedata.normalize("NFKD",c["context"]).encode("ascii","ignore").decode("ascii").lower()
        score=sum(k in ctx for k in ["gpt","grafik","tvarkar","iter","perdary","bandym","prompt"])
        return (-score,c["value"])

    def time_rank(c):
        ctx=unicodedata.normalize("NFKD",c["context"]).encode("ascii","ignore").decode("ascii").lower()
        score=sum(k in ctx for k in ["gpt","grafik","tvarkar","laik","truk","uztruk","schedule"])
        return (-score,c["minutes"])

    iteration_candidates=sorted(iteration_candidates,key=iter_rank)
    time_candidates=sorted(time_candidates,key=time_rank)

    best_iter=iteration_candidates[0] if iteration_candidates else None
    best_time=time_candidates[0] if time_candidates else None

    return {
        "iterations":None if best_iter is None else int(best_iter["value"]),
        "minutes":None if best_time is None else float(best_time["minutes"]),
        "iteration_evidence":None if best_iter is None else best_iter["context"],
        "time_evidence":None if best_time is None else best_time["context"],
        "iteration_candidates":iteration_candidates[:10],
        "time_candidates":time_candidates[:10],
    }


def _questionnaire_consensus(parsed_by_respondent):
    iter_vals=[
        int(v.get("iterations"))
        for v in parsed_by_respondent.values()
        if v and v.get("iterations") is not None
    ]
    time_vals=[
        float(v.get("minutes"))
        for v in parsed_by_respondent.values()
        if v and v.get("minutes") is not None
    ]
    return {
        "iterations":None if not iter_vals else int(round(median(iter_vals))),
        "minutes":None if not time_vals else round(float(median(time_vals)),1),
        "n_iterations":len(iter_vals),
        "n_minutes":len(time_vals),
    }


def _questionnaire_render_result(initials,extract,parsed):
    if not extract:
        return
    if extract.get("error"):
        st.warning(f"{initials}: {extract['error']}")
    if extract.get("ok"):
        st.success(
            f"{initials}: perskaityta {extract.get('file_name')} · "
            f"SHA-256 {extract.get('file_hash','')[:12]}…"
        )
        q1,q2=st.columns(2)
        q1.metric(
            "Rastos iteracijos",
            "Nerasta" if parsed.get("iterations") is None else parsed.get("iterations")
        )
        q2.metric(
            "Rastas bendras laikas",
            "Nerasta" if parsed.get("minutes") is None else f"{parsed.get('minutes'):g} min"
        )
        if parsed.get("iteration_evidence") or parsed.get("time_evidence"):
            with st.expander(f"{initials} — ką parseris rado",expanded=False):
                if parsed.get("iteration_evidence"):
                    st.markdown("**Iterations evidence**")
                    st.caption(parsed["iteration_evidence"])
                if parsed.get("time_evidence"):
                    st.markdown("**Laiko pagrindimas**")
                    st.caption(parsed["time_evidence"])
                st.caption(
                    "Tai automatinė teksto interpretacija, ne galutinis research outcome. "
                    "Prieš lock skaičius patvirtink / pataisyk laukeliuose žemiau."
                )



def _research_targets(y,m,people):
    """Research shadow uses the exact same workload-target calculation as Sudarymas."""
    return calculate_targets(y,m,people)


def _research_shadow_result_from_run(run,people,y,m):
    assignments={int(k):v for k,v in (run.get("assignments") or {}).items()}
    frozen_stats=run.get("full_stats") or {}
    if not isinstance(frozen_stats,dict) or "global" not in frozen_stats:
        frozen_stats=validate_schedule(
            y,m,people,make_slots(y,m),assignments,_research_targets(y,m,people)
        )
    proof=_friday_waterfill_proof(frozen_stats)
    frozen_ok=bool(run.get("success")) and bool(proof.get("passed"))
    msg=f"Frozen research shadow run {run.get('run_no')}"
    if bool(run.get("success")) and not proof.get("passed"):
        msg+=(
            f" — LEGACY FRIDAY WATER-FILL INVALID: total {proof['total']} requires "
            f"{proof['floor']}-{proof['ceil']} each, observed spread {proof['spread']}"
        )
    return SolveResult(
        ok=frozen_ok,
        message=msg,
        assignments=assignments,
        targets=_research_targets(y,m,people),
        stats=frozen_stats,
        objective_value=None,
    )


def _research_shadow_run_log_df(runs):
    rows=[]
    total=0.0
    for r in runs:
        total+=float(r.get("elapsed_seconds") or 0)
        rows.append({
            "Bandymas":int(r.get("run_no") or 0),
            "Paskirtis":"PIRMAS BANDYMAS (PAGRINDINIS)" if int(r.get("run_no") or 0)==1 else "TOBULINIMO BANDYMAS",
            "Sėkmė":bool(r.get("success")),
            "Laikas, s":round(float(r.get("elapsed_seconds") or 0),2),
            "Sukauptas laikas, s":round(total,2),
            "Variklio versija":r.get("app_version"),
            "Taisyklių profilis":r.get("rule_profile_version"),
            "Skaičiavimo etapas":r.get("solver_stage"),
            "HARD errors":r.get("hard_errors"),
            "Mėnesio teisingumas %":r.get("monthly_fairness"),
            "Preference %":r.get("preference_mean"),
            "Mėnesio darbo vietų netolygumas":r.get("monthly_workplace_imbalance"),
            "Savaitgalių skirtumas":r.get("weekend_spread"),
            "Penktadienių skirtumas":r.get("friday_spread"),
            "Dublių skirtumas":r.get("double_spread"),
            "Darbo dienų skirtumas":r.get("weekday_day_spread"),
            "Skirtingos darbo vietos":r.get("mean_distinct_workplaces"),
            "Neužpildytų vietų skaičius":r.get("gap_count"),
            "Neužpildytų darbo vietų skirtumas":r.get("gap_category_spread"),
        })
    return pd.DataFrame(rows)


def _research_people_stats_df(result):
    """Full per-resident research stats without reading operational backup tables."""
    rows=[]
    for initials,d in (result.stats or {}).get("people",{}).items():
        row={
            "Initials":initials,
            "Name":d.get("name",""),
            "Target":d.get("target"),
            "Workload":d.get("workload"),
            "Assignments":d.get("assignments"),
            "Weekday assignments":d.get("weekday_assignments"),
            "Distinct weekdays":d.get("weekday_days"),
            "Weekend assignments":d.get("weekend_assignments"),
            "Prior weekends":d.get("prior_weekend_count"),
            "Cumulative weekends":d.get("cumulative_weekend_count"),
            "Friday assignments (frozen SYSTEM run)":d.get("friday_assignments"),
            "Doubles":d.get("doubles"),
            "Max consecutive days":d.get("max_consecutive_days"),
            "Max rolling-7 hours":d.get("max_rolling7_hours"),
            "Max calendar-week hours":d.get("max_calendar_week_hours"),
            "Free days":d.get("fully_free_days"),
            "Consecutive double pairs":d.get("consecutive_double_pairs"),
            "Worked day after two doubles":d.get("worked_after_two_doubles"),
            "Skirtingos darbo vietos":d.get("distinct_rotations"),
            "RESIDENT HARD requested":d.get("resident_hard_requested"),
            "RESIDENT HARD honored":d.get("resident_hard_honored"),
            "„Dirbti negaliu“ pažeidimai":d.get("resident_hard_losses"),
            "RESIDENT HARD fulfilment %":d.get("resident_hard_score"),
            "Prior RESIDENT HARD losses":d.get("prior_resident_hard_loss_count"),
            "Cumulative RESIDENT HARD losses":d.get("cumulative_resident_hard_losses"),
            "Exact SOFT requests":d.get("exact_preference_requests"),
            "Exact SOFT honored":d.get("exact_preference_honored"),
            "Exact SOFT fulfilment %":d.get("exact_preference_score"),
            "SOFT preference %":d.get("soft_preference_score"),
            "Overall resident-request satisfaction %":d.get("overall_request_score",d.get("preference_score")),
        }
        rc=d.get("rotation_counts") or {}
        for cat in ROTATION_CATEGORIES:
            row[cat]=int(rc.get(cat,0) or 0)
        rows.append(row)
    return pd.DataFrame(rows)


def _research_global_stats_df(result):
    g=(result.stats or {}).get("global",{})
    rows=[]
    for key in sorted(g):
        value=g.get(key)
        if isinstance(value,(dict,list,tuple,set)):
            value=json.dumps(_research_json_safe(value),ensure_ascii=False,sort_keys=True)
        rows.append({"Metric":key,"Value":value})
    return pd.DataFrame(rows)


def _research_hard_errors_df(result):
    errors=list(((result.stats or {}).get("global",{}) or {}).get("errors") or [])
    return pd.DataFrame([{"#":i+1,"HARD / solver detail":e} for i,e in enumerate(errors)])


def _research_feasibility_precheck_df(y,m,people):
    """Two generous individual upper bounds: ABSOLUTE HARD vs strict RESIDENT HARD.

    The ABSOLUTE-only bound answers whether even relaxing every personal
    `Negaliu dirbti` request could ever reach the target. The strict bound shows
    whether some RESIDENT-HARD relaxation may be necessary before group
    competition and other fairness rules are considered.
    """
    targets=_research_targets(y,m,people)
    slots=make_slots(y,m)
    rows=[]

    def upper_for(p,strict_resident_hard):
        upper2=0
        for d in range(1,calendar.monthrange(y,m)[1]+1):
            ds=[]
            for sl in slots:
                if sl.day!=d or sl.blocked:
                    continue
                blocked=(
                    hard_unavailable_for_block(p,d,sl.block)
                    if strict_resident_hard else
                    absolute_unavailable_for_block(p,d,sl.block)
                )
                if not blocked:
                    ds.append(sl)
            best=0
            for a in ds:
                best=max(best,int(a.workload2))
            for ai,a in enumerate(ds):
                for b in ds[ai+1:]:
                    if blocks_overlap(a.block,b.block):
                        continue
                    best=max(best,int(a.workload2)+int(b.workload2))
            upper2+=best
        return upper2/2.0

    for p in people:
        target=float(targets.get(p.initials,0))
        strict_upper=upper_for(p,True)
        absolute_upper=upper_for(p,False)
        rows.append({
            "Inicialai":p.initials,
            "Vardas":p.name,
            "Target":target,
            "Strict zero-RESIDENT-HARD-loss max (generous)":strict_upper,
            "ABSOLUTE-HARD-only max after Resident-HARD relaxation (generous)":absolute_upper,
            "Resident-HARD relaxation may be required":bool(target>strict_upper+1e-9 and target<=absolute_upper+1e-9),
            "Clear ABSOLUTE infeasibility":bool(target>absolute_upper+1e-9),
        })
    return pd.DataFrame(rows)


def _research_input_preferences_df(people, year=None, month=None):
    """Human-readable audit of scored requests plus ignored legacy signals.

    Holiday preference is active only for months that actually contain an official
    public holiday, so a standing account setting does not create a fake scored
    request in a holiday-free research month.
    """
    rows=[]
    for p in people:
        exact_soft=(
            len(p.soft_free)+len(p.soft_free_am)+len(p.soft_free_pm)
            +len(p.preferred)+len(p.preferred_am)+len(p.preferred_pm)
        )
        holiday_active = bool(
            int(getattr(p,"holiday_preference",0) or 0)
            and year is not None and month is not None
            and public_holiday_days_in_month(int(year),int(month))
        )
        directional=sum([
            1 if p.spread_preference else 0,
            1 if holiday_active else 0,
            1 if p.avoid_doubles else 0,
        ])
        ignored_legacy_directional=sum([
            1 if p.weekday_preference else 0,
            1 if p.weekend_preference else 0,
        ])
        resident_hard=(len(p.unavailable)+len(p.unavailable_am)+len(p.unavailable_pm))
        absolute_hard=(len(p.vacation)+len(p.justified_absence)+len(p.long_duty))
        choice_items=sum(
            1 for x in (p.request_items or [])
            if x.get("included_in_score") and x.get("kind") in ("backup_claim","rest_credit")
        )
        active_overall=bool(resident_hard or exact_soft or directional or choice_items)
        rows.append({
            "Inicialai":p.initials,
            "Vardas":p.name,
            "RESIDENT HARD request units":resident_hard,
            "ABSOLUTE HARD audit units":absolute_hard,
            "Exact SOFT requests":exact_soft,
            "Scored directional SOFT settings":directional,
            "Holiday setting":({1:"Prefer work",0:"Neutral",-1:"Prefer rest"}.get(int(getattr(p,"holiday_preference",0) or 0),"Neutral")),
            "Holiday preference active this month":holiday_active,
            "Ignored legacy weekday/weekend signals":ignored_legacy_directional,
            "Other structured resident choices":choice_items,
            "Overall request % status":("ACTIVE" if active_overall else "N/A — no scored request submitted"),
            "SOFT % status":("ACTIVE" if exact_soft or directional else "N/A — no SOFT submitted"),
            "Preferred work":", ".join(map(str,sorted(p.preferred))) or "—",
            "Preferred AM":", ".join(map(str,sorted(p.preferred_am))) or "—",
            "Preferred PM":", ".join(map(str,sorted(p.preferred_pm))) or "—",
            "Soft free":", ".join(map(str,sorted(p.soft_free))) or "—",
            "RESIDENT HARD unavailable":", ".join(map(str,sorted(p.unavailable))) or "—",
            "ABSOLUTE vacation":", ".join(map(str,sorted(p.vacation))) or "—",
            "ABSOLUTE other justified absence":", ".join(map(str,sorted(p.justified_absence))) or "—",
        })
    return pd.DataFrame(rows)


def _research_write_schedule_grid(writer,sheet_name,y,m,result):
    """Write the same Sudarymas grid to research XLSX and apply resident colors."""
    grid=schedule_grid(y,m,result)
    grid.to_excel(writer,sheet_name=sheet_name,index=True)
    ws=writer.sheets[sheet_name]
    ws.freeze_panes(1,1)
    ws.set_column(0,0,28)
    ws.set_column(1,len(grid.columns),8)
    wb=writer.book
    resident_formats={}
    for initials,color in PERSON_COLORS.items():
        resident_formats[initials]=wb.add_format({
            "bg_color":color,
            "font_color":contrast_text(color),
            "bold":True,
            "align":"center",
            "valign":"vcenter",
            "border":1,
        })
    for r_idx,row in enumerate(grid.itertuples(index=False),start=1):
        for c_idx,value in enumerate(row,start=1):
            if value in resident_formats:
                ws.write(r_idx,c_idx,value,resident_formats[value])


def research_shadow_xlsx(y,m,case,people,runs):
    bio=BytesIO()
    valid=[
        r for r in runs
        if bool(r.get("success"))
        and int(r.get("hard_errors") or 0)==0
        and bool(r.get("assignments"))
    ]
    best=min(valid,key=_research_run_quality_key) if valid else None
    first=next((r for r in runs if int(r.get("run_no") or 0)==1),None)

    with pd.ExcelWriter(bio,engine="xlsxwriter") as w:
        pd.DataFrame([
            ["Tyrimo objektas","Specializuotas grafiko variklis SHADOW / FAKE GENERATOR"],
            ["Laikotarpis",f"{y}-{m:02d}"],
            ["Operational status","RESEARCH ONLY — unconfirmed; never published; never changes the operational Seniūnė schedule"],
            ["Profile","ŠR resident profile / researcher access"],
            ["Input source","Uploaded wishes / HARD workbook"],
            ["Input SHA-256",case.get("input_hash")],
            ["Engine version at lock",case.get("app_version_at_lock")],
            ["Rule Profile at lock",case.get("rule_profile_version_at_lock")],
            ["Primary endpoint","Frozen 1 bandymas / PIRMAS BANDYMAS"],
            ["Reset policy","Researcher may delete/reset the active frozen experiment; reset event is audit-logged"],
            ["Created at",case.get("created_at")],
        ],columns=["Field","Value"]).to_excel(w,index=False,sheet_name="method")

        _research_shadow_run_log_df(runs).to_excel(w,index=False,sheet_name="run_log")
        _research_feasibility_precheck_df(y,m,people).to_excel(w,index=False,sheet_name="feasibility_precheck")

        snapshot_excel=[]
        for row in _research_people_snapshot(people):
            snapshot_excel.append({
                k:(json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(list,dict)) else v)
                for k,v in row.items()
            })
        pd.DataFrame(snapshot_excel).to_excel(w,index=False,sheet_name="input_snapshot")

        audit=case.get("import_audit") or {}
        pd.DataFrame([{
            "Workbook SHA-256":audit.get("workbook_hash"),
            "Lapas":r.get("sheet"),
            "Būsena":r.get("status"),
            "Antraštės eilutė":r.get("header_row"),
            "Eilučių":r.get("rows"),
            "Priežastis":r.get("reason",""),
        } for r in audit.get("sheets",[]) or []] or [{
            "Workbook SHA-256":audit.get("workbook_hash",""),
            "Sheet":"","Status":"No audit rows","Header row":"","Rows":"","Reason":""
        }]).to_excel(w,index=False,sheet_name="input_import_audit")

        # Every run gets its own grafikas + all statistics. Failed runs get a non-empty
        # diagnostic sheet, so research downloads are never misleadingly blank.
        for r in runs:
            n=int(r.get("run_no") or 0)
            rr=_research_shadow_result_from_run(r,people,y,m)
            if r.get("assignments"):
                _research_write_schedule_grid(w,f"r{n}_grid",y,m,rr)
                schedule_list_df(y,m,rr).to_excel(w,index=False,sheet_name=f"r{n}_schedule")
                _research_people_stats_df(rr).to_excel(w,index=False,sheet_name=f"r{n}_people_stats")
                _research_post_matrix_df(rr,people).to_excel(w,index=False,sheet_name=f"r{n}_post_matrix")
                _research_global_stats_df(rr).to_excel(w,index=False,sheet_name=f"r{n}_global_stats")
                _research_hard_errors_df(rr).to_excel(w,index=False,sheet_name=f"r{n}_hard_errors")
            else:
                g=(r.get("full_stats") or {}).get("global",{}) if isinstance(r.get("full_stats"),dict) else {}
                errors=g.get("errors") or []
                pd.DataFrame([
                    {"Field":"Run","Value":n},
                    {"Field":"Success","Value":bool(r.get("success"))},
                    {"Field":"Solver stage","Value":r.get("solver_stage") or g.get("solve_stage")},
                    {"Field":"HARD errors","Value":r.get("hard_errors")},
                    {"Field":"Elapsed seconds","Value":r.get("elapsed_seconds")},
                    {"Field":"Failure / diagnostic","Value":" | ".join(map(str,errors)) if errors else "No assignments were returned by the engine."},
                ]).to_excel(w,index=False,sheet_name=f"r{n}_failure")

        if first and first.get("assignments"):
            r1=_research_shadow_result_from_run(first,people,y,m)
            _research_write_schedule_grid(w,"PRIMARY_grid",y,m,r1)
            _research_people_stats_df(r1).to_excel(w,index=False,sheet_name="PRIMARY_people")
            _research_global_stats_df(r1).to_excel(w,index=False,sheet_name="PRIMARY_metrics")

        if best and best.get("assignments"):
            rb=_research_shadow_result_from_run(best,people,y,m)
            _research_write_schedule_grid(w,"BEST_grid",y,m,rb)
            _research_people_stats_df(rb).to_excel(w,index=False,sheet_name="BEST_people")
            _research_global_stats_df(rb).to_excel(w,index=False,sheet_name="BEST_metrics")

        # Make ordinary table sheets readable.
        for name,ws in w.sheets.items():
            if name.endswith("_grid") or name in ("PRIMARY_grid","BEST_grid"):
                continue
            ws.freeze_panes(1,0)
            ws.set_column(0,0,28)
            ws.set_column(1,30,20)

    return bio.getvalue()


def _render_research_shadow_result(rr,run_no,y,m,people,primary=False):
    g=(rr.stats or {}).get("global",{})
    label=("PAGRINDINIS PALYGINIMAS — MOCK PIRMAS BANDYMAS" if primary else f"MOCK RUN {run_no}")
    st.markdown(f"### {label}")
    st.info(
        "RESEARCH SHADOW / UNCONFIRMED — tai yra Sudarymas juodraščio ekvivalentas. "
        "Nėra Publish / Confirm / Authenticate mygtuko ir šis grafikas nepatenka į operacinį grafiką."
    )
    m1,m2,m3,m4=st.columns(4)
    m1.metric("HARD errors *",g.get("hard_errors","—"))
    m2.metric("Monthly fairness",("—" if g.get("monthly_fairness_score") is None else f"{g.get('monthly_fairness_score')}%"))
    m3.metric("Worst post spread",g.get("worst_monthly_post_spread","—"))
    m4.metric("Post structural water-fill","ATITINKA" if g.get("post_spread_quality_gate_passed") else "FAIL")
    q1,q2,q3,q4=st.columns(4)
    q1.metric("Active SOFT residents",g.get("active_preference_residents",0))
    q2.metric("Worst preference %",g.get("min_preference_score") if g.get("min_preference_score") is not None else "N/A")
    q3.metric("Mean preference %",g.get("mean_preference_score") if g.get("mean_preference_score") is not None else "N/A")
    q4.metric("Preference spread, pp",g.get("preference_score_spread") if g.get("preference_score_spread") is not None else "N/A")
    p1,p2,p3,p4=st.columns(4)
    p1.metric("SYSTEM-HARD worst post lock",g.get("post_system_hard_worst_spread_lock","—"))
    p2.metric("SYSTEM-HARD total 9-post spread",g.get("post_system_hard_total_spread_lock","—"))
    p3.metric("Distinct workplace spread",g.get("distinct_rotation_spread","—"))
    p4.metric("Post-stage proof",("OPTIMAL" if g.get("post_system_hard_stage_optimal") else "BEST FOUND"))
    if g.get("generation_quality_issues"):
        st.warning("Generation quality diagnostics: "+"; ".join(map(str,g.get("generation_quality_issues") or [])))

    # The actual visible Sudarymas-style grid — same helper and permanent resident colors.
    st.dataframe(
        style_schedule(schedule_grid(y,m,rr)),
        use_container_width=True,
        height=620,
    )

    friday_proof=_friday_waterfill_proof(rr.stats)
    if not friday_proof.get("passed"):
        counts=friday_proof.get("counts") or {}
        st.error(
            "FRIDAY WATER-FILL INVALID šiame frozen run: "
            f"{friday_proof['total']} Friday assignments / {friday_proof['n']} rezidentų → "
            f"teisingas entitlement {friday_proof['floor']}-{friday_proof['ceil']} kiekvienam; "
            f"šiame run observed {min(counts.values()) if counts else 0}-{max(counts.values()) if counts else 0} "
            f"(spread {friday_proof['spread']}). Tai legacy frozen rezultatas; naujas V2.5.86 run su tokiu spread negali būti pažymėtas validžiu."
        )
    else:
        st.success(
            f"Friday SYSTEM water-fill PASS: {friday_proof['total']} assignments / {friday_proof['n']} residents → "
            f"{friday_proof['floor']}-{friday_proof['ceil']} each, raw spread {friday_proof['spread']}."
        )

    t1,t2,t3,t4=st.tabs(["Rezidentų rodikliai","Darbo vietų matrica","Bendri rodikliai","Privalomos taisyklės / diagnostika"])
    with t1:
        st.dataframe(_research_people_stats_df(rr),use_container_width=True,hide_index=True,height=520)
    with t2:
        st.dataframe(_research_post_matrix_df(rr,people),use_container_width=True,hide_index=True,height=520)
    with t3:
        st.dataframe(_research_global_stats_df(rr),use_container_width=True,hide_index=True,height=520)
    with t4:
        render_hard_error_explainer(g,lang,key_suffix=f"shadow_{y}_{m}_{run_no}")
        hdf=_research_hard_errors_df(rr)
        if not hdf.empty:
            st.dataframe(hdf,use_container_width=True,hide_index=True)


def render_research_shadow_generator():
    st.subheader("Tyrėjo bandomasis grafiko generatorius")
    st.success("ŠR RESEARCHER ACCESS — embedded in the same single ŠR account window. No profile switching is required.")
    st.error(
        "RESEARCH ONLY. Šis generatorius NIEKADA nepublikuoja grafiko, "
        "nekeičia realaus operacinio Seniūnės grafiko, backupų, fairness_history ar operacinių duomenų."
    )
    st.caption(
        "GENERATE MOCK SCHEDULE naudoja tą patį solve_schedule engine kaip normalus Seniūnės Sudarymas. "
        "Skirtumas: rezultatas saugomas tik research-shadow lentelėse ir neturi Publish/Confirm/Authenticate veiksmo."
    )

    st.markdown(f"### {month_label(year,month)}")
    case=db.get_research_shadow_case_v2545(year,month)

    if not case:
        st.markdown("### 1. UPLOAD WISHES / HARD CONSTRAINTS")
        wishes_file=st.file_uploader(
            "Pageidavimai / HARD taisyklės (.xlsx / .xls)",
            type=["xlsx","xls"],
            key=f"research_shadow_wishes_{year}_{month}"
        )
        st.caption(
            "Galima kelti originalų mėnesio Excel. Importeris skanuoja VISUS worksheet'us, "
            "sujungia suderinamas pageidavimų/HARD lenteles ir saugo sheet/row provenance."
        )

        preflight_ok=False
        people=None
        audit=None
        warnings=[]
        if wishes_file is not None:
            try:
                people,audit,warnings=research_people_from_excel(
                    wishes_file,year,month,return_audit=True
                )
                st.markdown("### WHOLE-WORKBOOK WISHES PREFLIGHT")
                a1,a2,a3=st.columns(3)
                a1.metric("Workbook sheets",audit.get("sheet_count"))
                a2.metric("Prefs/HARD sheets used",audit.get("used_sheet_count"))
                a3.metric("Warnings",len(warnings or []))
                scan_df=pd.DataFrame([{
                    "Lapas":r.get("sheet"),
                    "Būsena":r.get("status"),
                    "Antraštės eilutė":r.get("header_row"),
                    "Eilučių":r.get("rows"),
                    "Priežastis":r.get("reason",""),
                } for r in audit.get("sheets",[])])
                st.dataframe(scan_df,use_container_width=True,hide_index=True)
                if warnings:
                    with st.expander(f"Importo perspėjimai ({len(warnings)})"):
                        for x in warnings:
                            st.write("• "+str(x))

                pref_input_df=_research_input_preferences_df(people,year,month)
                active_requests=int((pref_input_df["Overall request % status"]=="ACTIVE").sum())
                resident_hard_units=int(pref_input_df["RESIDENT HARD request units"].sum())
                exact_soft=int(pref_input_df["Exact SOFT requests"].sum())
                st.markdown("### IMPORTED RESIDENT INPUT AUDIT")
                p1,p2,p3,p4=st.columns(4)
                p1.metric("Residents in roster",len(pref_input_df))
                p2.metric("Residents with scored requests",active_requests)
                p3.metric("RESIDENT HARD units",resident_hard_units)
                p4.metric("Exact SOFT units",exact_soft)
                st.dataframe(pref_input_df,use_container_width=True,hide_index=True,height=520)
                st.caption(
                    "V2.5.49: `Negaliu dirbti` yra RESIDENT HARD ir įeina į bendrą rezidento prašymų išpildymą. "
                    "Liga / atostogos / teisės-poilsio sauga yra ABSOLUTE HARD: jos audituojamos atskirai ir į procento vardiklį neįtraukiamos, nes jų negalima aukoti. "
                    "SOFT fairness lieka MAX-MIN: tarp aktyvių SOFT rezidentų 85/85/85 yra geriau už 100/100/55."
                )

                feas=_research_feasibility_precheck_df(year,month,people)
                impossible=feas[feas["Clear ABSOLUTE infeasibility"]==True]
                with st.expander("ABSOLUTE / RESIDENT HARD feasibility pre-check",expanded=not impossible.empty):
                    st.dataframe(feas,use_container_width=True,hide_index=True)
                    st.caption(
                        "Pirmas upper bound saugo visus RESIDENT HARD; antras leidžia tik minimaliai aukoti `Negaliu dirbti`, bet vis tiek niekada nelaužo ABSOLUTE HARD. "
                        "Tik kai Target viršija net ABSOLUTE-HARD-only upper bound, tai aiškus individualus matematinis neįmanomumas."
                    )
                if not impossible.empty:
                    st.warning(
                        "Pre-check found at least one resident whose target exceeds even a generous maximum allowed by the uploaded HARD dates. "
                        "You may still run the engine so the PIRMAS BANDYMAS failure is recorded, or correct the source file before generating."
                    )
                preflight_ok=True
                st.success("WHOLE-WORKBOOK WISHES PREFLIGHT — PASSED")
            except Exception as exc:
                st.error("WHOLE-WORKBOOK WISHES PREFLIGHT — BLOCKED")
                st.error(str(exc))

        if st.button(
            "GENERATE MOCK SCHEDULE — PIRMAS BANDYMAS",
            type="primary",
            use_container_width=True,
            disabled=(not preflight_ok),
            key=f"research_shadow_run1_{year}_{month}"
        ):
            snapshot=_research_people_snapshot(people)
            input_hash=_research_input_hash(year,month,people)
            case=db.create_research_shadow_case_v2545(
                year,month,input_hash,snapshot,_research_json_safe(audit),
                APP_VERSION,ACTIVE_RULE_PROFILE_VERSION
            )

            t0=perf_counter()
            engine_message=""
            try:
                result=solve_schedule(year,month,people,time_limit=180.0)
                elapsed=perf_counter()-t0
                full_stats=_research_json_safe(result.stats or {})
                run_ok=result.ok
                assignments=result.assignments
                engine_message=str(result.message or "")
                if not run_ok:
                    full_stats.setdefault("global",{})
                    full_stats["global"].setdefault("errors",[])
                    if engine_message and engine_message not in full_stats["global"]["errors"]:
                        full_stats["global"]["errors"].append(engine_message)
                    full_stats["global"].setdefault("solve_stage","NO_VALID_FIRST_SHOT")
            except Exception as solve_exc:
                elapsed=perf_counter()-t0
                engine_message=f"ENGINE EXCEPTION: {type(solve_exc).__name__}: {solve_exc}"
                full_stats={
                    "global":{
                        "hard_errors":None,
                        "errors":[engine_message],
                        "solve_stage":"ENGINE_EXCEPTION",
                    },
                    "people":{}
                }
                run_ok=False
                assignments={}

            db.record_research_shadow_run_v2545(
                case["id"],input_hash,elapsed,run_ok,
                APP_VERSION,ACTIVE_RULE_PROFILE_VERSION,
                _research_json_safe(full_stats),assignments
            )
            if run_ok:
                st.success("MOCK PIRMAS BANDYMAS generated and frozen in research storage. It remains UNCONFIRMED / NOT PUBLISHED.")
            else:
                st.error("PIRMAS BANDYMAS returned no valid schedule. The failure and diagnostics were frozen for research; you can delete/reset this experiment below and try again.")
            st.rerun()
        return

    people=_research_people_from_snapshot(case.get("input_snapshot") or [])
    runs=db.list_research_shadow_runs_v2545(case["id"])
    st.success(
        f"LOCKED SHADOW INPUT {year}-{month:02d} · "
        f"SHA-256 {str(case.get('input_hash'))[:16]}…"
    )
    st.caption(
        f"Užfiksuotas variklis: {case.get('app_version_at_lock')} · "
        f"Rule Profile v{case.get('rule_profile_version_at_lock')} · "
        f"created {str(case.get('created_at') or '')[:19]}"
    )

    # Researcher-only reset: intentionally available in ŠR resident profile so
    # operational Seniūnė role changes never remove ŠR research control.
    with st.expander("DELETE / RESET FROZEN MOCK EXPERIMENT",expanded=False):
        st.warning(
            "This deletes the active research-shadow case and all its frozen runs for this month, then lets you upload wishes and generate a new PIRMAS BANDYMAS. "
            "It does NOT delete or change the operational Seniūnė draft/published schedule, backups, swaps or fairness_history. A reset audit tombstone is kept."
        )
        reset_token=f"DELETE SHADOW {year}-{month:02d}"
        typed=st.text_input(
            f"Type exactly: {reset_token}",
            key=f"research_shadow_delete_confirm_{case['id']}"
        )
        reason=st.text_input(
            "Reset note (optional)",
            key=f"research_shadow_delete_reason_{case['id']}",
            placeholder="e.g. testing input corrected / regenerate experiment"
        )
        if st.button(
            "DELETE FROZEN PIRMAS BANDYMAS / ALL SHADOW RUNS",
            type="primary",
            use_container_width=True,
            disabled=(typed.strip()!=reset_token),
            key=f"research_shadow_delete_{case['id']}"
        ):
            db.reset_research_shadow_case_v2546(year,month,reason or "researcher requested reset")
            st.session_state.pop(f"research_shadow_wishes_{year}_{month}",None)
            st.success("Research shadow experiment deleted/reset. You can now generate a completely new mock PIRMAS BANDYMAS from the same or corrected wishes file.")
            st.rerun()

    st.markdown("### Shadow run log")
    if runs:
        st.dataframe(_research_shadow_run_log_df(runs),use_container_width=True,hide_index=True)

    version_ok=(
        str(case.get("app_version_at_lock"))==APP_VERSION
        and int(case.get("rule_profile_version_at_lock") or 0)==int(ACTIVE_RULE_PROFILE_VERSION)
    )
    if not version_ok:
        st.error(
            "FROZEN ENGINE MISMATCH — šio mėnesio shadow testas turi būti tęsiamas tik su "
            f"{case.get('app_version_at_lock')} / taisyklių profilis v{case.get('rule_profile_version_at_lock')}."
        )

    next_no=len(runs)+1
    if next_no<=5:
        if st.button(
            f"PERTIKRINTI / GERINTI MOCK GRAFIKĄ — RUN {next_no}/5",
            use_container_width=True,
            disabled=not version_ok,
            key=f"research_shadow_next_{case['id']}_{next_no}"
        ):
            locked_hash=_research_input_hash(year,month,people)
            if locked_hash!=case.get("input_hash"):
                st.error("Užfiksuotos įvesties kontrolinis kodas nesutampa. Bandymas nutrauktas.")
                return
            t0=perf_counter()
            try:
                result=solve_schedule(year,month,people,time_limit=180.0)
                elapsed=perf_counter()-t0
                full_stats=_research_json_safe(result.stats or {})
                run_ok=result.ok
                assignments=result.assignments
                engine_message=str(result.message or "")
                if not run_ok:
                    full_stats.setdefault("global",{})
                    full_stats["global"].setdefault("errors",[])
                    if engine_message and engine_message not in full_stats["global"]["errors"]:
                        full_stats["global"]["errors"].append(engine_message)
                    full_stats["global"].setdefault("solve_stage","NO_VALID_SCHEDULE")
            except Exception as solve_exc:
                elapsed=perf_counter()-t0
                full_stats={
                    "global":{
                        "hard_errors":None,
                        "errors":[f"ENGINE EXCEPTION: {type(solve_exc).__name__}: {solve_exc}"],
                        "solve_stage":"ENGINE_EXCEPTION",
                    },
                    "people":{}
                }
                run_ok=False
                assignments={}
            saved=db.record_research_shadow_run_v2545(
                case["id"],locked_hash,elapsed,run_ok,
                APP_VERSION,ACTIVE_RULE_PROFILE_VERSION,
                _research_json_safe(full_stats),assignments
            )
            if run_ok:
                st.success(f"MOCK RUN {saved.get('run_no',next_no)} frozen. PIRMAS BANDYMAS remains the primary endpoint.")
            else:
                st.warning(f"RUN {saved.get('run_no',next_no)} did not return a valid schedule; diagnostics were saved.")
            st.rerun()
    else:
        st.success("5/5 shadow runs complete. Reset the experiment if you intentionally want to start over.")

    first=next((r for r in runs if int(r.get("run_no") or 0)==1),None)
    valid=[
        r for r in runs
        if bool(r.get("success")) and int(r.get("hard_errors") or 0)==0 and bool(r.get("assignments"))
    ]
    best=min(valid,key=_research_run_quality_key) if valid else None

    # Always show the frozen PIRMAS BANDYMAS diagnostics. If it has a schedule, render
    # the actual Sudarymas-style colored grid immediately in this window.
    if first:
        if first.get("assignments"):
            rr=_research_shadow_result_from_run(first,people,year,month)
            _render_research_shadow_result(rr,1,year,month,people,primary=True)
        else:
            st.markdown("### PAGRINDINIS PALYGINIMAS — MOCK PIRMAS BANDYMAS")
            st.error("The engine returned no valid grafikas for 1 bandymas, so there is no grid to display for this frozen attempt.")
            fg=(first.get("full_stats") or {}).get("global",{}) if isinstance(first.get("full_stats"),dict) else {}
            diag=fg.get("errors") or []
            if diag:
                st.dataframe(pd.DataFrame({"PIRMAS BANDYMAS diagnostic":diag}),use_container_width=True,hide_index=True)
            feas=_research_feasibility_precheck_df(year,month,people)
            st.dataframe(feas,use_container_width=True,hide_index=True)
            st.caption(
                "If a target exceeds the generous HARD-only maximum, the same operational Sudarymas engine is mathematically unable to create a valid grafikas from that frozen input. "
                "Use DELETE / RESET above after correcting the input or target semantics."
            )

    if best and (not first or int(best.get("run_no") or 0)!=1):
        st.divider()
        rb=_research_shadow_result_from_run(best,people,year,month)
        _render_research_shadow_result(rb,int(best.get("run_no") or 0),year,month,people,primary=False)
        st.caption(
            f"Secondary best-of-{len(runs)} = Run {best.get('run_no')} · "
            f"fairness {best.get('monthly_fairness')}%. PIRMAS BANDYMAS remains the primary research endpoint."
        )

    inspectable=[r for r in runs if r.get("assignments")]
    if len(inspectable)>1:
        st.divider()
        chosen_no=st.selectbox(
            "PERŽIŪRĖTI UŽRAKINTĄ BANDOMĄJĮ PALEIDIMĄ",
            [int(r.get("run_no") or 0) for r in inspectable],
            format_func=lambda n:(
                f"Run {n} — PIRMAS BANDYMAS" if n==1 else f"Run {n} — tobulinimo bandymas"
            ),
            key=f"research_shadow_view_run_{case['id']}"
        )
        chosen=next(r for r in inspectable if int(r.get("run_no") or 0)==int(chosen_no))
        # Avoid duplicating 1 bandymas / current best unless the researcher explicitly wants
        # to inspect it here; this selector is intentionally an experiment workbench.
        with st.expander(f"Peržiūrėti užrakintą bandymą {chosen_no}",expanded=False):
            chosen_result=_research_shadow_result_from_run(chosen,people,year,month)
            _render_research_shadow_result(
                chosen_result,int(chosen_no),year,month,people,primary=(int(chosen_no)==1)
            )

    st.download_button(
        "ATSISIŲSTI VISĄ BANDOMŲJŲ PALEIDIMŲ TYRIMO RINKINĮ (.xlsx)",
        research_shadow_xlsx(year,month,case,people,runs),
        file_name=f"my_engine_shadow_{year}_{month:02d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        use_container_width=True
    )
    st.info(
        "Eksporte pateikiamas kiekvieno sėkmingo bandymo grafikas, rezidentų rodikliai, darbo vietų matricos, bendri rodikliai, privalomų taisyklių diagnostika, paleidimo laikas, įvesties kopija ir įgyvendinamumo patikra."
    )

def render_available_gpt_vs_engine_research():
    st.subheader("Grafikų sudarymo metodų palyginimas")
    st.success("Tik tyrėjui · užrakinamas oficialus tyrimo bandymas")
    st.caption(
        "Palyginamasis metodas = bendrinis DI + seniūnė, kuri grafiką tobulino rankiniu būdu, "
        "teikė papildomas užklausas ir sprendė, kada rezultatas jau pakankamai geras. "
        "Specializuotas grafiko variklis = ši grafiko sistema su aiškiai aprašytomis saugos, paskirstymo ir audito taisyklėmis."
    )
    st.info(
        "Pagrindinis tyrimo rezultatas = pirmasis bandymas; jis duomenų bazėje užrakinamas visam laikui. "
        "Papildomai galima atlikti iki 4 tobulinimo bandymų (iš viso ne daugiau kaip 5), tačiau pirmasis bandymas niekada nepakeičiamas vėlesniu geresniu rezultatu."
    )

    c1,c2=st.columns(2)
    ry=int(c1.number_input("Palyginimo metai",min_value=2026,max_value=2100,value=int(year),step=1,key="research_lock_year"))
    rm=int(c2.selectbox("Palyginimo mėnuo",options=list(range(1,13)),index=int(month)-1,key="research_lock_month"))

    case=db.get_research_scheduler_case_v2541(ry,rm)
    all_cases=db.list_research_scheduler_cases_v2541()

    # Engine freeze audit across already locked months.
    other_versions=sorted({
        (str(c.get("app_version_at_lock")),int(c.get("rule_profile_version_at_lock") or 0))
        for c in all_cases
    })
    if other_versions:
        st.caption("Jau užrakintos tyrimo variklio versijos: "+", ".join(
            f"{v} / taisyklių profilis v{rp}" for v,rp in other_versions
        ))

    if not case:
        t1,t2=st.columns(2)
        t1.download_button(
            "ATSISIŲSTI ISTORINIŲ ĮVESČIŲ ŠABLONĄ (.xlsx)",
            research_preferences_template(ry,rm),
            file_name=f"historical_inputs_{ry}_{rm:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
        t2.download_button(
            "ATSISIŲSTI BENDRINIO DI + SENIŪNĖS GRAFIKO ŠABLONĄ (.xlsx)",
            research_schedule_template(ry,rm),
            file_name=f"available_gpt_human_schedule_{ry}_{rm:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

        st.warning(
            "Naudok tik realiai turėtus duomenis. Palyginimui rekomenduojama naudoti sistemoje esančius to mėnesio pageidavimus: "
            "užrakinimo momentu sistema nukopijuos pasirinkto mėnesio pageidavimus ir tą pačią užfiksuotą įvestį naudos abiem grafikams."
        )
        input_source=st.radio(
            "Pageidavimų įvesties šaltinis",
            ["SISTEMOJE ESANTYS PAGEIDAVIMAI — tas pats pasirinktas mėnuo", "ĮKELTI ISTORINĘ ĮVESTIES EXCEL BYLĄ"],
            horizontal=True,key=f"research_input_source_{ry}_{rm}"
        )
        use_live_inputs=input_source.startswith(("LIVE APP","SISTEMOJE"))
        u1,u2=st.columns(2)
        if use_live_inputs:
            u1.success("1. Pasirinkti sistemoje esantys pageidavimai — atskiro Excel failo nereikia")
            pref_file=None
        else:
            pref_file=u1.file_uploader(
                "1. Istoriniai pageidavimai ir apribojimai",
                type=["xlsx","xls"],key=f"research_lock_pref_{ry}_{rm}"
            )
        sched_file=u2.file_uploader(
            "2. Bendrinio DI + seniūnės galutinis grafikas",
            type=["xlsx","xls"],key=f"research_lock_sched_{ry}_{rm}"
        )

        # V2.5.108 preflight. Live DB wishes OR whole-workbook historical wishes are frozen before comparison.
        import_preflight_ok=False
        preflight_people=None
        preflight_assignments=None
        preflight_warnings=[]
        pref_audit=None
        sched_audit=None

        if use_live_inputs or pref_file is not None or sched_file is not None:
            st.markdown("### Vienodos įvesties patikra prieš palyginimą")
            st.caption(
                "Svarbiausia taisyklė: bendrinio DI + seniūnės ir specializuoto grafiko variklio rezultatai vertinami pagal identišką užfiksuotą pageidavimų įvestį. "
                "Grafiko Excel įkėlimas patikrina visus lapus ir išsaugo duomenų kilmės informaciją."
            )

        try:
            if use_live_inputs:
                preflight_people=load_people(ry,rm)
                pref_audit={
                    "source_type":"LIVE_APP_DB",
                    "selected_cycle":f"{ry}-{rm:02d}",
                    "snapshot_hash":_research_input_hash(ry,rm,preflight_people),
                    "resident_count":len(preflight_people),
                    "used_sheet_count":0,
                    "sheet_count":0,
                    "sheets":[],
                }
                st.success(
                    f"Sistemos pageidavimai įkelti: {len(preflight_people)} rezidentų · įvesties kontrolinis kodas {_research_input_hash(ry,rm,preflight_people)[:12]}…"
                )
                st.dataframe(_research_input_preferences_df(preflight_people,ry,rm),use_container_width=True,hide_index=True,height=420)
                st.info(
                    "Būtent ši pageidavimų įvestis bus užfiksuota ir taikoma abiem lyginamiems grafikams. "
                    "Rankiniu būdu tobulintas grafikas negauna kitokio ar lengvesnio pageidavimų rinkinio."
                )
            elif pref_file is not None:
                preflight_people,pref_audit,pref_warn=research_people_from_excel(
                    pref_file,ry,rm,return_audit=True
                )
                preflight_warnings.extend(pref_warn or [])
            if sched_file is not None:
                preflight_assignments,sched_warn,sched_audit=research_assignments_from_excel(
                    sched_file,ry,rm,return_audit=True
                )
                preflight_warnings.extend(sched_warn or [])

            if preflight_people is not None and sched_file is not None and preflight_assignments is not None:
                import_preflight_ok=True
                same_workbook=(
                    (not use_live_inputs) and pref_audit and sched_audit
                    and pref_audit.get("workbook_hash")==sched_audit.get("workbook_hash")
                )
                if same_workbook:
                    st.success(
                        "Tas pats Excel failas įkeltas į abu laukus — tinkama. "
                        "Pageidavimų ir grafiko įkėlimo dalys jį tikrina atskirai ir informaciją ima iš atpažintų skirtingų lapų."
                    )

                p1,p2,p3,p4=st.columns(4)
                p1.metric("Pageidavimų šaltinis",("Sistemos duomenys" if use_live_inputs else "Excel failas"))
                p2.metric("Užfiksuota rezidentų",len(preflight_people) if preflight_people is not None else "—")
                p3.metric("Naudota grafiko lapų",sched_audit.get("used_sheet_count") if sched_audit else "—")
                p4.metric("Nuskaityta paskyrimų",sched_audit.get("assignment_count") if sched_audit else "—")

                def _audit_sheet_df(audit):
                    if not audit:
                        return pd.DataFrame()
                    return pd.DataFrame([{
                        "Lapas":r.get("sheet"),
                        "Būsena":r.get("status"),
                        "Antraštės eilutė":r.get("header_row"),
                        "Eilučių":r.get("rows"),
                        "Priežastis":r.get("reason",""),
                    } for r in audit.get("sheets",[])])

                left_a,right_a=st.columns(2)
                with left_a:
                    st.markdown("**Pageidavimų šaltinio patikra**")
                    if use_live_inputs:
                        st.dataframe(pd.DataFrame([{
                            "Source":"Sistemos duomenys",
                            "Laikotarpis":f"{ry}-{rm:02d}",
                            "Įvesties kontrolinis kodas":pref_audit.get("snapshot_hash"),
                            "Rezidentai":pref_audit.get("resident_count"),
                        }]),use_container_width=True,hide_index=True)
                    else:
                        st.dataframe(_audit_sheet_df(pref_audit),use_container_width=True,hide_index=True)
                with right_a:
                    st.markdown("**Grafiko Excel lapų patikra**")
                    st.dataframe(_audit_sheet_df(sched_audit),use_container_width=True,hide_index=True)

                if sched_audit.get("duplicates"):
                    st.info(
                        f"Grafiko įkėlime rasta {len(sched_audit['duplicates'])} tikslių pasikartojančių eilučių skirtinguose lapuose; "
                        "jos patikrintos ir antrą kartą neskaičiuotos."
                    )
                if preflight_warnings:
                    with st.expander(f"Importo perspėjimai ({len(preflight_warnings)})",expanded=False):
                        for w in preflight_warnings:
                            st.write("• "+str(w))

                st.success(
                    "Vienodos įvesties patikra sėkminga. Užrakinus tyrimo atvejį būtent ši įvestis bus naudojama abiem grafikams."
                )
        except Exception as import_exc:
            import_preflight_ok=False
            st.error("Vienodos įvesties patikra nepavyko")
            st.error(str(import_exc))

        st.markdown("### Bendrinio DI + seniūnės proceso klausimynai")
        st.caption(
            "Gali įkelti MG ir VL to mėnesio retrospektyvius klausimynus. "
            "Sistema perskaitys tekstą ir pasiūlys bandymų skaičiaus bei laiko reikšmes, tačiau galutinį skaičių visada matai ir patvirtini pats."
        )
        q1,q2=st.columns(2)
        gm_q=q1.file_uploader(
            "MG klausimynas",
            type=["pdf","docx","xlsx","xls","csv","txt","md"],
            key=f"gm_questionnaire_{ry}_{rm}"
        )
        lv_q=q2.file_uploader(
            "VL klausimynas",
            type=["pdf","docx","xlsx","xls","csv","txt","md"],
            key=f"lv_questionnaire_{ry}_{rm}"
        )

        questionnaire_payloads={}
        parsed_by_respondent={}
        for initials,uploaded in [("MG",gm_q),("VL",lv_q)]:
            if uploaded is None:
                continue
            extract=_questionnaire_extract_text(uploaded)
            parsed=_questionnaire_parse_process_metrics(extract.get("text","")) if extract.get("ok") else {
                "iterations":None,"minutes":None,
                "iteration_evidence":None,"time_evidence":None,
                "iteration_candidates":[],"time_candidates":[]
            }
            questionnaire_payloads[initials]=(extract,parsed)
            parsed_by_respondent[initials]=parsed
            _questionnaire_render_result(initials,extract,parsed)

        consensus=_questionnaire_consensus(parsed_by_respondent)
        if parsed_by_respondent:
            st.info(
                "Klausimynų bendra siūloma reikšmė: "
                + ("bandymų skaičius = nėra duomenų" if consensus["iterations"] is None else f"bandymų skaičius ≈ {consensus['iterations']}")
                + " · "
                + ("laikas = nėra duomenų" if consensus["minutes"] is None else f"laikas ≈ {consensus['minutes']:g} min")
                + ". Galutiniai tyrimo metaduomenų laukai lieka redaguojami."
            )

        iter_key=f"gpt_iter_{ry}_{rm}"
        minutes_key=f"gpt_minutes_{ry}_{rm}"
        if consensus["iterations"] is not None and not str(st.session_state.get(iter_key,"")).strip():
            st.session_state[iter_key]=str(consensus["iterations"])
        if consensus["minutes"] is not None and not str(st.session_state.get(minutes_key,"")).strip():
            st.session_state[minutes_key]=str(consensus["minutes"])

        m1,m2=st.columns(2)
        gpt_iter_text=m1.text_input(
            "Bendrinio DI + seniūnės bandymų skaičius (patvirtintas)",
            placeholder="pvz. 6",key=iter_key
        )
        gpt_minutes_text=m2.text_input(
            "Apytikslis bendras bendrinio DI + seniūnės darbo laikas, min. (patvirtintas)",
            placeholder="pvz. 45",key=minutes_key
        )
        method_note=st.text_area(
            "Bendrinio DI + seniūnės proceso pastaba (nebūtina)",
            placeholder="Pvz. seniūnė kelis kartus tikslino užklausą ir vertino rezultatą; formalios teisingumo statistikos neturėjo.",
            key=f"gpt_method_{ry}_{rm}"
        )

        version_mismatch=bool(all_cases) and any(
            str(c.get("app_version_at_lock"))!=APP_VERSION
            or int(c.get("rule_profile_version_at_lock") or 0)!=int(ACTIVE_RULE_PROFILE_VERSION)
            for c in all_cases
        )
        if version_mismatch:
            st.error(
                "Variklio versijų neatitikimas: jau yra užrakintas kitas tyrimo mėnuo su kita variklio arba taisyklių profilio versija. "
                "Oficialus palyginimas turi būti atliekamas ta pačia užfiksuota versija."
            )

        confirm=st.checkbox(
            "PATVIRTINU: tai oficiali šio mėnesio tyrimo įvestis; po užrakinimo jos nekeisiu.",
            key=f"confirm_research_case_{ry}_{rm}"
        )
        if st.button(
            "UŽRAKINTI TYRIMO ATVEJĮ + 1-ASIS BANDYMAS",
            type="primary",use_container_width=True,
            disabled=(not confirm or not sched_file or version_mismatch or not import_preflight_ok),
            key=f"lock_run1_{ry}_{rm}"
        ):
            try:
                if not import_preflight_ok or preflight_people is None or preflight_assignments is None:
                    raise ValueError("WHOLE_WORKBOOK_PREFLIGHT_REQUIRED")
                people=preflight_people
                assignments=preflight_assignments
                warnings=list(preflight_warnings or [])
                warnings.append(_research_json_safe({
                    "type":("LIVE_APP_SAME_INPUT_AUDIT_V25108" if use_live_inputs else "WHOLE_WORKBOOK_IMPORT_AUDIT_V2544"),
                    "selected_cycle":f"{ry}-{rm:02d}",
                    "input_source":("LIVE_APP_DB" if use_live_inputs else "UPLOADED_WORKBOOK"),
                    "preferences":pref_audit,
                    "schedule":sched_audit,
                    "same_workbook":(
                        (not use_live_inputs) and bool(pref_audit and sched_audit)
                        and pref_audit.get("workbook_hash")==sched_audit.get("workbook_hash")
                    ),
                    "same_frozen_snapshot_for_both_schedules":True,
                }))
                snapshot=_research_people_snapshot(people)
                input_hash=_research_input_hash(ry,rm,people)
                schedule_hash=_research_schedule_hash(assignments)
                gpt_iters=_research_parse_optional_int(gpt_iter_text)
                gpt_minutes=_research_parse_optional_float(gpt_minutes_text)

                case=db.create_research_scheduler_case_v2541(
                    ry,rm,input_hash,schedule_hash,snapshot,
                    {str(k):v for k,v in assignments.items()},warnings,
                    gpt_iters,gpt_minutes,method_note,
                    APP_VERSION,ACTIVE_RULE_PROFILE_VERSION,
                )

                questionnaire_save_warnings=[]
                for initials,(extract,parsed) in questionnaire_payloads.items():
                    if not extract.get("ok"):
                        questionnaire_save_warnings.append(f"{initials}: klausimyno teksto nuskaityti nepavyko; failas neišsaugotas.")
                        continue
                    try:
                        db.save_research_scheduler_questionnaire_v2542(case["id"],initials,extract,parsed)
                    except Exception as qexc:
                        questionnaire_save_warnings.append(f"{initials}: {qexc}")

                t0=perf_counter()
                try:
                    algorithm=solve_schedule(ry,rm,people,time_limit=180.0)
                    elapsed=perf_counter()-t0
                    full_stats=_research_json_safe(algorithm.stats or {})
                    gg=full_stats.get("global",{}) if isinstance(full_stats,dict) else {}
                    run_assignments=algorithm.assignments
                    run_ok=algorithm.ok
                except Exception as solve_exc:
                    elapsed=perf_counter()-t0
                    full_stats={"global":{
                        "hard_errors":None,
                        "errors":[f"ENGINE EXCEPTION: {type(solve_exc).__name__}: {solve_exc}"],
                        "solve_stage":"ENGINE_EXCEPTION",
                    },"people":{}}
                    gg=full_stats["global"]
                    run_assignments={}
                    run_ok=False

                db.record_research_scheduler_run_v2541(
                    case["id"],input_hash,elapsed,run_ok,
                    APP_VERSION,ACTIVE_RULE_PROFILE_VERSION,gg,
                    run_assignments,raw_metrics=_research_json_safe(full_stats),
                )
                if questionnaire_save_warnings:
                    st.warning("Klausimynų patikra: "+" | ".join(questionnaire_save_warnings))
                st.success("Tyrimo atvejis užrakintas. Pirmasis bandymas išsaugotas nekintamame duomenų bazės įraše.")
                st.rerun()
            except Exception as e:
                msg=str(e)
                if "RESEARCH_CASE_LOCKED_INPUT_MISMATCH" in msg:
                    st.error("Šis mėnuo jau užrakintas su kita įvestimi arba grafiku. Oficialaus tyrimo atvejo perrašyti negalima.")
                else:
                    st.exception(e)
            return

        st.caption("Kol nepaspaudei „UŽRAKINTI TYRIMO ATVEJĮ + 1-ASIS BANDYMAS“, įkeltus failus gali saugiai keisti ir taisyti.")
        return

    # ===== UŽRAKINTAS TYRIMO ATVEJIS =====
    people=_research_people_from_snapshot(case.get("input_snapshot") or [])
    comparator=_research_locked_comparator(case,people)
    runs=db.list_research_scheduler_runs_v2541(case["id"])

    st.success(
        f"UŽRAKINTAS TYRIMO ATVEJIS {ry}-{rm:02d} · įvestis {str(case.get('input_hash'))[:12]}… · "
        f"Bendrinis DI + seniūnė grafikas {str(case.get('comparator_schedule_hash'))[:12]}…"
    )
    st.caption(
        f"Užfiksuotas variklis: {case.get('app_version_at_lock')} · Rule Profile v{case.get('rule_profile_version_at_lock')} · "
        f"locked {str(case.get('created_at') or '')[:19]}"
    )

    questionnaires=db.list_research_scheduler_questionnaires_v2542(case["id"])
    q_by={q.get("respondent_initials"):q for q in questionnaires}

    st.markdown("### MG / VL retrospektyvūs klausimynai")
    if questionnaires:
        st.dataframe(pd.DataFrame([{
            "Respondentas":q.get("respondent_initials"),
            "Failas":q.get("file_name"),
            "SHA-256":str(q.get("file_hash") or "")[:16]+"…",
            "Nuskaitytas bandymų skaičius":q.get("parsed_iterations"),
            "Nuskaitytas bendras laikas, min.":q.get("parsed_minutes"),
            "Užrakinta":str(q.get("created_at") or "")[:19],
        } for q in questionnaires]),use_container_width=True,hide_index=True)

    for initials in ("MG","VL"):
        if initials in q_by:
            q=q_by[initials]
            payload=q.get("parser_payload") or {}
            with st.expander(f"{initials} klausimyno patikra",expanded=False):
                st.caption(
                    f"{q.get('file_name')} · SHA-256 {q.get('file_hash')} · "
                    f"{q.get('file_size')} bytes"
                )
                st.write(
                    f"Nuskaityta: bandymai={q.get('parsed_iterations')} · "
                    f"minutes={q.get('parsed_minutes')}"
                )
                if payload.get("iteration_evidence"):
                    st.markdown("**Bandymų skaičiaus pagrindimas**")
                    st.caption(str(payload.get("iteration_evidence")))
                if payload.get("time_evidence"):
                    st.markdown("**Laiko pagrindimas**")
                    st.caption(str(payload.get("time_evidence")))
                if q.get("extracted_text"):
                    st.markdown("**Nuskaitytas klausimyno tekstas**")
                    st.text_area(
                        f"{initials} extracted text",
                        value=str(q.get("extracted_text")),
                        height=220,disabled=True,
                        key=f"locked_questionnaire_text_{q.get('id')}",
                        label_visibility="collapsed"
                    )
        else:
            uploaded=st.file_uploader(
                f"{initials} klausimynas — papildyti locked case",
                type=["pdf","docx","xlsx","xls","csv","txt","md"],
                key=f"locked_questionnaire_upload_{case['id']}_{initials}"
            )
            if uploaded is not None:
                extract=_questionnaire_extract_text(uploaded)
                parsed=_questionnaire_parse_process_metrics(extract.get("text","")) if extract.get("ok") else {
                    "iterations":None,"minutes":None,
                    "iteration_evidence":None,"time_evidence":None,
                    "iteration_candidates":[],"time_candidates":[]
                }
                _questionnaire_render_result(initials,extract,parsed)
                if extract.get("ok") and st.button(
                    f"LOCK {initials} QUESTIONNAIRE TO CASE",
                    key=f"lock_questionnaire_{case['id']}_{initials}",
                    use_container_width=True
                ):
                    try:
                        db.save_research_scheduler_questionnaire_v2542(
                            case["id"],initials,extract,parsed
                        )
                        st.success(f"{initials} klausimynas išsaugotas kaip nekintamas tyrimo įrašas.")
                        st.rerun()
                    except Exception as qexc:
                        if "QUESTIONNAIRE_ALREADY_LOCKED" in str(qexc):
                            st.error(f"{initials} klausimynas jau užrakintas kitu failu.")
                        else:
                            st.error(str(qexc))

    if questionnaires:
        stored_parsed={
            q.get("respondent_initials"):{
                "iterations":q.get("parsed_iterations"),
                "minutes":q.get("parsed_minutes"),
            }
            for q in questionnaires
        }
        q_consensus=_questionnaire_consensus(stored_parsed)
        st.info(
            "Išsaugotų klausimynų bendra siūloma reikšmė: "
            + ("bandymų skaičius = nėra duomenų" if q_consensus["iterations"] is None else f"bandymų skaičius ≈ {q_consensus['iterations']}")
            + " · "
            + ("laikas = nėra duomenų" if q_consensus["minutes"] is None else f"laikas ≈ {q_consensus['minutes']:g} min")
        )
        if (q_consensus["iterations"] is not None or q_consensus["minutes"] is not None):
            if st.button(
                "APPLY QUESTIONNAIRE CONSENSUS TO GPT+HUMAN METADATA",
                key=f"apply_q_consensus_{case['id']}",
                use_container_width=True
            ):
                db.update_research_scheduler_process_v2541(
                    case["id"],
                    q_consensus["iterations"] if q_consensus["iterations"] is not None else case.get("gpt_human_iterations"),
                    q_consensus["minutes"] if q_consensus["minutes"] is not None else case.get("gpt_human_minutes"),
                    str(case.get("method_note") or "")
                )
                st.success("Consensus perkeltas į GPT+human proceso metadata; klausimyno patikra įrašai liko atskiri.")
                st.rerun()

    # Allow later enrichment ONLY of human-process metadata, never inputs or schedules.
    with st.expander("Papildyti GPT+human proceso duomenis (inputų/grafiko tai nekeičia)",expanded=False):
        meta1,meta2=st.columns(2)
        it_txt=meta1.text_input(
            "Perdarymų / iteracijų skaičius",
            value="" if case.get("gpt_human_iterations") is None else str(case.get("gpt_human_iterations")),
            key=f"update_iters_{case['id']}"
        )
        min_txt=meta2.text_input(
            "Apytikslis bendras laikas, min.",
            value="" if case.get("gpt_human_minutes") is None else str(case.get("gpt_human_minutes")),
            key=f"update_minutes_{case['id']}"
        )
        note_txt=st.text_area(
            "Proceso pastaba",
            value=str(case.get("method_note") or ""),
            key=f"update_method_{case['id']}"
        )
        if st.button("IŠSAUGOTI TIK PROCESO METADATA",key=f"save_process_{case['id']}"):
            try:
                db.update_research_scheduler_process_v2541(
                    case["id"],_research_parse_optional_int(it_txt),
                    _research_parse_optional_float(min_txt),note_txt
                )
                st.success("Proceso metaduomenys atnaujinti; užfiksuota įvestis ir grafikas nepakeisti.")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    # Frozen run log.
    st.markdown("### Grafiko variklio bandymų žurnalas")
    if runs:
        logdf=_research_run_log_df(runs)
        st.dataframe(logdf,use_container_width=True,hide_index=True)
        st.caption(
            f"Užfiksuota variklio bandymų: {len(runs)}/5 · bendras skaičiavimo laikas: "
            f"{sum(float(r.get('elapsed_seconds') or 0) for r in runs):.2f} s."
        )
    else:
        st.error("Tyrimo atvejis yra, tačiau trūksta pirmojo bandymo. Atvejo nekurk iš naujo; atlik kitą variklio bandymą žemiau.")

    # Engine version is frozen server-side by the case; block future run if local build changed.
    version_ok=(
        str(case.get("app_version_at_lock"))==APP_VERSION
        and int(case.get("rule_profile_version_at_lock") or 0)==int(ACTIVE_RULE_PROFILE_VERSION)
    )
    if not version_ok:
        st.error(
            "UŽFIKSUOTO VARIKLIO VERSIJA NESUTAMPA — šį tyrimo atvejį galima tęsti tik su "
            f"{case.get('app_version_at_lock')} / taisyklių profilis v{case.get('rule_profile_version_at_lock')}. "
            "Naujo bandymo su kita versija neatlik."
        )

    next_no=len(runs)+1
    if next_no<=5:
        role="PIRMAS BANDYMAS" if next_no==1 else f"TOBULINIMO BANDYMAS {next_no-1}"
        if st.button(
            f"PALEISTI VARIKLĮ #{next_no}/5 — {role}",
            type="primary" if next_no==1 else "secondary",
            use_container_width=True,disabled=not version_ok,
            key=f"research_next_run_{case['id']}_{next_no}"
        ):
            try:
                # Reconstruct locked input directly from DB; no re-upload/cherry-picking.
                locked_hash=_research_input_hash(ry,rm,people)
                if locked_hash!=case.get("input_hash"):
                    st.error("Užfiksuotos įvesties kontrolinis kodas nesutampa. Bandymas nutrauktas.")
                    return
                t0=perf_counter()
                try:
                    algorithm=solve_schedule(ry,rm,people,time_limit=180.0)
                    elapsed=perf_counter()-t0
                    full_stats=_research_json_safe(algorithm.stats or {})
                    gg=full_stats.get("global",{}) if isinstance(full_stats,dict) else {}
                    run_assignments=algorithm.assignments
                    run_ok=algorithm.ok
                except Exception as solve_exc:
                    elapsed=perf_counter()-t0
                    full_stats={"global":{
                        "hard_errors":None,
                        "errors":[f"ENGINE EXCEPTION: {type(solve_exc).__name__}: {solve_exc}"],
                        "solve_stage":"ENGINE_EXCEPTION",
                    },"people":{}}
                    gg=full_stats["global"]
                    run_assignments={}
                    run_ok=False

                saved=db.record_research_scheduler_run_v2541(
                    case["id"],locked_hash,elapsed,run_ok,
                    APP_VERSION,ACTIVE_RULE_PROFILE_VERSION,gg,
                    run_assignments,raw_metrics=_research_json_safe(full_stats),
                )
                st.success(f"Bandymas {saved.get('run_no',next_no)} išsaugotas kaip nekintamas įrašas.")
                st.rerun()
            except Exception as e:
                if "RESEARCH_RUN_LIMIT_REACHED" in str(e):
                    st.error("Jau pasiekti 5 variklio bandymai — daugiau atlikti negalima.")
                else:
                    st.exception(e)
    else:
        st.success("Atlikti visi 5/5 variklio bandymai. Tyrimo bandymų ciklas užrakintas.")

    # Primary comparison = immutable 1 bandymas.
    first=next((r for r in runs if int(r.get("run_no") or 0)==1),None)
    valid_runs=[r for r in runs if bool(r.get("success")) and int(r.get("hard_errors") or 0)==0]
    best=min(valid_runs,key=_research_run_quality_key) if valid_runs else None

    cg=comparator.stats.get("global",{})
    st.markdown("### Palyginimo atskaitos grafikas — Bendrinis DI + seniūnė")
    b1,b2,b3,b4=st.columns(4)
    b1.metric("Privalomų taisyklių klaidos *",cg.get("hard_errors"))
    b2.metric("Mėnesio teisingumas",cg.get("monthly_fairness_score"))
    b3.metric("Pageidavimų įvykdymas %",cg.get("mean_preference_score") if cg.get("mean_preference_score") is not None else "—")
    b4.metric("Darbo vietų netolygumas",cg.get("rotation_monthly_imbalance"))
    if cg.get("errors"):
        with st.expander(f"Bendrinio DI + seniūnės privalomų taisyklių radiniai ({len(cg.get('errors',[]))})",expanded=False):
            for e in cg.get("errors",[]):
                st.write("• "+_hard_error_explanation(e,lang))

    run1_result=(
        _research_result_from_run(first,people,ry,rm)
        if first and first.get("success") else None
    )
    best_result=(
        _research_result_from_run(best,people,ry,rm)
        if best else None
    )

    if first:
        if run1_result is not None:
            st.markdown("### PAGRINDINIS PALYGINIMAS — bendrinis DI + seniūnė ir specializuoto variklio pirmasis bandymas")
            st.dataframe(
                _research_metric_rows(comparator,run1_result,"Specializuotas variklis — 1 bandymas"),
                use_container_width=True,hide_index=True
            )
            left,right=st.columns(2)
            with left:
                st.markdown("**Bendrinis DI + seniūnė — realiai naudotas grafikas**")
                st.dataframe(schedule_list_df(ry,rm,comparator),use_container_width=True,hide_index=True,height=480)
            with right:
                st.markdown("**Specializuotas grafiko variklis — nekintamas pirmasis bandymas**")
                st.dataframe(schedule_list_df(ry,rm,run1_result),use_container_width=True,hide_index=True,height=480)

            st.markdown("### TIE PATYS UŽFIKSUOTI PAGEIDAVIMAI — tiesioginis rezultatų palyginimas")
            st.caption(
                "Tai tiesioginis palyginimas: abu grafikai iš naujo patikrinami pagal tiksliai tą pačią užfiksuotą rezidentų pageidavimų įvestį. "
                "Iš rankiniu būdu sudaryto grafiko jokie papildomi pageidavimai nenumanomi."
            )
            _ct=_research_result_wish_totals(comparator); _et=_research_result_wish_totals(run1_result)
            w1,w2,w3,w4=st.columns(4)
            w1.metric("Aktyvūs užfiksuoti pageidavimai",_ct["active"])
            w2.metric("Bendrinis DI + seniūnė — įvykdyta",f"{_ct['honored']}/{_ct['active']}" if _ct['active'] else "N/A")
            w3.metric("Specializuotas variklis — įvykdyta",f"{_et['honored']}/{_et['active']}" if _et['active'] else "N/A")
            w4.metric("„Dirbti negaliu“ pažeidimai: bendrinis DI / variklis",f"{_ct['hard_missed']} / {_et['hard_missed']}")
            st.dataframe(
                _research_wish_summary_comparison_df(comparator,run1_result,people),
                use_container_width=True,hide_index=True,height=520
            )
            _wishcmp=_research_wish_request_comparison_df(comparator,run1_result,people)
            _diff=_wishcmp[_wishcmp["Rezultatas"]!="Abu įvykdyti"] if not _wishcmp.empty else _wishcmp
            if _diff.empty:
                st.success("Abu grafikai įvykdė visus užfiksuotus pageidavimus.")
            else:
                st.markdown("**Neįvykdyti arba skirtingai įvykdyti pageidavimai**")
                st.dataframe(_diff,use_container_width=True,hide_index=True,height=520)
            with st.expander("Rodyti visus užfiksuotus pageidavimus",expanded=False):
                st.dataframe(_wishcmp,use_container_width=True,hide_index=True,height=620)
        else:
            st.error(
                f"Pagrindinis pirmasis bandymas nepavyko po {float(first.get('elapsed_seconds') or 0):.2f} s. "
                "Tai yra galiojantis pagrindinis tyrimo rezultatas ir jo negalima pakeisti vėlesniu bandymu."
            )

    if best_result is not None:
        st.markdown(f"### PAPILDOMI BANDYMAI — geriausias iš {len(runs)} = bandymas {best['run_no']}")
        st.caption(
            "Geriausias papildomas bandymas parenkamas taip: be privalomų taisyklių klaidų → didžiausias mėnesio teisingumas → mažesnis darbo vietų netolygumas → "
            "didesnis pageidavimų išpildymas → didesnė darbo vietų įvairovė. Pirmasis bandymas lieka pagrindinis ir nėra pakeičiamas."
        )
        st.dataframe(
            _research_metric_rows(comparator,best_result,f"Specializuotas variklis — geriausias bandymas {best['run_no']}"),
            use_container_width=True,hide_index=True
        )

    st.markdown("### DARBO VIETŲ PASKIRSTYMAS")
    st.caption(
        "Čia matomas ne tik bendras teisingumo rodiklis. Kiekvienai darbo vietai rodomas bendras paskyrimų skaičius, "
        "mažiausias ir didžiausias paskyrimų skaičius vienam rezidentui bei jų skirtumas. "
        "Neigiamas skirtumo pokytis reiškia, kad specializuotas grafiko variklis tą darbo vietą paskirstė tolygiau už bendrinį DI + seniūnę."
    )
    post_compare=_research_post_spread_comparison_df(
        comparator,people,
        run1_result=run1_result,
        best_result=best_result,
        best_label=("Geriausias" if best is None else f"Geriausias bandymas {best['run_no']}")
    )
    st.dataframe(post_compare,use_container_width=True,hide_index=True)

    with st.expander("Rezidentų × darbo vietų matricos",expanded=False):
        st.markdown("**Bendrinis DI + seniūnė**")
        st.dataframe(
            _research_post_matrix_df(comparator,people),
            use_container_width=True,hide_index=True
        )
        if run1_result is not None:
            st.markdown("**Specializuotas variklis — 1 bandymas / PIRMAS BANDYMAS**")
            st.dataframe(
                _research_post_matrix_df(run1_result,people),
                use_container_width=True,hide_index=True
            )
        if best_result is not None:
            st.markdown(f"**Specializuotas variklis — geriausias bandymas {best['run_no']}**")
            st.dataframe(
                _research_post_matrix_df(best_result,people),
                use_container_width=True,hide_index=True
            )

    warnings=case.get("import_warnings") or []
    if warnings:
        with st.expander(f"Importo perspėjimai ({len(warnings)})"):
            for w in warnings:
                st.write("• "+str(w))

    report=research_locked_comparison_xlsx(ry,rm,case,people,comparator,runs,questionnaires)
    st.download_button(
        "ATSISIŲSTI UŽRAKINTĄ TYRIMO DUOMENŲ RINKINĮ (.xlsx)",
        report,
        file_name=f"available_gpt_human_vs_engine_{ry}_{rm:02d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",use_container_width=True
    )
    st.caption(
        "Tyrimo interpretacija: Bendrinis DI + seniūnė = realus iteracinis bendrinio DI ir seniūnės darbo srautas; "
        "Specializuoto variklio 1-asis bandymas = pagrindinis tyrimo rezultatas; 2–5 bandymai = papildomi tobulinimo, paspaudimų ir laiko efektyvumo bandymai."
    )


def render_opto_research_workbench():
    """Neutral three-arm research workbench: HUMAN vs RAPA vs OPTO."""
    st.subheader("OPTO vs RAPA vs RANKA")
    st.caption(
        "Izoliuotas tyrimo workbench'as. Extension = kitos grupės taisyklės / darbo paradigma. "
        "Ta pati extension ir ta pati realių pageidavimų įvestis naudojama RAPA, OPTO ir žmogaus sudarytam grafikui vertinti. "
        "Niekas šiame bloke nerašoma į SYSTEM ar ACTUAL grafiką."
    )
    st.info(
        "Trys lygiaverčiai audito metodai: RANKA (žmogaus sudarytas Excel), RAPA (mano izoliuotas engine paleidimas) ir OPTO (OPTO sugeneruotas Excel). "
        "Galima lyginti bet kurią porą arba visus tris vienu metu pagal identiškas metrikas."
    )

    c1,c2=st.columns(2)
    ry=int(c1.number_input("Tyrimo metai",min_value=2026,max_value=2100,value=int(year),step=1,key="opto_research_year"))
    rm=int(c2.selectbox("Tyrimo mėnuo",options=list(range(1,13)),index=int(month)-1,key="opto_research_month"))

    st.markdown("#### 1. Grupės extension")
    st.caption("Extension aprašo tik grupės paradigmą: žmones, postus, pamainų tipus, kiekius ir lokalias taisykles. Jis nėra grafikas.")
    x1,x2=st.columns([2,1])
    ext_file=x1.file_uploader(
        "Įkelti grupės taisykles / extension",
        type=["json","xlsx","xls","docx","pdf"],
        key=f"opto_extension_{ry}_{rm}",
        help="JSON/Excel struktūruojami tiesiogiai. Word/PDF paverčiami extension juodraščiu ir prieš paleidimą parodomi patikrai.",
    )
    x2.download_button(
        "EXTENSION EXCEL ŠABLONAS",
        opto_extension_template_xlsx(),
        file_name="RAPA_extension_sablonas.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    use_current=st.checkbox("Naudoti dabartinės I kurso grupės extension",value=True,key=f"opto_use_current_{ry}_{rm}")

    research_ext=None
    ext_warnings=[]
    if ext_file is not None:
        try:
            research_ext,ext_warnings=parse_opto_extension_upload(ext_file.getvalue(),ext_file.name)
        except Exception as exc:
            st.error(f"Extension nepavyko perskaityti: {exc}")
    elif use_current:
        try:
            example_path=BASE/"extensions"/"LSMU_R1_2026_10.extension.json"
            research_ext=load_optus_extension(example_path.read_bytes())
        except Exception as exc:
            st.error(f"Dabartinės grupės extension nepavyko atidaryti: {exc}")

    if research_ext is None:
        st.caption("Įkelkite extension arba pasirinkite dabartinės grupės pavyzdį — tada atsivers pageidavimų ir trijų grafikų palyginimas.")
        return

    for w in ext_warnings:
        st.warning(w)
    try:
        es=optus_extension_summary(research_ext,ry,rm)
        m1,m2,m3,m4=st.columns(4)
        m1.metric("Žmonės",es.get("people",0)); m2.metric("Pamainos",es.get("slots",0))
        m3.metric("6 h vienetai",round(float(es.get("workload2",0))/2.0,1)); m4.metric("Postai",len(es.get("by_category") or {}))
        with st.expander("Patikrinti extension santrauką",expanded=False):
            st.dataframe(pd.DataFrame([
                {"Postas":k,"Pamainų skaičius":v} for k,v in (es.get("by_category") or {}).items()
            ]),use_container_width=True,hide_index=True)
            st.dataframe(pd.DataFrame(research_ext.get("people") or []),use_container_width=True,hide_index=True)
            st.download_button(
                "ATSISIŲSTI NORMALIZUOTĄ EXTENSION (.json)",
                json.dumps(research_ext,ensure_ascii=False,indent=2).encode("utf-8"),
                file_name=f"{research_ext.get('extension_id','group')}.extension.json",
                mime="application/json",use_container_width=True,
            )
    except Exception as exc:
        st.error(f"Extension validacija nepraėjo: {exc}")
        return

    st.markdown("#### 2. Realūs grupės pageidavimai")
    p1,p2=st.columns([2,1])
    pref_file=p1.file_uploader(
        "Įkelti realius tos grupės pageidavimus (Excel)",type=["xlsx","xls"],key=f"opto_prefs_{ry}_{rm}",
        help="Tie patys pageidavimai naudojami visų trijų metodų vertinimui."
    )
    p2.download_button(
        "PAGEIDAVIMŲ ŠABLONAS",
        opto_preferences_template_xlsx(research_ext,ry,rm),
        file_name=f"pageidavimai_{ry}_{rm:02d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True,
    )
    frozen_ext=research_ext
    pref_warnings=[]
    pref_bytes=b""
    if pref_file is not None:
        pref_bytes=pref_file.getvalue()
        try:
            prefs,pref_warnings=parse_opto_preferences_excel(pref_bytes,research_ext,ry,rm)
            frozen_ext=apply_opto_preferences(research_ext,prefs)
            active_off=sum(len(v.get("unavailable_days") or []) for v in prefs.values())
            active_pref=sum(len(v.get("preferred_days") or []) for v in prefs.values())
            st.success(f"Pageidavimai įkelti: „Dirbti negaliu“ įrašų {active_off} · „Pageidauju dirbti“ įrašų {active_pref}.")
        except Exception as exc:
            st.error(f"Pageidavimų failo nepavyko perskaityti: {exc}")
            return
    else:
        st.warning("Pageidavimų failas dar neįkeltas. Galima testuoti tik struktūrinį fairness, bet realiam tyrimo palyginimui įkelkite tikrus tos grupės pageidavimus.")
    for w in pref_warnings:
        st.caption("• "+str(w))

    st.markdown("#### 3. Trys grafiko metodai")
    t1,t2,t3=st.columns(3)
    human_file=t1.file_uploader("RANKA · jų pačių Excel grafikas",type=["xlsx","xls"],key=f"opto_human_{ry}_{rm}")
    opto_file=t2.file_uploader("OPTO · OPTO sugeneruotas Excel grafikas",type=["xlsx","xls"],key=f"opto_model_{ry}_{rm}")
    with t3:
        st.caption("RAPA · generuojamas iš aukščiau įkeltų extension + pageidavimų")
        run_rapa=st.button("GENERUOTI RAPA",type="primary",use_container_width=True,key=f"opto_run_rapa_{ry}_{rm}")

    st.download_button(
        "ATSISIŲSTI BENDRĄ GRAFIKO EXCEL ŠABLONĄ",
        opto_schedule_template_xlsx(frozen_ext,ry,rm),
        file_name=f"grafiko_sablonas_{ry}_{rm:02d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True,
        key=f"opto_schedule_template_{ry}_{rm}",
    )

    input_hash=hashlib.sha256(
        (json.dumps(frozen_ext,ensure_ascii=False,sort_keys=True)+str(ry)+str(rm)).encode("utf-8")+pref_bytes
    ).hexdigest()[:16]
    rapa_state_key=f"opto_rapa_assignments_{input_hash}"
    if run_rapa:
        try:
            with st.spinner("RAPA izoliuotai generuoja grafiką pagal šios grupės extension..."):
                rr=solve_rapa_extension_research(frozen_ext,ry,rm,time_limit=25.0)
            if rr.get("ok"):
                st.session_state[rapa_state_key]=rr.get("assignments") or {}
                st.success("RAPA grafikas sugeneruotas. Production grafikas nepakeistas.")
                if rr.get("post_corridors_relaxed"):
                    st.warning("Kai kuriems postams 0–1 koridorius buvo matematiškai per griežtas; RAPA išlaikė coverage/saugą/workload/weekend fairness ir atlaisvino tik postų koridorių.")
            else:
                st.error(rr.get("message","RAPA grafiko sugeneruoti nepavyko."))
        except Exception as exc:
            st.error(f"RAPA izoliuotas paleidimas nepavyko: {exc}")

    schedules={}
    schedule_warnings={}
    def _read_arm(label,uploaded):
        if uploaded is None:
            return
        try:
            a,w=parse_opto_schedule_excel(uploaded.getvalue(),frozen_ext,ry,rm)
            schedules[label]=a; schedule_warnings[label]=w
        except Exception as exc:
            st.error(f"{label} grafiko nepavyko perskaityti: {exc}")
    _read_arm("RANKA",human_file)
    _read_arm("OPTO",opto_file)
    if rapa_state_key in st.session_state:
        schedules["RAPA"]=st.session_state[rapa_state_key]

    for arm,warns in schedule_warnings.items():
        for w in warns[:8]:
            st.caption(f"{arm}: {w}")
        if len(warns)>8:
            st.caption(f"{arm}: dar {len(warns)-8} importo pastabų.")

    if not schedules:
        st.caption("Įkelkite bent vieną realų/OPTO grafiką arba sugeneruokite RAPA grafiką.")
        return

    metrics={arm:evaluate_opto_schedule(frozen_ext,ry,rm,a) for arm,a in schedules.items()}
    st.markdown("#### 4. Vienodas vertinimas")
    pair_options=[]
    if all(x in schedules for x in ("RANKA","RAPA")): pair_options.append("RANKA vs RAPA")
    if all(x in schedules for x in ("RANKA","OPTO")): pair_options.append("RANKA vs OPTO")
    if all(x in schedules for x in ("RAPA","OPTO")): pair_options.append("RAPA vs OPTO")
    if len(schedules)>=2: pair_options.append("VISI TURIMI METODAI")
    compare_mode=st.radio("Palyginimas",pair_options or ["VISI TURIMI METODAI"],horizontal=True,key=f"opto_compare_mode_{ry}_{rm}")
    if compare_mode=="VISI TURIMI METODAI":
        selected=list(schedules.keys())
    else:
        selected=[x.strip() for x in compare_mode.split("vs")]
    selected_metrics={k:metrics[k] for k in selected if k in metrics}
    st.dataframe(opto_comparison_dataframe(selected_metrics),use_container_width=True,hide_index=True)

    arm_tabs=st.tabs([f"{arm} · grafikas" for arm in selected]) if selected else []
    for tab,arm in zip(arm_tabs,selected):
        with tab:
            st.dataframe(opto_assignments_dataframe(frozen_ext,ry,rm,schedules[arm]),use_container_width=True,hide_index=True)
            mm=metrics[arm]
            a,b,c,d=st.columns(4)
            a.metric("Pageidavimai",f"{mm.get('wish_pct',0)}%")
            b.metric("HARD klaidos",mm.get("hard_errors",0))
            c.metric("Krūvio skirtumas",mm.get("workload_spread",0))
            d.metric("Savaitgalių skirtumas",mm.get("weekend_spread",0))

    if len(schedules)>=2:
        report=opto_comparison_xlsx(frozen_ext,ry,rm,schedules,metrics)
        st.download_button(
            "ATSISIŲSTI OPTO TYRIMO PALYGINIMĄ (.xlsx)",report,
            file_name=f"OPTO_tyrimas_{ry}_{rm:02d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",use_container_width=True,key=f"opto_research_export_{ry}_{rm}",
        )
        st.caption("Eksporte yra bendra metrikų lentelė ir kiekvieno įkelto / sugeneruoto metodo grafikas. Tai izoliuotas tyrimo failas.")



# --- Research ---
with tabs[pos]:
    # V2.5.154: keep the questionnaire identity stable for every account/mode.
    st.subheader(tr("research_survey"))
    st.caption(tr("research_privacy"))
    st.markdown(f"### {tr('research_study_plan')}")
    st.info(f"{tr('research_study_period')}  \n{tr('research_primary_outcomes')}")

    # Resident survey: exactly three planned checkpoints across the study.
    st.markdown(f"### {tr('research_survey')}")
    st.caption(tr("research_resident_note"))
    cp_codes=[c for c,_,_,_ in RESIDENT_RESEARCH_CHECKPOINTS]
    # Prefer baseline before launch, then month-3, then month-6. Users can still open any checkpoint for QA/testing.
    completed={}
    for c,ph,yy,mm in RESIDENT_RESEARCH_CHECKPOINTS:
        completed[c]=bool(db.get_my_research_survey(ph,yy,mm))
    default_cp=next((c for c in cp_codes if not completed[c]),cp_codes[-1])
    cp=st.selectbox(tr("research_checkpoint"),cp_codes,index=cp_codes.index(default_cp),format_func=research_checkpoint_label,key="research_checkpoint_select")
    phase,sy,sm=research_checkpoint_for_storage(cp)
    status_cols=st.columns(3)
    current_period=(year,month)
    activation={"baseline":(2026,9),"month3":(2026,12),"month6":(2027,3)}
    for i,c in enumerate(cp_codes):
        if completed[c]:
            status="✓ " + tr("research_checkpoint_done")
        elif current_period < activation[c]:
            status=tr("research_checkpoint_locked")
        else:
            status=tr("research_checkpoint_pending")
        status_cols[i].metric(research_checkpoint_label(c),status)

    existing=db.get_my_research_survey(phase,sy,sm) or {}
    old_answers=existing.get("answers") or {}
    old_free=existing.get("free_text") or {}
    st.caption(tr("research_likert_help"))
    item_labels=RESEARCH_ITEMS_LT if lang=="LT" else RESEARCH_ITEMS
    with st.form(f"research_form_{active_user}_{cp}"):
        answers={}
        for key,label in item_labels.items():
            default=int(old_answers.get(key,3)) if str(old_answers.get(key,"")).isdigit() else 3
            answers[key]=st.slider(label,1,5,default,1,key=f"rq_{cp}_{key}")
        answers["stress"]=st.slider(tr("research_stress"),0,10,int(old_answers.get("stress",5) or 5),1,key=f"rq_{cp}_stress")
        answers["change_count"]=st.selectbox(tr("research_changes"),[0,1,2,3,4],index=min(int(old_answers.get("change_count",0) or 0),4),format_func=lambda x:"4+" if x==4 else str(x),key=f"rq_{cp}_changes")
        contact_opts=["never","rarely","sometimes","often","very_often"]
        contact_labels={"LT":["Niekada","Retai","Kartais","Dažnai","Labai dažnai"],"EN":["Never","Rarely","Sometimes","Often","Very often"]}[lang]
        old_contact_code=int(old_answers.get("contact_frequency_code",0) or 0)
        old_contact_code=max(0,min(old_contact_code,4))
        contact=st.selectbox(tr("research_contact"),contact_opts,index=old_contact_code,format_func=lambda x:contact_labels[contact_opts.index(x)],key=f"rq_{cp}_contact")
        answers["contact_frequency_code"]=contact_opts.index(contact)
        if phase=="followup":
            for key,label_key in [("easy","research_easy"),("mobile","research_mobile"),("actual","research_actual"),("system_actual","research_system_actual"),("continue","research_continue")]:
                answers[key]=st.slider(tr(label_key),1,5,int(old_answers.get(key,3) or 3),1,key=f"rq_{cp}_{key}")
        problem=st.text_area(tr("research_problem"),value=old_free.get("problem","") or "",key=f"rq_{cp}_problem")
        improve=st.text_area(tr("research_improve"),value=old_free.get("improve","") or "",key=f"rq_{cp}_improve")
        submitted=st.form_submit_button(tr("research_submit"),type="primary")
        if submitted:
            db.submit_research_survey(phase,sy,sm,answers,{"problem":problem,"improve":improve,"checkpoint":cp})
            st.success(tr("research_saved"))

    # Current Seniūnė: workflow-burden checkpoints, separate from the resident survey.
    if active_user==SENIOR_INITIALS:
        st.divider(); st.markdown(f"### {tr('research_scheduler_section')}")
        st.caption(tr("research_scheduler_intro"))
        study_options=[f"{yy:04d}-{mm:02d}" for yy,mm in STUDY_MONTHS]
        current_key=f"{year:04d}-{month:02d}"
        default_idx=study_options.index(current_key) if current_key in study_options else 0
        month_key=st.selectbox(tr("research_scheduler_month"),study_options,index=default_idx,format_func=lambda x:study_month_label(int(x[:4]),int(x[5:])),key="senior_research_month")
        gy,gm=map(int,month_key.split("-"))
        checkpoint=st.radio(tr("research_scheduler_checkpoint"),["post_creation","post_month"],format_func=lambda x:tr("research_after_creation") if x=="post_creation" else tr("research_after_month"),horizontal=True,key="senior_research_checkpoint")
        old=db.get_my_scheduler_research_checkpoint(gy,gm,checkpoint) or {}
        oa=old.get("answers") or {}; of=old.get("free_text") or {}
        if checkpoint=="post_creation":
            methods=["tool","excel","shadow"]
            method_labels={"tool":tr("research_method_tool"),"excel":tr("research_method_excel"),"shadow":tr("research_method_shadow")}
            with st.form(f"senior_creation_{gy}_{gm}"):
                method=st.selectbox(tr("research_workflow_method"),methods,index=methods.index(oa.get("method","shadow") if oa.get("method","shadow") in methods else "shadow"),format_func=lambda x:method_labels[x])
                c1,c2=st.columns(2)
                total_minutes=c1.number_input(tr("research_total_minutes"),0,2000,int(oa.get("total_minutes",0) or 0),5)
                corrections=c2.number_input(tr("research_corrections"),0,200,int(oa.get("corrections",0) or 0),1)
                c3,c4=st.columns(2)
                contacts=c3.number_input(tr("research_resident_contacts"),0,500,int(oa.get("resident_contacts",0) or 0),1)
                comm_minutes=c4.number_input(tr("research_communication_minutes"),0,2000,int(oa.get("communication_minutes",0) or 0),5)
                stress=st.slider(tr("research_scheduler_stress"),0,10,int(oa.get("stress",5) or 5),1)
                q1,q2,q3=st.columns(3)
                fairness=q1.slider(tr("research_fairness_confidence"),1,5,int(oa.get("fairness_confidence",3) or 3),1)
                hard=q2.slider(tr("research_hard_confidence"),1,5,int(oa.get("hard_confidence",3) or 3),1)
                sat=q3.slider(tr("research_scheduler_satisfaction"),1,5,int(oa.get("satisfaction",3) or 3),1)
                excel_minutes=tool_minutes=excel_corr=tool_corr=0
                if method=="shadow":
                    a,b=st.columns(2); excel_minutes=a.number_input(tr("research_excel_minutes"),0,2000,int(oa.get("excel_minutes",0) or 0),5); tool_minutes=b.number_input(tr("research_tool_minutes"),0,2000,int(oa.get("tool_minutes",0) or 0),5)
                    a,b=st.columns(2); excel_corr=a.number_input(tr("research_excel_corrections"),0,200,int(oa.get("excel_corrections",0) or 0),1); tool_corr=b.number_input(tr("research_tool_corrections"),0,200,int(oa.get("tool_corrections",0) or 0),1)
                notes=st.text_area(tr("research_scheduler_notes"),value=of.get("notes","") or "")
                if st.form_submit_button(tr("research_submit"),type="primary"):
                    db.submit_scheduler_research_checkpoint(gy,gm,checkpoint,{"method":method,"total_minutes":total_minutes,"corrections":corrections,"resident_contacts":contacts,"communication_minutes":comm_minutes,"stress":stress,"fairness_confidence":fairness,"hard_confidence":hard,"satisfaction":sat,"excel_minutes":excel_minutes,"tool_minutes":tool_minutes,"excel_corrections":excel_corr,"tool_corrections":tool_corr},{"notes":notes})
                    st.success(tr("research_scheduler_saved"))
        else:
            with st.form(f"senior_month_{gy}_{gm}"):
                c1,c2=st.columns(2)
                post_minutes=c1.number_input(tr("research_post_minutes"),0,3000,int(oa.get("post_minutes",0) or 0),5)
                interventions=c2.number_input(tr("research_post_interventions"),0,500,int(oa.get("interventions",0) or 0),1)
                contacts=st.number_input(tr("research_post_contacts"),0,1000,int(oa.get("post_contacts",0) or 0),1)
                stress=st.slider(tr("research_stress"),0,10,int(oa.get("stress",5) or 5),1,key=f"senior_post_stress_{gy}_{gm}")
                q1,q2=st.columns(2)
                actual_conf=q1.slider(tr("research_actual_confidence"),1,5,int(oa.get("actual_confidence",3) or 3),1)
                sat=q2.slider(tr("research_scheduler_satisfaction"),1,5,int(oa.get("satisfaction",3) or 3),1,key=f"senior_post_sat_{gy}_{gm}")
                use_opts=["yes","unsure","no"]; use_labels={"yes":tr("research_yes"),"unsure":tr("research_unsure"),"no":tr("research_no")}
                old_use=oa.get("use_next","unsure") if oa.get("use_next","unsure") in use_opts else "unsure"
                use_next=st.selectbox(tr("research_use_next"),use_opts,index=use_opts.index(old_use),format_func=lambda x:use_labels[x])
                notes=st.text_area(tr("research_scheduler_notes"),value=of.get("notes","") or "",key=f"senior_post_notes_{gy}_{gm}")
                if st.form_submit_button(tr("research_submit"),type="primary"):
                    db.submit_scheduler_research_checkpoint(gy,gm,checkpoint,{"post_minutes":post_minutes,"interventions":interventions,"post_contacts":contacts,"stress":stress,"actual_confidence":actual_conf,"satisfaction":sat,"use_next":use_next},{"notes":notes})
                    st.success(tr("research_scheduler_saved"))
        # Show automatic operational counts for the same month to reduce manual counting burden.
        cp_current=db.load_schedule(gy,gm,"current"); cp_base=db.load_schedule(gy,gm,"baseline")
        if cp_current:
            cr=deserialize_result(cp_current); br=deserialize_result(cp_base or cp_current); gg=br.stats.get("global",{})
            try: changed=len(observer_assignment_changes_df(gy,gm,br,cr))
            except Exception: changed=0
            nsw=len(db.list_swap_requests(gy,gm,None)); bsw=len(db.list_backup_swap_requests(gy,gm,None)); covers=sum(1 for r in db.list_backups(gy,gm) if r.get("completed_at"))
            m1,m2,m3,m4=st.columns(4); m1.metric(tr("research_changed_assignments"),changed); m2.metric(tr("research_normal_swaps"),nsw); m3.metric(tr("research_backup_swaps"),bsw); m4.metric(tr("research_completed_covers"),covers)

    # Aggregate dashboard: current Seniūnė gets group-only results; ŠR gets full research QA / exports.
    if active_user in (RESEARCHER_INITIALS,SENIOR_INITIALS) and advanced_mode:
        st.divider(); st.markdown(f"### {tr('research_dashboard')}")
        st.info(tr("research_rs_note") if active_user==RESEARCHER_INITIALS else tr("research_gm_note"))
        counts=db.research_checkpoint_counts(); summary=db.research_checkpoint_summary()
        count_map={(int(r.get("cycle_year")),int(r.get("cycle_month"))):int(r.get("response_count",0)) for r in counts}
        c1,c2,c3=st.columns(3)
        c1.metric(tr("research_baseline_checkpoint"),f"{count_map.get((2026,9),0)}/{RESEARCH_EXPECTED_RESIDENTS}")
        c2.metric(tr("research_month3_checkpoint"),f"{count_map.get((2026,12),0)}/{RESEARCH_EXPECTED_RESIDENTS}")
        c3.metric(tr("research_month6_checkpoint"),f"{count_map.get((2027,3),0)}/{RESEARCH_EXPECTED_RESIDENTS}")
        if summary:
            sdf=pd.DataFrame(summary)
            label_map={(2026,9):("Pradinis vertinimas" if lang=="LT" else "Baseline"),(2026,12):("3 mėn." if lang=="LT" else "Month 3"),(2027,3):("6 mėn." if lang=="LT" else "Month 6")}
            sdf["Checkpoint"]=[label_map.get((int(y),int(m)),f"{y}-{int(m):02d}") for y,m in zip(sdf["cycle_year"],sdf["cycle_month"])]
            piv=sdf.pivot(index="question_key",columns="Checkpoint",values="mean_score").reset_index()
            st.markdown(f"### {tr('research_survey_results')}"); st.dataframe(piv,use_container_width=True,hide_index=True)
        else:
            st.caption(tr("research_no_data"))

        # Monthly objective metrics across the full six-month prospective period.
        monthly=[]
        for yy,mm in STUDY_MONTHS:
            curp=db.load_schedule(yy,mm,"current"); basep=db.load_schedule(yy,mm,"baseline")
            row={("Laikotarpis" if lang=="LT" else "Period"):f"{yy}-{mm:02d}",( "Paskelbtas" if lang=="LT" else "Published"):bool(curp)}
            if curp:
                # V2.5.49 retrospective satisfaction: SYSTEM stays frozen at publication,
                # while ACTUAL is recalculated against the SAME frozen ORIGINAL request set.
                # This lets the six-month study later measure whether resident-led swaps
                # improved or worsened realized request satisfaction without rewriting
                # algorithmic fairness history.
                cr=refresh_result_payload(curp,yy,mm,use_actual_backups=True) or deserialize_result(curp)
                br=refresh_result_payload(basep or curp,yy,mm,use_actual_backups=False) or deserialize_result(basep or curp)
                gg=br.stats.get("global",{})
                ag=cr.stats.get("global",{})
                published_sat=gg.get("mean_preference_score")
                actual_sat=ag.get("mean_preference_score")
                sat_delta=(round(float(actual_sat)-float(published_sat),1) if published_sat is not None and actual_sat is not None else None)
                sys_live=calculate_live_fairness_snapshot(yy,mm,br.assignments,people_initials=[p["initials"] for p in DEFAULT_PEOPLE],backup_assignments=[])["global"]
                act_live=calculate_live_fairness_snapshot(yy,mm,cr.assignments,people_initials=[p["initials"] for p in DEFAULT_PEOPLE],backup_assignments=db.list_backups(yy,mm))["global"]
                row.update({
                    ("Privalomų taisyklių klaidos" if lang=="LT" else "HARD"):gg.get("hard_errors"),
                    ("SYSTEM mėnesio fairness" if lang=="LT" else "SYSTEM monthly fairness"):sys_live.get("monthly_fairness_score"),
                    ("ACTUAL mėnesio fairness" if lang=="LT" else "ACTUAL monthly fairness"):act_live.get("monthly_fairness_score"),
                    ("Faktinis−pradinis balansas, proc. p." if lang=="LT" else "Actual−baseline balance, pp"):round(float(act_live.get("monthly_fairness_score",0))-float(sys_live.get("monthly_fairness_score",0)),1),
                    ("SYSTEM postų imbalance" if lang=="LT" else "SYSTEM post imbalance"):sys_live.get("rotation_monthly_imbalance"),
                    ("ACTUAL postų imbalance" if lang=="LT" else "ACTUAL post imbalance"):act_live.get("rotation_monthly_imbalance"),
                    ("SYSTEM pageidavimų išpildymas %" if lang=="LT" else "SYSTEM request satisfaction %"):published_sat,
                    ("ACTUAL pageidavimų išpildymas %" if lang=="LT" else "ACTUAL request satisfaction %"):actual_sat,
                    ("Pokytis po apsikeitimų, proc. p." if lang=="LT" else "Change after swaps, pp"):sat_delta,
                    ("SYSTEM RESIDENT HARD pažeidimai" if lang=="LT" else "SYSTEM RESIDENT HARD violations"):gg.get("resident_hard_total_losses",0),
                    ("ACTUAL RESIDENT HARD pažeidimai" if lang=="LT" else "ACTUAL RESIDENT HARD violations"):ag.get("resident_hard_total_losses",0),
                })
                try: row[("Sistemos→faktinio grafiko pakeitimai" if lang=="LT" else "SYSTEM→ACTUAL changes")]=len(observer_assignment_changes_df(yy,mm,br,cr))
                except Exception: row[("Sistemos→faktinio grafiko pakeitimai" if lang=="LT" else "SYSTEM→ACTUAL changes")]=0
                row["Normal swaps"]=len(db.list_swap_requests(yy,mm,None)); row["Backup swaps"]=len(db.list_backup_swap_requests(yy,mm,None)); row["Completed covers"]=sum(1 for r in db.list_backups(yy,mm) if r.get("completed_at"))
            monthly.append(row)
        monthly_df=pd.DataFrame(monthly)
        st.markdown(f"### {tr('research_monthly_table')}"); st.dataframe(monthly_df,use_container_width=True,hide_index=True)

        gm_rows=db.research_scheduler_dashboard()
        if gm_rows:
            st.markdown(f"### {tr('research_scheduler_status')}")
            st.dataframe(pd.DataFrame(gm_rows),use_container_width=True,hide_index=True)
        gen_rows=db.research_generation_dashboard()
        if gen_rows:
            st.markdown(f"### {tr('research_generation_telemetry')}")
            st.dataframe(pd.DataFrame(gen_rows),use_container_width=True,hide_index=True)

        if active_user=="ŠR":
            st.caption(tr("research_researcher_only"))
            raw=db.research_survey_deidentified()
            if raw:
                rows=[]
                for r in raw:
                    flat={"code":r.get("response_code"),"phase":r.get("phase"),"year":r.get("cycle_year"),"month":r.get("cycle_month"),"submitted_at":r.get("submitted_at")}
                    flat.update(r.get("answers") or {})
                    for k,v in (r.get("free_text") or {}).items(): flat[f"comment_{k}"]=v
                    rows.append(flat)
                raw_df=pd.DataFrame(rows)
                st.markdown(f"### {tr('research_deidentified')}"); st.dataframe(raw_df,use_container_width=True,hide_index=True)
                st.download_button(tr("research_download_surveys"),raw_df.to_csv(index=False).encode("utf-8-sig"),file_name="research_surveys_deidentified.csv",mime="text/csv")
            st.download_button(tr("research_download_monthly"),monthly_df.to_csv(index=False).encode("utf-8-sig"),file_name="research_monthly_metrics.csv",mime="text/csv")
            comments=db.research_comments_v2510()
            if comments:
                st.markdown(f"### {tr('research_comments')}"); st.dataframe(pd.DataFrame(comments),use_container_width=True,hide_index=True)
            obs=db.research_observer_dashboard()
            if obs:
                st.markdown(f"### {tr('research_observer_tab')}"); st.dataframe(pd.DataFrame(obs),use_container_width=True,hide_index=True)
pos+=1

# --- V2.5.161: dedicated RESEARCH tab, Rapolas/ŠR only ---
if is_researcher_account:
    with tabs[pos]:
        st.subheader("RESEARCH")
        st.success(
            "AUDIT ONLY — šis langas yra izoliuotas nuo production grafiko. "
            "RANKA / OPTO Excel įkėlimai ir čia sugeneruotas RAPA palyginimas nekeičia SYSTEM, ACTUAL, pageidavimų, fairness istorijos ar publikavimo būsenos."
        )
        st.caption(
            "Čia kelk žmogaus sudarytą Excel (RANKA) ir OPTO Excel, o RAPA sugeneruok iš tos pačios extension + pageidavimų įvesties. "
            "Rezultatus galima audituoti ekrane ir atsisiųsti vienu palyginimo Excel failu."
        )
        render_opto_research_workbench()
        with st.expander("RAPA bandomieji paleidimai · dabartinė grupė", expanded=False):
            st.caption(
                "Papildomas dabartinės grupės izoliuotų RAPA paleidimų workbench. "
                "Jis taip pat nerašo į production SYSTEM / ACTUAL grafiką."
            )
            render_research_shadow_generator()
    pos+=1

# --- Proof ---
if advanced_mode:
    with tabs[pos]:
        st.subheader(tr("proof_title")); st.write(tr("proof_intro")); currentp=db.load_schedule(year,month,"current"); basep=db.load_schedule(year,month,"baseline")
        if not currentp:
            st.info(tr("not_published"))
        else:
            current=refresh_result_payload(currentp,year,month); base=refresh_result_payload(basep or currentp,year,month,use_actual_backups=False); pref=db.get_preference(year,month,active_user) or {}; slots=make_slots(year,month)
            def worked_days(res): return {s.day for s in slots if res.assignments.get(s.idx)==active_user}
            cdays=worked_days(current)
            hard=set(pref.get("unavailable",set()))
            hard_am=set(pref.get("unavailable_am",set()))
            hard_pm=set(pref.get("unavailable_pm",set()))
            soft=set(pref.get("soft_free",set())); soft_am=set(pref.get("soft_free_am",set())); soft_pm=set(pref.get("soft_free_pm",set()))
            wanted=set(pref.get("preferred",set())); wanted_am=set(pref.get("preferred_am",set())); wanted_pm=set(pref.get("preferred_pm",set()))

            current_person_slots=[s for s in slots if current.assignments.get(s.idx)==active_user]
            hard_bad=[]
            for d in sorted(hard):
                if any(s.day==d for s in current_person_slots):
                    hard_bad.append(f"{d} · {tr('full_day')}")
            for d in sorted(hard_am):
                if any(s.day==d and blocks_overlap(s.block,"AM") for s in current_person_slots):
                    hard_bad.append(f"{d} · {tr('morning')}")
            for d in sorted(hard_pm):
                if any(s.day==d and blocks_overlap(s.block,"PM") for s in current_person_slots):
                    hard_bad.append(f"{d} · {tr('afternoon')}")
            hard_total=len(hard)+len(hard_am)+len(hard_pm)
            def req_label(day,block):
                label=tr("full_day") if block=="FULL" else tr("morning") if block=="AM" else tr("afternoon")
                return f"{day} · {label}"
            def has_overlap(day,block):
                if block=="FULL": return any(s.day==day for s in current_person_slots)
                return any(s.day==day and blocks_overlap(s.block,block) for s in current_person_slots)
            soft_requests=[(d,"FULL") for d in soft]+[(d,"AM") for d in soft_am]+[(d,"PM") for d in soft_pm]
            pref_requests=[(d,"FULL") for d in wanted]+[(d,"AM") for d in wanted_am]+[(d,"PM") for d in wanted_pm]
            soft_miss=[req_label(d,b) for d,b in sorted(soft_requests) if has_overlap(d,b)]
            pref_miss=[req_label(d,b) for d,b in sorted(pref_requests) if not has_overlap(d,b)]
            bd=base.stats["people"].get(active_user,{}); cd=current.stats["people"].get(active_user,{})
            fair=base.stats["global"].get("fairness_score"); rr=balance_ratio(cd.get("preference_score"),fair)

            # Top visual summary.
            a,b,c,d=st.columns(4)
            a.metric(tr("hard_errors"),len(hard_bad))
            b.metric(tr("workload_ok"),f"{cd.get('workload')} / {cd.get('target')}")
            c.metric(tr("preference_score"),tr("not_applicable") if cd.get("preference_score") is None else f"{cd.get('preference_score')}%")
            d.metric(tr("balance_ratio"),tr("not_applicable") if rr is None else f"{rr:.2f}")

            comps=cd.get("preference_components",{})
            # Account settings (6 h/12 h, spread etc.) are mode inputs, not wishes.
            # Only actual monthly/recurring wish misses drive request warnings/statistics.
            soft_problem=bool(soft_miss or pref_miss)
            if hard_bad:
                st.error(tr("proof_hard_issue"))
            elif soft_problem:
                st.warning(tr("proof_soft_issues"))
            else:
                st.success(tr("proof_all_good"))

            if advanced_mode:
                rows=[]
                hard_score=100.0 if not hard_bad else max(0.0,100.0*(hard_total-len(hard_bad))/max(1,hard_total))
                rows.append({tr("criterion"):tr("hard_ok"),tr("result"):component_status(hard_score),tr("score"):f"{hard_score:.0f}%",tr("explanation"):("—" if not hard_bad else f"{tr('missed_dates')}: {', '.join(map(str,hard_bad))}")})
                if soft_requests:
                    score=round(100*(len(soft_requests)-len(soft_miss))/len(soft_requests),1)
                    rows.append({tr("criterion"):tr("soft_off_ok"),tr("result"):component_status(score),tr("score"):f"{score}%",tr("explanation"):("—" if not soft_miss else f"{tr('missed_dates')}: {', '.join(map(str,soft_miss))}")})
                if pref_requests:
                    score=round(100*(len(pref_requests)-len(pref_miss))/len(pref_requests),1)
                    rows.append({tr("criterion"):tr("preferred_ok"),tr("result"):component_status(score),tr("score"):f"{score}%",tr("explanation"):("—" if not pref_miss else f"{tr('missed_dates')}: {', '.join(map(str,pref_miss))}")})
                wl_credit=float(cd.get("workload_credit",cd.get("workload",0)) or 0)
                wl_target=float(cd.get("target",0) or 0)
                wl_ok=abs(wl_credit-wl_target)<1e-9
                rows.append({tr("criterion"):tr("workload_ok"),tr("result"):tr("matches") if wl_ok else tr("mismatch"),tr("score"):"100%" if wl_ok else "0%",tr("explanation"):(f"{wl_credit:g} / {wl_target:g} · pradinio grafiko krūvio kreditas užfiksuotas paskelbimo metu" if lang=="LT" else f"{wl_credit:g} / {wl_target:g} · SYSTEM workload credit frozen at publication")})
                st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

                # Native progress visuals show actual wishes only. Account settings
                # are scheduling-mode guidance and intentionally absent from wish stats.
                active_progress=[]
                if soft_requests: active_progress.append((tr("soft_off_ok"),100*(len(soft_requests)-len(soft_miss))/len(soft_requests)))
                if pref_requests: active_progress.append((tr("preferred_ok"),100*(len(pref_requests)-len(pref_miss))/len(pref_requests)))
                if active_progress:
                    st.divider()
                    for label,val in active_progress:
                        st.write(f"{label}: {val:.1f}%")
                        st.progress(max(0.0,min(1.0,val/100.0)))

                st.divider(); x,y,z=st.columns(3)
                x.metric(tr("baseline"),tr("not_applicable") if bd.get("preference_score") is None else f"{bd.get('preference_score')}%")
                y.metric(tr("current"),tr("not_applicable") if cd.get("preference_score") is None else f"{cd.get('preference_score')}%")
                z.metric(tr("balance_ratio"),tr("not_applicable") if rr is None else f"{rr:.2f}")
                if hard_bad or soft_problem: st.info(tr("swap_suggestion"))
            else:
                if hard_bad or soft_problem:
                    st.info(tr("swap_suggestion"))
                st.caption(
                    ("Detali kriterijų lentelė ir komponentų progresas rodomi Išplėstiniame režime."
                     if lang=="LT" else
                     "Detailed criterion tables and component progress are shown in Advanced mode.")
                )
    pos+=1

def explanatory_manual_only(content: str) -> str:
    """Hide obsolete version-locked operational sections.

    Operational rules are rendered live from the active Rule Profile above.
    The manual below is explanatory context only and must not duplicate mutable
    engine parameters.
    """
    locked_prefixes=(
        "## Dubliai — V2.5.2 LOCKED",
        "## Savaitgalio dublių savitarna — V2.5.3 LOCKED",
        "## LOCKED V2.5.28",
        "## LOCKED V2.5.29",
        "## LOCKED V2.5.32",
    )
    lines=str(content or "").splitlines()
    out=[]
    skipping=False
    for line in lines:
        if any(line.startswith(p) for p in locked_prefixes):
            skipping=True
            continue
        if skipping and line.startswith("## "):
            skipping=False
        if not skipping:
            out.append(line)
    return "\n".join(out).strip()



# --- OPTO/RAPA extension research moved into Tyrimas in V2.5.144 ---

# --- Rules ---
with tabs[pos]:
    st.subheader(tr("rules_title"))
    st.info(
        ("V2.5.158 — NAUJAUSIAS SP / ADMIN SPALIO MODELIS. Onko/TBL yra VIENA 08:00–17:00 FULL pamaina (1,5 pamainos vieneto), ne AM+PM. "
         "2026 m. spalį Onko skiriamas tik rugsėjį Onko nedirbusiems rezidentams; vienam Onko rezidentui skiriamos 2 Onko dienos. "
         "SPS UG 1035 vakaro pamaina grąžinta. MUST: CENTRO RO 4+4, SPS RO rytas+vakaras, Centro UG 120 rytas, Onko/TBL, Skopijos ir esami budėjimai. "
         "II prioritetas: Vaikų UG rytas, ADC rytai, Centro UG 120 vakaras. III / paskutinis prioritetas: ADC vakarai ir SPS UG rytas+vakaras. "
         "Centro UG eilutės grafike rodomos greta; rezidentų raidžių spalva suvienodinta; BLOCK nerodomas. Naktinių SPS RO budėjimų eilutė rodoma kaip vizualus scaffold, bet naktinių datų/valandų engine nekuria, kol jos nepatvirtintos."
         if lang=="LT" else
         "V2.5.158 — LATEST SP / ADMIN OCTOBER MODEL. Onko/TBL is ONE 08:00–17:00 FULL shift worth 1.5 standard shift-units, not AM+PM. "
         "In October 2026 Onko is assigned only to residents who did not work Onko in September; an Onko resident receives 2 Onko days. "
         "SPS UG 1035 PM is restored. MUST: CENTRO RO 4+4, SPS RO AM+PM, Centro UG 120 AM, Onko/TBL, Endoscopy and existing duties. "
         "Second tier: Pediatric US AM, ADC AM, Centro UG 120 PM. Last tier: ADC PM and SPS UG AM+PM. "
         "Centro UG rows are adjacent; resident text color is unified; BLOCK is hidden. A night SPS RO duty row is shown as a visual scaffold, but the engine does not invent night dates/hours until they are confirmed.")
    )

    if lang=="LT":
        st.success(
            "V2.5.65 — PIRMA DARBO DIENOS, TADA DARBO VIETOS. Pirmiausia parenkama, kuriomis dienomis ir kuriuo metu kiekvienas rezidentas dirba, kuo labiau saugant „Negaliu dirbti“, poilsį ir kitus pageidavimus. Tik tada parenkamos konkrečios darbo vietos. Kai tam tikro posto per mėnesį yra nedaug, bet jų užtenka bent po vieną kiekvienam, sistema pirmiausia stengiasi kiekvienam duoti bent vieną kartą, o tik tada skiria antrą. Todėl, pavyzdžiui, 22 Onko / Centro UG / Vaikų UG vietos 16 rezidentų normaliai turi pasiskirstyti po 1–2, o ne 0–2. SPS UG ir nesavanoriškas SPS RO / šeštadienių / sekmadienių krūvis laikomas kuo lygesnis; aiškiai savanoriškai „Pageidauju dirbti“ pasirinkti savaitgaliai gali RAW skaičių padidinti. Konkreti SPS data nėra užrakinama žmogui, jei tą patį bendrą kiekį galima išlaikyti kitu paskyrimu ir geriau įvykdyti jo pageidavimą. Patvirtintos atostogos yra privalomos nedarbo dienos ir proporcingai sumažina to žmogaus mėnesio darbo tikslą. "
            "V2.5.74 — VISŲ POSTŲ STRUKTŪRINIS WATER-FILL. Prieš atiduodama SYSTEM grafiką sistema pirmiausia užrakina darbo datas/blokus, tada VISUS ne-Onko postų labelius sprendžia kartu. SPS UG ir kiekvienas įprastas ne-Onko postas pirmiausia bandomi 0–1 koridoriuje; savaitgaliams ir savaitgalio SPS RO 0–1 taikomas likusiam nesavanoriškam krūviui, o aiškiai savanoriškos „Pageidauju dirbti“ pamainos gali RAW spread padidinti. Platesnis 0–2 ar 0–3 koridorius leidžiamas tik po matematinio įrodymo, kad siauresnis koridorius neįmanomas. Timeout nėra įrodymas. Tokiu būdu 1-vs-3 negali likti, jei validus dviejų ar kelių rezidentų postų perkeitimas gali padaryti 2-vs-2 nepakeičiant darbo datos/bloko. "
            "Generatorius lieka konservatyvus: ~40 val./7 d. tikslas, ≤48 val./7 d., ≤6 darbo dienos/7 d. ir recovery po dvigubų. "
            "Po publikavimo bilateral voluntary swapas tikrina ABSOLUTE / operacinius ir darbo-laiko blokatorius, o naują 12 h double, >40/>48 h krūvį, "
            "6 dienų seką, post-double recovery ar savo RESIDENT HARD override parodo pasekmių lentelėje ir prašo paveikto rezidento ACK. "
            "ACK niekada neapeina >12 h/d., <11 h poilsio, >6 darbo dienų/7 d., >60 h/7 d., pateisinamo neatvykimo, overlap/coverage ar privalomo poilsio po 24 h budėjimo."
        )
        st.markdown("### Kaip derinama darbo vietų lygybė ir asmeniniai pageidavimai")
        st.info(
            "Sistema saugo ne konkretaus žmogaus SPS datą, o bendrą mėnesio paskirstymo lygumą. "
            "Pavyzdžiui, jei rezidentas nori 18 d. PM laisvos, jo SPS UG pamaina gali būti perkelta kitam tinkamam rezidentui arba jam parinkta kita SPS UG data, "
            "jeigu galutinis kiekis tarp žmonių išlieka kuo lygesnis ir nepažeidžiamos svarbesnės taisyklės. "
            "Todėl vien faktas, kad SPS yra aukšto prioriteto kategorija, nereiškia, kad konkretus SOFT pageidavimas turi būti atmestas."
        )
        st.markdown("### Supaprastinta vertikali prioritetų lentelė")
        st.dataframe(pd.DataFrame([
            {"Rangas":"1. TRUE ABSOLUTE HARD","Kas įeina":"Sauga, patvirtinta liga/atostogos, fizinis neįmanomumas, coverage; generatoriui ≤48 val./7 d. ir bent 1 laisva diena/7 d.","Kaip sprendžiama":"Generuojant 100%. Po publikavimo tik 48h riba gali būti savanoriškai viršyta normaliu bilateral swapu su aiškiu asmens sutikimu; kiti HARD lieka"},
            {"Rangas":"2. CRITICAL STRUCTURAL","Kas įeina":"SPS RO + šeštadieniai + sekmadieniai + penktadieniai","Kaip sprendžiama":"SPS RO ir savaitgalio našta saugoma struktūriškai; tai nepakeičia atskiros V2.5.158 postų padengimo hierarchijos, kur SPS UG AM+PM yra paskutiniame optional prioritete."},
            {"Rangas":"3. RESIDENT HARD","Kas įeina":"Negaliu dirbti — data / AM / PM / recurring","Kaip sprendžiama":"0 pažeidimų privaloma; jei tokio SYSTEM grafiko nėra, juodraštis negrąžinamas"},
            {"Rangas":"4. WEEKLY LOAD + RECOVERY","Kas įeina":"Valandos per slenkančias 7 d., kalendorinės savaitės, 12 val. dvigubų dienų seka","Kaip sprendžiama":"Taikosi į ~40 val./7 d.; lygina savaitinį krūvį. Po 1 double vengia kito double; po 2 doubles kita diena PM arba laisva, preferuojama laisva"},
            {"Rangas":"5. ŠVENČIŲ WATER-FILL","Kas įeina":"Oficialios Lietuvos švenčių dienos ir ilgalaikis pasirinkimas: noriu dirbti / neutralu / noriu ilsėtis","Kaip sprendžiama":"Pirmiausia norintys dirbti, tada neutralūs, o norintys ilsėtis — tik kai reikia. Kiekvienoje grupėje 1 visiems → 2 visiems; žiūrima ankstesnė SYSTEM švenčių našta ir mėnesio krūvis."},
            {"Rangas":"6. Kitas struktūrinis krūvis","Kas įeina":"Dvigubų pamainų bendras skaičius ir kitas consecutive/fatigue","Kaip sprendžiama":"Lyginama grupėje nebloginant aukštesnių užraktų; penktadieniai jau užrakinti aukščiau raw 0–1"},
            {"Rangas":"7. POSTŲ PADENGIMO PRIORITETAI","Kas įeina":"MUST: CENTRO RO 4+4, SPS RO AM+PM, Centro UG 120 AM, Onkologinė/TBL, Skopijos, budėjimai. II: Vaikų UG AM, ADC AM, Centro UG 120 PM. III: ADC PM, SPS UG AM+PM.","Kaip sprendžiama":"Nuo 2026-10 privalomas MUST padengimas užrakinamas. Jei dėl bendro mėnesio krūvio reikia palikti tuščių optional vietų, jos pirmiausia imamos iš III prioriteto ir tik tada iš II prioriteto."},
            {"Rangas":"8. SOFT-1","Kas įeina":"Noriu laisvos; struktūruotas recovery / vengti dublių","Kaip sprendžiama":"Horizontalus water-filling: bendras sluoksnis visiems prieš papildomus vieno žmogaus prašymus"},
            {"Rangas":"9. SOFT-2","Kas įeina":"Pageidauju dirbti konkrečią datą / AM / PM","Kaip sprendžiama":"Horizontalus water-filling"},
            {"Rangas":"10. SOFT-3","Kas įeina":"Išsklaidymas / koncentracija","Kaip sprendžiama":"Tik po aukštesnių rangų"},
            {"Rangas":"11. CURRENT-MONTH POST OPTIMAL","Kas įeina":"Likęs einamojo mėnesio ordinary-post spread","Kaip sprendžiama":"SOFT rezultato neblogina; kuo labiau grąžina šio mėnesio spread į 0–1. Jokio future catch-up nėra."},
        ]),use_container_width=True,hide_index=True)

        st.markdown("### Švenčių dienų paskirstymo protokolas")
        st.dataframe(pd.DataFrame([
            {"Žingsnis":"1. Šventės atpažinimas","Veikimas":"Sistema automatiškai atpažįsta oficialias Lietuvos DK švenčių dienas. Darbo dieną sutampanti šventė naudoja ne darbo dienos SPS RO budėjimo modelį, o įprasti outpatient postai tą dieną uždaromi / nepriskiriami; aktyvūs lieka SPS RO budėjimo AM/PM slotai."},
            {"Žingsnis":"2. Noriu dirbti","Veikimas":"Jei keli rezidentai nustatymuose pažymėjo, kad linkę dirbti per šventes, šventinės pamainos pirmiausia skiriamos jiems, bet water-fill'inamos: 1 kiekvienam prieš 2 tam pačiam."},
            {"Žingsnis":"3. Neutralu","Veikimas":"Kai norinčių neužtenka arba nėra, naudojami neutralūs. Tarp lygiaverčių kandidatų prioritetą gauna turintis mažesnę ankstesnę SYSTEM švenčių naštą ir mažesnį einamojo mėnesio krūvį."},
            {"Žingsnis":"4. Noriu ilsėtis","Veikimas":"Rezidentai, pasirinkę poilsį per šventes, naudojami tik kai aukštesnių grupių nepakanka dėl coverage / HARD. Ir jų neišvengiama našta water-fill'inama kuo lygiau."},
            {"Žingsnis":"5. Istorija","Veikimas":"SYSTEM ir ACTUAL švenčių darbo istorija saugoma auditui. Kito mėnesio generatorius jos nenaudoja kompensaciniam catch-up; kiekvienas mėnuo pradeda nuo naujo water-fill baseline."},
        ]),use_container_width=True,hide_index=True)
        st.caption("Švenčių pasirinkimas yra normalizuotas SOFT signalas, o ne teisė visada gauti arba visada išvengti šventės. Jis veikia tik aukštesnių ABSOLUTE / critical SPS / RESIDENT HARD / recovery užraktų viduje. Taip išlaikomas ir norų tenkinimas, ir grupės fairness.")

        st.markdown("### Neplanuotas neatvykimas: kritinių SPS postų gelbėjimo hierarchija")
        st.dataframe(pd.DataFrame([
            {"Situacija":"Suserga / neatvyksta žmogus iš SPS RO arba SPS UG","Veiksmas":"Kritinis postas PALIEKAMAS padengtas. Pirmiausia ieškomas tos pačios dienos ir persidengiančio bloko rezidentas, jau dirbantis žemesnės hierarchijos NEPRIVALOMAME poste.","Kas nutinka donoriniam postui":"Rezidentas perkeliamas į SPS; optional donorinis postas gali likti tuščias."},
            {"Situacija":"Yra keli tinkami donorai","Veiksmas":"Neleisti naujo RESIDENT HARD konflikto SYSTEM generavimo metu. Donoro parinkimas neturi bandyti atkurti water-fill; po operacinio pakeitimo ACTUAL spread tiesiog perskaičiuojamas ir parodomas.","Kas nutinka donoriniam postui":"Aukštesnio prioriteto mandatory coverage laimi prieš optional coverage."},
            {"Situacija":"Nėra saugaus donorinio rezidento iš optional posto","Veiksmas":"Tik tada rodomas tame bloke laisvo rezidento fallback, jei jis ABSOLUTE-safe ir nekuria overlap / mandatory coverage problemos.","Kas nutinka donoriniam postui":"Nėra priverstinio critical posto aukojimo."},
            {"Situacija":"Neatvykstama iš paprasto optional posto","Veiksmas":"Šis postas nėra aukščiau SPS RO / SPS UG; kritinio SPS rezidento iš jo traukti negalima.","Kas nutinka donoriniam postui":"Post-publication ACTUAL grafike optional gap gali būti toleruojamas; SYSTEM fairness lieka frozen."},
        ]),use_container_width=True,hide_index=True)
        st.caption("Principas: liga / force majeure pirmiausia perstato jau suplanuotą tos pačios pamainos pajėgumą į privalomą SPS. SYSTEM publikavimo baseline nekinta, bet ACTUAL postų ekspozicija ir fairness perskaičiuojami pagal realią situaciją. Istorija auditinė — jokio ateities catch-up.")

        st.markdown("### Savaitinio krūvio ir savanoriško swapo protokolas")
        st.dataframe(pd.DataFrame([
            {"Taisyklė":"GENERATORIUS — ~40 val./7 d.","Veikimas":"Savaitinis krūvis water-fill'inamas tarp rezidentų; tai planavimo tikslas.","Statusas":"STRUCTURAL TARGET"},
            {"Taisyklė":"GENERATORIUS — ≤48 val./7 d.","Veikimas":"Sistema pati nekuria >48 h rolling-7 krūvio.","Statusas":"GENERATION HARD"},
            {"Taisyklė":"VOLUNTARY SWAP — >48 val./7 d.","Veikimas":"Vien 48 h viršijimas swapo neblokuoja. Paveiktas rezidentas mato pasekmių lentelę ir turi aiškiai patvirtinti.","Statusas":"ACK / WARNING"},
            {"Taisyklė":"VOLUNTARY SWAP — ≤60 val./7 d.","Veikimas":">60 h per bet kurias 7 paeiliui einančias dienas atmetama.","Statusas":"BLOCK"},
            {"Taisyklė":"≤12 val. per darbo dieną","Veikimas":"AM+PM = 12 h galima; >12 h atmetama. Nauja 12 h diena prieš sutikimą aiškiai parodoma.","Statusas":"BLOCK + ACK ties 12 h"},
            {"Taisyklė":"≥11 val. nepertraukiamo paros poilsio","Veikimas":"Jei tarp darbo dienų / pamainų po swapo lieka <11 h, swapas atmetamas.","Statusas":"BLOCK"},
            {"Taisyklė":"BUDEJIMO DIENA = TIK BUDEJIMAS","Veikimas":"Jei rezidentas tą kalendorinę dieną turi bet kokį RAPA budėjimą (SPS RO dieninį ar naktinį), jokios kitos AM / PM / FULL / Onko pamainos tą dieną negali būti.","Statusas":"VERY HARD / BLOCK"},
            {"Taisyklė":"PO NAKTINIO BUDEJIMO KITA DIENA = LAISVA","Veikimas":"Visa sekanti kalendorinė diena privalomai laisva TIK po SPS RO NAKTINIO budėjimo. Po dieninio / savaitgalio 08:00–20:00 budėjimo automatinės kitos laisvos dienos nėra. Taisyklė galioja ir per mėnesio ribą; jos negalima apeiti swap ACK.","Statusas":"VERY HARD / BLOCK"},
            {"Taisyklė":"VISI SPS RO BUDEJIMAI = WATER-FILL","Veikimas":"Visi SPS RO budėjimai skaičiuojami viename atskirame budėjimų skaitiklyje: dieniniai savaitgalio / šventiniai ir naktiniai. Niekas negauna antro budėjimo, kol kitas tinkamas rezidentas dar neturi pirmo. Leidžiamas tik matematiškai būtinas 0–1 skirtumas; jei HARD apribojimai to neleidžia, grafikas nestatomas, o ne tyliai iškreipiamas.","Statusas":"HARD WATER-FILL"},
            {"Taisyklė":"Po 6 darbo dienų — poilsis","Veikimas":"Negalima >6 darbo dienų per 7 paeiliui einančias dienas. 6 dienų seka leidžiama ir rodoma kaip perspėjimas.","Statusas":"7-a diena = BLOCK"},
            {"Taisyklė":"Recovery po doubles","Veikimas":"Generatorius po dviejų doubles kitą dieną riboja. Savanoriškame swape tai tampa ACK perspėjimu, jei 11 h / 12 h / 6 d. / 60 h ribos išlaikytos.","Statusas":"GENERATION HARD → SWAP ACK"},
            {"Taisyklė":"RESIDENT HARD per savanorišką swapą","Veikimas":"Jei rezidentas pats priima darbą per savo ankstesnį „Negaliu dirbti“, sistema rodo override ir prašo jo ACK; ORIGINAL pageidavimas istorijoje lieka.","Statusas":"SWAP ACK"},
        ]),use_container_width=True,hide_index=True)

        st.markdown("### Kas swapą BLOKUOJA ir kas tik PERSPĖJA")
        st.dataframe(pd.DataFrame([
            {"Tipas":"BLOKUOJA","Pavyzdžiai":"ABSOLUTE HARD / pateisinamas neatvykimas; overlap; >12 h/d.; <11 h poilsio; >6 darbo dienų/7 d.; >60 h/7 d.; post-NIGHT full-day rest; neįmanomas backup/coverage; mėnesio target ≠ tikslus; Onko 1/3/5","ACK":"Negali apeiti"},
            {"Tipas":"PERSPĖJA + ACK","Pavyzdžiai":"Nauja 12 h double; >40 ar >48 h/7 d.; 6 darbo dienų seka; consecutive doubles; darbas po 2 doubles; consecutive Onko; savo RESIDENT HARD override","ACK":"Kiekvienas paveiktas rezidentas patvirtina atskirai"},
            {"Tipas":"NEBLOKUOJA VOLUNTARY SWAP","Pavyzdžiai":"SYSTEM post spread, weekend/double fairness, SOFT satisfaction","ACK":"SYSTEM baseline frozen; ACTUAL perskaičiuojamas"},
        ]),use_container_width=True,hide_index=True)
        st.caption("ACK nėra teisinė išimtis: jis tik patvirtina rezidentui parodytas pasekmes. Darbo laiko režimo ir apskaitinio laikotarpio teisinį taikymą galutinai nustato darbdavys.")
        st.info("V2.5.66 — vienas rezidentas gali turėti kelis laukiančius apsikeitimus, jei jie liečia skirtingas pamainas. Ta pati konkreti pamaina vienu metu gali būti tik viename aktyviame pasiūlyme. Ta pati taisyklė taikoma dublių apsikeitimams. Savo dar nepriimtą pasiūlymą galima atšaukti. Jau pritaikytas ar atmestas pasiūlymas pamainos neberezervuoja.")
        st.info("V2.5.67 — mėnesio darbo krūvio targetas yra ABSOLIUTUS: 28 reiškia tiksliai 28.0, 26 reiškia tiksliai 26.0. Onko diena = 1.5 pamainos, todėl Onko skiriamas poromis (0, 2, 4...) ir mėnesio skirtumas tarp rezidentų negali viršyti 2. Kas šį mėnesį gauna mažiau Onko, turi catch-up prioritetą kitais mėnesiais pagal publikuotą istoriją.")
        st.info("V2.5.68 — Onko RO atsigavimo taisyklė yra ABSOLIUTI: tas pats rezidentas negali būti Onko RO dvi kalendorines dienas iš eilės. Jei dirbo Onko paskutinę ankstesnio mėnesio dieną, naujo mėnesio 1 d. Onko jam taip pat blokuojamas. Taisyklė negali būti paaukota dėl postų lygybės ar SOFT pageidavimų.")
        st.info("V2.5.165 — BUDEJIMAI: (1) VISI SPS RO budėjimai water-fill'inami viename HARD skaitiklyje — niekas negauna antro, kol kitas tinkamas rezidentas neturi pirmo; (2) bet kokio budėjimo dieną negali būti jokios kitos RAPA pamainos; (3) kita kalendorinė diena privalomai LAISVA TIK po NAKTINIO budėjimo; po dieninio / savaitgalio budėjimo automatinės laisvos dienos nėra; (4) 2026-10-30 SPS RO naktinis budėjimas HARD priskirtas GE — Gertui Ernestui, todėl 2026-10-31 jam privalomai laisva.")
        st.info("V2.5.73 — ONKO PORŲ ABSOLIUTI TAISYKLĖ: kiekvieno rezidento Onko skaičius SYSTEM ir ACTUAL grafike turi būti tik 0, 2, 4, 6... Kadangi viena Onko diena = 1.5 pamainos, nelyginis 1/3/5 sukurtų 0.5 krūvio trupmeną ir yra BLOKUOJAMAS net savanoriškame swape. Jei aktyvių mėnesio Onko dienų skaičius nelyginis, viena Onko diena paliekama neužpildyta, kad bendras užpildytų Onko skaičius būtų lyginis. Consecutive Onko po publikavimo gali likti tik ACK išimtis; parity ir tikslus mėnesio targetas — niekada.")
        st.info("V2.5.74 — VISŲ POSTŲ STRUCTURAL WATER-FILL: SYSTEM generavime, kai datos ir AM/PM blokai jau parinkti, visi ne-Onko postų labeliai sprendžiami kartu. Kiekvienam postui pirmiausia bandomas floor/ceil pasiskirstymas raw spread 0–1. Pvz., 38 Mamografijos vietos / 16 rezidentų → 10 rezidentų po 2 ir 6 rezidentai po 3; 1-vs-3 negali likti, jei egzistuoja validus postų perkeitimas ar kelių žmonių ciklas. Po publikavimo savanoriški ACTUAL swapai gali išbalansuoti postų ekspoziciją — fairness / UG / Mamografijos kiekiai swapo NEBLOKUOJA; SYSTEM fairness lieka užšaldytas.")
        st.info("V2.5.164 — PENKTADIENIŲ FAIRNESS YRA STRUKTŪRINĖ: rezidentas gali prašyti vieno ar visų penktadienių laisvų, tačiau SYSTEM negali dėl to neproporcingai perkelti penktadienio darbo kitiems. Pirmiausia apskaičiuojamas kiekvieno rezidento pagal HARD tinkamumą sąžiningas penktadienių koridorius; tada jo viduje maksimaliai pildomi konkretūs pageidavimai. Taigi prašymas nėra ignoruojamas — sistema suteikia maksimalų laisvų penktadienių skaičių, kurį leidžia visos grupės balansas. Po publikavimo abipusis ACTUAL swapas gali balansą pakeisti; SYSTEM baseline lieka užšaldytas.")

        st.markdown("### Emergency — jau įvykusio pakeitimo registravimas")
        st.dataframe(pd.DataFrame([
            {"Situacija":"Skubiai realybėje sukeisti du rezidentai / jų pamainos","Ką darome":"Seniūnė arba vienas iš dalyvavusių rezidentų Apsikeitimai → Emergency lange įrašo abi buvusias pamainas.","Kas pasikeičia":"ACTUAL grafikas ir pakeitimų žurnalas."},
            {"Situacija":"Pakeitimą įrašo seniūnė","Ką darome":"Abiem dalyvavusiems rezidentams žurnale rodoma 🔔, kol jie pažymi, kad įrašą matė / jis teisingas.","Kas pasikeičia":"Tik peržiūros patvirtinimas; grafikas jau rodo faktą."},
            {"Situacija":"Pakeitimą įrašo pats rezidentas","Ką darome":"Jo peržiūra pažymima iš karto; kitam dalyviui paliekamas 🔔 patvirtinimas.","Kas pasikeičia":"ACTUAL + audito istorija."},
            {"Situacija":"Mėnuo uždaromas / eksportuojamas galutinis grafikas","Ką darome":"Naudojamas ACTUAL grafikas su visais įrašytais emergency pakeitimais.","Kas pasikeičia":"Galutinė faktinė istorija tiksli."},
            {"Situacija":"Fairness / mokomojo paskirstymo vertinimas","Ką darome":"Emergency įrašas jo neperskaičiuoja.","Kas pasikeičia":"Nieko: SYSTEM publikavimo bazė, postų istorija ir ateities kompensacijos lieka frozen."},
        ]),use_container_width=True,hide_index=True)
        st.caption("Jei apsikeitimas dar tik planuojamas, naudokite įprastą savanoriško apsikeitimo srautą. Emergency poskyris skirtas realiai jau įvykusiam / tą pačią dieną aiškiai sutartam faktui užregistruoti, kad galutinis ACTUAL grafikas atitiktų realybę.")
        st.info("Teisinis orientyras pagal VDI: bent 11 val. nepertraukiamo paros poilsio, bent 35 val. nepertraukiamo poilsio per 7 paeiliui einančias dienas ir ne daugiau kaip 6 darbo dienos per 7. 48 val. yra svarbus vidutinio darbo laiko slenkstis; atskirais režimais taikomi papildomi 52/60 val. limitai. Todėl >48 visada rodoma su tiksliu skaičiumi ir aiškiu perspėjimu, o tikros absoliučios ribos lieka blokuojamos.")

        st.markdown("### Savanoriško dublio perėmimo išimtis")
        st.dataframe(pd.DataFrame([
            {"Situacija":"Po dublio būtų 12 val. darbo diena","Ką mato žmogus":"Dabar X val. → po dublio 12 val.","Veiksmas":"Perspėjimas. Galima ATŠAUKTI arba PATVIRTINTI VIS TIEK, jei kitos absoliučios ribos išlaikytos."},
            {"Situacija":"Po dublio 7 dienų krūvis viršija ~40 / 48 val.","Ką mato žmogus":"Tikslus skaičius ir konkrečios 7 dienos, pvz. 54 val. (12–18 d.)","Veiksmas":"Savanoriškas ACK. 48 val. nėra tyliai ignoruojama — žmogus aiškiai mato pasekmę."},
            {"Situacija":"Rezidentas pats perima dublį per savo RESIDENT HARD laiką","Ką mato žmogus":"Kuri data / blokas buvo pažymėtas „Negaliu dirbti“","Veiksmas":"Galima tik aiškiai savanoriškai patvirtinus; ORIGINAL pageidavimas istorijoje lieka."},
            {"Situacija":"Po dublio būtų >12 val./d., aktyvios 7 d. ribos viršijimas, <11 val. paros poilsio arba >6 darbo dienos/7 d.","Ką mato žmogus":"Tikslus apskaičiuotas pažeidimas ir riba skliausteliuose","Veiksmas":"BLOKUOJAMA — šių ribų manual ACK neapeina."},
            {"Situacija":"Pateisinamas neatvykimas / privalomas po-naktinio budėjimo poilsis / persidengianti pamaina","Ką mato žmogus":"Konkreti priežastis","Veiksmas":"BLOKUOJAMA."},
        ]),use_container_width=True,hide_index=True)
        st.caption("Principas paprastas: jei dublis tik pablogina planavimo komfortą, žmogus gali sąmoningai sutikti. Jei atsiranda tikras saugos / teisinis blokatorius, sistema jo nevadina „override“ ir neleidžia patvirtinti.")

        st.markdown("### Kaip lyginamas darbas skirtingose pozicijose")
        st.dataframe(pd.DataFrame([
            {"Grupė":"KRITINĖ","Pozicijos":"SPS RO, SPS UG, šeštadieniai, sekmadieniai","Taisyklė":"Kiekviena kategorija balansuojama atskirai. Šeštadieniai ir sekmadieniai turi atskirą water-fill 0–1, nes jų atlygio / naštos pobūdis skiriasi."},
            {"Grupė":"ONKO RO — SPECIALI HARD","Pozicijos":"Onko RO 08:00–17:00","Taisyklė":"1 diena = 1.5 pamainos, todėl SYSTEM skiriama lyginėmis poromis (0/2/4...), mėnesio skirtumas ≤2. Tas pats rezidentas NEGALI būti Onko dvi kalendorines dienas iš eilės, įskaitant mėnesio ribą."},
            {"Grupė":"KITI POSTAI","Pozicijos":"CENTRO RO, Centro UG, ADC 144, ADC 145, Vaikų UG, Mamografijos","Taisyklė":"Jei mėnesio vietų pakanka, pirmiausia kiekvienas turi gauti bent vieną galimybę. Toliau paskirstymas lyginamas kuo labiau; didesnis skirtumas leidžiamas tik kai lygesnis variantas neįmanomas arba būtinas svarbesnei taisyklei."},
            {"Grupė":"FUTURE CATCH-UP","Pozicijos":"Kiekvienas postas × rezidentas","Taisyklė":"Jei šį mėnesį žmogus konkrečioje darbo vietoje gavo mažiau nei kiti, kitą mėnesį sistema jam teikia pirmenybę pasivyti. Jei gavo daugiau, papildomas paskyrimas pirmiau siūlomas kitiems."},
            {"Grupė":"TEMPORAL SPACING","Pozicijos":"Ypač savaitgaliai, taip pat SPS RO/SPS UG","Taisyklė":"Vienodi skaičiai dar nereiškia vienodo nuovargio: tarp lygiaverčių variantų vengiami 2–3 savaitgaliai iš eilės ir bereikalingas SPS suspaudimas."},
        ]),use_container_width=True,hide_index=True)

        st.markdown("### Kokie SOFT priimami")
        st.dataframe(pd.DataFrame([
            {"Būsena":"PRIIMAMA","Pavyzdys":"Noriu laisvos konkrečią datą / AM / PM","Kodėl":"Aiškus asmeninio laiko poreikis; SOFT-1"},
            {"Būsena":"PRIIMAMA","Pavyzdys":"Pageidauju dirbti konkrečią datą / AM / PM","Kodėl":"Aiškus teigiamas darbo pageidavimas; SOFT-2"},
            {"Būsena":"PRIIMAMA","Pavyzdys":"Vengti dublių / labiau išsklaidytas ar koncentruotas mėnuo","Kodėl":"Standartizuotas recovery / schedule-shape signalas"},
            {"Būsena":"NEPRIIMAMA kaip SOFT","Pavyzdys":"Nedėk manęs į Mamografiją / tik SPS RO / kuo daugiau Centro RO","Kodėl":"Pageidavimų sistema nėra darbo vietų pasirinkimo meniu; visi turi gauti kuo lygesnes mokymosi galimybes."},
            {"Būsena":"NEPRIIMAMA kaip bendras SOFT","Pavyzdys":"Nenoriu savaitgalių / noriu mažiau darbo dienų","Kodėl":"Gali permesti kritinę naštą kitiems. Jei reikia konkrečios datos — rinktis ją; jei realiai negalite — RESIDENT HARD"},
        ]),use_container_width=True,hide_index=True)
        st.caption("Principas: sistema tenkina realius poreikius, bet kartu saugo lygybę visai grupei. Vien tai, kad žmogus pateikė daugiau pageidavimų, nesuteikia jam didesnės galios už kitus.")
    else:
        st.success(
            "V2.5.62 — EMERGENCY ACTUAL SWAP LOG + VOLUNTARY BACKUP OVERRIDE. V2.5.58 engine rules are preserved; a dedicated Senior guide adds a five-minute concrete-statement verification audit, red flags and end-to-end monthly workflow. "
            "Generation remains conservative (~40h target, ≤48h/7d, ≤6 workdays/7d and post-double recovery). "
            "After publication, bilateral voluntary swaps are blocked only by ABSOLUTE/operational and labour-time guardrails; new 12h doubles, >40/>48h load, six-day streaks, post-double recovery patterns and self-overridden Resident-HARD requests are shown in a consequence table and require acknowledgement."
        )
        st.markdown("### Unplanned absence: critical SPS rescue hierarchy")
        st.dataframe(pd.DataFrame([
            {"Situation":"Resident absent from SPS RO or SPS UG","Action":"Keep the critical post covered. First pull a resident already working the same day / overlapping block in a lower-priority NON-MANDATORY post.","Donor post":"Move the resident to SPS; the optional source post may remain empty."},
            {"Situation":"Several safe donors exist","Action":"Reject new Resident-HARD conflicts unless a later ACTUAL voluntary action explicitly changes the resident's own request. Do not force a donor choice to restore water-fill; after the operational move, ACTUAL exposure/fairness is simply recalculated and reported.","Donor post":"Mandatory critical coverage outranks optional coverage."},
            {"Situation":"No safe optional-post donor exists","Action":"Only then use a resident free in that block as fallback if ABSOLUTE-safe and overlap/coverage-valid.","Donor post":"Never sacrifice another critical SPS post."},
        ]),use_container_width=True,hide_index=True)

        st.markdown("### Simplified vertical-priority table")
        st.dataframe(pd.DataFrame([
            {"Rank":"1. TRUE ABSOLUTE HARD","Includes":"Safety/rest, approved absence, physical impossibility, coverage; generation <=48h/rolling7 and >=1 free day/7d","Method":"100% during generation. Post-publication voluntary swaps use consequence + ACK warnings, but ABSOLUTE/operational and labour-time blockers remain hard"},
            {"Rank":"2. CRITICAL STRUCTURAL","Includes":"SPS RO + Saturday + Sunday + Fridays","Method":"Structural SPS RO/weekend load fairness; separate V2.5.158 service-coverage tiers govern which optional stations may be left unfilled"},
            {"Rank":"3. RESIDENT HARD","Includes":"Unavailable date / AM / PM / recurring","Method":"Zero violations are mandatory in SYSTEM generation; if impossible, no draft is returned"},
            {"Rank":"4. WEEKLY LOAD + RECOVERY","Includes":"Rolling-7 hours, calendar-week load, double-shift sequences","Method":"Aim ~40h/7d; equalize weekly load; after 2 consecutive doubles next day PM-only or off, preferring off"},
            {"Rank":"5. OTHER STRUCTURAL","Includes":"Total doubles and other consecutive/fatigue","Method":"Balance without worsening higher locks; Fridays are already structurally locked at raw 0–1"},
            {"Rank":"6. OTHER POST CORE","Includes":"CENTRO RO, Centro UG, ADC 144/145, Vaikų UG ir nuo 2026-10 Onkologinė/TBL; Mamografija nuo 2026-10 uždaryta šiai laidai","Method":"Ordinary non-Onko posts: structural floor/ceil water-fill with target raw spread <=1 before SOFT; <=2/<=3 only after the tighter corridor is proven infeasible. Onko: exact-workload even pairs, monthly spread <=2, never consecutive calendar days."},
            {"Rank":"7–9. SOFT","Includes":"SOFT-1 time/recovery; SOFT-2 exact desired work; SOFT-3 month shape","Method":"Vertical rank + horizontal resident water-fill"},
            {"Rank":"10. CURRENT-MONTH POST OPTIMAL","Includes":"Residual ordinary-post spread in this month","Method":"Improve toward 0–1 without worsening locked SOFT; no longitudinal catch-up"},
        ]),use_container_width=True,hide_index=True)
    # RULES = ENGINE: this summary is rendered from the active engine profile,
    # never from a separate hard-coded policy copy.
    enabled_backup=[]
    if bool(rule_value("backup_sps_ro")): enabled_backup.append("SPS RO")
    if bool(rule_value("backup_sps_ug")): enabled_backup.append("SPS UG")
    if bool(rule_value("backup_centro120_am")): enabled_backup.append("Centro 120 AM")
    if bool(rule_value("backup_onko_ro")): enabled_backup.append("Onko RO")
    if bool(rule_value("backup_centro_ro_best_effort")): enabled_backup.append("CENTRO RO best-effort")

    if lang=="LT":
        st.info(
            f"AKTYVUS TAISYKLIŲ PROFILIS v{ACTIVE_RULE_PROFILE_VERSION} — TAISYKLĖS = ENGINE. "
            f"Dublio padengimas: {', '.join(enabled_backup)}. "
            f"Target formulė: darbo dienos × {float(rule_value('target_daily_hours')):g} / {float(rule_value('target_shift_hours')):g}. "
            f"Min. poilsis: {float(rule_value('min_rest_hours')):g} val.; max. darbo valandų/d.: {float(rule_value('max_hours_per_day')):g}; "
            f"max. darbo dienų per 7 d.: {min(int(rule_value('max_workdays_rolling7')), int(FATIGUE_MAX_WORKDAYS_ROLLING7))}; "
            f"GENERATION HARD max. valandų per 7 d.: {min(float(rule_value('max_hours_rolling7')), float(FATIGUE_ROLLING7_HARD_CEILING_HOURS)):g}; voluntary swap >48 = ACK, absoliutus guardrail ≤{float(SWAP_ABSOLUTE_MAX_HOURS_ROLLING7):g}; "
            f"planavimo tikslas ~{float(WEEKLY_LOAD_SOFT_TARGET_HOURS):g} val./7 d. "
            f"Mėnesio krūvio targetas: TIKSLUS HARD (leidžiamas nuokrypis 0.0). "
            f"Onko: 1.5 pamainos, tik lyginės poros (0/2/4...), mėnesio skirtumas ≤2; jokio istorinio catch-up, niekada dvi kalendorines dienas iš eilės tam pačiam rezidentui; "
            f"savaitgalio unikalumo taisyklė: {'TAIP' if rule_value('weekend_unique_required') else 'NE'}. "
            f"Struktūrinis guardrail: SPS RO / SPS UG / ŠEŠTADIENIAI / SEKMADIENIAI / PENKTADIENIAI raw 0–1; Onko ≤2 poromis; VISI kiti postai pirmiausia raw 0–1. 0–2/0–3 leidžiama tik įrodžius, kad siauresnis variantas neįmanomas. Jokio future future catch-up nėra. "
            f"Kiti pagrindiniai burden spread baseline +{int(rule_value('general_guardrail_tolerance'))}. "
            f"Pageidavimų pateikimo terminas: ankstesnio mėnesio {int(rule_value('deadline_day'))} d."
        )
    else:
        st.info(
            f"ACTIVE RULE PROFILE v{ACTIVE_RULE_PROFILE_VERSION} — RULES = ENGINE. "
            f"Backup scope: {', '.join(enabled_backup)}. "
            f"Target formula: weekdays × {float(rule_value('target_daily_hours')):g} / {float(rule_value('target_shift_hours')):g}. "
            f"Minimum rest: {float(rule_value('min_rest_hours')):g}h; max hours/day: {float(rule_value('max_hours_per_day')):g}; "
            f"max workdays/7d: {min(int(rule_value('max_workdays_rolling7')), int(FATIGUE_MAX_WORKDAYS_ROLLING7))}; "
            f"GENERATION HARD max hours/7d: {min(float(rule_value('max_hours_rolling7')), float(FATIGUE_ROLLING7_HARD_CEILING_HOURS)):g}; voluntary swap >48 = ACK, absolute guardrail ≤{float(SWAP_ABSOLUTE_MAX_HOURS_ROLLING7):g}; "
            f"planning target ~{float(WEEKLY_LOAD_SOFT_TARGET_HOURS):g}h/7d. "
            f"Monthly workload target: EXACT HARD (allowed deviation 0.0). "
            f"Onko: 1.5 shift units, even pairs only (0/2/4...), monthly spread ≤2 with no historical catch-up, never on consecutive calendar days for the same resident; "
            f"weekend uniqueness: {'YES' if rule_value('weekend_unique_required') else 'NO'}. "
            f"Structural guardrail: SPS RO / SPS UG / SATURDAYS / SUNDAYS / FRIDAYS raw 0–1; Onko ≤2 in even pairs; ALL other posts first target raw 0–1. 0–2/0–3 is allowed only after the tighter corridor is proven infeasible. No future future catch-up exists. "
            f"Other main burden spreads baseline +{int(rule_value('general_guardrail_tolerance'))}. "
            f"Preference deadline: day {int(rule_value('deadline_day'))} of the preceding month."
        )

    if lang=="LT":
        workflow_rows=[
            {"Etapas":"0. Request pre-check","Sistema":"Užšaldo ORIGINAL request ledger ir pašalina nepriimamus/gaming SOFT signalus.","Vertina":"RESIDENT HARD, tikslias SOFT datas, recovery ir month-shape; generic weekday/weekend pattern ir postų vengimas neįeina.","Principas":"Pageidavimų skaičius nesuteikia daugiau balsų."},
            {"Etapas":"1. TRUE ABSOLUTE HARD","Sistema":"Randa tik saugų/fiziškai įmanomą grafiką; generuojant taiko ≤48h/7d ir Onko recovery guard.","Vertina":"Poilsį, valandas, patvirtintą neatvykimą, coverage/overlap, tikslų mėnesio krūvį ir lygines Onko poras.","Principas":"Tikslus mėnesio targetas ir Onko 0/2/4/... yra HARD SYSTEM ir ACTUAL. Consecutive Onko gali būti tik savanoriško swapo ACK pasekmė; parity niekada neapeinama."},
            {"Etapas":"2. Kritinių darbų lygybė","Sistema":"Kartu lygina SPS RO, SPS UG, šeštadienius, sekmadienius ir penktadienius tarp rezidentų.","Vertina":"Šeštadienis ir sekmadienis yra atskiros naštos / atlygio klasės.","Principas":"Neutralus SYSTEM baseline pradeda nuo 0–1 water-fill kiekvienai klasei; po publikavimo savanoriški swapai gali ACTUAL balansą pakeisti."},
            {"Etapas":"3. RESIDENT HARD","Sistema":"Užrakina `Negaliu dirbti` kaip privalomą 0-pažeidimų SYSTEM apribojimą prieš bet kokį fairness ar SOFT optimizavimą.","Vertina":"Whole-day, AM/PM ir recurring RESIDENT HARD.","Principas":"0 pažeidimų privaloma; jei safety/coverage/target su tuo nesuderinami, SYSTEM juodraštis negrąžinamas."},
            {"Etapas":"4. Critical spacing","Sistema":"Nejudindama kritinių count spreadų, išdėsto juos laike.","Vertina":"Consecutive weekends ir SPS dienų clustering, įskaitant ankstesnio mėnesio weekend tail.","Principas":"Vengti 2–3 savaitgalių iš eilės ir bereikalingo streso suspaudimo."},
            {"Etapas":"5. WEEKLY LOAD + RECOVERY","Sistema":"Water-fill'ina savaitinį valandų krūvį ir užrakina recovery frontier.","Vertina":"Rolling-7 valandas, kalendorinių savaičių spreadą, consecutive 12h doubles.","Principas":"~40 val./7 d. tikslas; ≤48 HARD; po 2 doubles kita diena tik PM arba laisva, laisva preferinama."},
            {"Etapas":"6. ŠVENČIŲ WATER-FILL","Sistema":"Šventines pamainas skirsto einamajame mėnesyje, atsižvelgdamas į aktyvų švenčių pageidavimą ir aukštesnius užraktus.","Vertina":"Tik einamojo mėnesio holiday burden ir mėnesio krūvį.","Principas":"Kur įmanoma 1 visiems prieš 2; ankstesni mėnesiai catch-up nesukuria."},
            {"Etapas":"7. Kitas burden fairness","Sistema":"Balansuoja bendrą dublių skaičių ir kitą consecutive/fatigue.","Vertina":"Likusią struktūrinę naštą.","Principas":"Penktadieniai jau HARD water-fillinti raw 0–1 ir čia nebeatlaisvinami."},
            {"Etapas":"8. Kitų darbo vietų lygybė","Sistema":"Patikrina likusių darbo vietų paskirstymą tarp rezidentų.","Vertina":"Kiek skiriasi daugiausiai ir mažiausiai konkrečią darbo vietą gavę rezidentai.","Principas":"Siekiama 0–1; įprastai leidžiama iki 2; 3 tik jei 2 tikrai neįmanoma dėl svarbesnių taisyklių."},
            {"Etapas":"9. SOFT-1 → SOFT-2 → SOFT-3","Sistema":"Kiekvieną rangą water-fill'ina horizontaliai ir užrakina.","Vertina":"Asmeninį laiką/recovery → tikslias darbo datas → month shape.","Principas":"2,2,3,4 pirmiausia 2,2,2,2; tik tada extras."},
            {"Etapas":"10. CURRENT-MONTH POST OPTIMAL","Sistema":"SOFT neblogindama grąžina šio mėnesio ordinary post spread kuo arčiau 0–1.","Vertina":"Tik einamojo mėnesio resident × post exposure.","Principas":"Istorija stebima, bet nekuria skolos ir nekeičia kito mėnesio paskyrimų."},
            {"Etapas":"11. ACTUAL + swaps/repairs","Sistema":"Po swap/repair perskaičiuoja ACTUAL grafiką, satisfaction ir live fairness. Kritinio SPS neatvykimo atveju pirmiausia perkelia žmogų iš tos pačios pamainos optional posto.","Vertina":"Mandatory SPS coverage, realią postų ekspoziciją, ACTUAL spread, konkrečius misses ir saugą.","Principas":"SYSTEM baseline lieka užšaldytas auditui; ACTUAL fairness seka realybę. Post-publication water-fill gali būti pralaužtas, bet jokio future catch-up nesukuria."},
        ]
        if advanced_mode:
            st.markdown("### Generatorius: workflow")
            st.dataframe(pd.DataFrame(workflow_rows),use_container_width=True,hide_index=True)
            st.caption("Kai žmogus neturi SOFT, jis neįtraukiamas į SOFT max-min; tačiau jo RESIDENT HARD vis tiek pilnai dalyvauja aukštesnio prioriteto request-fairness sluoksnyje.")
        else:
            st.caption("Pilną generatoriaus workflow lentelę gali matyti Išplėstiniame režime.")
    else:
        st.info(
            "V2.5.65 — WORKDAYS FIRST, THEN WORKPLACES. The engine first chooses when each resident works while protecting Resident-HARD, recovery and personal requests. It then assigns workplaces. For ordinary 1.0-unit sparse posts such as Centro UG / pediatric US, the system gives everyone a first exposure before avoidable second exposures where mathematically feasible. Onko is now governed by the later V2.5.67–68 exact-workload pair + recovery rules, not by first-exposure 1–2 logic. SPS RO, SPS UG and weekends remain as equal as possible. A specific SPS date is not locked to one resident if the same monthly amount can be preserved with another placement that honors the resident's request. Approved vacation is an absolute no-work period and proportionally lowers that resident's monthly workload target. "
            "V2.5.63 FAIRNESS FAILSAFE. A SYSTEM draft is returned only after the solver verifies an acceptably even distribution: SPS RO, SPS UG and weekends normally differ by no more than one assignment between residents; other main workplaces normally differ by no more than two. A timeout is not treated as proof that a wider imbalance is necessary. Concrete SPS dates remain flexible, so personal requests may still be honored whenever the same overall equality can be preserved."
        )
        st.info("V2.5.66 — a resident may have several pending swaps when they involve different shifts. The same concrete shift may be in only one active future offer at a time; the same rule applies to backup swaps. A requester may cancel their own still-pending offer. Applied/rejected offers release the shift.")
        st.info("V2.5.67 — the calculated monthly workload target is ABSOLUTE: 28 means exactly 28.0 and 26 means exactly 26.0. One Onko day = 1.5 shift units, so Onko is assigned in pairs (0, 2, 4...) with a monthly resident spread no greater than 2. Residents with fewer Onko exposures receive catch-up priority in later months using published history.")
        st.info("V2.5.68 — Onko RO recovery is ABSOLUTE: the same resident may not work Onko RO on two consecutive calendar days. If the resident worked Onko on the last day of the previous published month, day 1 of the new month is also blocked for Onko. Fairness or SOFT preferences may not override this rule.")
        st.info("V2.5.73 — ONKO PAIRING ABSOLUTE: every resident's Onko count must be 0, 2, 4, 6... in both SYSTEM and ACTUAL. Because one Onko day equals 1.5 workload units, odd 1/3/5 would create a half-unit monthly workload and is blocked even in a voluntary swap. If the number of active monthly Onko days is odd, one Onko day remains unfilled so the filled total is even. Consecutive Onko may remain a post-publication ACK exception; parity and exact monthly workload never are.")
        st.info("V2.5.74 — ALL-POST STRUCTURAL WATER-FILL: in SYSTEM generation, after dates and AM/PM blocks are frozen, all non-Onko post labels are solved jointly. Every post first targets its floor/ceil distribution with raw spread 0–1. Example: 38 Mammography slots / 16 residents → ten residents receive 2 and six receive 3; a 1-vs-3 pattern cannot remain when a valid post exchange or multi-person cycle can equalize it. After publication, voluntary ACTUAL swaps may unbalance exposure — post fairness / US / Mammography counts do NOT block a mutually accepted swap; SYSTEM fairness remains frozen.")
        workflow_rows=[
            {"Stage":"0. Request pre-check","System":"Freezes ORIGINAL request ledger and removes non-whitelisted/gaming SOFT signals.","Evaluates":"Resident-HARD, exact SOFT dates, recovery/month-shape; generic weekday/weekend patterns and station avoidance are excluded.","Principle":"More raw requests do not buy more priority."},
            {"Stage":"1. TRUE ABSOLUTE HARD","System":"Finds only safe/physically feasible schedules; generation applies <=48h/7d and the Onko recovery guard.","Evaluates":"Rest, hours, approved absence, coverage/overlap, exact monthly workload and even Onko pairing.","Principle":"Exact monthly workload and Onko 0/2/4/... are HARD in SYSTEM and ACTUAL. Consecutive Onko may be accepted only as a voluntary-swap ACK consequence; parity can never be overridden."},
            {"Stage":"2. CRITICAL WATER-FILL","System":"Co-optimizes SPS RO, SPS UG and all weekend exposure.","Evaluates":"Raw max-min in the three critical categories.","Principle":"0–1; first unit for everyone before second; ordinary SOFT cannot widen to 2."},
            {"Stage":"3. RESIDENT HARD","System":"Locks every Unavailable block as a mandatory zero-violation SYSTEM constraint before fairness or SOFT optimization.","Evaluates":"Whole-day, AM/PM and recurring Resident-HARD.","Principle":"Zero violations are mandatory; if safety/coverage/target cannot coexist with them, no SYSTEM draft is returned."},
            {"Stage":"4. Critical spacing","System":"Places equivalent critical counts more evenly in time.","Evaluates":"Consecutive weekends and SPS clustering, including prior-month weekend tail.","Principle":"Avoid concentrated fatigue."},
            {"Stage":"5. WEEKLY LOAD + RECOVERY","System":"Water-fills weekly hours and locks the recovery frontier.","Evaluates":"Rolling-7 hours, calendar-week spread, consecutive 12h doubles.","Principle":"Aim ~40h/7d; <=48h HARD; after 2 doubles next day PM-only or off, preferring off."},
            {"Stage":"6. HOLIDAY WATER-FILL","System":"Allocates public-holiday duty within the current month while respecting active holiday preferences and higher locks.","Evaluates":"Current-month holiday burden and monthly load only.","Principle":"One unit for everyone before seconds where feasible; prior months do not create catch-up."},
            {"Stage":"7. Other burden","System":"Balances total doubles and other consecutive/fatigue burden.","Evaluates":"Remaining structural burden.","Principle":"Fridays are already HARD water-filled at raw 0–1 and are not relaxed here."},
            {"Stage":"8. OTHER POST CORE","System":"Tests the all-post structural floor/ceil water-fill corridor.","Evaluates":"Seven noncritical post spreads.","Principle":"Target raw 0–1. <=2 and then <=3 are tried only after the tighter corridor is proven infeasible inside higher locks."},
            {"Stage":"9. SOFT-1 → SOFT-2 → SOFT-3","System":"Water-fills residents horizontally and locks each vertical rank.","Evaluates":"Time/recovery → exact desired work → month shape.","Principle":"Common entitlement layers before extras."},
            {"Stage":"10. CURRENT-MONTH POST OPTIMAL","System":"Without worsening SOFT, returns this month’s ordinary posts toward 0–1.","Evaluates":"Current-month resident × post exposure only.","Principle":"History is monitored but creates no debt and never steers a future month."},
            {"Stage":"11. ACTUAL + swaps/repairs","System":"Recomputes ACTUAL schedule, satisfaction and live fairness. For critical SPS absence, first transfers a resident from a same-block optional post.","Evaluates":"Mandatory SPS coverage, real post exposure, ACTUAL spreads, misses and safety.","Principle":"SYSTEM publication baseline stays frozen for audit; ACTUAL fairness follows reality. Water-fill may be broken post-publication and no future catch-up is created."},
        ]
        if advanced_mode:
            st.markdown("### Generator workflow")
            st.dataframe(pd.DataFrame(workflow_rows),use_container_width=True,hide_index=True)
        else:
            st.caption("The full generator workflow table is available in Advanced mode.")
        st.caption("Residents with no SOFT request are excluded from SOFT max-min, but any Resident-HARD requests still participate in the higher-priority burden-equity layer.")
    if senior_mode and advanced_mode:
        st.divider()
        st.markdown("### RULE CHANGE RESCUE" if lang=="EN" else "### TAISYKLIŲ KEITIMO RESCUE")
        st.caption(
            ("Čia keičiamos tik iš anksto saugiai sukonfigūruotos administracinės taisyklės. "
             "Kiekvienas pakeitimas sukuria naują versiją; ankstesnė versija lieka istorijoje ir gali būti grąžinta vienu veiksmu."
             if lang=="LT" else
             "Only pre-defined safe administrative rules are editable here. Every change creates a new version; the previous version remains in history and can be restored in one action.")
        )

        active_cfg=dict(ACTIVE_RULES)
        with st.expander("Keisti aktyvias taisykles" if lang=="LT" else "Edit active rules", expanded=False):
            with st.form(f"rule_profile_editor_v2534_{ACTIVE_RULE_PROFILE_VERSION}"):
                profile_name=st.text_input(
                    "Naujos versijos pavadinimas" if lang=="LT" else "New version name",
                    value=f"Rule profile v{ACTIVE_RULE_PROFILE_VERSION+1}"
                )
                profile_note=st.text_area(
                    "Kodėl keičiama?" if lang=="LT" else "Reason for change",
                    placeholder=("Pvz. nuo spalio SPS UG dubliams taikoma kita taisyklė." if lang=="LT" else "Example: SPS UG backup policy changes from October.")
                )

                st.markdown("#### Operacinės / HARD taisyklės" if lang=="LT" else "#### Operational / HARD rules")
                r1,r2,r3=st.columns(3)
                deadline_v=r1.number_input("Deadline day",1,28,int(active_cfg["deadline_day"]),1)
                rest_v=r2.number_input("Min rest, h",0.0,24.0,float(active_cfg["min_rest_hours"]),1.0)
                maxday_v=r3.number_input("Max hours/day",1.0,24.0,float(active_cfg["max_hours_per_day"]),1.0)
                r4,r5,r6=st.columns(3)
                maxdays7_v=r4.number_input("Max workdays / 7d",1,int(FATIGUE_MAX_WORKDAYS_ROLLING7),min(int(active_cfg["max_workdays_rolling7"]),int(FATIGUE_MAX_WORKDAYS_ROLLING7)),1)
                maxhours7_v=r5.number_input("Generation max hours / 7d",1.0,float(FATIGUE_ROLLING7_HARD_CEILING_HOURS),min(float(active_cfg["max_hours_rolling7"]),float(FATIGUE_ROLLING7_HARD_CEILING_HOURS)),1.0)
                maxassign_v=r6.number_input("Max assignments/day",1,4,int(active_cfg["max_assignments_per_day"]),1)
                swap_cap_v=st.number_input(
                    "Voluntary swap hard cap / 7d",
                    48.0,float(SWAP_ABSOLUTE_MAX_HOURS_ROLLING7),
                    min(float(active_cfg.get("swap_max_hours_rolling7",SWAP_ABSOLUTE_MAX_HOURS_ROLLING7)),float(SWAP_ABSOLUTE_MAX_HOURS_ROLLING7)),1.0,
                    help=("Tai nėra 'legalizavimo' mygtukas: 48 h lieka perspėjimo slenkstis; šis laukas tik nustato absoliutų techninį bloką pagal klinikos patvirtintą darbo laiko režimą." if lang=="LT" else "This does not legalize extra hours: 48h remains a warning threshold; this field only sets the absolute technical blocker for the employer-approved work-time regime.")
                )

                t1,t2=st.columns(2)
                target_daily_v=t1.number_input("Target norm h/day",1.0,24.0,float(active_cfg["target_daily_hours"]),0.1)
                target_shift_v=t2.number_input("Target shift h",1.0,24.0,float(active_cfg["target_shift_hours"]),0.5)

                st.markdown("#### Struktūrinės taisyklės" if lang=="LT" else "#### Structural rules")
                s1,s2=st.columns(2)
                onko_v=s1.toggle("Onko pairs + recovery — HARD",value=True,disabled=True,help=("V2.5.68: Onko = 1.5 pamainos, todėl skiriamas lyginiu skaičiumi; be to, tam pačiam rezidentui Onko negalima dvi kalendorines dienas iš eilės." if lang=="LT" else "V2.5.68: Onko = 1.5 shift units, so counts are even; additionally, the same resident cannot work Onko on consecutive calendar days."))
                weekend_unique_v=s2.toggle("Weekend uniqueness required",value=bool(active_cfg["weekend_unique_required"]))
                weekend_cap_v=st.number_input("Weekend max assignments/resident",1,4,int(active_cfg["weekend_max_assignments_per_resident"]),1)

                st.markdown("#### Dublių apimtis" if lang=="LT" else "#### Backup scope")
                b1,b2=st.columns(2)
                backup_sps_ro_v=b1.toggle("SPS RO — visos dienos / blokai",value=bool(active_cfg["backup_sps_ro"]))
                backup_sps_ug_v=b2.toggle("SPS UG — visos dienos / blokai",value=bool(active_cfg["backup_sps_ug"]))
                backup_weekends_v=False  # compatibility-only; generic weekend scope retired in V2.5.98
                b4,b5,b6=st.columns(3)
                backup_centro120_v=b4.toggle("Centro 120 AM",value=bool(active_cfg.get("backup_centro120_am",True)))
                backup_onko_v=b5.toggle("Onko RO",value=bool(active_cfg.get("backup_onko_ro",True)))
                backup_centro_ro_v=b6.toggle("CENTRO RO best-effort",value=bool(active_cfg.get("backup_centro_ro_best_effort",True)))

                st.markdown("#### Fairness guardrails")
                g1,g2=st.columns(2)
                post_tol_v=g1.number_input("Legacy post tolerance (V2.5.53 constitutional gates are fixed)",0,5,int(active_cfg["post_guardrail_tolerance"]),1,disabled=True)
                general_tol_v=g2.number_input("Other spread tolerance",0,5,int(active_cfg["general_guardrail_tolerance"]),1)
                st.caption("V2.5.74 fixed generation gates: SPS RO / SPS UG / weekends / FRIDAYS raw 0–1; every ordinary non-Onko post targets raw 0–1, widening only after proven infeasibility; generation ≤48 known hours and ≤6 worked days per rolling 7 days. Voluntary-swap hard cap is separately configurable 48–60h and should match the employer-approved legal work-time regime.")

                with st.expander("Optimizerio svoriai — keisti tik sąmoningai" if lang=="LT" else "Optimizer weights — change deliberately"):
                    w1,w2,w3=st.columns(3)
                    post_weight_v=w1.number_input("Monthly post weight",0.0,100000.0,float(active_cfg["monthly_post_spread_weight"]),50.0)
                    catchup_weight_v=w2.number_input("Legacy catch-up weight — DISABLED in V2.5.96",0.0,100000.0,0.0,1.0,disabled=True,help="Kept only for Rule Profile schema compatibility. Historical fairness is audit-only and never steers future generation.")
                    active_reward_v=w3.number_input("Active SOFT reward",0.0,100000.0,float(active_cfg["active_date_reward"]),10.0)

                candidate_cfg={
                    "deadline_day":deadline_v,
                    "target_daily_hours":target_daily_v,
                    "target_shift_hours":target_shift_v,
                    "max_assignments_per_day":maxassign_v,
                    "max_hours_per_day":maxday_v,
                    "min_rest_hours":rest_v,
                    "max_workdays_rolling7":maxdays7_v,
                    "max_hours_rolling7":maxhours7_v,
                    "swap_max_hours_rolling7":swap_cap_v,
                    "onko_even_required":True,
                    "weekend_unique_required":weekend_unique_v,
                    "weekend_max_assignments_per_resident":weekend_cap_v,
                    "backup_weekends":backup_weekends_v,
                    "backup_sps_ro":backup_sps_ro_v,
                    "backup_sps_ug":backup_sps_ug_v,
                    "backup_centro120_am":backup_centro120_v,
                    "backup_onko_ro":backup_onko_v,
                    "backup_centro_ro_best_effort":backup_centro_ro_v,
                    "post_guardrail_tolerance":post_tol_v,
                    "general_guardrail_tolerance":general_tol_v,
                    "monthly_post_spread_weight":post_weight_v,
                    "cumulative_post_catchup_weight":catchup_weight_v,
                    "active_date_reward":active_reward_v,
                }
                validate_btn=st.form_submit_button("VALIDUOTI PAKEITIMUS" if lang=="LT" else "VALIDATE CHANGES")
                activate_btn=st.form_submit_button("SUKURTI IR AKTYVUOTI NAUJĄ VERSIJĄ" if lang=="LT" else "CREATE & ACTIVATE NEW VERSION",type="primary")

            normalized_cfg,rule_errors=validate_rule_profile(candidate_cfg)
            if validate_btn:
                if rule_errors:
                    st.error(("Taisyklių profilis netinkamas: " if lang=="LT" else "Invalid rule profile: ")+"; ".join(rule_errors))
                else:
                    changes={k:(active_cfg.get(k),normalized_cfg.get(k)) for k in normalized_cfg if active_cfg.get(k)!=normalized_cfg.get(k)}
                    if changes:
                        st.success("VALIDATION — PASSED")
                        st.dataframe(pd.DataFrame([
                            {"Rule":k,"Current":a,"Proposed":b} for k,(a,b) in changes.items()
                        ]),use_container_width=True,hide_index=True)
                    else:
                        st.info("Nėra pakeitimų." if lang=="LT" else "No changes.")

            if activate_btn:
                if rule_errors:
                    st.error(("NEAKTYVUOTA: " if lang=="LT" else "NOT ACTIVATED: ")+"; ".join(rule_errors))
                else:
                    changes={k:(active_cfg.get(k),normalized_cfg.get(k)) for k in normalized_cfg if active_cfg.get(k)!=normalized_cfg.get(k)}
                    if not changes:
                        st.info("Nėra pakeitimų." if lang=="LT" else "No changes.")
                    else:
                        try:
                            created=db.create_and_activate_rule_profile(profile_name,normalized_cfg,profile_note)
                            st.success(
                                ("Naujas taisyklių profilis aktyvuotas. " if lang=="LT" else "New Rule Profile activated. ")
                                + f"v{created.get('version_no','?')}"
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(("Aktyvuoti nepavyko: " if lang=="LT" else "Activation failed: ")+str(e))

        profiles=db.list_rule_profiles(20)
        if profiles:
            with st.expander("Versijų istorija / rollback" if lang=="LT" else "Version history / rollback", expanded=False):
                hist=pd.DataFrame([{
                    "Version":r.get("version_no"),
                    "Name":r.get("name"),
                    "Active":bool(r.get("is_active")),
                    "Created":str(r.get("created_at") or "")[:19],
                    "Note":r.get("note") or "",
                } for r in profiles])
                st.dataframe(hist,use_container_width=True,hide_index=True)
                older=[r for r in profiles if not r.get("is_active")]
                if older:
                    selected_profile=st.selectbox(
                        "Grąžinti versiją" if lang=="LT" else "Restore version",
                        older,
                        format_func=lambda r:f"v{r.get('version_no')} — {r.get('name')}",
                        key="rollback_rule_profile_v2534"
                    )
                    confirm_rule_rollback=st.checkbox(
                        "Patvirtinu rollback" if lang=="LT" else "Confirm rollback",
                        key="confirm_rule_rollback_v2534"
                    )
                    if st.button(
                        "ROLLBACK Į PASIRINKTĄ VERSIJĄ" if lang=="LT" else "ROLL BACK TO SELECTED VERSION",
                        disabled=not confirm_rule_rollback,
                        use_container_width=True
                    ):
                        try:
                            restored=db.activate_rule_profile(int(selected_profile["id"]))
                            st.success(("Aktyvuota " if lang=="LT" else "Activated ")+f"v{restored.get('version_no','?')}")
                            st.rerun()
                        except Exception as e:
                            st.error(("Rollback nepavyko: " if lang=="LT" else "Rollback failed: ")+str(e))

    content=db.get_manual(lang)
    explanatory=explanatory_manual_only(content)
    st.caption(
        ("Žemiau — tik paaiškinimai ir kontekstas. Keičiamos operacinės taisyklės negali būti aprašomos ranka: jos keičiamos tik per aktyvų Rule Profile aukščiau."
         if lang=="LT" else
         "Below is explanatory context only. Mutable operational rules must not be defined manually; they are changed only through the active Rule Profile above.")
    )
    mode=tr("read")
    if senior_mode: mode=st.radio("",[tr("read"),tr("edit")],horizontal=True,label_visibility="collapsed")
    if mode==tr("read"):
        st.markdown(explanatory)
    else:
        st.warning(
            "Šis tekstas nėra engine taisyklių šaltinis. HARD, backup, target, guardrail ir kiti keičiami parametrai turi būti keičiami tik per RULE CHANGE RESCUE."
            if lang=="LT" else
            "This text is not the engine rule source. HARD, backup, target, guardrail and other mutable parameters must be changed only through RULE CHANGE RESCUE."
        )
        edited=st.text_area(("Paaiškinimai / pastabos" if lang=="LT" else "Explanatory notes"),value=explanatory,height=760,label_visibility="collapsed")
        if st.button(tr("save_rules"),type="primary"):
            db.save_manual(lang,edited)
            st.success(tr("rules_saved"))
            st.rerun()
