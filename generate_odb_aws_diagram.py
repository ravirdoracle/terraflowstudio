#!/usr/bin/env python3
"""
Generate ODB@AWS ExaCS architecture diagram in draw.io XML format.

Usage:
    python generate_odb_aws_diagram.py [output_file.drawio]

Default output: odb_aws_architecture.drawio
Open the file in https://app.diagrams.net or the draw.io desktop app.

Architecture covered:
    - AWS Cloud / Region boundary
    - ODB Network (Oracle-managed, with Client & Backup subnets)
    - Exadata Infrastructure (X11M)
    - ExaCS VM Cluster
    - OCI DB Resources (DB Home · CDB · PDB) via oracle/oci provider
    - Customer VPC with application servers
    - ODB Network Peering Connection
    - Oracle backbone link to OCI
"""

import sys
import xml.etree.ElementTree as ET
from xml.dom.minidom import parseString


# ─── Shape / style constants ─────────────────────────────────────────────────

S_AWS_CLOUD = (
    "points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],"
    "[1,1],[0.75,1],[0.5,1],[0.25,1],[0,1],[0,0.75],[0,0.5],[0,0.25]];"
    "shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_aws_cloud_alt;"
    "strokeColor=#232F3E;fillColor=#FFFFFF;"
    "verticalLabelPosition=top;verticalAlign=bottom;align=center;"
    "html=1;fontSize=14;fontStyle=1;"
)

S_VPC = (
    "points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],"
    "[1,1],[0.75,1],[0.5,1],[0.25,1],[0,1],[0,0.75],[0,0.5],[0,0.25]];"
    "shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_vpc;"
    "strokeColor=#8C4FFF;fillColor=#F4EDFF;"
    "verticalLabelPosition=top;verticalAlign=bottom;align=center;"
    "html=1;fontSize=12;fontStyle=1;"
)

S_PRIVATE_SUBNET = (
    "points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],"
    "[1,1],[0.75,1],[0.5,1],[0.25,1],[0,1],[0,0.75],[0,0.5],[0,0.25]];"
    "shape=mxgraph.aws4.group;grIcon=mxgraph.aws4.group_private_subnet;"
    "strokeColor=#147EBA;fillColor=#E6F2F8;"
    "verticalLabelPosition=top;verticalAlign=bottom;align=center;"
    "html=1;fontSize=11;"
)

S_ODB_NET = (
    "rounded=1;arcSize=3;whiteSpace=wrap;html=1;"
    "strokeColor=#C7131F;strokeWidth=2;fillColor=#FFF5F5;"
    "verticalLabelPosition=top;verticalAlign=bottom;align=center;"
    "fontSize=13;fontStyle=1;fontColor=#C7131F;"
)

S_EXA_CONTAINER = (
    "rounded=1;arcSize=3;whiteSpace=wrap;html=1;"
    "strokeColor=#FF8000;strokeWidth=2;fillColor=#FFF8F0;"
    "verticalLabelPosition=top;verticalAlign=bottom;align=center;"
    "fontSize=12;fontStyle=1;fontColor=#804000;"
)

S_VMC_CONTAINER = (
    "rounded=1;arcSize=3;whiteSpace=wrap;html=1;"
    "strokeColor=#C7131F;strokeWidth=2;fillColor=#FFF0F0;"
    "verticalLabelPosition=top;verticalAlign=bottom;align=center;"
    "fontSize=12;fontStyle=1;fontColor=#C7131F;"
)

S_OCI_CONTAINER = (
    "rounded=1;arcSize=3;whiteSpace=wrap;html=1;dashed=1;dashPattern=8 4;"
    "strokeColor=#F80000;strokeWidth=2;fillColor=#FFFAF0;"
    "verticalLabelPosition=top;verticalAlign=bottom;align=center;"
    "fontSize=12;fontStyle=1;fontColor=#F80000;"
)

S_INFO_BOX = (
    "rounded=1;arcSize=5;whiteSpace=wrap;html=1;"
    "strokeColor=#aaaaaa;strokeWidth=1;fillColor=#f9f9f9;"
    "fontSize=10;align=left;verticalAlign=top;"
)

