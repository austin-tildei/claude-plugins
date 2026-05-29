# austin

Austin's personal Claude Code toolbox — a namespace plugin holding a set of
personal skills. Install once; each skill is invoked as `/austin:<skill>`.

## Install

```
/plugin marketplace add austin-tildei/claude-plugins
/plugin install austin@austin-tildei
```

## Skills

### `/austin:save-convo`

Renders the current session into a shareable Markdown file — user prompts,
Claude replies, and one-line tool summaries — and copies it to the clipboard.
Thinking blocks and raw tool output are omitted, and a best-effort secret
redaction pass runs before the file is written.

The skill reports the written file path, how many potential secrets were masked,
and whether the clipboard was populated. Output lands in
`~/.claude/shared-transcripts/YYYY-MM-DD-HHMM-<slug>.md`.

## Requirements

- **Python 3** on `PATH` (standard library only — no pip dependencies).
- Clipboard copy uses macOS `pbcopy`. On other platforms the file is still
  written; the clipboard step is skipped.

## Caveats

- **Review before sharing.** Redaction is regex-based and best-effort. It will
  miss secrets that don't match its patterns. Always skim the generated file
  before sending it to anyone.
- **Coupled to Claude Code internals.** The renderer locates the live
  transcript via the `CLAUDE_CODE_SESSION_ID` environment variable and reads the
  session JSONL under `~/.claude/projects/`. These are undocumented internals;
  a future Claude Code release could change the layout or event schema and break
  rendering. `skills/save-convo/test_render.py` exercises the parser
  against fixture events and acts as a regression canary if the format shifts.

## Tests

```
python3 skills/save-convo/test_render.py
```
