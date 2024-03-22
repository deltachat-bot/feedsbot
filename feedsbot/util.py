"""Utilities"""

import datetime
import functools
import mimetypes
import re
import time
from multiprocessing.pool import ThreadPool
from tempfile import NamedTemporaryFile
from typing import Optional

import bs4
import feedparser
import requests
from deltabot_cli import Bot, JsonRpcError
from feedparser.datetimes import _parse_date
from feedparser.exceptions import CharacterEncodingOverride
from sqlalchemy import delete, select, update

from .orm import Fchat, Feed, session_scope

www = requests.Session()
www.headers.update(
    {
        "user-agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:60.0) Gecko/20100101 Firefox/60.0"
    }
)
www.request = functools.partial(www.request, timeout=15)  # type: ignore


def check_feeds(bot: Bot, interval: int, pool_size: int) -> None:
    lastcheck_key = "ui.feedsbot.lastcheck"
    lastcheck = float(bot.rpc.get_config(lastcheck_key) or 0)
    took = max(time.time() - lastcheck, 0)

    with ThreadPool(pool_size) as pool:
        while True:
            delay = interval - took
            if delay > 0:
                bot.logger.info(f"[WORKER] Sleeping for {delay:.1f} seconds")
                time.sleep(delay)
            bot.logger.info("[WORKER] Starting to check feeds")
            lastcheck = time.time()
            bot.rpc.set_config(lastcheck_key, str(lastcheck))
            with session_scope() as session:
                feeds = session.execute(select(Feed)).scalars().all()
            bot.logger.info(f"[WORKER] There are {len(feeds)} feeds to check")
            for _ in pool.imap_unordered(lambda f: _check_feed_task(bot, f), feeds):
                pass
            took = time.time() - lastcheck
            bot.logger.info(
                f"[WORKER] Done checking {len(feeds)} feeds after {took:.1f} seconds"
            )


def _check_feed_task(bot: Bot, feed: Feed):
    bot.logger.debug(f"Checking feed: {feed.url}")
    try:
        _check_feed(bot, feed)
        if feed.errors != 0:
            with session_scope() as session:
                stmt = update(Feed).where(Feed.url == feed.url).values(errors=0)
                session.execute(stmt)
    except Exception as err:
        bot.logger.exception(err)
        if feed.errors < 50:
            with session_scope() as session:
                stmt = update(Feed).where(Feed.url == feed.url)
                session.execute(stmt.values(errors=feed.errors + 1))
        else:
            with session_scope() as session:
                stmt = select(Fchat.accid, Fchat.gid).where(Fchat.feed_url == feed.url)
                fchats = session.execute(stmt).all()
                session.execute(delete(Feed).where(Feed.url == feed.url))
            reply = {
                "text": f"❌ Due to errors, this chat was unsubscribed from feed: {feed.url}"
            }
            for accid, gid in fchats:
                try:
                    bot.rpc.send_msg(accid, gid, reply)
                except JsonRpcError:
                    pass
    bot.logger.debug(f"Done checking feed: {feed.url}")


def _check_feed(bot: Bot, feed: Feed) -> None:
    d = parse_feed(feed.url, etag=feed.etag, modified=feed.modified)

    if d.entries and feed.latest:
        d.entries = get_new_entries(d.entries, tuple(map(int, feed.latest.split())))
    if not d.entries:
        return

    full_html = format_entries(d.entries[:100], "")
    with session_scope() as session:
        stmt = select(Fchat).where(Fchat.feed_url == feed.url)
        fchats = session.execute(stmt).scalars().all()
        if not fchats:
            session.delete(feed)
            return

    for fchat in fchats:
        if fchat.filter:
            html = format_entries(d.entries[:100], fchat.filter)
            if not html:
                continue
        else:
            html = full_html
        reply = {"html": html, "OverrideSenderName": d.feed.get("title") or feed.url}
        try:
            bot.rpc.send_msg(fchat.accid, fchat.gid, reply)
        except JsonRpcError:
            with session_scope() as session:
                stmt = delete(Fchat).where(
                    Fchat.accid == fchat.accid, Fchat.gid == fchat.gid
                )
                session.execute(stmt)

    latest = get_latest_date(d.entries) or feed.latest
    modified = d.get("modified") or d.get("updated")
    with session_scope() as session:
        stmt = update(Feed).where(Feed.url == feed.url)
        session.execute(
            stmt.values(etag=d.get("etag"), modified=modified, latest=latest)
        )


def format_entries(entries: list, filter_: str) -> str:
    entries_text = []
    for e in entries:
        pub_date, title, desc = _parse_entry(e)
        if filter_ not in title and filter_ not in desc:
            continue
        text = title + pub_date + desc
        if text:
            entries_text.append(text)

    return "<br/><hr/>".join(entries_text)


def _parse_entry(entry) -> tuple:
    title = entry.get("title") or ""
    pub_date = entry.get("published") or ""
    desc = entry.get("description") or ""
    if not desc and entry.get("content"):
        for c in entry.get("content"):
            if c.get("type") == "text/html":
                desc += c["value"]

    if title:
        desc_soup = bs4.BeautifulSoup(desc, "html5lib")
        for tag in desc_soup("br"):
            tag.replace_with("\n")
        title_soup = bs4.BeautifulSoup(title.rstrip("."), "html5lib")
        if " ".join(desc_soup.get_text().split()).startswith(
            " ".join(title_soup.get_text().split())
        ):
            title = ""

    if title:
        title = f'<a href="{entry.get("link") or ""}"><h3>{title}</h3></a>'
    elif pub_date:
        pub_date = f'<a href="{entry.get("link") or ""}">{pub_date}</a>'
    elif desc:
        desc = f'<a href="{entry.get("link") or ""}">{desc}</a>'

    if pub_date:
        pub_date = f"<p>📆 <small><em>{pub_date}</em></small></p>"

    return pub_date, title, desc


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


def parse_feed(
    url: str, etag: Optional[str] = None, modified: Optional[tuple] = None
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
    with www.get(url, headers=headers) as resp:
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


def set_group_image(bot: Bot, url: str, accid: int, chatid: int) -> None:
    with www.get(url) as resp:
        if resp.status_code < 400 or resp.status_code >= 600:
            with NamedTemporaryFile(suffix=get_img_ext(resp)) as temp_file:
                with open(temp_file.name, "wb") as file:
                    file.write(resp.content)
                try:
                    bot.rpc.set_chat_profile_image(accid, chatid, temp_file.name)
                except JsonRpcError as ex:
                    bot.logger.exception(ex)
