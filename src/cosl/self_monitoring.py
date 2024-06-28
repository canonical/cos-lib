#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.


import json
import logging
import socket
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Mapping, Iterable, Sequence, TypedDict

from cosl.juju_topology import JujuTopology

import ops

from cosl.helpers import check_libs_installed


logger = logging.getLogger(__name__)

_EndpointMapping=TypedDict(
    '_EndpointMapping',
{'tracing':str, 
    'logging':str,
    'grafana-dashboards':str,
    'metrics':str},
    total=True
)

_EndpointMappingOverrides=TypedDict(
    '_EndpointMappingOverrides',
    {'tracing':str,
    'logging':str,
    'grafana-dashboards':str,
    'metrics':str},
    total=False
)

class SelfMonitoring(ops.Object):
    """Self monitoring integrations wrapper."""

    _endpoints:_EndpointMapping = {
        "grafana-dashboards": "grafana-dashboards",
        "logging": "logging",
        "metrics": "metrics-endpoint",
        "tracing": "tracing",
    }


    def __init__(self,
                 charm: ops.CharmBase,
                 external_url: str, # the ingressed url if we have ingress, else fqdn
                 cert_handler: Optional[CertHandler] = None,
                 endpoints: Optional[_EndpointMappingOverrides] = None,
                 
                 ):  # type: ignore
        super().__init__(charm, key="server")

        # TODO: Question: Should we allow disabling individual integrations?
        _endpoints = self._endpoints
        _endpoints.update(endpoints or {})
