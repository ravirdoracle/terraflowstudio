# Terraflow Studio v2026.11.17

## Interactive tutorial and cloud screen fixes

- Added a standalone HTML tutorial, available from the home page and `/tutorial`.
- Added separate AWS, GCP, Azure, OCI Data Guard and OCI DB walkthroughs: 57 scenes in total.
- Replaced shared mockups in the GCP and Azure walkthroughs with captures of their actual workspace pages using sample data. Each now includes its own network, Exadata infrastructure, VM cluster, generated Terraform and mock validation screens.
- Added play/pause, replay, seeking, playback speed, chapters, keyboard controls and a written walkthrough.
- Download HTML preserves the selected workspace and embeds the screen captures for offline playback. Playback does not execute cloud commands or modify saved configurations.

## Active Data Guard and UI features included

- Create a standby and its Data Guard association on a supported existing VM cluster or DB system, with Active Data Guard enabled by default.
- Inspect an existing database pair through read-only association lookup. This does not associate two independently created databases.
- Generate Terraform/OpenTofu, OCI CLI scripts, or both. Creation prompts for the primary database password at runtime; it is not embedded in generated files.
- Removed AI template controls and the AI prompt bar. Spreadsheet import and template download appear below the customer row on AWS, GCP, Azure and OCI Data Guard.

## Download or pull

The release provides Linux AMD64 (Intel/AMD x86_64) and ARM64 archives, each with a SHA-256 checksum. Use Images → Load in Podman Desktop.

```sh
# The registry selects the host architecture.
podman pull ghcr.io/ravirdoracle/terraflowstudio-images:v2026.11.17
```

Or download `odb-terraform-app-amd64.tar` or `odb-terraform-app-arm64.tar` and its `.sha256` file. Verify the checksum, then use `podman load -i ARCHIVE.tar`. Archives contain `localhost/odb-terraform-app:latest`.

Set `APP_AUTH_USER` and `APP_AUTH_PASSWORD` in a private `.env`, then run:

```sh
podman run -d --name terraflowstudio --restart unless-stopped \
  -p 0.0.0.0:8080:5000 --env-file .env \
  -v terraflowstudio-data:/app/data \
  ghcr.io/ravirdoracle/terraflowstudio-images:v2026.11.17
```

Open `http://localhost:8080` or `http://HOST_IP:8080` on a reachable private network. Docker users can substitute `docker` for `podman`. Use HTTPS when exposing Basic authentication beyond a trusted private network.

Reuse the existing data volume when upgrading. Stop and rename the old container before reusing its name. Refresh the browser after upgrading, and download a fresh tutorial HTML if using an older offline copy.

## Validation

- All 57 tutorial scenes checked in Chrome, including cloud-specific screens, playback, seeking, completion, keyboard controls, offline download, direct workspace links and mobile layout; no external tutorial requests or JavaScript errors.
- 39 Data Guard/CLI tests and 54 architecture tests passed.
- Data Guard UI configuration roundtrip, password filtering, preview paths and defaults checked.
- Published images checked for authentication, application source parity and exclusion of local credentials. Terraform and OpenTofu remain bundled; provider initialization requires network access.
- Full suite: 1,298 tests run; 1,287 passed, 3 skipped, 8 failed. Six provider-initialization tests could not reach the Terraform registry in the restricted local test environment. The other failures are an older GCP page-label assertion and a test requiring saved customer fixtures absent from the clean checkout. These unrelated assertions and customer data were not changed.
- Full suite: 1,298 tests run; 1,287 passed, 3 skipped, 8 failed. Six provider-initialization tests could not reach the Terraform registry in the restricted local test environment. The other failures are an older GCP page-label assertion and a test requiring saved customer fixtures absent from the clean checkout. These unrelated assertions and customer data were not changed.
- No cloud infrastructure was created during validation.
