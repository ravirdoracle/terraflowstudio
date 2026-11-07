"""OCI Database generators: DB Home -> CDB -> PDB.

Used by every cloud package and coupled to none of them.
"""
import os

from core.helpers import make_renderer
from core.helpers import tf_bool

# This package renders only its own templates. Reaching for another cloud's
# raises TemplateNotFound rather than quietly working.
render_tf = make_renderer(os.path.join(os.path.dirname(__file__), 'templates'))


def _mn_dbhome(base): return f'{base}_dbhome'
def _mn_cdb(base):    return f'{base}_cdb'
def _mn_pdb(base):    return f'{base}_pdb'


def _avmc_filled(d):
    return bool(d.get('display_name', '').strip())


def _ocidb_filled(d):
    dn  = d.get('db_home_display_name', '').strip()
    db  = d.get('db_name', '').strip()
    vcr = d.get('vmcluster_ref', '').strip()
    return vcr or dn not in ('', 'dbhome') or db not in ('', 'MYDB')


def _oci_db_defaults(d, first_cluster_name=''):
    return {**d,
        'module_name':          d.get('module_name') or 'oci_database',
        'vmcluster_ref':        d.get('vmcluster_ref') or first_cluster_name,
        'db_home_display_name': d.get('db_home_display_name') or 'dbhome',
        'db_version':           d.get('db_version') or '19.0.0.0',
        'db_name':              d.get('db_name') or 'MYDB',
        'character_set':        d.get('character_set') or 'AL32UTF8',
        'ncharacter_set':       d.get('ncharacter_set') or 'AL16UTF16',
        'pdb_name':             d.get('pdb_name') or '',
        'db_unique_name':       d.get('db_unique_name') or '',
        'sid_prefix':           d.get('sid_prefix') or '',
        'create_pdb':           bool(d.get('create_pdb', True)),
        'auto_backup_enabled':  bool(d.get('auto_backup_enabled', False)),
        'auto_backup_window':   d.get('auto_backup_window') or 'SLOT_TWO',
        'recovery_window_in_days': int(d.get('recovery_window_in_days') or 7),
    }


def oci_dbhome_main(mn, d, vmcluster_ref=''):
    return render_tf('oci_db_home/main.tf.j2', module_name=mn, vmcluster_ref=vmcluster_ref,
        display_name=d.get('db_home_display_name', 'dbhome'),
        db_version=d.get('db_version', '19.0.0.0'))


def oci_dbhome_vars(mn, d, vmcluster_ref=''):
    return render_tf('oci_db_home/variables.tf.j2', module_name=mn, vmcluster_ref=vmcluster_ref,
        display_name=d.get('db_home_display_name', 'dbhome'),
        db_version=d.get('db_version', '19.0.0.0'))


def oci_dbhome_outputs(mn):
    return render_tf('oci_db_home/outputs.tf.j2', module_name=mn)


def oci_dbhome_tfvars(mn, d, vmcluster_ref=''):
    return render_tf('oci_db_home/terraform.tfvars.j2', module_name=mn, vmcluster_ref=vmcluster_ref,
        display_name=d.get('db_home_display_name', 'dbhome'),
        db_version=d.get('db_version', '19.0.0.0'))


def _cdb_ctx(mn, d, dbhome_ref=''):
    ab = bool(d.get('auto_backup_enabled', False))
    return dict(module_name=mn, dbhome_ref=dbhome_ref,
        db_name=d.get('db_name', 'MYDB'),
        character_set=d.get('character_set', 'AL32UTF8'),
        ncharacter_set=d.get('ncharacter_set', 'AL16UTF16'),
        pdb_name=d.get('pdb_name', ''),
        db_unique_name=d.get('db_unique_name', ''),
        sid_prefix=d.get('sid_prefix', ''),
        auto_backup_enabled=tf_bool(ab),
        auto_backup_window=d.get('auto_backup_window', 'SLOT_TWO'),
        recovery_window_in_days=int(d.get('recovery_window_in_days') or 7))


