Feeds
=====

.. image:: https://img.shields.io/pypi/v/simplebot_feeds.svg
   :target: https://pypi.org/project/simplebot_feeds

.. image:: https://img.shields.io/pypi/pyversions/simplebot_feeds.svg
   :target: https://pypi.org/project/simplebot_feeds

.. image:: https://pepy.tech/badge/simplebot_feeds
   :target: https://pepy.tech/project/simplebot_feeds

.. image:: https://img.shields.io/pypi/l/simplebot_feeds.svg
   :target: https://pypi.org/project/simplebot_feeds

.. image:: https://github.com/simplebot-org/simplebot_feeds/actions/workflows/python-ci.yml/badge.svg
   :target: https://github.com/simplebot-org/simplebot_feeds/actions/workflows/python-ci.yml

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
   :target: https://github.com/psf/black

A `SimpleBot`_ plugin that allows to subscribe to RSS/Atom feeds.

Install
-------

To install run::

  pip install simplebot-feeds

Configuration
-------------

By default the time (in seconds) between checks for feeds updates is 300 seconds (5 minutes), to change it::

  simplebot -a bot@example.com db -s simplebot_feeds/delay 600

To limit the total number of feeds subscriptions the bot will allow::

  simplebot -a bot@example.com db -s simplebot_feeds/max_feed_count 1000

If this plugin has collisions with commands from other plugins in your bot, you can set a command prefix like ``/feed_`` for all commands::

  simplebot -a bot@example.com db -s simplebot_feeds/command_prefix feed_

.. _SimpleBot: https://github.com/simplebot-org/simplebot
