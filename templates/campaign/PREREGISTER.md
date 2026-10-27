Your lane: MEASURE, job PREREG-1.
Owns: {{dir}}/card.md ; {{dir}}/baseline.json

You are the measuring lane of campaign {{name}} ({{date}}). Read the charter {{charter}} and every brief in {{briefs}} first. Launch this before the other lanes start work. You write only the two files above and your report; you change nothing a lane owns.

The owner may have written the question below; where a field is still in angle brackets, you write it.

1. Write {{dir}}/card.md, the pre-registration, before any lane output exists:
   - Question: <what this campaign tests, in one sentence; for example "N parallel lanes with a charter and owned paths deliver verified, owner-usable outputs with no collisions, inside the caps">.
   - Hypothesis: one sentence, then its parts, each with a test that decides it true or false at the end.
   - Measures, each with how it is read on the box: per lane, claims made vs claims verified (file exists, test passes, link answers, hash in git); collisions (two lanes changing one path, from git log by path); rule breaks (push, publish, delete, secrets, edits outside the lane); outside spend vs the caps (spend.tsv); owner-minutes owed (the reports' Needs the owner sections); usable by the owner at the end, yes or no, with the path or link the owner would open.
   - Predictions: a table of numbered predictions, each a probability between 0 and 1, written now. At least one per measure, and one for the whole hypothesis.
   - Scoring rule: how each prediction resolves (1, 0, or undecided with a reason), and the Brier score over the resolved ones.
   - What the measures cannot see, stated now.
2. Take the baseline in {{dir}}/baseline.json: for each repo named in the lane table, its branch and HEAD commit; the line count of spend.tsv; which reports already exist in {{reports}}; the time.
3. Write the checklist the scoring pass follows into card.md under "Method": read-only checks, one command each.

The card's question, hypothesis, measures and predictions are not edited after this job ends; the scoring pass checks that with git log on card.md.
Report to {{reports}}/MEASURE.md following {{contract}}.
