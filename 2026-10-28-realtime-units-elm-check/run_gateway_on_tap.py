"""Run the web-backend gateway as the tap broker's gw.analyst login.

That login may declare queues only under its own prefix, so this harness
sets the consumer's queue prefix before the gateway starts; nothing else
differs from `python -m gateway`. Run from gridworks-web-backend with
`uv run python <this file>`.
"""
import os
import sys

# The repo root is the working directory; the script lives elsewhere.
sys.path.insert(0, os.getcwd())

import gateway.consumer as consumer  # noqa: E402
from gateway.__main__ import main  # noqa: E402

consumer.QUEUE_PREFIX = "gw.analyst.gateway."

if __name__ == "__main__":
    main()
