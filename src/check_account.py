#!/usr/bin/env python3

"""
This script checks whether the initial account exists for a given
landscape-server installation, exiting 0 if it does and 1 if it does not.
It's in a separate script to avoid polluting the charm source with
landscape imports.
"""

import logging
import sys

from canonical.landscape.application import setup_logging
from canonical.landscape.model.main.account import get_account_by_name
from canonical.landscape.setup import load_config


def main() -> None:
    """Exits 0 if the standalone account exists, otherwise exits 1."""
    setup_logging("check-account", level=logging.INFO)
    load_config("maintenance")

    if get_account_by_name("standalone") is None:
        logging.info("The standalone account does not exist")
        sys.exit(1)

    logging.info("The standalone account exists")


if __name__ == "__main__":
    main()