def oci_cdb_main(mn, d, dbhome_ref=''):
    return render_tf('oci_cdb/main.tf.j2', **_cdb_ctx(mn, d, dbhome_ref))


def oci_cdb_vars(mn, d, dbhome_ref=''):
    return render_tf('oci_cdb/variables.tf.j2', **_cdb_ctx(mn, d, dbhome_ref))


def oci_cdb_outputs(mn):
    return render_tf('oci_cdb/outputs.tf.j2', module_name=mn)


def oci_cdb_tfvars(mn, d, dbhome_ref=''):
    return render_tf('oci_cdb/terraform.tfvars.j2', **_cdb_ctx(mn, d, dbhome_ref))


def oci_pdb_main(mn, d, cdb_ref=''):
    return render_tf('oci_pdb/main.tf.j2', module_name=mn, cdb_ref=cdb_ref,
        pdb_name=d.get('pdb_name', 'MYPDB'))


def oci_pdb_vars(mn, d, cdb_ref=''):
    return render_tf('oci_pdb/variables.tf.j2', module_name=mn, cdb_ref=cdb_ref,
        pdb_name=d.get('pdb_name', 'MYPDB'))


def oci_pdb_outputs(mn):
    return render_tf('oci_pdb/outputs.tf.j2', module_name=mn)


def oci_pdb_tfvars(mn, d, cdb_ref=''):
    return render_tf('oci_pdb/terraform.tfvars.j2', module_name=mn, cdb_ref=cdb_ref,
        pdb_name=d.get('pdb_name', 'MYPDB'))


# ── Standalone OCI DB generator ───────────────────────────────────────────────

def generate_oci_db_tf(data: dict) -> dict:
    """Return a files dict for standalone OCI DB Home / CDB / PDB modules.

    Canonical payload key is oci_databases. The <cloud>_oci_databases variants
    are accepted for configs saved before the keys were unified.
    """
    raw = (data.get('oci_databases')
           or data.get('aws_oci_databases')
           or data.get('gcp_oci_databases')
           or data.get('azure_oci_databases')
           or [])
    files = {}
    for db in raw:
        db = _oci_db_defaults(db)
        if not _ocidb_filled(db):
            continue
        base   = db['module_name']
        vcr    = db.get('vmcluster_ref', '')
        mn_h   = _mn_dbhome(base)
        mn_c   = _mn_cdb(base)
        mn_p   = _mn_pdb(base)
        files[f'{mn_h}/main.tf']          = oci_dbhome_main(mn_h, db, vcr)
        files[f'{mn_h}/variables.tf']     = oci_dbhome_vars(mn_h, db, vcr)
        files[f'{mn_h}/outputs.tf']       = oci_dbhome_outputs(mn_h)
        files[f'{mn_h}/terraform.tfvars'] = oci_dbhome_tfvars(mn_h, db, vcr)
        files[f'{mn_c}/main.tf']          = oci_cdb_main(mn_c, db, mn_h)
        files[f'{mn_c}/variables.tf']     = oci_cdb_vars(mn_c, db, mn_h)
        files[f'{mn_c}/outputs.tf']       = oci_cdb_outputs(mn_c)
        files[f'{mn_c}/terraform.tfvars'] = oci_cdb_tfvars(mn_c, db, mn_h)
        if db.get('create_pdb') and db.get('pdb_name'):
            files[f'{mn_p}/main.tf']          = oci_pdb_main(mn_p, db, mn_c)
            files[f'{mn_p}/variables.tf']     = oci_pdb_vars(mn_p, db, mn_c)
            files[f'{mn_p}/outputs.tf']       = oci_pdb_outputs(mn_p)
            files[f'{mn_p}/terraform.tfvars'] = oci_pdb_tfvars(mn_p, db, mn_c)
    return files
