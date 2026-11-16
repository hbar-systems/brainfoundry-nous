# Spoke: your laptop becomes part of your brain

Created: 2026-11-11 (SPOKE-1). Status: design and Mac installer written and tested on the brain's box (dry run, fixture folder, signature chain); not yet run on a real friend's Mac. Scripts: `scripts/spoke/`.

A spoke is a computer the brain reaches and works on, the way a laptop uses its own disk. The owner's laptop joins **the owner's own brain's network** (never the operator's, never another member's), and the brain gets one narrow door into it. The brain looks first and organises only after a yes. This note is the whole design: the conversation, the join, the door, the first act, what "reads all data" means, offline, and how to leave.

## 1. The conversation comes first

The brain never guesses what computer it is talking about. Before any download it asks, one question per message (the first-use rule, `docs/first-use.md`):

1. What computer is it? (A Mac, a Windows laptop, something else.) If they do not know: "Click the apple at the top left of the screen, then About This Mac, and tell me the first two lines."
2. Which macOS version (from the same window)? Below 13, the brain says it cannot join yet and why.
3. What do you want organised? (Photos, documents, music, "everything is a mess".) This becomes the first plan's scope.
4. Is this laptop only yours? If others use it, only the friend's own user account is ever reached; other users' homes are never touched.

After the join, the brain confirms the answers by reading `facts` (model, chip, memory, macOS) and says if anything differs from what the friend said.

## 2. The join: the brain's own network

- Each brain has its own coordination server (Headscale, one instance per brain on the brain's box, its own https name). One brain, one network: two brains never share one, and the operator's own network is never used for a member's devices.
- The brain's side joins that network as a node in userspace mode (`tailscaled --tun=userspace-networking`, state under the brain's folder, run by a door user, not by the reasoner). Its address is fixed at join and written into the laptop's key line.
- When the friend presses Download, the brain issues an auth key for **one device, single use, expiring in one hour** (`headscale preauthkeys create --user <brain> --expiration 1h`), and `scripts/spoke/make-bundle.sh` writes it into the bundle.
- Policy on that network: the brain's node may reach the laptop on port 22; the laptop may reach nothing on the brain's node. A second device of the same owner joins with a new key.

## 3. The door

- The brain holds an ed25519 key in a door user's home (mode 700, unreadable by the reasoner), the push-helper pattern: the reasoner asks, the door user runs one narrow command, the console raises a card for every consequential step.
- On the laptop, one line in `~/.ssh/authorized_keys`:
  `from="<brain address>",restrict,command="$HOME/.brain-spoke/door.sh" ssh-ed25519 ... brain-spoke:<handle>`
  The key works only from the brain's address, gets no shell, no port forwarding, no terminal. It can run `door.sh` and only `door.sh`.
- `door.sh` has verbs, not a shell: `facts`, `inventory`, `log`, `mode`, `organise on|off`, `list <folder>`, `peek <file>`, `apply` (a plan of `mkdir` and `mv` lines), `undo <id>`, `leave`. There is no delete verb. Every call is written to `~/.brain-spoke/door.log` before it runs, refused ones too; the friend reads it with `spoke.sh status` and the brain shows it on the spoke page.
- Two modes. `look` (the start): only `facts`, `inventory`, `log`, `mode`. `organise`: adds `list`, `peek`, `apply`, `undo`. The switch is a card in the console ("Let your brain organise this laptop?"), never remembered, never judged; the friend can switch it back from the console or on the laptop (`bash ~/.brain-spoke/door.sh organise off`).
- Posture: the owner's, default `cards` (a friend's brain is set up with cards on; CC.md). Every door call is a card or, in the judged posture, a judged call whose numbers show on the card; nothing runs silently. `organise on` and every `apply` are always cards, never remembered and never judged: an `apply` card shows the plan line by line, the number of moves and the undo.
- What the laptop side cannot know: whether a call came through a card. The gate is on the brain's side (the key sits with the door user, and only the card path calls it). The laptop side keeps the verbs narrow, the paths fenced and the log honest; that is what holds if the brain's side is wrong.

## 4. The first act: a read-only inventory

