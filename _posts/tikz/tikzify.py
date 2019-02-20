# This is a terribly hacky script for turning ```tikz codeblocks into svg
# images. You call it like this:
#
# tikzify.py in.md out.md
#
# and the script reads through in.md, replacing all the ```tikz codeblocks by
# references to svg images, which are then automatically generated. The syntax
# of what goes in the tikz codeblocks is ad-hoc and undocumented. You'll have to
# read this script, sorry.

import os
import os.path
import re
import shutil
import subprocess
import sys
import tempfile

LINE_HEIGHT_MM = 4
LINE_WIDTH_MM = 35
LINE_PADDING = 2
MID_DAGLE_LINE_PADDING = 5

FILE_SPEC_RE = re.compile(r"(FILE|DAGLE) \(([-0-9]+), ([-0-9]+)\)\s*([a-zA-Z0-9'?]*)")
DAGLE_LINE_RE = re.compile(r"PARENT ([0-9/]+) POS ([0-9/]+)(\s*GHOST)?\s*([a-zA-Z0-9- ><*:/]*)")


def write_one_file(out, lines, offset_mm, file_label, line_prefix):
    (x_offset, y_offset) = offset_mm
    line_no = 0
    num_lines = len(lines)

    rect_height = LINE_HEIGHT_MM * (num_lines + 1)
    rect_width = LINE_WIDTH_MM + 2 * LINE_PADDING

    print(r'\draw [rounded corners] ({}mm, {}mm) rectangle ({}mm, {}mm);'.format(x_offset, y_offset, x_offset + rect_width, y_offset - rect_height), file=out)

    if file_label:
        print(r'\node [anchor = base west, text width = {}mm] at ({}mm, {}mm) {{ \tt {} }};'.format(LINE_WIDTH_MM, x_offset + LINE_PADDING, y_offset + LINE_HEIGHT_MM / 2, file_label), file=out)

    for line in lines:
        line_no += 1
        if line_no == 1:
            print(r'\node({}{}) [anchor = base west, text width = {}mm] at ({}mm, {}mm) {{ \tt {} }};'.format(line_prefix, line_no, LINE_WIDTH_MM, x_offset + LINE_PADDING, y_offset - LINE_HEIGHT_MM, line), file=out)
        else:
            print(r'\node({}{}) [below = {}mm of {}{}.base west, anchor = base west, text width = {}mm] {{ \tt {} }};'.format(line_prefix, line_no, LINE_HEIGHT_MM, line_prefix, line_no-1, LINE_WIDTH_MM, line), file=out)

def write_one_dagle(out, lines, offset_mm, file_label, line_prefix):
    (x_offset, y_offset) = offset_mm
    num_vert_lines = 0
    max_horiz = 1

    # For proper formatting, dagles should have shorter, taller lines than files
    line_width = LINE_WIDTH_MM / 2
    line_height = LINE_HEIGHT_MM * 2

    if file_label:
        print(r'\node [anchor = base west, text width = {}mm] at ({}mm, {}mm) {{ \tt {} }};'.format(LINE_WIDTH_MM, x_offset + LINE_PADDING, y_offset + LINE_HEIGHT_MM / 2, file_label), file=out)

    line_no = 0
    parent_edges = []
    for line in lines:
        line_no += 1
        (parent_nos, pos, ghost, line_text) = re.match(DAGLE_LINE_RE, line).group(1, 2, 3, 4)
        parent_nos = [int(n) for n in parent_nos.split('/')]
        [row_no, col_no] = [int(n) for n in pos.split('/')]
        max_horiz = max(max_horiz, col_no)
        num_vert_lines = max(num_vert_lines, row_no)
        color = "black"
        if ghost is not None:
            color = "gray"

        x_pos = x_offset + (line_width + MID_DAGLE_LINE_PADDING) * (col_no - 1) + LINE_PADDING
        y_pos = y_offset - line_height * (row_no - 0.5)

        print(r'\node({}{}) [text = {}, anchor = base west] at ({}mm, {}mm) {{ \tt {} }};'.format(line_prefix, line_no, color, x_pos, y_pos, line_text), file=out)
        for p in parent_nos:
            if p != 0:
                # Defer printing of parent edges, in case the parent is a node
                # that hasn't appeared yet
                parent_edges.append(r'\draw[-Latex] ({}{}) to ({}{});'.format(line_prefix, p, line_prefix, line_no))

    for p in parent_edges:
        print(p, file=out)

    rect_height = line_height * num_vert_lines
    rect_width = max_horiz * (line_width + MID_DAGLE_LINE_PADDING) + 2 * LINE_PADDING

    print(r'\draw [rounded corners] ({}mm, {}mm) rectangle ({}mm, {}mm);'.format(x_offset, y_offset, x_offset + rect_width, y_offset - rect_height), file=out)