# AWS resource icon styles
S_EC2 = (
    "outlineConnect=0;fontColor=#232F3E;"
    "gradientColor=#F54749;gradientDirection=north;"
    "fillColor=#BF0816;strokeColor=none;dashed=0;"
    "verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;"
    "shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.ec2;"
)
S_RDS = (
    "outlineConnect=0;fontColor=#232F3E;"
    "gradientColor=#4AB29A;gradientDirection=north;"
    "fillColor=#01A88D;strokeColor=none;dashed=0;"
    "verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;"
    "shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.rds;"
)
S_ORACLE_ICON = (
    "outlineConnect=0;fontColor=#232F3E;gradientColor=none;"
    "fillColor=#C7131F;strokeColor=none;dashed=0;"
    "verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;"
    "shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.database;"
)
S_PEERING_ICON = (
    "outlineConnect=0;fontColor=#232F3E;gradientColor=none;"
    "fillColor=#8C4FFF;strokeColor=none;dashed=0;"
    "verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;"
    "shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.vpc_peering_connection;"
)
S_EXA_ICON = (
    "outlineConnect=0;fontColor=#232F3E;gradientColor=none;"
    "fillColor=#FF8000;strokeColor=none;dashed=0;"
    "verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;"
    "shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.ec2_instance;"
)
S_CLUSTER_ICON = (
    "outlineConnect=0;fontColor=#232F3E;gradientColor=none;"
    "fillColor=#C7131F;strokeColor=none;dashed=0;"
    "verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;"
    "shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.ec2_instances;"
)

# Edge styles
S_EDGE_INTERNAL = (
    "edgeStyle=orthogonalEdgeStyle;html=1;"
    "strokeWidth=1.5;strokeColor=#666666;"
    "endArrow=open;endFill=0;"
)
S_EDGE_PEERING = (
    "edgeStyle=orthogonalEdgeStyle;html=1;"
    "dashed=1;dashPattern=8 4;strokeWidth=2.5;strokeColor=#8C4FFF;"
    "endArrow=open;startArrow=open;endFill=0;startFill=0;"
)
S_EDGE_BACKBONE = (
    "edgeStyle=orthogonalEdgeStyle;html=1;"
    "dashed=1;dashPattern=4 4;strokeWidth=2;strokeColor=#C7131F;"
    "endArrow=open;endFill=0;"
)
S_EDGE_SUBNET = (
    "edgeStyle=orthogonalEdgeStyle;html=1;"
    "strokeWidth=1;strokeColor=#999999;"
    "endArrow=open;endFill=0;dashed=1;dashPattern=4 2;"
)

S_LABEL = (
    "text;html=1;strokeColor=none;fillColor=none;"
    "align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;"
)


# ─── XML builder helpers ──────────────────────────────────────────────────────

def _geo(parent_el, x, y, w, h, relative=False):
    g = ET.SubElement(parent_el, "mxGeometry")
    if relative:
        g.set("relative", "1")
    else:
        g.set("x", str(x)); g.set("y", str(y))
        g.set("width", str(w)); g.set("height", str(h))
    g.set("as", "geometry")
    return g


def shape(r, cid, value, style, x, y, w, h, parent="1"):
    c = ET.SubElement(r, "mxCell")
    c.set("id", cid)
    c.set("value", value)
    c.set("style", style)
    c.set("vertex", "1")
    c.set("parent", parent)
    _geo(c, x, y, w, h)
    return c


def edge(r, cid, value, style, src, tgt, parent="1"):
    c = ET.SubElement(r, "mxCell")
    c.set("id", cid)
    c.set("value", value)
    c.set("style", style)
    c.set("edge", "1")
    c.set("source", src)
    c.set("target", tgt)
    c.set("parent", parent)
    _geo(c, 0, 0, 0, 0, relative=True)
    return c


def label(r, cid, value, x, y, w, h, extra_style="", parent="1"):
    s = S_LABEL + extra_style
    shape(r, cid, value, s, x, y, w, h, parent)


# ─── Diagram builder ─────────────────────────────────────────────────────────