`inventory.sh` runs on the laptop and sends back only counts and sizes: by place (Desktop, Documents, Downloads, Pictures, Music, Movies, other home folders, external drives by name), by kind (photos, video, audio, music projects, documents, code, archives, other), by age (30 days, this year, 1 to 3 years, older), likely copies (same name and size), files over 1 GB, and places macOS refused. The aggregation happens on the laptop: no file name, no folder name below the top level and no content leaves it. It writes nothing on the laptop. The Photos and Music libraries and apps are counted whole, never opened.

The brain renders it as a page (`render_inventory.py`): the computer's facts, four headline numbers, three bar lists, what it did not read, and one question: propose a plan, or not now. Only after "propose a plan" does the brain ask for `organise` mode, then proposes folders one place at a time (Downloads first: it is usually the mess). A plan is a list of moves the friend reads on the card; nothing moves without it, and each applied plan has an undo.

## 5. What "reads all data" means, plainly

What the friend is told, in these words, before the join:

- **In look mode** your brain sees how many files of each kind you have, how big, how old, in which of your main folders. Not their names, not what is in them.
- **In organise mode** it also sees the names of files in a folder it asks about, and can read the beginning of a file it needs to place (64 KB, about 30 pages of text). Each of those is one line in your log. What it reads goes to your brain, and to the reasoner your brain uses (the model company named on your console's settings page) to think about it.
- **Never, in any mode:** your passwords and keychain, Messages, Mail and other people's conversations, your browsers (history, cookies, logins), hidden settings folders, anything inside Library (apps' own data), other users of the laptop. `door.sh` refuses these paths before anything is read: anything under Library, any hidden folder, any `..`, any link that leads out of your home folder.
- **Nothing is ever deleted** by your brain. Moves never overwrite.
- macOS itself guards Desktop, Documents and Downloads from remote access unless you turn on "Allow full disk access for remote users" in Remote Login's settings. Without it, the inventory says which places it could not count. Turning it on is your choice. It also makes the protected Library folders readable to a remote login, which is why `door.sh` fences Library off itself.

## 6. Offline

The laptop works exactly as before when the brain cannot reach it: nothing on the laptop depends on the brain. When the laptop sleeps or is away, the spoke page says "asleep since <time>", and the last inventory is shown with its date. A card for a plan does not run late: if the laptop was away when the card was allowed, the plan waits for the laptop, then the brain re-reads the folder, and if anything changed the card asks again. Plans are never queued and replayed blind. If the brain's own box is down, the laptop simply is not reached.

## 7. How to leave

- On the laptop: double-click **Leave my brain** on the Desktop, or `bash ~/.brain-spoke/spoke.sh leave`. It removes the key line, logs the laptop out of the brain's network, removes `~/.brain-spoke` (the door log is kept as `~/brain-spoke-door.log`), and, if Remote Login was off before the join, opens Sharing to turn it off. The Tailscale app stays; drag it to the Bin to remove it.
- From the console: "Disconnect laptop" runs `door.sh leave` (the key line goes) and deletes the node from the brain's network (`headscale nodes delete`). Either side alone is enough to end access.

## 8. The installer (Mac first)

- The friend downloads a zip from their own console (https, behind the console login). Inside: `Join my brain.command`, `WHAT-THIS-DOES.txt`, `spoke.sh`, `door.sh`, `inventory.sh`, `SHA256SUMS` with an ssh signature by the brain's signing key, and the key's public half. All text, all readable before running.
- `Join my brain.command` shows WHAT-THIS-DOES, checks the signature and the checksums, prints the signing key's fingerprint (the console shows the same one beside the Download button), and asks once: **Join**, **Show the steps only** (`spoke.sh join --dry-run`: every step printed, nothing changed) or **Not now**.
- No curl-pipe-bash anywhere. Tailscale's package is downloaded from pkgs.tailscale.com and installed only if `pkgutil --check-signature` names Tailscale Inc. (W5364U7YZB).
- What the signature proves: the files are the ones the brain built. The zip carries its own public key, so a swapped zip would verify against a swapped key; the fingerprint on the console page is what closes that, and the friend is told to compare it.
- macOS 15 does not open a downloaded, unnotarised `.command` on double-click: the friend presses "Open Anyway" once in System Settings, Privacy and Security (unverified on a real Mac yet). Notarising the wrapper removes that step and needs a paid Apple Developer account.

## 9. The first session, word for word

What the brain says (B) and what the friend sees or does (F). One question per message.

