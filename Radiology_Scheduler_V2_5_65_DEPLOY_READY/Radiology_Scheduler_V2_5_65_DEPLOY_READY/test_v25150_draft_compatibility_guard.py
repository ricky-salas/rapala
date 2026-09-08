from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')
ENGINE=(ROOT/'scheduler_engine.py').read_text(encoding='utf-8')


def run():
    # Release/API provenance is no longer the stale V2.5.77 marker.
    assert 'APP_VERSION = "2.5.150 DRAFT COMPATIBILITY GUARD"' in APP
    assert 'EXPECTED_ENGINE_API_VERSION = "2.5.150"' in APP
    assert 'ENGINE_API_VERSION = "2.5.150"' in ENGINE
    assert '"engine_stats_version": f"V{ENGINE_API_VERSION}"' in ENGINE
    assert '"engine_api_version": str(ENGINE_API_VERSION)' in ENGINE
    assert '"engine_stats_version": "V2.5.77"' not in ENGINE

    # SolveResult carries immutable provenance through serialize -> deserialize -> revalidate.
    assert 'provenance: Optional[dict] = None' in ENGINE
    assert 'provenance=dict(result.provenance or {})' in ENGINE
    assert '"provenance": dict(result.provenance or {})' in ENGINE
    assert 'def stamp_generation_provenance' in APP
    assert '"draft_compatibility_version":DRAFT_COMPATIBILITY_VERSION' in APP
    assert 'result=stamp_generation_provenance(result,"generate_rebuild")' in APP
    assert 'candidate=stamp_generation_provenance(candidate,"improve_recheck")' in APP

    # DB-row existence is never treated as validity. Current engine + current inputs are mandatory.
    assert 'def draft_compatibility_status' in APP
    guard=APP[APP.index('def draft_compatibility_status'):APP.index('def render_invalid_draft_guard')]
    assert 'revalidate_loaded_result' in guard
    assert 'hard==0 and hard_missed==0' in guard
    assert 'snapshot_matches' in guard
    assert 'valid_for_improve' in guard

    # Invalid legacy drafts are audit-only: improve and every publication path are fail-closed.
    assert 'LEGACY / INVALID DRAFT — SKELBTI NEGALIMA' in APP
    assert 'negali būti kokybės baseline' in APP
    assert 'disabled=(generation_locked or _sp_private_generation_gate or not _improve_health.get("valid_for_improve"))' in APP
    publish=APP[APP.index('def publish_system_baseline_for_swap_window'):APP.index('def render_operator_manual_override')]
    assert 'draft_health=draft_compatibility_status' in publish
    assert 'if not draft_health.get("publishable")' in publish
    assert 'INVALID / LEGACY DRAFT' in publish
    assert 'disabled=not _schedule_draft_publishable' in APP
    assert '_candidate_source_valid' in APP

    # A timeout/no-incumbent never rebrands a stale draft as valid.
    assert 'NAUJAS GRAFIKAS NESUGENERUOTAS' in APP
    assert 'auditui — jo skelbti ar gerinti negalima' in APP
    assert 'The UI must revalidate any stored draft before treating it as publishable' in ENGINE

    # Runtime serialization smoke test without importing the Streamlit app.
    sys.path.insert(0,str(ROOT))
    import scheduler_engine as mod
    r=mod.SolveResult(True,'ok',provenance={'app_version':'2.5.150 test'})
    raw=mod.serialize_result(r)
    assert raw['engine_stats_version']=='V2.5.150'
    assert raw['engine_api_version']=='2.5.150'
    assert raw['provenance']['app_version']=='2.5.150 test'
    r2=mod.deserialize_result(raw)
    assert r2.provenance['app_version']=='2.5.150 test'

    print('V2.5.150 Draft Compatibility Guard PASS')


if __name__=='__main__':
    run()
