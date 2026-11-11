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

## 10. Not built yet

The brain's side: the per-brain Headscale, the brain's userspace node, the door user and its sudoers line, the console's spoke page (Download, fingerprint, inventory page, cards for organise and apply, Disconnect), `cc-job spoke <verb>` raising the cards. Windows and Linux laptops (same door shape; Windows needs OpenSSH Server and a PowerShell door). Notarisation.
