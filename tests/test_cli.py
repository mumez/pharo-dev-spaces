import pytest

from pds import cli
from pds.cli import build_parser


def test_slot_number_comes_before_the_slot_action():
    args = build_parser().parse_args(["slot", "2", "up"])

    assert (args.slot_number, args.slot_action) == (2, "up")


def test_slot_claude_passes_arguments_after_double_dash_to_claude(monkeypatch):
    launches = []
    monkeypatch.setattr(cli, "launch_claude", lambda layout, slot_number, arguments: launches.append((slot_number, arguments)))
    args = build_parser().parse_args(["slot", "1", "claude", "--", "-p", "/st-eval Smalltalk version"])

    args.handler(None, args)

    assert launches == [(1, ["-p", "/st-eval Smalltalk version"])]


def test_slot_number_outside_fixed_slots_is_rejected():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["slot", "4", "up"])
