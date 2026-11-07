"""Nyelvi fájlok ellenőrzése: minden kulcs létezik, a helyőrzők egyeznek a magyar alapszöveggel."""
import ast, json, os, re, string, sys, tempfile
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import i18n

ok = True
def check(name, cond, extra=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name, extra); ok &= bool(cond)

def placeholders(s):
    return {re.split(r"[.\[!:]", f)[0] for _, f, _, _ in string.Formatter().parse(s) if f}

hu = json.load(open(os.path.join(ROOT, "lang", "hu.json"), encoding="utf-8"))
# 1) minden tl("kulcs") a kódban létezik, és a paraméterek egyeznek a helyőrzőkkel
used, bad = {}, []
for f in ("core.py", "orbiq.py", "skyplot.py", "viewlogic.py", "storage.py"):
    tree = ast.parse(open(os.path.join(ROOT, f), encoding="utf-8").read())
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "tl" and n.args:
            a = n.args[0]
            if isinstance(a, ast.Constant): used.setdefault(a.value, []).append(({k.arg for k in n.keywords}, f, n.lineno))
            elif isinstance(a, ast.JoinedStr) or isinstance(a, ast.IfExp):
                for c in ast.walk(a):
                    if isinstance(c, ast.Constant) and isinstance(c.value, str) and "." in c.value:
                        used.setdefault(c.value, []).append(({k.arg for k in n.keywords}, f, n.lineno))
missing = [k for k in used if k not in hu and not k.startswith("compass8.")]
check("minden használt kulcs szerepel a hu.json-ban", not missing, str(missing))
for k, uses in used.items():
    if k in hu:
        for kw, f, ln in uses:
            if placeholders(hu[k]) != kw: bad.append((k, f, ln))
check("a hívások paraméterei egyeznek a {helyőrzőkkel}", not bad, str(bad))
shadow = []
for f in ("core.py", "orbiq.py", "skyplot.py", "viewlogic.py", "storage.py"):
    for n in ast.walk(ast.parse(open(os.path.join(ROOT, f), encoding="utf-8").read())):
        if (isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id == "tl") or (isinstance(n, ast.arg) and n.arg == "tl"):
            shadow.append((f, n.lineno))
check("nincs 'tl' nevű helyi változó (elfedné a fordítófüggvényt)", not shadow, str(shadow))

# 2) minden nyelvi fájl: azonos kulcsok és helyőrzők, mint a magyarban
for code, name in i18n.available().items():
    d = json.load(open(os.path.join(ROOT, "lang", code + ".json"), encoding="utf-8"))
    miss = [k for k in hu if k not in d]
    extra = [k for k in d if k not in hu]
    badph = [k for k in d if k in hu and k != "_meta" and placeholders(d[k]) != placeholders(hu[k])]
    check(f"{code} ({name}): nincs hiányzó kulcs", not miss, f"{len(miss)} hiányzik")
    check(f"{code}: nincs felesleges kulcs", not extra, str(extra[:5]))
    check(f"{code}: a helyőrzők egyeznek", not badph, str(badph[:5]))

# 3) tartalék: hiányzó kulcs -> a magyar szöveg; ismeretlen nyelv -> magyar
i18n.init("hu")
check("t() ismert kulcs", i18n.t("sky.aos", time="12:00") == "AOS 12:00")
check("t() ismeretlen kulcs -> a kulcs maga", i18n.t("nincs.ilyen") == "nincs.ilyen")
check("ismeretlen nyelv -> magyar", i18n.init("zz") == "hu")
check("hibás helyőrző nem dob kivételt", isinstance(i18n.t("sky.aos"), str))

print("\nÖSSZESEN:", "MINDEN OK" if ok else "VAN HIBA")
sys.exit(0 if ok else 1)
