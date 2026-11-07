"""Cross-cutting infrastructure shared by every cloud package.

Nothing here knows about AWS, GCP, Azure or OCI. This is the bottom of the
dependency graph:

    core            <- helpers, template rendering
      ^
    oci             <- OCI Database + Data Guard, depends on core only
      ^
    clouds/aws, clouds/gcp, clouds/azure

A change under core/ can reach anything, which is why it stays small and stable.
Cloud-specific logic belongs in that cloud's package, even at the cost of some
duplication between them.
"""
from .helpers import render_tf, is_ref, parse_list, tf_bool, tf_num

__all__ = ['render_tf', 'is_ref', 'parse_list', 'tf_bool', 'tf_num']
