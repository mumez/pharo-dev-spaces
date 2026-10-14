import argparse
import json
import sys

from pds.baseline import project_entry
from pds.dev_base import prepare_dev_base
from pds.layout import Layout
from pds.mcp_config import launch_claude
from pds.projects import add_project_entry
from pds.snapshot import build_snapshot
from pds.slot import SLOT_NUMBERS, reset_slot, start_slot, stop_slot
from pds.setup_plain import setup_plain


def build_parser():
    parser = argparse.ArgumentParser(prog="pds", description="Pharo dev spaces for AI coding agents")
    commands = parser.add_subparsers(dest="command", required=True)

    setup_plain_parser = commands.add_parser("setup-plain", help="download a plain Pharo image + VM")
    setup_plain_parser.add_argument("--version", default="140", help="Pharo version for get.pharo.org (e.g. 140)")
    setup_plain_parser.add_argument("--force", action="store_true", help="replace an existing plain-pharo/")
    setup_plain_parser.set_defaults(handler=lambda layout, args: setup_plain(layout, args.version, args.force))

    prepare_dev_base_parser = commands.add_parser(
        "prepare-dev-base", help="plain + load_agentic_browser.st -> dev-base/"
    )
    prepare_dev_base_parser.add_argument("--force", action="store_true", help="replace an existing dev-base/")
    prepare_dev_base_parser.set_defaults(handler=lambda layout, args: prepare_dev_base(layout, args.force))

    slot_parser = commands.add_parser("slot", help="manage the fixed slots slot1..3")
    slot_actions = slot_parser.add_subparsers(dest="slot_action", required=True)
    for action, handler, help_text in (
        ("reset", reset_slot, "recreate the slot from snapshots/current (or dev-base)"),
        ("up", start_slot, "start the slot headless with PHARO_SIS_PORT=8086+N"),
        ("down", stop_slot, "stop the slot"),
    ):
        action_parser = slot_actions.add_parser(action, help=help_text)
        action_parser.add_argument("slot_number", type=int, choices=SLOT_NUMBERS)
        action_parser.set_defaults(handler=lambda layout, args, handler=handler: handler(layout, args.slot_number))

    claude_parser = slot_actions.add_parser("claude", help="run Claude Code with MCP pointed at the slot")
    claude_parser.add_argument("slot_number", type=int, choices=SLOT_NUMBERS)
    claude_parser.add_argument("claude_arguments", nargs=argparse.REMAINDER, help="passed to claude (after --)")
    claude_parser.set_defaults(
        handler=lambda layout, args: launch_claude(layout, args.slot_number, args.claude_arguments)
    )

    add_project_parser = commands.add_parser("add-project", help="print a projects.json entry derived from BaselineOf")
    add_project_parser.add_argument("repository", help="path of the git repository")
    add_project_parser.add_argument("--groups", default="default", help="comma-separated Metacello groups (default: default)")
    add_project_parser.add_argument("--write", action="store_true", help="append the entry to projects.json")
    add_project_parser.set_defaults(handler=add_project)

    build_snapshot_parser = commands.add_parser("build-snapshot", help="build snapshots/current from origin/develop")
    build_snapshot_parser.add_argument("--full", action="store_true", help="rebuild from dev-base through the baselines")
    build_snapshot_parser.set_defaults(handler=lambda layout, args: build_snapshot(layout, full=args.full))

    return parser


def add_project(layout, args):
    entry = project_entry(args.repository, args.groups.split(","))
    print(json.dumps(entry, indent=2))
    if args.write:
        add_project_entry(layout, entry)



def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        args.handler(Layout.default(), args)
    except Exception as error:
        print(f"pds: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
