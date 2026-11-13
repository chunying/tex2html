#!/usr/bin/env bash
# Smoke-test a built tex2html executable: smoke-test.sh <path-to-executable>
set -euo pipefail

exe="$1"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cat > "$work/test.tex" <<'EOF'
\documentclass{article}
\title{Smoke Test}
\begin{document}
\maketitle
\section{Intro}\label{sec:intro}
Some \textbf{bold} text and math $e^{i\pi}+1=0$, see Section~\ref{sec:intro}.
\begin{equation}\label{eq:a} a^2+b^2=c^2 \end{equation}
Equation~\eqref{eq:a} and a citation \cite{k}.
\begin{thebibliography}{9}
\bibitem{k} A. Author, \emph{A Title}, 2024.
\end{thebibliography}
\end{document}
EOF

"$exe" "$work/test.tex" "$work/out.html"
"$exe" "$work/test.tex" "$work/out.md"

check() {  # check <file> <fixed string>
  grep -qF -- "$2" "$1" || { echo "FAIL: '$2' not found in $(basename "$1")"; exit 1; }
}
check "$work/out.html" '<h1 class="title">Smoke Test</h1>'
check "$work/out.html" '<strong>bold</strong>'
check "$work/out.html" 'class="math inline"'
check "$work/out.md" '**bold**'
check "$work/out.md" '[(1)](#lbl-eq:a)'
check "$work/out.md" 'bib-k'

# wrong usage must exit with status 2
status=0
"$exe" > /dev/null 2>&1 || status=$?
[ "$status" -eq 2 ] || { echo "FAIL: usage error exited with $status, expected 2"; exit 1; }

echo "smoke test passed"
