from pathlib import Path
import ast
import importlib.util
import sys

BASE = Path(__file__).resolve().parent
app_path = BASE / 'app.py'
eng_path = BASE / 'scheduler_engine.py'

app_tree = ast.parse(app_path.read_text(encoding='utf-8'))
imports = []
for node in app_tree.body:
    if isinstance(node, ast.ImportFrom) and node.module == 'scheduler_engine':
        imports.extend(alias.name for alias in node.names)

spec = importlib.util.spec_from_file_location('scheduler_engine', eng_path)
mod = importlib.util.module_from_spec(spec)
sys.modules['scheduler_engine'] = mod
assert spec and spec.loader
spec.loader.exec_module(mod)

missing = [name for name in imports if not hasattr(mod, name)]
assert not missing, f'Missing scheduler_engine imports: {missing}'
assert str(getattr(mod, 'ENGINE_API_VERSION', '')) == '2.5.153'

text = app_path.read_text(encoding='utf-8')
assert 'APP_VERSION = "2.5.155 DEPLOY-SYNC HOTFIX"' in text
assert 'EXPECTED_ENGINE_API_VERSION = "2.5.153"' in text
assert 'COMPATIBLE_ENGINE_API_VERSIONS = {"2.5.153"}' in text
print(f'PASS V2.5.155 deploy import sync: {len(imports)} scheduler symbols resolved; engine 2.5.153')
