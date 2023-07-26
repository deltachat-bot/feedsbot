Feeds
=====

.. image:: https://github.com/simplebot-org/simplebot_feeds/actions/workflows/python-ci.yml/badge.svg
   :target: https://github.com/simplebot-org/simplebot_feeds/actions/workflows/python-ci.yml

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
   :target: https://github.com/psf/black

A `SimpleBot`_ plugin that allows to subscribe to RSS/Atom feeds.

Install
-------

To install run::

  pip install git+https://github.com/simplebot-org/simplebot_feeds

Configuration
-------------

By default the time (in seconds) between checks for feeds updates is 300 seconds (5 minutes), to change it::

  simplebot -a bot@example.com feeds --interval 600

To limit the total number of feeds subscriptions the bot will allow (by default it is unlimited)::

  simplebot -a bot@example.com feeds --max 1000

If this plugin has collisions with commands from other plugins in your bot, you can set a command prefix like ``/feed_`` for all commands::

  simplebot -a bot@example.com feeds --prefix feed_

User Guide
----------

To subscribe an existing group to some feed:

1. Add the bot to the group.
2. Send `/sub https://delta.chat/feed.xml` (replace the URL with the desired feed)

To subscribe to a feed and let the bot create a dedicated group for you with the feed image as group avatar, etc., just send the command `/sub https://delta.chat/feed.xml` (replacing the URL for the desired feed) to the bot in private/direct (1:1) chat.

To unsubscribe the group from all feeds, just remove the bot from the group, or to unsubscribe from a particular feed (replace feed URL as appropriate):

`/unsub https://delta.chat/feed.xml`

To see all feeds a group is subscribed to, just send `/list` inside the desired group.


.. _SimpleBot: https://github.com/simplebot-org/simplebot
