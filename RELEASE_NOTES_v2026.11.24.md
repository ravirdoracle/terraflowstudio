# Terraflow Studio v2026.11.24

## AWS Transit VPC

- Added an optional Transit VPC screen for Oracle AI Database@AWS. Create a transit VPC and subnet, or reuse an existing VPC/subnet, ODB peering and Transit Gateway attachment by ID.
- Connect to an existing Transit Gateway. Route management is explicit: configure ODB-facing transit routes, optional TGW routes, and optional application VPC routes according to ownership.
- Validate that reused networking, peering and attachments match the selected VPC and ODB network availability-zone ID. New attachment subnets use the ODB network's AZ ID.
- Generated Terraform/OpenTofu includes `TRANSIT_VPC.md` with routing ownership, DNS prerequisites, connectivity checks and staged peered-CIDR registration. Keep `register_peer_cidrs = false` for the initial apply; enable it only after a new attachment and peering are available. Existing peerings managed elsewhere require an explicit owner-side CIDR update.
- Omit untouched infrastructure and peering sample cards from transit-only exports. Transit configurations require AWS provider 6.68.0 or later and are not supported by CloudFormation; unsupported downloads return an actionable error.

## Region and zone catalogues

- Refreshed the editable catalogues against Oracle's regional availability tables on November 23, 2026: 22 AWS, 33 Azure and 17 Google Cloud live regions.
- Added missing AWS AZ IDs and made Northern California and Stockholm selectable as live regions.
- Corrected and completed paired OCI regions, including AWS Ohio → `us-columbus-1`, Oregon → `us-boardman-1`, and Ireland → `eu-dublin-3`.
- Corrected Google Cloud Turin to `europe-west12` and enabled its Oracle zone and Querétaro's Oracle zone. These two regions currently list Exadata Dedicated availability only; other database services can have narrower coverage.
- Preserve Azure's exact live physical-zone identifiers and store planned placements separately. Italy North's third physical zone remains planned.
- Azure logical zone candidates are not a subscription-specific availability guarantee. Picker and catalogue guidance now explain that physical zones must be mapped to logical numbers for the user's Azure subscription.
- Catalogues record their source URL and verification date. Region and zone pickers and generated OCI region mappings continue to read these catalogues.

## Exadata shape catalogues

- Aligned AWS, Azure and Google Cloud catalogues with Oracle's current Exadata Dedicated provisioning guides: `Exadata.X9M`, `Exadata.X11M` and `Exadata.X11MV`.
- Added X11MV to Azure and Google Cloud; removed unconfirmed X10M entries from new selections. Saved shape values absent from the catalogue remain visible as **not in catalogue**.
- For AWS and Azure, X9M uses provider-default server types. Documented newer server pairs are `X11M` / `X11M-HC` and `X11MV` / `X11MV-HC`; removed unconfirmed EF storage choices.
- Shape and server-type choices remain driven by the editable Shape Catalogue. Existing default shapes are unchanged. Google Terraform server versions remain computed outputs rather than selectable inputs.
- Added a reminder that shape availability depends on region, zone and account. This refresh uses documentation, not authenticated account-specific shape discovery.

## Upgrade notes

- Refresh the browser after upgrading and generate a new Terraform/OpenTofu ZIP to use the refreshed catalogues. Previously downloaded files do not update automatically.
- Review corrected OCI provider regions before applying an existing configuration. Terraform state and deployed resources are not migrated automatically.
- Review route ownership and both plans when enabling Transit VPC peered-CIDR registration. No Transit Gateway, application VPC or cloud infrastructure is created by installing this application release.
- Customer configurations, credentials, runtime authentication settings and static blueprint files are excluded from this source change. Preserve your data volume and environment file when updating a container.

## Sources

- Regional availability: [AWS](https://docs.oracle.com/en-us/iaas/Content/database-at-aws/oaaws-regions.htm), [Azure](https://docs.oracle.com/en-us/iaas/Content/database-at-azure/oaa_regions.htm), [Google Cloud](https://docs.oracle.com/en-us/iaas/Content/database-at-gcp/get-started-regions.htm).
- Exadata shapes: [AWS](https://docs.oracle.com/en-us/iaas/Content/database-at-aws-exadata-awscr/awscr-create-exadata-infrastructure.html), [Azure](https://docs.oracle.com/en-us/iaas/Content/database-at-azure/azucr-create-exadata-infrastructure.html), [Google Cloud](https://docs.oracle.com/en-us/iaas/Content/database-at-gcp/gcpcr-create-exadata-infrastructure.html).
- [Azure physical/logical availability-zone mappings](https://learn.microsoft.com/azure/availability-zones/az-overview).

## Validation

- Full clean-checkout suite: 1,344 tests and 363 subtests passed; four optional checks were skipped in that run.
- The initial six provider-backed checks could not reach the Terraform registry in the restricted environment; all six passed when rerun with registry access. The opt-in Transit VPC provider-backed test also passed, covering five mocked Terraform plan scenarios (seven Python tests passed in the provider rerun).
- Two pre-existing assertions remain: an outdated GCP page-label assertion and a test expecting eight saved customer infrastructures that are intentionally absent from a clean source checkout. Customer fixtures were not added to the repository.
- Catalogue/API checks, cloud page rendering, shared shape-picker JavaScript syntax, catalogue-driven custom choices and X11MV Terraform generation were verified. Local container pages were checked against the served catalogues.
- Static blueprint files and customer data are unchanged. No cloud infrastructure was applied.
