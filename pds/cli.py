import argparse
import sys

from pds.layout import Layout
from pds.setup_plain import setup_plain


def build_parser():
    parser = argparse.ArgumentParser(prog="pds", description="Pharo dev spaces for AI coding agents")
    commands = parser.add_subparsers(dest="command", required=True)

    setup_plain_parser = commands.add_parser("setup-plain", help="download a plain Pharo image + VM")
    setup_plain_parser.add_argument("--version", default="140", help="Pharo version for get.pharo.org (e.g. 140)")
    setup_plain_parser.add_argument("--force", action="store_true", help="replace an existing plain-pharo/")
    setup_plain_parser.set_defaults(handler=lambda layout, args: setup_plain(layout, args.version, args.force))

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
