# Limpeza em Lote + Quarentena .vec — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o fluxo de confirmação item-a-item por revisão em grupos de risco com confirmação única, execução em lote estilo Genesis e quarentena `.vec` (zip auto-contido, só a última execução) com restauração pela GUI e associação da extensão no Windows.

**Architecture:** Regras de segurança e quarentena moram no Python (`quarantine.py` novo + comandos no bridge JSON-lines); agrupamento por risco é apresentação (JS); `VectorHost.ps1` só repassa (`engine-call` genérico com whitelist) e provê diálogos nativos + registro HKCU. A GUI orquestra o lote chamando `remove` por item (guard revalida cada caminho).

**Tech Stack:** Python 3.9+ stdlib (zipfile/shutil/json/pathlib), pytest, WebView2 (PowerShell WinForms), JS vanilla (app.js/mock.js), ps2exe.

**Spec:** `docs/superpowers/specs/2026-09-21-batch-clean-quarantine-design.md` (branch `feat/phase2-engine-bridge`)

**Testes sempre com:** `python -m pytest tests/ -q` dentro de `vector/`. Commit após cada task (branch atual, nunca main).

---

### Task 1: `summaryPlain` — frase-motivo em linguagem humana (motor)

**Files:**
- Modify: `src/vector/scoring.py` (acrescentar mapa + função no fim)
- Modify: `src/vector/report.py` (`to_report_payload` e `write_json`)
- Test: `tests/test_scoring.py` (novo ou acrescentar), `tests/test_report.py`

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_scoring.py`:

```python
from vector.models import Evidence, OrphanCandidate
from vector.scoring import plain_summary


def _cand(kind="folder", *evs):
    return OrphanCandidate(kind=kind, path=r"C:\Program Files\Foo",
                           label="Foo", evidences=list(evs))


def test_plain_summary_uses_dominant_evidence():
    c = _cand("folder",
              Evidence("+10 pasta vazia ou ilegivel", 10, "filesystem"),
              Evidence("+40 nome ausente nos programas instalados", 40, "filesystem"))
    assert "lista de programas instalados" in plain_summary(c)


def test_plain_summary_registry_manual():
    c = _cand("registry",
              Evidence("+40 chave sem programa correspondente instalado", 40, "registry"))
    s = plain_summary(c)
    assert "registro" in s and "manual" in s


def test_plain_summary_fallback_generic_folder():
    c = _cand("folder", Evidence("+15 resta unins000.exe sem entrada de desinstalacao",
                                 15, "filesystem"))
    assert plain_summary(c)  # nao vazio; mapa cobre o prefixo "resta "


def test_plain_summary_empty_evidences_fallback():
    assert plain_summary(_cand("folder")) == "possível resíduo de programa desinstalado"
    assert "manual" in plain_summary(_cand("service"))
```

Acrescentar em `tests/test_report.py` (no teste que já exercita `to_report_payload`, ou novo):

```python
def test_payload_includes_summary_plain(sample_report):
    payload = to_report_payload(sample_report)
    cand = payload["candidates"][0]
    assert "summaryPlain" in cand and cand["summaryPlain"]
```

(Adapte `sample_report` à fixture existente de `tests/`; o requisito é: `to_report_payload` devolve `summaryPlain` não-vazio por candidato.)

- [ ] **Step 2: Rodar e confirmar FAIL** — `python -m pytest tests/test_scoring.py -q` → `ImportError: cannot import name 'plain_summary'`.

- [ ] **Step 3: Implementar** — em `src/vector/scoring.py`, adicionar:

```python
# Frases em linguagem simples para a GUI (campo summaryPlain). Casadas por
# substring com a descricao da evidencia dominante (maior peso): a fonte de
# verdade dos textos tecnicos continua nos scanners; aqui so a "traducao".
_PLAIN_PHRASES: tuple[tuple[str, str], ...] = (
    ("nome ausente nos programas instalados",
     "não aparece na lista de programas instalados do Windows, "
     "mas ainda há pastas dele no sistema"),
    ("chave sem programa correspondente",
     "chave de registro sem programa correspondente — a remoção é manual"),
    ("InstallLocation inexistente",
     "o registro aponta para uma pasta que não existe mais — a remoção é manual"),
    ("Run aponta",
     "iniciava com o Windows, mas o programa apontado não existe mais "
     "— a remoção é manual"),
    ("App Path quebrado",
     "atalho de execução do Windows quebrado — a remoção é manual"),
    ("servico aponta",
     "serviço aponta para um executável que não existe mais — a remoção é manual"),
    ("servico sem programa",
     "serviço sem programa correspondente instalado — a remoção é manual"),
    ("tarefa executa binario",
     "tarefa agendada aponta para um executável que não existe mais "
     "— a remoção é manual"),
    ("tarefa sem programa",
     "tarefa agendada sem programa correspondente — a remoção é manual"),
    ("resta ", "só tem resto de instalador/desinstalador para trás"),
    ("pasta abandonada", "está sem uso há muito tempo"),
    ("pasta vazia", "está vazia ou ilegível"),
)

_FALLBACK_FOLDER = "possível resíduo de programa desinstalado"
_FALLBACK_OTHER = "remoção manual recomendada"


def plain_summary(candidate: OrphanCandidate) -> str:
    """Uma frase, derivada da evidencia de maior peso. Nunca levanta excecao."""
    for ev in sorted(candidate.evidences, key=lambda e: e.weight, reverse=True):
        for needle, phrase in _PLAIN_PHRASES:
            if needle in ev.description:
                return phrase
    return _FALLBACK_FOLDER if candidate.kind == "folder" else _FALLBACK_OTHER
```

- [ ] **Step 4: Ligar no payload e no JSON da CLI** — em `src/vector/report.py`:

No topo: `from vector.scoring import plain_summary` (cuidado com import circular: `scoring` importa `models/settings/utils`, nunca `report` — seguro).

Em `to_report_payload`, no dict de cada candidato, acrescentar após `"label": c.label,`:

```python
                "summaryPlain": plain_summary(c),
```

Em `write_json` (contrato Orbit — aditivo), acrescentar após `"label": c.label,`:

```python
                "summary_plain": plain_summary(c),
```

- [ ] **Step 5: Rodar testes GREEN** — `python -m pytest tests/ -q` → todos passam (22 + novos).

- [ ] **Step 6: Commit**

```bash
git add src/vector/scoring.py src/vector/report.py tests/test_scoring.py tests/test_report.py
git commit -m "feat(engine): summaryPlain - frase-motivo em linguagem humana por candidato"
```

---

### Task 2: `quarantine.py` — stage + seal + inspect (núcleo .vec)

**Files:**
- Create: `src/vector/quarantine.py`
- Create: `tests/test_quarantine.py`

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_quarantine.py`:

```python
"""Quarentena .vec: staging -> selar (zip+manifesto) -> inspecionar.

Tudo em tmp_path; nenhuma pasta real do usuario e tocada. `base` explícito
e a injecao de teste (mesma filosofia de scan_fn/remove_fn no bridge).
"""

import json

import pytest

from vector import quarantine
from vector.models import OrphanCandidate


@pytest.fixture
def folder(tmp_path):
    def make(name, files=("a.txt",)):
        d = tmp_path / "src" / name
        d.mkdir(parents=True, exist_ok=True)
        for f in files:
            (d / f).write_text("x", encoding="utf-8")
        return d
    return make


def _cand(path, label="Foo", confidence="HIGH", kind="folder", sensitive=False):
    return OrphanCandidate(kind=kind, path=str(path), label=label,
                           size_bytes=123, confidence=confidence,
                           sensitive=sensitive)


def test_stage_moves_folder_and_writes_meta(tmp_path, folder):
    base = tmp_path / "q"
    d = folder("Foo")
    entry, err = quarantine.stage(_cand(d), base=base)
    assert err == "" and entry["original"] == str(d)
    assert not d.exists()                      # MOVeu, nao copiou
    assert entry["summaryPlain"]               # frase vem junto
    meta = base / "staging" / f'{entry["id"]}.meta.json'
    assert json.loads(meta.read_text(encoding="utf-8"))["id"] == entry["id"]


def test_stage_missing_folder_returns_reason(tmp_path):
    entry, err = quarantine.stage(_cand(tmp_path / "nao-existe"), base=tmp_path / "q")
    assert entry is None and "nao existe mais" in err


def test_seal_creates_selfcontained_vec_and_empties_staging(tmp_path, folder):
    base = tmp_path / "q"
    d1, d2 = folder("Um"), folder("Dois")
    quarantine.stage(_cand(d1, label="Um"), base=base)
    quarantine.stage(_cand(d2, label="Dois"), base=base)
    info = quarantine.seal(base=base)
    vec = base / "last.vec"
    assert vec.exists() and info["sealedTs"]
    names = info["items"] and [i["label"] for i in info["items"]]
    assert sorted(names) == ["Dois", "Um"]
    assert not (base / "staging").exists()     # staging.promovido ao zip
    import zipfile
    with zipfile.ZipFile(vec) as zf:
        assert "manifest.json" in zf.namelist()
        assert any(n.endswith("a.txt") for n in zf.namelist())


def test_seal_replaces_previous_backup(tmp_path, folder):
    base = tmp_path / "q"
    quarantine.stage(_cand(folder("Velho")), base=base)
    quarantine.seal(base=base)
    quarantine.stage(_cand(folder("Novo")), base=base)
    info = quarantine.seal(base=base)
    assert [i["label"] for i in info["items"]] == ["Novo"]  # so a ultima execucao


def test_seal_nothing_returns_none(tmp_path):
    assert quarantine.seal(base=tmp_path / "q") is None


def test_inspect_none_when_empty_and_seals_orphan_staging(tmp_path, folder):
    base = tmp_path / "q"
    assert quarantine.inspect(base=base) is None
    d = folder("Orfa")
    quarantine.stage(_cand(d), base=base)
    info = quarantine.inspect(base=base)       # staging orfao e selado no 1o acesso
    assert (base / "last.vec").exists()
    assert info["items"][0]["label"] == "Orfa"


def test_inspect_flags_external_files(tmp_path, folder):
    base = tmp_path / "q"
    quarantine.stage(_cand(folder("X")), base=base)
    quarantine.seal(base=base)
    copy = tmp_path / "copia.vec"
    copy.write_bytes((base / "last.vec").read_bytes())
    assert quarantine.inspect(path=copy, base=base)["external"] is True
    assert quarantine.inspect(base=base)["external"] is False


def test_inspect_corrupt_file(tmp_path):
    bad = tmp_path / "ruim.vec"
    bad.write_bytes(b"nao sou um zip")
    out = quarantine.inspect(path=bad, base=tmp_path / "q")
    assert out["corrupt"] is True and out["items"] == []
```

