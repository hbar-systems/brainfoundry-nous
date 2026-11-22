# The report contract (every lane, campaign {{name}})

One file per lane: {{reports}}/<LANE>.md. Four sections, in this order, with these headings. The scoring pass reads them mechanically, so keep the headings.

    ---
    created: <date>
    lane: <LANE>
    job: <JOB>
    ---

    # <LANE>, <JOB>: <one line of what came out>

    ## Done
    One line per thing made or changed: the path, the commit hash (repo and branch), the link. Nothing here without something checkable.

    ## Verified, and how
    One line per claim from Done: the command run and what it printed, the test count, the file size, the HTTP status.

    ## Not verified
    What the job could not check, and why (no access, needs the owner's eyes or ears, ran out of cap). Empty is allowed; say "none".

    ## Needs the owner
    One line per decision or action only the owner can take, each with its minutes and the word or click that settles it:
    - <what> (<n> min): <the one word, or the link to press>

Rules: no claim without a path, hash, command or link; "done" means checked, not hoped; a step skipped is named here, not left out.
