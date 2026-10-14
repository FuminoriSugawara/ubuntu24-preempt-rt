# PREEMPT_RT kernel for Ubuntu 24.04

[日本語のインストール手順](INSTALL.ja.md)

This repository provides build scripts and Debian packages for Linux 6.17.5 with the rt7 patch, using an Ubuntu kernel configuration as the baseline.
The packages target Ubuntu 24.04 on amd64; building from source is optional.

## Requirements

- Ubuntu 24.04 / amd64, with any required external drivers compatible with this kernel.
- About 3 GiB free in `/usr` and 1 GiB in `/boot`; allow another 8 GiB for optional debug symbols.
- Console access to select the previous kernel in GRUB if boot fails.
- Secure Boot disabled, or your own signing and key enrollment setup; this kernel has no Canonical boot signature.

Keep the previous kernel installed.
Check the OS, architecture and available space below; on UEFI systems, check Secure Boot with `mokutil --sb-state`.

```bash
cat /etc/os-release
dpkg --print-architecture
df -h /usr /boot
```

## Download and install

Download these three files from the [release Assets](https://github.com/FuminoriSugawara/ubuntu24-preempt-rt/releases/tag/rt-6.17.5-rt7) into one directory.

- `linux-image-6.17.5-rt7_6.17.5-rt7-1_amd64.deb`
- `linux-headers-6.17.5-rt7_6.17.5-rt7-1_amd64.deb`
- `SHA256SUMS`

Run the following commands in that directory.
Confirm that both packages report `OK` before installing; `--ignore-missing` skips the optional debug package.

```bash
sha256sum --check --ignore-missing SHA256SUMS
```

```bash
sudo apt install ./linux-image-6.17.5-rt7_6.17.5-rt7-1_amd64.deb \
  ./linux-headers-6.17.5-rt7_6.17.5-rt7-1_amd64.deb
```

Confirm that installation, including any DKMS builds, finishes without errors and that both boot files exist.

```bash
ls -lh /boot/vmlinuz-6.17.5-rt7 /boot/initrd.img-6.17.5-rt7
```

### Optional debug symbols

Download `linux-image-6.17.5-rt7-dbg_6.17.5-rt7-1_amd64.deb` from the same release into the directory containing `SHA256SUMS`.
Confirm that this package reports `OK`, then install it.

```bash
sha256sum --check --ignore-missing SHA256SUMS
sudo apt install ./linux-image-6.17.5-rt7-dbg_6.17.5-rt7-1_amd64.deb
```

## Select the default kernel and reboot

Set `6.17.5-rt7` as the default and show the GRUB menu for 10 seconds during evaluation.
Separate files allow you to restore the original timeout without changing the default kernel.

```bash
printf '%s\n' 'GRUB_DEFAULT="Advanced options for Ubuntu>Ubuntu, with Linux 6.17.5-rt7"' | \
  sudo tee /etc/default/grub.d/zz-rt-default.cfg
```

```bash
printf 'GRUB_TIMEOUT_STYLE=menu\nGRUB_TIMEOUT=10\n' | \
  sudo tee /etc/default/grub.d/zz-rt-menu.cfg
sudo env LC_ALL=C update-grub
```

`LC_ALL=C` generates the English menu titles used by the default setting.
Confirm that `update-grub` succeeds and detects `vmlinuz-6.17.5-rt7`.
Finish active work, ensure console access, then reboot.
Without input, GRUB boots this kernel after 10 seconds; select another kernel under “Advanced options for Ubuntu” if needed.

```bash
sudo reboot
```

After boot, expect `6.17.5-rt7` and `1`, respectively.

```bash
uname -r
cat /sys/kernel/realtime
```

Check your devices and applications.

## Restore the original timeout

After evaluation, remove only the menu override.
This restores the original menu visibility and timeout while keeping the RT kernel as the default.

```bash
sudo rm /etc/default/grub.d/zz-rt-menu.cfg
sudo env LC_ALL=C update-grub
```

## Update to a newer release

Updates are installed manually from [Releases](https://github.com/FuminoriSugawara/ubuntu24-preempt-rt/releases).
Keep the current kernel installed until the new one works correctly.

1. Download the new image, headers and `SHA256SUMS` into a separate directory. If needed, also download the matching debug package.
2. Follow [Download and install](#download-and-install), using the new filenames, and confirm the checksum and installation results.
3. Follow [Select the default kernel and reboot](#select-the-default-kernel-and-reboot), replacing `6.17.5-rt7` with the new kernel name in the GRUB setting. Restore the 10-second menu if it was removed.
4. Reboot and confirm that `uname -r` shows the new kernel name and `/sys/kernel/realtime` is `1`. Check your devices and applications.
5. Once verified, [restore the original timeout](#restore-the-original-timeout).

The kernel name is the part after `linux-image-` in the image filename, before the first underscore; it is distinct from the package version after that underscore.
If the update fails, boot the previous kernel from GRUB and set its name as the default using the same configuration procedure.

## Roll back

Boot the previous kernel from GRUB and confirm it with `uname -r`.
Remove the default override, then remove the RT packages if no longer needed.

```bash
sudo rm /etc/default/grub.d/zz-rt-default.cfg
sudo update-grub
```

```bash
sudo apt remove linux-image-6.17.5-rt7 linux-headers-6.17.5-rt7
sudo update-grub
```

If installed, also remove `linux-image-6.17.5-rt7-dbg`.

<details>
<summary>Build from source</summary>

Use an x86_64 host with Docker access and about 100 GiB of free space.
The script downloads and verifies the source and patch, then builds in the background.

```bash
git clone --branch rt-6.17.5-rt7 https://github.com/FuminoriSugawara/ubuntu24-preempt-rt.git
cd ubuntu24-preempt-rt
JOBS=16 MEMORY=24g ./build-rt-kernel.sh
source scripts/kernel-settings.sh
docker logs --tail 30 -f "$DEFAULT_CONTAINER_NAME"
```

Press Ctrl+C to stop following the logs.
Once the container reports `exited` with exit code `0`, check the artifacts.

```bash
docker inspect --format '{{.State.Status}} exit={{.State.ExitCode}}' "$DEFAULT_CONTAINER_NAME"
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD:/workspace" -w /workspace rt-kernel-builder:noble \
  bash scripts/check-artifacts.sh
```

Packages are written to `artifacts/6.17.5-rt7/`; the build does not install them on the host.

</details>

## Source and licensing

Kernel source and the RT patch are in the [source release](https://github.com/FuminoriSugawara/ubuntu24-preempt-rt/releases/tag/sources-6.17.5-rt7).
The [release tag](https://github.com/FuminoriSugawara/ubuntu24-preempt-rt/tree/rt-6.17.5-rt7) identifies the scripts and configuration used for the build.

No license has been assigned to the custom scripts.
The kernel, RT patch and derived files remain subject to their respective licenses.
