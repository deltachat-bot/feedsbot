import datetime
import functools
import itertools
import mimetypes
import os
import re
import sqlite3
import time
from tempfile import NamedTemporaryFile
from threading import Thread
from typing import Optional

import feedparser
import html2text
import requests
import simplebot
from deltachat import Chat, Contact, Message
from feedparser.datetimes import _parse_date
from feedparser.exceptions import CharacterEncodingOverride
from pkg_resources import DistributionNotFound, get_distribution
from simplebot.bot import DeltaBot, Replies

from .db import DBManager

try:
    __version__ = get_distribution(__name__).version
except DistributionNotFound:
    # package is not installed
    __version__ = "0.0.0.dev0-unknown"
session = requests.Session()
session.headers.update(
    {
        "user-agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/60.0"
    }
)
session.request = functools.partial(session.request, timeout=15)  # type: ignore
html2text.config.WRAP_LINKS = False
db: DBManager


@simplebot.hookimpl
def deltabot_init(bot: DeltaBot) -> None:
    global db
    db = _get_db(bot)

    _getdefault(bot, "delay", 60 * 5)
    _getdefault(bot, "max_feed_count", -1)
    prefix = _getdefault(bot, "cmd_prefix", "")

    desc = f"Subscribe current chat to the given feed.\n\nExample:\n/{prefix}sub https://delta.chat/feed.xml"
    bot.commands.register(func=sub_cmd, name=f"/{prefix}sub", help=desc)
    desc = f"Unsubscribe current chat from the given feed.\n\nExample:\n/{prefix}unsub https://delta.chat/feed.xml"
    bot.commands.register(func=unsub_cmd, name=f"/{prefix}unsub", help=desc)
    bot.commands.register(func=list_cmd, name=f"/{prefix}list")


@simplebot.hookimpl
def deltabot_start(bot: DeltaBot) -> None:
    Thread(target=_check_feeds, args=(bot,), daemon=True).start()


@simplebot.hookimpl
def deltabot_member_removed(bot: DeltaBot, chat: Chat, contact: Contact) -> None:
    me = bot.self_contact
    if me == contact or len(chat.get_contacts()) <= 1:
        db.remove_fchat(chat.id)


def sub_cmd(bot: DeltaBot, payload: str, message: Message, replies: Replies) -> None:
    url = _normalize_url(payload)
    feed = db.get_feed(url)

    if feed:
        d = _parse(feed["url"])
    else:
        max_fc = int(_getdefault(bot, "max_feed_count"))
        if 0 <= max_fc <= db.get_feeds_count():
            replies.add(text="❌ Sorry, maximum number of feeds reached")
            return
        d = _parse(url)
        bozo_exception = d.get("bozo_exception", "")
        if (
            d.get("bozo") == 1
            and not isinstance(bozo_exception, CharacterEncodingOverride)
        ) or not d.entries:
            replies.add(text="❌ Invalid feed url.", quote=message)
            bot.logger.warning("Invalid feed %s: %s", url, bozo_exception)
            return
        feed = dict(
            url=url,
            etag=d.get("etag"),
            modified=d.get("modified") or d.get("updated"),
            latest=get_latest_date(d.entries),
        )
        db.add_feed(url, feed["etag"], feed["modified"], feed["latest"])
    assert feed

    if message.chat.is_group():
        chat = message.chat
        if chat.id in db.get_fchats(feed["url"]):
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
            with session.get(url) as resp:
                if resp.status_code < 400 or resp.status_code >= 600:
                    with NamedTemporaryFile(
                        dir=bot.account.get_blobdir(),
                        prefix="group-image-",
                        suffix=_get_img_ext(resp),
                        delete=False,
                    ) as file:
                        path = file.name
                    with open(path, "wb") as file:
                        file.write(resp.content)
                    try:
                        chat.set_profile_image(path)
                    except ValueError as ex:
                        bot.logger.exception(ex)

    db.add_fchat(chat.id, feed["url"])
    title = d.feed.get("title") or "-"
    desc = d.feed.get("description") or "-"
    text = f"Title: {title}\n\nURL: {feed['url']}\n\nDescription: {desc}"

    if d.entries and feed["latest"]:
        latest = tuple(map(int, feed["latest"].split()))
        html = format_entries(get_old_entries(d.entries, latest)[:5])
        replies.add(text=text, html=html, chat=chat)
    else:
        replies.add(text=text, chat=chat)


def unsub_cmd(payload: str, message: Message, replies: Replies) -> None:
    feed = db.get_feed(_normalize_url(payload))

    if not feed or message.chat.id not in db.get_fchats(feed["url"]):
        replies.add(text="❌ This chat is not subscribed to that feed", quote=message)
        return

    db.remove_fchat(message.chat.id, feed["url"])
    replies.add(text=f"Chat unsubscribed from: {feed['url']}")


def list_cmd(message: Message, replies: Replies) -> None:
    """List feed subscriptions in the group the command is sent."""
    if message.chat.is_group():
        text = "\n\n".join(f["url"] for f in db.get_feeds(message.chat.id))
        replies.add(text=text or "❌ No feed subscriptions in this chat")
    else:
        replies.add(
            text="❌ You must send that command in the group where you have the subscriptions",
            quote=message,
        )