- [ ] **Step 2: FAIL** — `python -m pytest tests/test_quarantine.py -q` → `ModuleNotFoundError: vector.quarantine`.

- [ ] **Step 3: Implementar o módulo** — `src/vector/quarantine.py`:

```python
"""Quarentena do Vector: na GUI nada e apagado - pastas sao MOVIDAS para um
backup unico .vec (zip auto-contido com manifesto) e podem voltar de la.

Politica (spec 2026-09-21): guarda apenas a ULTIMA execucao; seal()
substitui o backup anterior. restaurar do backup ATIVO = move de volta e
enxuga a entrada; restaurar de .vec EXTERNO = copia, o arquivo nao muda.

Formato .vec: zip ZIP_DEFLATED com manifest.json na raiz + itens sob
"<id>/<pasta-arquivo>/...". O manifesto carrega os metadados de decisao
(kind/confidence/sensitive/label/summaryPlain/original/tamanho) para a tela
de Restauração funcionar em qualquer maquina, sem re-scan.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Optional

from vector.models import OrphanCandidate
from vector.scoring import plain_summary

ACTIVE_NAME = "last.vec"
MANIFEST_NAME = "manifest.json"
_STAGING = "staging"


def root(base: Optional[Path] = None) -> Path:
    """Pasta da quarentena. Testes injetam base (tmp_path); runtime usa LOCALAPPDATA."""
    if base is not None:
        return Path(base)
    local = os.environ.get("LOCALAPPDATA")
    parent = Path(local) / "Vector" if local else Path.home() / ".vector"
    return parent / "quarantine"


def active_path(base: Optional[Path] = None) -> Path:
    return root(base) / ACTIVE_NAME


def _entry_json(entry: dict) -> str:
    return json.dumps(entry, ensure_ascii=False)


def stage(candidate: OrphanCandidate,
          base: Optional[Path] = None) -> tuple[Optional[dict], str]:
    """Move a pasta inteira para o staging. Devolve (entrada, "") ou (None, motivo)."""
    src = Path(candidate.path)
    if not src.exists():
        return None, "a pasta nao existe mais (ja foi removida em outra limpeza?)"
    rid = f"{int(time.time())}-{uuid.uuid4().hex[:8]}"
    entry = {
        "id": rid,
        "original": str(src),
        "archived": src.name,
        "sizeBytes": candidate.size_bytes,
        "ts": int(time.time()),
        "kind": candidate.kind,
        "confidence": candidate.confidence,
        "sensitive": candidate.sensitive,
        "label": candidate.label,
        "summaryPlain": plain_summary(candidate),
    }
    dst = root(base) / _STAGING / rid / src.name
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        (root(base) / _STAGING / f"{rid}.meta.json").write_text(
            _entry_json(entry), encoding="utf-8")
    except PermissionError:
        return None, "sem permissao para mover esta pasta (rode como admin)."
    except OSError as exc:
        return None, f"falha ao mover: {exc}"
    return entry, ""


def _read_staged(base: Optional[Path]) -> list[tuple[dict, Path]]:
    staging = root(base) / _STAGING
    if not staging.exists():
        return []
    out = []
    for meta in sorted(staging.glob("*.meta.json")):
        entry = json.loads(meta.read_text(encoding="utf-8"))
        out.append((entry, staging / entry["id"]))
    return out


def seal(base: Optional[Path] = None) -> Optional[dict]:
    """Compacta o staging em last.vec, SUBSTITUINDO o backup anterior.

    None se nao ha nada selado. Falha nunca apaga o staging (itens se preservam).
    """
    staged = _read_staged(base)
    if not staged:
        shutil.rmtree(root(base) / _STAGING, ignore_errors=True)
        return None
    staged.sort(key=lambda t: t[0]["ts"])
    entries = [e for e, _ in staged]
    target = active_path(base)
    tmp = target.with_name(ACTIVE_NAME + ".tmp")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
            for entry, folder in staged:
                top = folder / entry["archived"]
                for f in sorted(top.rglob("*")):
                    if f.is_file():
                        rel = f.relative_to(folder).as_posix()
                        zf.write(f, rel)
            zf.writestr(MANIFEST_NAME, _entry_json(
                {"sealed_ts": int(time.time()), "items": entries}))
        if target.exists():
            target.unlink()
        tmp.replace(target)
    except OSError as exc:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise RuntimeError(f"falha ao selar a quarentena: {exc}")
    shutil.rmtree(root(base) / _STAGING, ignore_errors=True)
    return inspect(base=base)


def _read_vec(path: Path) -> Optional[dict]:
    try:
        with zipfile.ZipFile(path) as zf:
            return json.loads(zf.read(MANIFEST_NAME))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, OSError):
        return None


def _is_external(path: Path, base: Optional[Path]) -> bool:
    try:
        return Path(path).resolve() != active_path(base).resolve()
    except OSError:
        return True


def inspect(path: Optional[Path] = None,
            base: Optional[Path] = None) -> Optional[dict]:
    """Le um .vec (default: o ativo). Staging orfao (queda no meio de uma
    execucao) e selado no primeiro acesso - itens nunca se perdem."""
    if path is None:
        if _read_staged(base):
            return seal(base=base)
        target = active_path(base)
    else:
        target = Path(path)
    if not target.exists():
        return None
    manifest = _read_vec(target)
    if manifest is None:
        return {"file": str(target), "corrupt": True, "items": [],
                "external": _is_external(target, base)}
    return {
        "file": str(target),
        "external": _is_external(target, base),
        "sealedTs": manifest["sealed_ts"],
        "fileBytes": target.stat().st_size,
        "totalBytes": sum(i.get("sizeBytes", 0) for i in manifest["items"]),
        "items": manifest["items"],
    }
```

- [ ] **Step 4: GREEN** — `python -m pytest tests/test_quarantine.py -q`.
- [ ] **Step 5: Commit** — `git add src/vector/quarantine.py tests/test_quarantine.py && git commit -m "feat(engine): quarentena .vec - stage e seal auto-contidos (so a ultima execucao)"`

---

### Task 3: `quarantine.py` — restore_one + export + purge

**Files:**
- Modify: `src/vector/quarantine.py` (acrescentar após `inspect`)
- Modify: `tests/test_quarantine.py` (acrescentar)

- [ ] **Step 1: Testes que falham** — acrescentar a `tests/test_quarantine.py`:

```python
def test_restore_one_active_moves_back_and_shrinks(tmp_path, folder):
    base = tmp_path / "q"
    d1, d2 = folder("Um"), folder("Dois")
    quarantine.stage(_cand(d1, label="Um"), base=base)
    quarantine.stage(_cand(d2, label="Dois"), base=base)
    info = quarantine.seal(base=base)
    first = next(i for i in info["items"] if i["label"] == "Um")
    ok, detail = quarantine.restore_one(first["id"], base=base)
    assert ok and (tmp_path / "src" / "Um" / "a.txt").exists()
    left = quarantine.inspect(base=base)
    assert [i["label"] for i in left["items"]] == ["Dois"]


def test_restore_all_items_removes_vec(tmp_path, folder):
    base = tmp_path / "q"
    d = folder("Só")
    entry, _ = quarantine.stage(_cand(d), base=base)
    quarantine.seal(base=base)
    ok, _ = quarantine.restore_one(entry["id"], base=base)
    assert ok and not (base / "last.vec").exists()
    assert quarantine.inspect(base=base) is None


def test_restore_one_skips_when_destination_exists(tmp_path, folder):
    base = tmp_path / "q"
    d = folder("Volta")
    entry, _ = quarantine.stage(_cand(d), base=base)
    quarantine.seal(base=base)
    d.mkdir(parents=True, exist_ok=True)          # alguem recriou a origem
    ok, err = quarantine.restore_one(entry["id"], base=base)
    assert not ok and "já existe" in err
    # nada enxugado: o item continua no backup
    assert len(quarantine.inspect(base=base)["items"]) == 1


def test_restore_external_copies_and_preserves(tmp_path, folder):
    base = tmp_path / "q"
    quarantine.stage(_cand(folder("X")), base=base)
    quarantine.seal(base=base)
    copy = tmp_path / "copia.vec"
    shutil.copyfile(base / "last.vec", copy)
    item = quarantine.inspect(path=copy, base=base)["items"][0]
    ok, original = quarantine.restore_one(item["id"], path=copy, base=base)
    assert ok and Path(original).exists()
    assert len(quarantine.inspect(path=copy, base=base)["items"]) == 1  # intacto


def test_restore_unknown_id(tmp_path, folder):
    base = tmp_path / "q"
    quarantine.stage(_cand(folder("Y")), base=base)
    quarantine.seal(base=base)
    ok, err = quarantine.restore_one("nao-existe", base=base)
    assert not ok and "nao esta neste backup" in err


def test_export_copies_active(tmp_path, folder):
    base = tmp_path / "q"
    quarantine.stage(_cand(folder("Z")), base=base)
    quarantine.seal(base=base)
    dest = tmp_path / "out" / "meu-backup.vec"
    ok, detail = quarantine.export(dest, base=base)
    assert ok and dest.exists() and detail == str(dest)
    assert (base / "last.vec").exists()           # original preservado


def test_purge_deletes_active(tmp_path, folder):
    base = tmp_path / "q"
    quarantine.stage(_cand(folder("W")), base=base)
    quarantine.seal(base=base)
    assert quarantine.purge(base=base) is True
    assert not (base / "last.vec").exists()
    assert quarantine.purge(base=base) is False   # idempotente
```

