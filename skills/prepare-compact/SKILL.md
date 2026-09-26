---
name: prepare-compact
description: Prepare this conversation for Claude Code's /compact (context compaction) - save anything that would otherwise live only in the conversation, report version-control and cleanup state, and propose a one-line compaction focus. A bare "compact" from the user means compacting the conversation, so use this skill whenever the user says they want to compact, in any language (e.g. "I want to compact", "prepare to compact", "compactしたい"), or when a tool such as the Herdr agent-parking dashboard sends /prepare-compact.
---

# Prepare for compaction

Compaction replaces the conversation with a summary. Anything that exists only in
the conversation - decisions and their reasons, identifiers, half-finished steps,
pending questions - can be lost or blurred. This skill saves it somewhere durable
first, then hands the user a ready `/compact` line. You cannot run `/compact`
yourself; only the user, or a tool acting for them, can.

Do not start new work in this turn.

## Steps

1. **Take stock.** Go over what this conversation has established: the goal,
   decisions and why, work done, work in progress, open questions, identifiers
   (paths, branches, commit hashes, PR and issue numbers, URLs, session and pane
   IDs), and the next step.

2. **Persist what would be lost.** For each item that lives only in the
   conversation, save it where the next turn will find it:
   - progress, decisions and next steps of a project: that project's own plan or
     notes files when it keeps them (for example the checkmarks in `plan.md`),
     otherwise your memory system when one is configured;
   - lasting facts about the user or the environment: memory.

   Update existing notes instead of adding duplicates. Do not copy what the
   repository or its git history already records.

3. **Check version control.** For every repository touched in this conversation,
   check for uncommitted changes and unpushed commits and report them. Do not
   commit or push unless the user already asked for it in this conversation or the
   project's instructions say to.

4. **Clean up what this conversation started.** Stop background processes, tunnels,
   port forwards, watchers and temporary servers that you started and no longer
   need, and delete temporary files you created in scratch locations. Never stop or
   delete anything you did not start. If something has to keep running, say what
   and why.

5. **Collect loose ends.** Note anything waiting on the user (a question, an
   approval, a choice) and any background task the next turn must pick up.

6. **Report and propose the focus.** Reply in the user's language, briefly:
   - what you saved and where, one line each (or say plainly that nothing needed
     saving);
   - the version-control state of each repository;
   - what you cleaned up, and what is still running on purpose;
   - the open items for after the compaction;
   - the focus, on a line of its own, in exactly this form: one line, no line
     breaks, at most 300 characters, in the user's language, even when nothing
     needed saving (a tool may read the tag):

     `<compact-focus>...</compact-focus>`

     The focus names what the summary must keep: the current goal, the next step,
     the key decisions and the identifiers the next turn needs. Leave out what is
     already saved and easy to reread.
   - the command ready to type: `/compact ` followed by the same focus text.
