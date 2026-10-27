Your lane: MEASURE, job SCORE-1.
Owns: {{dir}}/card.md ; {{reports}}/SCORE.md

You are the scoring pass of campaign {{name}} ({{date}}). Read the charter {{charter}}, the pre-registration {{dir}}/card.md, and every report in {{reports}}. Read-only on everything else: you check, you do not fix.

1. Running jobs: `cc-job campaign status`. Any lane still running or with no report is listed first in SCORE.md.
2. Every claim, checked on the box. For each report, take each line of Done and Verified and mark it:
   - verified: you checked it now and it holds (say how: `git cat-file -e <hash>`, the file and its size, the test command and its count, the HTTP status);
   - unverified: it may hold, but you could not check it from here (say why);
   - false: you checked and it does not hold (a missing path, a hash not in the repo, a failing test, a dead link).
   Prose claims (counts, durations, "it plays", "it renders") get a look: open the file, count the lines, read the log.
3. Rules: for each lane, commits outside its Owns: paths (git log by path since the baseline), any push, publish, deletion or secret touched, outside spend in {{dir}}/spend.tsv against the caps. Rented compute still up goes on the first line of SCORE.md.
4. Score the pre-registration: each prediction 1, 0 or undecided with a reason; the Brier score over the resolved ones. Write the Result and Critique sections of card.md; do not edit its earlier sections.
5. Write {{reports}}/SCORE.md:
   - a ten-line summary first;
   - per lane: claims verified / unverified / false, usable by the owner today (yes or no, with the path or link), minutes owed;
   - rule breaks and collisions, or "none found" with how you looked;
   - and last, one list: everything that waits on the owner, in order of value, each with its minutes and the one word or click that settles it. Merge duplicates across lanes; this list is the only thing the owner has to read.
