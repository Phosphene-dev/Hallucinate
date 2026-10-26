#!/bin/sh
# After the package is removed (not upgraded): anything left under /opt/hallucinate, such as bytecode caches
# Python wrote there, goes too. dpkg passes "remove" or "purge"; rpm passes 0 when the last version is erased.
case "$1" in
  remove|purge|0) rm -rf /opt/hallucinate ;;
esac
exit 0
