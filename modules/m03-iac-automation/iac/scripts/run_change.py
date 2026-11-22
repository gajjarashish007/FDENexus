#!/usr/bin/env python3
"""Execute one FDE Nexus change manifest with Atmos.

    run_change.py changes/CHG-ab12cd.json --mode plan|apply

plan : `atmos terraform plan` for every operation (destroy ops use `plan -destroy`).
apply: destroys first, then `atmos terraform deploy` (init + apply -auto-approve) in order.
Approval already happened in the portal and the merge request; this script only executes.
Exit code is non-zero on the first failing operation.
"""
import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def sh(args):
    print("$ " + " ".join(args), flush=True)
    return subprocess.call(args, cwd=ROOT)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--mode", choices=["plan", "apply"], default="plan")
    a = ap.parse_args()
    m = json.loads(pathlib.Path(a.manifest).read_text())
    stack = m["stack"]
    print(f"# {m['id']} {m['title']} (env {m['environment']}, tier {m['tier']}, risk {m['risk']})", flush=True)
    for op in m["operations"]:
        inst = op["instance"]
        if a.mode == "plan":
            extra = ["--", "-destroy"] if op["op"] == "destroy" else []
            code = sh(["atmos", "terraform", "plan", inst, "-s", stack, *extra])
        elif op["op"] == "destroy":
            code = sh(["atmos", "terraform", "destroy", inst, "-s", stack, "-auto-approve"])
        else:
            code = sh(["atmos", "terraform", "deploy", inst, "-s", stack])
        if code != 0:
            print(f"FAILED: {op['op']} {inst} (exit {code})", flush=True)
            return code
    print("OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
