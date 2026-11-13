#!/usr/bin/env python3
"""Convert a LaTeX document (or a bare LaTeX fragment) to a standalone HTML page.

Usage:
    python3 tex2html.py input.tex output.html
    python3 tex2html.py input.tex output.md     (GitHub-flavored Markdown)

Sections, text formatting, lists, tables, figures, theorems, footnotes,
cross-references, citations (from thebibliography or .bib files) and simple
user macros are converted.
Math is passed through as TeX: typeset in the browser by MathJax for HTML
output, or written as $...$ / $$...$$ for Markdown output.
Only the Python standard library is needed.
"""

import datetime
import html
import os
import re
import sys
import unicodedata
from html.parser import HTMLParser

# --------------------------------------------------------------------------
# Placeholder markers (private control characters) used during conversion.

PAR = '\x01'                                       # paragraph break
PH_RE = re.compile(r'\x00(\d+)\x00')               # protected math / verbatim
BLOCK_RE = re.compile(r'\x02(\d+)\x02')            # rendered block element
XREF_RE = re.compile(r'\x04(\w+):([^\x04]*)\x04')  # resolved at the very end

# --------------------------------------------------------------------------
# Tables of known commands.

SECTION_LEVELS = {'part': 0, 'chapter': 1, 'section': 2, 'subsection': 3,
                  'subsubsection': 4, 'paragraph': 5, 'subparagraph': 6}
SECTION_NAMES = {'part': 'Part', 'chapter': 'Chapter', 'section': 'Section',
                 'subsection': 'Section', 'subsubsection': 'Section',
                 'paragraph': 'Paragraph', 'subparagraph': 'Paragraph'}

EM = ('<em>', '</em>')
STRONG = ('<strong>', '</strong>')
CODE = ('<code>', '</code>')
SMALLCAPS = ('<span class="smallcaps">', '</span>')
SANS = ('<span class="sans">', '</span>')
PLAIN = ('', '')

INLINE_WRAP = {
    'textbf': STRONG, 'textit': EM, 'emph': EM, 'textsl': EM,
    'texttt': CODE, 'textsc': SMALLCAPS, 'textsf': SANS,
    'textrm': PLAIN, 'textup': PLAIN, 'textmd': PLAIN, 'textnormal': PLAIN,
    'mbox': PLAIN, 'hbox': PLAIN, 'text': PLAIN, 'makebox': PLAIN,
    'fbox': ('<span class="fbox">', '</span>'),
    'framebox': ('<span class="fbox">', '</span>'),
    'underline': ('<u>', '</u>'), 'uline': ('<u>', '</u>'),
    'sout': ('<s>', '</s>'), 'hl': ('<mark>', '</mark>'),
    'textsuperscript': ('<sup>', '</sup>'),
    'textsubscript': ('<sub>', '</sub>'),
}


DECLS = {
    'bf': STRONG, 'bfseries': STRONG,
    'it': EM, 'itshape': EM, 'em': EM, 'sl': EM, 'slshape': EM,
    'tt': CODE, 'ttfamily': CODE,
    'sc': SMALLCAPS, 'scshape': SMALLCAPS,
    'sf': SANS, 'sffamily': SANS,
    'rm': PLAIN, 'rmfamily': PLAIN, 'normalfont': PLAIN, 'upshape': PLAIN,
    'mdseries': PLAIN, 'normalsize': PLAIN,
}
SIZE_CLASSES = {'tiny': 'tiny', 'scriptsize': 'scriptsize',
                'footnotesize': 'footnotesize', 'small': 'small',
                'large': 'large', 'Large': 'large2', 'LARGE': 'large3',
                'huge': 'huge', 'Huge': 'huge2'}
for _size, _cls in SIZE_CLASSES.items():
    DECLS[_size] = ('<span class="size-%s">' % _cls, '</span>')

SYMBOLS = {
    'ldots': '\u2026', 'dots': '\u2026', 'textellipsis': '\u2026',
    'LaTeX': 'LaTeX', 'TeX': 'TeX', 'LaTeXe': 'LaTeX2\u03b5', 'BibTeX': 'BibTeX',
    'ss': '\u00df', 'ae': '\u00e6', 'AE': '\u00c6', 'oe': '\u0153', 'OE': '\u0152',
    'o': '\u00f8', 'O': '\u00d8', 'aa': '\u00e5', 'AA': '\u00c5', 'l': '\u0142',
    'L': '\u0141', 'i': '\u0131', 'j': '\u0237',
    'S': '\u00a7', 'P': '\u00b6', 'textsection': '\u00a7', 'textparagraph': '\u00b6',
    'copyright': '\u00a9', 'textcopyright': '\u00a9', 'textregistered': '\u00ae',
    'texttrademark': '\u2122', 'pounds': '\u00a3', 'textsterling': '\u00a3',
    'euro': '\u20ac', 'texteuro': '\u20ac', 'textdollar': '$', 'textyen': '\u00a5',
    'dag': '\u2020', 'ddag': '\u2021', 'textdagger': '\u2020',
    'textdaggerdbl': '\u2021', 'textbullet': '\u2022',
    'textperiodcentered': '\u00b7', 'textbackslash': '\\',
    'textasciitilde': '~', 'textasciicircum': '^', 'textunderscore': '_',
    'textbar': '|', 'textless': '<', 'textgreater': '>',
    'textbraceleft': '{', 'textbraceright': '}', 'textasteriskcentered': '*',
    'textendash': '\u2013', 'textemdash': '\u2014',
    'textquoteleft': '\u2018', 'textquoteright': '\u2019',
    'textquotedblleft': '\u201c', 'textquotedblright': '\u201d',
    'guillemotleft': '\u00ab', 'guillemotright': '\u00bb',
    'textdegree': '\u00b0', 'checkmark': '\u2713', 'slash': '/',
    'quad': '\u2003', 'qquad': '\u2003\u2003', 'enspace': '\u2002',
    'thinspace': '\u2009', 'enskip': '\u2002', 'hfill': ' ', 'dotfill': ' \u2026 ',
}

# Accents: control symbols (\' \" ...) and one-letter control words (\c \v ...).
ACCENTS = {"'": '\u0301', '`': '\u0300', '^': '\u0302', '"': '\u0308',
           '~': '\u0303', '=': '\u0304', '.': '\u0307', 'u': '\u0306',
           'v': '\u030c', 'H': '\u030b', 'c': '\u0327', 'k': '\u0328',
           'r': '\u030a', 'd': '\u0323', 'b': '\u0331', 't': ''}

# Commands whose output we drop: name -> number of mandatory arguments
# (a leading * and one optional [..] argument are skipped too).
IGNORE = {
    'documentclass': 1, 'usepackage': 1, 'RequirePackage': 1,
    'setlength': 2, 'addtolength': 2, 'setcounter': 2, 'addtocounter': 2,
    'stepcounter': 1, 'refstepcounter': 1, 'newlength': 1, 'newcounter': 1,
    'pagestyle': 1, 'thispagestyle': 1, 'pagenumbering': 1,
    'bibliographystyle': 1, 'addbibresource': 1, 'index': 1,
    'hypersetup': 1, 'graphicspath': 1, 'vspace': 1, 'hspace': 1,
    'addvspace': 1, 'addcontentsline': 3, 'enlargethispage': 1,
    'theoremstyle': 1, 'numberwithin': 2, 'counterwithin': 2,
    'counterwithout': 2, 'captionsetup': 1, 'lstset': 1, 'definecolor': 3,
    'linespread': 1, 'geometry': 1, 'phantom': 1, 'hphantom': 1,
    'vphantom': 1, 'markboth': 2, 'markright': 1, 'newtheorem': 2,
    'setstretch': 1, 'sisetup': 1, 'usetikzlibrary': 1, 'pgfplotsset': 1,
    'hyphenation': 1, 'fontsize': 2, 'includeonly': 1, 'footnotetext': 1,
}

NOOP = {
    'centering', 'raggedright', 'raggedleft', 'noindent', 'indent',
    'newpage', 'clearpage', 'cleardoublepage', 'pagebreak', 'nopagebreak',
    'smallskip', 'medskip', 'bigskip', 'vfill', 'hfil', 'protect', 'relax',
    'frenchspacing', 'nonfrenchspacing', 'sloppy', 'fussy', 'onecolumn',
    'twocolumn', 'hline', 'toprule', 'midrule', 'bottomrule', 'null',
    'strut', 'leavevmode', 'selectfont', 'makeatletter', 'makeatother',
    'FloatBarrier', 'allowbreak', 'nobreak', 'ignorespaces', 'unskip',
    'item', 'listoffigures', 'listoftables', 'printindex', 'makeindex',
    'frontmatter', 'mainmatter', 'backmatter', 'xspace', 'footnotemark',
    'break', 'clubpenalty',
}

CITE_CMDS = {'cite', 'citep', 'citet', 'citealp', 'citealt', 'Cite',
             'parencite', 'textcite', 'autocite', 'citeyear', 'citeauthor',
             'citeyearpar', 'supercite', 'footcite'}
REF_CMDS = {'ref', 'eqref', 'pageref', 'autoref', 'cref', 'Cref',
            'nameref', 'vref', 'Vref', 'Autoref'}

MATH_ENVS = {'equation', 'equation*', 'align', 'align*', 'alignat',
             'alignat*', 'gather', 'gather*', 'multline', 'multline*',
             'flalign', 'flalign*', 'eqnarray', 'eqnarray*', 'displaymath',
             'math', 'dmath', 'dmath*'}

TABULAR_ENVS = {'tabular', 'tabular*', 'tabularx', 'tabulary', 'longtable',
                'longtable*', 'supertabular', 'tabu'}
FLOAT_ENVS = {'figure', 'figure*', 'table', 'table*', 'wrapfigure',
              'wraptable', 'sidewaysfigure', 'sidewaystable', 'subfigure',
              'subtable', 'SCfigure'}

DEFAULT_THEOREMS = {
    'theorem': 'Theorem', 'lemma': 'Lemma', 'proposition': 'Proposition',
    'corollary': 'Corollary', 'definition': 'Definition', 'remark': 'Remark',
    'example': 'Example', 'conjecture': 'Conjecture', 'claim': 'Claim',
    'fact': 'Fact', 'observation': 'Observation', 'exercise': 'Exercise',
    'problem': 'Problem', 'question': 'Question', 'note': 'Note',
    'assumption': 'Assumption', 'hypothesis': 'Hypothesis',
    'notation': 'Notation', 'axiom': 'Axiom', 'property': 'Property',
    'solution': 'Solution',
}
PLAIN_THEOREMS = {'theorem', 'lemma', 'proposition', 'corollary',
                  'conjecture', 'claim', 'fact', 'observation', 'axiom',
                  'property', 'hypothesis'}

# --------------------------------------------------------------------------
# Low-level parsing helpers.

