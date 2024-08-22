#!/usr/bin/env python
import sys, os, argparse, subprocess, tempfile, shutil, collections, time, re
from os.path import join as pj, basename, dirname, realpath
#cf https://sourceforge.net/p/mingw-w64/wiki2/Build%20a%20native%20Windows%2064-bit%20gcc%20from%20Linux%20(including%20cross-compiler)/
base_pkgs = '''
binutils=https://ftp.gnu.org/gnu/binutils/binutils-2.43.tar.xz
mingw-w64=https://downloads.sourceforge.net/project/mingw-w64/mingw-w64/mingw-w64-release/mingw-w64-v12.0.0.tar.bz2
gcc=https://ftp.gnu.org/gnu/gcc/gcc-14.2.0/gcc-14.2.0.tar.xz
'''
compiler_pkgnames = 'binutils mingw-w64 gcc'.split()
default_cross_script_name = 'cross.env'
default_cmake_toolchain_name = 'toolchain.cmake'
tcsyms = 'rgybpcweRGYBPCWE'
tcmap = {s:f'\033[38;5;{i+1}m' for i, s in enumerate(tcsyms)}
tcmap['0'] = '\033[0m'
tcpat = re.compile('`([0'+tcsyms+'])')
tcrepl = lambda m: tcmap[m[1]]
term_width = shutil.get_terminal_size()[0]
eraser = '\r' + (' ' * term_width) + '\r'
class Builder:
    a = None
    pkgs = {}
    olines = collections.deque()
    max_olines = 16
    found = []
    download = []
    cur_src = None
    cur_build = None
    cross_env = None
    dirs = []
g = Builder()
def fmt(f, *a): return tcpat.sub(tcrepl, f % a if a else f)
def fprint(f, *a): print(fmt(f+'`0', *a))
def info(f, *a): fprint(f, *a)
def warn(f, *a): fprint('`Y'+f, *a)
def err(f, *a): fprint('`R'+f, *a)
def die(f, *a, quietly=0):
    if quietly:
        err(f, *a)
        sys.exit(1)
    raise RuntimeError(fmt(f, *a))
class Package:
    def __init__(self, name, url):
        self.name = name
        self.url = url
        self.src = None
    @staticmethod
    def from_desc(d):
        t = d.split('=', 1)
        if len(t) != 2:
            raise ValueError('Invalid package description: %r (expecting NAME=URL)', d)
        return Package(t[0], t[1])
def parse_pkgdesc(d):
    lines = d if isinstance(d, list) else d.splitlines()
    return {p.name:p for p in (
        Package.from_desc(l) for l in lines
        if l and l[0] not in ' #'
    )}