Adicione no topo do arquivo de teste: `import shutil` e `from pathlib import Path`.

- [ ] **Step 2: FAIL** (NameError nas funções novas).
- [ ] **Step 3: Implementar** — acrescentar a `src/vector/quarantine.py`:

```python
def _rewrite_without(target: Path, drop_id: str, sealed_ts: int) -> None:
    """Reescreve o .vec sem as entradas de drop_id; apaga o arquivo se esvaziou."""
    with zipfile.ZipFile(target) as zf:
        manifest = json.loads(zf.read(MANIFEST_NAME))
    items = [i for i in manifest["items"] if i["id"] != drop_id]
    if not items:
        target.unlink(missing_ok=True)
        return
    tmp = target.with_name(target.name + ".tmp")
    prefix = drop_id + "/"
    with zipfile.ZipFile(target) as src, \
            zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            if name == MANIFEST_NAME or name.startswith(prefix):
                continue
            dst.writestr(name, src.read(name))
        dst.writestr(MANIFEST_NAME, _entry_json(
            {"sealed_ts": sealed_ts, "items": items}))
    target.unlink()
    tmp.replace(target)


def restore_one(entry_id: str, path: Optional[Path] = None,
                base: Optional[Path] = None) -> tuple[bool, str]:
    """Restaura UMA pasta do .vec. Ativo (path=None): move de volta e enxuga a
    entrada. Externo: copia e o backup permanece intacto (e um backup, nao
    uma lixeira). (ok, caminho_original | motivo)."""
    target = Path(path) if path else active_path(base)
    active = path is None
    if not target.exists():
        return False, "o backup nao existe mais."
    manifest = _read_vec(target)
    if manifest is None:
        return False, "arquivo de backup corrompido ou ilegível."
    entry = next((i for i in manifest["items"] if i["id"] == entry_id), None)
    if entry is None:
        return False, f"item {entry_id} nao esta neste backup."
    original = Path(entry["original"])
    if original.exists():
        return False, f"já existe algo em {original}; nada foi restaurado."
    prefix = f"{entry_id}/{entry['archived']}"
    try:
        with zipfile.ZipFile(target) as zf:
            names = [n for n in zf.namelist() if n.startswith(prefix)]
            original.mkdir(parents=True, exist_ok=True)
            for name in names:
                rel = name[len(prefix):].lstrip("/")
                if not rel:
                    continue  # entrada de diretorio raiz, ja criada
                dest = original / Path(*PurePosixPath(rel).parts)
                if name.endswith("/"):
                    dest.mkdir(parents=True, exist_ok=True)
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src_f, open(dest, "wb") as out_f:
                    shutil.copyfileobj(src_f, out_f)
    except OSError as exc:
        return False, f"falha ao restaurar: {exc}"
    if active:
        _rewrite_without(target, entry_id, manifest.get("sealed_ts", 0))
    return True, str(original)


def export(dest: Path, path: Optional[Path] = None,
           base: Optional[Path] = None) -> tuple[bool, str]:
    """Copia o backup (ativo por omissao) para dest, sem esvaziar nada."""
    src = Path(path) if path else active_path(base)
    if not src.exists():
        return False, "nao ha backup ativo para copiar."
    dest = Path(dest)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    except OSError as exc:
        return False, f"falha ao copiar o backup: {exc}"
    return True, str(dest)


def purge(base: Optional[Path] = None) -> bool:
    """Apaga o backup ATIVO (hard delete - unico ponto sem volta da GUI)."""
    target = active_path(base)
    existed = target.exists()
    target.unlink(missing_ok=True)
    shutil.rmtree(root(base) / _STAGING, ignore_errors=True)
    return existed
```

- [ ] **Step 4: GREEN** — `python -m pytest tests/test_quarantine.py -q` (Task 2+3 juntos).
- [ ] **Step 5: Commit** — `git commit -am "feat(engine): quarentena .vec - restore/export/purge com semantica ativo-vs-externo"`

---

### Task 4: Bridge — `remove` quarentena + comandos de backup

**Files:**
- Modify: `src/vector/bridge.py`
- Modify: `tests/test_bridge.py` (remove_fn → stage_fn; novos testes)

- [ ] **Step 1: Ajustar testes existentes + escrever novos (FAIL)**

Em `tests/test_bridge.py`: onde hoje se injeta `remove_fn=lambda p: (True, "ok")`, trocar para `stage_fn=lambda cand: ({"id": "abc", "sizeBytes": 10}, "")` (assinatura recebe o CANDIDATO, devolve `(entrada|None, motivo)`). Teste de falha de remoção passa a injetar `stage_fn=lambda cand: (None, "sem permissao")` e espera `removed=False, detail="sem permissao"`. Acrescentar:

```python
def test_remove_result_marks_quarantined(state, fake_stage):
    _scan(state, scan_fn=fake_scan_with_cleanable_folder)
    resp = handle_request({"id": 9, "cmd": "remove", "path": CLEANABLE_PATH},
                          state, stage_fn=fake_stage)
    assert resp["ok"] and resp["result"]["quarantined"] is True
    assert resp["result"]["id"] == "abc"


def test_quarantine_inspect_seals_orphans(tmp_path):
    state = BridgeState(base=tmp_path)
    resp = handle_request({"id": 10, "cmd": "quarantine-inspect"}, state)
    assert resp["ok"] and resp["result"]["items"] == []  # vazio, sem arquivo


def test_quarantine_flow_stage_seal_restore_purge(tmp_path, folder_setup):
    # folder_setup: cria pasta real em tmp_path e candidata HIGH no report
    state = BridgeState(base=tmp_path, report=report_with([cleanable_folder]))
    r = handle_request({"id": 11, "cmd": "remove", "path": cleanable_folder.path}, state)
    assert r["result"]["removed"] and r["result"]["quarantined"]
    r = handle_request({"id": 12, "cmd": "quarantine-seal"}, state)
    assert r["ok"] and r["result"]["sealedTs"]
    r = handle_request({"id": 13, "cmd": "quarantine-inspect"}, state)
    item = r["result"]["items"][0]
    r = handle_request({"id": 14, "cmd": "quarantine-restore", "id": item["id"]}, state)
    assert r["result"]["restored"] is True
    r = handle_request({"id": 15, "cmd": "quarantine-purge"}, state)
    assert r["result"]["purged"] in (True, False)


def test_backup_inspect_and_restore_external(tmp_path, ...):
    # gera um .vec via stage+seal, copia para fora, backup-inspect{path},
    # backup-restore{path,id} -> result["copied"] is True e o arquivo externo
    # mantem o item (inspect de novo).
    ...


def test_bridge_unknown_quarantine_cmd_still_errors(state):
    resp = handle_request({"id": 16, "cmd": "quarantine-teleport"}, state)
    assert not resp["ok"]
```

Escreva as fixtures auxiliares (`folder_setup`, `report_with`) reaproveitando os builders que já existem em `test_bridge.py` (candidatos fake HIGH folder). Os `...` acima são âncoras de contexto: o executor deve materializar com os helpers existentes — o comportamento exigido está descrito nas asserts.

- [ ] **Step 2: FAIL** (BridgeState sem `base`, `stage_fn` desconhecido).

- [ ] **Step 3: Implementar** — em `src/vector/bridge.py`:

`BridgeState` ganha campo:

```python
from pathlib import Path
...
@dataclass
class BridgeState:
    report: Optional[ScanReport] = None
    base: Optional[Path] = None   # raiz da quarentena; None = LOCALAPPDATA (teste injeta tmp)
```

Trocar `_default_remove` por:

```python
def _default_stage(candidate, base=None):
    from vector import quarantine
    return quarantine.stage(candidate, base=base)
```

No `handle_request`: adicionar kwarg `stage_fn=None` (remover `remove_fn`), ramo `remove` novo e ramos de backup:

```python
    if cmd == "remove":
        path = request.get("path") or ""
        candidate, refusal = _authorize(state, path)
        if candidate is None:
            return _err(req_id, refusal)
        stage = stage_fn or _default_stage
        try:
            entry, fail = stage(candidate, base=state.base)
        except Exception as exc:  # noqa: BLE001
            return _err(req_id, f"Falha ao mover para a quarentena: {exc}")
        if entry is None:
            return _ok(req_id, {"removed": False, "quarantined": False,
                                "path": path, "detail": fail})
        return _ok(req_id, {"removed": True, "quarantined": True, "path": path,
                            "id": entry["id"], "sizeBytes": entry["sizeBytes"],
                            "detail": "movida para a quarentena"})

    if cmd in ("quarantine-seal", "quarantine-inspect", "quarantine-purge",
               "quarantine-restore", "quarantine-export",
               "backup-inspect", "backup-restore"):
        return _quarantine(req_id, cmd, request, state)
```

Handler dedicado (import tardio keeps bridge importável sem o módulo? não — import direto no topo de `vector.quarantine` é leve e stdlib):