WS_RE = re.compile(r'[ \t]*(?:\n(?![ \t]*\n)[ \t]*)?')
CW_RE = re.compile(r'\\([A-Za-z]+)')
CS_ANY_RE = re.compile(r'\\(?:([A-Za-z]+)|.)', re.S)
BEGIN_RE = re.compile(r'\\begin\s*\{([^}]*)\}')
TEXT_RE = re.compile(r'[^\\{}\x00\n]+')
BLANK_RE = re.compile(r'\n[ \t]*\n\s*')
ITEM_RE = re.compile(r'\\item(?![A-Za-z])')
BIBITEM_RE = re.compile(r'\\bibitem(?![A-Za-z])')
ROW_RE = re.compile(r'\\\\\*?(?:[ \t]*\[[^\]]*\])?|\\tabularnewline(?![A-Za-z])')
AMP_RE = re.compile(r'&')
AND_RE = re.compile(r'\\(?:and|And|AND)(?![A-Za-z])')
RULE_RE = re.compile(
    r'\s*\\(?:hline|toprule|midrule|bottomrule|hdashline|morecmidrules'
    r'|endhead|endfirsthead|endfoot|endlastfoot'
    r'|cline\s*\{[^}]*\}|cdashline\s*\{[^}]*\}'
    r'|cmidrule\s*(?:\([^)]*\))?\s*\{[^}]*\}'
    r'|specialrule\s*\{[^}]*\}\s*\{[^}]*\}\s*\{[^}]*\}'
    r'|addlinespace(?:\s*\[[^\]]*\])?)(?![A-Za-z])')
DEF_RE = re.compile(
    r'\\(newcommand|renewcommand|providecommand|DeclareRobustCommand'
    r'|DeclareMathOperator|newenvironment|renewenvironment'
    r'|def|gdef|edef|xdef|newtheorem|theoremstyle)(?![A-Za-z])(\*?)')
COMMENT_RE = re.compile(r'(?<!\\)((?:\\\\)*)%[^\n]*(\n(?![ \t]*\n)[ \t]*)?')


def skip_ws(s, i):
    """Skip spaces and at most one line break (but never a blank line)."""
    return WS_RE.match(s, i).end()


def read_group(s, i):
    """s[i] == '{'. Return (contents, index after the matching '}')."""
    depth, j, n = 0, i, len(s)
    while j < n:
        c = s[j]
        if c == '\\':
            j += 2
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], n


def read_bracket(s, i):
    """s[i] == '['. Return (contents, index after the matching ']')."""
    depth, j, n = 0, i + 1, len(s)
    while j < n:
        c = s[j]
        if c == '\\':
            j += 2
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        elif c == ']' and depth == 0:
            return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], n


def read_arg(s, i):
    """Read a mandatory argument at i. Returns (text, new_i) or (None, i)."""
    j = skip_ws(s, i)
    if j >= len(s):
        return None, i
    c = s[j]
    if c == '{':
        return read_group(s, j)
    if c == '\\':
        m = CS_ANY_RE.match(s, j)
        return m.group(), m.end()
    if c == '\x00':
        k = s.index('\x00', j + 1)
        return s[j:k + 1], k + 1
    if c in '}' or c == PAR:
        return None, i
    return c, j + 1


def read_opt(s, i):
    """Read an optional [..] argument at i. Returns (text, new_i) or (None, i)."""
    j = skip_ws(s, i)
    if j < len(s) and s[j] == '[':
        return read_bracket(s, j)
    return None, i


def read_star(s, i):
    if i < len(s) and s[i] == '*':
        return True, i + 1
    return False, i


def find_env_end(s, i, name):
    """i is just after \\begin{name}. Return (start of \\end{name}, index after it)."""
    pat = re.compile(r'\\(begin|end)\s*\{' + re.escape(name) + r'\}')
    depth = 1
    for m in pat.finditer(s, i):
        if m.group(1) == 'begin':
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return m.start(), m.end()
    return len(s), len(s)


def find_delim(s, i, delim):
    """Find delim at or after i, skipping backslash escapes. -1 if absent."""
    j, n = i, len(s)
    while j < n:
        if s.startswith(delim, j):
            return j
        j += 2 if s[j] == '\\' else 1
    return -1


