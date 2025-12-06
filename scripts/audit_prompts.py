#!/usr/bin/env python3
"""Audit prompt usage in OLAV codebase."""

import re
from pathlib import Path

# 收集所有prompt使用
prompts_used = set()
pattern = re.compile(r'load_prompt\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']')
raw_pattern = re.compile(r'load_raw_template\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']')
guide_pattern = re.compile(r'load_tool_capability_guide\s*\(\s*["\']?([^"\')]+)["\']?\s*\)')

for py_file in Path('src/olav').rglob('*.py'):
    content = py_file.read_text(encoding='utf-8')
    for m in pattern.finditer(content):
        prompts_used.add(f'{m.group(1)}/{m.group(2)}')
    for m in raw_pattern.finditer(content):
        prompts_used.add(f'{m.group(1)}/{m.group(2)}')
    for m in guide_pattern.finditer(content):
        prompts_used.add(f'tools/{m.group(1)}_capability_guide')

print('=== USED PROMPTS ===')
for p in sorted(prompts_used):
    print(p)

# 检查config/prompts下的所有yaml文件
print('\n=== ALL PROMPT FILES ===')
prompts_dir = Path('config/prompts')
all_prompts = set()
for yaml_file in prompts_dir.rglob('*.yaml'):
    rel_path = yaml_file.relative_to(prompts_dir)
    # 去掉.yaml后缀
    prompt_path = str(rel_path.with_suffix('')).replace('\\', '/')
    all_prompts.add(prompt_path)
    print(prompt_path)

# 找出未使用的
print('\n=== UNUSED PROMPTS ===')
unused = all_prompts - prompts_used
for p in sorted(unused):
    if not p.startswith('archive/'):
        print(p)

# 找出缺失的
print('\n=== MISSING PROMPTS ===')
missing = prompts_used - all_prompts
for p in sorted(missing):
    print(p)
