"""Filesystem: cruzamento, filtro --target e PermissionError elegante."""

import os

from vector.scanners.filesystem import (
    safe_iterdir,
    safe_stat_size_mtime,
    scan_filesystem,
)


def test_orphan_folder_detected(tmp_path):
    app = tmp_path / "OldApp"
    app.mkdir()
    (app / "data.bin").write_bytes(b"x" * 100)
    result = scan_filesystem(installed=set(), roots=[tmp_path])
    assert len(result.candidates) == 1
    assert result.candidates[0].label == "OldApp"


def test_name_matches_tolerates_affixes():
    from vector.utils import name_matches, normalize_name

    installed = {"mozilla firefox", "docker desktop", "python"}
    assert name_matches(normalize_name("Mozilla"), installed)
    assert name_matches(normalize_name("Docker"), installed)
    assert name_matches(normalize_name("Python314"), installed)
    assert not name_matches(normalize_name("OldApp"), installed)


def test_temp_needs_extra_evidence(tmp_path):
    """Em raizes reais, TEMP so vira candidato com evidencia extra."""
    import time

    from vector.scanners import filesystem as fs

    real = fs.resolve_roots()
    temp_roots = [r for r in real if "temp" in str(r).lower()]
    if not temp_roots:  # fora do Windows: nada a verificar
        return
    stale = temp_roots[0] / "vector-stale-probe-xyz"
    stale.mkdir(exist_ok=True)
    (stale / "f.bin").write_bytes(b"x")
    old = time.time() - 200 * 86400
    import os as _os

    _os.utime(stale / "f.bin", (old, old))
    try:
        result = scan_filesystem(installed=set())
        match = [c for c in result.candidates if c.label == stale.name]
        assert match and any("abandonada" in e.description for e in match[0].evidences)
    finally:
        import shutil as _shutil

        _shutil.rmtree(stale, ignore_errors=True)


def test_installed_folder_skipped(tmp_path):
    app = tmp_path / "Notion"
    app.mkdir()
    (app / "app.exe").write_bytes(b"x" * 10)
    result = scan_filesystem(installed={"notion"}, roots=[tmp_path])
    # Instalado + recente + sem restos: nenhuma evidencia -> sem candidato.
    assert result.candidates == []


def test_target_filter(tmp_path):
    (tmp_path / "OldApp").mkdir()
    (tmp_path / "OtherApp").mkdir()
    result = scan_filesystem(installed=set(), target="oldapp", roots=[tmp_path])
    assert [c.label for c in result.candidates] == ["OldApp"]


def test_leftover_uninstaller_evidence(tmp_path):
    app = tmp_path / "OldApp"
    app.mkdir()
    (app / "unins000.exe").write_bytes(b"fake")
    result = scan_filesystem(installed=set(), roots=[tmp_path])
    descriptions = [e.description for e in result.candidates[0].evidences]
    assert any("unins000.exe" in d for d in descriptions)


def test_permission_error_is_graceful(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise PermissionError(13, "Acesso negado")

    monkeypatch.setattr(os, "scandir", boom)
    denied: list[str] = []
    assert safe_iterdir(tmp_path, denied) == []
    assert denied and "permissao" in denied[0].lower()
    size, mtime = safe_stat_size_mtime(tmp_path / "inexistente")
    assert (size, mtime) == (0, None)
