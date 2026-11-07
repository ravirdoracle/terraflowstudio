"""Oracle AI Database@AWS package.

Owns everything specific to this cloud: the page route, the payload validation
rules, and the Terraform provider schema. Nothing here is imported by another
cloud package, so a change cannot reach GCP or Azure.

routes is deliberately not imported here - importing this package for its
validator should not require Flask.
"""
from .validator import validate

__all__ = ['validate']
