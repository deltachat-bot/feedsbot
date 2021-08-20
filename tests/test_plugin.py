class TestPlugin:
    """Online tests"""

    def test_sub(self, mocker) -> None:
        msg = mocker.get_one_reply("/sub")
        assert "❌" in msg.text

        msg = mocker.get_one_reply("/sub https://delta.chat/feed.xml")
        assert "❌" not in msg.text
        chat = msg.chat

        msg = mocker.get_one_reply("/sub https://delta.chat/feed.xml", group=chat)
        assert "❌" in msg.text

    def test_unsub(self, mocker) -> None:
        msg = mocker.get_one_reply("/unsub https://delta.chat/feed.xml")
        assert "❌" in msg.text

        msg = mocker.get_one_reply("/sub https://delta.chat/feed.xml")
        chat = msg.chat

        msg = mocker.get_one_reply("/unsub https://delta.chat/feed.xml", group=chat)
        assert "❌" not in msg.text

    def test_list(self, mocker) -> None:
        msg = mocker.get_one_reply("/list")
        assert "❌" in msg.text

        msg = mocker.get_one_reply("/list", group="group1")
        assert "❌" in msg.text

        msg = mocker.get_one_reply("/sub https://delta.chat/feed.xml")
        chat = msg.chat

        msg = mocker.get_one_reply("/list", group=chat)
        assert "❌" not in msg.text
