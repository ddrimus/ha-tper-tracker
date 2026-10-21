import json
import re
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parent.parent / "custom_components" / "tper_tracker"
LANGUAGES = ["en", "it"]


# Load the translation file of one language
def load(language: str) -> dict:
    return json.loads((COMPONENT / "translations" / f"{language}.json").read_text())


# Collect every key path of a translation file
def keys(data: dict, prefix: str = "") -> set[str]:
    found = set()
    for key, value in data.items():
        path = f"{prefix}{key}"
        found |= keys(value, f"{path}.") if isinstance(value, dict) else {path}
    return found


# Test that English and Italian translate the same keys
def test_languages_have_the_same_keys() -> None:
    assert keys(load("it")) == keys(load("en"))


# Test that every error, abort, exception and status used in code is translated
@pytest.mark.parametrize("language", LANGUAGES)
def test_codes_used_in_code_are_translated(language: str) -> None:
    strings = load(language)
    flow = (COMPONENT / "config_flow.py").read_text()
    config_flow, options_flow = flow.split("class TperTrackerOptionsFlowHandler")

    for section, source in (("config", config_flow), ("options", options_flow)):
        for code in re.findall(r'errors\[[^\]]+\] = "(\w+)"', source):
            assert code in strings[section]["error"], f"{section}.error.{code}"
        for code in re.findall(r'async_abort\(reason="(\w+)"\)', source):
            assert code in strings[section]["abort"], f"{section}.abort.{code}"

    coordinator = (COMPONENT / "coordinator.py").read_text()
    for code in re.findall(r'translation_key="(\w+)"', coordinator):
        assert code in strings["exceptions"], f"exceptions.{code}"

    statuses = re.findall(r'^STATUS_\w+ = "(\w+)"', coordinator, re.MULTILINE)
    attribute = strings["entity"]["sensor"]["bus_line"]["state_attributes"]["status"]["state"]
    assert set(statuses) == set(attribute)


# Test that repair issues, the fix flow and reconfigure are translated
@pytest.mark.parametrize("language", LANGUAGES)
def test_repairs_and_reconfigure_are_translated(language: str) -> None:
    strings = load(language)

    source = (COMPONENT / "issues.py").read_text()
    issues = re.findall(r'^(?:ISSUE_\w+|NO_LINES_SERVED) = "(\w+)"', source, re.MULTILINE)
    assert len(issues) == 4
    for issue in issues:
        # Home Assistant allows a description or a fix flow, never both
        text = set(strings["issues"][issue])
        assert "title" in text, f"issues.{issue}"
        assert ("description" in text) != ("fix_flow" in text), f"issues.{issue}"

    fix_flow = strings["issues"]["lines_not_served"]["fix_flow"]
    assert "confirm" in fix_flow["step"]
    for reason in re.findall(r'async_abort\(reason="(\w+)"\)', (COMPONENT / "repairs.py").read_text()):
        assert reason in fix_flow["abort"], f"fix_flow.abort.{reason}"

    assert "reconfigure" in strings["config"]["step"]
    assert "reconfigure_successful" in strings["config"]["abort"]
    assert "active_entity" in strings["options"]["step"]["init"]["data_description"]