def split_top(s, sep_re):
    """Split s at sep_re matches that are outside braces and nested environments.

    Returns a list of (separator match or None, chunk following it)."""
    parts, last, last_m = [], 0, None
    i, n, depth = 0, len(s), 0
    while i < n:
        c = s[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        elif depth == 0 and (m := sep_re.match(s, i)) and m.end() > i:
            parts.append((last_m, s[last:i]))
            last_m, last = m, m.end()
            i = m.end()
            continue
        if c == '\\':
            m = BEGIN_RE.match(s, i)
            if m:
                i = find_env_end(s, m.end(), m.group(1))[1]
            else:
                i += 2
            continue
        i += 1
    parts.append((last_m, s[last:]))
    return parts


def parse_colspec(spec):
    """Return a list of CSS text-align values for a tabular column spec."""
    while True:
        m = re.search(r'\*\s*\{(\d+)\}\s*', spec)
        if not m or m.end() >= len(spec) or spec[m.end()] != '{':
            break
        body, e = read_group(spec, m.end())
        spec = spec[:m.start()] + body * int(m.group(1)) + spec[e:]
    aligns, i = [], 0
    while i < len(spec):
        c = spec[i]
        if c in 'lcr':
            aligns.append({'l': 'left', 'c': 'center', 'r': 'right'}[c])
        elif c in 'LCR':
            aligns.append({'L': 'left', 'C': 'center', 'R': 'right'}[c])
        elif c in 'pmbX':
            aligns.append('left')
        elif c == 'S':
            aligns.append('right')
        if c in 'pmb@!<>' or c == '{':
            j = skip_ws(spec, i + (0 if c == '{' else 1))
            if j < len(spec) and spec[j] == '{':
                i = read_group(spec, j)[1]
                continue
        i += 1
    return aligns


def css_length(value):
    """Translate a LaTeX length into CSS (percent for \\textwidth fractions)."""
    if not value:
        return None
    m = re.fullmatch(r'\s*([\d.]*)\s*\\(?:textwidth|linewidth|columnwidth|hsize)\s*', value)
    if m:
        return '%g%%' % (float(m.group(1) or 1) * 100)
    m = re.fullmatch(r'\s*([\d.]+)\s*(cm|mm|in|pt|px|em|ex|bp)\s*', value)
    if m:
        return m.group(1) + ('pt' if m.group(2) == 'bp' else m.group(2))
    return None


def roman(n):
    out = ''
    for v, r in ((1000, 'm'), (900, 'cm'), (500, 'd'), (400, 'cd'), (100, 'c'),
                 (90, 'xc'), (50, 'l'), (40, 'xl'), (10, 'x'), (9, 'ix'),
                 (5, 'v'), (4, 'iv'), (1, 'i')):
        while n >= v:
            out += r
            n -= v
    return out


def alpha(n):
    out = ''
    while n > 0:
        n, r = divmod(n - 1, 26)
        out = chr(97 + r) + out
    return out


def enum_label(depth, n):
    return [str(n), alpha(n), roman(n), alpha(n).upper()][(depth - 1) % 4]


def anchor(prefix, key):
    return prefix + re.sub(r'[^A-Za-z0-9_.:-]', '-', key)


def unwrap_p(h):
    if h.startswith('<p>') and h.endswith('</p>') and h.count('<p>') == 1:
        return h[3:-4]
    return h


def strip_tags(h):
    return html.unescape(re.sub(r'<[^>]+>', '', h))


BIB_MONTHS = {m[:3]: m for m in (
    'January', 'February', 'March', 'April', 'May', 'June', 'July',
    'August', 'September', 'October', 'November', 'December')}
BIB_MONTHS = {k.lower(): v for k, v in BIB_MONTHS.items()}


def parse_bib_value(s, i, strings):
    """Parse a field value at i: {..}, "..", a number or @string name, joined by #."""
    parts, n = [], len(s)
    while True:
        i = re.compile(r'\s*').match(s, i).end()
        if i >= n:
            break
        c = s[i]
        if c == '{':
            value, i = read_group(s, i)
        elif c == '"':
            j, depth = i + 1, 0
            while j < n and not (s[j] == '"' and depth == 0):
                depth += {'{': 1, '}': -1}.get(s[j], 0)
                j += 2 if s[j] == '\\' else 1
            value, i = s[i + 1:j], j + 1
        else:
            m = re.compile(r'[^\s,#{}"=]+').match(s, i)
            if not m:
                break
            value, i = strings.get(m.group().lower(), m.group()), m.end()
        parts.append(value)
        i = re.compile(r'\s*').match(s, i).end()
        if i < n and s[i] == '#':
            i += 1
            continue
        break
    return ''.join(parts), i


def parse_bib(text):
    """Parse a BibTeX database. Returns {key: (entry type, {field: value})}."""
    entries, strings = {}, dict(BIB_MONTHS)
    head = re.compile(r'@\s*(\w+)\s*([{(])')
    field = re.compile(r'[\s,]*([^\s,={}"#]+)\s*=\s*')
    i = 0
    while (m := head.search(text, i)):
        kind = m.group(1).lower()
        if m.group(2) == '{':
            body, i = read_group(text, m.end() - 1)
        else:
            end = text.find(')', m.end())
            end = len(text) if end < 0 else end
            body, i = text[m.end():end], end + 1
        if kind in ('comment', 'preamble'):
            continue
        if kind == 'string':
            fm = field.match(body)
            if fm:
                strings[fm.group(1).lower()] = parse_bib_value(body, fm.end(), strings)[0]
            continue
        key, _, rest = body.partition(',')
        fields, j = {}, 0
        while (fm := field.match(rest, j)):
            value, j = parse_bib_value(rest, fm.end(), strings)
            fields[fm.group(1).lower()] = value
        entries[key.strip()] = (kind, fields)
    return entries


def warn(msg):
    print('tex2html: ' + msg, file=sys.stderr)


# --------------------------------------------------------------------------

class Converter:
    def __init__(self, base_dir, out_dir):
        self.base_dir = base_dir
        self.out_dir = out_dir
        self.store = []          # protected snippets: (html, is_block)
        self.blocks = []         # rendered block-level HTML
        self.macros = {}         # name -> (nargs, default or None, body)
        self.envdefs = {}        # name -> (nargs, default, begin, end)
        self.theorems = {}       # env -> spec dict
        self.thm_style = 'plain'
        self.labels = {}         # key -> (number, kind name)
        self.label_target = ('??', '')
        self.footnotes = []
        self.toc = []
        self.bib = {}            # cite key -> label shown in [..]
        self.bibdb = {}          # entries read from .bib files: key -> (type, fields)
        self.bibdb_order = []
        self.cite_order = []     # keys in order of first citation
        self.nocite_all = False
        self.bib_placed = False
        self.counters = {}
        self.counter_prefix = {}
        self.sec = [0] * 7
        self.has_chapters = False
        self.appendix = False
        self.float_stack = []
        self.enum_depth = 0
        self.literal = 0
        self.meta = {}
        self.markdown = False
        self.eq_count = 0
        self.unknown = set()
        self.unknown_envs = set()
        today = datetime.date.today()
        self.symbols = dict(SYMBOLS, today='%s %d, %d' % (
            today.strftime('%B'), today.day, today.year))

        self.handlers = {
            'href': self.c_href, 'url': self.c_url, 'nolinkurl': self.c_url,
            'footnote': self.c_footnote, 'thanks': self.c_footnote,
            'label': self.c_label, 'includegraphics': self.c_includegraphics,
            'caption': self.c_caption, 'maketitle': self.c_maketitle,
            'tableofcontents': self.c_toc, 'newline': self.c_br,
            'linebreak': self.c_br, 'par': self.c_par,
            'appendix': self.c_appendix, 'textcolor': self.c_textcolor,
            'color': self.c_color, 'colorbox': self.c_colorbox,
            'bibliography': self.c_bibliography, 'rule': self.c_rule,
            'printbibliography': self.c_bibliography, 'nocite': self.c_nocite,
            'hrule': self.c_rule, 'hyperref': self.c_hyperref,
            'parbox': self.c_parbox, 'raisebox': self.c_raisebox,
            'and': self.c_and,
        }
        for name in SECTION_LEVELS:
            self.handlers[name] = self.c_section
        for name in REF_CMDS:
            self.handlers[name] = self.c_ref
        for name in CITE_CMDS:
            self.handlers[name] = self.c_cite

    # ------------------------------------------------------------ pipeline

    def convert(self, src, markdown=False):
        self.markdown = markdown
        src = self.preprocess(src, self.base_dir, 0)
        src = self.extract_definitions(src)
        self.load_bib_files(src)
        for key in ('title', 'author', 'date'):
            value, src = self.extract_command(src, key)
            if value is not None:
                self.meta[key] = value

        m = re.search(r'\\begin\s*\{document\}', src)
        if m:
            e = re.search(r'\\end\s*\{document\}', src[m.end():])
            body = src[m.end():m.end() + e.start()] if e else src[m.end():]
        else:
            body = src   # a bare fragment without preamble
        self.has_chapters = bool(re.search(r'\\chapter(?![A-Za-z])', body))

        body = self.protect_math(self.expand_macros(body))
        for key in self.meta:
            self.meta[key] = self.protect_math(self.expand_macros(self.meta[key]))

        content = self.paragraphs(self.render(body))
        if self.bib_placed:
            content = content.replace('\x04bibtex:\x04', self.bibtex_html())
        elif self.bibdb and self.cite_order:
            content += '\n' + self.bibtex_html()   # cited but never printed: append it
        if self.footnotes:
            items = ''.join(
                '<li id="fn%d">%s <a href="#fnref%d" class="footnote-back">'
                '\u21a9\ufe0e</a></li>\n' % (k, text, k)
                for k, text in enumerate(self.footnotes, 1))
            content += '\n<section class="footnotes">\n<ol>\n%s</ol>\n</section>' % items
        content = XREF_RE.sub(self.resolve_xref, content)
        content = XREF_RE.sub(self.resolve_xref, content)  # refs inside the TOC

        if self.unknown:
            warn('ignored unknown commands: ' + ', '.join(
                '\\' + n for n in sorted(self.unknown)))
        if self.unknown_envs:
            warn('rendered unknown environments as plain content: ' +
                 ', '.join(sorted(self.unknown_envs)))
        if markdown:
            return MarkdownWriter().convert(content)

        title = 'Document'
        if 'title' in self.meta:
            t = re.sub(r'\\thanks\s*\{[^{}]*\}', '', self.meta['title'])
            title = ' '.join(strip_tags(self.flatten(self.render(t), ' ')).split()) or title
        return (TEMPLATE.replace('%%TITLE%%', html.escape(title))
                .replace('%%CSS%%', CSS).replace('%%BODY%%', content))

    # ------------------------------------------------------------ preprocessing

    def preprocess(self, src, base, depth):
        """Protect verbatim text, strip comments and inline \\input files."""
        src = src.replace('\r\n', '\n').replace('\r', '\n')
        src = self.protect_verbatim(src)
        src = COMMENT_RE.sub(lambda m: m.group(1), src)

        def include(m):
            name = m.group(2).strip()
            for cand in (name, name + '.tex'):
                path = os.path.join(base, cand)
                if os.path.isfile(path) and depth < 20:
                    with open(path, encoding='utf-8', errors='replace') as f:
                        return self.preprocess(f.read(), os.path.dirname(path), depth + 1)
            warn('cannot find input file %r' % name)
            return ''
        return re.sub(r'\\(input|include|subfile)\s*\{([^}]*)\}', include, src)

    def protect(self, snippet, is_block=False):
        self.store.append((snippet, is_block))
        return '\x00%d\x00' % (len(self.store) - 1)

    def protect_verbatim(self, src):
        def env(m):
            name, body = m.group(1), m.group(2)
            lang = ''
            if name == 'lstlisting':
                opt = re.match(r'\s*\[([^\]]*)\]', body)
                if opt:
                    lm = re.search(r'language\s*=\s*\{?([\w+#-]+)', opt.group(1))
                    lang = lm.group(1) if lm else ''
                    body = body[opt.end():]
            elif name == 'minted':
                mm = re.match(r'\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}', body)
                if mm:
                    lang, body = mm.group(1), body[mm.end():]
            body = re.sub(r'^[ \t]*\n', '', body, count=1).rstrip()
            cls = ' class="language-%s"' % html.escape(lang.lower()) if lang else ''
            return self.protect('<pre><code%s>%s</code></pre>' % (
                cls, html.escape(body, quote=False)), True)

        def inline(m):
            return self.protect('<code>%s</code>' % html.escape(m.group(2), quote=False))

        src = re.sub(r'\\begin\{(verbatim\*?|Verbatim|lstlisting|minted)\}(.*?)\\end\{\1\}',
                     env, src, flags=re.S)
        src = re.sub(r'\\(?:verb\*?|lstinline(?:\[[^\]]*\])?)([^A-Za-z\s{*])(.*?)\1',
                     inline, src)
        src = re.sub(r'\\(lstinline|mintinline\{[^}]*\})\{([^}]*)\}', inline, src)
        return src

    def extract_definitions(self, s):
        """Record and remove \\newcommand, \\def, \\newenvironment, \\newtheorem."""
        out, pos = [], 0
        while True:
            m = DEF_RE.search(s, pos)
            if not m:
                break
            out.append(s[pos:m.start()])
            kind, star, j = m.group(1), m.group(2), m.end()
            if kind in ('def', 'gdef', 'edef', 'xdef'):
                dm = re.compile(r'\s*\\([A-Za-z@]+)((?:#\d)*)').match(s, j)
                if not dm:
                    out.append(m.group())
                    pos = j
                    continue
                body, j = read_arg(s, dm.end())
                self.add_macro(dm.group(1), len(dm.group(2)) // 2, None, body)
            elif kind in ('newcommand', 'renewcommand', 'providecommand',
                          'DeclareRobustCommand'):
                name, j = read_arg(s, j)
                nargs, j = read_opt(s, j)
                default, j = read_opt(s, j)
                body, j = read_arg(s, j)
                name = (name or '').strip().lstrip('\\')
                if not (kind == 'providecommand' and name in self.macros):
                    try:
                        n = int(nargs or 0)
                    except ValueError:
                        n = 0
                    self.add_macro(name, n, default, body)
            elif kind == 'DeclareMathOperator':
                name, j = read_arg(s, j)
                body, j = read_arg(s, j)
                self.add_macro((name or '').strip().lstrip('\\'), 0, None,
                               '\\operatorname%s{%s}' % (star, body or ''))
            elif kind in ('newenvironment', 'renewenvironment'):
                name, j = read_arg(s, j)
                nargs, j = read_opt(s, j)
                default, j = read_opt(s, j)
                begin, j = read_arg(s, j)
                end, j = read_arg(s, j)
                try:
                    n = int(nargs or 0)
                except ValueError:
                    n = 0
                self.envdefs[(name or '').strip()] = (n, default, begin or '', end or '')
            elif kind == 'newtheorem':
                env, j = read_arg(s, j)
                shared, j = read_opt(s, j)
                title, j = read_arg(s, j)
                within, j = read_opt(s, j)
                env = (env or '').strip()
                self.theorems[env] = {
                    'title': title or env, 'counter': (shared or env).strip(),
                    'numbered': not star, 'within': within and within.strip(),
                    'style': self.thm_style}
            elif kind == 'theoremstyle':
                style, j = read_arg(s, j)
                self.thm_style = (style or 'plain').strip()
            pos = j
        out.append(s[pos:])
        return ''.join(out)

    def add_macro(self, name, nargs, default, body):
        # Skip LaTeX-internals programming; we cannot emulate it.
        if name and body is not None and '@' not in name and '@' not in body:
            self.macros[name] = (nargs, default, body)

    def extract_command(self, s, name):
        m = re.search(r'\\%s(?![A-Za-z])\*?' % name, s)
        if not m:
            return None, s
        _, j = read_opt(s, m.end())
        value, j = read_arg(s, j)
        return value, s[:m.start()] + s[j:]

    def read_macro_args(self, s, j, nargs, default):
        args = []
        if default is not None and nargs > 0:
            opt, j = read_opt(s, j)
            args.append(default if opt is None else opt)
        while len(args) < nargs:
            a, j = read_arg(s, j)
            args.append(a or '')
        return args, j

    @staticmethod
    def substitute(body, args):
        return re.sub(r'#(\d)', lambda m: args[int(m.group(1)) - 1]
                      if 0 < int(m.group(1)) <= len(args) else '', body).replace('##', '#')

    def expand_macros(self, s):
        if self.envdefs:
            pat = re.compile(r'\\(begin|end)\s*\{(%s)\}' %
                             '|'.join(re.escape(e) for e in self.envdefs))
            for _ in range(10):
                out, pos, changed = [], 0, False
                while (m := pat.search(s, pos)):
                    out.append(s[pos:m.start()])
                    nargs, default, begin, end = self.envdefs[m.group(2)]
                    if m.group(1) == 'begin':
                        args, pos = self.read_macro_args(s, m.end(), nargs, default)
                        out.append(self.substitute(begin, args))
                    else:
                        out.append(end)
                        pos = m.end()
                    changed = True
                out.append(s[pos:])
                s = ''.join(out)
                if not changed:
                    break
        if not self.macros:
            return s
        for _ in range(30):
            out, pos, changed = [], 0, False
            while (m := CS_ANY_RE.search(s, pos)):
                name = m.group(1)
                if not name or name not in self.macros:
                    out.append(s[pos:m.end()])
                    pos = m.end()
                    continue
                out.append(s[pos:m.start()])
                nargs, default, body = self.macros[name]
                args, pos = self.read_macro_args(s, m.end(), nargs, default)
                rep = self.substitute(body, args)
                # keep "\foo x" from turning into "\alphax"
                if re.search(r'\\[A-Za-z]+$', rep) and pos < len(s) and s[pos].isalpha():
                    rep += ' '
                out.append(rep)
                changed = True
            out.append(s[pos:])
            s = ''.join(out)
            if not changed:
                break
        return s

    def protect_math(self, s):
        """Replace every piece of math with a placeholder holding MathJax-ready HTML."""
        def math(tex, display):
            cls = 'math display' if display else 'math inline'
            return self.protect('<span class="%s">%s</span>' % (
                cls, html.escape(tex, quote=False)))

        out, last, i, n = [], 0, 0, len(s)
        while i < n:
            c = s[i]
            rep = None
            if c == '\\':
                nxt = s[i + 1:i + 2]
                if nxt in ('(', '['):
                    close = '\\)' if nxt == '(' else '\\]'
                    e = find_delim(s, i + 2, close)
                    if e >= 0:
                        rep, end = math(s[i:e + 2], nxt == '['), e + 2
                elif s.startswith('begin', i + 1):
                    m = BEGIN_RE.match(s, i)
                    if m and m.group(1).strip() in MATH_ENVS:
                        env = m.group(1).strip()
                        es, end = find_env_end(s, m.end(), m.group(1))
                        inner = s[m.end():es]
                        if env == 'math':
                            rep = math('\\(' + inner + '\\)', False)
                        elif env == 'displaymath':
                            rep = math('\\[' + inner + '\\]', True)
                        elif self.markdown:
                            rep = self.number_equations(env, inner, math)
                        else:
                            rep = math(s[i:end], True)
                elif s.startswith('ensuremath', i + 1) and not s[i + 11:i + 12].isalpha():
                    arg, end = read_arg(s, i + 11)
                    rep = math('\\(' + (arg or '') + '\\)', False)
                if rep is None:
                    i += 2
                    continue
            elif c == '$':
                if s.startswith('$$', i):
                    e = find_delim(s, i + 2, '$$')
                    if e >= 0:
                        rep, end = math('\\[' + s[i + 2:e] + '\\]', True), e + 2
                else:
                    e = find_delim(s, i + 1, '$')
                    if e >= 0:
                        rep, end = math('\\(' + s[i + 1:e] + '\\)', False), e + 1
                if rep is None:
                    i += 1
                    continue
            else:
                i += 1
                continue
            out.append(s[last:i])
            out.append(rep)
            last = i = end
        out.append(s[last:])
        return ''.join(out)

    def number_equations(self, env, inner, math):
        """Markdown output: number display equations with \\tag and record their labels.

        Markdown renderers typeset each math block on its own, so they cannot
        resolve \\label/\\eqref across blocks; we number equations ourselves."""
        base = env.rstrip('*')
        numbered = not env.endswith('*')
        rows = [chunk for _, chunk in split_top(inner, re.compile(r'\\\\'))]
        if base in ('equation', 'dmath'):
            rows = [inner]
        anchors, out_rows, labels = [], [], []
        for idx, row in enumerate(rows):
            # a multline is one equation: its labels wait for the number on the last row
            if base != 'multline' or idx == 0:
                labels = []
            labels += re.findall(r'\\label\s*\{([^}]*)\}', row)
            row = re.sub(r'\\label\s*\{[^}]*\}', '', row)
            tag = re.search(r'\\tag\*?\s*\{([^}]*)\}', row)
            number = None
            if re.search(r'\\(?:nonumber|notag)(?![A-Za-z])', row):
                row = re.sub(r'\\(?:nonumber|notag)(?![A-Za-z])', '', row)
            elif tag:
                number = tag.group(1)
            elif numbered and (base != 'multline' or idx == len(rows) - 1) and row.strip():
                self.eq_count += 1
                number = str(self.eq_count)
                row = row.rstrip() + ' \\tag{%s}' % number
            if base == 'multline' and idx < len(rows) - 1:
                out_rows.append(row)
                continue
            for key in labels:
                key = key.strip()
                self.labels[key] = (number or '??', 'Equation')
                anchors.append('<span id="%s" class="label-anchor"></span>' % anchor('lbl-', key))
            out_rows.append(row)
        if base in ('equation', 'dmath'):
            tex = '\\[' + out_rows[0] + '\\]'
        else:
            star = base + '*'
            tex = '\\begin{%s}%s\\end{%s}' % (star, '\\\\'.join(out_rows), star)
        placeholder = math(tex, True)
        return self.protect(''.join(anchors)) + placeholder if anchors else placeholder

    # ------------------------------------------------------------ rendering core

    def block(self, h):
        self.blocks.append(h)
        return '%s\x02%d\x02%s' % (PAR, len(self.blocks) - 1, PAR)

    def paragraphs(self, h):
        """Turn a rendered stream into HTML paragraphs and block elements."""
        res = []
        for chunk in h.split(PAR):
            t = chunk.strip()
            if not t:
                continue
            m = BLOCK_RE.fullmatch(t)
            if m:
                res.append(self.blocks[int(m.group(1))])
            elif re.fullmatch(r'(?:<span id="[^"]*" class="label-anchor"></span>\s*)+', t):
                res.append(t)
            else:
                res.append('<p>%s</p>' % self.flatten(t, ' '))
        return '\n'.join(res)

    def flatten(self, h, par):
        """Render a stream inline: paragraph breaks become `par`."""
        h = BLOCK_RE.sub(lambda m: self.blocks[int(m.group(1))], h)
        h = h.replace(PAR + PAR, PAR)
        return h.strip(PAR).replace(PAR, par).strip()

    def blocks_html(self, tex):
        return self.paragraphs(self.render(tex))

    def inline(self, tex):
        return self.flatten(self.render(tex or ''), ' ')

    def wrap(self, open_, close, h):
        if not open_:
            return h
        if PAR not in h:
            return open_ + h + close
        return PAR.join(open_ + p + close
                        if p.strip() and not BLOCK_RE.fullmatch(p.strip()) else p
                        for p in h.split(PAR))

    def text(self, t):
        t = html.escape(t, quote=False)
        if not self.literal:
            t = (t.replace('---', '\u2014').replace('--', '\u2013')
                 .replace('``', '\u201c').replace("''", '\u201d')
                 .replace('`', '\u2018').replace("'", '\u2019'))
        return t.replace('~', '\u00a0')

    def render(self, s):
        out, i, n = [], 0, len(s)
        while i < n:
            c = s[i]
            if c == '\\':
                i = self.command(s, i, out)
            elif c == '{':
                inner, i = read_group(s, i)
                out.append(self.render(inner))
            elif c == '}':
                i += 1
            elif c == '\x00':
                m = PH_RE.match(s, i)
                snippet, is_block = self.store[int(m.group(1))]
                out.append(self.block(snippet) if is_block else snippet)
                i = m.end()
            elif c == '\n':
                m = BLANK_RE.match(s, i)
                if m:
                    out.append(PAR)
                    i = m.end()
                else:
                    out.append('\n')
                    i += 1
            else:
                m = TEXT_RE.match(s, i)
                out.append(self.text(m.group()))
                i = m.end()
        return ''.join(out)

    def command(self, s, i, out):
        m = CW_RE.match(s, i)
        if not m:
            return self.control_symbol(s, i, out)
        name, j = m.group(1), m.end()

        if name == 'begin':
            env, j = read_arg(s, j)
            env = (env or '').strip()
            end, after = find_env_end(s, j, env)
            out.append(self.environment(env, s[j:end]))
            return after
        if name == 'end':
            return read_arg(s, j)[1]
        handler = self.handlers.get(name)
        if handler:
            return handler(s, j, out, name)
        if name in INLINE_WRAP:
            if name in ('makebox', 'framebox'):
                _, j = read_opt(s, j)
                _, j = read_opt(s, j)
            arg, j = read_arg(s, j)
            lit = name == 'texttt'
            self.literal += lit
            h = self.render(arg or '')
            self.literal -= lit
            out.append(self.wrap(*INLINE_WRAP[name], h))
            return j
        if name in DECLS:
            lit = name in ('tt', 'ttfamily')
            self.literal += lit
            h = self.render(s[skip_ws(s, j):])
            self.literal -= lit
            out.append(self.wrap(*DECLS[name], h))
            return len(s)
        if name in self.symbols:
            out.append(html.escape(self.symbols[name], quote=False))
            return skip_ws(s, j)
        if name in ACCENTS and len(name) == 1:
            arg, j = read_arg(s, j)
            out.append(self.accent(name, arg))
            return j
        if name in IGNORE:
            _, j = read_star(s, j)
            _, j = read_opt(s, j)
            for _ in range(IGNORE[name]):
                _, j = read_arg(s, j)
            return j
        if name in NOOP:
            return skip_ws(s, j)
        self.unknown.add(name)
        return skip_ws(s, j)

    def control_symbol(self, s, i, out):
        c = s[i + 1:i + 2]
        j = i + 2
        if c == '\\':
            _, j = read_star(s, j)
            if j < len(s) and s[j] == '[':
                _, j = read_bracket(s, j)
            out.append('<br>\n')
        elif c in ACCENTS and c:
            arg, j = read_arg(s, j)
            out.append(self.accent(c, arg))
        elif c in ('&', '%', '$', '#', '_', '{', '}'):
            out.append(html.escape(c))
        elif c in (' ', '\n', '\t'):
            out.append(' ')
        elif c == ',':
            out.append('\u2009')
        elif c in (';', ':', '>'):
            out.append('\u2005')
        elif c in ('!', '/', '@', '-', ''):
            pass
        else:
            out.append(html.escape(c))
        return j

    def accent(self, c, arg):
        mark = ACCENTS[c]
        if arg is None or not arg.strip():
            return html.escape({'~': '~', '^': '^', '"': '"', "'": "'", '`': '`'}.get(c, ''))
        base = arg.strip()
        if base in ('\\i', '\\j'):
            base = base[1]
        rendered = self.inline(base)
        if rendered and rendered[0].isalpha():
            return unicodedata.normalize('NFC', rendered[0] + mark + rendered[1:])
        return rendered

    # ------------------------------------------------------------ commands

    def section_number(self, level):
        top = 1 if self.has_chapters else 2
        parts = []
        for k in range(top, level + 1):
            v = self.sec[k]
            parts.append(chr(64 + v) if k == top and self.appendix and v else str(v))
        return '.'.join(parts)

    def c_section(self, s, j, out, name):
        star, j = read_star(s, j)
        _, j = read_opt(s, j)
        title, j = read_arg(s, j)
        level = SECTION_LEVELS[name]
        top = 1 if self.has_chapters else 2
        number = ''
        if not star and (name == 'part' or top <= level <= top + 2):
            self.sec[level] += 1
            for k in range(level + 1, 7):
                self.sec[k] = 0
            number = roman(self.sec[0]).upper() if name == 'part' else self.section_number(level)
            self.label_target = (number, 'Appendix' if self.appendix and level == top
                                 else SECTION_NAMES[name])
        title_html = self.inline(title)
        h = 1 if name == 'part' else max(2, min(6, level - top + 2))
        anchor_id = 'sec-%d' % (len(self.toc) + 1)
        if not star:
            self.toc.append((level, number, title_html, anchor_id))
        num_html = '<span class="secnum">%s</span> ' % number if number else ''
        if name == 'part' and number:
            num_html = '<span class="secnum">Part %s</span><br>' % number
        elif name == 'chapter' and number:
            num_html = '<span class="secnum">%s %s</span><br>' % (
                'Appendix' if self.appendix else 'Chapter', number)
        out.append(self.block('<h%d id="%s" class="%s">%s%s</h%d>' % (
            h, anchor_id, name, num_html, title_html, h)))
        return j

    def c_label(self, s, j, out, name):
        key, j = read_arg(s, j)
        key = (key or '').strip()
        self.labels[key] = self.label_target
        out.append('<span id="%s" class="label-anchor"></span>' % anchor('lbl-', key))
        return j

    def c_ref(self, s, j, out, name):
        _, j = read_star(s, j)
        key, j = read_arg(s, j)
        out.append('\x04%s:%s\x04' % (name, (key or '').strip()))
        return j

    def c_cite(self, s, j, out, name):
        _, j = read_star(s, j)
        opt1, j = read_opt(s, j)
        opt2, j = read_opt(s, j)
        keys, j = read_arg(s, j)
        pre, post = (opt1, opt2) if opt2 is not None else (None, opt1)
        keys = self.record_cites(keys)
        refs = ', '.join('\x04cite:%s\x04' % k for k in keys)
        text = '['
        if pre:
            text += self.inline(pre) + ' '
        text += refs
        if post:
            text += ', ' + self.inline(post)
        out.append(text + ']')
        return j

    def resolve_xref(self, m):
        kind, key = m.group(1), m.group(2)
        if kind == 'toc':
            return self.toc_html()
        if kind == 'cite':
            if key in self.bib:
                return '<a href="#%s" class="cite">%s</a>' % (anchor('bib-', key), self.bib[key])
            return '<span class="cite missing">%s</span>' % html.escape(key)
        if key in self.labels:
            number, what = self.labels[key]
            if kind == 'eqref':
                text = '(%s)' % number
            elif kind in ('autoref', 'Autoref', 'cref', 'Cref', 'vref', 'Vref') and what:
                text = '%s\u00a0%s' % (what, number)
            else:
                text = number
            return '<a href="#%s" class="ref">%s</a>' % (anchor('lbl-', key), text)
        # Not a label we saw: most likely an equation label, which MathJax numbers.
        k = html.escape(key)
        if kind == 'eqref':
            return '<span class="math inline">\\(\\eqref{%s}\\)</span>' % k
        prefix = 'Equation\u00a0' if kind in ('autoref', 'Autoref', 'cref', 'Cref') else ''
        return '%s<span class="math inline">\\(\\ref{%s}\\)</span>' % (prefix, k)

    def c_href(self, s, j, out, name):
        url, j = read_arg(s, j)
        text, j = read_arg(s, j)
        url = re.sub(r'\\([#%&_~$])', r'\1', (url or '').strip())
        out.append('<a href="%s">%s</a>' % (html.escape(url), self.inline(text)))
        return j

    def c_url(self, s, j, out, name):
        url, j = read_arg(s, j)
        url = re.sub(r'\\([#%&_~$])', r'\1', (url or '').strip())
        if name == 'nolinkurl':
            out.append('<code>%s</code>' % html.escape(url))
        else:
            out.append('<a href="%s" class="url">%s</a>' % (html.escape(url), html.escape(url)))
        return j

    def c_hyperref(self, s, j, out, name):
        key, j = read_opt(s, j)
        text, j = read_arg(s, j)
        if key is None:   # \hyperref{url}{category}{name}{text}
            _, j = read_arg(s, j)
            _, j = read_arg(s, j)
            text, j = read_arg(s, j)
            out.append(self.inline(text))
        else:
            out.append('<a href="#%s">%s</a>' % (anchor('lbl-', key.strip()), self.inline(text)))
        return j

    def c_footnote(self, s, j, out, name):
        _, j = read_opt(s, j)
        text, j = read_arg(s, j)
        self.footnotes.append('')
        n = len(self.footnotes)
        self.footnotes[n - 1] = unwrap_p(self.blocks_html(text or ''))
        out.append('<sup class="footnote-ref"><a href="#fn%d" id="fnref%d">%d</a></sup>'
                   % (n, n, n))
        return j

    def c_br(self, s, j, out, name):
        _, j = read_star(s, j)
        _, j = read_opt(s, j)
        out.append('<br>\n')
        return j

    def c_par(self, s, j, out, name):
        out.append(PAR)
        return skip_ws(s, j)

    def c_and(self, s, j, out, name):
        out.append(' and ')
        return skip_ws(s, j)

    def c_appendix(self, s, j, out, name):
        self.appendix = True
        top = 1 if self.has_chapters else 2
        self.sec[top] = 0
        return skip_ws(s, j)

    @staticmethod
    def css_color(model, color):
        color = (color or '').strip()
        if model is None and re.fullmatch(r'[A-Za-z]+', color):
            return color
        if model == 'HTML' and re.fullmatch(r'[0-9A-Fa-f]{6}', color):
            return '#' + color
        return None

    def c_textcolor(self, s, j, out, name):
        model, j = read_opt(s, j)
        color, j = read_arg(s, j)
        text, j = read_arg(s, j)
        css = self.css_color(model, color)
        h = self.render(text or '')
        out.append(self.wrap('<span style="color:%s">' % css, '</span>', h) if css else h)
        return j

    def c_colorbox(self, s, j, out, name):
        model, j = read_opt(s, j)
        color, j = read_arg(s, j)
        text, j = read_arg(s, j)
        css = self.css_color(model, color)
        style = ' style="background:%s"' % css if css else ''
        out.append('<span class="colorbox"%s>%s</span>' % (style, self.inline(text)))
        return j

    def c_color(self, s, j, out, name):
        model, j = read_opt(s, j)
        color, j = read_arg(s, j)
        css = self.css_color(model, color)
        h = self.render(s[j:])
        out.append(self.wrap('<span style="color:%s">' % css, '</span>', h) if css else h)
        return len(s)

    def c_rule(self, s, j, out, name):
        if name == 'rule':
            _, j = read_opt(s, j)
            width, j = read_arg(s, j)
            _, j = read_arg(s, j)
            if not (width and 'width' in width):
                return j
        out.append(self.block('<hr>'))
        return j

    def c_parbox(self, s, j, out, name):
        for _ in range(3):
            _, j = read_opt(s, j)
        _, j = read_arg(s, j)
        text, j = read_arg(s, j)
        out.append(self.render(text or ''))
        return j

    def c_raisebox(self, s, j, out, name):
        _, j = read_arg(s, j)
        _, j = read_opt(s, j)
        _, j = read_opt(s, j)
        text, j = read_arg(s, j)
        out.append(self.render(text or ''))
        return j

    def record_cites(self, keys):
        keys = [k.strip() for k in (keys or '').split(',') if k.strip()]
        for k in keys:
            if k == '*':
                self.nocite_all = True
            elif k not in self.cite_order:
                self.cite_order.append(k)
        return [k for k in keys if k != '*']

    def c_nocite(self, s, j, out, name):
        keys, j = read_arg(s, j)
        self.record_cites(keys)
        return j

    def c_bibliography(self, s, j, out, name):
        _, j = read_opt(s, j)
        if name == 'bibliography':
            _, j = read_arg(s, j)
        if not self.bib_placed:   # files were loaded up front by load_bib_files
            self.bib_placed = True
            out.append(self.block('\x04bibtex:\x04'))
        return j

    # ------------------------------------------------------------ BibTeX

    def load_bib_files(self, src):
        """Read every database named by \\bibliography{..} or \\addbibresource{..}."""
        for m in re.finditer(r'\\(?:bibliography|addbibresource)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}', src):
            for name in m.group(1).split(','):
                name = name.strip()
                if not name:
                    continue
                if not name.lower().endswith('.bib'):
                    name += '.bib'
                path = os.path.join(self.base_dir, name)
                try:
                    with open(path, encoding='utf-8', errors='replace') as f:
                        entries = parse_bib(f.read())
                except OSError:
                    warn('cannot find bibliography file %r' % name)
                    continue
                for key, entry in entries.items():
                    if key not in self.bibdb:
                        self.bibdb_order.append(key)
                    self.bibdb[key] = entry

    def bib_field(self, value):
        """Render a BibTeX field value (which is LaTeX) as inline HTML."""
        return self.inline(self.protect_math(self.expand_macros(' '.join(value.split()))))

    def bib_names(self, value):
        names = []
        for _, name in split_top(value, re.compile(r'\s+and\s+', re.I)):
            name = name.strip()
            if name.lower() == 'others':
                names.append(None)
                continue
            parts = [p.strip() for _, p in split_top(name, re.compile(','))]
            if len(parts) == 2:          # Last, First
                name = parts[1] + ' ' + parts[0]
            elif len(parts) >= 3:        # Last, Jr, First
                name = '%s %s, %s' % (parts[2], parts[0], parts[1])
            names.append(self.bib_field(name))
        et_al = None in names
        names = [n for n in names if n]
        if et_al:
            return ', '.join(names) + ' et al.'
        if len(names) <= 2:
            return ' and '.join(names)
        return ', '.join(names[:-1]) + ', and ' + names[-1]

    def bib_entry(self, kind, f):
        parts = []
        people = f.get('author') or f.get('editor')
        if people:
            parts.append(self.bib_names(people) + (' (ed.)' if 'author' not in f else ''))
        if f.get('title'):
            parts.append(self.bib_field(f['title']))
        venue = next((f[k] for k in ('journal', 'journaltitle', 'booktitle', 'school',
                                     'institution', 'organization', 'howpublished',
                                     'publisher') if f.get(k)), None)
        eprint = f.get('eprint')
        is_arxiv = eprint and f.get('archiveprefix', f.get('eprinttype', '')).lower() == 'arxiv'
        if venue:
            parts.append('<em>%s</em>' % self.bib_field(venue))
        elif is_arxiv:
            parts.append('arXiv:%s' % html.escape(eprint))
        year = f.get('year') or f.get('date', '')[:4]
        if year:
            parts.append(self.bib_field(year))
        url = f.get('url')
        if not url and f.get('doi'):
            url = 'https://doi.org/' + re.sub(r'^https?://(dx\.)?doi\.org/', '', f['doi'].strip())
        if not url and is_arxiv:
            url = 'https://arxiv.org/abs/' + eprint.strip()
        if url:
            url = re.sub(r'\\([#%&_~$])', r'\1', re.sub(r'^\\url\{(.*)\}$', r'\1', url.strip()))
            parts.append('<a href="%s" class="url">%s</a>' % (html.escape(url), html.escape(url)))
        return ', '.join(parts)

    def bibtex_html(self):
        keys = list(self.cite_order)
        if self.nocite_all:
            keys += [k for k in self.bibdb_order if k not in keys]
        lower = {k.lower(): k for k in self.bibdb}
        items, missing = [], []
        for key in keys:
            entry = self.bibdb.get(key) or self.bibdb.get(lower.get(key.lower(), ''))
            if entry is None:
                if key not in self.bib:
                    missing.append(key)
                continue
            n = len(items) + 1
            self.bib[key] = str(n)
            items.append('<li id="%s"><span class="bib-label">[%d]</span> %s</li>' % (
                anchor('bib-', key), n, self.bib_entry(*entry)))
        if missing:
            warn('citation keys not found in the bibliography: ' + ', '.join(missing))
        if not items:
            return ''
        heading = 'Bibliography' if self.has_chapters else 'References'
        return ('<section class="bibliography">\n<h2>%s</h2>\n<ul>\n%s\n</ul>\n</section>'
                % (heading, '\n'.join(items)))

    def resolve_image(self, path):
        base, ext = os.path.splitext(path)
        web = ['.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp']
        candidates = [path] if ext.lower() in web else []
        candidates += [base + e for e in web] if ext.lower() in ('', '.pdf', '.eps', '.ps') else []
        candidates += [path]
        for cand in candidates:
            full = os.path.join(self.base_dir, cand)
            if os.path.isfile(full):
                return os.path.relpath(full, self.out_dir).replace(os.sep, '/')
        warn('image not found: %s' % path)
        return path if ext else path + '.png'

    def c_includegraphics(self, s, j, out, name):
        _, j = read_star(s, j)
        opt, j = read_opt(s, j)
        path, j = read_arg(s, j)
        path = (path or '').strip()
        style = []
        for prop in ('width', 'height'):
            m = re.search(r'(?<![a-z])%s\s*=\s*([^,]+)' % prop, opt or '')
            css = css_length(m.group(1)) if m else None
            if css:
                style.append('%s:%s' % (prop, css))
        out.append('<img src="%s" alt="%s"%s>' % (
            html.escape(self.resolve_image(path)),
            html.escape(os.path.basename(path)),
            ' style="%s"' % ';'.join(style) if style else ''))
        if self.float_stack:
            self.float_stack[-1]['content_seen'] = True
        return j

    def c_caption(self, s, j, out, name):
        _, j = read_star(s, j)
        _, j = read_opt(s, j)
        text, j = read_arg(s, j)
        if not self.float_stack:
            out.append(self.block('<p class="caption">%s</p>' % self.inline(text)))
            return j
        ctx = self.float_stack[-1]
        kind = ctx['kind']
        if ctx['sub'] and len(self.float_stack) > 1:
            parent = self.float_stack[-2]
            parent['subcount'] += 1
            letter = alpha(parent['subcount'])
            self.label_target = ('%d%s' % (self.counters.get(kind, 0) + 1, letter), kind)
            ctx['caption'] = '(%s) %s' % (letter, self.inline(text))
        else:
            self.counters[kind] = self.counters.get(kind, 0) + 1
            number = str(self.counters[kind])
            self.label_target = (number, kind)
            ctx['caption'] = '<span class="caption-label">%s %s:</span> %s' % (
                kind, number, self.inline(text))
        ctx['caption_first'] = not ctx['content_seen']
        return j

    def c_maketitle(self, s, j, out, name):
        parts = []
        if 'title' in self.meta:
            parts.append('<h1 class="title">%s</h1>' % self.inline(self.meta['title']))
        if 'author' in self.meta:
            authors = [self.inline(chunk) for _, chunk in split_top(self.meta['author'], AND_RE)]
            parts.append('<div class="authors">%s</div>' % ''.join(
                '<span class="author">%s</span>' % a for a in authors if a))
        if self.meta.get('date', '').strip():
            parts.append('<div class="date">%s</div>' % self.inline(self.meta['date']))
        if parts:
            out.append(self.block('<header class="title-block">\n%s\n</header>' % '\n'.join(parts)))
        return skip_ws(s, j)

    def c_toc(self, s, j, out, name):
        out.append(self.block('\x04toc:\x04'))
        return skip_ws(s, j)

    def toc_html(self):
        items = ''.join(
            '<li class="toc-l%d"><a href="#%s">%s%s</a></li>\n' % (
                level, aid, '<span class="secnum">%s</span> ' % num if num else '', title)
            for level, num, title, aid in self.toc if level <= 4)
        return '<nav class="toc">\n<h2>Contents</h2>\n<ul>\n%s</ul>\n</nav>' % items

    # ------------------------------------------------------------ environments

    def environment(self, name, inner):
        base = name.rstrip('*')
        if name == 'document':
            return self.render(inner)
        if base in ('itemize', 'enumerate', 'description', 'compactitem',
                    'compactenum', 'inparaenum', 'asparaenum'):
            kind = {'compactitem': 'itemize', 'compactenum': 'enumerate',
                    'inparaenum': 'enumerate', 'asparaenum': 'enumerate'}.get(base, base)
            return self.env_list(kind, inner)
        if base in ('quote', 'quotation', 'verse'):
            return self.block('<blockquote>\n%s\n</blockquote>' % self.blocks_html(inner))
        if base in ('center', 'flushleft', 'flushright'):
            return self.block('<div class="%s">\n%s\n</div>' % (base, self.blocks_html(inner)))
        if base == 'abstract':
            return self.block('<div class="abstract">\n<h2 class="abstract-title">Abstract</h2>\n'
                              '%s\n</div>' % self.blocks_html(inner))
        if name in FLOAT_ENVS:
            return self.env_float(name, inner)
        if name in TABULAR_ENVS:
            return self.env_tabular(name, inner)
        if base == 'thebibliography':
            return self.env_bibliography(inner)
        if base == 'proof':
            note, k = read_opt(inner, 0)
            if note is not None:
                inner = inner[k:]
            head = '<em class="proof-head">%s.</em> ' % (self.inline(note) if note else 'Proof')
            body = self.paragraphs(head + self.render(inner) + ' <span class="qed">\u220e</span>')
            return self.block('<div class="proof">\n%s\n</div>' % body)
        if base in self.theorems or name in self.theorems or base in DEFAULT_THEOREMS:
            return self.env_theorem(name, inner)
        if base == 'minipage':
            k = 0
            for _ in range(3):
                _, k = read_opt(inner, k)
            width, k = read_arg(inner, k)
            css = css_length(width)
            style = ' style="width:%s"' % css if css else ''
            return self.block('<div class="minipage"%s>\n%s\n</div>' % (
                style, self.blocks_html(inner[k:])))
        if base == 'multicols':
            cols, k = read_arg(inner, 0)
            _, k = read_opt(inner, k)
            return self.block('<div style="column-count:%s">\n%s\n</div>' % (
                html.escape((cols or '2').strip()), self.blocks_html(inner[k:])))
        if base in DECLS:
            return self.wrap(*DECLS[base], self.render(inner))
        if base == 'comment':
            return ''
        if base not in ('titlepage', 'subequations', 'singlespace', 'onehalfspace',
                        'doublespace', 'spacing', 'samepage', 'adjustbox', 'landscape'):
            self.unknown_envs.add(name)
        return self.render(inner)

    def env_list(self, kind, inner):
        opt, k = read_opt(inner, 0)
        if opt is not None:
            inner = inner[k:]
        if kind == 'enumerate':
            self.enum_depth += 1
        depth = self.enum_depth
        items, count = [], 0
        for m, chunk in split_top(inner, ITEM_RE):
            if m is None:
                continue
            label, k = read_opt(chunk, 0)
            if label is not None:
                chunk = chunk[k:]
            if kind == 'enumerate':
                count += 1
                self.label_target = (enum_label(depth, count), 'item')
            label_html = self.inline(label) if label is not None else None
            body = unwrap_p(self.blocks_html(chunk))
            if kind == 'description':
                items.append('<dt>%s</dt>\n<dd>%s</dd>' % (label_html or '', body))
            elif label_html is not None:
                items.append('<li class="custom-label"><span class="item-label">%s</span> %s</li>'
                             % (label_html, body))
            else:
                items.append('<li>%s</li>' % body)
        if kind == 'enumerate':
            self.enum_depth -= 1
            ol_type = '1aiA'[(depth - 1) % 4]
            return self.block('<ol type="%s">\n%s\n</ol>' % (ol_type, '\n'.join(items)))
        if kind == 'description':
            return self.block('<dl>\n%s\n</dl>' % '\n'.join(items))
        return self.block('<ul>\n%s\n</ul>' % '\n'.join(items))

    def env_float(self, name, inner):
        base = name.rstrip('*')
        k = 0
        if base in ('wrapfigure', 'wraptable'):
            _, k = read_opt(inner, k)
            _, k = read_arg(inner, k)
            _, k = read_opt(inner, k)
            _, k = read_arg(inner, k)
        elif base in ('subfigure', 'subtable'):
            _, k = read_opt(inner, k)
            width, k = read_arg(inner, k)
        else:
            _, k = read_opt(inner, k)
        kind = 'Table' if 'table' in base else 'Figure'
        sub = base in ('subfigure', 'subtable')
        ctx = {'kind': kind, 'caption': None, 'sub': sub, 'subcount': 0,
               'content_seen': False, 'caption_first': False}
        self.float_stack.append(ctx)
        body = self.blocks_html(inner[k:])
        self.float_stack.pop()
        if self.float_stack:
            self.float_stack[-1]['content_seen'] = True
        cap = '<figcaption>%s</figcaption>' % ctx['caption'] if ctx['caption'] else ''
        parts = [cap, body] if ctx['caption_first'] else [body, cap]
        style = ''
        if sub:
            css = css_length(width)
            style = ' style="width:%s"' % css if css else ''
        cls = 'subfigure' if sub else kind.lower()
        return self.block('<figure class="%s"%s>\n%s\n</figure>' % (
            cls, style, '\n'.join(p for p in parts if p)))

    def env_tabular(self, name, inner):
        k = 0
        if name in ('tabular*', 'tabularx', 'tabulary'):
            _, k = read_arg(inner, k)
        _, k = read_opt(inner, k)
        spec, k = read_arg(inner, k)
        aligns = parse_colspec(spec or '')
        longtable = name.startswith('longtable')
        if longtable:
            ctx = {'kind': 'Table', 'caption': None, 'sub': False, 'subcount': 0,
                   'content_seen': False, 'caption_first': True}
            self.float_stack.append(ctx)
        rows, occupied = [], {}
        rule, header_end, saw_mid = False, None, False
        for _, chunk in split_top(inner[k:], ROW_RE):
            while (m := RULE_RE.match(chunk)):
                if 'midrule' in m.group() and not saw_mid:
                    saw_mid, header_end = True, len(rows)
                rule = True
                chunk = chunk[m.end():]
            if not chunk.strip():
                continue
            cells = self.table_row(chunk, aligns, occupied)
            if all(not c[1].strip() for c in cells) and len(cells) <= 1:
                continue   # e.g. a longtable \caption row
            rows.append((rule, cells))
            rule = False
        bottom_rule = rule
        if self.float_stack:
            self.float_stack[-1]['content_seen'] = True

        lines = ['<table>']
        for idx, (rule_above, cells) in enumerate(rows):
            classes = []
            if rule_above:
                classes.append('rule-above')
            if bottom_rule and idx == len(rows) - 1:
                classes.append('rule-below')
            tag = 'th' if header_end is not None and idx < header_end else 'td'
            lines.append('<tr%s>%s</tr>' % (
                ' class="%s"' % ' '.join(classes) if classes else '',
                ''.join('<%s%s>%s</%s>' % (tag, attrs, h, tag) for attrs, h in cells)))
        lines.append('</table>')
        table = '<div class="table-wrap">\n%s\n</div>' % '\n'.join(lines)
        if longtable:
            self.float_stack.pop()
            if ctx['caption']:
                table = '<figure class="table">\n<figcaption>%s</figcaption>\n%s\n</figure>' % (
                    ctx['caption'], table)
        return self.block(table)

    def table_row(self, chunk, aligns, occupied):
        cells, col = [], 0
        for _, cell in split_top(chunk, AMP_RE):
            if occupied.get(col, 0) > 0:   # covered by a \multirow above
                occupied[col] -= 1
                col += 1
                continue
            t = cell.strip()
            span, rowspan = 1, 1
            align = aligns[col] if col < len(aligns) else 'left'
            m = re.match(r'\\multicolumn(?![A-Za-z])', t)
            if m:
                n, p = read_arg(t, m.end())
                sp, p = read_arg(t, p)
                body, p = read_arg(t, p)
                span = int(n) if n and n.strip().isdigit() else 1
                a = parse_colspec(sp or '')
                align = a[0] if a else 'center'
                t = (body or '') + t[p:]
            m = re.match(r'\s*\\multirow(?![A-Za-z])', t)
            if m:
                n, p = read_arg(t, m.end())
                _, p = read_opt(t, p)
                _, p = read_arg(t, p)
                _, p = read_opt(t, p)
                body, p = read_arg(t, p)
                rowspan = int(n) if n and n.strip().isdigit() else 1
                t = (body or '') + t[p:]
                for c in range(col, col + span):
                    occupied[c] = rowspan - 1
            attrs = ''
            if span > 1:
                attrs += ' colspan="%d"' % span
            if rowspan > 1:
                attrs += ' rowspan="%d"' % rowspan
            if align != 'left':
                attrs += ' style="text-align:%s"' % align
            cells.append((attrs, self.flatten(self.render(t), '<br>')))
            col += span
        return cells

    def env_bibliography(self, inner):
        _, k = read_arg(inner, 0)
        items, n = [], 0
        for m, chunk in split_top(inner[k:], BIBITEM_RE):
            if m is None:
                continue
            label, p = read_opt(chunk, 0)
            key, p = read_arg(chunk, p)
            key = (key or '').strip()
            n += 1
            label_html = self.inline(label) if label else str(n)
            self.bib[key] = label_html
            items.append('<li id="%s"><span class="bib-label">[%s]</span> %s</li>' % (
                anchor('bib-', key), label_html, unwrap_p(self.blocks_html(chunk[p:]))))
        heading = 'Bibliography' if self.has_chapters else 'References'
        return self.block('<section class="bibliography">\n<h2>%s</h2>\n<ul>\n%s\n</ul>\n</section>'
                          % (heading, '\n'.join(items)))

    def env_theorem(self, name, inner):
        base = name.rstrip('*')
        spec = self.theorems.get(name) or self.theorems.get(base)
        starred = name.endswith('*') and name not in self.theorems
        if spec is None:
            spec = {'title': DEFAULT_THEOREMS[base], 'counter': base, 'numbered': True,
                    'within': None, 'style': 'plain' if base in PLAIN_THEOREMS else 'definition'}
        note, k = read_opt(inner, 0)
        if note is not None:
            inner = inner[k:]
        number = ''
        title_html = self.inline(spec['title'])
        if spec['numbered'] and not starred:
            cname = spec['counter']
            within = self.theorems.get(cname, spec).get('within')
            prefix = self.section_number(SECTION_LEVELS[within]) if within in SECTION_LEVELS else ''
            if self.counter_prefix.get(cname) != prefix:
                self.counter_prefix[cname] = prefix
                self.counters['thm:' + cname] = 0
            self.counters['thm:' + cname] = self.counters.get('thm:' + cname, 0) + 1
            count = self.counters['thm:' + cname]
            number = '%s.%d' % (prefix, count) if prefix else str(count)
            self.label_target = (number, strip_tags(title_html))
        head = '<span class="thm-head">%s%s</span>' % (title_html, ' ' + number if number else '')
        if note:
            head += ' <span class="thm-note">(%s)</span>' % self.inline(note)
        head += '<span class="thm-head">.</span> '
        style = 'plain' if spec.get('style', 'plain') == 'plain' else 'upright'
        body = self.paragraphs(head + self.render(inner))
        return self.block('<div class="theorem thm-%s thm-%s">\n%s\n</div>' % (
            re.sub(r'[^A-Za-z0-9-]', '', base), style, body))


# --------------------------------------------------------------------------
# Markdown output: the HTML produced above is re-written as GitHub-flavored
# Markdown (math as $...$ / $$...$$, footnotes as [^n], GFM tables).

VOID_TAGS = {'br', 'img', 'hr', 'meta', 'link', 'input', 'wbr'}
MD_BLOCK_TAGS = {'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'dl',
                 'blockquote', 'pre', 'figure', 'figcaption', 'table', 'div',
                 'header', 'nav', 'section', 'hr'}
MD_ESCAPE_RE = re.compile(r'([\\`*_\[\]<$])')


class Node:
    def __init__(self, tag, attrs=(), parent=None):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []
        self.parent = parent

    def classes(self):
        return (self.attrs.get('class') or '').split()

    def elements(self, *tags):
        return [c for c in self.children if isinstance(c, Node) and c.tag in tags]

    def text(self):
        return ''.join(c if isinstance(c, str) else c.text() for c in self.children)


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.cur = Node('root')

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.cur)
        self.cur.children.append(node)
        if tag not in VOID_TAGS:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        node = self.cur
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.cur = node.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def md_escape(t, table=False):
    t = MD_ESCAPE_RE.sub(r'\\\1', t)
    return t.replace('|', '\\|') if table else t


def md_wrap(mark, inner):
    """Wrap inline text in emphasis markers, keeping outer spaces outside."""
    core = inner.strip()
    if not core:
        return inner
    lead = inner[:len(inner) - len(inner.lstrip())]
    trail = inner[len(inner.rstrip()):]
    return lead + mark + core + mark + trail


def md_indent(marker, body):
    """Prefix the first line with marker and indent the rest to match."""
    pad = ' ' * len(marker)
    lines = body.split('\n')
    return marker + lines[0] + ''.join('\n' + (pad + l if l else '') for l in lines[1:])


class MarkdownWriter:
    def convert(self, h):
        tb = TreeBuilder()
        tb.feed(h)
        tb.close()
        return self.tidy(self.flow(tb.root.children)) + '\n'

    @staticmethod
    def tidy(md):
        """Strip trailing spaces and squeeze blank lines, leaving code fences alone."""
        out, blank, fence = [], 0, None
        for line in md.split('\n'):
            m = re.match(r'(`{3,})', line)
            if fence:
                out.append(line)
                if m and m.group(1) == fence:
                    fence = None
                continue
            if m:
                fence = m.group(1)
            line = line.rstrip()
            blank = blank + 1 if not line else 0
            if blank <= 1:
                out.append(line)
        return '\n'.join(out).strip('\n')

    # ---- block level

    def flow(self, nodes):
        """Render a mix of inline and block nodes as Markdown blocks."""
        blocks, buf = [], []

        def flush():
            text = ''.join(buf)
            buf.clear()
            if text.strip():
                blocks.append(self.para(text))
        prev_list = False
        for n in nodes:
            if isinstance(n, Node) and n.tag in MD_BLOCK_TAGS:
                flush()
                b = self.block(n)
                if b and b.strip():
                    is_list = n.tag in ('ul', 'ol', 'dl')
                    if is_list and prev_list and blocks:
                        blocks.append('<!-- -->')   # stop the two lists merging
                    blocks.append(b)
                    prev_list = is_list
                continue
            if isinstance(n, str) and not n.strip():
                buf.append(' ')
                continue
            prev_list = False
            buf.append(self.inline(n))
        flush()
        return '\n\n'.join(blocks)

    @staticmethod
    def para(text):
        lines = [l.strip() for l in text.strip().split('\n')]
        text = re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).replace('****', '')
        # keep a paragraph from being read as a heading, quote or list
        text = re.sub(r'^([#>+-])(?=\s|$)', r'\\\1', text)
        return re.sub(r'^(\d+)([.)])(?=\s)', r'\1\\\2', text)

    def block(self, n):
        tag, cls = n.tag, n.classes()
        if tag == 'p':
            return self.para(self.inline_children(n))
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            text = ' '.join(self.inline_children(n).split()).replace('****', '')
            if 'abstract-title' in cls:
                return '**%s**' % text
            anchor = '<a id="%s"></a>' % n.attrs['id'] if n.attrs.get('id') else ''
            return '#' * int(tag[1]) + ' ' + anchor + text
        if tag == 'hr':
            return '---'
        if tag == 'pre':
            code = (n.elements('code') or [n])[0]
            lang = next((c[9:] for c in code.classes() if c.startswith('language-')), '')
            body = code.text()
            fence = '```'
            while fence in body:
                fence += '`'
            return '%s%s\n%s\n%s' % (fence, lang, body, fence)
        if tag == 'blockquote':
            inner = self.flow(n.children)
            return '\n'.join('> ' + l if l else '>' for l in inner.split('\n'))
        if tag in ('ul', 'ol'):
            return self.md_list(n)
        if tag == 'dl':
            items, term = [], ''
            for c in n.elements('dt', 'dd'):
                if c.tag == 'dt':
                    term = ' '.join(self.inline_children(c).split())
                else:
                    body = self.flow(c.children)
                    items.append(md_indent('- ', ('**%s** ' % term if term else '') + body))
                    term = ''
            return '\n'.join(items)
        if tag == 'table':
            return self.md_table(n)
        if tag == 'nav' and 'toc' in cls:
            lis = [li for ul in n.elements('ul') for li in ul.elements('li')]
            levels = [int(re.sub(r'\D', '', next((c for c in li.classes()
                                                  if c.startswith('toc-l')), '2')) or 2)
                      for li in lis]
            base = min(levels, default=0)
            lines = ['  ' * (lvl - base) + '- ' + ' '.join(self.inline_children(li).split())
                     for lvl, li in zip(levels, lis)]
            return '## Contents\n\n' + '\n'.join(lines)
        if tag == 'section' and 'footnotes' in cls:
            notes = []
            for ol in n.elements('ol'):
                for li in ol.elements('li'):
                    kids = [c for c in li.children if not (
                        isinstance(c, Node) and 'footnote-back' in c.classes())]
                    num = li.attrs.get('id', 'fn')[2:]
                    notes.append(md_indent('[^%s]: ' % num, self.flow(kids)).replace(
                        '\n' + ' ' * (len(num) + 5), '\n    '))
            return '\n'.join(notes)
        if tag == 'div' and 'authors' in cls:
            return ' · '.join(
                ' '.join(self.inline_children(a).replace('<br>', ', ').split()).replace(' ,', ',')
                for a in n.elements('span'))
        if tag == 'figcaption':
            return self.para(self.inline_children(n))
        return self.flow(n.children)

    def md_list(self, n):
        ordered = n.tag == 'ol'
        items = []
        for k, li in enumerate(n.elements('li'), 1):
            body = self.flow(li.children)
            if li.attrs.get('id'):
                body = '<a id="%s"></a>' % li.attrs['id'] + body
            items.append(md_indent('%d. ' % k if ordered else '- ', body))
        loose = any('\n\n' in it for it in items)
        return ('\n\n' if loose else '\n').join(items)

    def md_table(self, n):
        rows = []

        def collect(node):
            for c in node.children:
                if isinstance(c, Node):
                    if c.tag == 'tr':
                        rows.append(c)
                    elif c.tag != 'table':
                        collect(c)
        collect(n)
        grid, aligns, pending = [], {}, {}
        for tr in rows:
            row, col = [], 0
            cells = tr.elements('td', 'th')
            ci = 0
            while ci < len(cells) or pending.get(col, 0) > 0:
                if pending.get(col, 0) > 0:   # covered by a rowspan from above
                    pending[col] -= 1
                    row.append('')
                    col += 1
                    continue
                cell = cells[ci]
                ci += 1
                span = int(cell.attrs.get('colspan') or 1)
                rowspan = int(cell.attrs.get('rowspan') or 1)
                m = re.search(r'text-align:\s*(\w+)', cell.attrs.get('style') or '')
                if span == 1:
                    aligns.setdefault(col, m.group(1) if m else 'left')
                text = ' '.join(self.inline_children(cell, table=True).split())
                row.extend([text] + [''] * (span - 1))
                for c in range(col, col + span):
                    if rowspan > 1:
                        pending[c] = rowspan - 1
                col += span
            grid.append(row)
        if not grid:
            return ''
        ncols = max(len(r) for r in grid)
        grid = [r + [''] * (ncols - len(r)) for r in grid]
        sep = {'left': ':---', 'center': ':---:', 'right': '---:'}
        lines = ['| ' + ' | '.join(grid[0]) + ' |',
                 '| ' + ' | '.join(sep.get(aligns.get(c, 'left'), '---')
                                   for c in range(ncols)) + ' |']
        lines += ['| ' + ' | '.join(r) + ' |' for r in grid[1:]]
        return '\n'.join(lines)

    # ---- inline level

    def inline_children(self, n, table=False):
        return ''.join(self.inline(c, table) for c in n.children)

    def inline(self, n, table=False):
        if isinstance(n, str):
            return md_escape(re.sub(r'\s+', ' ', n), table)
        tag, cls = n.tag, n.classes()
        if tag == 'span' and 'math' in cls:
            return self.math(n.text(), table)
        if tag == 'span' and 'label-anchor' in cls:
            return '<a id="%s"></a>' % n.attrs.get('id', '')
        if tag == 'br':
            return '<br>'
        if tag == 'img':
            return '![%s](%s)' % (md_escape(n.attrs.get('alt', '')),
                                  self.url(n.attrs.get('src', '')))
        if tag == 'code':
            body = n.text()
            ticks = '`'
            while ticks in body:
                ticks += '`'
            pad = ' ' if body.startswith('`') or body.endswith('`') else ''
            return ticks + pad + body + pad + ticks
        if tag == 'sup' and 'footnote-ref' in cls:
            return '[^%s]' % n.text().strip()
        inner = self.inline_children(n, table)
        if tag in ('strong', 'b') or (tag == 'span' and {'caption-label', 'thm-head'} & set(cls)):
            return md_wrap('**', inner)
        if tag in ('em', 'i'):
            return md_wrap('*', inner)
        if tag == 's':
            return md_wrap('~~', inner)
        if tag in ('u', 'mark', 'sup', 'sub'):
            return '<%s>%s</%s>' % (tag, inner, tag)
        if tag == 'a':
            href = n.attrs.get('href')
            if not href:
                return inner
            if 'url' in cls:
                return '<%s>' % href
            return '[%s](%s)' % (inner, self.url(href))
        return inner

    @staticmethod
    def url(href):
        return '<%s>' % href if re.search(r'[\s()<>]', href) else href

    @staticmethod
    def math(tex, table):
        tex = tex.strip()
        if tex.startswith('\\(') and tex.endswith('\\)'):
            body = tex[2:-2].strip()
            return '$%s$' % (body.replace('|', '\\|') if table else body)
        body = tex[2:-2].strip() if tex.startswith('\\[') and tex.endswith('\\]') else tex
        if table:
            return '$%s$' % ' '.join(body.split()).replace('|', '\\|')
        return '\n\n$$\n%s\n$$\n\n' % body