def build_diagram():
    model = ET.Element("mxGraphModel")
    model.set("dx", "1422"); model.set("dy", "762")
    model.set("grid", "1"); model.set("gridSize", "10")
    model.set("guides", "1"); model.set("tooltips", "1")
    model.set("connect", "1"); model.set("arrows", "1")
    model.set("fold", "1"); model.set("page", "1")
    model.set("pageScale", "1")
    model.set("pageWidth", "1654")
    model.set("pageHeight", "1169")
    model.set("math", "0"); model.set("shadow", "0")

    r = ET.SubElement(model, "root")
    ET.SubElement(r, "mxCell", {"id": "0"})
    ET.SubElement(r, "mxCell", {"id": "1", "parent": "0"})

    # ── AWS Cloud boundary ────────────────────────────────────────────────────
    shape(r, "aws_cloud",
          "AWS Cloud — us-east-1  (ODB@AWS)",
          S_AWS_CLOUD,
          x=10, y=10, w=1620, h=1140)

    label(r, "diagram_title",
          "<b>Oracle AI Database@AWS — ExaCS Architecture</b>",
          x=400, y=18, w=850, h=28,
          extra_style="fontSize=15;fontStyle=1;align=center;")

    # ─────────────────────────────────────────────────────────────────────────
    # ODB Network  (left column, Oracle-managed)
    # ─────────────────────────────────────────────────────────────────────────
    shape(r, "odb_net",
          "ODB Network  (Oracle-Managed)",
          S_ODB_NET,
          x=30, y=65, w=840, h=1060)

    # Terraform resource label
    label(r, "odb_net_tf",
          "<i>aws_odb_network</i>",
          x=30, y=1120, w=840, h=20,
          extra_style="fontSize=9;fontColor=#C7131F;fontStyle=2;")

    # Client Subnet ───────────────────────────────────────────────────────────
    shape(r, "client_sub",
          "Client Subnet",
          S_PRIVATE_SUBNET,
          x=50, y=150, w=380, h=160)

    label(r, "client_sub_body",
          "CIDR: 10.0.1.0/26<br/>"
          "─────────────<br/>"
          "SCAN VIPs (×3)<br/>"
          "Node Private IPs<br/>"
          "Node VIPs",
          x=50, y=180, w=380, h=125,
          extra_style="fontSize=10;")

    # Backup Subnet ───────────────────────────────────────────────────────────
    shape(r, "backup_sub",
          "Backup Subnet",
          S_PRIVATE_SUBNET,
          x=455, y=150, w=395, h=160)

    label(r, "backup_sub_body",
          "CIDR: 10.0.1.64/27<br/>"
          "─────────────<br/>"
          "Backup traffic only<br/>"
          "RMAN backups<br/>"
          "Data Guard redo",
          x=455, y=180, w=395, h=125,
          extra_style="fontSize=10;")

    # Exadata Infrastructure ──────────────────────────────────────────────────
    shape(r, "exa_infra",
          "Exadata Infrastructure  (X11M)",
          S_EXA_CONTAINER,
          x=50, y=345, w=800, h=250)

    shape(r, "exa_icon", "Exadata", S_EXA_ICON, x=70, y=395, w=60, h=60)

    label(r, "exa_detail",
          "<b>aws_odb_cloud_exadata_infrastructure</b><br/><br/>"
          "Shape:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Exadata.X11M<br/>"
          "Compute Count:&nbsp;2 nodes<br/>"
          "Storage Count:&nbsp;&nbsp;3 cells<br/>"
          "Availability Zone: use1-az1<br/>"
          "Maint. Window:&nbsp;&nbsp;Rolling · NO_PREFERENCE",
          x=145, y=375, w=695, h=200,
          extra_style="fontSize=11;align=left;verticalAlign=top;")

    # ExaCS VM Cluster ────────────────────────────────────────────────────────
    shape(r, "vm_cluster",
          "ExaCS VM Cluster",
          S_VMC_CONTAINER,
          x=50, y=625, w=800, h=250)

    shape(r, "vmc_icon", "VM Cluster", S_CLUSTER_ICON, x=70, y=675, w=60, h=60)

    label(r, "vmc_detail",
          "<b>aws_odb_cloud_vm_cluster</b><br/><br/>"
          "CPU Core Count:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;16<br/>"
          "GI Version:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;23.0.0.0<0<br/>"
          "License Model:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;LICENSE_INCLUDED<br/>"
          "SCAN Port TCP:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;1521<br/>"
          "Local Backup:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;enabled&nbsp;&nbsp;"
          "Sparse Diskgroup: disabled",
          x=145, y=655, w=695, h=200,
          extra_style="fontSize=11;align=left;verticalAlign=top;")

    # OCI DB Resources (inside ODB Network, bottom) ───────────────────────────
    shape(r, "oci_in_odb",
          "OCI DB Resources  (oracle/oci provider)",
          S_OCI_CONTAINER,
          x=50, y=905, w=800, h=195)

    label(r, "oci_in_note",
          "Provisioned via <b>oracle/oci</b> Terraform provider over Oracle's private backbone",
          x=50, y=910, w=800, h=30,
          extra_style="fontSize=9;fontStyle=2;fontColor=#666666;")

    shape(r, "db_home", "DB Home", S_ORACLE_ICON, x=100, y=950, w=60, h=60)
    label(r, "db_home_lbl",
          "<b>oci_database_db_home</b><br/>GI: 19.0.0.0<br/>dbhome",
          x=70, y=1015, w=120, h=50, extra_style="fontSize=9;")

    shape(r, "cdb", "CDB", S_ORACLE_ICON, x=390, y=950, w=60, h=60)
    label(r, "cdb_lbl",
          "<b>oci_database_database</b><br/>MYDB · AL32UTF8<br/>MYPDB (PDB)",
          x=350, y=1015, w=140, h=50, extra_style="fontSize=9;")

    shape(r, "pdb", "PDB", S_ORACLE_ICON, x=680, y=950, w=60, h=60)
    label(r, "pdb_lbl",
          "<b>oci_database_pluggable_db</b><br/>MYPDB<br/>oracle/oci",
          x=650, y=1015, w=120, h=50, extra_style="fontSize=9;")

    edge(r, "e_dbhome_cdb", "", S_EDGE_INTERNAL, "db_home", "cdb")
    edge(r, "e_cdb_pdb",    "", S_EDGE_INTERNAL, "cdb",     "pdb")

    # Internal connections inside ODB Network
    edge(r, "e_client_exa", "", S_EDGE_SUBNET, "client_sub", "exa_infra")
    edge(r, "e_backup_exa", "", S_EDGE_SUBNET, "backup_sub", "exa_infra")
    edge(r, "e_exa_vmc",    "", S_EDGE_INTERNAL, "exa_infra", "vm_cluster")
    edge(r, "e_vmc_oci",    "", S_EDGE_INTERNAL, "vm_cluster", "oci_in_odb")

    # ─────────────────────────────────────────────────────────────────────────
    # Customer VPC  (right column, top)
    # ─────────────────────────────────────────────────────────────────────────
    shape(r, "cust_vpc",
          "Customer VPC  (10.0.0.0/16)",
          S_VPC,
          x=920, y=65, w=700, h=510)

    label(r, "vpc_tf",
          "<i>aws_vpc  ·  Customer-managed</i>",
          x=920, y=570, w=700, h=20,
          extra_style="fontSize=9;fontColor=#8C4FFF;fontStyle=2;")

    # Private Subnet inside VPC
    shape(r, "app_subnet",
          "Private Subnet  (10.0.2.0/24)",
          S_PRIVATE_SUBNET,
          x=940, y=155, w=660, h=200)

    shape(r, "app1", "App Server 1",  S_EC2, x=970,  y=195, w=60, h=60)
    shape(r, "app2", "App Server 2",  S_EC2, x=1110, y=195, w=60, h=60)
    shape(r, "app3", "DB Client App", S_RDS, x=1250, y=195, w=60, h=60)

    label(r, "app_notes",
          "Application servers connect to Oracle DB<br/>"
          "using the SCAN listener (port 1521) via peering",
          x=940, y=285, w=660, h=55,
          extra_style="fontSize=10;fontStyle=2;")

    # ODB Peering icon inside VPC
    shape(r, "peering_icon",
          "ODB Network\nPeering Connection",
          S_PEERING_ICON,
          x=1080, y=390, w=60, h=60)

    label(r, "peering_tf",
          "<i>aws_odb_network_peering_connection</i>",
          x=920, y=455, w=700, h=22,
          extra_style="fontSize=9;fontColor=#8C4FFF;fontStyle=2;")

    # Info box: peering details
    shape(r, "peer_info",
          "Peering allows EC2 instances in the Customer VPC to reach<br/>"
          "the ODB Network's SCAN IPs and node VIPs over private<br/>"
          "RFC1918 space — no internet traffic.",
          S_INFO_BOX,
          x=940, y=480, w=660, h=75)

    edge(r, "e_app_peering", "", S_EDGE_INTERNAL, "app3", "peering_icon")

    # ─────────────────────────────────────────────────────────────────────────
    # Oracle Cloud (OCI)  (right column, bottom)
    # ─────────────────────────────────────────────────────────────────────────
    shape(r, "oci_cloud",
          "Oracle Cloud Infrastructure (OCI)",
          S_OCI_CONTAINER,
          x=920, y=620, w=700, h=505)

    label(r, "oci_backbone_note",
          "Traffic between ExaCS VM Cluster and OCI DB resources<br/>"
          "flows over Oracle's <b>private managed backbone</b> — not through<br/>"
          "the AWS VPC peering connection.",
          x=930, y=630, w=680, h=70,
          extra_style="fontSize=10;")

    shape(r, "oci_dbhome", "DB Home",     S_ORACLE_ICON, x=960,  y=730, w=60, h=60)
    shape(r, "oci_cdb",    "CDB",         S_ORACLE_ICON, x=1110, y=730, w=60, h=60)
    shape(r, "oci_pdb",    "PDB",         S_ORACLE_ICON, x=1260, y=730, w=60, h=60)

    label(r, "oci_dbhome_lbl",
          "<b>DB Home</b><br/>oci_database_db_home<br/>v19.0.0.0",
          x=930, y=800, w=120, h=55, extra_style="fontSize=9;")
    label(r, "oci_cdb_lbl",
          "<b>Container DB</b><br/>oci_database_database<br/>MYDB",
          x=1080, y=800, w=120, h=55, extra_style="fontSize=9;")
    label(r, "oci_pdb_lbl",
          "<b>Pluggable DB</b><br/>oci_database_pluggable<br/>MYPDB",
          x=1230, y=800, w=120, h=55, extra_style="fontSize=9;")

    edge(r, "e_oci_dh_cdb",  "", S_EDGE_INTERNAL, "oci_dbhome", "oci_cdb")
    edge(r, "e_oci_cdb_pdb", "", S_EDGE_INTERNAL, "oci_cdb",    "oci_pdb")

    # Terraform resource legend box
    shape(r, "legend",
          "<b>Terraform Resources</b><br/>"
          "① aws_odb_network<br/>"
          "② aws_odb_cloud_exadata_infrastructure<br/>"
          "③ aws_odb_cloud_vm_cluster<br/>"
          "④ aws_odb_network_peering_connection<br/>"
          "⑤ oci_database_db_home  /  oci_database_database<br/>"
          "⑥ oci_database_pluggable_database",
          S_INFO_BOX,
          x=930, y=880, w=680, h=130)

    # ─────────────────────────────────────────────────────────────────────────
    # Cross-boundary connections
    # ─────────────────────────────────────────────────────────────────────────

    # ODB Peering Connection (bidirectional dashed arrow)
    edge(r, "e_peering",
         "<font color='#8C4FFF'><b>ODB Peering\n(private RFC1918)</b></font>",
         S_EDGE_PEERING,
         "odb_net", "cust_vpc")

    # Oracle backbone: VM Cluster → OCI
    edge(r, "e_backbone",
         "<font color='#C7131F'><b>Oracle managed\nbackbone</b></font>",
         S_EDGE_BACKBONE,
         "vm_cluster", "oci_cloud")

    return model


# ─── Write output ─────────────────────────────────────────────────────────────

def main():
    output_file = sys.argv[1] if len(sys.argv) > 1 else "odb_aws_architecture.drawio"

    model = build_diagram()

    # Serialize and pretty-print
    raw = ET.tostring(model, encoding="unicode")
    pretty = parseString(raw).toprettyxml(indent="  ")
    # Replace the declaration added by minidom with the one draw.io expects
    lines = pretty.splitlines()
    if lines[0].startswith("<?xml"):
        lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    content = "\n".join(lines)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"✓  Diagram written to:  {output_file}")
    print(f"   Open in draw.io:     https://app.diagrams.net")
    print(f"   Or File > Open in the draw.io desktop app")


if __name__ == "__main__":
    main()
