"""OCI Database and Data Guard generators.

Shared by the AWS, GCP and Azure packages, and deliberately independent of all
three: nothing in here imports a cloud package, renders a cloud-specific
template, or reads a cloud-prefixed payload key. The Data Guard templates were
once named aws_dg_* but contain only `oci_core_*` resources and declare only the
`oracle/oci` provider, so they were never AWS-specific.

    core  <-  oci  <-  clouds/{aws,gcp,azure}

Everything a cloud package is allowed to use is re-exported here. Importing from
oci.database or oci.dataguard directly works but is not the supported surface -
if you need something that is not listed below, add it here deliberately so the
shared contract stays visible.

The underscore-prefixed names are historical: the cloud generators reach into
OCI internals to decide whether a DB stanza is filled in and to compute module
names. Narrowing that surface is worthwhile but is a behavioural change, so it
is left for a later pass rather than folded into the extraction.
"""
from .database import (
    generate_oci_db_tf,
    _avmc_filled, _ocidb_filled, _oci_db_defaults,
    _mn_dbhome, _mn_cdb, _mn_pdb,
    oci_dbhome_main, oci_dbhome_vars, oci_dbhome_outputs, oci_dbhome_tfvars,
    oci_cdb_main, oci_cdb_vars, oci_cdb_outputs, oci_cdb_tfvars,
    oci_pdb_main, oci_pdb_vars, oci_pdb_outputs, oci_pdb_tfvars,
)
from .dataguard import generate_oci_dg_tf

__all__ = [
    'generate_oci_db_tf', 'generate_oci_dg_tf',
    '_avmc_filled', '_ocidb_filled', '_oci_db_defaults',
    '_mn_dbhome', '_mn_cdb', '_mn_pdb',
    'oci_dbhome_main', 'oci_dbhome_vars', 'oci_dbhome_outputs', 'oci_dbhome_tfvars',
    'oci_cdb_main', 'oci_cdb_vars', 'oci_cdb_outputs', 'oci_cdb_tfvars',
    'oci_pdb_main', 'oci_pdb_vars', 'oci_pdb_outputs', 'oci_pdb_tfvars',
]
