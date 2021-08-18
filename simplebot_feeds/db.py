import sqlite3
from typing import Iterator, Optional


class DBManager:
    def __init__(self, db_path: str) -> None:
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.execute("PRAGMA foreign_keys = ON;")
            self.db.execute(
                """CREATE TABLE IF NOT EXISTS feeds
                (url TEXT PRIMARY KEY,
                etag TEXT,
                modified TEXT,
                latest TEXT,
                errors INTEGER DEFAULT 0)"""
            )
            self.db.execute(
                """CREATE TABLE IF NOT EXISTS fchats
                (gid INTEGER,
                feed TEXT REFERENCES feeds(url) ON DELETE CASCADE,
                 PRIMARY KEY(gid, feed))"""
            )

    def execute(self, statement: str, args=()) -> sqlite3.Cursor:
        return self.db.execute(statement, args)

    def commit(self, statement: str, args=()) -> sqlite3.Cursor:
        with self.db:
            return self.db.execute(statement, args)

    def close(self) -> None:
        self.db.close()

    # ==== feeds =====

    def add_feed(self, url: str, etag: str, modified: str, latest: str) -> None:
        url = self.normalize_url(url)
        with self.db:
            self.db.execute(
                "INSERT INTO feeds VALUES (?,?,?,?)", (url, etag, modified, latest)
            )

    def remove_feed(self, url: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM feeds WHERE url=?", (url,))
            self.db.execute("DELETE FROM fchats WHERE feed=?", (url,))

    def update_feed(
        self,
        url: str,
        etag: Optional[str],
        modified: Optional[str],
        latest: Optional[str],
    ) -> None:
        q = "UPDATE feeds SET etag=?, modified=?, latest=? WHERE url=?"
        self.commit(q, (etag, modified, latest, url))

    def set_feed_errors(self, url: str, errors: int) -> None:
        self.commit("UPDATE feeds SET errors=? WHERE url=?", (errors, url))

    def get_feed(self, url: str) -> Optional[sqlite3.Row]:
        url = self.normalize_url(url)
        return self.db.execute("SELECT * FROM feeds WHERE url=?", (url,)).fetchone()

    def get_feeds_count(self) -> int:
        return self.db.execute("SELECT count(*) FROM feeds").fetchone()[0]

    def get_feeds(self, gid: int = None) -> Iterator[sqlite3.Row]:
        if gid is None:
            for row in self.db.execute("SELECT * FROM feeds"):
                yield row
            return
        rows = self.db.execute("SELECT feed FROM fchats WHERE gid=?", (gid,)).fetchall()
        if not rows:
            return
        rows = [r[0] for r in rows]
        q = "SELECT * FROM feeds WHERE "
        q += " or ".join("url=?" for r in rows)
        for row in self.db.execute(q, rows):
            yield row

    def add_fchat(self, gid: int, url: str) -> None:
        url = self.normalize_url(url)
        self.commit("INSERT INTO fchats VALUES (?,?)", (gid, url))

    def remove_fchat(self, gid: int, url: str = None) -> None:
        if url:
            rows = self.db.execute(
                "SELECT feed FROM fchats WHERE gid=? AND feed=?", (gid, url)
            )
        else:
            rows = self.db.execute("SELECT feed FROM fchats WHERE gid=?", (gid,))
        for row in rows:
            fchats_count = self.db.execute(
                "SELECT count(*) FROM fchats WHERE feed=?", (row[0],)
            ).fetchone()[0]
            if fchats_count <= 1:
                self.remove_feed(row[0])
        if url:
            self.commit("DELETE FROM fchats WHERE gid=? AND feed=?", (gid, url))
        else:
            self.commit("DELETE FROM fchats WHERE gid=?", (gid,))

    def get_fchats(self, url: str) -> Iterator[int]:
        url = self.normalize_url(url)
        for row in self.db.execute("SELECT gid FROM fchats WHERE feed=?", (url,)):
            yield row[0]

    def normalize_url(self, url: str) -> str:
        if not url.startswith("http"):
            url = "http://" + url
        if url.endswith("/"):
            url = url[:-1]
        return url
