"""Self-check contribution for the OCI Database and Data Guard products.

These are configured and validated entirely in the browser, so there is nothing
to assert about the inputs. The generic checks in the route still apply -
generation succeeds and no generated file is empty - and this supplies the empty
hooks that let the route stay uniform rather than special-casing them.
"""

PAYLOAD_KEYS = {}


def derive(payload):
    return {'raw_nets': [], 'raw_infras': [], 'raw_peerings': [], 'raw_clusters': [],
            'nets': [], 'infras': [], 'peerings': [], 'clusters': []}


def check_inputs(d, t):
    return None


def module_keys(d):
    return []


def check_content(d, files, t):
    return None


# ── Security review ───────────────────────────────────────────────────────────

def collect_cidrs(data):
    """No CIDRs to collect: these products consume existing OCIDs rather than
    defining address space."""
    return []


SECURITY_PROMPT_LINE = ''