# --------------------------------------------------------------------------
# Output page.

CSS = """
:root {
  --fg: #1d1f23; --bg: #fdfcf9; --muted: #5f6670; --rule: #d6d3cc;
  --link: #1a5fb4; --code-bg: #f1efea; --box: #f6f4ef;
}
@media (prefers-color-scheme: dark) {
  :root {
    --fg: #e4e2dd; --bg: #17181b; --muted: #a0a6ae; --rule: #3b3e44;
    --link: #79b0ff; --code-bg: #24262b; --box: #1e2024;
  }
}
html { background: var(--bg); color: var(--fg); }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font-family: "Latin Modern Roman", "CMU Serif", Charter, "Iowan Old Style",
               Georgia, "Times New Roman", serif;
  font-size: 1.125rem; line-height: 1.6;
  -webkit-text-size-adjust: 100%;
}
main { max-width: 46rem; margin: 0 auto; padding: 2.5rem 1rem 4rem; }
h1, h2, h3, h4, h5, h6 { line-height: 1.25; margin: 2em 0 0.6em; }
h1 { font-size: 2rem; } h2 { font-size: 1.5rem; } h3 { font-size: 1.25rem; }
h4, h5, h6 { font-size: 1.05rem; }
.secnum { margin-right: 0.4em; }
.title-block { text-align: center; margin: 1rem 0 2.5rem; }
.title-block h1 { margin: 0 0 0.75rem; }
.authors { display: flex; flex-wrap: wrap; justify-content: center; gap: 0.5rem 2.5rem; }
.date { margin-top: 0.5rem; color: var(--muted); }
p { margin: 0 0 1em; }
a { color: var(--link); }
code, pre { font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: 0.88em; }
code { background: var(--code-bg); padding: 0.1em 0.3em; border-radius: 3px; }
pre { background: var(--code-bg); padding: 0.8em 1em; overflow-x: auto; border-radius: 4px; line-height: 1.45; }
pre code { background: none; padding: 0; font-size: 1em; }
blockquote { margin: 1em 0; padding: 0 1.5em; color: var(--muted); }
.center { text-align: center; } .flushright { text-align: right; }
.abstract { margin: 0 auto 2rem; max-width: 38rem; font-size: 0.95em; }
.abstract-title { font-size: 1rem; text-align: center; margin: 0 0 0.5em; }
.math.display { display: block; overflow-x: auto; overflow-y: hidden; margin: 0.8em 0; text-align: center; }
figure { margin: 1.5em 0; text-align: center; }
figure img { max-width: 100%; height: auto; }
figcaption { font-size: 0.92em; margin: 0.5em 0; }
.caption-label { font-weight: bold; }
.subfigure { display: inline-block; vertical-align: top; margin: 0.5em; }
.minipage { display: inline-block; vertical-align: top; max-width: 100%; }
.table-wrap { overflow-x: auto; margin: 1em 0; }
table { border-collapse: collapse; margin: 0 auto; }
th, td { padding: 0.3em 0.75em; vertical-align: top; text-align: left; }
th { font-weight: bold; }
tr.rule-above > * { border-top: 1px solid var(--fg); }
tr.rule-below > * { border-bottom: 1px solid var(--fg); }
.theorem, .proof { margin: 1.2em 0; }
.thm-head { font-weight: bold; }
.thm-plain { font-style: italic; }
.thm-plain .thm-head, .thm-plain .thm-note { font-style: normal; }
.proof-head { font-style: italic; }
.qed { float: right; }
.proof::after { content: ""; display: block; clear: both; }
li.custom-label { list-style: none; }
.item-label { display: inline-block; min-width: 1.2em; margin-left: -1.6em; margin-right: 0.4em; text-align: right; }
dt { font-weight: bold; } dd { margin: 0 0 0.5em 1.5em; }
.smallcaps { font-variant: small-caps; }
.sans { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
.fbox { border: 1px solid currentColor; padding: 0 0.25em; }
.colorbox { padding: 0 0.25em; }
.size-tiny { font-size: 0.5em; } .size-scriptsize { font-size: 0.7em; }
.size-footnotesize { font-size: 0.8em; } .size-small { font-size: 0.9em; }
.size-large { font-size: 1.2em; } .size-large2 { font-size: 1.44em; }
.size-large3 { font-size: 1.73em; } .size-huge { font-size: 2.07em; } .size-huge2 { font-size: 2.49em; }
.toc { margin: 1.5em 0 2em; }
.toc ul { list-style: none; padding: 0; }
.toc li { margin: 0.2em 0; }
.toc-l1 { font-weight: bold; } .toc-l3 { margin-left: 1.5em !important; }
.toc-l4 { margin-left: 3em !important; }
.bibliography ul { list-style: none; padding: 0; }
.bibliography li { margin-bottom: 0.6em; padding-left: 2.5em; text-indent: -2.5em; }
.cite.missing { color: var(--muted); }
.footnotes { margin-top: 3em; border-top: 1px solid var(--rule); font-size: 0.9em; }
.footnote-back { text-decoration: none; }
hr { border: 0; border-top: 1px solid var(--rule); margin: 2em 0; }
img { max-width: 100%; }
"""

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%%TITLE%%</title>
<script>
window.MathJax = {
  tex: {
    inlineMath: [['\\(', '\\)']],
    displayMath: [['\\[', '\\]']],
    processEscapes: false,
    processEnvironments: true,
    tags: 'ams'
  },
  options: { ignoreHtmlClass: 'tex2html-ignore', processHtmlClass: 'math' }
};
</script>
<script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
<style>%%CSS%%</style>
</head>
<body class="tex2html-ignore">
<main>
%%BODY%%
</main>
</body>
</html>
"""


def main(argv):
    if len(argv) != 3:
        print('usage: %s <input.tex> <output.html>' % os.path.basename(argv[0]), file=sys.stderr)
        return 2
    src_path, out_path = argv[1], argv[2]
    try:
        with open(src_path, encoding='utf-8', errors='replace') as f:
            src = f.read()
    except OSError as e:
        print('tex2html: cannot read %s: %s' % (src_path, e.strerror), file=sys.stderr)
        return 1
    out_dir = os.path.dirname(os.path.abspath(out_path))
    conv = Converter(os.path.dirname(os.path.abspath(src_path)), out_dir)
    markdown = os.path.splitext(out_path)[1].lower() in ('.md', '.markdown')
    result = conv.convert(src, markdown)
    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(result)
    except OSError as e:
        print('tex2html: cannot write %s: %s' % (out_path, e.strerror), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
