import os
import tempfile
import unittest
from pathlib import Path

import render


class TestSlugify(unittest.TestCase):
    def test_basic_kebab(self):
        self.assertEqual(render.slugify("Build a Share Skill"), "build-a-share-skill")

    def test_truncates_words_and_strips_punctuation(self):
        s = render.slugify("can you help me build a skill that copies transcripts?")
        self.assertEqual(s, "can-you-help-me-build-a")  # max 6 words

    def test_empty_falls_back(self):
        self.assertEqual(render.slugify(""), "session")
        self.assertEqual(render.slugify(None), "session")


class TestStripWrappers(unittest.TestCase):
    def test_removes_system_reminder(self):
        text = "hello there<system-reminder>\nignore me\n</system-reminder> world"
        self.assertEqual(render.strip_wrappers(text), "hello there world")

    def test_removes_command_wrappers(self):
        text = "<command-name>/share</command-name><command-message>msg</command-message>real prompt"
        self.assertEqual(render.strip_wrappers(text), "real prompt")

    def test_empty_after_strip(self):
        self.assertEqual(render.strip_wrappers("<system-reminder>x</system-reminder>"), "")

    def test_none(self):
        self.assertEqual(render.strip_wrappers(None), "")


class TestSummarizeTool(unittest.TestCase):
    def test_bash_uses_description(self):
        out = render.summarize_tool("Bash", {"command": "ls -la", "description": "list files"})
        self.assertEqual(out, "- Bash: list files")

    def test_read_uses_file_path(self):
        self.assertEqual(render.summarize_tool("Read", {"file_path": "/a/b.py"}), "- Read: /a/b.py")

    def test_askuserquestion_uses_headers(self):
        inp = {"questions": [{"header": "Output artifact", "question": "x?"},
                             {"header": "Scope", "question": "y?"}]}
        self.assertEqual(render.summarize_tool("AskUserQuestion", inp),
                         "- AskUserQuestion: Output artifact; Scope")

    def test_unknown_tool_first_scalar(self):
        self.assertEqual(render.summarize_tool("Mystery", {"foo": "bar"}), "- Mystery: bar")

    def test_no_salient_just_name(self):
        self.assertEqual(render.summarize_tool("Mystery", {}), "- Mystery")

    def test_truncates_and_collapses(self):
        out = render.summarize_tool("Bash", {"description": "a\nb " + "x" * 200})
        self.assertTrue(out.startswith("- Bash: a b "))
        self.assertTrue(out.endswith("…"))
        self.assertLessEqual(len(out), 110)


class TestRedact(unittest.TestCase):
    def test_aws_key(self):
        out, n = render.redact("key AKIAIOSFODNN7EXAMPLE here")
        self.assertIn("[REDACTED]", out)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", out)
        self.assertEqual(n, 1)

    def test_github_token(self):
        out, n = render.redact("ghp_" + "a" * 36)
        self.assertEqual(out, "[REDACTED]")
        self.assertEqual(n, 1)

    def test_secret_assignment_keeps_key(self):
        out, n = render.redact("API_KEY=supersecretvalue123")
        self.assertEqual(out, "API_KEY=[REDACTED]")
        self.assertEqual(n, 1)

    def test_jwt(self):
        jwt = "eyJ" + "a" * 12 + "." + "b" * 12 + "." + "c" * 12
        out, n = render.redact(jwt)
        self.assertEqual(out, "[REDACTED]")
        self.assertGreaterEqual(n, 1)

    def test_clean_text_untouched(self):
        out, n = render.redact("just a normal sentence")
        self.assertEqual(out, "just a normal sentence")
        self.assertEqual(n, 0)