```python
def _quarantine(req_id, cmd, request, state):
    from vector import quarantine

    path = Path(request["path"]) if request.get("path") else None
    dest = Path(request["dest"]) if request.get("dest") else None
    entry_id = request.get("id") or ""
    try:
        if cmd == "quarantine-seal":
            info = quarantine.seal(base=state.base)
            return _ok(req_id, info or {"sealedTs": None, "items": []})
        if cmd == "quarantine-inspect":
            info = quarantine.inspect(base=state.base)
            return _ok(req_id, info or {"file": None, "items": []})
        if cmd == "quarantine-restore":
            ok, detail = quarantine.restore_one(entry_id, base=state.base)
            return _ok(req_id, {"restored": ok, "moved": True, "detail": detail})
        if cmd == "quarantine-purge":
            return _ok(req_id, {"purged": quarantine.purge(base=state.base)})
        if cmd == "quarantine-export":
            if not dest:
                return _err(req_id, "falta o destino da copia.")
            ok, detail = quarantine.export(dest, base=state.base)
            return _ok(req_id, {"exported": ok, "detail": detail})
        if cmd == "backup-inspect":
            if not path:
                return _err(req_id, "falta o caminho do .vec.")
            info = quarantine.inspect(path=path, base=state.base)
            return _ok(req_id, info or {"file": None, "items": []})
        if cmd == "backup-restore":
            if not path:
                return _err(req_id, "falta o caminho do .vec.")
            ok, detail = quarantine.restore_one(entry_id, path=path, base=state.base)
            return _ok(req_id, {"restored": ok, "moved": False, "detail": detail})
    except Exception as exc:  # noqa: BLE001 - fronteira
        return _err(req_id, f"Quarentena: {exc}")
    return _err(req_id, f"Comando desconhecido: {cmd!r}")
```

`serve()`: kwarg `stage_fn` em vez de `remove_fn`, repassado a `handle_request`. Atualizar o docstring do protocolo no topo do arquivo (remove → quarentena; exemplos dos comandos novos).

- [ ] **Step 4: GREEN** — `python -m pytest tests/ -q`.
- [ ] **Step 5: Smoke do protocolo** — alimentar o serve com stdin de verdade:

```powershell
'"{\"cmd\":\"ping\"}"' | python vector-cli.py --serve   # ok:true, phase:engine
```

- [ ] **Step 6: Commit** — `git commit -am "feat(bridge): remove quarantena + comandos quarantine-*/backup-* (base injetavel p/ teste)"`

---

### Task 5: VectorHost.ps1 — registro `.vec`, `--open`, `engine-call`, diálogos, drop-temp

**Files:**
- Modify: `gui/VectorHost.ps1`

- [ ] **Step 1: Parse de `--open` + registro da associação.** Logo após o bloco que define `$Root`/`$indexPath` (antes do `Add-Type` do NativeDrag), adicionar:

```powershell
# --- arquivo .vec recebido por associsao (duplo-clique => exe --open <path>) --
$script:OpenBackup = $null
for ($i = 0; $i -lt ($args.Count - 1); $i++) {
    if ($args[$i] -eq '--open') { $script:OpenBackup = [string]$args[$i + 1] }
}

# Associa .vec ao exe em HKCU (nao exige admin; idempotente; so no exe
# empacotado - em dev o registro apontaria pra um powershell -File).
function Register-VecAssociation {
    if ($script:IsScript) { return }
    try {
        New-Item -Path 'HKCU:\Software\Classes\.vec' -Force | Out-Null
        Set-ItemProperty -Path 'HKCU:\Software\Classes\.vec' -Name '(default)' -Value 'Vector.Backup'
        New-Item -Path 'HKCU:\Software\Classes\Vector.Backup' -Force | Out-Null
        Set-ItemProperty -Path 'HKCU:\Software\Classes\Vector.Backup' -Name '(default)' -Value 'Backup do Vector'
        New-Item -Path 'HKCU:\Software\Classes\Vector.Backup\shell\open\command' -Force | Out-Null
        Set-ItemProperty -Path 'HKCU:\Software\Classes\Vector.Backup\shell\open\command' `
            -Name '(default)' -Value "`"$exeFullPath`" --open `"%1`""
    } catch { }   # associacao e conforto, nunca motivo de falha no boot
}
Register-VecAssociation
```

- [ ] **Step 2: Entregar `open-backup` ao JS.** No handler `ready` de `Handle-Message`, após o `Send-ToJs host-ready`:

```powershell
            if ($script:OpenBackup) {
                Send-ToJs -Type 'open-backup' -Payload @{ path = $script:OpenBackup }
                $script:OpenBackup = $null
            }
```

- [ ] **Step 3: Handler genérico `engine-call` + diálogos.** Adicionar casos no `switch ($Msg.type)` (antes do `default`):

```powershell
        'engine-call' {
            # Passa-thru para os comandos de quarentena/backup do motor. A
            # whitelist existe so pra host nenhum virar canonicalizador de
            # cmd arbitrario; 'scan'/'remove' continuam pelos handlers
            # dedicados acima (mesmo gateway de seguranca do motor).
            $allowed = @('quarantine-inspect', 'quarantine-seal',
                         'quarantine-restore', 'quarantine-purge',
                         'quarantine-export', 'backup-inspect', 'backup-restore')
            $cmd = [string]$Msg.payload.cmd
            if ($allowed -notcontains $cmd) {
                Send-ToJs -Type 'engine-reply' -Payload @{
                    cmd = $cmd; ok = $false; error = "comando nao permitido: $cmd" }
                return
            }
            $req = @{ cmd = $cmd }
            foreach ($k in @('id', 'path', 'dest')) {
                if ($Msg.payload.$k) { $req[$k] = [string]$Msg.payload.$k }
            }
            try {
                $resp = Invoke-Engine -Request $req
                Send-ToJs -Type 'engine-reply' -Payload @{
                    cmd = $cmd; ok = [bool]$resp.ok
                    result = $resp.result; error = $resp.error }
            } catch {
                Send-ToJs -Type 'engine-reply' -Payload @{
                    cmd = $cmd; ok = $false; error = $_.Exception.Message }
            }
        }
        'pick-backup' {
            $dlg = New-Object System.Windows.Forms.OpenFileDialog
            $dlg.Filter = 'Backup do Vector (*.vec)|*.vec|Todos os arquivos (*.*)|*.*'
            $dlg.Title = 'Selecionar backup .vec'
            $res = $dlg.ShowDialog($form)
            $picked = if ($res -eq [System.Windows.Forms.DialogResult]::OK) { $dlg.FileName } else { $null }
            Send-ToJs -Type 'backup-picked' -Payload @{ path = $picked }
        }
        'export-backup' {
            $dlg = New-Object System.Windows.Forms.SaveFileDialog
            $dlg.Filter = 'Backup do Vector (*.vec)|*.vec'
            $dlg.FileName = 'vector-backup.vec'
            $dlg.Title = 'Salvar copia do backup'
            $res = $dlg.ShowDialog($form)
            if ($res -ne [System.Windows.Forms.DialogResult]::OK) {
                Send-ToJs -Type 'backup-exported' -Payload @{ ok = $false; detail = 'cancelado' }
                return
            }
            try {
                $resp = Invoke-Engine -Request @{ cmd = 'quarantine-export'; dest = $dlg.FileName }
                Send-ToJs -Type 'backup-exported' -Payload @{
                    ok = [bool]$resp.ok; detail = $(if ($resp.ok) { $resp.result.detail } else { $resp.error }) }
            } catch {
                Send-ToJs -Type 'backup-exported' -Payload @{ ok = $false; error = $_.Exception.Message }
            }
        }
        'drop-temp' {
            # Fallback do drag&drop sem File.path (limite de 20 MB travado na GUI):
            # materializa o conteudo recebido em %TEMP% e devolve o caminho.
            try {
                $bytes = [Convert]::FromBase64String([string]$Msg.payload.b64)
                $tmp = Join-Path ([System.IO.Path]::GetTempPath()) (
                    'vector-drop-' + [guid]::NewGuid().ToString('N') + '.vec')
                [System.IO.File]::WriteAllBytes($tmp, $bytes)
                Send-ToJs -Type 'backup-picked' -Payload @{ path = $tmp }
            } catch {
                Send-ToJs -Type 'backup-picked' -Payload @{ path = $null; error = $_.Exception.Message }
            }
        }
```

- [ ] **Step 4: Atualizar o docstring do protocolo** (lista JS→PS ganha `engine-call | pick-backup | export-backup | drop-temp`; PS→JS ganha `engine-reply | backup-picked | backup-exported | open-backup`).
- [ ] **Step 5: Verificar parse**:

```powershell
$errs = $null; [System.Management.Automation.Language.Parser]::ParseFile("$PWD\gui\VectorHost.ps1", [ref]$null, [ref]$errs) | Out-Null; $errs
```
Esperado: saída vazia.
- [ ] **Step 6: Commit** — `git add gui/VectorHost.ps1; git commit -m "feat(host): engine-call, dialog nativos, drop-temp e associacao .vec (HKCU)"`

---

### Task 6: GUI — máquina de estados nova (review / plan / executing / done)

**Files:**
- Modify: `gui/vector/app.js` (reestruturação das telas de limpeza)
- Modify: `gui/vector/mock.js` (campo `summaryPlain` nos candidatos)

**Ancoragem (estado atual de app.js):** telas `welcome|scan|evidence|clean|done`
(`renderEvidence` L288, bloco clean L344–543, `onBridgeMessage` L553). O bloco
`/* ---------------- tela: evidence ---------------- */` até o fim de
`applyRemoveResult` é SUBSTITUÍDO pelo código abaixo; `renderWelcome`,
`renderScanSetup`, `renderScanning`, `runScan`, `metaLine`, `evidenceCard`
(reusado dentro de `<details>`), `filteredCandidates`, `feedLine`(adaptado),
`updatePhaseBadge` e os listeners de titlebar permanecem com ajustes mínimos.

- [ ] **Step 1: STEPS + state + render() + go()**

Substituir a constante `STEPS` por:

```js
const STEPS = [
  { id: "welcome", label: "Início" },
  { id: "scan", label: "Varredura" },
  { id: "review", label: "Revisão" },
  { id: "plan", label: "Plano" },
  { id: "executing", label: "Execução" },
  { id: "done", label: "Concluído" },
];
```

Substituir o objeto `state` por:

```js
const state = {
  step: "welcome",
  doneSteps: [],
  target: "",
  minConfidence: "LOW",
  verbose: false,
  report: null,          // ultimo ScanReport (payload camelCase do motor ou mock)
  selected: {},          // path -> true (o que vai para o lote)
  exec: null,            // { queue, i, ok, fail, lines, running, sealed, simulation }
  engineAvailable: false,
  phase: "mock",
  scanning: false,
  scanError: "",
  // Backup/quarentena (Task 7):
  utility: null,         // null | "quarantine" | "restore"
  backup: null,          // resultado de inspect: {file, external, sealedTs, items, fileBytes}
  backupSel: {},         // id -> true nas telas de restauracao
  replyIntent: null,     // roteia 'engine-reply' de inspect: 'picker' | 'quarantine' | 'restore'
};
```

Substituir `render()` por:

```js
function render() {
  renderSidebar();
  const screens = {
    welcome: renderWelcome,
    scan: renderScanSetup,
    review: renderReview,
    plan: renderPlan,
    executing: renderExecuting,
    done: renderDone,
    quarantine: renderQuarantine,   // Task 7
    restore: renderRestore,         // Task 7
  };
  const host = $("#content");
  host.innerHTML = "";
  if (state.scanning) { renderScanning(host); renderNav(); return; }
  (screens[state.utility || state.step] || renderWelcome)(host);
  renderNav();
}
```

Em `go()`, deletar as duas linhas `state.awaitingConfirm = false;` e
`state.awaitingHost = false;` (campos morreram).

- [ ] **Step 2: Helpers de seleção e seções de risco**

```js
/* ---------------- lote: secoes de risco e selecao ---------------- */

