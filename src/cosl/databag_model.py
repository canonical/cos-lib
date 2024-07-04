#!/usr/bin/env python3
# Copyright 2024 Canonical
# See LICENSE file for licensing details.

"""DatabagModel implementation from traefik.v1.ingress charm lib."""

import json
import logging
from typing import MutableMapping, Optional, cast

import pydantic

logger = logging.getLogger(__name__)


_RawDatabag = MutableMapping[str, str]

class DataValidationError(Exception):
    """Raised when relation databag validation fails."""


PYDANTIC_IS_V1 = int(pydantic.version.VERSION.split(".")[0]) < 2
if PYDANTIC_IS_V1:

    class DatabagModel(pydantic.BaseModel):  # type: ignore
        """Base databag model."""

        class Config:
            """Pydantic config."""

            allow_population_by_field_name = True
            """Allow instantiating this class by field name (instead of forcing alias)."""

        _NEST_UNDER = None

        @classmethod
        def load(cls, databag: _RawDatabag) -> "DatabagModel":
            """Load this model from a Juju databag."""
            if cls._NEST_UNDER:
                return cast(DatabagModel, cls.parse_obj(json.loads(databag[cls._NEST_UNDER]))) # type: ignore

            try:
                data = {
                    k: json.loads(v)
                    for k, v in databag.items()
                    # Don't attempt to parse model-external values
                    if k in {f.alias for f in cls.__fields__.values()}  # type: ignore
                }
            except json.JSONDecodeError as e:
                msg = f"invalid databag contents: expecting json. {databag}"
                logger.error(msg)
                raise DataValidationError(msg) from e

            try:
                return cls.parse_raw(json.dumps(data))  # type: ignore
            except pydantic.ValidationError as e:
                msg = f"failed to validate databag: {databag}"
                logger.debug(msg, exc_info=True)
                raise DataValidationError(msg) from e

        def dump(self, databag: Optional[_RawDatabag] = None, clear: bool = True):
            """Write the contents of this model to Juju databag.

            :param databag: the databag to write the data to.
            :param clear: ensure the databag is cleared before writing it.
            """
            if clear and databag:
                databag.clear()

            if databag is None:
                databag = {}

            if self._NEST_UNDER:
                databag[self._NEST_UNDER] = self.json(by_alias=True, exclude_defaults=True) # type: ignore
                return databag

            for key, value in self.dict(by_alias=True, exclude_defaults=True).items():  # type: ignore
                databag[key] = json.dumps(value)

            return databag

else:
    from pydantic import ConfigDict

    class DatabagModel(pydantic.BaseModel):
        """Base databag model."""

        model_config = ConfigDict(
            # tolerate additional keys in databag
            extra="ignore",
            # Allow instantiating this class by field name (instead of forcing alias).
            populate_by_name=True,
            # Custom config key: whether to nest the whole datastructure (as json)
            # under a field or spread it out at the toplevel.
            _NEST_UNDER=None,
            # TODO: Check if this is necessary / good to have
            # Protected namespaces: will warn if keys starts with those
            protected_namespaces=(),
        )  # type: ignore
        """Pydantic config."""

        @classmethod
        def load(cls, databag: _RawDatabag):
            """Load this model from a Juju databag."""
            nest_under = cls.model_config.get("_NEST_UNDER")
            if nest_under:
                return cls.model_validate(json.loads(databag[nest_under]))  # type: ignore

            try:
                data = {
                    k: json.loads(v)
                    for k, v in databag.items()
                    # Don't attempt to parse model-external values
                    if k in {(f.alias or n) for n, f in cls.__fields__.items()}  # type: ignore
                }
            except json.JSONDecodeError as e:
                msg = f"invalid databag contents: expecting json. {databag}"
                logger.error(msg)
                raise DataValidationError(msg) from e

            try:
                return cls.model_validate_json(json.dumps(data))  # type: ignore
            except pydantic.ValidationError as e:
                msg = f"failed to validate databag: {databag}"
                logger.debug(msg, exc_info=True)
                raise DataValidationError(msg) from e

        def dump(self, databag: Optional[_RawDatabag] = None, clear: bool = True):
            """Write the contents of this model to Juju databag.

            :param databag: the databag to write the data to.
            :param clear: ensure the databag is cleared before writing it.
            """
            if clear and databag:
                databag.clear()

            if databag is None:
                databag = {}
            nest_under = self.model_config.get("_NEST_UNDER")
            if nest_under:
                databag[nest_under] = self.model_dump_json(  # type: ignore
                    by_alias=True,
                    # skip keys whose values are default
                    exclude_defaults=True,
                )
                return databag

            dct = self.model_dump(mode="json", by_alias=True, exclude_defaults=True)  # type: ignore
            databag.update({k: json.dumps(v) for k, v in dct.items()})
            return databag
