"""Synthetic fixtures only: never consult real user histories or launch tools."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch


READER = Path(__file__).resolve().parents[2] / "skills/resume-claude/scripts/session_reader.py"
spec = importlib.util.spec_from_file_location("resume_reader", READER)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {
            "HOME": str(self.root), "USERPROFILE": str(self.root),
            "CLAUDE_CONFIG_DIR": str(self.root / "claude"),
            "CODEX_HOME": str(self.root / "codex"),
            "APPDATA": str(self.root / "appdata"),
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        for name, value in (
            ("_claude_config_dir", self.root / "claude"),
            ("_codex_home", self.root / "codex"),
            ("_cursor_root", self.root / "cursor"),
            ("_cursor_desktop_paths", [self.root / "desktop/state.vscdb"]),
        ):
            mocked = patch.object(reader, name, return_value=value)
            mocked.start()
            self.addCleanup(mocked.stop)
        no_process = patch.object(reader.subprocess, "run", side_effect=AssertionError("No external process allowed"))
        no_process.start()
        self.addCleanup(no_process.stop)

    def write_jsonl(self, name, records):
        path = self.root / name
        path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
        return path

    def codes(self, result):
        return {item["code"] for item in result["warnings"]}

    def test_missing_homes_are_empty(self):
        for tool in reader.TOOLS:
            self.assertEqual(reader.discover_sessions(tool, str(self.root / "project")), [])

    def test_codex_analysis_never_rendered(self):
        path = self.write_jsonl("codex.jsonl", [
            {"type": "response_item", "payload": {"type": "message", "role": "assistant", "channel": "analysis", "content": [{"type": "output_text", "text": "PRIVATE_SENTINEL"}]}},
            {"type": "response_item", "payload": {"type": "message", "role": "assistant", "channel": "final", "content": [{"type": "output_text", "text": "public"}]}},
        ])
        result = reader.read_codex_session(path)
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(result))
        self.assertEqual(result["last_assistant_action"], "public")
        self.assertIn("unsafe_records_skipped", self.codes(result))

    def test_cursor_analysis_and_tool_reasoning_never_rendered(self):
        path = self.write_jsonl("cursor.jsonl", [
            {"role": "assistant", "message": {"channel": "analysis", "content": "PRIVATE_SENTINEL"}},
            {"role": "tool", "content": [{"type": "reasoning", "text": "PRIVATE_SENTINEL"}, {"type": "text", "text": "public"}]},
        ])
        result = reader.read_cursor_session({"path": str(path), "source": "cursor-transcript"})
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(result))
        self.assertIn("public", json.dumps(result))
        self.assertIn("unsafe_records_skipped", self.codes(result))

    def test_claude_tool_reasoning_filtered(self):
        path = self.write_jsonl("claude.jsonl", [{"type": "user", "uuid": "u", "message": {"role": "user", "content": [{"type": "tool_result", "content": [{"type": "thinking", "text": "PRIVATE_SENTINEL"}, {"type": "text", "text": "public"}]}]}}])
        result = reader.read_claude_session(path)
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(result))
        self.assertIn("public", json.dumps(result))

    def test_cursor_store_without_related_transcript_warns_order(self):
        store = self.root / "store.db"
        with sqlite3.connect(store) as database:
            database.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
            database.execute("INSERT INTO blobs VALUES (?, ?)", ("hash", json.dumps({"role": "user", "content": "a request"})))
        before = store.read_bytes()
        candidate = reader._candidate_from_path("cursor", str(store), str(self.root))
        with patch.object(reader, "_ordered_cursor_transcript", return_value=None):
            result = reader.read_cursor_session(candidate)
        self.assertEqual(result["path"], str(store))
        self.assertIn("ordering_unknown", self.codes(result))
        self.assertIsNone(result["last_user_request"])
        self.assertEqual(before, store.read_bytes())

    def test_cursor_store_prefers_ordered_same_id_transcript(self):
        session_id = "00000000-0000-0000-0000-000000000000"
        session = self.root / session_id
        session.mkdir()
        store = session / "store.db"
        with sqlite3.connect(store) as database:
            database.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
        transcript = self.root / "cursor/projects/project/agent-transcripts" / session_id / (session_id + ".jsonl")
        transcript.parent.mkdir(parents=True)
        transcript.write_text(json.dumps({"role": "user", "content": "ordered request"}), encoding="utf-8")
        candidate = reader._candidate_from_path("cursor", str(store), str(self.root / "requested"))
        result = reader.read_cursor_session(candidate)
        self.assertEqual(result["path"], str(transcript))
        self.assertEqual(result["last_user_request"], "ordered request")
        self.assertIn("related_transcript_selected", self.codes(result))
        self.assertIsNone(result["cwd"])

    def test_cursor_related_lookup_rejects_path_traversal(self):
        self.assertIsNone(reader._ordered_cursor_transcript("../outside/*"))

    def test_cursor_related_lookup_escapes_arbitrary_exact_id(self):
        session_id = "custom[id]"
        transcript = self.root / "cursor/projects/project/agent-transcripts" / session_id / (session_id + ".jsonl")
        transcript.parent.mkdir(parents=True)
        transcript.write_text("{}", encoding="utf-8")
        self.assertEqual(reader._ordered_cursor_transcript(session_id), transcript)

    def test_sqlite_connection_is_read_only(self):
        store = self.root / "test.db"
        with sqlite3.connect(store) as database:
            database.execute("CREATE TABLE sample (value TEXT)")
        database = reader._open_sqlite_readonly(store)
        self.addCleanup(database.close)
        with self.assertRaises(sqlite3.Error):
            database.execute("INSERT INTO sample VALUES ('forbidden')")

    def test_explicit_cursor_source_workspace_is_not_requested_workspace(self):
        actual = str(self.root / "project-B")
        requested = str(self.root / "project-A")
        meta = self.root / "meta.json"
        store = self.root / "store.db"
        with sqlite3.connect(store) as database:
            database.execute("CREATE TABLE blobs (id TEXT, data TEXT)")
            database.execute("CREATE TABLE meta (key TEXT, value TEXT)")
        for value in ({"cwd": actual}, {"workspacePath": actual}, {"workspaceIdentifier": {"uri": {"fsPath": actual}}}):
            with self.subTest(metadata=value):
                meta.write_text(json.dumps(value), encoding="utf-8")
                for path in (store, meta):
                    candidate = reader._candidate_from_path("cursor", str(path), requested)
                    self.assertIsNone(candidate["cwd"])
                    self.assertEqual(reader.read_cursor_session(candidate)["cwd"], actual)
        meta.unlink()
        with sqlite3.connect(store) as database:
            database.execute("INSERT INTO meta VALUES (?, ?)", ("metadata", json.dumps({"cwd": actual})))
        candidate = reader._candidate_from_path("cursor", str(store), requested)
        self.assertEqual(reader.read_cursor_session(candidate)["cwd"], actual)

    def test_explicit_cursor_transcript_workspace_remains_unknown(self):
        path = self.write_jsonl("cursor.jsonl", [{"role": "user", "content": "hello"}])
        candidate = reader._candidate_from_path("cursor", str(path), str(self.root / "requested"))
        self.assertIsNone(reader.read_cursor_session(candidate)["cwd"])

    def test_native_cursor_desktop_id_keeps_source_workspace(self):
        store = self.root / "desktop/state.vscdb"
        store.parent.mkdir()
        session_id = "00000000-0000-0000-0000-000000000000"
        actual = str(self.root / "project-B")
        with sqlite3.connect(store) as database:
            database.execute("CREATE TABLE composerHeaders (composerId TEXT, lastUpdatedAt INTEGER, value TEXT, isArchived INTEGER, isSubagent INTEGER)")
            database.execute("INSERT INTO composerHeaders VALUES (?, ?, ?, 0, 0)", (session_id, 1700000000000, json.dumps({"cwd": actual})))
        candidate = reader._find_cursor_id(session_id, str(self.root / "project-A"))
        self.assertEqual(candidate["cwd"], actual)
        self.assertEqual(reader.read_cursor_session(candidate)["cwd"], actual)

    def test_claude_gaps_and_malformed_structure_warn(self):
        path = self.write_jsonl("claude.jsonl", [
            {"type": "system", "uuid": "boundary", "subtype": "compact_boundary"},
            {"type": "assistant", "uuid": "bad", "message": []},
            {"type": "user", "uuid": "u", "parentUuid": "missing", "timestamp": "2026-01-01", "message": {"role": "user", "content": [{"type": "tool_result", "content": "<persisted-output>missing"}]}},
        ])
        result = reader.read_claude_session(path)
        self.assertTrue({"compaction_gap", "missing_parent", "replacement_content_unavailable", "malformed_records_skipped"}.issubset(self.codes(result)))

    def test_unknown_cursor_schema_warns(self):
        path = self.write_jsonl("cursor.jsonl", [{"future_schema": "unknown"}])
        result = reader.read_cursor_session({"path": str(path), "source": "cursor-transcript"})
        self.assertIn("unsafe_records_skipped", self.codes(result))
        self.assertIn("transcript_content_unavailable", self.codes(result))

    def test_claude_discovery_does_not_read_other_projects(self):
        other = self.root / "claude/projects/other"
        other.mkdir(parents=True)
        (other / "00000000-0000-0000-0000-000000000000.jsonl").write_text("{}")
        with patch.object(reader, "read_claude_session", side_effect=AssertionError("Unrelated project read")):
            self.assertEqual(reader.discover_sessions("claude", str(self.root / "wanted")), [])

    def test_codex_head_does_not_use_whole_file_reader(self):
        path = self.write_jsonl("head.jsonl", [{"type": "session_meta", "payload": {"cwd": str(self.root)}}])
        with patch.object(reader, "_read_codex_jsonl", side_effect=AssertionError("Full file read")):
            self.assertEqual(reader._codex_rollout_head(path), {"cwd": str(self.root)})

    def test_cli_dash_reference_after_options(self):
        args = reader._build_parser().parse_intermixed_args(["claude", "show", "--cwd", str(self.root), "--json", "--", "-ref"])
        self.assertEqual(args.ref, "-ref")
        self.assertTrue(args.json)

    def test_nonfinite_timestamps_are_ignored(self):
        self.assertIsNone(reader._timestamp_to_millis(float("nan")))
        self.assertIsNone(reader._timestamp_to_millis(float("inf")))


if __name__ == "__main__":
    unittest.main()
