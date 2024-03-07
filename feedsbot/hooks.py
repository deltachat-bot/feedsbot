"""Event Hooks"""

from argparse import Namespace
from pathlib import Path
from threading import Thread

from deltabot_cli import (
    AttrDict,
    Bot,
    BotCli,
    ChatType,
    EventType,
    SpecialContactId,
    events,
    is_not_known_command,
)
from feedparser import FeedParserDict
from rich.logging import RichHandler
from sqlalchemy import delete, func, select

from .orm import Fchat, Feed, init, session_scope
from .util import (
    check_feeds,
    format_entries,
    get_latest_date,
    get_old_entries,
    normalize_url,
    parse_feed,
    set_group_image,
)

cli = BotCli("feedsbot")
cli.add_generic_option(
    "--interval",
    type=int,
    default=60 * 5,
    help="how many seconds to sleep before checking the feeds again (default: %(default)s)",
)
cli.add_generic_option(
    "--parallel",
    type=int,
    default=10,
    help="how many feeds to check in parallel (default: %(default)s)",
)
cli.add_generic_option(
    "--max",
    type=int,
    default=-1,
    help="the maximum number of feeds the bot will subscribe to before rejecting new unknown feeds, by default: -1 (infinite)",
)
cli.add_generic_option(
    "--no-time",
    help="do not display date timestamp in log messages",
    action="store_false",
)


@cli.on_init
def on_init(bot: Bot, args: Namespace) -> None:
    bot.logger.handlers = [
        RichHandler(show_path=False, omit_repeated_times=False, show_time=args.no_time)
    ]
    for accid in bot.rpc.get_all_account_ids():
        if not bot.rpc.get_config(accid, "displayname"):
            bot.rpc.set_config(accid, "displayname", "FeedsBot")
            status = "I am a Delta Chat bot, send me /help for more info"
            bot.rpc.set_config(accid, "selfstatus", status)
            bot.rpc.set_config(accid, "delete_server_after", "1")
            bot.rpc.set_config(accid, "delete_device_after", "3600")


@cli.on_start
def on_start(bot: Bot, args: Namespace) -> None:
    bot.add_hook(
        (lambda b, a, e: _sub(args.max, b, a, e)), events.NewMessage(command="/sub")
    )
    config_dir = Path(args.config_dir)
    init(f"sqlite:///{config_dir / 'sqlite.db'}")
    Thread(
        target=check_feeds,
        args=(bot, args.interval, args.parallel, config_dir),
        daemon=True,
    ).start()


@cli.on(events.RawEvent)
def log_event(bot: Bot, accid: int, event: AttrDict) -> None:
    if event.kind == EventType.INFO:
        bot.logger.debug(event.msg)
    elif event.kind == EventType.WARNING:
        bot.logger.warning(event.msg)
    elif event.kind == EventType.ERROR:
        bot.logger.error(event.msg)
    elif event.kind == EventType.SECUREJOIN_INVITER_PROGRESS:
        if event.progress == 1000:
            bot.logger.debug("QR scanned by contact id=%s", event.contact_id)
            chatid = bot.rpc.create_chat_by_contact_id(accid, event.contact_id)
            send_help(bot, accid, chatid)


@cli.on(events.MemberListChanged)
def on_memberlist_change(bot: Bot, accid: int, event: AttrDict) -> None:
    if event.member_added:
        return
    chat_id = event.msg.chat_id
    chat = bot.rpc.get_full_chat_by_id(accid, chat_id)
    if SpecialContactId.SELF not in chat.contact_ids or len(chat.contact_ids) <= 1:
        with session_scope() as session:
            stmt = delete(Fchat).where(Fchat.accid == accid, Fchat.gid == chat_id)
            session.execute(stmt)
            bot.logger.debug(
                f"group(id={chat_id}) subscriptions were deleted due to member-removed event"
            )


@cli.on(events.NewMessage(is_info=False))
def markseen_commands(bot: Bot, accid: int, event: AttrDict) -> None:
    if not is_not_known_command(bot, event):
        bot.rpc.markseen_msgs(accid, [event.msg.id])


@cli.on(events.NewMessage(is_info=False, func=is_not_known_command))
def on_unknown_cmd(bot: Bot, accid: int, event: AttrDict) -> None:
    msg = event.msg
    chat = bot.rpc.get_basic_chat_info(accid, msg.chat_id)
    if chat.chat_type == ChatType.SINGLE:
        bot.rpc.markseen_msgs(accid, [msg.id])
        send_help(bot, accid, event.msg.chat_id)


@cli.on(events.NewMessage(command="/help"))
def _help(bot: Bot, accid: int, event: AttrDict) -> None:
    send_help(bot, accid, event.msg.chat_id)


def send_help(bot: Bot, accid: int, chat_id: int) -> None:
    text = """Hello, I'm a bot 🤖, with me you can subscribe group chats to RSS/Atom feeds.

**Available commands**

/sub URL - Subscribe current chat to the given feed.
    Examples:
    /sub https://delta.chat/feed.xml
    /sub https://delta.chat/feed.xml keyword

/unsub URL - Unsubscribe current chat from the given feed.
    Example:
    /unsub https://delta.chat/feed.xml

/list - List feed subscriptions in the group the command is sent.


**How to use me?**

Add me to a group then you can use the /sub command there to subscribe the group to RSS/Atom feeds.
    """
    bot.rpc.send_msg(accid, chat_id, {"text": text})


