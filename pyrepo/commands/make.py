from   pathlib import Path
from   shutil  import rmtree
import sys
import click
from   ..util  import runcmd

@click.command()
@click.option('-c', '--clean', is_flag=True, default=False)
@click.option('--sdist/--no-sdist', default=True)
@click.option('--wheel/--no-wheel', default=True)
def cli(clean, sdist, wheel):
    """ Build an sdist and/or wheel for a project """
    make(clean=clean, sdist=sdist, wheel=wheel)

def make(proj_dir=None, clean=False, sdist=True, wheel=True):
    if proj_dir is None:
        proj_dir = Path()
    if clean:
        try:
            rmtree(proj_dir / 'build')
        except FileNotFoundError:
            pass
        try:
            rmtree(proj_dir / 'dist')
        except FileNotFoundError:
            pass
    if sdist or wheel:
        if (proj_dir / 'pyproject.toml').exists():
            args = []
            if sdist:
                args.append('--source')
            if wheel:
                args.append('--binary')
            runcmd(
                sys.executable, '-m', 'pep517.build',
                '-o', 'dist',
                *args,
                proj_dir,
            )
        else:
            args = []
            if sdist:
                args.append('sdist')
            if wheel:
                args.append('bdist_wheel')
            runcmd(sys.executable, 'setup.py', '-q', *args, cwd=proj_dir)
