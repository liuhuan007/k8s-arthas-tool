#!/usr/bin/env python3
"""
Temporary test runner
"""
import subprocess
import sys

def run_tests():
    """Run pytest and capture output"""
    cmd = [sys.executable, "-m", "pytest", "tests/test_connection_page_markup.py", "-v"]
    result = subprocess.run(cmd, cwd="e:/tmp/k8s-arthas-tool")
    return result.returncode

if __name__ == "__main__":
    sys.exit(run_tests())