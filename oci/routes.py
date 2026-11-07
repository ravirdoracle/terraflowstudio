"""OCI product page routes.

The Database (DB Home / CDB / PDB) and Data Guard pages. They live with the OCI
generators rather than under clouds/ because neither belongs to a hyperscaler -
both drive oracle/oci resources only.

Not imported by oci/__init__.py: using the generators should not require Flask.
"""
from flask import Blueprint

from core.pages import render_page

# template_folder puts these pages next to the routes that serve them.
bp = Blueprint('oci_pages', __name__, template_folder='pages')


@bp.route('/oci')
def db_page():
    return render_page('oci_db.html')


@bp.route('/dg')
def dg_page():
    return render_page('dg.html')
