# Oracle Exadata X11M Hardware Specifications

Source: Oracle Exadata X11M Datasheet (oracle.com/a/ocom/docs/engineered-systems/exadata/exadata-x11m-ds.pdf)

## Overview
Exadata X11M is the latest generation Oracle Exadata hardware. It uses AMD EPYC "Turin" processors, DDR5 6400MT/s memory, PCIe 5.0 NVMe flash, and a 200 Gb/s dual-rail RoCE RDMA fabric. It is 25% faster per core than X10M, with 33% more memory bandwidth.

Minimum system software: Oracle Exadata System Software 25.1.0.

---

## Database Server — X11M (Standard)
- **CPU:** 2 × AMD EPYC 9J25, 96 cores each = 192 physical cores; 2.6 GHz base / 4.5 GHz boost
- **Memory (DDR5 6400MT/s):** 512 GB / 1,536 GB / 2,304 GB / 3,072 GB (standard config: 1.5 TB)
- **System NVMe:** 2 × 3.84 TB (expandable to 4 × 3.84 TB)
- **RDMA Fabric:** 1 × dual-port CX7 (PCIe 5.0), 2 × 100 Gb/s active-active RoCE = 200 Gb/s
- **Client Network:** 2 × CX6-LX adapters (2 × SFP+/SFP28 each, 10/25 GbE)
- **Optional NIC:** CX6-LX (10/25 GbE), CX6-DX (100 GbE QSFP28), or Quad 10G RJ45

## Database Server — X11M-Z (Entry-Level, Single-Socket)
- **CPU:** 1 × AMD EPYC 9J15, 32 cores; 2.95 GHz / 4.4 GHz boost
- **Memory:** 768 GB or 1,152 GB DDR5
- **RDMA Fabric:** Same 200 Gb/s dual-port CX7 as standard

---

## Storage Servers

### X11M Extreme Flash (EF)
Best for OLTP / lowest latency:
- **CPU:** 2 × AMD EPYC 9J15, 32 cores each = 64 cores; 2.95 GHz
- **Memory:** 1,536 GB DDR5 — 1.25 TB allocated as XRMEM (Exadata RDMA Memory cache), 256 GB for system
- **Performance flash (Smart Flash Cache/Log):** 4 × 6.8 TB NVMe PCIe 5.0 (Flash Accelerator F680 v2) = 27.2 TB
- **Capacity flash (persistent data):** 4 × 30.72 TB NVMe = 122.88 TB
- **Total raw flash per cell:** 150.08 TB
- **System NVMe:** 2 × 480 GB
- **RDMA Fabric:** 200 Gb/s dual-port CX7

### X11M High Capacity (HC)
Best for analytics / mixed OLTP+OLAP:
- **CPU:** 2 × AMD EPYC 9J15, 64 cores total
- **Memory:** 1,536 GB DDR5 — 1.25 TB XRMEM
- **HDD:** 12 × 22 TB SAS 7,200 RPM = 264 TB raw
- **Flash cache:** 4 × 6.8 TB NVMe PCIe 5.0 = 27.2 TB (Smart Flash Cache)
- **System NVMe:** 2 × 480 GB
- **RDMA Fabric:** 200 Gb/s dual-port CX7

### X11M-Z HC (Entry-Level)
- **CPU:** 1 × AMD EPYC 9J15, 32 cores
- **Memory:** 768 GB DDR5 (576 GB for caching)
- **HDD:** 6 × 22 TB SAS
- **Flash:** 2 × 6.8 TB

---

## Storage Server Types — Terraform Relevance
When configuring `database_server_type` and `storage_server_type` in `aws_odb_cloud_exadata_infrastructure`:
- `database_server_type = "X11M"` — standard dual-socket database server
- `storage_server_type = "X11M-EF"` — Extreme Flash (low latency, all-flash)
- `storage_server_type = "X11M-HC"` — High Capacity (HDDs + flash cache, high capacity)
- `storage_server_type = "X11M"` — generic X11M storage
These fields are only configurable on X11M shape; they are fixed on X9M.

---

## RDMA Network Fabric
- **Technology:** RoCE (RDMA over Converged Ethernet), dual-rail active-active
- **Per-server bandwidth:** 200 Gb/s (2 × 100 Gb/s ports)
- **Latency:** Single-digit microseconds
- **Max cluster scale:** Up to 14 racks interlinked
- **XRMEM:** 1.25 TB per storage server, accessible via RDMA; positioned between buffer cache and Flash Cache; achieves 14 µs read latency

---

## Performance Benchmarks

