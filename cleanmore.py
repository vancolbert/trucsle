#!/usr/bin/env python
import sys, os, re
def fmt(f, *a): return f % a if a else f
def info(f, *a): print(fmt(f, *a))
def die(f, *a): info(f, *a); sys.exit(1)
def main():
    a = sys.argv[1:]
    if not a:
        die('expecting input files')
    enc = 'latin1'
    pid = os.getpid()
    rs = [(re.compile(t[0]), t[1]) for t in (
        (r'\(\s+', r'('),
        (r'\s+\)', r')'),
        (r'\s+\\\s+{', r' {'),
        (r'} \\\s+else', r'} else'),
        (r'#(ifdef|ifndef|define|else|endif)[ \t]+(\S)', r'#\1 \2'),
        (r':[ \t]+', r': '),
        (r'([^ \t\n/:"])[ \t]*//[ \t/"]*', r'\1 // '),
        (r'([^ \t\n/])[ \t]*/\*', r'\1 /*'),
        (r'///+\n', r''),
        (r'\s*//[ \t]*\n', r'\n'),
        (r'(^|[^:])//[ \t]*([^/ ])', r'\1// \2'),
        (r'\n //', r'\n//'),
        (r'\n\n+', r'\n'),
    )]
    for p in a:
        if not os.path.exists(p):
            info('%s: not found', p)
            continue
        s = open(p, encoding=enc).read()
        n = s
        for r in rs:
            n = r[0].sub(r[1], n)
        nl = []
        for l in n.splitlines():
            t = l.strip()
            if t.startswith('//') and ';' in t:
                continue
            nl.append(l)
        n = '\n'.join(nl) + '\n'
        if n == s:
            info('%s: unchanged', p)
            continue
        o = fmt('%s.cleanmore.%s.tmp', p, pid)
        with open(o, 'w', encoding=enc) as f:
            f.write(n)
        os.replace(o, p)
        info('%s: modified %d bytes -> %d', p, len(s), len(n))
if __name__ == '__main__':
    main()
