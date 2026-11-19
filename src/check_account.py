#!/usr/bin/env python3

"""
This script checks whether the initial account exists for a given
landscape-server installation, printing "true" or "false" on stdout.
It's in a seperate script to avoid polluting the charm source with
landscape imports.
"""

import logging

from canonical.landscape.application import setup_logging
from canonical.landscape.model.main.account import get_account_by_name
from canonical.landscape.setup import load_config


def main() -> None:
    """Prints "true" if the standalone account exists, otherwise "false"."""
    setup_logging("check-account", level=logging.INFO)
    load_config("maintenance")

    account = get_account_by_name("standalone")
    print("true" if account is not None else "false")


if __name__ == "__main__":
    main()
