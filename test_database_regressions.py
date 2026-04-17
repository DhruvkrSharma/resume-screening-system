import os
import tempfile
import unittest
import sqlite3

from database import ResumeDatabase


class TestDatabaseRegressions(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db = ResumeDatabase(db_path=self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_role_upsert_preserves_identity(self):
        self.db.add_role("Data Intern", "python; sql")
        first_id = int(self.db.list_roles().iloc[0]["id"])
        self.db.add_role("Data Intern", "python; sql; pandas")
        roles_df = self.db.list_roles()
        self.assertEqual(len(roles_df), 1)
        self.assertEqual(int(roles_df.iloc[0]["id"]), first_id)

    def test_get_results_for_role_uses_validated_limit(self):
        self.db.add_role("ML Intern", "python; pytorch")
        role_id = int(self.db.list_roles().iloc[0]["id"])
        resume1 = self.db.add_resume("a.pdf", "text", "extracted")
        resume2 = self.db.add_resume("b.pdf", "text", "extracted")
        self.db.add_result(role_id, resume1, "python", 2, 0.80)
        self.db.add_result(role_id, resume2, "python", 2, 0.80)

        top_one = self.db.get_results_for_role(role_id, top_n=1)
        self.assertEqual(len(top_one), 1)
        self.assertEqual(list(top_one.columns).count("resume_id"), 1)

        with self.assertRaises(ValueError):
            self.db.get_results_for_role(role_id, top_n=0)
        with self.assertRaises(ValueError):
            self.db.get_results_for_role(role_id, top_n="abc")

    def test_foreign_keys_enforced(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.add_result(9999, 8888, "", 0, 0.0)


if __name__ == "__main__":
    unittest.main()
