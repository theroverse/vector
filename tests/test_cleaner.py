"""Cleaner: LOW nunca oferecido, confirmacao explicita, alerta sensivel."""

from vector.cleaner import run_clean
from vector.models import Evidence, OrphanCandidate, ScanReport


def _folder(label, path, confidence="MEDIUM", sensitive=False):
    return OrphanCandidate(
        kind="folder", path=path, label=label,
        evidences=[Evidence(description="+40 ausente", weight=40, source="t")],
        score=40, confidence=confidence, sensitive=sensitive,
    )


def test_low_never_offered(capsys, monkeypatch):
    report = ScanReport(target=None, candidates=[_folder("A", r"C:\x\A", "LOW")])
    monkeypatch.setattr("builtins.input", lambda *a, **k: (_ for _ in ()).throw(AssertionError("nao deve pedir")))
    assert run_clean(report) == 0
    assert "Nenhuma pasta HIGH/MEDIUM" in capsys.readouterr().out


def test_skip_on_empty_input(tmp_path, capsys, monkeypatch):
    real = tmp_path / "OldApp"
    real.mkdir()
    report = ScanReport(target=None, candidates=[_folder("OldApp", str(real))])
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")
    assert run_clean(report) == 0
    assert real.exists()  # Enter vazio = pula, nao apaga
    assert "pulada" in capsys.readouterr().out


def test_explicit_confirmation_removes(tmp_path, monkeypatch):
    real = tmp_path / "OldApp"
    real.mkdir()
    (real / "f.bin").write_bytes(b"x")
    report = ScanReport(target=None, candidates=[_folder("OldApp", str(real))])
    answers = iter(["REMOVER 1", "s"])
    monkeypatch.setattr("builtins.input", lambda *a, **k: next(answers))
    assert run_clean(report) == 0
    assert not real.exists()


def test_sensitive_warns(capsys, monkeypatch):
    real = r"C:\x\GameSave"
    report = ScanReport(target=None, candidates=[_folder("G", real, sensitive=True)])
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")
    run_clean(report)
    out = capsys.readouterr().out
    assert "DADO SENSIVEL" in out and "PERDA IRREVERSIVEL" in out


def test_registry_never_auto_removed(capsys, monkeypatch):
    reg = OrphanCandidate(
        kind="registry", path=r"HKLM\...\OldApp", label="OldApp",
        evidences=[Evidence(description="+40 chave orfa", weight=40, source="registry")],
        score=40, confidence="MEDIUM", manual_command="reg delete ...",
    )
    report = ScanReport(target=None, candidates=[reg])
    monkeypatch.setattr("builtins.input", lambda *a, **k: (_ for _ in ()).throw(AssertionError("nao deve pedir")))
    assert run_clean(report) == 0
    assert "NAO sao removidos automaticamente" in capsys.readouterr().out
