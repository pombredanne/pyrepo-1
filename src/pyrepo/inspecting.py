import ast
from configparser import ConfigParser
from pathlib import Path
import re
import time
from intspan import intspan
from read_version import read_version
from setuptools.config import read_configuration
import yaml
from . import util  # Import module to keep mocking easy
from .readme import Readme


def inspect_project(dirpath=None):
    """Fetch various information about an already-initialized project"""
    if dirpath is None:
        dirpath = Path()
    else:
        dirpath = Path(dirpath)

    def exists(*fname):
        return Path(dirpath, *fname).exists()

    if not exists("pyproject.toml"):
        raise InvalidProjectError("Project is missing pyproject.toml file")
    if not exists("setup.cfg"):
        raise InvalidProjectError("Project is missing setup.cfg file")
    if not exists("src"):
        raise InvalidProjectError("Project does not have src/ layout")

    cfg = read_configuration(str(dirpath / "setup.cfg"))
    env = {
        "name": cfg["metadata"]["name"],
        "short_description": cfg["metadata"]["description"],
        "author": cfg["metadata"]["author"],
        "author_email": cfg["metadata"]["author_email"],
        "python_requires": util.sort_specifier(cfg["options"]["python_requires"]),
        "install_requires": cfg["options"].get("install_requires", []),
        # Until <https://github.com/pypa/setuptools/issues/2575> is fixed, we
        # have to determine versions via read_version() instead of
        # read_configuration().
        # "version": cfg["metadata"].get("version"),
        "keywords": cfg["metadata"].get("keywords", []),
        "supports_pypy3": False,
        "default_branch": get_default_branch(dirpath),
    }

    # if env["version"] is None:
    #    raise InvalidProjectError("Cannot determine project version")

    if cfg["options"].get("packages"):
        env["is_flat_module"] = False
        env["import_name"] = cfg["options"]["packages"][0]
        env["version"] = read_version(
            (dirpath / "src" / env["import_name"] / "__init__.py").resolve()
        )
    else:
        env["is_flat_module"] = True
        env["import_name"] = cfg["options"]["py_modules"][0]
        env["version"] = read_version(
            (dirpath / "src" / (env["import_name"] + ".py")).resolve()
        )

    env["python_versions"] = []
    for clsfr in cfg["metadata"]["classifiers"]:
        m = re.fullmatch(r"Programming Language :: Python :: (\d+\.\d+)", clsfr)
        if m:
            env["python_versions"].append(m.group(1))
        if clsfr == "Programming Language :: Python :: Implementation :: PyPy":
            env["supports_pypy3"] = True

    env["commands"] = {}
    try:
        commands = cfg["options"]["entry_points"]["console_scripts"]
    except KeyError:
        pass
    else:
        for cmd in commands:
            k, v = re.split(r"\s*=\s*", cmd, maxsplit=1)
            env["commands"][k] = v

    m = re.fullmatch(
        r"https://github.com/([^/]+)/([^/]+)",
        cfg["metadata"]["url"],
    )
    assert m, "Project URL is not a GitHub URL"
    env["github_user"] = m.group(1)
    env["repo_name"] = m.group(2)

    if "Documentation" in cfg["metadata"]["project_urls"]:
        m = re.fullmatch(
            r"https?://([-a-zA-Z0-9]+)\.(?:readthedocs|rtfd)\.io",
            cfg["metadata"]["project_urls"]["Documentation"],
        )
        assert m, "Documentation URL is not a Read the Docs URL"
        env["rtfd_name"] = m.group(1)
    else:
        env["rtfd_name"] = env["name"]

    toxcfg = ConfigParser(interpolation=None)
    toxcfg.read(str(dirpath / "tox.ini"))  # No-op when tox.ini doesn't exist
    env["has_tests"] = toxcfg.has_section("testenv")

    env["has_doctests"] = False
    for pyfile in (dirpath / "src").rglob("*.py"):
        if re.search(r"^\s*>>>\s+", pyfile.read_text(), flags=re.M):
            env["has_doctests"] = True
            break

    env["has_typing"] = exists("src", env["import_name"], "py.typed")
    env["has_ci"] = exists(".github", "workflows", "test.yml")
    env["has_docs"] = exists("docs", "index.rst")

    env["codecov_user"] = env["github_user"]
    try:
        with (dirpath / "README.rst").open(encoding="utf-8") as fp:
            rdme = Readme.parse(fp)
    except FileNotFoundError:
        env["has_pypi"] = False
    else:
        for badge in rdme.badges:
            m = re.fullmatch(
                r"https://codecov\.io/gh/([^/]+)/[^/]+/branch/.+" r"/graph/badge\.svg",
                badge.href,
            )
            if m:
                env["codecov_user"] = m.group(1)
        env["has_pypi"] = any(link["label"] == "PyPI" for link in rdme.header_links)

    with (dirpath / "LICENSE").open(encoding="utf-8") as fp:
        for line in fp:
            m = re.match(r"^Copyright \(c\) (\d[-,\d\s]+\d) \w+", line)
            if m:
                env["copyright_years"] = list(intspan(m.group(1)))
                break
        else:
            raise InvalidProjectError("Copyright years not found in LICENSE")

    env["extra_testenvs"] = parse_extra_testenvs(
        dirpath / ".github" / "workflows" / "test.yml"
    )

    return env