def _sub(max_feed_count: int, bot: Bot, accid: int, event: AttrDict) -> None:
    chat = bot.rpc.get_basic_chat_info(accid, event.msg.chat_id)
    args = event.payload.split(maxsplit=1)
    url = normalize_url(args[0]) if args else ""
    filter_ = args[1] if len(args) == 2 else ""

    with session_scope() as session:
        feed = session.execute(select(Feed).where(Feed.url == url)).scalar()
        if feed:
            try:
                d = parse_feed(feed.url)
            except Exception as ex:
                reply = {
                    "text": "❌ Invalid feed url.",
                    "quotedMessageId": event.msg.id,
                }
                bot.rpc.send_msg(accid, event.msg.chat_id, reply)
                bot.logger.exception("Invalid feed %s: %s", url, ex)
                return
        else:
            stmt = select(func.count()).select_from(  # noqa: func.count is callable
                Feed
            )
            if 0 <= max_feed_count <= session.execute(stmt).scalar_one():
                reply = {"text": "❌ Sorry, maximum number of feeds reached"}
                bot.rpc.send_msg(accid, event.msg.chat_id, reply)
                return
            try:
                d = parse_feed(url)
                feed = Feed(
                    url=url,
                    etag=d.get("etag"),
                    modified=d.get("modified") or d.get("updated"),
                    latest=get_latest_date(d.entries),
                )
                session.add(feed)
            except Exception as ex:
                reply = {
                    "text": "❌ Invalid feed url.",
                    "quotedMessageId": event.msg.id,
                }
                bot.rpc.send_msg(accid, event.msg.chat_id, reply)
                bot.logger.exception("Invalid feed %s: %s", url, ex)
                return

        if chat.chat_type == ChatType.SINGLE:
            chat_id = bot.rpc.create_group_chat(
                accid, d.feed.get("title") or url, False
            )
            bot.rpc.add_contact_to_chat(accid, chat_id, event.msg.from_id)
            url = d.feed.get("image", {}).get("href") or d.feed.get("logo")
            if url:
                set_group_image(bot, url, accid, chat_id)
        else:
            chat_id = event.msg.chat_id
            stmt = select(Fchat).where(
                Fchat.accid == accid, Fchat.gid == chat.id, Fchat.feed_url == feed.url
            )
            if session.execute(stmt).scalar():
                reply = {
                    "text": "❌ Chat already subscribed to that feed.",
                    "quotedMessageId": event.msg.id,
                }
                bot.rpc.send_msg(accid, chat_id, reply)
                return

        session.add(Fchat(accid=accid, gid=chat_id, feed_url=feed.url, filter=filter_))

    reply = {"text": _format_feed_info(d, feed.url, filter_)}

    if d.entries and feed.latest:
        reply["html"] = format_entries(
            get_old_entries(d.entries, tuple(map(int, feed.latest.split())))[:15],
            filter_,
        )

    bot.rpc.send_msg(accid, chat_id, reply)


def _format_feed_info(d: FeedParserDict, url: str, filter_: str) -> str:
    url = f"{url} ({filter_})" if filter_ else url
    title = d.feed.get("title") or "-"
    desc = d.feed.get("description") or "-"
    return f"Title: {title}\n\nURL: {url}\n\nDescription: {desc}"


@cli.on(events.NewMessage(command="/unsub"))
def _unsub(bot: Bot, accid: int, event: AttrDict) -> None:
    if not event.payload:
        _list(bot, accid, event)
        return

    msg = event.msg
    with session_scope() as session:
        stmt = select(Feed).where(Feed.url == normalize_url(event.payload))
        feed = session.execute(stmt).scalar()
        fchat = None
        if feed:
            stmt = select(Fchat).where(
                Fchat.accid == accid,
                Fchat.gid == msg.chat_id,
                Fchat.feed_url == feed.url,
            )
            fchat = session.execute(stmt).scalar()
        if fchat:
            session.delete(fchat)
            reply = {"text": f"Chat unsubscribed from: {feed.url}"}
            bot.rpc.send_msg(accid, msg.chat_id, reply)
        else:
            reply = {
                "text": "❌ This chat is not subscribed to that feed",
                "quotedMessageId": msg.id,
            }
            bot.rpc.send_msg(accid, msg.chat_id, reply)


@cli.on(events.NewMessage(command="/list"))
def _list(bot: Bot, accid: int, event: AttrDict) -> None:
    msg = event.msg
    chat = bot.rpc.get_basic_chat_info(accid, msg.chat_id)
    if chat.chat_type == ChatType.SINGLE:
        text = (
            "❌ You must send that command in the group where you have the subscriptions.\n"
            "You can check the groups you share with me in my profile"
        )
        reply = {"text": text, "quotedMessageId": msg.id}
    else:
        with session_scope() as session:
            stmt = select(Fchat).where(Fchat.accid == accid, Fchat.gid == msg.chat_id)
            fchats = session.execute(stmt).scalars()
            text = "\n\n".join(fchat.feed_url for fchat in fchats)
        reply = {"text": text or "❌ No feed subscriptions in this chat"}
    bot.rpc.send_msg(accid, msg.chat_id, reply)
