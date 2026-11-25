savedcmd_xnulog.mod := printf '%s\n'   xnulog.o | awk '!x[$$0]++ { print("./"$$0) }' > xnulog.mod
