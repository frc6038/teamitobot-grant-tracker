"""
Paket metadata, build ve import davranışını doğrulayan testler
"""

import hashlib
import os
import subprocess
import sys
import tomllib
import venv
from pathlib import Path
from zipfile import ZipFile

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_MODULES = (
    "bot.py",
    "config.py",
    "database.py",
    "scraper.py",
    "smtp_notifier.py",
    "domain/__init__.py",
    "adapters/__init__.py",
    "adapters/telegram/__init__.py",
    "adapters/first_web/__init__.py",
    "infrastructure/__init__.py",
    "infrastructure/config.py",
)

CLEAN_INSTALL_TIMEOUT = 240


def _venv_python(venv_dir):
    venv.create(venv_dir, with_pip=True)
    if sys.platform.startswith("win"):
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _pip_list(python):
    result = subprocess.run(
        [str(python), "-m", "pip", "list", "--format=freeze"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.lower()


def test_dependency_groups_are_separated():
    """pyproject.toml'da runtime bağımlılıkları test/lint araçlarını içermemeli;
    test/lint araçları da kendi aralarında ayrı gruplarda olmalı."""

    with open(REPO_ROOT / "pyproject.toml", "rb") as handle:
        data = tomllib.load(handle)

    runtime_deps = {
        dep.split("==")[0].lower() for dep in data["project"]["dependencies"]
    }
    extras = data["project"]["optional-dependencies"]
    test_deps = {dep.split("==")[0].lower() for dep in extras["test"]}
    dev_deps = {dep.split("==")[0].lower().split("[")[0] for dep in extras["dev"]}

    assert "pytest" not in runtime_deps
    assert "ruff" not in runtime_deps
    assert "pytest" in test_deps
    assert "ruff" not in test_deps
    assert "ruff" in dev_deps


def test_lock_file_pins_every_runtime_dependency_at_declared_version():
    """requirements.lock, pyproject.toml'daki her runtime bağımlılığını aynı
    sabit sürümle içermeli (üretim akışının tek doğrulanmış kaynağı olmalı)."""

    with open(REPO_ROOT / "pyproject.toml", "rb") as handle:
        declared = dict(
            dep.split("==") for dep in tomllib.load(handle)["project"]["dependencies"]
        )

    lock_versions = {}
    for line in (REPO_ROOT / "requirements.lock").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, version = line.split("==")
        lock_versions[name.lower()] = version

    for name, version in declared.items():
        assert lock_versions.get(name.lower()) == version, name


def test_requirements_txt_matches_pyproject_exactly():
    """requirements.txt (Procfile/Render uyumluluk aynası), pyproject.toml'daki
    runtime bağımlılıklarıyla isim ve sürüm bazında birebir aynı kümeyi
    içermeli — ne eksik ne fazla. Aksi halde iki kaynak birbirinden
    habersizce sürüklenir (bkz. requirements.lock testinin sadece tek
    yönlü kontrol ettiği, burada iki yönlü kontrol edilen aynı risk)."""

    with open(REPO_ROOT / "pyproject.toml", "rb") as handle:
        declared = dict(
            dep.split("==") for dep in tomllib.load(handle)["project"]["dependencies"]
        )

    requirements_txt = {}
    for line in (REPO_ROOT / "requirements.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, version = line.split("==")
        requirements_txt[name.lower()] = version

    declared_normalized = {name.lower(): version for name, version in declared.items()}

    assert requirements_txt == declared_normalized


def test_wheel_build_contains_expected_modules_only(tmp_path):
    """Paket build edilince beklenen modülleri içermeli; test/lint araçlarını
    dosya olarak hiç barındırmamalı."""

    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(tmp_path), "."],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )

    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1

    with ZipFile(wheels[0]) as archive:
        names = archive.namelist()

    for expected in EXPECTED_MODULES:
        assert expected in names

    assert not any("pytest" in name or "ruff" in name for name in names)


def test_wheel_build_is_reproducible(tmp_path):
    """Aynı kaynaktan iki kez build edilen wheel, hem tam dosya SHA-256'sı hem
    de içerik bazında birebir aynı olmalı (build-path/zaman damgası/ZIP
    metadata kaynaklı hiçbir sapma kabul edilmez)."""

    build_env = {**os.environ, "SOURCE_DATE_EPOCH": "1700000000"}
    file_hashes = []
    content_hashes_list = []

    for attempt in ("first", "second"):
        out_dir = tmp_path / attempt
        out_dir.mkdir()
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "-w",
                str(out_dir),
                ".",
            ],
            cwd=REPO_ROOT,
            env=build_env,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        wheel = next(out_dir.glob("*.whl"))
        file_hashes.append(hashlib.sha256(wheel.read_bytes()).hexdigest())

        with ZipFile(wheel) as archive:
            content_hashes_list.append(
                {
                    info.filename: archive.read(info.filename)
                    for info in archive.infolist()
                }
            )

    assert file_hashes[0] == file_hashes[1]
    assert content_hashes_list[0] == content_hashes_list[1]


