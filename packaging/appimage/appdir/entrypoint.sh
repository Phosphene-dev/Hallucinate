#! /bin/bash

# Prefer X11/Wayland as detected by Qt; keep user's choice if already set.
exec {{ python-executable }} -s -P -c 'import sys; from hallucinate.app import main; sys.exit(main())' "$@"
