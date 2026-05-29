---
name: save-convo
description: Use when the user wants to save, share, export, or hand off the current Claude Code conversation to a teammate as a readable file. Renders the live session transcript to shareable Markdown (prompts + replies + one-line tool summaries; thinking and tool output omitted; light secret redaction) under ~/.claude/shared-transcripts/ and copies it to the clipboard. Triggers on "save this conversation", "save this chat", "share this session", "share this conversation", "export this chat", "send this transcript to a teammate".
---

# save-convo

Render the current Claude Code session into a shareable Markdown file and copy it to the clipboard.

## Steps

1. Run the renderer. It reads `CLAUDE_CODE_SESSION_ID` to locate the live transcript, so it must run inside the session being shared:

   ```bash
   python3 "<SKILL_DIR>/render.py"
   ```

   `<SKILL_DIR>` is this skill's base directory, printed when the skill loads.

2. Relay the script's stdout to the user: the written file path, the count of masked secrets, whether the clipboard was populated, and the "review before sharing" reminder.

3. Do NOT read the transcript or the generated file into your context unless the user explicitly asks — the script does all the rendering, and sessions can be very large.

## Notes

- Output lands in `~/.claude/shared-transcripts/YYYY-MM-DD-HHMM-<slug>.md`.
- Redaction is best-effort (regex). Always remind the user to skim the file before sending it.
- Off macOS there is no `pbcopy`; the file is still written and the script reports the clipboard was skipped.
