"""payload -> draw.io (.drawio) XML renderer.

Turns a Terraflow Studio ``buildPayload()`` document into an editable draw.io
diagram. Every shape carries ``tf_type`` + key-field metadata (draw.io "Edit
Data" attributes) so the diagram is a *lossless-enough* carrier: the reverse
parser (.drawio -> payload) just walks these same attributes.

Design:
  * One shape per resource. Provider group -> brand colour:
      - net/peering/vnet  -> the cloud provider (aws/gcp/azure)
      - exadata infra + vm/autonomous clusters -> oci (Oracle-managed)
  * Edges resolve by ``module_name``: a resource's ``*_ref`` field points at
    the ``module_name`` of another resource.
  * ``style`` per tf_type is a plain coloured rounded-rect today; swap in real
    mxgraph AWS/OCI/GCP/Azure sprite styles later without touching anything else.

CLI:  python -m diagram.drawio             # writes diagram/examples/*.drawio
      python diagram/drawio.py in.json out.drawio
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

# ── provider brand styling ────────────────────────────────────────────────────
PROVIDER_STYLE = {
    "aws":   "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF2E6;strokeColor=#ED7100;fontColor=#7A3E00;",
    "oci":   "rounded=1;whiteSpace=wrap;html=1;fillColor=#FBE9E7;strokeColor=#C74634;fontColor=#7A1B12;",
    "gcp":   "rounded=1;whiteSpace=wrap;html=1;fillColor=#E8F0FE;strokeColor=#4285F4;fontColor=#174EA6;",
    "azure": "rounded=1;whiteSpace=wrap;html=1;fillColor=#E5F1FB;strokeColor=#0078D4;fontColor=#004578;",
}
EDGE_STYLE = ("edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;"
              "strokeColor=#8A8A8A;fontColor=#555555;fontSize=10;")

# ── resource registry ─────────────────────────────────────────────────────────
# Each spec: (payload_key, tf_type, provider, col, title, meta_fields, refs)
#   meta_fields : field names copied onto the shape as Edit-Data attributes
#                 (topology-relevant + headline specs). module_name always added.
#   refs        : list of (field, edge_label) -> edge to node whose module_name
#                 equals this resource's <field> value.
REGISTRY = {
    "aws": [
        ("aws_networks",    "aws_odb_network",             "aws",   0, "ODB Network",
            ["availability_zone_id", "client_subnet_cidr", "backup_subnet_cidr", "region"], []),
        ("aws_peerings",    "aws_odb_peering",             "aws",   1, "Network Peering",
            ["peer_network_id", "region"], [("network_ref", "peers")]),
        ("aws_infras",      "aws_exadata_infra",           "oci",   2, "Exadata Infra",
            ["shape", "compute_count", "storage_count", "availability_zone_id"], []),
        ("aws_clusters",    "aws_vm_cluster",              "oci",   3, "VM Cluster",
            ["cpu_core_count", "gi_version", "license_model"],
            [("infra_ref", "runs on"), ("network_ref", "attached to")]),
        ("aws_avmclusters", "aws_autonomous_vm_cluster",   "oci",   3, "Autonomous VM Cluster",
            ["cpu_core_count_per_node", "total_container_databases", "license_model"],
            [("infra_ref", "runs on"), ("network_ref", "attached to")]),
        ("aws_autonomous_dbs", "aws_autonomous_database", "oci", 3, "Autonomous DB (Serverless)",
            ["db_workload", "compute_count", "data_storage_size_in_tbs"],
            [("network_ref", "attached to")]),
    ],
    "gcp": [
        ("gcp_networks",  "gcp_odb_network",   "gcp", 0, "ODB Network",
            ["network", "gcp_oracle_zone", "client_cidr", "backup_cidr"], []),
        ("gcp_infras",    "gcp_exadb_infra",   "oci", 1, "Exadata Infra",
            ["shape", "compute_count", "storage_count", "gcp_oracle_zone"], []),
        ("gcp_clusters",  "gcp_exadb_vm_cluster", "oci", 2, "Exadb VM Cluster",
            ["cpu_core_count", "gi_version", "license_type"],
            [("infra_ref", "runs on"), ("network_ref", "attached to")]),
    ],
    "azure": [
        ("azure_vnets",    "azure_vnet",          "azure", 0, "VNet",
            ["vnet_name", "address_space", "subnet_name", "subnet_address_prefix"], []),
        ("azure_infras",   "azure_exadata_infra", "oci",   1, "Exadata Infra",
            ["shape", "compute_count", "storage_count", "zone"], []),
        ("azure_clusters", "azure_vm_cluster",    "oci",   2, "VM Cluster",
            ["cpu_core_count", "gi_version", "memory_size_in_gbs"],
            [("infra_ref", "runs on"), ("vnet_ref", "attached to")]),
    ],
}

# ── layout constants ──────────────────────────────────────────────────────────
NODE_W, NODE_H = 220, 90
COL_GAP, ROW_GAP = 140, 40
X0, Y0 = 40, 40


def _label(title: str, res: dict, meta_fields: list[str]) -> str:
    """HTML label: bold type, module name, then up to 3 non-empty specs."""
    name = res.get("module_name") or "(unnamed)"
    lines = [f"<b>{escape(title)}</b>", escape(str(name))]
    shown = 0
    for f in meta_fields:
        v = res.get(f)
        if v in (None, "", [], {}) or shown >= 3:
            continue
        lines.append(f'<span style="font-size:9px;color:#888">{escape(f)}: {escape(str(v))}</span>')
        shown += 1
    return "<br>".join(lines)


def _obj(node_id: str, title: str, tf_type: str, provider: str,
         res: dict, meta_fields: list[str], x: int, y: int) -> str:
    """A draw.io <object> (metadata carrier) wrapping a vertex mxCell."""
    attrs = {"tf_type": tf_type, "provider": provider,
             "module_name": str(res.get("module_name", ""))}
    for f in meta_fields:
        v = res.get(f)
        if v not in (None, "", [], {}):
            attrs[f] = v if isinstance(v, str) else json.dumps(v) if isinstance(v, (list, dict)) else str(v)
    attr_str = " ".join(f"{k}={quoteattr(str(v))}" for k, v in attrs.items())
    style = PROVIDER_STYLE[provider]
    return (
        f'        <object label={quoteattr(_label(title, res, meta_fields))} {attr_str} id={quoteattr(node_id)}>\n'
        f'          <mxCell style={quoteattr(style)} vertex="1" parent="1">\n'
        f'            <mxGeometry x="{x}" y="{y}" width="{NODE_W}" height="{NODE_H}" as="geometry"/>\n'
        f'          </mxCell>\n'
        f'        </object>\n'
    )


def _edge(edge_id: str, src: str, dst: str, label: str) -> str:
    return (
        f'        <mxCell id={quoteattr(edge_id)} value={quoteattr(label)} '
        f'style={quoteattr(EDGE_STYLE)} edge="1" parent="1" '
        f'source={quoteattr(src)} target={quoteattr(dst)}>\n'
        f'          <mxGeometry relative="1" as="geometry"/>\n'
        f'        </mxCell>\n'
    )


def payload_to_drawio(payload: dict) -> str:
    """Render a buildPayload() document to draw.io XML."""
    cloud = (payload.get("cloud") or "").lower()
    specs = REGISTRY.get(cloud)
    if not specs:
        raise ValueError(f"unsupported cloud: {cloud!r} (expected aws|gcp|azure)")

    cells: list[str] = []
    module_to_id: dict[str, str] = {}   # module_name -> node id (for edges)
    pending_refs: list[tuple[str, dict, list]] = []  # (node_id, res, refs)
    col_y: dict[int, int] = {}
    nid = 0

    for payload_key, tf_type, provider, col, title, meta_fields, refs in specs:
        for res in payload.get(payload_key) or []:
            nid += 1
            node_id = f"n{nid}"
            x = X0 + col * (NODE_W + COL_GAP)
            y = col_y.get(col, Y0)
            col_y[col] = y + NODE_H + ROW_GAP
            cells.append(_obj(node_id, title, tf_type, provider, res, meta_fields, x, y))
            mn = res.get("module_name")
            if mn:
                module_to_id[mn] = node_id
            if refs:
                pending_refs.append((node_id, res, refs))

    eid = 0
    for node_id, res, refs in pending_refs:
        for field, label in refs:
            target_mn = res.get(field)
            dst = module_to_id.get(target_mn) if target_mn else None
            if dst:
                eid += 1
                cells.append(_edge(f"e{eid}", node_id, dst, label))

    name = payload.get("customer") or f"{cloud.upper()} architecture"
    body = "".join(cells)
    return (
        '<mxfile host="app.diagrams.net">\n'
        f'  <diagram name={quoteattr(name)} id="terraflow">\n'
        '    <mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" '
        'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageWidth="1600" '
        'pageHeight="1000" math="0" shadow="0">\n'
        '      <root>\n'
        '        <mxCell id="0"/>\n'
        '        <mxCell id="1" parent="0"/>\n'
        f'{body}'
        '      </root>\n'
        '    </mxGraphModel>\n'
        '  </diagram>\n'
        '</mxfile>\n'
    )


# ── demo payloads (one topology per cloud) ────────────────────────────────────
_SAMPLES = {
    "aws": {
        "cloud": "aws", "customer": "Acme ODB@AWS",
        "aws_networks": [{"module_name": "odb_network", "availability_zone_id": "use1-az6",
                          "client_subnet_cidr": "10.0.1.0/24", "backup_subnet_cidr": "10.0.2.0/24",
                          "region": "us-east-1"}],
        "aws_peerings": [{"module_name": "odb_peering", "network_ref": "odb_network",
                          "peer_network_id": "vpc-abc123", "region": "us-east-1"}],
        "aws_infras": [{"module_name": "odb_exaInfra", "shape": "Exadata.X11M",
                        "compute_count": 2, "storage_count": 3, "availability_zone_id": "use1-az6"}],
        "aws_clusters": [{"module_name": "odb_vmcluster", "infra_ref": "odb_exaInfra",
                          "network_ref": "odb_network", "cpu_core_count": 16,
                          "gi_version": "23.0.0.0", "license_model": "LICENSE_INCLUDED"}],
        "aws_avmclusters": [{"module_name": "odb_avmcluster", "infra_ref": "odb_exaInfra",
                             "network_ref": "odb_network", "cpu_core_count_per_node": 40,
                             "total_container_databases": 2, "license_model": "LICENSE_INCLUDED"}],
    },
    "gcp": {
        "cloud": "gcp", "customer": "Acme AI DB@GCP",
        "gcp_networks": [{"module_name": "gcp_network", "network": "odb-vpc",
                          "gcp_oracle_zone": "us-east4-a-r1", "client_cidr": "10.10.1.0/24",
                          "backup_cidr": "10.10.2.0/24"}],
        "gcp_infras": [{"module_name": "gcp_infra", "shape": "Exadata.X9M",
                        "compute_count": 2, "storage_count": 3, "gcp_oracle_zone": "us-east4-a-r1"}],
        "gcp_clusters": [{"module_name": "gcp_cluster", "infra_ref": "gcp_infra",
                          "network_ref": "gcp_network", "cpu_core_count": 16,
                          "gi_version": "23.0.0.0", "license_type": "LICENSE_INCLUDED"}],
    },
    "azure": {
        "cloud": "azure", "customer": "Acme AI DB@Azure",
        "azure_vnets": [{"module_name": "azure_vnet", "vnet_name": "odb-vnet",
                         "address_space": "10.20.0.0/16", "subnet_name": "odb-subnet",
                         "subnet_address_prefix": "10.20.1.0/24"}],
        "azure_infras": [{"module_name": "azure_exainfra", "shape": "Exadata.X11M",
                          "compute_count": 2, "storage_count": 3, "zone": "1"}],
        "azure_clusters": [{"module_name": "azure_vmcluster", "infra_ref": "azure_exainfra",
                            "vnet_ref": "azure_vnet", "cpu_core_count": 4,
                            "gi_version": "19.0.0.0", "memory_size_in_gbs": 60}],
    },
}


def _main(argv: list[str]) -> int:
    if len(argv) == 3:
        payload = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        Path(argv[2]).write_text(payload_to_drawio(payload), encoding="utf-8")
        print(f"wrote {argv[2]}")
        return 0
    out_dir = Path(__file__).parent / "examples"
    out_dir.mkdir(exist_ok=True)
    for cloud, payload in _SAMPLES.items():
        dest = out_dir / f"{cloud}_example.drawio"
        dest.write_text(payload_to_drawio(payload), encoding="utf-8")
        print(f"wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv))