class TestParseSession(unittest.TestCase):
    def _events(self):
        return [
            {"type": "queue-operation", "operation": "enqueue", "content": "ignored"},
            {"type": "user", "sessionId": "S1", "cwd": "/proj",
             "timestamp": "2026-05-29T09:30:00.000Z",
             "message": {"role": "user", "content":
                         "real prompt<system-reminder>noise</system-reminder>"}},
            {"type": "assistant", "timestamp": "2026-05-29T09:31:00.000Z",
             "message": {"role": "assistant", "content": [
                 {"type": "thinking", "thinking": "secret reasoning"},
                 {"type": "text", "text": "Here is my reply"},
                 {"type": "tool_use", "id": "t1", "name": "Bash",
                  "input": {"command": "ls", "description": "list"}}]}},
            {"type": "user",
             "message": {"role": "user", "content": [
                 {"type": "tool_result", "tool_use_id": "t1", "content": "file output"}]}},
            {"type": "assistant", "timestamp": "2026-05-29T09:32:00.000Z",
             "message": {"role": "assistant", "content": [
                 {"type": "tool_use", "id": "q1", "name": "AskUserQuestion",
                  "input": {"questions": [{"header": "Scope"}]}}]}},
            {"type": "user",
             "message": {"role": "user", "content": [
                 {"type": "tool_result", "tool_use_id": "q1",
                  "content": "Your questions have been answered: Scope=Conversation only"}]}},
            {"type": "assistant", "isSidechain": True,
             "message": {"role": "assistant", "content": [
                 {"type": "text", "text": "subagent chatter"}]}},
        ]

    def test_segments_order_and_filtering(self):
        meta, segs = render.parse_session(self._events())
        self.assertEqual(segs, [
            ("user", "real prompt"),
            ("claude", "Here is my reply"),
            ("tool", "- Bash: list"),
            ("tool", "- AskUserQuestion: Scope"),
            ("user", "Your questions have been answered: Scope=Conversation only"),
        ])

    def test_meta(self):
        meta, segs = render.parse_session(self._events())
        self.assertEqual(meta["session"], "S1")
        self.assertEqual(meta["project"], "/proj")
        self.assertEqual(meta["first_prompt"], "real prompt")
        self.assertEqual(meta["prompts"], 2)   # prompt + askq answer
        self.assertEqual(meta["replies"], 1)
        self.assertEqual(meta["start"], "2026-05-29T09:30:00.000Z")

    def test_sidechain_dropped(self):
        meta, segs = render.parse_session(self._events())
        self.assertNotIn(("claude", "subagent chatter"), segs)


class TestRenderMarkdown(unittest.TestCase):
    def test_header_and_body(self):
        meta = {"project": "/proj", "session": "S1", "first_prompt": "hello world",
                "prompts": 1, "replies": 1,
                "start": "2026-05-29T09:30:00.000Z", "end": "2026-05-29T09:46:00.000Z"}
        segs = [("user", "hello world"), ("claude", "hi"),
                ("tool", "- Bash: ls"), ("tool", "- Read: a.py")]
        md = render.render_markdown(meta, segs)
        self.assertIn("# Session transcript — hello-world", md)
        self.assertIn("- Project: /proj", md)
        self.assertIn("- Session: S1", md)
        self.assertIn("2026-05-29 09:30 → 09:46", md)
        self.assertIn("1 prompts, 1 replies", md)
        self.assertIn("**User**", md)
        self.assertIn("**Claude**", md)
        # tool lines grouped with no blank line between them
        self.assertIn("- Bash: ls\n- Read: a.py", md)

    def test_format_when_same_day(self):
        meta = {"start": "2026-05-29T09:30:00.000Z", "end": "2026-05-29T09:46:00.000Z"}
        self.assertEqual(render._format_when(meta), "2026-05-29 09:30 → 09:46")

    def test_format_when_unknown(self):
        self.assertEqual(render._format_when({"start": None, "end": None}), "unknown")


class TestFindTranscript(unittest.TestCase):
    def test_finds_by_session_id(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "-some-proj"
            proj.mkdir()
            target = proj / "SID123.jsonl"
            target.write_text("{}\n")
            (proj / "other.jsonl").write_text("{}\n")
            found = render.find_transcript(projects_dir=d, session_id="SID123")
            self.assertEqual(found, target)

    def test_fallback_most_recent(self):
        with tempfile.TemporaryDirectory() as d:
            proj = Path(d) / "-p"
            proj.mkdir()
            old = proj / "old.jsonl"
            old.write_text("{}\n")
            new = proj / "new.jsonl"
            new.write_text("{}\n")
            os.utime(old, (1, 1))
            os.utime(new, (10 ** 9, 10 ** 9))
            found = render.find_transcript(projects_dir=d, session_id="missing")
            self.assertEqual(found, new)

    def test_none_when_empty(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(render.find_transcript(projects_dir=d, session_id="x"))


if __name__ == "__main__":
    unittest.main()
