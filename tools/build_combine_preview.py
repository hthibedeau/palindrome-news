#!/usr/bin/env python3
"""Build preview-combined.html: the homepage with its sections combined, no repeats (Hannah, Wed Nov 4, 2026:
"do that and then I want to look at it. Be prepared to go back to this if I dont").

    python3 tools/build_design_preview.py            # rebuild preview-combined.html from index.html
    python3 tools/build_design_preview.py --adopt    # Hannah keeps it: put the layer into index.html itself
    python3 tools/build_design_preview.py --drop     # Hannah doesn't: remove the preview page (index.html was never changed)

index.html is never changed except by --adopt. The auto-update workflow runs the plain build after each pass, so the
preview carries the same news as the homepage.
"""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAGE, LAYER, OUT = ROOT / 'index.html', ROOT / 'tools' / 'combine_layer.html', ROOT / 'preview-combined.html'
MARK_A, MARK_B = '<!-- cmb:start -->', '<!-- cmb:end -->'


def with_layer(html, layer):
    html = re.sub(re.escape(MARK_A) + '.*?' + re.escape(MARK_B), '', html, flags=re.S)
    i = html.rfind('</body>')
    block = MARK_A + '\n' + layer + '\n' + MARK_B + '\n'
    return html[:i] + block + html[i:] if i >= 0 else html + block


def main():
    layer = LAYER.read_text(encoding='utf-8')
    if '--drop' in sys.argv:
        OUT.unlink(missing_ok=True)
        print('preview-combined.html removed; index.html untouched')
        return
    html = PAGE.read_text(encoding='utf-8')
    if '--adopt' in sys.argv:
        PAGE.write_text(with_layer(html, layer), encoding='utf-8')
        OUT.unlink(missing_ok=True)
        print('combine layer adopted into index.html')
        return
    out = with_layer(html, layer)
    # keep the preview out of search engines
    out = out.replace('<head>', '<head>\n<meta name="robots" content="noindex">', 1)
    if not OUT.exists() or OUT.read_text(encoding='utf-8') != out:
        OUT.write_text(out, encoding='utf-8')
        print('preview-combined.html rebuilt')
    else:
        print('preview-combined.html already current')


if __name__ == '__main__':
    main()
