# NightOwl ONVIF Bridge for UniFi Protect

Bridge NightOwl DVR camera channels into UniFi Protect as individual ONVIF cameras, with H.264 transcoding, snapshots, and video-based motion events.

Developed for an Ubuntu Linux server, this project builds on [daniela-hase/onvif-server](https://github.com/daniela-hase/onvif-server). It adds a transcoding pipeline and per-camera motion notifications for recorders that expose RTSP streams but do not provide the ONVIF integration needed by Protect.

## Features

- Separate ONVIF discovery and adoption for each recorder channel.
- H.265-to-H.264 main-stream transcoding using NVIDIA NVENC.
- CPU-encoded low-resolution streams and live JPEG snapshots.
- Server-side motion detection with configurable sensitivity, noise filtering, warmup, and event hold time.
- Per-camera ONVIF PullPoint motion notifications.
- systemd service definitions and virtual-network helpers.
- Cached ONVIF schemas and diagnostic tools.

The reference configuration supports seven camera channels. Compatibility with other recorders, channel counts, and hardware configurations has not been verified.

## How it works

1. MediaMTX pulls an RTSP stream for each recorder channel.
2. FFmpeg produces H.264 main and low-resolution streams, snapshots, and grayscale frames for motion analysis.
3. The ONVIF bridge exposes each channel through its own virtual network interface and camera identity.
4. Protect discovers and adopts each virtual camera independently, then receives motion notifications through the ONVIF Events service.

Motion is detected from video on the server. The bridge does not depend on the recorder's native alarm API. Face recognition, license-plate recognition, audio, and PTZ are not implemented by this bridge.

## Requirements

- An Ubuntu Linux server with systemd and systemd-networkd.
- Node.js 22, Python 3 with NumPy, and FFmpeg with NVIDIA NVENC support.
- An NVIDIA GPU and driver with sufficient encoding capacity for the configured streams.
- [MediaMTX](https://github.com/bluenviron/mediamtx); the reference deployment used version 1.21.3.
- A NightOwl recorder with accessible RTSP streams and valid streaming credentials.
- UniFi Protect with third-party camera discovery enabled.
- A network that supports macvlan interfaces and a separate DHCP lease for each virtual camera.

The supplied deployment uses native Linux services. The inherited Dockerfile has not been adapted or validated for the complete transcoding and motion pipeline.

## Configuration and deployment

The deployment helpers and example configurations reflect a reference installation. They require adaptation before use on another system; this repository does not yet provide a portable installer.

1. Review the deployment scripts and service definitions. Create an unprivileged service account and give it access to the checkout, configuration, runtime directory, and GPU. The installer defaults to account `nightowl`; set `NIGHTOWL_SERVICE_USER` to use another account.
2. Install the requirements and Node.js dependencies with `npm ci --omit=dev --ignore-scripts`.
3. Use `config.example.yaml`, `mediamtx.example.yml`, and `probe-results.example.json` as configuration references. Both configuration helpers accept `--host` or prompt for the recorder address. Run them as the service account. The transcoding setup helper also prompts for recorder credentials and a separate bridge password.
4. Copy `network.example.env` to `network.env` in the deployment directory and set the LAN interface, gateway, and allowed subnet. Review the installer before running it with elevated privileges. It uses the checkout's location and creates virtual interfaces, routing rules, services, and firewall rules when UFW is active. See [configuration details](docs/CONFIGURATION.md).
5. Start the services and verify that each virtual camera receives its own network address. DHCP reservations are recommended for stable adoption addresses.
6. In Protect, enable **Discover Third-Party Cameras** and adopt each camera using the bridge credentials. If necessary, use **Advanced Adoption** with the camera's address and ONVIF port `8081`. The bridge exposes RTSP on port `8554`.

Keep real credentials, private configuration, runtime data, recordings, snapshots, and operational backups out of version control. Git and Docker ignore rules are included; review them before publishing.

## Motion tuning

Each camera's `motion` configuration controls detection sensitivity. The example configuration uses:

| Setting | Value | Purpose |
|---|---|---|
| `pixelThreshold` | `24` | Minimum pixel intensity change |
| `minChangedPercent` | `0.4` | Minimum percentage of changed pixels |
| `holdSeconds` | `8` | Time to keep motion active after the last detection |
| `warmupSeconds` | `10` | Initial detector settling time |

Increase the first two values to reduce sensitivity to rain, dust, and small changes. Restart the affected transcoder after changing its configuration. Video-based motion detection can still produce false positives during weather or lighting changes.

Lower sensitivity reduces event markers. With continuous recording enabled in Protect, it does not materially reduce video storage usage.

## Diagnostics

Use the included endpoint and motion-event tools to check discovery, stream availability, and event subscriptions. They accept camera addresses in channel order or read the local runtime address map; use `--help` for options. Service logs are available through `journalctl`; `nvidia-smi` can help check GPU activity.

Run the isolated detector and event-service checks with:

```bash
python3 test_motion_detector.py
node --test test-events-service.js
```

## License and attribution

This project uses the [MIT License](LICENSE). The upstream copyright and license notice are preserved. See the [upstream project](https://github.com/daniela-hase/onvif-server) for its original implementation and documentation.

MediaMTX, FFmpeg, and other dependencies are separate projects with their own licenses. Bundled ONVIF, W3C, and OASIS schema files retain their respective notices and provenance.

This is an independent community project and is not affiliated with or endorsed by NightOwl or Ubiquiti.