function fmtBytes(n) {
  if (!n || n <= 0) return "tamanho n/d";
  const units = ["B", "KB", "MB", "GB"];
  let v = n, u = 0;
  while (v >= 1024 && u < 3) { v /= 1024; u++; }
  return v.toFixed(1) + " " + units[u];
}

function reviewSections() {
  const items = filteredCandidates();
  const folders = items.filter(function (c) { return c.kind === "folder"; });
  const low = folders.filter(function (c) { return c.confidence === "LOW"; });
  const cleanFolders = folders.filter(function (c) { return c.confidence !== "LOW"; });
  return [
    { id: "high", title: "Quase certamente sobra de programa desinstalado",
      sub: "Não aparecem na lista de programas do Windows. Pode marcar o grupo inteiro com confiança.",
      items: cleanFolders.filter(function (c) { return c.confidence === "HIGH" && !c.sensitive; }),
      groupable: true },
    { id: "med", title: "Provável sobra — vale conferir",
      sub: "Boas chances de ser resíduo, mas a evidência é mais fraca. Marcável em grupo.",
      items: cleanFolders.filter(function (c) { return c.confidence === "MEDIUM" && !c.sensitive; }),
      groupable: true },
    { id: "sens", title: "Pasta com dados seus",
      sub: "Configurações, conversas, saves. Fora do “marcar todos” — marque item a item, sabendo o que faz.",
      items: cleanFolders.filter(function (c) { return c.sensitive; }),
      groupable: false },
    { id: "low", title: "Confiança baixa — o Vector não oferece para remover",
      sub: "Há indícios fracos demais para uma limpeza segura; nada aqui entra no lote.",
      items: low, readonly: true },
    { id: "man", title: "O Vector não apaga — veja o passo a passo",
      sub: "Registro, serviços e tarefas: o comando sugerido abaixo resolve com segurança.",
      items: items.filter(function (c) { return c.kind !== "folder"; }),
      readonly: true },
  ].filter(function (s) { return s.items.length > 0; });
}

// Pre-selecao padrao da spec: HIGH nao-sensive marcado; MEDIUM/sensive livres.
function preselect(items) {
  const sel = {};
  items.forEach(function (c) {
    if (c.kind === "folder" && !c.sensitive && c.confidence === "HIGH") sel[c.path] = true;
  });
  return sel;
}

function selectedCandidates() {
  if (!state.report) return [];
  return state.report.candidates.filter(function (c) { return state.selected[c.path]; });
}

function selectedBytes() {
  return selectedCandidates().reduce(function (s, c) { return s + (c.sizeBytes || 0); }, 0);
}
```

- [ ] **Step 3: runScan/onBridgeMessage — pós-scan cai em review com pre-seleção**

Em `runScan()`, trocar a linha final `go("evidence");` (fallback mock) por:

```js
  state.selected = preselect(state.report.candidates);
  go("review");
```

Em `onBridgeMessage`: nos ramos `scan-result` e `scan-error`, trocar
`go("evidence")` por, respectivamente:

```js
    state.selected = preselect(p.candidates || []);
    go("review");
```

```js
    go("review");   // renderReview mostra o estado de erro quando !state.report
```

Acrescentar ANTES do comentário final de `onBridgeMessage` (e criar a função):

```js
  if (msg.type === "engine-reply") { onEngineReply(p); return; }
```

```js
function engineCall(cmd, args) {
  const req = Object.assign({ cmd: cmd }, args || {});
  sendToHost("engine-call", req);
}
```

(`onEngineReply` chega completo na Task 7 — nesta task, declare um stub
`function onEngineReply() {}` no fim do arquivo para não quebrar o boot.)

- [ ] **Step 4: SUBSTITUIR o bloco `tela: evidence` + `tela: clean` inteiros
  (L286–543) pelas telas novas**

```js
/* ---------------- tela: review ---------------- */

function renderReview(root) {
  const el = document.createElement("div");
  el.className = "screen screen-wide";

  if (!state.report) {
    el.innerHTML =
      '<h1 class="screen-title">Rev<span class="hl">isão</span></h1>' +
      '<div class="ev-empty ev-error">[!] A varredura falhou no motor.' +
      (state.scanError ? "<br/>" + escapeHtml(state.scanError) : "") +
      "<br/>Volte e tente de novo, ou verifique se o Vector roda como admin.</div>";
    root.appendChild(el);
    setStatus("varredura com erro · nada foi movido");
    return;
  }

  const sections = reviewSections();
  el.innerHTML =
    '<h1 class="screen-title">Rev<span class="hl">isão</span> — o que vai, o que fica</h1>' +
    '<p class="screen-lede">' + state.report.installedCount + " programas instalados · " +
    filteredCandidates().length + " candidato(s). Nada é apagado agora: o que você marcar " +
    "será <b>movido para a quarentena</b> e poderá voltar de lá.</p>";

  sections.forEach(function (s) {
    const sec = document.createElement("div");
    sec.className = "bk-section";
    const groupCheck = s.groupable
      ? '<input type="checkbox" class="bk-check bk-group-check" data-group="' + s.id + '"' +
        (s.items.length && s.items.every(function (c) { return state.selected[c.path]; }) ? " checked" : "") +
        ' title="marcar o grupo inteiro" />'
      : "";
    sec.innerHTML =
      '<div class="bk-group-head">' + groupCheck +
      '<span class="bk-group-title">' + escapeHtml(s.title) + "</span>" +
      '<span class="ev-count">' + s.items.length + "</span></div>" +
      '<p class="bk-group-sub">' + escapeHtml(s.sub) + "</p>" +
      s.items.map(function (c) { return reviewRow(c, s.groupable || s.id === "sens"); }).join("");
    el.appendChild(sec);
  });

  const foot = document.createElement("div");
  foot.className = "bk-foot";
  el.appendChild(foot);
  root.appendChild(el);
  wireReview(el);
  updateReviewFoot();
  setStatus("revisão · marque os grupos que conhece");
}

function reviewRow(c, selectable) {
  return '<label class="bk-row' + (selectable ? "" : " is-locked") + '">' +
    (selectable
      ? '<input type="checkbox" class="bk-check bk-item-check" data-path="' +
        escapeHtml(c.path) + '"' + (state.selected[c.path] ? " checked" : "") + " />"
      : '<span class="bk-lock">' + (KIND_LABEL[c.kind] || c.kind) + "</span>") +
    '<span class="bk-main">' +
    '<span class="bk-name">' + escapeHtml(c.label) + "</span>" +
    '<span class="bk-path">' + escapeHtml(c.path) + "</span>" +
    '<span class="bk-why">' + escapeHtml(c.summaryPlain || "") + " · " +
    escapeHtml(metaLine(c)) + "</span></span></label>" +
    '<details class="bk-tech"><summary>detalhes técnicos</summary>' +
    evidenceInner(c) + "</details>";
}

// miolo de evidencias reaproveitado do antigo evidenceCard, agora so o interior
function evidenceInner(c) {
  const rows = c.evidences.map(function (e) {
    return '<div class="ev-row"><span class="ev-weight">+' + e.weight + "</span><span>" +
      escapeHtml(e.description.replace(/^\+\d+\s*/, "")) + "</span>" +
      (state.verbose ? '<span class="ev-src">' + escapeHtml(e.source) + "</span>" : "") +
      "</div>";
  }).join("");
  return '<div class="ev-score">score <strong>' + c.score + "</strong> · " +
    c.confidence + "</div>" + rows +
    (c.manualCommand
      ? '<div class="ev-manual"><span>manual — o Vector nunca remove sozinho:</span><br/>' +
        escapeHtml(c.manualCommand) + "</div>"
      : "");
}

function wireReview(el) {
  el.querySelectorAll(".bk-item-check").forEach(function (chk) {
    chk.addEventListener("change", function () {
      if (chk.checked) state.selected[chk.dataset.path] = true;
      else delete state.selected[chk.dataset.path];
      updateReviewFoot();
      syncGroupChecks(el);
    });
  });
  el.querySelectorAll(".bk-group-check").forEach(function (chk) {
    chk.addEventListener("change", function () {
      const s = reviewSections().filter(function (x) { return x.id === chk.dataset.group; })[0];
      if (!s) return;
      s.items.forEach(function (c) {
        if (chk.checked) state.selected[c.path] = true;
        else delete state.selected[c.path];
      });
      render();
    });
  });
}

function syncGroupChecks(el) {
  el.querySelectorAll(".bk-group-check").forEach(function (chk) {
    const s = reviewSections().filter(function (x) { return x.id === chk.dataset.group; })[0];
    chk.checked = !!(s && s.items.length && s.items.every(function (c) { return state.selected[c.path]; }));
  });
}

