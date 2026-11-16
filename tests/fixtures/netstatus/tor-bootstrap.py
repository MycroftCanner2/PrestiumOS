#!/usr/bin/python3
# test fixture for prestium-netstatus: Tor bootstrap percentage (2.1: asked over the
# control port now, the journal has no Tor lines in the default boot). 100 = bootstrapped.
import os
print(os.environ.get("PRESTIUM_FIXTURE_TORBP", "100"))
