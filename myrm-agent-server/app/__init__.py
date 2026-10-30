"""Myrm Agent Server application package."""

import os

# litellm downloads its model price table from GitHub while it is imported, which stalls every
# launch (up to its 5 s timeout when the network is unreachable). Default to the table packaged
# with litellm. To get the remote table back, export LITELLM_LOCAL_MODEL_COST_MAP=False in the
# real process environment: .env is loaded after this package, so it cannot override the default.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
