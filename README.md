# My mini tex2html tool

Convert a LaTeX document, or a bare snippet of LaTeX, into a standalone HTML
page or a GitHub-flavored Markdown file.

`tex2html.py` is a single Python script that uses only the standard library.
It does not need a TeX installation and does not run TeX. It reads the source
itself and translates the commands it knows.

## Requirements

- Python 3.8 or newer
- To view math in the HTML output, a browser with internet access (MathJax is
  loaded from a CDN)

### Prebuilt binaries

Standalone executables that need no Python are built by GitHub Actions
(`.github/workflows/build.yml`):

| Platform                    | File                          |
| --------------------------- | ----------------------------- |
| Linux x86-64                | `tex2html-linux-x86_64`       |
| Linux ARM64 (aarch64)       | `tex2html-linux-aarch64`      |
| Windows x86-64              | `tex2html-windows-x86_64.exe` |
| Windows ARM64               | `tex2html-windows-aarch64.exe`|
| macOS Apple Silicon (arm64) | `tex2html-macos-aarch64`      |

- **Linux:** built on manylinux_2_28, so the binaries run on any distribution
  with glibc 2.28 or newer, such as Debian 10+, Ubuntu 20.04+ and
  RHEL/Rocky/Alma 8+. The ARM64 build also covers Raspberry Pi OS (64-bit) and
  ARM cloud servers like AWS Graviton.
- **Windows ARM64:** for Windows 11 on ARM devices, such as Snapdragon laptops
  and Surface Pro.
- **macOS:** needs macOS 11 (Big Sur) or newer on an Apple Silicon Mac.

The macOS and Windows binaries are not code-signed, so the system may warn
when you first run one:

- **macOS** blocks downloaded unsigned programs. Clear the download flag once
  with `xattr -d com.apple.quarantine tex2html-macos-aarch64`, or right-click
  it in Finder and choose Open.
- **Windows SmartScreen** may show "Windows protected your PC". Choose
  "More info", then "Run anyway".

Builds run only when a tag is pushed or created, or when started by hand from
the Actions tab ("Run workflow").

