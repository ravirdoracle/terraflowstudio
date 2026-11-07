"""Shared helpers used by all generator modules."""
import os
import re
from jinja2 import Environment, FileSystemLoader, StrictUndefined


def _env(template_root):
    return Environment(
        loader=FileSystemLoader(template_root),
        undefined=StrictUndefined,   # a missing variable must fail, not render ''
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def make_renderer(template_root):
    """A render_tf bound to one directory of templates.

    Each package owns its templates and gets its own loader, so a cloud can only
    render its own: reaching for another cloud's template raises TemplateNotFound
    rather than quietly working. That is the property that keeps the packages
    independent - a shared search path would let them drift into each other.
    """
    env = _env(template_root)

    def render_tf(template_path: str, **ctx) -> str:
        return env.get_template(template_path).render(**ctx).rstrip('\n')

    return render_tf


#: Legacy shared renderer, rooted at the old templates/tf tree. Kept for anything
#: not yet migrated to a package-local template directory.
render_tf = make_renderer(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates', 'tf')
)


def is_ref(s: str) -> bool:
    if not s:
        return False
    return bool(re.match(r'^[a-z_][a-z0-9_.]*(\.[a-z_][a-z0-9_.\[\]*]*)+$', s))


def parse_list(s: str) -> list:
    if not s:
        return []
    return [x.strip() for x in s.split(',') if x.strip()]


def tf_bool(v) -> str:
    return 'true' if v else 'false'


def tf_num(v):
    """Coerce a form value to a number for HCL, or None when it should be omitted.

    Number inputs arrive from the browser as strings ('', '120', '8.5'), so blank
    and unparseable values become None and the caller leaves the attribute out.
    Integral floats render as ints so '8.0' does not become 8.0 in the output."""
    if v is None or v == '':
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else f
