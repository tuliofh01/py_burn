"""Tests for the CLI workflow model."""

from pathlib import Path

from py_burn.model.workflow import WorkflowModel


def test_default_tree_has_sections() -> None:
    model = WorkflowModel()
    assert set(model.sections) == {"iso", "usb", "format", "actions"}


def test_incomplete_until_iso_and_usb_selected() -> None:
    model = WorkflowModel()
    missing = model.incomplete_fields()
    labels = {field.label for _, _, field in missing}
    assert "ISO file path" in labels
    assert "Device path" in labels
    assert not model.is_ready()


def test_storage_mode_skips_iso_requirement() -> None:
    model = WorkflowModel()
    model.apply_storage_profile()
    model.set_field("usb", "device_path", "/dev/sdb")
    model.set_field("actions", "confirmed", "yes")
    assert model.job_mode() == "storage"
    assert model.is_ready()


def test_ready_after_burn_configuration() -> None:
    model = WorkflowModel()
    model.set_field("iso", "iso_path", "/tmp/test.iso")
    model.set_field("iso", "iso_info", "test")
    model.set_field("usb", "device_path", "/dev/sdb")
    model.set_field("actions", "confirmed", "yes")
    assert model.job_mode() == "burn"
    assert model.is_ready()


def test_snapshot_values() -> None:
    model = WorkflowModel()
    model.set_field("iso", "iso_path", "/tmp/ubuntu.iso")
    model.set_field("usb", "device_path", "/dev/sdc")
    model.set_field("format", "volume_label", "DATA")
    snapshot = model.snapshot()
    assert snapshot["iso_path"] == "/tmp/ubuntu.iso"
    assert snapshot["usb_device"] == "/dev/sdc"
    assert snapshot["job_mode"] == "burn"
    assert snapshot["volume_label"] == "DATA"


def test_navigation_into_section() -> None:
    model = WorkflowModel()
    assert model.enter("iso")
    assert model.path == ["iso"]
    items = model.list_items()
    assert any(kind == "field" and key == "iso_path" for kind, key, _ in items)
    model.back()
    assert model.path == []


def test_apply_iso_profile_missing_file() -> None:
    model = WorkflowModel()
    ok, message = model.apply_iso_profile(Path("/tmp/definitely-missing-file.iso"))
    assert not ok
    assert "not found" in message.lower() or "ISO" in message
