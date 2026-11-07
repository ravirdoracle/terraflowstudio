"""What app.py needs to know about each cloud, in one table.

Generation and download used to be if/elif chains repeated in several routes, so
adding a cloud meant finding every chain and remembering to extend it. They are
now lookups against this registry: one entry per cloud, and a missing entry fails
visibly rather than silently falling through to AWS.

The registry imports the cloud packages; no cloud package imports the registry.
That direction matters - it is what keeps the clouds unaware of each other.
"""
from dataclasses import dataclass
from typing import Callable, Optional

from clouds.aws.generator import generate_aws_tf
from clouds.gcp.generator import generate_gcp_tf
from clouds.azure.generator import generate_azure_tf
from oci import generate_oci_db_tf, generate_oci_dg_tf

import clouds.aws.validator as _aws_validator
import clouds.gcp.validator as _gcp_validator
import clouds.azure.validator as _azure_validator
import clouds.aws.selftest as _aws_selftest
import clouds.gcp.selftest as _gcp_selftest
import clouds.azure.selftest as _azure_selftest
import oci.selftest as _oci_selftest
import oci.validator as _dg_validator


@dataclass(frozen=True)
class CloudSpec:
    """Everything the generic routes need in order to serve one cloud."""

    name: str
    generate: Callable[[dict], dict]
    zip_name: str
    #: None where a product is validated in the browser only. Distinct from a
    #: no-op so "nothing to check here" cannot be confused with a missing entry.
    validate: Optional[Callable[[dict, dict], None]] = None
    #: Module supplying this cloud's /api/test checks - derive, check_inputs,
    #: module_keys and check_content - plus its security-review contributions.
    #: See clouds/aws/selftest.py.
    selftest: object = None

    def collect_cidrs(self, data):
        """(label, cidr) pairs this cloud's payload carries, for overlap checks."""
        return self.selftest.collect_cidrs(data)

    @property
    def security_prompt_line(self):
        """Provider-specific risk to name in the security-review prompt."""
        return getattr(self.selftest, 'SECURITY_PROMPT_LINE', '')


REGISTRY = {
    spec.name: spec for spec in (
        CloudSpec('aws',   generate_aws_tf,    'terraflow-studio-aws',
                  _aws_validator.validate,   _aws_selftest),
        CloudSpec('gcp',   generate_gcp_tf,    'terraflow-studio-gcp',
                  _gcp_validator.validate,   _gcp_selftest),
        CloudSpec('azure', generate_azure_tf,  'terraflow-studio-azure',
                  _azure_validator.validate, _azure_selftest),
        # oci is validated in the browser only. dg gained server rules with its
        # hub-and-spoke VCN pairs (oci/validator.py). The self-check of both is
        # limited to generation succeeding and the output being non-empty.
        CloudSpec('oci',   generate_oci_db_tf, 'terraflow-studio-oci',
                  None, _oci_selftest),
        CloudSpec('dg',    generate_oci_dg_tf, 'terraflow-studio-dg',
                  _dg_validator.validate, _oci_selftest),
    )
}

DEFAULT_CLOUD = 'aws'


def get(cloud):
    """Spec for `cloud`, falling back to AWS as the routes have always done."""
    return REGISTRY.get(cloud) or REGISTRY[DEFAULT_CLOUD]
