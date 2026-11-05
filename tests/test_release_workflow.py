"""Release boundaries: automated checks must not invoke legacy Production writes."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseWorkflowTests(unittest.TestCase):
    def test_production_diagnostics_cannot_run_on_push_or_pull_request(self):
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            source = path.read_text()
            if 'rztdbdurkjfrirsrrhtu.supabase.co/functions/' not in source:
                continue
            with self.subTest(workflow=path.name):
                trigger = source.split('\non:', 1)[1].split('\njobs:', 1)[0]
                self.assertNotRegex(trigger, r'(?m)^  (push|pull_request|schedule):')
                self.assertIn('workflow_dispatch:', trigger)
                self.assertIn('inputs.confirmation ==', source)
                self.assertIn('contents: read', source)

    def test_test_environment_installs_the_actual_runtime(self):
        dependencies = (ROOT / 'requirements-dev.txt').read_text().splitlines()
        self.assertIn('-r requirements.txt', dependencies)
        pipeline = (ROOT / '.github/workflows/test.yml').read_text()
        self.assertIn("python-version: '3.12'", pipeline)
        self.assertIn('pip install -r requirements-dev.txt', pipeline)
        for command in ('npm run lint', 'npm test', 'npm run build'):
            self.assertIn(command, pipeline)
        self.assertNotRegex(pipeline, re.compile(r'https://[^\s]+supabase.co'))
