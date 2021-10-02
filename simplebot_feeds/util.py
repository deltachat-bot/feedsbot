"""Utilities"""

import datetime
import functools
import mimetypes
import os
import re
import sqlite3
import time
from tempfile import NamedTemporaryFile
from typing import Optional

import feedparser
import requests
from deltachat import Chat
from feedparser.datetimes import _parse_date
from feedparser.exceptions import CharacterEncodingOverride
from simplebot.bot import DeltaBot, Replies

from simplebot_feeds import db

session = requests.Session()
session.headers.update(
    {
        "user-agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/60.0"
    }
)
session.request = functools.partial(session.request, timeout=15)  # type: ignore


def check_feeds(bot: DeltaBot) -> None:
    while True:
        bot.logger.debug("Checking feeds")
        now = time.time()
        for f in db.manager.get_feeds():
            bot.logger.debug("Checking feed: %s", f["url"])
            try:
                _check_feed(bot, f)
                if f["errors"] != 0:
                    db.manager.set_feed_errors(f["url"], 0)
            except Exception as err:
                bot.logger.exception(err)
                if f["errors"] < 50:
                    db.manager.set_feed_errors(f["url"], f["errors"] + 1)
                    continue
                for gid in db.manager.get_fchats(f["url"]):
                    try:
                        replies = Replies(bot, logger=bot.logger)
                        replies.add(
                            text=f"❌ Due to errors, this chat was unsubscribed from feed: {f['url']}",
                            chat=bot.get_chat(gid),
                        )
                        replies.send_reply_messages()
                    except (ValueError, AttributeError):
                        pass
                db.manager.remove_feed(f["url"])
        bot.logger.debug("Done checking feeds")
        delay = int(get_default(bot, "delay")) - time.time() + now
        if delay > 0:
            time.sleep(delay)


def _check_feed(bot: DeltaBot, f: sqlite3.Row) -> None:
    d = parse_feed(f["url"], etag=f["etag"], modified=f["modified"])
    fchats = db.manager.get_fchats(f["url"])

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
            db.manager.remove_fchat(gid)

    latest = get_latest_date(d.entries) or f["latest"]
    modified = d.get("modified") or d.get("updated")
    db.manager.update_feed(f["url"], d.get("etag"), modified, latest)


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


def get_default(bot: DeltaBot, key: str, value=None) -> str:
    scope = __name__.split(".", maxsplit=1)[0]
    val = bot.get(key, scope=scope)
    if val is None and value is not None:
        bot.set(key, value, scope=scope)
        val = value
    return val


def init_db(bot: DeltaBot) -> None:
    path = os.path.join(
        os.path.dirname(bot.account.db_path), __name__.split(".", maxsplit=1)[0]
    )
    if not os.path.exists(path):
        os.makedirs(path)
    db.manager = db.DBManager(os.path.join(path, "sqlite.db"))


def parse_feed(
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
        headers["If-Modified-Since"] = "%s, %02d %s %04d %02d:%02d:%02d GMT" % (  # noqa
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
        dict_ = feedparser.parse(resp.text)
    bozo_exception = dict_.get("bozo_exception", ValueError("Invalid feed"))
    if (
        dict_.get("bozo")
        and not isinstance(bozo_exception, CharacterEncodingOverride)
        and not dict_.get("entries")
    ):
        raise bozo_exception
    return dict_


def get_img_ext(resp: requests.Response) -> str:
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


def normalize_url(url: str) -> str:
    if not url.startswith("http"):
        url = "http://" + url
    return url.rstrip("/")


def set_group_image(bot: DeltaBot, url: str, group: Chat) -> None:
    with session.get(url) as resp:
        if resp.status_code < 400 or resp.status_code >= 600:
            with NamedTemporaryFile(
                dir=bot.account.get_blobdir(),
                prefix="group-image-",
                suffix=get_img_ext(resp),
                delete=False,
            ) as file:
                path = file.name
            with open(path, "wb") as file:
                file.write(resp.content)
            try:
                group.set_profile_image(path)
            except ValueError as ex:
                bot.logger.exception(ex)
