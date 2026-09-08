from io import BytesIO
from pathlib import Path
import json
import pandas as pd

import scheduler_engine as se
from extension_core import load_extension, extension_summary
from opto_research import (
    solve_rapa_extension, evaluate_schedule, assignments_dataframe,
    parse_schedule_excel, extension_template_xlsx, parse_extension_upload,
)


def run():
    app=Path('app.py').read_text(encoding='utf-8')
    assert 'OPTO tyrimas' in app
    assert 'RANKA · jų pačių Excel grafikas' in app
    assert 'OPTO · OPTO sugeneruotas Excel grafikas' in app
    assert 'GENERUOTI RAPA' in app
    assert 'names.append("RAPA Extension")' not in app
    assert 'research_shadow_tab_index=None' in app

    ext=load_extension(Path('extensions/LSMU_R1_2026_10.extension.json').read_bytes())
    sm=extension_summary(ext,2026,10)
    assert sm['people']==16 and sm['slots']>0
    rr=solve_rapa_extension(ext,2026,10,time_limit=30)
    assert rr['ok'], rr.get('message')
    met=evaluate_schedule(ext,2026,10,rr['assignments'])
    assert met['coverage_pct']==100.0
    assert met['hard_errors']==0
    assert met['workload_spread']<=1.0
    assert met['weekend_spread']<=1

    # Generated schedule survives Excel round-trip for RANKA/OPTO import path.
    df=assignments_dataframe(ext,2026,10,rr['assignments'])
    b=BytesIO()
    with pd.ExcelWriter(b,engine='xlsxwriter') as w:
        df.to_excel(w,index=False,sheet_name='GRAFIKAS')
    parsed,warnings=parse_schedule_excel(b.getvalue(),ext,2026,10)
    assert parsed==rr['assignments'] and not warnings

    # Structured Excel extension path is supported.
    ext2,warnings=parse_extension_upload(extension_template_xlsx(),'extension.xlsx')
    assert extension_summary(ext2,2026,10)['people']==2

    # October weekend duty/dublis is one full 12h position per weekend day.
    wk=se.weekend_fcfs_backup_slots(2026,10)
    assert wk and all(s.block=='FULL' and s.workload2==4 for s in wk)
    assert len({s.day for s in wk})==len(wk)
    # Unconfirmed night model stays fail-closed.
    assert not se.night_xray_duty_active(2026,11)

    print('V2.5.144 release checks PASS')

if __name__=='__main__':
    run()