1. B: "Hello. Do you want me to help sort what is on your laptop? I can look first and change nothing."
2. F: "Yes, it's a mess."
3. B: "What computer is it? If you are not sure, click the apple at the top left, then About This Mac, and tell me the first two lines."
4. F: "MacBook Air, M2, 2022. macOS Sequoia 15.3."
5. B: "Thank you. What would you most like tidied: photos, documents, music, downloads, or everything?"
6. F: "Photos and all the PDFs."
7. B: "Is this laptop only yours, or does someone else log in to it too?"
8. F: "Only mine."
9. B: "Here is what joining does, in four steps. [the four lines of WHAT-THIS-DOES]. First I only look: how many photos and documents, how big, how old. I never open your passwords, messages, mail or browsers. I move nothing until you read a plan and say yes, and I never delete. Shall I make your download?"
10. F: presses **Make my download**. The console shows the button "Download Join my brain" and under it: "Signing key SHA256:xxxx. This link works once, for one hour."
11. B: "When it has downloaded, open it in your Downloads folder and double-click Join my brain. If your Mac says it cannot open it, open System Settings, Privacy and Security, scroll down and press Open Anyway. I will wait here."
12. F (on the laptop): a Terminal window shows WHAT-THIS-DOES, then "Signed by your brain. Key: SHA256:xxxx". A dialog: Not now, Show the steps only, Join. Presses **Join**.
13. F: the Mac asks for the password (to install Tailscale), then "Tailscale would like to add VPN configurations": Allow. Then System Settings opens at Sharing; the Terminal says which switch.
14. B (the moment the laptop appears on the network): "I can see your laptop now. It says MacBook Air (M2, 2022), 8 GB, macOS 15.3: that matches what you told me. Shall I look?"
15. F: "Yes." A card: "Look at your laptop: count files by kind, size and age. No names, nothing opened." Allow.
16. B runs `inventory`, then: "Here is what is on it." The page opens beside the conversation. "The biggest part is photos, 41 GB, most of it older than three years. Downloads holds 9 GB, half of it installers. 2 GB look like copies."
17. B: "Would you like me to propose where things should go? To do that I need to see file names in one folder at a time; I start with Downloads. Nothing moves until you read the plan."
18. F: presses **Propose a plan**. A card: "Let your brain organise this laptop? It will see names in the folders it asks about, and read the start of files it needs to place. It moves nothing without a plan you approve. You can turn this off at any time." Allow.
19. B: lists Downloads, proposes: "Downloads: 23 installers into Downloads/Installers (you can delete them yourself later), 41 PDFs into Documents/PDFs by year, 12 photos into Pictures/From Downloads. 76 moves. Undo is one button." Card with the plan.
20. F: Allow. B: "Done: 76 moved, undo id 20261112T... . Next time, photos?" The session ends; nothing else runs until the friend comes back.

## 10. The brain's side (SPOKE-2A, 2026-11-14)

Written and tested on the brain box; not yet installed on any box. Files: `scripts/spoke/box/`.

