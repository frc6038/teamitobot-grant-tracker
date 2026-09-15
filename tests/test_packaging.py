"""
Paket metadata, build ve import davranışını doğrulayan testler.
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
    "tools/token_setup/__init__.py",
    "tools/token_setup/__main__.py",
    "tools/token_setup/validator.py",
)

CLEAN_INSTALL_TIMEOUT = 240
TEST_ENVIRONMENT = "test"


def _build_and_install_wheel(tmp_path):
    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(wheel_dir),
            str(REPO_ROOT),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=CLEAN_INSTALL_TIMEOUT - 30,
    )

    wheels = list(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1

    python = _venv_python(tmp_path / "venv")

    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--quiet",
            str(wheels[0]),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=CLEAN_INSTALL_TIMEOUT - 30,
    )

    return python


def _run_installed_token_setup(python, cwd, env):
    script = r"""
import os
import runpy
import sys

import requests


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def fake_get(*args, **kwargs):
    mode = os.environ["TOKEN_SETUP_TEST_RESPONSE"]

    if mode == "network":
        raise requests.RequestException("simulated provider failure")

    if mode == "unauthorized":
        return FakeResponse(
            401,
            {
                "ok": False,
            },
        )

    if mode == "malformed":
        return FakeResponse(
            200,
            {
                "ok": True,
            },
        )

    if mode == "rate-limited":
        return FakeResponse(
            429,
            {
                "ok": False,
            },
        )

    if mode == "server-error":
        return FakeResponse(
            500,
            {
                "ok": False,
            },
        )

    if mode == "valid":
        return FakeResponse(
            200,
            {
                "ok": True,
                "result": {
                    "id": 123456789,
                    "is_bot": True,
                    "first_name": "Test Bot",
                    "username": "test_bot",
                },
            },
        )

    raise AssertionError(f"unknown test mode: {mode}")


requests.get = fake_get

sys.argv = ["tools.token_setup"]

runpy.run_module("tools.token_setup", run_name="__main__")
"""

    return subprocess.run(
        [str(python), "-c", script],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


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
    sabit sürümle içermeli."""

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
    """requirements.txt, pyproject.toml'daki runtime bağımlılıklarıyla isim ve
    sürüm bazında birebir aynı kümeyi içermeli."""

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
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "-w",
            str(tmp_path),
            ".",
        ],
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
    de içerik bazında birebir aynı olmalı."""

    build_env = {
        **os.environ,
        "SOURCE_DATE_EPOCH": "1700000000",
    }

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
    pytest/ruff bulunmamalı ve kurulan paket gerçekten import edilebilmeli."""

    python = _venv_python(tmp_path / "venv")

    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--quiet",
            str(REPO_ROOT),
        ],
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
        "DATABASE_URL": ("postgresql://user:pass@127.0.0.1:1/itobot_test"),
    }

    # Kaynak checkout'taki bot.py/config.py dosyalarının yanlışlıkla import
    # edilmesini önlemek için kaynak ağacının dışındaki cwd kullanılır.
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


@pytest.mark.timeout(CLEAN_INSTALL_TIMEOUT)
def test_clean_wheel_install_runs_token_setup_outside_source_tree(tmp_path):
    python = _build_and_install_wheel(tmp_path)

    import_cwd = tmp_path / "import-cwd"
    import_cwd.mkdir()

    env = {
        **os.environ,
        "TELEGRAM_BOT_TOKEN": "",
    }

    result = subprocess.run(
        [str(python), "-m", "tools.token_setup"],
        cwd=import_cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 1
    assert "TELEGRAM_BOT_TOKEN is not set in the environment." in result.stderr
    assert str(REPO_ROOT) not in result.stdout + result.stderr
    assert list(import_cwd.iterdir()) == []

    module_check = subprocess.run(
        [
            str(python),
            "-c",
            (
                "import tools.token_setup, "
                "tools.token_setup.validator; "
                "print(tools.token_setup.__file__); "
                "print(tools.token_setup.validator.__file__)"
            ),
        ],
        cwd=import_cwd,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    secret_token = "123456789:SuperSecret_Test-Token"

    scenarios = (
        ("invalid-format", "not-a-valid-token", None, 1),
        ("unauthorized", secret_token, "unauthorized", 1),
        ("rate-limited", secret_token, "rate-limited", 2),
        ("server-error", secret_token, "server-error", 2),
        ("network", secret_token, "network", 2),
        ("malformed", secret_token, "malformed", 2),
        ("valid", secret_token, "valid", 0),
    )

    for name, token, response_mode, expected_code in scenarios:
        scenario_cwd = tmp_path / f"scenario-{name}"
        scenario_cwd.mkdir()

        scenario_env = {
            **os.environ,
            "ENVIRONMENT": TEST_ENVIRONMENT,
            "TELEGRAM_BOT_TOKEN": token,
        }

        if response_mode is None:
            result = subprocess.run(
                [str(python), "-m", "tools.token_setup"],
                cwd=scenario_cwd,
                env=scenario_env,
                capture_output=True,
                text=True,
                timeout=30,
            )
        else:
            scenario_env["TOKEN_SETUP_TEST_RESPONSE"] = response_mode

            result = _run_installed_token_setup(
                python,
                scenario_cwd,
                scenario_env,
            )

        combined_output = result.stdout + result.stderr

        assert result.returncode == expected_code
        assert token not in combined_output
        assert str(REPO_ROOT) not in combined_output
        assert list(scenario_cwd.iterdir()) == []

    assert "site-packages" in module_check.stdout
    assert str(REPO_ROOT) not in module_check.stdout


@pytest.mark.timeout(CLEAN_INSTALL_TIMEOUT)
def test_clean_dev_install_includes_test_and_lint_tooling(tmp_path):
    """Sıfırdan bir venv'e [dev] extra'sıyla kurulum, test ve lint araçlarını
    da ([test] extra'sı dahil) kurmalı."""

    python = _venv_python(tmp_path / "venv")

    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--quiet",
            f"{REPO_ROOT}[dev]",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=CLEAN_INSTALL_TIMEOUT - 30,
    )

    listing = _pip_list(python)

    assert "pytest==" in listing
    assert "pytest-timeout==" in listing
    assert "ruff==" in listing