function updateReviewFoot() {
  const foot = document.querySelector(".bk-foot");
  if (!foot) return;
  const n = Object.keys(state.selected).length;
  foot.innerHTML =
    '<button class="btn btn-ghost" id="btn-all">Marcar todos (exceto sensíveis)</button>' +
    '<span class="bk-tally">' + n + " selecionado(s) · ~" + fmtBytes(selectedBytes()) + "</span>" +
    '<button class="btn btn-primary" id="btn-to-plan"' + (n ? "" : " disabled") + ">Revisar plano →</button>";
  foot.querySelector("#btn-all").onclick = function () {
    reviewSections().forEach(function (s) {
      if (s.groupable) s.items.forEach(function (c) { state.selected[c.path] = true; });
    });
    render();
  };
  const tp = foot.querySelector("#btn-to-plan");
  if (tp) tp.onclick = function () { go("plan"); };
}

/* ---------------- tela: plan ---------------- */

function renderPlan(root) {
  const chosen = selectedCandidates();
  const el = document.createElement("div");
  el.className = "screen";
  el.innerHTML =
    '<h1 class="screen-title">Pla<span class="hl">no</span> de limpeza</h1>' +
    '<p class="screen-lede">Uma confirmação única executa o lote inteiro.</p>' +
    '<div class="panel"><h2 class="panel-title">' + chosen.length + " item(ns) — ~" +
    fmtBytes(selectedBytes()) + "</h2>" +
    '<ul class="bk-plan">' + chosen.map(function (c) {
      return "<li><b>" + escapeHtml(c.label) + "</b><br/><span class=\"bk-path\">" +
        escapeHtml(c.path) + "</span></li>";
    }).join("") + "</ul></div>" +
    '<div class="panel"><h2 class="panel-title">Para onde vai</h2>' +
    '<p class="panel-sub">Nada é apagado. As pastas serão <b>movidas para a quarentena</b> ' +
    "do Vector — um arquivo <code>.vec</code> compactado com só a última execução. " +
    "Você pode restaurar tudo pela própria interface, ou abrir o arquivo no futuro.</p></div>" +
    '<div class="bk-actions"><button class="btn btn-ghost" id="btn-back-review">← Ajustar seleção</button>' +
    '<button class="btn btn-primary" id="btn-exec">Mover ' + chosen.length +
    " itens para a quarentena" +
    (state.engineAvailable ? "" : " (simulação — motor indisponível)") + "</button></div>";
  root.appendChild(el);
  $("#btn-back-review").onclick = function () { go("review"); };
  $("#btn-exec").onclick = startExecution;
  setStatus("plano pronto · confirme uma única vez");
}

/* ---------------- tela: executing ---------------- */

function startExecution() {
  const queue = selectedCandidates();
  state.exec = { queue: queue, i: 0, ok: 0, fail: 0, lines: [],
                 running: true, sealed: null, simulation: !state.engineAvailable };
  go("executing");
  pumpExecution();
}

function pumpExecution() {
  const ex = state.exec;
  if (!ex) return;
  if (ex.i >= ex.queue.length) {
    ex.running = false;
    if (!ex.simulation) { engineCall("quarantine-seal"); return; }
    go("done");
    return;
  }
  const c = ex.queue[ex.i];
  if (ex.simulation) {
    ex.ok++; ex.lines.push({ kind: "ok", text: c.path });
    ex.i++;
    renderExecutingInPlace();
    setTimeout(pumpExecution, 120);
    return;
  }
  renderExecutingInPlace();
  sendToHost("remove-folder", { path: c.path });
}

function applyRemoveResult(p) {
  const ex = state.exec;
  if (!ex) return;
  if (p.removed) { ex.ok++; ex.lines.push({ kind: "ok", text: p.path }); }
  else { ex.fail++; ex.lines.push({ kind: "fail", text: p.path + " — " + (p.detail || "") }); }
  ex.i++;
  pumpExecution();
}

function renderExecutingInPlace() {
  const host = $("#content");
  host.innerHTML = "";
  renderExecuting(host);
}

function renderExecuting(root) {
  const ex = state.exec || { queue: [], i: 0, ok: 0, fail: 0, lines: [] };
  const el = document.createElement("div");
  el.className = "screen";
  el.innerHTML =
    '<h1 class="screen-title">Exe<span class="hl">cutando</span></h1>' +
    '<p class="screen-lede">' + ex.i + " de " + ex.queue.length +
    (ex.simulation ? " · simulação com dados de exemplo" : " · movendo para a quarentena") + "</p>" +
    '<div class="feed" id="feed">' + ex.lines.map(function (l) {
      return '<div class="feed-line feed-' + l.kind + '">' +
        (l.kind === "ok" ? "✓ " : "✗ ") + escapeHtml(l.text) + "</div>";
    }).join("") + "</div>";
  root.appendChild(el);
  const feed = $("#feed");
  if (feed) feed.scrollTop = feed.scrollHeight;
  setStatus("execução em andamento · não feche a janela");
}

/* ---------------- tela: done ---------------- */

function renderDone(root) {
  const ex = state.exec || { ok: 0, fail: 0, simulation: true, sealed: null };
  const el = document.createElement("div");
  el.className = "screen";
  el.innerHTML =
    '<h1 class="screen-title">Limpeza <span class="hl">concluída</span></h1>' +
    '<p class="screen-lede">' + ex.ok + " item(ns) na quarentena" +
    (ex.fail ? ", " + ex.fail + " falhou(ram) — veja o relatório acima" : "") + ".</p>" +
    '<div class="panel"><h2 class="panel-title">Seu backup</h2><p class="panel-sub">' +
    (ex.simulation
      ? "Modo exemplo: nenhuma pasta real foi tocada."
      : "Guardado como <code>.vec</code> compactado (só a última execução). " +
        "Restaura pela interface a qualquer momento.") +
    "</p></div>" +
    '<div class="bk-actions">' +
    (ex.simulation ? "" :
      '<button class="btn btn-ghost" id="btn-open-q">Abrir quarentena</button>' +
      '<button class="btn btn-ghost" id="btn-export">Salvar cópia do backup…</button>') +
    '<button class="btn btn-primary" id="btn-again">Nova varredura</button></div>';
  root.appendChild(el);
  if (!ex.simulation) {
    $("#btn-open-q").onclick = openQuarantine;                 // Task 7
    $("#btn-export").onclick = function () { sendToHost("export-backup", {}); };
  }
  $("#btn-again").onclick = resetWizard;
  setStatus("concluído · nada foi apagado de verdade");
}

function resetWizard() {
  state.report = null;
  state.selected = {};
  state.exec = null;
  state.utility = null;
  state.backup = null;
  state.backupSel = {};
  state.doneSteps = [];
  go("welcome");
}
```

- [ ] **Step 5: renderNav() novo (passos próprios nos rodapés das telas)**

```js
function renderNav() {
  const order = STEPS.map(function (s) { return s.id; });
  const idx = order.indexOf(state.step);
  const back = $("#btn-back");
  const next = $("#btn-next");
  const busy = state.exec && state.exec.running;
  const inPlanLike = state.step === "plan" || state.step === "executing" ||
                     state.step === "done" || !!state.utility;
  if (busy || inPlanLike) {
    back.style.display = "none";
    next.style.display = "none";
    return;
  }
  back.style.display = "";
  next.style.display = "";
  back.disabled = idx === 0;
  const labels = { welcome: "Iniciar varredura", scan: "Revisar seleção", review: "Revisar plano →" };
  next.textContent = labels[state.step] || "Avançar";
  back.onclick = function () { if (idx > 0) go(order[idx - 1]); };
  next.onclick = function () {
    if (state.step === "welcome") runScan();
    else if (state.step === "scan") go(state.report ? "review" : "scan");
    else if (state.step === "review") go("plan");
  };
}
```

- [ ] **Step 6: mock.js — acrescentar `summaryPlain`** em cada um dos 8
  candidatos de `VECTOR_MOCK` (uma frase cada, ex.: o `VS Revo Group`:
  `"não aparece na lista de programas instalados do Windows, mas ainda há pastas dele no sistema"`;
  `GameSaveBackup`: `"nome da pasta sugere dados de jogo/salvos — confira antes"`;
  itens registry/service/task: frases com "— a remoção é manual").

- [ ] **Step 7: Verificar** — `node --check gui/vector/app.js && node --check gui/vector/mock.js`.
  Abrir preview (`start gui/vector/index.html` no browser): fluxo completo
  mock welcome→scan→review→plan→executing→done com pre-seleção nos HIGH.

- [ ] **Step 8: Commit** — `git add gui/vector/app.js gui/vector/mock.js; git commit -m "feat(gui): revisao por grupos de risco, plano unico e execucao em lote"`

---

### Task 7: GUI — quarentena, restauração e modal com trava de 20 MB

**Files:**
- Modify: `gui/vector/app.js` (substitui o stub `onEngineReply` da Task 6;
  reescreve `renderSidebar`; acrescenta telas/modal)
- Modify: `gui/vector/style.css`

- [ ] **Step 1: Sidebar com grupo Utilitários** — substituir `renderSidebar`:

```js
function renderSidebar() {
  const order = STEPS.map(function (s) { return s.id; });
  const currentIdx = state.utility ? -1 : order.indexOf(state.step);
  const item = function (id, label, i) {
    const cls = (i >= 0 && (i < currentIdx || state.doneSteps.indexOf(id) >= 0)) ? " is-done"
      : (i === currentIdx || state.utility === id) ? " is-current"
      : (i > currentIdx && currentIdx >= 0) ? " is-locked" : "";
    return '<div class="side-item' + cls + '" data-step="' + id + '"><span class="dot"></span><span>' +
      label + "</span></div>";
  };
  $("#sidebar").innerHTML =
    '<div class="side-group"><div class="side-group-title">Vector</div>' +
    STEPS.map(function (s, i) { return item(s.id, s.label, i); }).join("") + "</div>" +
    '<div class="side-group"><div class="side-group-title">Backup</div>' +
    '<div class="side-item' + (state.utility === "quarantine" ? " is-current" : "") +
    '" data-util="quarantine"><span class="dot"></span><span>Quarentena</span></div>' +
    '<div class="side-item" data-util="pick"><span class="dot"></span><span>Restaurar backup…</span></div>' +
    "</div>";
}
```

Wiring único no boot (junto dos listeners da titlebar, pois `#sidebar` é
reescrito a cada render):

