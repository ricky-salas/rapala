from pathlib import Path

ROOT=Path(__file__).resolve().parent
APP=(ROOT/'app.py').read_text(encoding='utf-8')


def run():
    assert 'APP_VERSION = "2.5.152 STRICT FAIRNESS + WISH AUDIT"' in APP

    # Request side: privacy-preserving email reset from the existing login gate.
    assert '"forgot_password":"Pamiršau slaptažodį?"' in APP
    assert 'sb.auth.reset_password_email(clean' in APP
    assert 'Jei paskyra su šiuo el. paštu egzistuoja' in APP
    assert '_password_recovery_redirect_url' in APP
    assert 'SCHEDULER_PUBLIC_URL' in APP

    # Completion side: tokens stay in the browser URL fragment and never enter Streamlit query params.
    bridge=APP[APP.index('def render_password_recovery_bridge'):APP.index('def _consume_password_reset_done')]
    assert 'window.parent.location.hash' in bridge
    assert "hash.get('access_token')" in bridge
    assert '/auth/v1/user' in bridge
    assert "method:'PUT'" in bridge
    assert "'Authorization':'Bearer '+access" in bridge
    assert 'st.query_params' not in bridge
    assert 'history.replaceState' in bridge

    # A non-sensitive completion marker forces a clean post-reset login session.
    assert 'password_reset_done' in APP
    assert 'sb.auth.sign_out()' in APP
    assert 'clear_cross_account_session_state(keep_client=False)' in APP

    # Password UX guard.
    assert 'a.length<8 || a!==b' in bridge

    # Existing identity binding remains untouched.
    assert 'def require_linked_profile(sb,user):' in APP
    assert 'db.claim_profile(initials,code.strip())' in APP

    print('V2.5.149 Password Recovery PASS')


if __name__=='__main__':
    run()
