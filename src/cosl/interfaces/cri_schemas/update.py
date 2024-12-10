#!/usr/bin/env python3
# Copyright 2024 Canonical
# See LICENSE file for licensing details.

"""Utilities to download schemas from charm-relation-interfaces.

This to work around the fact that charm-relation-interfaces is not on pypi.
"""

from pathlib import Path
import shlex
from shutil import rmtree
from subprocess import Popen
import tempfile

REQUIRED_INTERFACES = (
    "grafana_datasource_exchange/v0",
    # add here any future dependencies
)
CRI_SCHEMAS_PATH = Path(__file__).parent


def cleanup_root():
    root = Path(__file__).parent
    print(f"cleaning up {root}...")
    for folder in root.glob("*"):
        if folder.is_dir():
            rmtree(folder)


def download_schemas(branch:str):
    print("cloning CRI...")
    tempdir = tempfile.mkdtemp()
    proc = Popen(shlex.split(f"git clone https://github.com/canonical/charm-relation-interfaces.git --branch {branch} --quiet --depth 1 {tempdir}"))
    proc.wait()

    print("copying schemas...")
    for interface_path in REQUIRED_INTERFACES:
        schema_path = Path(tempdir) / "interfaces" / interface_path / "schema.py"
        destination_path = CRI_SCHEMAS_PATH / interface_path / "schema.py"
        destination_path.parent.mkdir(parents=True)
        destination_path.write_text(schema_path.read_text())
        print(f"copied {schema_path} --> {destination_path}")

    print("all done! don't forget to `git add CRI_SCHEMAS_PATH`.")


def main(*, branch:str):
    cleanup_root()
    download_schemas(branch=branch)


if __name__ == '__main__':
    main(branch="main")