```js
$("#sidebar").addEventListener("click", function (e) {
  const util = e.target.closest("[data-util]");
  if (util) {
    if (util.dataset.util === "quarantine") openQuarantine();
    else openBackupPicker();
    return;
  }
  const st = e.target.closest("[data-step]");
  if (st && (state.utility || st.dataset.step !== state.step)) {
    state.utility = null;
    go(st.dataset.step);
  }
});
```

- [ ] **Step 2: Roteamento `engine-reply`** — substituir o stub por:

```js
function onEngineReply(p) {
  const r = p.result || {};
  if (p.cmd === "quarantine-seal") {
    if (state.exec) state.exec.sealed = r;
    go("done");
    return;
  }
  if (p.cmd === "quarantine-inspect" || p.cmd === "backup-inspect") {
    state.backup = r.file ? r : null;
    state.backupSel = {};
    if (r.corrupt) {
      showNotice("Este arquivo não é um backup do Vector válido (ou está corrompido).", null);
      state.replyIntent = null;
      render();
      return;
    }
    if (state.replyIntent === "picker") {
      state.replyIntent = null;
      showPicker(state.backup);       // modal decide o proximo passo
      return;
    }
    if (state.replyIntent === "restore") state.utility = "restore";
    else if (state.replyIntent === "quarantine") state.utility = "quarantine";
    state.replyIntent = null;
    render();
    return;
  }
  if (p.cmd === "quarantine-restore" || p.cmd === "backup-restore") {
    advanceRestore(p.ok ? r : { restored: false, detail: p.error });
    return;
  }
  if (p.cmd === "quarantine-purge") {
    state.backup = null;
    render();
    return;
  }
}
```

E no `onBridgeMessage` acrescentar os dois casos restantes:

```js
  if (msg.type === "backup-picked") {
    if (p.path) inspectBackup(p.path);
    return;
  }
  if (msg.type === "open-backup") {
    inspectBackup(p.path);   // duplo-clique num .vec => cai direto na restauracao
    return;
  }
  if (msg.type === "backup-exported") {
    showNotice(p.ok ? "Cópia do backup salva em:\n" + p.detail
                    : "Não deu para salvar a cópia: " + (p.detail || p.error || "cancelado"), null);
    return;
  }
```

- [ ] **Step 3: Entradas de navegação**

```js
function inspectBackup(path) { engineCall("backup-inspect", { path: path }); }

function openQuarantine() {
  state.replyIntent = "quarantine";
  state.exec = null;
  engineCall("quarantine-inspect");
  state.utility = "quarantine";
  render();   // tela assume "carregando..." ate o engine-reply
}

function openBackupPicker() {
  state.replyIntent = "picker";
  engineCall("quarantine-inspect");   // data/tamanho no botao primario do modal
}
```

- [ ] **Step 4: Telas Quarentena e Restauração (componente compartilhado)**

```js
function renderQuarantine(root) {
  if (!state.engineAvailable) {
    root.appendChild(noticePanel("A quarentena precisa do motor real (Python). " +
      "Sem ele a interface roda com dados de exemplo."));
    return;
  }
  if (!state.backup && !state.replyIntent) {
    root.appendChild(noticePanel("Quarentena vazia — rode uma limpeza primeiro."));
    return;
  }
  if (!state.backup) { root.appendChild(noticePanel("Carregando…")); return; }
  renderBackupView(root, {
    title: "Quar<span class=\"hl\">entena</span>",
    lede: "Última execução, guardada em <code>last.vec</code>. Restaurar devolve " +
          "cada pasta ao lugar de origem e tira do backup.",
    purge: true,
  });
}

function renderRestore(root) {
  if (!state.backup) { root.appendChild(noticePanel("Selecione um arquivo de backup."); return; }
  renderBackupView(root, {
    title: "Restau<span class=\"hl\">ração</span>",
    lede: "Abrindo <code>" + escapeHtml(state.backup.file.split("\\").pop()) + "</code>. " +
      (state.backup.external
        ? "Este é um arquivo externo: restaurar <b>copia</b> as pastas de volta e o backup permanece intacto."
        : "Backup ativo: restaurar <b>move</b> de volta e enxuga o arquivo."),
    purge: false,
  });
}

function noticePanel(text) {
  const el = document.createElement("div");
  el.className = "screen";
  el.innerHTML = '<div class="panel"><p class="panel-sub">' + text + "</p></div>";
  return el;
}

function renderBackupView(root, opts) {
  const b = state.backup;
  const running = state.exec && state.exec.running;
  const el = document.createElement("div");
  el.className = "screen screen-wide";
  const done = b.sealedTs ? new Date(b.sealedTs * 1000).toLocaleString("pt-BR") : "—";
  el.innerHTML =
    '<h1 class="screen-title">' + opts.title + "</h1>" +
    '<p class="screen-lede">' + opts.lede + "</p>" +
    '<p class="bk-meta-line">' + b.items.length + " item(ns) · backup de " + done +
    " · arquivo " + fmtBytes(b.fileBytes) + "</p>";
  if (running) {
    el.innerHTML += '<div class="feed" id="feed">' + state.exec.lines.map(function (l) {
      return '<div class="feed-line feed-' + l.kind + '">' +
        (l.kind === "ok" ? "✓ " : "✗ ") + escapeHtml(l.text) + "</div>";
    }).join("") + "</div>";
  } else {
    b.items.forEach(function (it) {
      const row = document.createElement("label");
      row.className = "bk-row";
      row.innerHTML =
        '<input type="checkbox" class="bk-check" data-id="' + escapeHtml(it.id) + '"' +
        (state.backupSel[it.id] ? " checked" : "") + " />" +
        '<span class="bk-main"><span class="bk-name">' + escapeHtml(it.label) +
        ' <span class="conf conf-' + (it.confidence || "low").toLowerCase() + '">' +
        (it.confidence || "?") + "</span></span>" +
        '<span class="bk-path">' + escapeHtml(it.original) + "</span>" +
        '<span class="bk-why">' + escapeHtml(it.summaryPlain || "") + " · " +
        fmtBytes(it.sizeBytes) + "</span></span>";
      el.appendChild(row);
    });
    const foot = document.createElement("div");
    foot.className = "bk-foot";
    const n = Object.keys(state.backupSel).length;
    foot.innerHTML =
      '<button class="btn btn-ghost" id="btn-bk-all">Marcar todos</button>' +
      '<span class="bk-tally">' + n + " selecionado(s)</span>" +
      '<button class="btn btn-primary" id="btn-bk-restore"' + (n ? "" : " disabled") + ">Restaurar selecionados</button>" +
      (opts.purge ? '<button class="btn btn-danger" id="btn-bk-purge">Esvaziar quarentena…</button>' : "");
    el.appendChild(foot);
  }
  root.appendChild(el);
  if (!running) wireBackupView(el, opts);
  setStatus(running ? "restauração em andamento" : "quarentena");
}

function wireBackupView(el, opts) {
  el.querySelectorAll(".bk-check[data-id]").forEach(function (chk) {
    chk.addEventListener("change", function () {
      if (chk.checked) state.backupSel[chk.dataset.id] = true;
      else delete state.backupSel[chk.dataset.id];
      const btn = el.querySelector("#btn-bk-restore");
      if (btn) btn.disabled = !Object.keys(state.backupSel).length;
      const tally = el.querySelector(".bk-tally");
      if (tally) tally.textContent = Object.keys(state.backupSel).length + " selecionado(s)";
    });
  });
  el.querySelector("#btn-bk-all").onclick = function () {
    state.backup.items.forEach(function (it) { state.backupSel[it.id] = true; });
    render();
  };
  el.querySelector("#btn-bk-restore").onclick = startRestore;
  const purge = el.querySelector("#btn-bk-purge");
  if (purge) {
    purge.onclick = function () {
      if (purge.dataset.armed) { engineCall("quarantine-purge"); return; }
      purge.dataset.armed = "1";
      purge.textContent = "Clique de novo para APAGAR o backup";
    };
  }
}

function startRestore() {
  const ids = Object.keys(state.backupSel);
  const items = state.backup.items.filter(function (i) { return state.backupSel[i.id]; });
  state.exec = { queue: items, i: 0, ok: 0, fail: 0, lines: [], running: true,
                 external: !!state.backup.external };
  restorePump();
}

function restorePump() {
  const ex = state.exec;
  if (!ex || ex.i >= ex.queue.length) {
    if (ex) ex.running = false;
    state.backupSel = {};
    if (state.utility === "quarantine") openQuarantine();   // re-inspeciona o que sobrou
    else render();
    return;
  }
  render();
  const it = ex.queue[ex.i];
  if (state.backup && state.backup.external) engineCall("backup-restore", { path: state.backup.file, id: it.id });
  else engineCall("quarantine-restore", { id: it.id });
}

function advanceRestore(r) {
  const ex = state.exec;
  if (!ex) return;
  if (r.restored) { ex.ok++; ex.lines.push({ kind: "ok", text: r.detail }); }
  else { ex.fail++; ex.lines.push({ kind: "fail", text: (ex.queue[ex.i] || {}).original + " — " + (r.detail || "") }); }
  ex.i++;
  restorePump();
}
```

- [ ] **Step 5: Modal de seleção (dois caminhos + trava de 20 MB)**

