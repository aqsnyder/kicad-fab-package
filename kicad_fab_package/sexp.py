"""Minimal KiCad s-expression parser that keeps text spans. Library module, imported by the other tools.

parse_top(text)        -> list of top-level items: {head, node, start, end, uuid}
                          node = [head, child, ...]; atoms are raw token strings (quoted strings keep their quotes).
parse_tree(text, pos)  -> one list parsed from text[pos] == '(' as an SNode, which also records the text span of
                          itself (.start, .end) and of every child (.spans[i]); used for sub-item text splices.
canon(node)            -> canonical one-line text (whitespace-insensitive comparison key)
get / getall / strip   -> child lookup by head, and a copy without the children whose head is in a set
load_board(path)       -> (text, items, nets): nets maps KiCad 9 net codes to quoted names (empty on KiCad 10)
norm(node, nets)       -> copy with every (net ...) reference written as (net "name"), so KiCad 9 (numeric) and
                          KiCad 10 (by name) items compare equal
read_text / write_text -> byte-exact file I/O (no newline translation)
"""
import re

_TOK = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+', re.S)

# children that hold zone fill results rather than design intent
FILL_KEYS = frozenset({'filled_polygon', 'fill_segments', 'filled_areas_thickness'})
# fields KiCad 10 writes that KiCad 9 does not (vias: capping/covering/plugging/filling)
K10_ONLY = frozenset({'capping', 'covering', 'plugging', 'filling'})
# what else differs between a KiCad 9 item and the same item saved by KiCad 10 without a design change: K9 zones
# carry (net_name ...) beside the net number, K10 footprints add (units ...) / (duplicate_pad_numbers_are_jumpers ...).
# Used by format-neutral comparisons. strip() is recursive, so a dimension's (units ...) is dropped too.
K10_DEFAULTS = K10_ONLY | frozenset({'net_name', 'units', 'duplicate_pad_numbers_are_jumpers'})
TRACK_HEADS = frozenset({'segment', 'via', 'arc'})


def parse_span(text, pos):
    """Parse one list starting at text[pos] == '('. Returns (node, end_pos)."""
    stack = []
    cur = None
    for m in _TOK.finditer(text, pos):
        t = m.group(0)
        if t == '(':
            new = []
            if cur is not None:
                cur.append(new)
                stack.append(cur)
            cur = new
        elif t == ')':
            if not stack:
                return cur, m.end()
            cur = stack.pop()
        else:
            cur.append(t)
    raise ValueError('unbalanced')


def parse_top(text):
    """Parse the children of the root list. Each item keeps its text span and its own (uuid ...) if it has one."""
    i = text.index('(')
    pos = i + 1
    items = []
    while True:
        m = _TOK.search(text, pos)
        if m is None:
            break
        t = m.group(0)
        if t == ')':
            break
        if t == '(':
            node, end = parse_span(text, m.start())
            uid = None
            for c in node[1:]:
                if isinstance(c, list) and c and c[0] == 'uuid':
                    uid = c[1].strip('"')
                    break
            items.append({'head': node[0], 'node': node, 'start': m.start(), 'end': end, 'uuid': uid})
            pos = end
        else:
            pos = m.end()
    return items


class SNode(list):
    """A parsed list that remembers its text span (.start, .end) and the span of each element (.spans)."""
    __slots__ = ('start', 'end', 'spans')


def parse_tree(text, pos):
    """Parse one list starting at text[pos] == '(' into SNodes with spans."""
    stack = []
    cur = None
    for m in _TOK.finditer(text, pos):
        t = m.group(0)
        if t == '(':
            new = SNode()
            new.start = m.start()
            new.spans = []
            if cur is not None:
                cur.append(new)
                cur.spans.append(None)
                stack.append(cur)
            cur = new
        elif t == ')':
            cur.end = m.end()
            if not stack:
                return cur
            parent = stack.pop()
            parent.spans[-1] = (cur.start, cur.end)
            cur = parent
        else:
            cur.append(t)
            cur.spans.append((m.start(), m.end()))
    raise ValueError('unbalanced')


def canon(node):
    if isinstance(node, list):
        return '(' + ' '.join(canon(c) for c in node) + ')'
    return node


def get(node, key):
    for c in node[1:]:
        if isinstance(c, list) and c and c[0] == key:
            return c
    return None


def getall(node, key):
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == key]


def strip(node, keys):
    """Return a copy of node without children whose head is in keys (recursive)."""
    if not isinstance(node, list):
        return node
    out = [node[0]]
    for c in node[1:]:
        if isinstance(c, list) and c and c[0] in keys:
            continue
        out.append(strip(c, keys))
    return out


def is_teardrop(node):
    a = get(node, 'attr') if node and node[0] == 'zone' else None
    return a is not None and 'teardrop' in canon(a)


def read_text(path):
    with open(path, encoding='utf-8', newline='') as f:
        return f.read()


def write_text(path, text):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def load_board(path):
    text = read_text(path)
    items = parse_top(text)
    nets = {i['node'][1]: i['node'][2] for i in items if i['head'] == 'net'}
    return text, items, nets


def norm(node, nets):
    if not isinstance(node, list):
        return node
    if node and node[0] == 'net' and len(node) >= 2:
        v = node[1]
        if v in nets:
            return ['net', nets[v]]
        if len(node) == 3:
            return ['net', node[2]]
        return ['net', v]
    return [norm(c, nets) for c in node]


def board_version(text):
    m = re.search(r'\(version (\d+)\)', text[:400])
    return int(m.group(1)) if m else None