def get_commit_years(dirpath, include_now=True):
    years = set(
        map(
            int,
            util.readcmd(
                "git", "log", "--format=%ad", "--date=format:%Y", cwd=dirpath
            ).splitlines(),
        )
    )
    if include_now:
        years.add(time.localtime().tm_year)
    return sorted(years)


def find_module(dirpath: Path):
    results = []
    if (dirpath / "src").exists():
        dirpath /= "src"
        src_layout = True
    else:
        src_layout = False
    for flat in dirpath.glob("*.py"):
        name = flat.stem
        if name.isidentifier() and name != "setup":
            results.append(
                {
                    "import_name": name,
                    "is_flat_module": True,
                    "src_layout": src_layout,
                }
            )
    for pkg in dirpath.glob("*/__init__.py"):
        name = pkg.parent.name
        if name.isidentifier():
            results.append(
                {
                    "import_name": name,
                    "is_flat_module": False,
                    "src_layout": src_layout,
                }
            )
    if len(results) > 1:
        raise InvalidProjectError("Multiple Python modules in repository")
    elif not results:
        raise InvalidProjectError("No Python modules in repository")
    else:
        return results[0]


def extract_requires(filename):
    ### TODO: Split off the destructive functionality so that this can be run
    ### idempotently/in a read-only manner
    variables = {
        "__python_requires__": None,
        "__requires__": None,
    }
    with open(filename, "rb") as fp:
        src = fp.read()
    lines = src.splitlines(keepends=True)
    dellines = []
    tree = ast.parse(src)
    for i, node in enumerate(tree.body):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in variables
        ):
            variables[node.targets[0].id] = ast.literal_eval(node.value)
            if i + 1 < len(tree.body):
                dellines.append(slice(node.lineno - 1, tree.body[i + 1].lineno - 1))
            else:
                dellines.append(slice(node.lineno - 1))
    for sl in reversed(dellines):
        del lines[sl]
    with open(filename, "wb") as fp:
        fp.writelines(lines)
    return variables


def parse_requirements(filepath):
    variables = {
        "__python_requires__": None,
        "__requires__": None,
    }
    try:
        with open(filepath, encoding="utf-8") as fp:
            for line in fp:
                m = re.fullmatch(
                    r"\s*#\s*python\s*((?:[=<>!~]=|[<>]|===)\s*\S(?:.*\S)?)\s*",
                    line,
                    flags=re.I,
                )
                if m:
                    variables["__python_requires__"] = m.group(1)
                    break
            fp.seek(0)
            variables["__requires__"] = list(util.yield_lines(fp))
    except FileNotFoundError:
        pass
    return variables


def parse_extra_testenvs(filepath: Path):
    try:
        with filepath.open(encoding="utf-8") as fp:
            workflow = yaml.safe_load(fp)
    except FileNotFoundError:
        return {}
    includes = workflow["jobs"]["test"]["strategy"]["matrix"].get("include", [])
    return {inc["toxenv"]: inc["python-version"] for inc in includes}


def get_default_branch(dirpath):
    branches = set(
        util.readcmd(
            "git", "--no-pager", "branch", "--format=%(refname:short)", cwd=dirpath
        ).splitlines()
    )
    for guess in ["main", "master"]:
        if guess in branches:
            return guess
    raise InvalidProjectError("Could not determine default Git branch")


class InvalidProjectError(Exception):
    pass