- `spoke_config.py`: one member's files from the handle and port block: Headscale `config.yaml` (every port on 127.0.0.1, server_url `https://spoke.<m>.brainfoundry.ai`, no MagicDNS), `policy.json` (tag:brain may reach the member's laptops on 22; the laptops reach nothing), `/etc/spoke/<m>.env`, the Caddy site block, the sudoers line. Ports: the brain node's SOCKS at the member block's spare +9 (8100+10n+9); Headscale http, metrics and grpc at 9100+10n, +1, +2 (a spoke block above every member block). hbar's rehearsal brain on friends-1 is not a member: it takes block 99 (SOCKS 9099, Headscale 10090 to 10092), bridge user and console named on the command line.
- `headscale@.service`: one Headscale per member (user headscale, group `<m>-spoke`, socket 0770 so only the door user drives the CLI). `spoke-node@.service`: the brain's own node, userspace tailscaled run by the door user, SOCKS on 127.0.0.1.
- `spoke-door.sh`, installed as `/usr/local/sbin/spoke-door <m> <verb>`, run as `<m>-spoke` through one sudoers line from the member's bridge user. Verbs: `status`, `inventory`, `plan`, `apply`, `undo <id>`, `leave`, `organise on|off`, and for the console `fingerprint` and `bundle`. It finds the laptop by its network name `<m>-laptop--<mac user>` (spoke.sh sets it at join), reaches it with the door key over the node's SOCKS port, and checks every plan line the way the laptop's door.sh does before anything leaves the box. Every call is a line in `/var/lib/spoke/<m>/door.log` (group `<m>-brain`), refused ones too. `bundle` issues a one-device key that expires in an hour and runs make-bundle.sh with the brain's signing key; the zip lands in `out/` for the bridge to serve once.
- `spoke-install.sh <m> --block <n> [--bridge-user U] [--console URL] [--group G]`: `--dry-run` (the default) prints every step and file, measures the four ports with `ss -ltn` and the programs it needs, and changes nothing. `--apply` runs only on the box named by `--host` (default friends-1); it backs up the Caddyfile with a dated name before the edit and runs `caddy validate` before the reload, restoring on refusal; it never touches the member's brain stack. `--undo` stops and disables the two units, drops the Caddy block (validate, reload), and moves the configs, the state and the door folder to `/var/backups/spoke-<m>-<date>/`; it deletes nothing and leaves the door user locked.
- The bridge: `cc-job spoke <verb>` (POST /spoke). `organise on` and every `apply` raise their own card first (tool `spoke`, in `BOX_ALWAYS_ASK` with orfeo_post: never remembered, never judged, never reused in a turn, never auto for Codex); the apply card shows the counts, the first twelve lines and the whole plan on press. The other verbs ride on the card or posture of the Bash call that ran cc-job. The bridge needs `CC_SPOKE=1` (and `CC_SPOKE_HANDLE` when it is not member `<m>`).
- The console's `/spoke` page: the laptop (here, asleep since, or not joined), Make my download (then Download Join my brain, the signing key's fingerprint, the hour), the last inventory page beside the conversation, Disconnect laptop (asks once in place).

## 11. Not built yet (amended 2026-11-16, SWITCH-1)