- Tags starting with `v` (e.g. `v1.0.0`) attach the binaries to a
  [GitHub release](https://github.com/chunying/tex2html/releases), along with
  `SHA256SUMS.txt`.
- Every other build keeps them as workflow artifacts on the Actions run page.

The binaries take the same arguments as the script:

```sh
./tex2html-linux-x86_64 paper.tex paper.html
./tex2html-macos-aarch64 paper.tex paper.html
tex2html-windows-x86_64.exe paper.tex paper.md
```

### Building a binary yourself

```sh
pip install nuitka zstandard   # Linux also needs: sudo apt install patchelf
make build                     # writes ./bin/tex2html
```

## Usage

```sh
python3 tex2html.py <input.tex> <output.html>
python3 tex2html.py <input.tex> <output.md>
```

The output format is chosen by the output file's extension:

| Extension             | Output                                              |
| --------------------- | --------------------------------------------------- |
| `.md`, `.markdown`    | GitHub-flavored Markdown                            |
| anything else         | Standalone HTML page (styled, light and dark modes) |

Examples:

```sh
python3 tex2html.py paper.tex paper.html
python3 tex2html.py paper.tex README-paper.md
```

The input can be a complete document (`\documentclass … \begin{document} …
\end{document}`) or just a fragment such as a few paragraphs with math. If the
file has no `\begin{document}`, the whole file is converted.

### Exit status and messages

| Exit code | Meaning                                         |
| --------- | ----------------------------------------------- |
| `0`       | Success                                         |
| `1`       | The input could not be read, or the output could not be written |
| `2`       | Wrong number of arguments (usage is printed)    |

Warnings go to stderr and do not stop the conversion. They cover:

- commands the converter does not know (they are dropped, but the text in
  their arguments is kept)
- unknown environments (their content is shown as plain text)
- image files that cannot be found
- `.bib` files that cannot be found
- citation keys missing from the bibliography

## What gets converted

### Document structure

- `\title`, `\author` (several authors separated by `\and`; `\thanks` becomes a
  footnote) and `\date` (including `\today`) are shown where `\maketitle`
  appears.
- The `abstract` environment.
- `\tableofcontents`, built from the document's sections.
- `\part`, `\chapter`, `\section`, `\subsection`, `\subsubsection`,
  `\paragraph` and `\subparagraph`, with LaTeX-style numbering. Starred
  versions are not numbered. `\appendix` switches to A, B, ….
- Paragraphs come from blank lines; `\par`, `\\` and `\newline` also work.
- `\input{…}`, `\include{…}` and `\subfile{…}` insert the named files, looked
  up relative to the input file.

### Text

- **Font commands:** `\textbf`, `\textit`, `\emph`, `\texttt`, `\textsc`,
  `\textsf`, `\underline`, `\sout`, `\textsuperscript`, `\textsubscript`.
- **Old-style switches:** `{\bf …}`, `{\it …}`, `{\em …}`, `{\tt …}`, as well
  as `\bfseries`, `\itshape` and similar.
- **Font sizes:** `\tiny` … `\Huge`.
- **Color:** `\textcolor`, `\color` and `\colorbox`, with named colors or
  `[HTML]{RRGGBB}`.
- **Typography:** ``` ``quotes'' ``` → “quotes”, `--` → –, `---` → —, and
  `~` → non-breaking space.
- **Accents and special characters:** `\'e` → é, `\"o` → ö, `\c{c}` → ç,
  `\H{o}` → ő, and more; `\ss`, `\o`, `\ae`, `\S`, `\copyright`, `\ldots`,
  `\LaTeX` and others; escaped characters `\% \$ \& \# \_ \{ \}`.
- **Links:** `\url`, `\href` and `\hyperref[label]{text}`.
- **Footnotes:** `\footnote`, collected at the end of the document.

### Math

All math is kept as LaTeX source:

- inline: `$…$`, `\(…\)`, `\begin{math}`, `\ensuremath`
- display: `$$…$$`, `\[…\]`, `displaymath`
- environments: `equation`, `align`, `alignat`, `gather`, `multline`,
  `flalign`, `eqnarray` (and their starred versions)

In **HTML** output, MathJax 3 draws the math in the browser and numbers
equations AMS-style. `\label`, `\ref` and `\eqref` for equations are resolved
by MathJax.

In **Markdown** output, math is written as `$…$` and `$$…$$`, which GitHub,
GitLab, Obsidian, Typora, Pandoc and others render. These viewers draw each
math block on its own and cannot resolve references between blocks, so the
converter numbers equations itself:

- each numbered row gets `\tag{n}`
- `\nonumber`, `\notag` and your own `\tag{…}` are respected
- `multline` gets a single number on its last row
- references become links such as `[(1)](#lbl-eq:main)`

### Your own commands

These definitions are read and expanded everywhere, including inside math:

- `\newcommand`, `\renewcommand` and `\providecommand`, with arguments and an
  optional first argument
- `\def`
- `\DeclareMathOperator`
- `\newenvironment` and `\renewenvironment`

Definitions that rely on LaTeX internals (names containing `@`) are skipped.

### Lists

- `itemize`, `enumerate` (nesting gives 1 → a → i → A) and `description`
- custom item labels: `\item[label]`
- `\label` on an enumerate item makes `\ref` give the item's number

### Tables

`tabular`, `tabular*`, `tabularx`, `tabulary` and `longtable` are supported:

- column alignment from the column spec (`l c r p{} m{} b{} X`, including
  `*{n}{…}`)
- merged cells: `\multicolumn` and `\multirow`
- horizontal rules: `\hline`, `\toprule`, `\midrule`, `\bottomrule`, `\cline`,
  `\cmidrule`
- rows before the first `\midrule` become the header row

In Markdown, tables become GFM pipe tables. Pipe tables cannot merge cells, so
merged cells are padded with empty ones.

### Figures and floats

- `figure`, `table`, `wrapfigure`, `subfigure`, `subtable` and `minipage`
- `\caption`, numbered as "Figure n:" / "Table n:". The caption stays above or
  below the content, as in the source.
- `\includegraphics[width=…]{file}`:
  - widths like `0.5\textwidth` become percentages; units like `cm` and `pt`
    are kept
  - a file given without an extension is looked up as `.svg`, `.png`,
    `.jpg`, `.jpeg`, `.gif` or `.webp`
  - for a `.pdf` or `.eps` image, a web image with the same name is used if
    one exists
  - image paths are rewritten relative to the output file

### Theorems and proofs

- `\newtheorem` in all its forms: shared counters (`\newtheorem{lemma}[theorem]{Lemma}`),
  per-section numbering (`\newtheorem{theorem}{Theorem}[section]`) and starred
  (unnumbered) versions
- `\theoremstyle`: the `plain` style uses an italic body, others are upright
- common names work even without `\newtheorem`: `theorem`, `lemma`,
  `proposition`, `corollary`, `definition`, `remark`, `example` and more
- optional notes: `\begin{theorem}[Pythagoras]`
- `proof`, ending with ∎

### Cross-references

`\label` works with `\ref`, `\eqref`, `\pageref`, `\autoref`, `\cref`,
`\Cref` and `\nameref`. The reference becomes a link to the section, figure,
table, theorem, list item or equation. `\autoref` and `\cref` add the kind,
e.g. "Figure 2" or "Section 1.3". References may point forward.

### Code and verbatim

- `verbatim`, `Verbatim`, `lstlisting` (with `language=`) and `minted` become
  code blocks
- `\verb|…|`, `\lstinline` and `\mintinline` become inline code
- their content is kept exactly, so `%` and `\` inside them are not
  interpreted

### Other environments

- `quote`, `quotation` and `verse` become block quotes
- `center`, `flushleft` and `flushright`
- `multicols`
- `comment` is dropped

## Citations and bibliography

Citations use one simple numeric style.

In the text, every citation command (`\cite`, `\citep`, `\citet`,
`\parencite`, `\textcite`, `\autocite`, …) prints numbers in brackets:

```
… as shown before [1, 2, 3].   … see [1, Sec. 2].
```

Optional notes work: `\cite[p.~5]{key}` and natbib's `\citep[see][p.~5]{key}`.

In the reference list, each entry is printed as:

```
[1] Author A, Author B, and Author C, Title, Venue, Year, URL
```

### Using a `.bib` file

The `.bib` file is named in either of the usual ways:

```latex
\bibliographystyle{plain}   % ignored
\bibliography{refs}         % reads refs.bib
```

```latex
\usepackage{biblatex}
\addbibresource{refs.bib}   % in the preamble
...
\printbibliography
```

Files are looked up relative to the input `.tex` file.

**Numbering:**

- entries are numbered in the order they are first cited (like `unsrt`)
- only cited entries are listed
- `\nocite{key}` adds one entry; `\nocite{*}` adds every entry in the file

**Placement:** the list goes where `\bibliography` or `\printbibliography`
appears. If neither is there but there are citations, the list is added at the
end of the document.

**How each part of an entry is chosen:**

| Part    | Source in the `.bib` entry |
| ------- | -------------------------- |
| Authors | `author`, or `editor` (marked "(ed.)") if there is no author. `Last, First` becomes `First Last`; `and others` becomes "et al." |
| Title   | `title` |
| Venue   | The first field present of `journal`, `journaltitle`, `booktitle`, `school`, `institution`, `organization`, `howpublished`, `publisher`. For an arXiv preprint with no venue: `arXiv:<id>` |
| Year    | `year`, or the year part of `date` |
| URL     | `url`, or `https://doi.org/<doi>`, or `https://arxiv.org/abs/<eprint>` |

A part that is missing from the entry is left out.

**BibTeX syntax supported:**

- values in `{…}` or `"…"`
- bare numbers
- `@string` abbreviations and month names (`jan` … `dec`)
- `#` to join values
- `@comment` and `@preamble` (skipped)
- LaTeX inside fields: accents such as `Erd{\H{o}}s`, `{\LaTeX}`, math, and
  braces that protect capitals

**Missing keys:** a key not found in any `.bib` file shows as `[key]`, and a
warning is printed.

### Using `thebibliography`

A hand-written list also works:

```latex
\begin{thebibliography}{9}
\bibitem{knuth} D.~Knuth, \emph{The \TeX book}, 1984.
\end{thebibliography}
```

Entries are numbered in the order they are listed. `\bibitem[label]{key}`
uses the given label instead of a number.

## Output details

### HTML

- one self-contained `.html` file with embedded CSS
- a serif reading layout that works on phones
- automatic dark mode
- no JavaScript other than MathJax

Only elements marked as math are processed by MathJax, so a literal `$` in the
text is never mistaken for math.

### Markdown

| LaTeX                    | Markdown                                          |
| ------------------------ | ------------------------------------------------- |
| Sections                 | `#` headings, each with an `<a id>` anchor so links work |
| Bold, italic, code       | `**bold**`, `*italic*`, `` `code` ``              |
| Strike-through           | `~~text~~`                                        |
| Underline, sup, sub      | inline HTML                                       |
| Lists                    | `-` and `1.` lists; description lists become `- **Term** text` |
| Footnotes                | `[^1]` with the notes collected at the end        |
| Code                     | fenced code blocks (with a language when known)   |
| Images                   | `![alt](path)`                                    |
| Theorems, captions       | bold labels, e.g. `**Theorem 2.1** (Name).`       |
| Special characters       | `* _ [ ] < $ \` in text are escaped               |

## Examples

The `examples/` folder holds test inputs:

| File                          | Covers                                             |
| ----------------------------- | -------------------------------------------------- |
| `sample.tex`                  | most features in one document                      |
| `fragment.tex`                | a bare snippet with no preamble                    |
| `eqs.tex`                     | equation numbering and references                  |
| `bib/paper.tex` + `refs.bib`  | BibTeX citations                                   |
| `bib/biblatex.tex`            | biblatex with `\nocite{*}`                         |

To convert one:

```sh
python3 tex2html.py examples/sample.tex examples/sample.html
python3 tex2html.py examples/bib/paper.tex examples/bib/paper.md
```

## Limitations

`tex2html` is not a TeX engine. It translates common LaTeX, so heavy macro
programming or unusual packages will not come through.

- **TikZ, PGFPlots and `picture`** are not drawn. Their environments are
  reported as unknown.
- **Unknown commands** are dropped, but their braced arguments are still shown
  as text. Check stderr for the list.
- **Bibliography style** is fixed to `[n]`:
  - author-year commands such as `\citet` and `\citeauthor` also print `[n]`
  - entries are not sorted by author
  - volume, pages and similar fields are left out
- **Images** are linked, not copied or converted. PDF and EPS images only show
  if a PNG, JPG or SVG with the same name exists.
- **Markdown images** lose their size, because Markdown has no syntax for it.
- **Markdown equation numbers** run 1, 2, 3… through the whole document;
  `\numberwithin{equation}{section}` is ignored.
- **HTML math** needs internet access, because MathJax is loaded from
  `cdn.jsdelivr.net`.
- **Equation labels written outside math** (rare) cannot be resolved.
- **`tabbing`, `\verb` inside other commands' arguments, and catcode tricks**
  are not supported.
