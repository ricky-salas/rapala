"""Exercise the real read-only preview without launching Streamlit or a DB."""
import ast
from pathlib import Path
from types import SimpleNamespace

root = Path(__file__).parent
tree = ast.parse((root / "app.py").read_text())
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
          and n.name == "render_generation_draft_preview")
calls = []
st = SimpleNamespace(
    markdown=lambda *a, **k: calls.append(("markdown", a, k)),
    caption=lambda *a, **k: calls.append(("caption", a, k)),
    dataframe=lambda *a, **k: calls.append(("table", a, k)),
)
draft = SimpleNamespace(assignments={1: "AA"})
ns = dict(st=st, lang="LT", DEFAULT_PEOPLE=[{"initials": "AA"}],
          badge=lambda initials, _: initials,
          schedule_grid=lambda y, m, result: (y, m, result),
          style_schedule=lambda grid: grid)
exec(compile(ast.Module(body=[fn], type_ignores=[]), "preview", "exec"), ns)
render = ns[fn.name]
for health in (None, {}, {"publishable": False, "result": draft},
               {"publishable": True, "result": None}):
    render(health, 2026, 10)
assert calls == []
render({"publishable": True, "result": draft}, 2026, 10)
tables = [c for c in calls if c[0] == "table"]
assert len(tables) == 1
assert tables[0][1][0] == (2026, 10, draft)
assert draft.assignments == {1: "AA"}
assert "db" not in {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
assert (root/"app.py").read_bytes() == (root/root.name/"app.py").read_bytes()
print("PASS validated colored draft preview, invalid-draft guard, no DB writes, deployment parity")
