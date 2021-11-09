"""Hooks and commands."""

from threading import Thread

import simplebot
from deltachat import Chat, Contact, Message
from pkg_resources import DistributionNotFound, get_distribution
from simplebot.bot import DeltaBot, Replies

from .util import (
    check_feeds,
    db,
    format_entries,
    get_default,
    get_latest_date,
    get_old_entries,
    init_db,
    normalize_url,
    parse_feed,
    set_group_image,
)

try:
    __version__ = get_distribution(__name__).version
except DistributionNotFound:
    # package is not installed
    __version__ = "0.0.0.dev0-unknown"


@simplebot.hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    init_db(bot)

    get_default(bot, "delay", 60 * 5)
    get_default(bot, "max_feed_count", -1)
    prefix = get_default(bot, "cmd_prefix", "")

    desc = f"Subscribe current chat to the given feed.\n\nExample:\n/{prefix}sub https://delta.chat/feed.xml\n/{prefix}sub https://delta.chat/feed.xml keyword"
    bot.commands.register(func=sub_cmd, name=f"/{prefix}sub", help=desc)
    desc = f"Unsubscribe current chat from the given feed.\n\nExample:\n/{prefix}unsub https://delta.chat/feed.xml"
    bot.commands.register(func=unsub_cmd, name=f"/{prefix}unsub", help=desc)
    bot.commands.register(func=list_cmd, name=f"/{prefix}list")


@simplebot.hookimpl
def deltabot_start(bot: DeltaBot) -> None:
    Thread(target=check_feeds, args=(bot,), daemon=True).start()


@simplebot.hookimpl
def deltabot_member_removed(bot: DeltaBot, chat: Chat, contact: Contact) -> None:
    me = bot.self_contact
    if me == contact or len(chat.get_contacts()) <= 1:
        db.manager.remove_fchat(chat.id)


def sub_cmd(bot: DeltaBot, payload: str, message: Message, replies: Replies) -> None:
    args = payload.split(maxsplit=1)
    url = normalize_url(args[0]) if args else ""
    filter_ = args[1] if len(args) == 2 else ""
    feed = dict(db.manager.get_feed(url) or {})

    if feed:
        try:
            d = parse_feed(feed["url"])
        except Exception as ex:
            replies.add(text="❌ Invalid feed url.", quote=message)
            bot.logger.exception("Invalid feed %s: %s", url, ex)
            return
    else:
        max_fc = int(get_default(bot, "max_feed_count"))
        if 0 <= max_fc <= db.manager.get_feeds_count():
            replies.add(text="❌ Sorry, maximum number of feeds reached")
            return
        try:
            d = parse_feed(url)
        except Exception as ex:
            replies.add(text="❌ Invalid feed url.", quote=message)
            bot.logger.exception("Invalid feed %s: %s", url, ex)
            return
        feed = dict(
            url=url,
            etag=d.get("etag"),
            modified=d.get("modified") or d.get("updated"),
            latest=get_latest_date(d.entries),
        )
        db.manager.add_feed(url, feed["etag"], feed["modified"], feed["latest"])

    if message.chat.is_group():
        chat = message.chat
        if chat.id in db.manager.get_fchat_ids(feed["url"]):
            replies.add(
                text="❌ Chat already subscribed to that feed.", chat=chat, quote=message
            )
            return
    else:
        chat = bot.create_group(
            d.feed.get("title") or url, [message.get_sender_contact()]
        )
        url = d.feed.get("image", {}).get("href") or d.feed.get("logo")
        if url:
            set_group_image(bot, url, chat)

    db.manager.add_fchat(chat.id, feed["url"], filter_)
    title = d.feed.get("title") or "-"
    desc = d.feed.get("description") or "-"
    url = f"{feed['url']} ({filter_})" if filter_ else feed["url"]
    text = f"Title: {title}\n\nURL: {url}\n\nDescription: {desc}"

    if d.entries and feed["latest"]:
        latest = tuple(map(int, feed["latest"].split()))
        html = format_entries(get_old_entries(d.entries, latest)[:15], filter_)
        replies.add(text=text, html=html, chat=chat)
    else:
        replies.add(text=text, chat=chat)


def unsub_cmd(payload: str, message: Message, replies: Replies) -> None:
    feed = db.manager.get_feed(normalize_url(payload))

    if not feed or message.chat.id not in db.manager.get_fchat_ids(feed["url"]):
        replies.add(text="❌ This chat is not subscribed to that feed", quote=message)
        return

    db.manager.remove_fchat(message.chat.id, feed["url"])
    replies.add(text=f"Chat unsubscribed from: {feed['url']}")


def list_cmd(message: Message, replies: Replies) -> None:
    """List feed subscriptions in the group the command is sent."""
    if message.chat.is_group():
        text = "\n\n".join(f["url"] for f in db.manager.get_feeds(message.chat.id))
        replies.add(text=text or "❌ No feed subscriptions in this chat")
    else:
        replies.add(
            text="❌ You must send that command in the group where you have the subscriptions",
            quote=message,
        )
