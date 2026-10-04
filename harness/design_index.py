#!/usr/bin/env python3
"""Writes DESIGN_INDEX.md: the public API of the grizzi design system, signatures only.

Usage: design_index.py <tools dir> <output dir>
Writes DESIGN_INDEX.md (names per package, read it whole) and DESIGN_API.md (full signatures, grep it).
"""
import re
import sys
from pathlib import Path

tools, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
ROOTS = [
    tools / 'design/src/main/java/it/grizzi/core/design',
    tools / 'design-foundation/src/main/java/it/grizzi/core/design/foundation',
]
SKIP = ('/cardprovider/logo/', '/defaults/icons/', '/preview/', '/markdown/', '/shimmer/', '/utils/')
DECL = re.compile(r'^(\s*)public\s+(?:(?:data|sealed|enum|value|abstract|open|inline|fun|const)\s+)*'
                  r'(fun|val|var|object|class|interface)\b')


def first_sentence(kdoc_lines):
    text = ' '.join(l.strip().lstrip('/*').strip() for l in kdoc_lines)
    text = re.sub(r'\s+', ' ', text).strip()
    m = re.match(r'(.+?[.!?])(\s|$)', text)
    return (m.group(1) if m else text)[:140]


def signature(lines, i):
    """The declaration starting at line i, up to its body, on one line; and the next line index."""
    text, depth, j = '', 0, i
    while j < len(lines):
        line = lines[j]
        for k, ch in enumerate(line):
            prev = line[k - 1:k]
            if ch == '(' or (ch == '<' and line[k + 1:k + 2] != '='):
                depth += 1
            elif ch == ')' or (ch == '>' and prev != '-' and line[k + 1:k + 2] != '='):
                depth -= 1
            elif depth <= 0 and (ch == '{' or (ch == '=' and line[k + 1:k + 2] != '=' and line[k - 1:k] not in '!<>=')):
                return (text + line[:k]).strip(), j
        text += line.strip() + ' '
        j += 1
        if depth <= 0:
            return text.strip(), j - 1
    return text.strip(), j


def extract(path):
    lines = path.read_text(errors='ignore').splitlines()
    out, kdoc, composable, i = [], [], False, 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith('/**'):
            kdoc = []
            while i < len(lines):
                kdoc.append(lines[i])
                if '*/' in lines[i]:
                    break
                i += 1
            i += 1
            continue
        if s.startswith('@Composable'):
            composable = True
            i += 1
            continue
        m = DECL.match(line)
        if m and 'private' not in s and 'internal' not in s:
            indent = len(m.group(1)) // 4
            sig, end = signature(lines, i)
            sig = re.sub(r'\s+', ' ', sig).replace('( ', '(').replace(' )', ')').replace(',)', ')')
            sig = sig.replace('public ', '')
            note = first_sentence(kdoc) if kdoc else ''
            prefix = '@Composable ' if composable else ''
            out.append('  ' * indent + f'- `{prefix}{sig}`' + (f' — {note}' if note else ''))
            i = end + 1 if m.group(2) == 'fun' else i + 1
        else:
            i += 1
        if s and not s.startswith('@') and not s.startswith('*'):
            kdoc, composable = ([] if not DECL.match(line) else kdoc), False
    return dedupe(out)


def dedupe(decls):
    seen, kept = {}, []
    for d in decls:
        indent = len(d) - len(d.lstrip())
        m = re.search(r'`(?:@Composable )?(?:fun|val|var|object|class|interface|\w+ class)\s+(?:[\w<>, ?]+\.)?(\w+)', d)
        key = (indent, m.group(1) if m else d)
        if key in seen:
            kept[seen[key]][1] += 1
            if 'AnnotatedString' in kept[seen[key]][0] and 'AnnotatedString' not in d:
                kept[seen[key]][0] = d
            continue
        seen[key] = len(kept)
        kept.append([d, 0])
    return [d + (f' (+{n} overload{"s" if n > 1 else ""})' if n else '') for d, n in kept]


NAME = re.compile(r'`(?:@Composable )?(?:fun|val|var|object|class|interface|\w+ class)\s+(?:[\w<>, ?]+\.)?(\w+)')

full, catalog = [], []
for root in ROOTS:
    for path in sorted(root.rglob('*.kt')):
        rel = str(path.relative_to(root))
        if any(skip in '/' + rel for skip in SKIP):
            continue
        decls = extract(path)
        if not decls:
            continue
        pkg = re.search(r'^package (\S+)', path.read_text(errors='ignore'), re.M)
        pkg = pkg.group(1) if pkg else ''
        full.append(f'### {pkg} · {path.name}\n' + '\n'.join(decls))
        names, current = [], None
        for d in decls:
            m = NAME.search(d)
            if not m:
                continue
            if d.startswith('  '):
                if current is not None:
                    current[1].append(m.group(1))
            else:
                current = [m.group(1), []]
                names.append(current)
        flat = ', '.join(n + (' {' + ', '.join(dict.fromkeys(sub)) + '}' if sub else '') for n, sub in names)
        catalog.append((pkg.replace('it.grizzi.core.design.', ''), flat))

by_pkg = {}
for pkg, flat in catalog:
    by_pkg.setdefault(pkg, []).append(flat)
index = """# Design system index (generated)

Every public declaration of `tools/design` and `tools/design-foundation`, by package (prefix `it.grizzi.core.design.`).
For a signature, grep `DESIGN_API.md` (for example `grep -n -A3 "object DesignButtons" DESIGN_API.md`); do not open the implementation files.

""" + '\n'.join(f'- `{pkg}`: ' + '; '.join(v) for pkg, v in by_pkg.items()) + '\n'
api = """# Design system API (generated)

Signatures only, bodies omitted. One section per source file: `### <package> · <file>`.

""" + '\n\n'.join(full) + '\n'
(out_dir / 'DESIGN_INDEX.md').write_text(index)
(out_dir / 'DESIGN_API.md').write_text(api)
for name in ('DESIGN_INDEX.md', 'DESIGN_API.md'):
    size = (out_dir / name).stat().st_size
    print(f'{name}: {size} bytes (~{size // 4} tokens)')