### OLTP
- SQL single-block read latency: **14 µs** (21% better than X10M's 17 µs; 70× better than AWS RDS / Azure SQL at 1,000 µs)
- Serial transaction throughput: up to 25% faster than X10M
- Concurrent transaction throughput: up to 25% higher
- Max IOPS (8 KB ops): 25.2M read / 13M write per rack

### Analytics
- Flash SQL scan throughput: 100 GB/s per storage server
- XRMEM columnar scan: up to 500 GB/s per storage server
- Total rack I/O bandwidth: up to 8.5 TB/s
- Storage expansion rack: up to 9.5 TB/s
- Analytics improvement vs X10M: up to 25% faster
- vs Pure Storage FlashArray//XL: 300× higher throughput
- vs Dell PowerMax 8500: 40× higher throughput

### AI / Vector Search
- Persistent vector index (IVF) searches: up to 55% faster than X10M
- In-memory vector index (HNSW) queries: up to 43% faster
- Binary vector queries: up to 32× faster

### Memory
- DDR5 bandwidth: 33% faster than X10M

---

## Rack-Level Capacity (Full Rack X11M)
- CPU cores: up to 2,880 (DB) + 1,088 (storage) = 3,968 total
- Memory: up to 42 TB (DB servers) + 21.3 TB XRMEM (storage)
- Performance flash: up to 462.4 TB
- Capacity flash: up to 2 PB
- Disk: up to 4.4 PB

---

## Cloud Configuration Limits (ODB@AWS / OCI Exadata Service)
- **Minimum:** 2 database servers + 3 storage servers
- **Maximum (elastic):** 32 database servers + 64 storage servers
- Independently scalable — add/remove servers without downtime
- Max VM clusters per system: 8
- Max VMs per database server: 8

### Per-server cloud sizing (X11M)
- ECPUs per database server: 760
- Memory per database server: 1,390 GB
- Usable storage per storage server: ~80 TB

---

## Software Features (System Software 25.1)
- **Smart Scan:** SQL predicate pushdown and column projection at the storage layer (reduces data sent to DB servers)
- **Exadata Smart Flash Cache:** Intelligent caching of hot data on flash
- **Exadata Smart Flash Log:** Redo log acceleration on flash
- **XRMEM:** RDMA Memory as cache tier between buffer cache and flash
- **AI Vector Search offload:** IVF, HNSW, BINARY vector index queries pushed to storage
- **Exascale Free Space:** Reduced reserved space from 9% → 3% for 9+ storage servers
- **Automatic ASM Rebalance Tuning:** Dynamic `asm_power_limit` adjustment
- **Oracle RAC:** Multi-node clustering
- **Autonomous Database:** Self-managing/self-healing
- **Zero-downtime patching:** Ksplice kernel patching without reboot
- **Secure Fabric Default:** Internal RDMA isolation enabled by default

### Database version support
- Oracle AI Database 26ai (latest)
- Oracle Database 23ai
- Oracle Database 19c (minimum for Autonomous Recovery Service)

---

## Power & Energy
- Core disablement saves ~80 W per disabled core
- Intelligent power capping and low-power mode scheduling
- PCIe 5.0 flash doubles bandwidth vs PCIe 4.0 with improved efficiency

---

## Deployment Options
| Mode | Notes |
|------|-------|
| On-premises | Customer data center |
| Exadata Cloud@Customer | Oracle-managed hardware at customer site |
| OCI Exadata Database Service | Fully managed OCI cloud |
| ODB@AWS | Oracle AI Database@AWS (Exadata X11M shape = `Exadata.X11M`) |
| ODB@GCP | Oracle AI Database@GCP (Exadata X11M hardware backing) |

All deployments use identical Oracle software stack — applications are 100% portable.

---

## Licensing (Cloud)
- **License Included:** Oracle Database Enterprise Edition — Extreme Performance + all management packs
- **BYOL:** Available on X7, X8, X8M, X9M, X11M (not available on X6)
- Cloud billing: per second after 48-hour minimum; OCPU scaling billed per second (1-min minimum)

---

## Gotchas & Key Notes
- X10M is the predecessor; X11M replaces it at the same price point.
- `storage_server_type` values: `X11M-EF` (extreme flash) vs `X11M-HC` (high capacity) — choose EF for OLTP latency, HC for capacity/analytics.
- `database_server_type` and `storage_server_type` fields are only settable on X11M shape — they are ignored/fixed on X9M.
- Minimum `compute_count` = 2 (must be even); minimum `storage_count` = 3 (must be multiple of 3).
- Provisioning an Exadata infrastructure takes 15+ minutes.
- After provisioning, query DB server IDs via data source before creating VM clusters.
- `Exadata.X10M` shape is no longer listed as available in ODB@AWS — use `Exadata.X11M` for new deployments.
- `Exadata.X11MV` is an X11M-generation variant offered on ODB@AWS only. Its server types are `X11MV` and `X11MV-HC` (no EF option), and neither is mandatory — unlike `Exadata.X11M`, where AWS documents both as required.
