One JSON file per approved change, written by the portal next to the stack file it touches.
CI (and `scripts/run_change.py`) reads the `operations` list: destroys first, then applies, in dependency order.
