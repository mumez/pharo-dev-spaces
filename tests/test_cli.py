import json

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


def test_slot_cursor_agent_passes_arguments_after_double_dash(monkeypatch):
    launches = []
    monkeypatch.setattr(
        cli,
        "launch_cursor_agent",
        lambda layout, slot_number, arguments, workspace=None, approve_mcps=False: launches.append(
            (slot_number, arguments, workspace, approve_mcps)
        ),
    )
    args = build_parser().parse_args(["slot", "2", "cursor-agent", "--", "-p", "/st-eval Smalltalk version"])

    args.handler(None, args)

    assert launches == [(2, ["-p", "/st-eval Smalltalk version"], None, False)]


def test_slot_cursor_agent_passes_workspace_and_approve_mcps(monkeypatch):
    launches = []
    monkeypatch.setattr(
        cli,
        "launch_cursor_agent",
        lambda layout, slot_number, arguments, workspace=None, approve_mcps=False: launches.append(
            (slot_number, arguments, workspace, approve_mcps)
        ),
    )
    args = build_parser().parse_args(
        [
            "slot",
            "2",
            "cursor-agent",
            "--workspace",
            "./repos/Stick",
            "--approve-mcps",
            "--",
            "-p",
            "fix Stick",
        ]
    )

    args.handler(None, args)

    assert launches == [(2, ["-p", "fix Stick"], "./repos/Stick", True)]


def test_slot_number_outside_fixed_slots_is_rejected():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["slot", "4", "up"])


def run_cli(layout, monkeypatch, capsys, *argv):
    monkeypatch.setattr(cli.Layout, "default", classmethod(lambda cls: layout))
    assert cli.main(list(argv)) == 0
    return json.loads(capsys.readouterr().out)


def test_slot_status_prints_one_slot_as_json(layout, monkeypatch, capsys):
    assert run_cli(layout, monkeypatch, capsys, "slot", "1", "status")["slot"] == 1


def test_list_slots_prints_every_slot_as_json(layout, monkeypatch, capsys):
    statuses = run_cli(layout, monkeypatch, capsys, "list-slots")

    assert [(status["slot"], status["running"]) for status in statuses] == [(1, False), (2, False), (3, False)]
