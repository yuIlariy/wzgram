#  Pyrogram - Telegram MTProto API Client Library for Python
#  Copyright (C) 2017-present Dan <https://github.com/delivrance>
#
#  This file is part of Pyrogram.
#
#  Pyrogram is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Lesser General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Pyrogram is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public License
#  along with Pyrogram.  If not, see <http://www.gnu.org/licenses/>.

"""Fuzz the raw union members through the hot _parse dispatch paths.

Regression guard for the WebPageEmpty crash class: a raw union member (or an
optional field that is None on the wire) must never reach an unguarded read
in a _parse method, because _parse runs on every incoming message/update.
"""

import inspect
import re
import types as stdlib_types

import pytest

from pyrogram import raw, types

_TYPE_DUMMIES = {int: 1, str: "x", bytes: b"x", bool: False, float: 0.5}
_PREFERRED_MEMBERS = {"Peer": "PeerUser"}


def _unwrap(ann):
    s = str(ann).replace("typing.", "")
    m = re.match(r"Optional\[(.+)\]", s)
    if m:
        return _unwrap(m.group(1))
    m = re.match(r"List\[(.+)\]", s)
    if m:
        return ("list", _unwrap(m.group(1)))
    m = re.match(r"ForwardRef\('(.+)'\)", s)
    if m:
        return m.group(1)
    return s


def _dummy_for(ann, depth=0):
    if depth > 4:
        return None
    if isinstance(ann, type):
        return _TYPE_DUMMIES.get(ann)
    s = _unwrap(ann)
    if isinstance(s, tuple):
        return []
    if s in ("int", "long", "int53", "int64"):
        return 1
    if s == "str":
        return "x"
    if s == "bytes":
        return b"x"
    if s == "bool":
        return False
    if s in ("double", "float"):
        return 0.5
    if s.startswith("raw.base."):
        prefix = s.split(".")[-1]
        members = [
            n for n in dir(raw.types)
            if n.startswith(prefix) and inspect.isclass(getattr(raw.types, n))
        ]
        if not members:
            return None
        name = _PREFERRED_MEMBERS.get(prefix)
        if name not in members:
            name = sorted(members)[0]
        return _dummy(getattr(raw.types, name), depth + 1)
    if s.startswith("raw.types."):
        cls = getattr(raw.types, s.split(".")[-1], None)
        return _dummy(cls, depth + 1) if cls else None
    return None


def _dummy(cls, depth=0):
    if cls is None:
        return None
    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return None
    kwargs = {}
    for name, p in sig.parameters.items():
        if name == "self" or p.default is not inspect.Parameter.empty:
            continue
        kwargs[name] = _dummy_for(p.annotation, depth)
    try:
        return cls(**kwargs)
    except Exception:
        return None


class _EmptyResult:
    users = []
    chats = []
    updates = []

    def __iter__(self):
        return iter([])


class _StubClient:
    def __init__(self):
        self.me = stdlib_types.SimpleNamespace(is_bot=False, is_premium=False)
        self.message_cache = {}
        self.topic_cache = {}
        self.fetch_topics = False
        self.fetch_stories = False
        self.fetch_replies = False

    async def invoke(self, *a, **k):
        return _EmptyResult()

    async def get_messages(self, *a, **k):
        return []

    async def get_stories(self, *a, **k):
        return []


def _members(prefix, exclude=()):
    return sorted(
        n for n in dir(raw.types)
        if n.startswith(prefix)
        and not any(n.startswith(e) for e in exclude)
        and inspect.isclass(getattr(raw.types, n))
    )


def _users():
    return {1: raw.types.User(id=1)}


@pytest.mark.parametrize("media_name", _members("MessageMedia"))
async def test_every_message_media_variant_parses_without_attribute_error(media_name):
    media = _dummy(getattr(raw.types, media_name))
    if media is None:
        pytest.skip("not constructible with dummies")

    message = raw.types.Message(
        id=1, peer_id=raw.types.PeerUser(user_id=1), date=0,
        message="x", media=media, entities=[],
    )

    await types.Message._parse(_StubClient(), message, _users(), {})


@pytest.mark.parametrize("webpage_name", _members("WebPage", exclude=("WebPageAttribute",)))
def test_every_webpage_variant_parses_without_attribute_error(webpage_name):
    webpage = _dummy(getattr(raw.types, webpage_name))
    if webpage is None:
        pytest.skip("not constructible with dummies")

    parsed = types.WebPage._parse(None, raw.types.MessageMediaWebPage(webpage=webpage))
    assert parsed is None or isinstance(parsed, types.WebPage)


@pytest.mark.parametrize("photo_name", _members("Photo", exclude=("PhotoSize", "PhotoCached", "PhotoPath", "PhotoStripped")))
def test_every_photo_variant_parses_without_attribute_error(photo_name):
    photo = _dummy(getattr(raw.types, photo_name))
    if photo is None:
        pytest.skip("not constructible with dummies")

    types.Photo._parse(None, photo)


async def test_a_message_without_entities_parses():
    # entities is flags-optional in TL and can be None on the wire
    message = raw.types.Message(
        id=1, peer_id=raw.types.PeerUser(user_id=1), date=0, message="x", entities=None,
    )

    parsed = await types.Message._parse(_StubClient(), message, _users(), {})

    assert parsed.text == "x"
    assert parsed.entities is None


async def test_a_message_without_a_known_peer_does_not_crash():
    # chat is None when the peer is missing from users/chats
    message = raw.types.Message(
        id=1, peer_id=raw.types.PeerUser(user_id=999), date=0, message="x", entities=[],
    )

    parsed = await types.Message._parse(_StubClient(), message, _users(), {})

    assert parsed.text == "x"
    assert parsed.chat is None


async def test_a_chat_background_with_an_empty_document_does_not_crash():
    background = raw.types.WallPaper(
        id=1, access_hash=2, slug="s",
        document=raw.types.DocumentEmpty(id=5),
        creator=None, default=False, pattern=None, dark=False, settings=None,
    )

    parsed = types.ChatBackground._parse(_StubClient(), background)

    assert parsed is not None
    assert parsed.document is None
