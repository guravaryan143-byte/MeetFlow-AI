import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.extractor import MeetingExtractionAgent
from app.agents.memory import compute_embedding, cosine_similarity
from app.agents.transcription import TranscriptionAgent, validate_upload_file
from app.core.security import (
    compute_payload_hash,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class MeetFlowUnitTests(unittest.TestCase):
    def test_password_hashing_and_verification(self):
        hashed = hash_password("SuperSecret!2026")
        self.assertTrue(hashed.startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password("SuperSecret!2026", hashed))
        self.assertFalse(verify_password("WrongPassword", hashed))

    def test_jwt_create_verify_and_tamper_detection(self):
        token = create_access_token("u1", "test-user-01@example.test", "org1", "ADMIN", expires_minutes=10)
        decoded = decode_access_token(token)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["sub"], "u1")
        self.assertEqual(decoded["role"], "ADMIN")
        # Tampered token must fail
        tampered = token[:-4] + "AAAA"
        self.assertIsNone(decode_access_token(tampered))

    def test_upload_validation(self):
        self.assertEqual(validate_upload_file("sync.mp3", 1024), ("audio", ".mp3"))
        self.assertEqual(validate_upload_file("notes.vtt", 512), ("transcript", ".vtt"))
        with self.assertRaises(ValueError):
            validate_upload_file("malware.exe", 512)
        with self.assertRaises(ValueError):
            validate_upload_file("empty.txt", 0)

    def test_transcription_unknown_speaker_never_fabricated(self):
        agent = TranscriptionAgent()
        segs = agent.parse_transcript_segments(
            "[00:00:10] Unknown: We need to finalize the API spec.\n"
            "Just a raw unattributed line."
        )
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0]["speaker_label"], "Unknown Speaker")
        self.assertTrue(segs[0]["is_unknown"])
        self.assertEqual(segs[1]["speaker_label"], "Unknown Speaker")

    def test_extraction_does_not_invent_owner_or_deadline(self):
        transcriber = TranscriptionAgent()
        extractor = MeetingExtractionAgent()
        segs = transcriber.parse_transcript_segments(
            "[00:01:00] Unknown: We need to review the vendor contract."
        )
        out = extractor.extract("Vendor Sync", segs)
        self.assertEqual(len(out.action_items), 1)
        self.assertIsNone(out.action_items[0].assigned_name)
        self.assertIsNone(out.action_items[0].deadline)
        self.assertTrue(out.action_items[0].needs_review)

    def test_semantic_embedding_similarity(self):
        v1 = compute_embedding("Product launch date confirmed as December 10")
        v2 = compute_embedding("Propose moving product launch date to December 15")
        v3 = compute_embedding("Office snacks and coffee machine repair")
        self.assertGreater(cosine_similarity(v1, v2), cosine_similarity(v1, v3))

    def test_payload_hash_determinism(self):
        h1 = compute_payload_hash({"a": 1, "b": 2})
        h2 = compute_payload_hash({"b": 2, "a": 1})
        self.assertEqual(h1, h2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
