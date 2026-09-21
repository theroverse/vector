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
