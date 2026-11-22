# Configuration reference

The examples contain placeholder credentials, documentation-only recorder addresses, and example camera identities. Supply your own values before deployment. The current helpers configure seven channels; changing the channel count requires reviewing the application, network helper, installer, and MediaMTX permissions together.

## Installation and service account

Python helpers locate the project from their own script location. The installer locates the checkout from its own location and renders systemd units for that directory. The standalone unit templates use a neutral installation location; do not copy them directly without reviewing their settings.

Create an unprivileged service account before installing. The default account and group in the templates are named `nightowl`. To select an existing account, pass `NIGHTOWL_SERVICE_USER` to the installer; its primary group is used automatically. The account needs access to the project, Node.js, FFmpeg, the NVIDIA devices, private configuration, and runtime files. Use a checkout location without spaces or shell metacharacters.

Install the Node.js dependencies, Python NumPy, and an FFmpeg build with `h264_nvenc`. Place the appropriate Linux MediaMTX executable in the project's `bin` directory as `mediamtx`. Review upstream release checksums when obtaining binaries. The installer creates the writable runtime directory for the selected service account.

## Recorder and stream configuration

Run the configuration helpers as the intended service account from the project directory:

```bash
python3 configure-nightowl.py --host recorder.example.invalid
python3 setup-transcoding.py --host recorder.example.invalid
```

Replace the example hostname with your recorder's hostname or address. Both helpers prompt for it when `--host` is omitted. Passwords are entered through a hidden prompt; do not put them on the command line.

The probe saves stream metadata to `probe-results.json`. An exit code of `2` means one or more main streams are unavailable or are not H.264. Review the results: H.265 streams can be handled by the transcoding setup when valid metadata was obtained. Confirm that the configured channels actually show different camera feeds.

The transcoding helper reads that metadata and writes private `config.yaml` and `mediamtx.yml` files. It derives channel identities from the recorder hostname, generates a local worker password, and prompts for a separate bridge password. Keep the recorder hostname consistent when regenerating configuration to preserve the generated UUIDs. Existing per-camera motion settings are preserved when the MAC identities match.

The example camera configuration uses relative runtime filenames. Generated configuration uses paths for the current checkout. If you relocate an installation, regenerate or update its private configuration before restarting services. Cached WSDL and schema imports are relative and can move with the checkout.

The example MAC range must be unique on your LAN. If you deploy multiple bridges or have conflicting devices, change it consistently in the camera configuration, configuration generators, and network helper before installation.

## Virtual camera networking

Copy `deployment/network.example.env` to `deployment/network.env` and replace all three values:

- `NIGHTOWL_PARENT_INTERFACE`: the server's LAN interface used for macvlan cameras.
- `NIGHTOWL_GATEWAY`: the IPv4 gateway reachable from that interface.
- `NIGHTOWL_LAN_CIDR`: the local subnet allowed by the generated UFW rules.

The example uses a reserved documentation network. The installer rejects that unchanged gateway. The configured file is ignored by Git and Docker, then installed as a root-owned environment file for the network service. Review it as executable shell configuration before running the installer.

Review and run the installer after preparing the service account, credentials, network settings, and dependencies:

```bash
sudo env NIGHTOWL_SERVICE_USER=nightowl bash deployment/install-nightowl.sh
```

Each virtual camera needs its own DHCP lease. Reserve leases if stable addresses are required. The supervisor writes the current channel-to-address mapping to `runtime/camera-addresses.json`.

## Diagnostic targets

The endpoint and event checks use that local address map by default. To run them elsewhere, provide a copied map with `--addresses-file` or pass camera addresses in channel order:

```bash
python3 tools/check-endpoints.py camera-one.example.invalid camera-two.example.invalid
python3 tools/check-motion-events.py --addresses-file camera-addresses.json
```

These checks contact the supplied targets. The discovery tool sends standard ONVIF discovery probes on the local network. Keep generated address maps and diagnostic output private if they identify your deployment.

## Private files and export metadata

Private configuration, the configured network environment, runtime files, and camera media are excluded by the included ignore rules. Private installation notes are not included in this repository copy. Preserve local backups separately from the folder you publish.

`EXPORT-MANIFEST.json` lists repository-relative filenames and hashes of this sanitized snapshot. It does not contain original machine paths. Regenerate its hashes after making further changes if you intend to use it for integrity verification.
