"""extra command line subcommands for simplebot's CLI"""

from simplebot import DeltaBot

from .util import get_default, set_config

def_interval = 60 * 5


# pylama:ignore=C0103
class feeds:
    """Customize simplebot_feeds plugin's settings.

    Run without any arguments to see existing values.
    """

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--interval",
            type=int,
            default=None,
            help=f"set how many seconds to sleep between checking the feeds again (default: ${def_interval})",
        )
        parser.add_argument(
            "--max",
            type=int,
            default=None,
            help=f"set the maximum amount of feeds the bot will subscribe to before rejecting new unknown feeds, by default: -1 (infinite)",
        )
        parser.add_argument(
            "--prefix",
            default=None,
            help='set a prefix to append to every of this plugin\'s commands by default: "" (no prefix)',
        )

    def run(self, bot: DeltaBot, args, out) -> None:
        if args.interval is not None:
            set_config(bot, "delay", args.interval)
            out.line(f"interval: {args.interval}")
        if args.max is not None:
            set_config(bot, "max_feed_count", args.max)
            out.line(f"max feeds count: {args.max}")
        if args.prefix is not None:
            set_config(bot, "cmd_prefix", args.prefix)
            out.line(f"command prefix: {args.prefix}")


"""extra command line subcommands for simplebot's CLI"""

from simplebot import DeltaBot

from .util import set_config

def_interval = 60 * 5


# pylama:ignore=C0103
class feeds:
    """Customize simplebot_feeds plugin's settings.

    Run without any arguments to see existing values.
    """

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--interval",
            type=int,
            default=None,
            help=f"set how many seconds to sleep between checking the feeds again (default: ${def_interval})",
        )
        parser.add_argument(
            "--max",
            type=int,
            default=None,
            help=f"set the maximum amount of feeds the bot will subscribe to before rejecting new unknown feeds, by default: -1 (infinite)",
        )
        parser.add_argument(
            "--prefix",
            default=None,
            help='set a prefix to append to every of this plugin\'s commands by default: "" (no prefix)',
        )

    def run(self, bot: DeltaBot, args, out) -> None:
        if args.interval is not None:
            set_config(bot, "delay", args.interval)
            out.line(f"interval: {args.interval}")
        if args.max is not None:
            set_config(bot, "max_feed_count", args.max)
            out.line(f"max feeds count: {args.max}")
        if args.prefix is not None:
            set_config(bot, "cmd_prefix", args.prefix)
            out.line(f"command prefix: {args.prefix}")

        if (args.interval, args.max, args.prefix) == (None, None, None):
            interval = get_default(bot, "delay", def_interval)
            max_feeds = get_default(bot, "max_feed_count", -1)
            prefix = get_default(bot, "cmd_prefix", "")
            out.line(f"interval: {interval}")
            out.line(f"max feeds count: {max_feeds}")
            out.line(f"command prefix: {prefix}")
