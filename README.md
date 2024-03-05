# Feeds

[![Latest Release](https://img.shields.io/pypi/v/feedsbot.svg)](https://pypi.org/project/feedsbot)
[![CI](https://github.com/deltachat-bot/feedsbot/actions/workflows/python-ci.yml/badge.svg)](https://github.com/deltachat-bot/feedsbot/actions/workflows/python-ci.yml)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Delta Chat bot that allows to subscribe to RSS/Atom feeds.

## Install

```sh
pip install feedsbot
```

Configure the bot:

```sh
feedsbot init bot@example.com PASSWORD
```

Start the bot:

```sh
feedsbot serve
```

Run `feedsbot --help` to see all available options.

## User Guide

To subscribe an existing group to some feed:

1. Add the bot to the group.
2. Send `/sub https://delta.chat/feed.xml` (replace the URL with the desired feed)

To subscribe to a feed and let the bot create a dedicated group for you with the feed image as group avatar, etc., just send the command `/sub https://delta.chat/feed.xml` (replacing the URL for the desired feed) to the bot in private/direct (1:1) chat.

To unsubscribe the group from all feeds, just remove the bot from the group, or to unsubscribe from a particular feed (replace feed URL as appropriate):

`/unsub https://delta.chat/feed.xml`

To see all feeds a group is subscribed to, just send `/list` inside the desired group.