```js
/* ---------------- overlay: picker de backup ---------------- */

function overlay() {
  let el = document.getElementById("overlay");
  if (!el) {
    el = document.createElement("div");
    el.id = "overlay";
    el.className = "modal-mask";
    document.getElementById("app").appendChild(el);
  }
  return el;
}

function closeOverlay() {
  const el = document.getElementById("overlay");
  if (el) el.remove();
}

function showNotice(text, after) {
  const el = overlay();
  el.innerHTML = '<div class="modal-card"><p class="modal-text">' +
    escapeHtml(text).replace(/\n/g, "<br/>") +
    '</p><button class="btn btn-primary" id="modal-ok">Entendi</button></div>';
  el.querySelector("#modal-ok").onclick = function () {
    closeOverlay();
    if (after) after();
  };
}

function showPicker(activeBackup) {
  const el = overlay();
  const has = !!(activeBackup && activeBackup.file);
  const when = has ? new Date(activeBackup.sealedTs * 1000).toLocaleString("pt-BR") : "";
  el.innerHTML =
    '<div class="modal-card"><h2 class="modal-title">Restaurar backup</h2>' +
    '<button class="btn btn-primary modal-big" id="modal-active"' + (has ? "" : " disabled") + ">" +
    "Último backup automático" +
    (has ? "<small>" + activeBackup.items.length + " item(ns) · " + when +
          " · " + fmtBytes(activeBackup.fileBytes) + "</small>"
        : "<small>nenhum backup ainda — rode uma limpeza primeiro</small>") +
    "</button>" +
    '<button class="btn btn-ghost" id="modal-other">Outro arquivo…</button>' +
    '<button class="btn btn-ghost" id="modal-x">Cancelar</button></div>';
  el.querySelector("#modal-active").onclick = function () {
    closeOverlay();
    state.replyIntent = "restore";
    render();   // state.backup ja veio do inspect do picker
  };
  el.querySelector("#modal-other").onclick = function () { showDropForm(); };
  el.querySelector("#modal-x").onclick = closeOverlay;
}

function showDropForm() {
  const el = overlay();
  el.innerHTML =
    '<div class="modal-card"><h2 class="modal-title">Selecionar backup .vec</h2>' +
    '<div class="dropzone" id="dz">Arraste o arquivo <b>.vec</b> aqui<br/>' +
    '<small>ou use o botão abaixo</small></div>' +
    '<button class="btn btn-primary" id="dz-pick">Selecionar arquivo…</button>' +
    '<button class="btn btn-ghost" id="dz-x">Cancelar</button></div>';
  const dz = el.querySelector("#dz");
  dz.addEventListener("dragover", function (e) { e.preventDefault(); dz.classList.add("is-over"); });
  dz.addEventListener("dragleave", function () { dz.classList.remove("is-over"); });
  dz.addEventListener("drop", handleBackupDrop);
  el.querySelector("#dz-pick").onclick = function () { sendToHost("pick-backup", {}); };
  el.querySelector("#dz-x").onclick = closeOverlay;
}

const DROP_MAX_BYTES = 20 * 1024 * 1024;

function handleBackupDrop(e) {
  e.preventDefault();
  const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
  if (!f) return;
  const realPath = f.path || "";          // WebView2 expoe; padrao web nao
  if (realPath) { closeOverlay(); inspectBackup(realPath); return; }
  if (f.size > DROP_MAX_BYTES) {
    // Trava da spec: fecha o aviso e ABRE o seletor nativo direto.
    showNotice("Arquivos acima de 20 MB não podem ser arrastados — selecione o arquivo.",
      function () { sendToHost("pick-backup", {}); });
    return;
  }
  const rd = new FileReader();
  rd.onload = function () {
    closeOverlay();
    sendToHost("drop-temp", { name: f.name, b64: toBase64(rd.result) });
  };
  rd.readAsArrayBuffer(f);
}

function toBase64(buf) {
  const bytes = new Uint8Array(buf);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}
```

- [ ] **Step 6: style.css** — acrescentar:

```css
/* --- lote / quarentena --- */
.bk-section { margin-bottom: 26px; }
.bk-group-head { display: flex; align-items: center; gap: 10px; margin-bottom: 2px; }
.bk-group-title { font-weight: 650; font-size: 15px; }
.bk-group-sub { color: var(--text-dim, #b8a3b3); font-size: 12.5px; margin: 0 0 8px 26px; }
.bk-row { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px;
  border: 1px solid rgba(236,72,153,.14); border-radius: 10px; margin-bottom: 8px; cursor: pointer; }
.bk-row.is-locked { opacity: .62; cursor: default; }
.bk-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.bk-name { font-weight: 600; font-size: 14px; }
.bk-path { font-family: var(--mono, monospace); font-size: 11.5px; color: #9d87a0;
  overflow-wrap: anywhere; }
.bk-why { font-size: 12.5px; color: #d7bfd1; }
.bk-lock { font-size: 11px; color: #9d87a0; border: 1px solid rgba(236,72,153,.25);
  border-radius: 6px; padding: 2px 6px; align-self: center; }
.bk-tech { margin: 4px 0 0 26px; font-size: 12px; }
.bk-tech summary { cursor: pointer; color: #9d87a0; }
.bk-foot { position: sticky; bottom: 0; display: flex; align-items: center; gap: 14px;
  padding: 12px 4px; background: rgba(20,6,15,.92); border-top: 1px solid rgba(236,72,153,.2); }
.bk-tally { margin-left: auto; font-size: 13px; }
.bk-plan { margin: 6px 0 0 18px; font-size: 13px; }
.bk-actions { display: flex; gap: 12px; margin-top: 18px; }
.bk-meta-line { color: #b8a3b3; font-size: 12.5px; margin-bottom: 10px; }
.btn-danger { background: transparent; color: #fda4af; border: 1px solid rgba(253,164,175,.4); }
.feed { max-height: 260px; overflow-y: auto; font-family: var(--mono, monospace);
  font-size: 12.5px; border: 1px solid rgba(236,72,153,.16); border-radius: 10px; padding: 10px; }
.feed-line { padding: 2px 0; overflow-wrap: anywhere; }
.feed-ok { color: #6ee7b7; }
.feed-fail { color: #fda4af; }
.modal-mask { position: fixed; inset: 0; background: rgba(8,2,6,.72); display: flex;
  align-items: center; justify-content: center; z-index: 50; }
.modal-card { width: min(460px, 92vw); background: #1d0a16; border: 1px solid rgba(236,72,153,.3);
  border-radius: 14px; padding: 20px; display: flex; flex-direction: column; gap: 12px; }
.modal-title { margin: 0 0 2px; font-size: 17px; }
.modal-text { font-size: 13.5px; line-height: 1.5; }
.modal-big small { display: block; font-weight: 400; opacity: .8; margin-top: 2px; }
.dropzone { border: 1.5px dashed rgba(236,72,153,.45); border-radius: 12px; padding: 26px;
  text-align: center; font-size: 13px; color: #d7bfd1; }
.dropzone.is-over { background: rgba(236,72,153,.08); border-color: #EC4899; }
```

- [ ] **Step 7: Verificar** — `node --check gui/vector/app.js`; preview no
  browser (modal/navegação com dados de exemplo; telas de quarentena mostram o
  aviso "precisa do motor real" sem quebrar).
- [ ] **Step 8: Commit** — `git commit -am "feat(gui): quarentena + restauracao + picker com trava de 20MB"`

---

### Task 8: Validação total, exe e docs

- [ ] **Step 1: Suite completo** — `python -m pytest tests/ -q` → tudo verde
  (esperado ≈ 60+ testes; nenhum teste toca pastas reais).
- [ ] **Step 2: Estáticos** — `node --check gui/vector/app.js`,
  `node --check gui/vector/mock.js`, parser do `VectorHost.ps1` sem erros.
- [ ] **Step 3: Smoke do bridge sem GUI** — pipe de pedidos reais:

```powershell
$rows = @(
  '{"id":1,"cmd":"ping"}',
  '{"id":2,"cmd":"quarantine-inspect"}',
  '{"id":3,"cmd":"quarantine-export","dest":"c:\\nao\\usa.vec"}'
) -join "`n"
$rows | python vector-cli.py --serve
```
Esperado: 3 JSONs `ok:true`/`ok:false` coerentes (export falha com motivo, sem traceback).
- [ ] **Step 4: Rebuild** — fechar instâncias do exe e `.\build.ps1`; o exe já
  embute `gui\webview2` (Task do commit 65288ea) e o novo payload.
- [ ] **Step 5: Smoke real (usuário)** — abrir `dist\Vector.exe`: badge
  "motor real"; varredura; revisão com seções; plano; execução num alvo
  inofensivo criado antes (`New-Item 'C:\Program Files\VetorTeste' -ItemType Directory` +
  um arquivo dentro — some do scan? não: pasta sem registro instalados →
  entra MEDIUM/HIGH); quarentena mostra o item; restaurar devolve; `.vec`
  aparece em `HKCU:\Software\Classes\.vec`; duplo-clique numa cópia abre o
  Vector na tela de restauração.
- [ ] **Step 6: Docs** — README: seção GUI descreve o fluxo review→plan→executar
  + `.vec` (abrir/restring a extensão); DESIGN: atualizar a seção Finish
  (lote com confirmação única, quarentena última-execução compactada); spec
  permanece como contrato.
- [ ] **Step 7: Commit final** — `git commit -am "docs: fluxo em lote e backup .vec no README/DESIGN"`.
- [ ] **Step 8:** Oferecer push da branch + PR para `theroverse/vector:main`
  (nunca merge direto em main sem confirmação do usuário).

## Self-review do plano

- Cobre a spec: summaryPlain (T1), .vec auto-contido só-última-execução
  compactado (T2/T3), bridge (T4), host: registro/--open/diálogos/drop-temp
  (T5), GUI review/plan/executing/done (T6), quarentena/restore/picker com
  trava 20 MB e copia-vs-move (T7), validação (T8).
- Nomes consistentes: `stage`/`seal`/`inspect`/`restore_one`/`export`/`purge`
  em todo o plano; no JS, `engineCall`/`onEngineReply`/`inspectBackup`/
  `openQuarantine`/`openBackupPicker`/`showPicker`/`showDropForm`/
  `handleBackupDrop`.
- Desvio assumido da spec: `restore_done()` foi eliminada — `_rewrite_without`
  já apaga o `last.vec` quando esvazia (menos estado, mesma semântica).