@pytest.mark.timeout(CLEAN_INSTALL_TIMEOUT)
def test_clean_runtime_install_excludes_dev_tools_and_imports(tmp_path):
    """Sıfırdan bir venv'e sadece runtime bağımlılıklarıyla kurulum yapılmalı;
    pytest/ruff kesinlikle bulunmamalı ve kurulan paket gerçekten import
    edilebilmeli. Bu gerçek bir 'clean install' testidir; hız için mevcut
    dev ortamının paketlerini yeniden kullanmaz."""

    python = _venv_python(tmp_path / "venv")

    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", str(REPO_ROOT)],
        check=True,
        capture_output=True,
        text=True,
        timeout=CLEAN_INSTALL_TIMEOUT - 30,
    )

    listing = _pip_list(python)
    assert "pytest" not in listing
    assert "ruff" not in listing

    env = {
        **os.environ,
        "TELEGRAM_BOT_TOKEN": "dummy-token",
        "DATABASE_URL": "postgresql://user:pass@127.0.0.1:1/itobot_test",
    }
    # cwd, tmp_path'e (bot.py/config.py içermeyen bir dizin) kasıtlı olarak
    # sabitlenir; aksi halde "python -c" REPO_ROOT'u sys.path[0] yapar ve
    # kurulu wheel yerine kaynak checkout'taki dosyalar sessizce import edilir.
    import_cwd = tmp_path / "import-cwd"
    import_cwd.mkdir()
    script = (
        "import bot, config\n"
        "print(bot.__file__)\n"
        "print(config.__file__)\n"
        "print('IMPORT_OK')\n"
    )
    result = subprocess.run(
        [str(python), "-c", script],
        cwd=import_cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0
    assert "IMPORT_OK" in result.stdout
    assert str(REPO_ROOT) not in result.stdout

    # alembic runtime bağımlılığı (GRANT-09) kuruluysa CLI olarak da
    # kullanılabilmeli; sadece import edilebilir olması yetmez.
    alembic_result = subprocess.run(
        [str(python), "-m", "alembic", "--version"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert alembic_result.returncode == 0
    assert "alembic" in alembic_result.stdout.lower()


@pytest.mark.timeout(CLEAN_INSTALL_TIMEOUT)
def test_clean_dev_install_includes_test_and_lint_tooling(tmp_path):
    """Sıfırdan bir venv'e [dev] extra'sıyla kurulum, test ve lint araçlarını
    da (self-referencing [test] extra'sı dahil) kurmalı."""

    python = _venv_python(tmp_path / "venv")

    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", f"{REPO_ROOT}[dev]"],
        check=True,
        capture_output=True,
        text=True,
        timeout=CLEAN_INSTALL_TIMEOUT - 30,
    )

    listing = _pip_list(python)
    assert "pytest==" in listing
    assert "pytest-timeout==" in listing
    assert "ruff==" in listing
