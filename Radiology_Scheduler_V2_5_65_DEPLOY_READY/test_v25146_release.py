from pathlib import Path
p=Path(__file__).resolve().parent
app=(p/'app.py').read_text(encoding='utf-8')
assert '"special_days":"Specialios dienos"' in app
assert 'names += [tr("preferences"),tr("settings"),tr("special_days")]' in app
assert '### Pateisinamas neatvykimas' in app
assert 'Dubliai atsirakins tik paskelbus preliminarų grafiką.' in app
assert '### Darbo dienos ne klinikoje' not in app
assert 'st.title(tr("login_title"))' in app
assert 'auth.sign_in_with_password' in app
assert 'auth.sign_up' not in app
print('V2.5.146 release checks PASS')
