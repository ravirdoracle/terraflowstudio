# Terraflow Studio v2026.11.22

## Azure existing-resource workflows

- Added **Create new / Use existing** selectors for Network Anchors, Exadata infrastructure, and client VNets/subnets.
- Existing Network Anchors and Exadata infrastructure require their Azure resource IDs. Existing networking requires the client subnet resource ID; its parent VNet ID is derived automatically.
- Existing-resource modules pass IDs and outputs to dependent resources. They do not create, import, or manage the linked infrastructure, networking, subnet delegation, or DNS settings.
- Added opt-in Network Anchor provisioning for new VM clusters through `Oracle.Database/cloudVmClusters@2026-06-01` with `azure/azapi >= 2.14.0`. Saved configurations retain their existing AzureRM provisioning path unless explicitly changed.
- Kept the VM cluster's client subnet separate from the Network Anchor's own subnet.

## Terraform generation and configuration fixes

- Omit untouched sample cards from generated resources, preventing blank VNet and other placeholder modules from being deployed.
- Preserve entered resource groups and regions in per-resource root inputs. Infer deployment defaults only from unambiguous configured values, and infer a subscription only when the entered resource IDs identify one subscription. Explicit root inputs take precedence.
- Preserve entered values in `terraform.auto.tfvars`; comment blank values and sample assignments rather than making them active settings. Review `variables.tf` defaults when changing assignments.
- Export OCI VCN metadata only for newly created Network Anchors. Existing ID-only anchors no longer generate the unsupported `module.<anchor>.oci_vcn_id` reference.
- Validate required existing-resource IDs and missing client network inputs earlier.
- Keep empty resource lists empty when loading saved configurations instead of restoring seeded sample cards.
- Preserve creation settings when switching a card between new and existing modes.

## Import guidance

- Generated Terraform/OpenTofu output now includes `IMPORT.md` in previews, ZIP downloads, and GitHub exports.
- The guide inventories resource address templates across local modules and independent state roots, links provider import documentation, and describes instance keys, state backups, CLI imports, import blocks, and plan review.
- Reusing an external resource by ID does not require importing it. Import guidance is for resources whose management you explicitly want to bring into the generated configuration's state.

## Upgrade notes

- Refresh the browser after upgrading and generate a new ZIP. Previously downloaded Terraform does not update automatically.
- For an existing client network, select **Use existing VNet / subnet**, enter the client subnet's full Azure resource ID, and select that card on the VM cluster.
- Changing a previously applied **Create new** card to **Use existing** requires a separate state migration; the application does not perform that migration.
- Static files under `blueprints/azure` were not changed.
- Saved customer data and runtime authentication settings are not included in the image. Reuse your data volume and environment file when upgrading.

## Container images

Linux AMD64 and ARM64 images and downloadable image archives are published through the existing image release repository. Each archive has a SHA-256 checksum.

```sh
podman pull ghcr.io/ravirdoracle/terraflowstudio-images:v2026.11.22
```

Docker users can substitute `docker` for `podman`. Keep your current data volume and runtime environment settings. The versioned tag selects the host architecture automatically.

## Validation

- All 218 Azure regression tests passed, including Terraform validation of existing-anchor outputs and a provider-free Terraform plan proving that existing client subnet references create no network resources.
- Full suite: 1,334 passed and 3 skipped, including all six provider-backed Terraform initialization/validation tests. Two pre-existing failures remain: an outdated GCP page-label assertion and a test that expects local saved-customer fixtures absent from a clean checkout.
- Native container checks cover authentication, credential exclusion, application source parity, all existing-resource modes, and bundled Terraform/OpenTofu binaries.
- No cloud infrastructure was applied during validation.