def _check_feeds(bot: DeltaBot) -> None:
    while True:
        bot.logger.debug("Checking feeds")
        now = time.time()
        for f in db.get_feeds():
            bot.logger.debug("Checking feed: %s", f["url"])
            try:
                _check_feed(bot, f)
                if f["errors"] != 0:
                    db.set_feed_errors(f["url"], 0)
            except Exception as err:
                bot.logger.exception(err)
                if f["errors"] < 50:
                    db.set_feed_errors(f["url"], f["errors"] + 1)
                    continue
                for gid in db.get_fchats(f["url"]):
                    try:
                        replies = Replies(bot, logger=bot.logger)
                        replies.add(
                            text=f"❌ Due to errors, this chat was unsubscribed from feed: {f['url']}",
                            chat=bot.get_chat(gid),
                        )
                        replies.send_reply_messages()
                    except (ValueError, AttributeError):
                        pass
                db.remove_feed(f["url"])
        bot.logger.debug("Done checking feeds")
        delay = int(_getdefault(bot, "delay")) - time.time() + now
        if delay > 0:
            time.sleep(delay)


def _check_feed(bot: DeltaBot, f: sqlite3.Row) -> None:
    d = _parse(f["url"], etag=f["etag"], modified=f["modified"])
    fchats = db.get_fchats(f["url"])

    bozo_exception = d.get("bozo_exception", ValueError("Invalid feed"))
    if (
        d.get("bozo")
        and not isinstance(bozo_exception, CharacterEncodingOverride)
        and not d.get("entries")
    ):
        raise bozo_exception

    if d.entries and f["latest"]:
        d.entries = get_new_entries(d.entries, tuple(map(int, f["latest"].split())))
    if not d.entries:
        return

    html = format_entries(d.entries[:100])
    for gid in fchats:
        try:
            replies = Replies(bot, logger=bot.logger)
            replies.add(html=html, chat=bot.get_chat(gid))
            replies.send_reply_messages()
        except (ValueError, AttributeError):
            db.remove_fchat(gid)

    latest = get_latest_date(d.entries) or f["latest"]
    modified = d.get("modified") or d.get("updated")
    db.update_feed(f["url"], d.get("etag"), modified, latest)


def format_entries(entries: list) -> str:
    entries_text = []
    for e in entries:
        t = f'<a href="{e.get("link") or ""}"><h3>{e.get("title") or "NO TITLE"}</h3></a>'
        pub_date = e.get("published")
        if pub_date:
            t += f"<p>📆 <small><em>{pub_date}</em></small></p>"
        desc = e.get("description") or ""
        if not desc and e.get("content"):
            for c in e.get("content"):
                if c.get("type") == "text/html":
                    desc += c["value"]
        if desc and desc != e.get("title"):
            t += desc
        entries_text.append(t)
    return "<br><hr>".join(entries_text)


def get_new_entries(entries: list, date: tuple) -> list:
    new_entries = []
    for e in entries:
        d = e.get("published_parsed") or e.get("updated_parsed")
        if d is not None and d > date:
            new_entries.append(e)
    return new_entries


def get_old_entries(entries: list, date: tuple) -> list:
    old_entries = []
    for e in entries:
        d = e.get("published_parsed") or e.get("updated_parsed")
        if d is not None and d <= date:
            old_entries.append(e)
    return old_entries


def get_latest_date(entries: list) -> Optional[str]:
    dates = []
    for e in entries:
        d = e.get("published_parsed") or e.get("updated_parsed")
        if d:
            dates.append(d)
    return " ".join(map(str, max(dates))) if dates else None


def _getdefault(bot: DeltaBot, key: str, value=None) -> str:
    val = bot.get(key, scope=__name__)
    if val is None and value is not None:
        bot.set(key, value, scope=__name__)
        val = value
    return val


def _get_db(bot: DeltaBot) -> DBManager:
    path = os.path.join(os.path.dirname(bot.account.db_path), __name__)
    if not os.path.exists(path):
        os.makedirs(path)
    return DBManager(os.path.join(path, "sqlite.db"))


def _parse(
    url: str, etag: str = None, modified: tuple = None
) -> feedparser.FeedParserDict:
    headers = {"A-IM": "feed", "Accept-encoding": "gzip, deflate"}
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        if isinstance(modified, str):
            modified = _parse_date(modified)
        elif isinstance(modified, datetime.datetime):
            modified = modified.utctimetuple()
        short_weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        months = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        headers["If-Modified-Since"] = "%s, %02d %s %04d %02d:%02d:%02d GMT" % (
            short_weekdays[modified[6]],
            modified[2],
            months[modified[1] - 1],
            modified[0],
            modified[3],
            modified[4],
            modified[5],
        )
    with session.get(url, headers=headers) as resp:
        resp.raise_for_status()
        return feedparser.parse(resp.text)


def _get_img_ext(resp: requests.Response) -> str:
    disp = resp.headers.get("content-disposition")
    if disp is not None and re.findall("filename=(.+)", disp):
        fname = re.findall("filename=(.+)", disp)[0].strip('"')
    else:
        fname = resp.url.split("/")[-1].split("?")[0].split("#")[0]
    if "." in fname:
        ext = "." + fname.rsplit(".", maxsplit=1)[-1]
    else:
        ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        if ctype == "image/jpeg":
            ext = ".jpg"
        else:
            ext = mimetypes.guess_extension(ctype)
    return ext


def _normalize_url(url: str) -> str:
    if not url.startswith("http"):
        url = "http://" + url
    return url.rstrip("/")
