"""Import instructions derived from the generated local module tree.

This inspects generated HCL only; it never connects to a provider or state.
Instance keys and provider import IDs deliberately remain user-supplied.
"""
import posixpath
import re
import shlex


# Keep strings, comments and heredocs opaque when counting block braces.
_TOKENS = re.compile(
    r'<<-?([A-Za-z_]\w*)[^\n]*\n.*?^\s*\1\s*$'
    r'|"(?:\\.|[^"\\])*"|\#[^\n]*|//[^\n]*|/\*.*?\*/'
    r'|[A-Za-z_][\w-]*|[^\s]', re.MULTILINE | re.DOTALL)


def _blocks(text):
    """Read top-level resource/module declarations and their direct attributes."""
    tokens = [m.group() for m in _TOKENS.finditer(text)
              if not m.group().startswith(('#', '//', '/*'))]
    depth = 0
    i = 0
    while i < len(tokens):
        kind = tokens[i]
        label_count = {'resource': 2, 'module': 1}.get(kind, 0)
        if depth == 0 and label_count and i + label_count + 1 < len(tokens):
            labels = tokens[i + 1:i + label_count + 1]
            if all(t.startswith('"') for t in labels) and tokens[i + label_count + 1] == '{':
                i += label_count + 2
                level = 1
                attrs = {}
                while i < len(tokens) and level:
                    token = tokens[i]
                    if level == 1 and i + 2 < len(tokens) and tokens[i + 1] == '=':
                        attrs[token] = tokens[i + 2]
                    level += (token == '{') - (token == '}')
                    i += 1
                yield kind, [t[1:-1] for t in labels], attrs
                continue
        depth += (kind == '{') - (kind == '}')
        i += 1


def _suffix(attrs):
    if 'for_each' in attrs:
        return '["<KEY>"]'
    if 'count' in attrs:
        return '[<INDEX>]'
    return ''


def _resources(files, directory, prefix='', ancestors=()):
    if directory in ancestors:
        return
    for path, content in sorted(files.items()):
        if not path.endswith('.tf') or posixpath.dirname(path) != directory:
            continue
        for kind, labels, attrs in _blocks(content):
            if kind == 'resource':
                yield prefix + '.'.join(labels) + _suffix(attrs), labels[0], path
            else:
                source = attrs.get('source', '').strip('"')
                if source.startswith(('./', '../')):
                    target = posixpath.normpath(posixpath.join(directory, source))
                    yield from _resources(
                        files, target, prefix + 'module.' + labels[0] + _suffix(attrs) + '.',
                        (*ancestors, directory))


def _provider_doc(resource_type):
    for prefix, provider in (('aws_', 'hashicorp/aws'), ('google_', 'hashicorp/google'),
                             ('azurerm_', 'hashicorp/azurerm'), ('azapi_', 'azure/azapi'),
                             ('oci_', 'oracle/oci')):
        if resource_type.startswith(prefix):
            name = resource_type[len(prefix):]
            return f'https://registry.terraform.io/providers/{provider}/latest/docs/resources/{name}#import'
    return 'https://developer.hashicorp.com/terraform/cli/commands/import'


def add_import_guidance(files, iac_tool='terraform'):
    """Add a reviewable guide to application output, including all state roots."""
    roots = sorted({posixpath.dirname(p) for p in files
                    if p.endswith('.tf') and 'modules' not in p.split('/')[:-1]})
    if not roots:
        return files
    cli = 'tofu' if iac_tool == 'opentofu' else 'terraform'
    lines = [
        '# Import existing resources into state', '',
        'Use this guide to adopt existing cloud resources with this generated configuration. '
        'Import records the association in state; it does not rewrite the generated configuration '
        'to match the cloud resource. The app does not perform imports.', '',
        '## Before importing', '',
        '1. Set the generated variables to match the existing resources, including names, locations, '
        'network settings and immutable properties. Configure credentials for every provider used '
        'by the root, including OCI where applicable.',
        '2. Select the intended backend and workspace. Each root listed below has separate state. '
        'Run commands from that root, never from a child module directory. If the resource is '
        'already managed in another state, coordinate a state migration instead of importing it twice.',
        f'3. Run `{cli} init`, then `{cli} workspace show` and `{cli} state list`. '
        'For an existing state, back it up with '
        f'`{cli} state pull > state-before-import.json`; store that file securely outside version '
        'control because state can contain secrets. A new empty state has nothing to back up.',
        '4. Check each resource\'s provider Import documentation for import support and the ID format '
        'for your installed provider version. IDs can be simple identifiers, full resource paths, '
        'OCIDs, or composite values. Replace `<IMPORT_ID>`; do not assume an ARN or display name works.', '',
        '## Address templates', '',
        'The commands below follow the generated module sources and include managed resources only. '
        'Data sources are read automatically and are not imported. A listed resource may not support '
        'import in your installed provider; check the linked documentation first.', '',
        'Replace every `["<KEY>"]` with an actual `for_each` key from the variables or module inputs, '
        'and every `[<INDEX>]` with an enabled `count` instance index such as `[0]`. '
        'Repeat for each existing instance. Skip empty collections, `count = 0`, and resources '
        'you intend to create. Nested modules and resources can each have their own keys. '
        'For example, a map entry named `prod` uses `["prod"]`. '
        'The single quotes around each address preserve these characters in POSIX shells.', '',
    ]
    example = None
    for root in roots:
        lines += [f'## Root: `{root or "."}`', '',
                  f'From the extracted project directory, run `cd {shlex.quote(root)}`. '
                  'Return to the project directory before switching roots.' if root else
                  'Run these commands from the extracted project directory.', '']
        resources = list(_resources(files, root))
        if not resources:
            lines += ['This root has no generated managed resources to import.', '']
        for address, resource_type, path in resources:
            example = example or address
            lines += [f'### `{address}`', '', f'Declared in `{path}`. '
                      f'[Provider import ID and support]({_provider_doc(resource_type)}).', '',
                      '```sh', f"{cli} import '{address}' '<IMPORT_ID>'", '```', '']
    lines += ['## Review after importing', '',
              'Import only objects that already exist, one object per resource address. '
              'Import dependencies first when another resource needs their outputs '
              '(for example network, infrastructure, then VM cluster).', '',
              'Run these commands in each root after its imports:', '', '```sh',
              f'{cli} state list', f'{cli} plan', '```', '',
              'Review all planned changes. For adoption only, reconcile configuration until the '
              'plan shows no unintended additions, updates, replacements or deletions. '
              'Resolve missing required inputs, write-only secrets and immutable-property '
              'differences before applying. Generated defaults may differ from the existing resource.', '']
    if example:
        lines += ['## Optional: configuration-driven import', '',
                  'As an alternative to CLI import, Terraform 1.5+ supports import blocks. '
                  'For OpenTofu, check support in your installed version. Put a block in '
                  '`imports.tf` in the matching root, using an address from that root. '
                  'Replace all placeholders first; do not run both methods for the same instance.', '',
                  '```hcl', 'import {', f'  to = {example}', '  id = "<IMPORT_ID>"', '}', '```', '',
                  f'Run `{cli} plan` and review it before `{cli} apply`. Applying an import block '
                  'can also apply other planned changes, so proceed only when the whole plan is intended.', '']
    lines += ['References: [Terraform CLI import](https://developer.hashicorp.com/terraform/cli/commands/import) '
              'and [import blocks](https://developer.hashicorp.com/terraform/language/block/import).', '']
    result = dict(files)
    result['IMPORT.md'] = '\n'.join(lines)
    return result
