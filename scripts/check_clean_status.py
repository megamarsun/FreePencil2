#!/usr/bin/env python3
import subprocess

result = subprocess.run(['git', 'status', '--short'], capture_output=True, text=True)
print(result.stdout)
if result.stdout.strip():
    raise SystemExit('Working tree is not clean')
print('Git working tree is clean.')