Still owed: installed on friends-1 (the apply, DNS for spoke.<m>.brainfoundry.ai, the first real join on hbar's Mac). `list` and `peek` through the box door. Windows and Linux laptops. A Developer ID signature and notarisation for the app (section 12). The paragraph below is the 2026-11-14 list as it stood.


Installed on friends-1 (the apply, DNS for spoke.<m>.brainfoundry.ai, the first real join on hbar's Mac). `list` and `peek` through the box door (the laptop's door.sh has them; spoke-door adds them with the first plan). Windows and Linux laptops (same door shape; Windows needs OpenSSH Server and a PowerShell door). Notarisation.

## 12. For a person who has never opened Terminal (SWITCH-1, 2026-11-16)

hbar: "don't they have to give you ssh? this is too technical for people like my mother". The design above stays exactly as it is (the brain's own Headscale, a one-use key that expires in an hour inside the download, the restricted door key, look first, organise only on a yes). What changes is only what the person touches.

### What the owner presses, from the link to a brain that knows their computer

1. On their home, the card **Connect this computer**: **Get the file for this Mac**. One file downloads: `join-my-brain-<handle>.zip`, which Safari opens by itself into **Join my brain** in Downloads (an app, not a `.command`: no Terminal window opens at any point).
2. Double-click **Join my brain**. macOS 15 says Apple could not verify it (it is not signed by an Apple Developer ID yet): **Done**, then System Settings, Privacy & Security, scroll down, **Open Anyway**, their password, **Open**. This is the one step a paid Apple Developer ID (USD 99 a year, hbar's account to open; not bought) removes: a signed and notarised app opens on the first double-click.
3. The app's own window (a macOS dialog, in the console's language) says what joining does and shows the brain's key fingerprint, the same as on the card. **Join**.
4. macOS asks for their password once (macOS's own window: the app installs Tailscale with `do shell script ... with administrator privileges`, after checking Tailscale Inc.'s signature).
5. Tailscale's first start: macOS asks to allow its system extension and to **add VPN configurations**: **Allow** each time (if System Settings opens, they turn Tailscale on there). These stay with a Developer ID too: they are macOS asking them before a network program starts.
6. System Settings opens at Sharing: **Remote Login** on, then the (i) beside it, **Allow full disk access for remote users** on (without it the brain cannot count Documents, Desktop and Downloads; that is the macOS privacy rule of section 5), only their own user allowed. **Done**. This also stays with a Developer ID: it is the door itself.
7. If the Mac has no python3 yet (a fresh Mac has only Apple's stub), the app offers Apple's Command Line Tools: **Install** in Apple's own window, about 15 minutes of download in the background. Needed only for step 10.
8. **Done. Your brain can see this computer.** They come back to their home; the card wakes up by itself (it looks every few seconds).
9. **Look at it**: the look-mode inventory (section 4), counts and sizes only; the card shows the total and **Open the page**.
10. **Bring what is on it**, then **Yes, list it** after the words in place (names, sizes and dates go to the brain; nothing moves; passwords, keys, mail and browsers are never listed). The console mints the home's survey token (`POST /documents/import-laptop/token {"survey": true}`, MOVE-IN-2), the bridge switches the laptop to organise and runs `door.sh move-in` with the token on stdin. On the laptop that starts the same `brain_import.py --survey` the pasted line runs, detached, its log in `~/.brain-spoke/move-in.log`; it sends the list over https to `<console>/api/bf`, waits for the yes, brings exactly the chosen files and stops.
11. The plan appears in the card below, **Bring your whole computer** (MOVE-IN-2, unchanged): **Bring all proposed**, then **Remember all N** on the cards.

The pasted line stays: the whole-computer card below is titled **Or with a line in Terminal** when the spoke is on, and is the only way while the spoke is off on their brain (today, on every member brain: section 11).

### The pieces

- `scripts/spoke/app/` (`join-my-brain`, `Info.plist`): a shell program in an app folder (LSUIElement: no Dock icon; every question is an `osascript` dialog with its words passed as argv, never pasted into AppleScript). It checks `SHA256SUMS` and its signature before anything, as the `.command` does; on a mismatch it says so and stops. Steps and output: `~/Library/Logs/join-my-brain.log`. **Show the steps** writes the dry run to a text file and opens it.
- `scripts/spoke/words.sh`: every sentence of the app and of `spoke.sh`'s window mode in English and Russian (`w <key>`), and `dialog`.
- `spoke.sh join` with `SPOKE_GUI=1`: macOS's password window instead of `sudo`, a dialog after each macOS question (the Tailscale start is tried again after each OK, five times), Remote Login checked after each Done (ten times), Apple's tools offered, **Leave my brain.app** on the Desktop (made on the Mac, so macOS does not hold it back; asks once, then runs `spoke.sh leave`). Without `SPOKE_GUI` it prints exactly as before; the `.command` is in the app's Resources for a Terminal start.
- `make-bundle.sh --lang en|ru`: the zip holds only `Join my brain.app`; `Contents/Resources` carries spoke.sh (filled in), door.sh, inventory.sh, brain_import.py, words.sh, lang, the `.command`, WHAT-THIS-DOES.txt; `SHA256SUMS` covers those, `allowed_signers`, `../Info.plist` and `../MacOS/join-my-brain`, signed by the brain's key. `spoke-door bundle en|ru` passes the console's language (the sudoers line names both).
- `door.sh move-in` (organise only; the token on stdin, checked against the token shape, never on argv, never logged), `move-in status`. `spoke-door move-in` / `move-in-status`. Bridge: `POST /spoke/look`, `POST /spoke/move-in {token}`, `GET /spoke/move-in` (operator: the owner's own presses on the home), and `cc-job spoke move-in` for the reasoner, a card like organise on (never remembered, never judged), the bridge minting the token itself.
- The card: `ui/components/ConnectComputer.js`, words and steps `ui/lib/connectComputer.js`; inside MoveInCards, first.

### Windows

Not built. It would take: OpenSSH Server switched on (Settings, Optional features; an admin yes), Tailscale for Windows (its own signed installer), a PowerShell door with the same verbs and fences as door.sh, the key line in `administrators_authorized_keys` or the user's file, and an installer the person double-clicks (an unsigned `.exe` or `.ps1` meets SmartScreen, the Windows twin of step 2; a code-signing certificate removes it, a cost like the Developer ID). About a day of work, then a test on a real Windows laptop. Until then the card says so and points at the line.

### Unverified

The app has run only on Linux with a fake `osascript` (the tests); no real Mac has opened it. Not seen on a real Mac: Gatekeeper's exact words and whether **Open Anyway** shows for a shell-script app; whether the dialogs come to the front from an LSUIElement app; Tailscale's CLI `up` against a Headscale login server from the standalone app on first start; the Russian names of macOS's buttons in the card's steps.
