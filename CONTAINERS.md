# Run Terraflow Studio in a container

The container serves the app on port **5000**. The commands below publish it on
port **8080** of the computer running Podman or Docker.

## Prerequisites

- Install Podman Desktop / Podman, or Docker Desktop / Docker Engine.
- On macOS or Windows with Podman, start the Podman machine in
  **Settings → Resources**. Wait for **Running**.
- Run the commands from this project's directory.
- Copy `.env.example` to `.env` if you do not already have a `.env` file:

  ```sh
  cp .env.example .env
  ```

Set `APP_AUTH_USER` and a strong `APP_AUTH_PASSWORD` in `.env` before enabling
network access. Your browser will prompt for these credentials when opening the
app. Both fields must be set together; partial configuration blocks requests.

Edit `.env` to configure optional AI integrations. Basic Terraform generation
does not require API keys. Do not commit `.env` or include credentials in an image.

The exported `odb-terraform-app-arm64.tar` image supports **Linux ARM64**, including
Apple Silicon through Podman or Docker Desktop. For an AMD64 host, build from the
Dockerfile on that host; it selects the matching Terraform and OpenTofu binaries.

## Load or build the image

For the exported image archive:

```sh
podman load -i artifacts/odb-terraform-app-arm64.tar
podman images --filter reference=localhost/odb-terraform-app:latest
```

In Podman Desktop, use **Images → Load**, select the archive, then look for
`odb-terraform-app`. A saved image archive uses **Load**, not **Import Containers**.

Alternatively, build from source:

```sh
podman build -t localhost/odb-terraform-app:latest .
```

## Run with access through the host IP

```sh
podman run -d \
  --name odb-terraform-app \
  --restart unless-stopped \
  -p 0.0.0.0:8080:5000 \
  --env-file .env \
  -v odb-terraform-data:/app/data \
  localhost/odb-terraform-app:latest
```

Open either:

- On this computer: **http://localhost:8080**
- On another device on the same reachable network: **http://HOST_IP:8080**

Replace `HOST_IP` with the container host's LAN IP, not the Podman VM IP.
On a Mac using Wi-Fi, `ipconfig getifaddr en0` usually shows this address.
The host firewall must allow inbound TCP port 8080. VPNs and Wi-Fi client
isolation can prevent other devices from reaching the host.

Keep both `APP_AUTH_USER` and `APP_AUTH_PASSWORD` configured for IP access: they
protect every page and API, including settings. Basic authentication needs HTTPS
to encrypt credentials in transit; plain HTTP is only appropriate on a trusted
private network. For internet access, place an HTTPS reverse proxy in front of
the app and require these credentials.

The named volume `odb-terraform-data` preserves saved customer configurations
when the container is recreated. To use existing configurations from this
project's `data` directory instead, replace the volume option with:

```sh
-v "$(pwd)/data:/app/data"
```

To limit access to this computer, use `-p 127.0.0.1:8080:5000` instead.
Changing the port binding requires recreating the container.

For Docker, replace `podman` with `docker` in the load, build, run, logs, and
container-management commands. The same image archive and Dockerfile work with
both engines on the matching CPU architecture.

## Check and manage the app

```sh
podman ps --filter name=odb-terraform-app
podman logs --tail 50 odb-terraform-app
# Prompts for your password; replace admin if APP_AUTH_USER differs.
curl --fail --user admin http://localhost:8080/ -o /dev/null
podman stop odb-terraform-app
podman start odb-terraform-app
```

In Podman Desktop, the container appears under **Containers**. Use its exposed
8080 port link to open the app.

After changing the host `.env`, recreate the container to apply its new values:

```sh
podman stop odb-terraform-app
podman rm odb-terraform-app
# Repeat the run command above, using the same data volume or bind mount.
```

Settings edited inside a container should also be recorded in the host `.env`;
the container's own filesystem is not retained when it is removed.

## Publish to GitHub Container Registry

Repository: **https://github.com/ravirdoracle/terraflowstudio**.
Image: **`ghcr.io/ravirdoracle/terraflowstudio:latest`**.
This registry destination is independent of the app's Terraform GitHub
integration. The commands below require the image to have been published.

The repository's **Publish container image** GitHub Actions workflow builds and
checks authentication, then publishes **AMD64 and ARM64** variants. It runs on a
push to `main`, a `v*` tag, or manually through **Actions → Publish container image
→ Run workflow**. It uses the repository's automatic `GITHUB_TOKEN` with
`packages: write`; you do not need to store a personal token for this workflow.
The `latest` tag and a source-commit `sha-...` tag are published together.

To push the existing local ARM64 image manually instead, authenticate locally
with a GitHub personal access token (classic) that has
`write:packages`; enter the token at the password prompt, not in a command or chat:

```sh
podman login ghcr.io --username ravirdoracle
podman tag localhost/odb-terraform-app:latest ghcr.io/ravirdoracle/terraflowstudio:latest
podman push ghcr.io/ravirdoracle/terraflowstudio:latest
```

The exported local image is ARM64. A manual registry push preserves that
architecture; use the workflow for a multi-platform image.

After workflow publication, on another AMD64 or ARM64 host:

```sh
# Authenticate first if the package is private.
podman login ghcr.io --username ravirdoracle
podman pull ghcr.io/ravirdoracle/terraflowstudio:latest
```

Use `ghcr.io/ravirdoracle/terraflowstudio:latest` as the image in the run command.
Public packages can be pulled without login. Review package visibility in
GitHub before sharing the image address.

Reference: [GitHub Container Registry documentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).
