# 37 - Moving to a systemd distribution (handoff, 2026-11-27)

Decision (owner): the Alpine/OpenRC userland needs too many workarounds; the plan is to move to a systemd distribution **after** the important hardware works. This page is the handoff for whoever (agent or person) does it. Nothing here has been tried yet.

## Owner's choice (2026-11-27): two variants, to be built later
1. **Mobian (Debian) with Phosh**, the recommended one above.
2. **Fedora with Plasma Mobile** (`@plasma-mobile`/KDE Plasma Mobile packages, SDDM or its autologin, kwin_wayland, PipeWire; Plasma Mobile brings its own session, KDE Connect/Plasma Settings and its own Bluetooth/Wi-Fi/sensor integration, so the Phosh-specific workarounds below do not apply there: check how it gets orientation and sensors from `iio-sensor-proxy`/`libssc`, and how its Bluetooth and hostname settings work with systemd-hostnamed).
Both share the same boot image, kernel, firmware, udev rules and the delegated `iio-sensor-proxy` fix; they differ only in the rootfs recipe (`mkosi --distribution=debian` and `--distribution=fedora`) and the session/audio layer. Keep the rootfs recipes side by side in the repo and share one overlay of the common pieces.

## What does not change
The kernel (`linux-mainline-bitra`, branch `bitra`, `7.2.0-bitra`, DTB embedded through `CONFIG_BITRA_DTB_SHIM`), the boot image builder (`scripts/build_mainline_boot.py`, initramfs with the USB-NCM gadget and the `bitra.root=` switch_root hook, so the distro only has to provide a root filesystem for the `userdata` partition), the firmware tooling (`tools/bitra-firmware.py`, `firmware/manifest.json`, `tools/make-ath11k-board.py`, docs/FIRMWARE.md, docs/35), the SMEM sensor inventory driver (built into the kernel), the udev rules, the flashing/test flow with `bitra-agent`, and the safety rules in `AGENTS.md`.

## Candidates (all systemd; my knowledge of each project's current state is from memory, verify before choosing)
| Distro | For | Against |
|---|---|---|
| **Mobian (Debian stable/testing)** | Phosh is its main product, mature phone defaults (feedbackd, ModemManager, iio-sensor-proxy, squeekboard), huge package set, systemd-hostnamed so Phosh's device-name setting works and BlueZ takes name and class from the hostname/`/etc/machine-info` (`CHASSIS=handset`) | older Mesa/Phosh on stable (testing is newer); its device support targets other phones, SM8250 images would be our own |
| **Fedora (aarch64, Phosh packages)** | recent Mesa (freedreno/turnip), recent bluez/NetworkManager/Phosh, strong systemd integration, SELinux | no phone-specific image tooling for Qualcomm phones; rootless image builds need `mkosi` or `dnf --installroot` in a user namespace |
| **postmarketOS with its systemd option** (if still offered) | keeps the device-packaging ecosystem where `hexagonrpcd`/`libssc`-style packages came from | still Alpine/musl and its tooling (`pmbootstrap`) wants chroots/sudo, which conflicts with our no-sudo/no-containers rule |
| **Arch Linux ARM / DanctNIX Mobile** | newest packages, AUR for `hexagonrpcd`/`libssc` | rolling breakage, ARM port upkeep |
| **NixOS / mobile-nixos** | reproducible, declarative: the whole phone config in one tree | steep learning curve, little SM8250 precedent |
Not options: Droidian and Ubuntu Touch (Android HAL / libhybris, not mainline), Sailfish.

