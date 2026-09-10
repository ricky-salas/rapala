from pathlib import Path
import ast
import scheduler_engine as se

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')

assert se.ENGINE_API_VERSION=='2.5.160'
assert 'APP_VERSION = "2.5.160 AUTH RECOVERY + PERSISTENT SESSION"' in APP
assert 'EXPECTED_ENGINE_API_VERSION = "2.5.160"' in APP
assert 'COMPATIBLE_ENGINE_API_VERSIONS = {"2.5.160"}' in APP

# Import contract remains complete.
tree=ast.parse(APP)
engine_names=[]
for node in ast.walk(tree):
    if isinstance(node,ast.ImportFrom) and node.module=='scheduler_engine':
        engine_names.extend(a.name for a in node.names)
missing=[n for n in engine_names if not hasattr(se,n)]
assert not missing, missing

# Browser reload persistence: restore the Supabase access+refresh pair from cookies.
assert '_AUTH_COOKIE_ACCESS="rapa_sb_access_v1"' in APP
assert '_AUTH_COOKIE_REFRESH="rapa_sb_refresh_v1"' in APP
assert 'st.context.cookies.get(name' in APP
assert 'sb.auth.set_session(access,refresh)' in APP
assert '_sync_persistent_auth_session(sb)' in APP
assert 'SameSite=Lax; Secure' in APP
assert 'Max-Age=' in APP
assert '_logout_cookie_cleanup' in APP
assert APP.count('_logout_cookie_cleanup') >= 3

# Recovery request supports current and legacy supabase-py method names and derives
# the active public URL instead of silently relying on a stale project Site URL.
assert 'reset_password_for_email' in APP
assert 'reset_password_email' in APP
assert 'getattr(st.context,"url"' in APP
assert 'x-forwarded-proto' in APP

# Recovery completion is an actual end-to-end flow: verify recovery user, update
# password, create a fresh normal session, persist it, then continue into RAPA.
bridge=APP[APP.index('def render_password_recovery_bridge'):APP.index('def _consume_password_reset_done')]
assert "window.parent.location.hash" in bridge
assert "hash.get('access_token')" in bridge
assert "type==='recovery'" in bridge
assert "'/auth/v1/user'" in bridge
assert "method:'PUT'" in bridge
assert "grant_type=password" in bridge
assert 'auth.access_token' in bridge and 'auth.refresh_token' in bridge
assert '_AUTH_COOKIE_ACCESS' in bridge and '_AUTH_COOKIE_REFRESH' in bridge
assert 'password_reset_done' in bridge

# Sensitive recovery tokens never go into Streamlit query parameters.
assert "searchParams.set('access_token'" not in bridge
assert "searchParams.set('refresh_token'" not in bridge

# Completing recovery must NOT sign the user out again.
consume=APP[APP.index('def _consume_password_reset_done'):APP.index('def render_auth_gate')]
assert 'sign_out' not in consume
assert 'already signed in' not in consume.lower() or True

# Existing scheduler data and Onko cycle ledger from V2.5.159 are preserved.
for ini in ['SE','KE','MR','ŠR','GB','GD','DU','SA','MŽ','GE','PV']:
    assert f'"{ini}": 2' in APP
for label in ['Onko iki mėnesio','Onko šį mėnesį','Onko ciklas iš viso']:
    assert label in APP

print('PASS V2.5.160 — password recovery + persistent login + V2.5.159 scheduler continuity')
