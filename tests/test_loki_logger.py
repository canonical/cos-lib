# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from unittest.mock import patch

from src.cosl.loki_logger import LokiHandler


@patch("src.cosl.loki_logger.LokiEmitter._send_request")
def test_root_logging(send_request):
    root_logger = logging.getLogger()
    u1 = "http://foo.com"
    u2 = "https://bar.org/push/v1/hey"

    added = []
    for url in [u1, u2]:
        handler = LokiHandler(url=url, tags={"1": "2"})

        root_logger.addHandler(handler)
        added.append(handler)

    try:
        any_logger = logging.getLogger("test-foo")
        any_logger.setLevel("INFO")

        any_logger.info("hey there")
        any_logger.error("boo!")

    finally:
        for handler in added:
            root_logger.removeHandler(handler)

    assert send_request.call_count == 4
    assert [call.args[0].full_url for call in send_request.call_args_list] == [u1, u2, u1, u2]
    assert [
        json.loads(call.args[1].decode("utf-8"))["streams"][0]["stream"]["severity"]
        for call in send_request.call_args_list
    ] == ["info", "info", "error", "error"]
    assert [
        json.loads(call.args[1].decode("utf-8"))["streams"][0]["values"][0][1]
        for call in send_request.call_args_list
    ] == ["hey there", "hey there", "boo!", "boo!"]