def midsnip(s, w, sep='...'):
    return s if len(s) < w else s[:w//2] + sep + s[-w//2+len(sep):]
def exists(p):
    return os.path.exists(p)
def setup_pkgs():
    d = parse_pkgdesc(base_pkgs)
    selected = []
    for p in g.a.pkgs:
        if '=' in p:
            s = p
        elif exists(p):
            s = open(p).read()
        else:
            selected.append(p)
            continue
        s = open(p).read() if exists(p) else p
        d.update(parse_pkgdesc(s))
    ds = {}
    for p in selected:
        if e := d.get(p):
            ds[p] = e
        else:
            die('No such package: %r', p)
    g.pkgs = ds or d
def fsecs(t):
    m, s = divmod(int(t), 60)
    h, m = divmod(m, 60)
    return fmt('%02d:%02d:%02d', h, m, s)
class Timer:
    def __init__(self):
        self.t0 = time.monotonic()
    def read(self):
        return time.monotonic() - self.t0
    def fread(self):
        return fsecs(self.read())
def output_line(l, timer):
    if g.a.verbose_output:
        print(l)
        return
    f = timer.fread() + ' '
    q, o = g.olines, midsnip(l, term_width - 2 - len(f))
    f = fmt('`b%s`0', f)
    q.append(l)
    while len(q) > g.max_olines:
        q.popleft()
    print(eraser, f, o, sep='', end='', flush=1)
def run(*a, shell=0):
    from subprocess import Popen, PIPE, STDOUT
    if g.cross_env:
        a = [g.cross_env, *a]
    warn('Running `w%s', ' '.join(a))
    timer = Timer()
    c = Popen(a, stdout=PIPE, stderr=STDOUT, text=1, shell=shell)
    while 1:
        o = c.stdout.readline()
        if not o and c.poll() is not None:
            break
        output_line(o.strip(), timer)
    ft, r = timer.fread(), c.returncode
    if l := g.olines:
        print(eraser, end='', flush=1)
    if r:
        info('`b%s`0 Exit with return code `r%d', ft, r)
        if l:
            info('Command output before exit:')
            print('\n'.join(l))
        die('Failed to run: %s', ' '.join(a))
    info('`b%s`G Command completed successfully', ft)
def report():
    a, s = g.a, g.a.src
    info('Cross compilation host: `G%s', a.host)
    info('  Source path:     `cs`0=`w%s', s)
    info('  Build path:        `w%s', a.build)
    info('  Install sysroot:   `w%s', a.sysroot)
    if a.jobs > 1:
        info('Maximum parallel jobs (when safe): `Y%d', a.jobs)
    for k in 'CFLAGS', 'CXXFLAGS':
        if v := os.environ.get(k):
            info('  `g%-8s`0 = `w%s', k, v)
        else:
            warn('  %s not set', k)
    info('Packages to download: `Y%d', len(g.download))
    for p in g.download:
        info('  `b%-12s `P%s', p.name, p.url)
    if not a.only_download:
        info('Packages to build:    `Y%d', len(g.pkgs))
        for p in g.pkgs.values():
            abs_src = realpath(p.src)
            rel_src = abs_src.replace(s, '`c$s`w')
            info('  `b%-12s`0 -> %s', p.name, rel_src)
        if not g.download and not g.pkgs:
            die('Nothing to do', quietly=1)
    ask('`YProceed')
def find_pkgs():
    f, d, pl = [], [], list(g.pkgs.values())
    for p in pl:
        p.src = pj(g.a.src, p.name)
        (f if exists(p.src) else d).append(p)
    g.found, g.download = f, d
    if g.a.force and g.a.only_download:
        g.download = pl
def ask(what):
    if not g.a.yes and input(fmt('%s?`w [yn = y] ', what)) not in ('yes','y',''):
        die('Cancelled', quietly=1)
def mkdirp(*paths):
    for p in paths:
        os.makedirs(p, exist_ok=1)
def symlink(src, dst):
    os.symlink(src, dst)
def listdir(d):
    return os.listdir(d)
def rename(src, dst):
    os.rename(src, dst)
def rmdir(p):
    os.rmdir(p)
def chdir(d):
    os.chdir(d)
def pushd(d):
    g.dirs.append(os.getcwd())
    chdir(d)
    info('`epushd `P%s', d)
def popd():
    info('`epopd %s', g.dirs[-1])
    chdir(g.dirs.pop())
def unpack(filename):
    p = realpath(filename)
    if p.endswith('.git'):
        return p
    d = dirname(p)
    t = pj(d, 'tmp_unpack_' + next(tempfile._get_candidate_names()))
    mkdirp(t)
    pushd(t)
    info('Unpacking %s ...', p)
    run('tar', '-axvf', p)
    popd()
    l = listdir(t)
    if len(l) != 1:
        die('Expecting 1 new directory in %r not %d:\n  %s', t, len(d), '  \n'.join(l))
    o, r = pj(t, l[0]), pj(d, l[0])
    backup(r)
    rename(o, r)
    rmdir(t)
    return r
def autoreconf(p):
    if not uses_autotools(p):
        return
    pushd(p.src)
    if not exists('configure'):
        run('autoreconf', '-i')
    popd()
def backup(p):
    if not exists(p):
        return
    b = p + '.del'
    if exists(b):
        warn('Delete old backup: %s', b)
        if os.path.isfile(b):
            os.remove(b)
        else:
            shutil.rmtree(b)
    info('Rename to backup: %r -> %r', p, b)
    rename(p, b)
def download_pkgs():
    mkdirp(g.a.src)
    forced = g.a.force and g.a.only_download
    for p in g.download:
        if exists(p.src) and not forced:
            warn('Skipping download of %s because source directory exist: %s', p.name, p.src)
            continue
        u = p.url
        b = basename(u)
        o = pj(g.a.src, b)
        if u.startswith('http'):
            backup(o)
            run('wget', '--progress=bar:force', '-O', o, u)
            if not exists(o):
                die('Expected file not found: %s', o)
        elif u.startswith('git+'):
            o += '.git'
            run('git', 'clone', u[4:], o)
        else:
            die('Unrecognized URL: %r', u)
        o = unpack(o)
        if exists(p.src) and g.a.force:
            os.remove(p.src)
        symlink(o, p.src)
        autoreconf(p)
def ensure_pkg(n):
    p = g.pkgs.get(n)
    if not p:
        die('Package is missing: %s', n)
    return p
def push_build(n, src=None):
    b = pj(g.a.build, n)
    g.cur_src = src or pj(g.a.src, n)
    g.cur_build = b
    mkdirp(b)
    pushd(b)
def pop_build():
    g.cur_src, g.cur_build = None, None
    popd()
def configure(*a, unless='Makefile'):
    if unless and exists(unless) and not g.a.force:
        warn('Skipping \'configure\' because file exists: %s', unless)
        return
    c = [pj(g.cur_src, 'configure')]
    if g.cross_env:
        if not any(v.startswith('--prefix=') for v in a):
            c.append('--prefix='+g.a.sysroot)
        if not any(v.startswith('--host=') for v in a):
            c.append('--host='+g.a.host)
    run(*c, *a)
def find_any_built_o():
    for r, dl, fl in os.walk('.'):
        for f in fl:
            if f.endswith('.o'):
                return pj(r, f)
def make(*a, parallel_safe=1, unless=None, skip_on_built_o=0):
    w = 'make' + (' ' if a else '') + ' '.join(a)
    if skip_on_built_o and not g.a.force:
        if f := find_any_built_o():
            warn('Skipping %r because of existing built .o file: %s', w, f)
            return
    if unless and exists(unless) and not g.a.force:
        warn('Skipping %r because file exists: %s', w, unless)
        return
    c = ['make']
    if g.a.jobs > 1 and parallel_safe and 'install' not in a:
        c.append(f'-j{g.a.jobs}')
    run(*c, *a)
def build_binutils(h, i):
    push_build('binutils')
    configure('--prefix='+i, '--target='+h, '--disable-multilib')
    make(unless='ld/ld-new')
    make('install', unless=i+'/bin/'+h+'-objdump')
    pop_build()
def add_to_env_path(p):
    k = 'PATH'
    v = os.environ[k]
    if p in v:
        info('Already in %s: %s', k, p)
        return
    os.environ[k] = p + ':' + v
    warn('Set PATH=%s', os.environ[k])
def build_mingw_headers(h, i):
    n = 'mingw-w64-headers'
    p = ensure_pkg('mingw-w64')
    push_build(n, src=pj(p.src, n))
    configure(f'--prefix={i}/{h}', '--host='+h)
    make('install', unless=f'{i}/{h}/include/scardssp_i.c')
    pop_build()
def get_mark_path(n):
    return pj(g.cur_build, 'setupmingw.' + n + '.progress')
def have_mark(n):
    p = get_mark_path(n)
    return p if exists(p) and not g.a.force else None
def mark_done(n):
    p = get_mark_path(n)
    with open(p, 'w') as f:
        f.write('done\n')
def build_gcc_stage1(h, i):
    m = 'stage1'
    push_build('gcc')
    if p := have_mark(m):
        warn('Skipping gcc %s because mark exists: %s', m, p)
    else:
        configure('--prefix='+i, '--target='+h, '--disable-multilib', '--enable-languages=c,c++')
        make('all-gcc')
        make('install-gcc', parallel_safe=0)
        mark_done(m)
    pop_build()
def build_mingw(h, i):
    push_build('mingw-w64')
    configure(f'--prefix={i}/{h}', '--host='+h)
    make(parallel_safe=0, unless='mingw-w64-crt/lib32/libsynchronization.a')
    make('install', unless=f'{i}/{h}/lib/libmingwthrd.a')
    pop_build()
def build_gcc_stage2(h, i):
    m = 'stage2'
    push_build('gcc')
    if p := have_mark(m):
        warn('Skipping gcc %s because mark exists: %s', m, p)
    else:
        make()
        make('install')
        mark_done(m)
    pop_build()
def allow_execution(p):
    os.chmod(p, 0o755)
def write_env_script(h, i):
    s = f'''#!/bin/sh
h={h}
i={i}
export HOST=$h
export SYSROOT=$i
export CC=$h-gcc
export CXX=$h-g++
export CPP=$h-cpp
export RANLIB=$h-ranlib
export AR=$h-ar
export STRIP=$h-strip
export PKG_CONFIG_PATH="$i/lib/pkgconfig"
export PKG_CONFIG_LIBDIR="$i/lib/pkgconfig"
echo "$PATH" | grep -sqF "$i/bin" || export PATH="$i/bin:$PATH"
[ -z "$1" ] || exec "$@"
'''
    o = pj(i, default_cross_script_name)
    with open(o, 'w') as f:
        f.write(s)
    info('Wrote env script: %s', o)
    allow_execution(o)
def write_cmake_toolchain(h, i):
    o = pj(i, default_cmake_toolchain_name)
    s = fmt('''# cmake -DCMAKE_TOOLCHAIN_FILE=%s ...
set(setupmingw_host "%s")
set(setupmingw_sysroot "%s")
set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR i686)
set(CMAKE_C_COMPILER ${setupmingw_sysroot}/bin/${setupmingw_host}-gcc)
set(CMAKE_RC_COMPILER ${setupmingw_sysroot}/bin/${setupmingw_host}-windres)
set(CMAKE_CXX_COMPILER ${setupmingw_sysroot}/bin/${setupmingw_host}-g++)
set(CMAKE_FIND_ROOT_PATH "${setupmingw_sysroot}")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_INSTALL_PREFIX "${CMAKE_FIND_ROOT_PATH}" CACHE STRING "Install path prefix, prepended onto install directories." FORCE)
set(ENV{PKG_CONFIG_LIBDIR} "${CMAKE_INSTALL_PREFIX}/lib/pkgconfig")
''', o, h, i)
    with open(o, 'w') as f:
        f.write(s)
    info('Wrote cmake toolchain: %s', o)
def build_compiler():
    for n in compiler_pkgnames:
        if n not in g.pkgs:
            return
    h, i = g.a.host, g.a.sysroot
    mkdirp(g.a.build, i)
    build_binutils(h, i)
    add_to_env_path(pj(i, 'bin'))
    build_mingw_headers(h, i)
    build_gcc_stage1(h, i)
    build_mingw(h, i)
    build_gcc_stage2(h, i)
    write_env_script(h, i)
    write_cmake_toolchain(h, i)
def copytree(a, b):
    info('Copying %r to %r', a, b)
    shutil.copytree(a, b, dirs_exist_ok=1)
def uses_autotools(p):
    l = 'configure configure.ac configure.in'.split()
    return any(exists(pj(p.src, f)) for f in l)
def build_with_autotools(p, h, i, *x):
    configure('--enable-static', *x)
    make()
    make('install')
def build_zlib(p, h, i):
    if not exists('zlib.h'):
        copytree(realpath(p.src), realpath('.'))
    run('./configure', '--prefix='+i, '--static')
    x = [f'DESTDIR={i}/', f'PREFIX={h}-', 'prefix='+i]
    x += 'SHARED_MODE=1 INCLUDE_PATH=include BINARY_PATH=bin LIBRARY_PATH=lib'.split()
    make('-f', 'win32/Makefile.gcc', 'install', *x, unless=i+'/lib/libz.a')
def build_libxml2(p, h, i):
    configure('--enable-static', '--disable-silent-rules', '--with-iconv='+i, '--without-catalog', '--without-python', '--without-icu')
    make(unless='libxml2_la-xmlschemas.o')
    make('install', unless=i+'/lib/libxml2.a')
def build_libpng(p, h, i):
    x = [f'CC={h}-gcc', f'STRIP={h}-strip', f'CPPFLAGS=-I{i}/include', f'LDFLAGS=-L{i}/lib']
    configure('--enable-static', *x)
    make(unless='libpng.sym')
    make('install', unless=i+'/lib/libpng.a')
def uses_cmake(p):
    return exists(pj(p.src, 'CMakeLists.txt'))
def cmake(*a):
    i = g.a.sysroot
    tc = pj(i, default_cmake_toolchain_name)
    o = [f'-DCMAKE_TOOLCHAIN_FILE={tc}', '-DCMAKE_BUILD_TYPE=Release', f'-DCMAKE_INSTALL_PREFIX={i}', '-DCMAKE_VERBOSE_MAKEFILE=ON', '-Wno-dev']
    run('cmake', '-GUnix Makefiles', '-B.', f'-S{g.cur_src}', *o, *a)
def build_with_cmake(p, h, i, *x):
    cmake(*x)
    make()
    make('install')
def build_openal(p, h, i):
    x = '-DLIBTYPE=STATIC -DALSOFT_EXAMPLES=OFF -DALSOFT_INSTALL_EXAMPLES=OFF -DALSOFT_UTILS=OFF'.split()
    build_with_cmake(p, h, i, *x)
def build_sdl_image(p, h, i):
    build_with_autotools(p, h, i, 'CPPFLAGS=-I{i}/include -Wno-incompatible-pointer-types')
def build_libs():
    h, i = g.a.host, g.a.sysroot
    g.cross_env = pj(i, default_cross_script_name)
    for n, p in g.pkgs.items():
        if n in compiler_pkgnames:
            continue
        if not exists(p.src):
            die('Sources not found: %s', p.src)
        push_build(p.name)
        if f := globals().get('build_' + n):
            f(p, h, i)
        elif uses_autotools(p):
            build_with_autotools(p, h, i)
        elif uses_cmake(p):
            build_with_cmake(p, h, i)
        else:
            die('Unrecognized build system: %s', p.src)
        pop_build()
        g.olines.clear()
def get_args():
    p = argparse.ArgumentParser(description='download and build mingw-w64 cross compiler and libs')
    A = p.add_argument
    A('-a', '--arch', metavar='ARCH', default='i686', help='i686 for 32-bit, else x86_64')
    A('-b', '--build', metavar='PATH', help='configure and compile here')
    A('-c', '--colors', metavar='y|n|a', default='a', help='use term colors in messages')
    A('-d', '--only-download', action='store_true', help='just download and unpack sources')
    A('-f', '--force', action='store_true', help='never skip any build steps (or downloads with -d)')
    A('-i', '--sysroot', metavar='PATH', help='install everything here')
    A('-j', '--jobs', metavar='N', type=int, default=1, help='value of N for "make -jN ..."')
    A('-s', '--src', metavar='PATH', default='./src', help='download and unpack source packages here')
    A('-v', '--verbose-output', action='store_true', help='do not abbreviate command output')
    A('-y', '--yes', action='store_true', help='assume yes instead of asking')
    A('pkgs', metavar='NAME|NAME=URL|PKGLIST_FILE', nargs='*', help='package selection')
    a = p.parse_args()
    a.host = a.arch + '-w64-mingw32'
    a.build = realpath(a.build or './build.' + a.host)
    a.sysroot = realpath(a.sysroot or './sys.' + a.host)
    a.src, env = realpath(a.src), os.environ
    tc = a.colors in ('y', 'yes', '1')
    if a.colors in ('a', 'auto', 'maybe', 'm', '?'):
        tc = env.get('COLORTERM') or 'color' in env.get('TERM', '')
    if not tc:
        global tcrepl
        tcrepl = lambda m: ''
    return a
def main():
    timer = Timer()
    g.a = get_args()
    setup_pkgs()
    find_pkgs()
    report()
    download_pkgs()
    if not g.a.only_download:
        build_compiler()
        build_libs()
    info('All done in %s', timer.fread())
if __name__ == '__main__':
    main()
