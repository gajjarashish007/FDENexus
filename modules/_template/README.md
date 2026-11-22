# Module template

1. Copy this folder to `modules/mNN-short-name/` (the folder must start with `m`).
2. Edit `manifest.json`: id, name, capabilities. Set each capability `status` to `live`, `partial` or `planned`
   honestly; the dashboard and the module page show these badges.
3. Implement `backend/module.py` (optional) and a UI page; set `ui.workspace` to that page.
4. Restart `./start-portal.sh`. The core discovers the folder; a broken module is logged and skipped.

Everything stays centralized: one login, one database, one audit log, one UI shell.
