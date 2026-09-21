"""Quarentena .vec: staging -> selar (zip+manifesto) -> inspecionar.

Tudo em tmp_path; nenhuma pasta real do usuario e tocada. `base` explicito
e a injecao de teste (mesma filosofia de scan_fn/stage_fn no bridge).
"""

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from vector import quarantine
from vector.models import OrphanCandidate


@pytest.fixture
def folder(tmp_path):
    """Cria pastas-source em tmp (o que o stage vai MOV ER)."""
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
    assert not d.exists()                      # MOV E U, nao copiou
    assert entry["summaryPlain"]               # frase-motivo vem junto p/ restauracao
    meta = base / "staging" / f'{entry["id"]}.meta.json'
    assert json.loads(meta.read_text(encoding="utf-8"))["id"] == entry["id"]
    assert (base / "staging" / entry["id"] / "Foo" / "a.txt").exists()


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
    assert sorted(i["label"] for i in info["items"]) == ["Dois", "Um"]
    assert not (base / "staging").exists()     # staging promovido ao zip
    with zipfile.ZipFile(vec) as zf:
        assert "manifest.json" in zf.namelist()
        assert any(n.endswith("a.txt") for n in zf.namelist())


def test_seal_replaces_previous_backup(tmp_path, folder):
    base = tmp_path / "q"
    quarantine.stage(_cand(folder("Velho"), label="Velho"), base=base)
    quarantine.seal(base=base)
    quarantine.stage(_cand(folder("Novo"), label="Novo"), base=base)
    info = quarantine.seal(base=base)
    assert [i["label"] for i in info["items"]] == ["Novo"]  # so a ultima execucao


def test_seal_nothing_returns_none(tmp_path):
    assert quarantine.seal(base=tmp_path / "q") is None


def test_inspect_none_when_empty(tmp_path):
    assert quarantine.inspect(base=tmp_path / "q") is None


def test_inspect_seals_orphan_staging(tmp_path, folder):
    """Queda no meio da execucao: itens ja movidos sao selados no 1o acesso."""
    base = tmp_path / "q"
    d = folder("O'fao")
    quarantine.stage(_cand(d, label="Orfa"), base=base)
    info = quarantine.inspect(base=base)
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


def test_root_uses_localappdata_at_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert quarantine.root() == tmp_path / "Vector" / "quarantine"


# ---------------- restore / export / purge (semantica ativo vs externo) ----- 

def _sealed_one(tmp_path, folder, name="Só"):
    base = tmp_path / "q"
    d = folder(name)
    entry, _ = quarantine.stage(_cand(d, label=name), base=base)
    quarantine.seal(base=base)
    return base, entry, d


def test_restore_one_active_moves_back_and_shrinks(tmp_path, folder):
    base = tmp_path / "q"
    d1, d2 = folder("Um"), folder("Dois")
    quarantine.stage(_cand(d1, label="Um"), base=base)
    quarantine.stage(_cand(d2, label="Dois"), base=base)
    info = quarantine.seal(base=base)
    first = next(i for i in info["items"] if i["label"] == "Um")
    ok, detail = quarantine.restore_one(first["id"], base=base)
    assert ok and detail == str(d1) and (d1 / "a.txt").exists()
    left = quarantine.inspect(base=base)
    assert [i["label"] for i in left["items"]] == ["Dois"]


def test_restore_last_item_removes_vec(tmp_path, folder):
    base, entry, d = _sealed_one(tmp_path, folder)
    ok, _ = quarantine.restore_one(entry["id"], base=base)
    assert ok and d.exists() and not (base / "last.vec").exists()
    assert quarantine.inspect(base=base) is None


def test_restore_one_skips_when_destination_exists(tmp_path, folder):
    base, entry, d = _sealed_one(tmp_path, folder, name="Volta")
    d.mkdir(parents=True, exist_ok=True)          # alguem recriou a origem
    ok, err = quarantine.restore_one(entry["id"], base=base)
    assert not ok and "já existe" in err
    assert len(quarantine.inspect(base=base)["items"]) == 1  # nada enxugado


def test_restore_external_copies_and_preserves(tmp_path, folder):
    base, entry, d = _sealed_one(tmp_path, folder, name="X")
    copy = tmp_path / "copia.vec"
    shutil.copyfile(base / "last.vec", copy)
    # stage() ja moveu a origem - nada existe em src/X, condicao de restaurar
    item = quarantine.inspect(path=copy, base=base)["items"][0]
    ok, original = quarantine.restore_one(item["id"], path=copy, base=base)
    assert ok and Path(original).exists()
    # backup externo permanece com a entrada (e backup, nao lixeira)
    assert len(quarantine.inspect(path=copy, base=base)["items"]) == 1


def test_restore_unknown_id_and_missing_file(tmp_path, folder):
    base, entry, _ = _sealed_one(tmp_path, folder)
    ok, err = quarantine.restore_one("nao-existe", base=base)
    assert not ok and "nao esta neste backup" in err
    ok, _ = quarantine.restore_one("x", path=tmp_path / "fantasma.vec", base=base)
    assert not ok


def test_restore_preserves_subfolders(tmp_path, folder):
    base = tmp_path / "q"
    d = tmp_path / "src" / "Recursivo"
    (d / "sub" / "fundo").mkdir(parents=True)
    (d / "a.txt").write_text("A", encoding="utf-8")
    (d / "sub" / "fundo" / "b.txt").write_text("B", encoding="utf-8")
    entry, _ = quarantine.stage(_cand(d), base=base)
    quarantine.seal(base=base)
    ok, _ = quarantine.restore_one(entry["id"], base=base)
    assert ok
    assert (d / "sub" / "fundo" / "b.txt").read_text(encoding="utf-8") == "B"


def test_export_copies_active(tmp_path, folder):
    base, _, _ = _sealed_one(tmp_path, folder)
    dest = tmp_path / "out" / "meu-backup.vec"
    ok, detail = quarantine.export(dest, base=base)
    assert ok and dest.exists() and detail == str(dest)
    assert (base / "last.vec").exists()           # original preservado


def test_purge_deletes_active(tmp_path, folder):
    base, _, _ = _sealed_one(tmp_path, folder)
    assert quarantine.purge(base=base) is True
    assert not (base / "last.vec").exists()
    assert quarantine.purge(base=base) is False    # idempotente


def test_export_without_backup_returns_reason(tmp_path):
    ok, err = quarantine.export(tmp_path / "x.vec", base=tmp_path / "q")
    assert not ok and "nao ha backup ativo" in err

