# Personalization: one catalog, an arrangement per brain

Created 2026-10-29. hbar: "all the personalization tool kits -- these should just be exact ideas that i use, put into standard and different brains have different arrangement of those personalization items/dictionary."

Code: `scripts/cc/cc_catalog.py` (the catalog, the validator, presets), `scripts/cc/presets/*.json` (the four presets), `scripts/cc/cc_layout.py` (`from_answers(answers, preset)`, `Store.arrangement`). Tests: `tests/test_cc_catalog.py`.

## 1. The three pieces

- **Catalog.** One closed list of every personalizable thing the console has. Each item: `id` (`kind:name`), `kind`, `what` it does, its `default`, `who` may see it (owner, member, public), `status`, and `evidence`. Kinds: access, tab, pane, view, panel, door, app, look, voice, channel, seat.
- **Arrangement.** Per brain: `{"preset": <id or null>, "items": [ordered catalog ids]}`. It lives in the owner's `~/.cc-bridge/layout.json` beside `mode`, written by `Store.set_arrangement`, read by `Store.arrangement`. It is never part of the layout itself, so a shared layout pack cannot carry it. It extends the layout file; the layout schema, the interview and `from_answers` are unchanged for a brain without one.
- **Preset.** A file in `scripts/cc/presets/<id>.json`: `id`, `name`, `audience`, `mode` (newcomer or operator), `answers` (the interview's own values, checked by `validate_answers`), `items` (an arrangement), `evidence`. `from_answers(answers, preset)` starts from the preset's answers and the person's answers override them; the `<layout>` block may name the preset (`docs/personalize-interview.md`).

## 2. The rules

- **Used first.** An item is `standard` only when hbar has used it, with the evidence named (a path in hbar.world or a commit); spike-to-system, about five days of lived use. Everything else the console has is listed as `candidate` so the inventory is complete, and no arrangement may pick it. Promoting a candidate is a one-line change: write its evidence. The validator refuses a standard item without evidence.
- **Closed lists.** Ids only. No CSS, no URLs, no free text in an arrangement or a preset; an unknown id, a candidate, a repeat, or an item the audience may not see is refused with the reason.
- **One access at least.** Every arrangement holds at least one of `access:console`, `access:telegram`, `access:public-chat`.
- **Installed is not used.** The brain-apps on hbar's brain (installed.json, 15) are all candidates until a record shows him using one.

## 3. The four presets

| preset | audience | mode | access | items | evidence |
|---|---|---|---|---|---|
| owner | owner | operator | console, Telegram | every standard item an owner may see (32) | each item's own; answers not yet measured |
| family-telegram | member | newcomer | Telegram | access:telegram | Elena, ops/2026-10-24_next-three-members.md; amended 10-25: she will open the console after all |
| public | public | newcomer | public chat | access:public-chat | nous, yury-ai public brains (nous 3c6b6de) |
| org | member | newcomer | console | console, the six standard tabs a member may see, talk, files, the five doors, stock look (15) | university and health on showcase-1 |

The owner preset's answers are empty: hbar's live layout is in `/home/cc/.cc-bridge/layout.json`, which this seat cannot read. Measure it there with `python3 scripts/cc/cc_catalog.py measure` (prints the answers that reproduce the current layout, the mode and the stored interview answers) and copy the answers into `presets/owner.json`.

## 4. What is not built

- The console does not read the arrangement yet: Nav, the pane picker and the doors still show everything (or the newcomer tiers). Next: `/cc/layout` returns the arrangement, Nav and `PANE_ROUTES` filter and order by it.
- No bridge route or `<layout>` key sets the arrangement; the operator sets it (`Store.set_arrangement`) when the brain is made.
- Fonts, size, weight, width and colour vars stay layout values, not catalog items.

## 5. The catalog (2026-10-29)

Generated from `cc_catalog.CATALOG`; the code is the source, this table is a copy.

| id | kind | what | default | who | status | evidence |
|---|---|---|---|---|---|---|
| access:console | access | the full console in a browser | on | owner, member | standard | mind/claude/project_claude_code_in_brain.md (live 2026-09-20) |
| access:telegram | access | the Telegram door: text, voice notes and files into the brain | off | owner, member | standard | ops/2026-10-12_production-procedures.md (intake: Telegram, 20 MB cap) |
| access:public-chat | access | a public chat page, no login, labelled answers | off | owner, member, public | standard | nous 3c6b6de (public chat footer, yury-ai kit); hbar.science rulings 2026-10-29 |
| tab:_cc | tab | the conversation with the hands (CC) | on | owner, member | standard | mind/claude/project_claude_code_in_brain.md |
| tab:_chat | tab | plain chat with the brain's reasoner | on | owner, member | standard | mind/claude/project_brain_model_resolution.md |
| tab:_knowledge | tab | upload and search the brain's documents | on | owner, member | standard | mind/claude/project_mirror_corpus_ingest.md |
| tab:_files | tab | the box's files: out, in, work, world, brain | on | owner, member | standard | ops/2026-09-13_todo-plan.md (Files pane, session 2) |
| tab:_apps | tab | the brain-app shelf | on | owner, member | standard | mind/claude/project_brainapp_iframe_sandbox.md |
| tab:_settings | tab | settings: keys, model, look | on | owner, member | standard | mind/claude/project_brain_model_resolution.md (UI pick) |
| tab:_system | tab | the box: services, jobs, disk | on | owner | standard | mind/claude/project_claude_code_in_brain.md (System tab) |
| tab:_update | tab | pull the template and rebuild | on | owner | standard | mind/claude/reference_brain_deploy.md (Update tab) |
| tab:_persona | tab | the persona and charter files | on | owner | standard | mind/claude/project_brain_md_governance.md |
| tab:_federation | tab | peers and doors between brains | on | owner | standard | ops/sessions/2026-05-01_federation-dm-live.md |
| tab:_dashboard | tab | the overview page | on | owner | candidate | unknown |
| tab:_tasks | tab | tasks | on | owner, member | candidate | unknown |
| tab:_research | tab | research runs | on | owner, member | candidate | unknown |
| tab:_integrations | tab | email, calendar, Telegram, MCP set-up | on | owner | candidate | unknown |
| tab:_economy | tab | the economy page | on | owner | candidate | unknown |
| tab:_trace | tab | the trace of tool calls | on | owner | candidate | unknown |
| tab:_future | tab | the future page | on | owner | candidate | unknown |
| tab:_graph | tab | the memory graph | on | owner, member | candidate | unknown |
| tab:_guide | tab | the guide | on | owner, member | candidate | unknown |
| tab:_terminal | tab | a terminal on the box | on | owner | candidate | unknown |
| pane:/board | pane | the board of running jobs and agents | on | owner | standard | mind/claude/feedback_fan_out_and_board.md (watch /board) |
| pane:/agents | pane | agent cards by tag | on | owner | standard | mind/claude/feedback_agent_tags_clickable.md |
| pane:/permits | pane | permit history, who decided | on | owner | candidate | unknown |
| pane:/boxes | pane | the 2D body map of the boxes | on | owner | candidate | unknown |
| pane:/profile | pane | how the brain talks (profile interview) | on | owner, member | candidate | unknown |
| pane:/layout | pane | the layout chips and proposals | on | owner, member | candidate | unknown |
| view:talk | view | the conversation | on | owner, member | standard | mind/claude/project_claude_code_in_brain.md |
| view:panes | view | several conversations side by side | off | owner, member | standard | ops/2026-10-06_console-reading-space/README.md |
| view:gallery | view | conversations as a deck | off | owner, member | candidate | unknown |
| panel:handsfree | panel | the hands-free row | on | owner, member | standard | ops/2026-09-28_where-we-are.md (hands-free) |
| panel:files | panel | the files link | on | owner, member | standard | mind/claude/feedback_desk_files_group_readable.md |
| panel:board | panel | the board link | on | owner | standard | mind/claude/feedback_fan_out_and_board.md |
| panel:sidebyside | panel | the side by side button | on | owner, member | standard | ops/2026-10-06_console-reading-space/README.md |
| panel:hero | panel | the title block | on | owner, member | candidate | unknown |
| panel:hint | panel | the starter hints | on | owner, member | candidate | unknown |
| panel:gallery | panel | the gallery link | on | owner, member | candidate | unknown |
| door:choices | door | choice buttons, each with a probability | on | owner, member | standard | nous c6dafd1; mind/claude/feedback_probability_recommendations.md |
| door:highlight | door | a highlighted phrase opens its card | on | owner, member | standard | nous 0cd0d92; mind/claude/feedback_agent_tags_clickable.md |
| door:permit-card | door | approve or refuse an action before it runs | on | owner, member | standard | mind/claude/feedback_human_approve_destructive_infra.md |
| door:job-tile | door | a job or agent tile in the thread that started it | on | owner, member | standard | mind/claude/feedback_tiles_stay_in_thread.md |
| door:desk-link | door | an exact link to a file on the desk | on | owner, member | standard | mind/claude/feedback_link_is_right_there.md |
| app:poker-journal | app | poker trainer | off | owner, member | candidate | unknown |
| app:hbar-ink | app | thought-drop instrument | off | owner, member | candidate | unknown |
| app:mirror | app | self-knowledge notes | off | owner, member | candidate | unknown |
| app:daybook | app | day log | off | owner, member | candidate | unknown |
| app:today | app | today | off | owner, member | candidate | unknown |
| app:people | app | people | off | owner, member | candidate | unknown |
| app:weekly-review | app | weekly review | off | owner, member | candidate | unknown |
| app:toolbox | app | small utilities | off | owner, member | candidate | unknown |
| app:clip | app | clip | off | owner, member | candidate | unknown |
| app:thread-consolidator | app | thread consolidator | off | owner, member | candidate | unknown |
| app:quantum-room | app | quantum room | off | owner, member | candidate | unknown |
| app:cell-architecture-studio | app | cell architecture studio | off | owner, member | candidate | unknown |
| app:oracle | app | oracle | off | owner, member | candidate | unknown |
| app:science-experiment | app | science experiment | off | owner, member | candidate | unknown |
| app:hbar-health-letter-ingestion | app | health letter ingestion | off | owner, member | candidate | unknown |
| look:default | look | the stock warm dark palette | on | owner, member | standard | ui/pages/_app.js (stock) |
| look:black | look | black palette | off | owner, member | candidate | unknown |
| look:light | look | light palette | off | owner, member | candidate | unknown |
| voice:speak | voice | answers read aloud (streamed, speed 1.2) | off | owner, member | standard | ops/2026-09-28_where-we-are.md |
| voice:handsfree | voice | talk without pressing | off | owner, member | standard | ops/2026-09-28_where-we-are.md |
| channel:phone-upload | channel | photos and files from the phone | off | owner | standard | mind/claude/project_photo_memory_pipeline.md |
| seat:claude-code | seat | Claude Code as the hands | on | owner | standard | mind/claude/project_claude_code_in_brain.md |
| seat:codex | seat | Codex as the hands | off | owner | standard | hbar.world ad0fa6a, 58baec7 (Codex hands, rulings 2026-10-29) |
| seat:local | seat | a local model, read-only | off | owner | standard | ops/2026-10-25_evening-handoff.md (local seat) |