def write_spec_file(out, lines):
    cur_prefix = ord('a')
    cur_lines = []
    x_offset = 0
    y_offset = 0
    label = ''
    mode = None

    def flush():
        nonlocal cur_lines, cur_prefix
        if mode == 'FILE':
            write_one_file(out, cur_lines, (x_offset, y_offset), label, chr(cur_prefix))
            cur_lines.clear()
            cur_prefix += 1
        elif mode == 'DAGLE':
            write_one_dagle(out, cur_lines, (x_offset, y_offset), label, chr(cur_prefix))
            cur_lines.clear()
            cur_prefix += 1
        elif mode == 'EDGES':
            for edge in cur_lines:
                verts = edge.split()
                style = ""
                if len(verts) > 2:
                    style = ", " + verts[2]
                    verts = verts[:2]
                [u, v] = verts
                print(r'\draw[-Latex, thick, gray {}] ({}.east) to [out=0, in=180] ({}.west);'.format(style, u, v), file=out)
        elif mode == "EXTRA":
            for edge in cur_lines:
                print(edge.strip(), file=out)

    for line in lines:
        # Skip blank lines
        if len(line) == 1:
            continue

        if line.startswith('FILE') or line.startswith('EDGES') or line.startswith('EXTRA') or line.startswith('DAGLE'):
            flush()

            if line.startswith('FILE') or line.startswith('DAGLE'):
                (mode, x_offset, y_offset, label) = re.match(FILE_SPEC_RE, line).group(1, 2, 3, 4)
                x_offset = int(x_offset)
                y_offset = int(y_offset)
            elif line.startswith('EDGES'):
                mode = 'EDGES'
            else:
                mode = 'EXTRA'
        else:
            cur_lines.append(line[:-1])

    flush()

def write_all(in_lines, out_file):
    print(r"""
\documentclass{standalone}
\usepackage{tikz}
\usetikzlibrary{positioning}
\usetikzlibrary{arrows.meta}

\begin{document}
\begin{tikzpicture}
""", file=out_file)

    write_spec_file(out_file, in_lines)

    print(r'\end{tikzpicture}', file=out_file)
    print(r'\end{document}', file=out_file)

def tex_it(in_lines, out_name):
    with tempfile.TemporaryDirectory() as working_dir:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tex', delete=False) as tex_file:
            write_all(in_lines, tex_file)
            write_all(in_lines, sys.stdout)
            tex_file.flush()
            print(tex_file.name)
            subprocess.run(['pdflatex', '-interaction=nonstopmode', tex_file.name], cwd=working_dir)
            pdf_name = os.path.join(working_dir, os.path.basename(tex_file.name)[:-4] + '.pdf')
            subprocess.run(['pdf2svg', pdf_name, out_name])

def process_md(in_name, out_name):
    with open(in_name) as in_file:
        with open(out_name, 'w') as out_file:
            cur_lines = []
            in_tikz_block = False
            cur_block_num = 1
            basename = os.path.splitext(os.path.basename(in_name))[0]
            for line in in_file.readlines():
                if in_tikz_block and line.startswith('```'):
                    svg_name = '../images/{}_tikz_block_{}.svg'.format(basename, cur_block_num)
                    tex_it(cur_lines, svg_name)
                    in_tikz_block = False
                    cur_block_num += 1
                    cur_lines.clear()
                    print('![]({})'.format(svg_name), file=out_file)
                elif not in_tikz_block and line.startswith('```tikz'):
                    in_tikz_block = True
                elif in_tikz_block:
                    cur_lines.append(line)
                else:
                    out_file.write(line)


process_md(sys.argv[1], sys.argv[2])
