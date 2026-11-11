#!/bin/bash
# Join my brain.command: the double-click start of spoke.sh. Created 2026-11-11 (SPOKE-1).
# It shows what will happen, checks that the files are the ones your brain signed, asks once,
# then runs spoke.sh join (or only shows the steps). Everything it runs sits in this folder as text.
cd "$(dirname "$0")" || exit 1
clear
cat WHAT-THIS-DOES.txt
echo
echo "Checking the signature of these files..."
if ! ssh-keygen -Y verify -f allowed_signers -I brain -n brain-spoke -s SHA256SUMS.sig < SHA256SUMS >/dev/null 2>&1 \
   || ! shasum -a 256 -c SHA256SUMS >/dev/null 2>&1; then
    echo "The files are not the ones your brain signed. Nothing was changed. Download them again from your console."
    read -r -p "Press Return to close." _; exit 1
fi
echo "Signed by your brain. Key: $(ssh-keygen -lf allowed_signers.pub 2>/dev/null | awk '{print $2}')"
echo "Your console page shows the same key; if it does not, close this window."
choice=$(osascript -e 'button returned of (display dialog "Let your brain join this laptop? It will look first and change nothing without your yes." buttons {"Not now", "Show the steps only", "Join"} default button "Join" with title "Join my brain")' 2>/dev/null) || choice="Not now"
case "$choice" in
    Join) bash ./spoke.sh join ;;
    "Show the steps only") bash ./spoke.sh join --dry-run ;;
    *) echo "Nothing was changed." ;;
esac
read -r -p "Press Return to close." _
