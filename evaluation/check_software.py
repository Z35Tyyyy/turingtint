"""Execute actual unit/integration checks; emit a machine-readable receipt."""
from __future__ import annotations
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if __name__ == '__main__':
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern='test_*.py')
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    sys.stderr.write(stream.getvalue())
    passed = result.wasSuccessful() and result.testsRun > 0 and not result.skipped
    print(json.dumps({'status': 'passed' if passed else 'failed', 'summary': f'{result.testsRun} tests; {len(result.failures)} failures; {len(result.errors)} errors; {len(result.skipped)} skipped.', 'evidence': [{'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'skipped': len(result.skipped)}]}))
    sys.exit(0 if passed else 1)
