"""Shared plumbing for the product page routes.

Every product page is rendered the same way and must not be cached: the pages
embed generated state, so a stale copy from bfcache shows a config that no longer
matches what the server would produce.

Kept here rather than repeated in each cloud package because it is presentation
plumbing, not cloud behaviour - the thing that differs per cloud is the template
and its context, and those stay with the cloud.
"""
from flask import make_response, render_template

NO_STORE = {
    'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
    'Pragma': 'no-cache',
}


def render_page(template, **context):
    """Render a product page with caching disabled."""
    resp = make_response(render_template(template, **context))
    for header, value in NO_STORE.items():
        resp.headers[header] = value
    return resp
