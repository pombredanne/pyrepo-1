{% if importable %}
from setuptools import setup
setup()
{% else %}
from   os.path    import dirname, join
import re
from   setuptools import {% if not is_flat_module %}find_packages, {% endif %}setup

{% if is_flat_module %}
with open(join(dirname(__file__), {{(import_name + '.py')|repr}})) as fp:
{% else %}
with open(join(dirname(__file__), {{import_name|repr}}, '__init__.py')) as fp:
{% endif %}
    for line in fp:
        m = re.search(r'^\s*__version__\s*=\s*([\'"])([^\'"]+)\1\s*$', line)
        if m:
            version = m.group(2)
            break
    else:
        raise RuntimeError('Unable to find own __version__ string')

setup(version=version)
{% endif %}
