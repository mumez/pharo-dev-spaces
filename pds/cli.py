import argparse
import sys

from pds.dev_base import prepare_dev_base
from pds.layout import Layout
from pds.slot import SLOT_NUMBERS, reset_slot, start_slot, stop_slot
from pds.setup_plain import setup_plain


def build_parser():
    parser = argparse.ArgumentParser(prog="pds", description="Pharo dev spaces for AI coding agents")
    commands = parser.add_subparsers(dest="command", required=True)

    setup_plain_parser = commands.add_parser("setup-plain", help="download a plain Pharo image + VM")
    setup_plain_parser.add_argument("--version", default="140", help="Pharo version for get.pharo.org (e.g. 140)")
    setup_plain_parser.add_argument("--force", action="store_true", help="replace an existing plain-pharo/")
    setup_plain_parser.set_defaults(handler=lambda layout, args: setup_plain(layout, args.version, args.force))

    prepare_dev_base_parser = commands.add_parser("prepare-dev-base", help="plain + SIS + AgenticBrowser -> dev-base/")
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

    return parser


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