**Recommendation:** Debian-based (Mobian-style, trixie or testing), built rootless with `mkosi` (the systemd project's image builder: `--distribution=debian`, also supports Fedora and Arch, so switching distro later is a config change) or `debootstrap` in a user namespace like the current builder. Fedora is the second choice if Mesa/Phosh freshness matters more than package breadth. Decide with these checks: (1) are `hexagonrpcd` and `libssc` + `iio-sensor-proxy` with the SSC drivers packaged (else build them: small C/meson projects); (2) Mesa freedreno/turnip version for the Adreno 650; (3) bluez >= 5.8x, ath11k firmware package contents; (4) can the image be built without root and without containers.

## Workarounds to translate (where each lives today)
| Alpine/OpenRC piece | Files | On systemd |
|---|---|---|
| USB-NCM gadget, telnetd, udhcpd (`bitra-net`, `bitra-telnetd`, `bitra-udhcpd`) | `scripts/build_alpine_rootfs.py` (init script text) + initramfs | the initramfs gadget stays; `usb0` handled by systemd-networkd or NetworkManager (unmanaged or static 192.168.2.15); use sshd, drop telnet (root shell, no password) |
| `bitra-time` (RTC is read-only, keeps an offset) | same | `systemd-timesyncd` saves the clock at shutdown/boot natively; check the RTC offset case |
| `bitra-pstore` (copy ramoops to `/var/lib/pstore`) | same | `systemd-pstore.service` |
| `bitra-growfs` | same | `systemd-growfs` or repart |
| `bitra-diag` | same | persistent journald |
| `hexagonrpcd-sdsp` + sensor config tree + pruning | `docs/32-sensors.md`, `scripts/build_alpine_rootfs.py` (drop list), `tools/sensor-prune*.sh`, `tools/sensor-timeline.sh` | a unit with the same arguments (`-f /dev/fastrpc-sdsp -d sdsp -s -R /usr/share/qcom/sm8250/realme/bitra`), served directory, stock registry from the owner's persist backup |
| `bitra-sensors` (restarts Phosh once) | `rootfs-overlay/etc/init.d/bitra-sensors`, TODO in `docs/known-issues.md` | retire it once `iio-sensor-proxy` waits for the SSC (delegated task) |
| `81-bitra-iio-sensor-proxy.rules` (ssc types, `ACCEL_MOUNT_MATRIX`) | `rootfs-overlay/etc/udev/rules.d/` | unchanged |
| `bitra-wifi-mac` (SoC-serial MAC, OEM board data gives MAC 0) | `rootfs-overlay/etc/init.d/bitra-wifi-mac`, docs/35 | a first-boot unit writing `/etc/systemd/network/10-bitra-wlan.link` with `MACAddress=`, or a oneshot `Before=NetworkManager.service`; keep `wifi.cloned-mac-address=preserve` |
| `bitra-bt-addr` (btmgmt public-addr) | `rootfs-overlay/etc/init.d/bitra-bt-addr`, docs/36 | oneshot `Before=bluetooth.service` (btmgmt through `script`) |
| BlueZ name/class | `rootfs-overlay/etc/bluetooth/main.conf` | with hostnamed BlueZ's hostname plugin sets name and class from the pretty hostname/chassis; keep `main.conf` as the fallback |
| NetworkManager `bitra-wifi-mac.conf` | overlay | unchanged |
| PulseAudio mic remap (`bitra-mic.pa`) and ALSA UCM profile | `rootfs-overlay/etc/pulse`, `usr/share/alsa/ucm2` | UCM files unchanged; most systemd distros use PipeWire/WirePlumber: port the `bitra_mic` remap (the second PCM channel is silent, docs/31) |
| tinydm autologin + sway/Phosh start | builder, `rootfs-overlay/.../sway` | the distro's own greeter/autologin for Phosh (e.g. greetd or the Phosh systemd unit) |
| elogind/polkit-elogind | package list | native logind |
| `bitra-agent` shell path (telnet on 192.168.2.15:23) | `agent/` | the agent talks telnet today; with sshd on the phone the agent needs an ssh transport (small change in `bitra_agent.py`) |
| Wi-Fi credentials | never baked into images | keep: `put wpa.conf`/NM connection after install |

## Things that get easier
Phosh's device-name setting and BlueZ name via hostnamed; native logind (no elogind/polkit-elogind workarounds); pstore, timesync, growfs and journald as stock units; the session restart workaround disappears once the sensor proxy waits for the SSC; PipeWire gives a normal Bluetooth A2DP path.

## Definition of done for the migration
Same hardware status as docs/27 (display, touch, GPU, Wi-Fi with the OEM board data, Bluetooth with its own address, audio, sensors with rotation, USB-NCM shell, battery gauge, haptics, NFC), `userdata` flashed (needs the owner's explicit approval: it wipes the Alpine root), recovery path documented, `docs/27` and a new doc updated, the rootfs reproducible from the repo with no root and no containers.
