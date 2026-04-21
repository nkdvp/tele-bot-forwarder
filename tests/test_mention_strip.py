from bot.forwarder.relay import strip_mentions


def test_strips_standalone_mention():
    assert strip_mentions("Hey @nicky can you help?") == "Hey can you help?"


def test_preserves_email():
    assert strip_mentions("Send to abc@gmail.com please") == "Send to abc@gmail.com please"


def test_strips_mention_at_start():
    assert strip_mentions("@john what do you think?") == "what do you think?"


def test_strips_mention_at_end():
    assert strip_mentions("Thanks @bob") == "Thanks"


def test_strips_multiple_mentions():
    assert strip_mentions("@alice and @bob please review") == "and please review"


def test_preserves_email_with_subdomain():
    assert strip_mentions("user@domain.org sent this") == "user@domain.org sent this"


def test_empty_string():
    assert strip_mentions("") == ""


def test_only_mention_becomes_empty():
    assert strip_mentions("@nicky") == ""


def test_collapses_extra_whitespace():
    assert strip_mentions("hello @x world") == "hello world"
