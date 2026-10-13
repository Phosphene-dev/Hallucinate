"""CI runs this inside the built Flatpak: python3 decode_check.py FILE... (see hallucinate/decodecheck.py)."""
import sys

from hallucinate.decodecheck import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
