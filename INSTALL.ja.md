# Ubuntu 24.04向けPREEMPT_RTカーネルのインストール

[English README](README.md)

このリポジトリは、Ubuntu配布カーネルの設定を基準に、Linux 6.17.5へrt7パッチを適用するビルドスクリプトとDebianパッケージを提供する。
対象はUbuntu 24.04 / amd64であり、配布パッケージを使えばビルドは不要である。

## 導入条件

- Ubuntu 24.04 / amd64で、必要な外部ドライバーがこのカーネルに対応していること。
- `/usr` に約3 GiB、`/boot` に約1 GiBの空き容量があること。任意のデバッグシンボルには、さらに約8 GiBを確保する。
- 起動に失敗した場合、コンソールでGRUBを操作し、旧カーネルを選べること。
- Secure Bootを無効にするか、別途署名と鍵登録を用意すること。このカーネルにはCanonicalの起動用署名がない。

切り戻しに使う旧カーネルは残しておく。
次のコマンドでOS、アーキテクチャ、空き容量を確認する。
UEFI環境では `mokutil --sb-state` でSecure Bootの状態も確認する。

```bash
cat /etc/os-release
dpkg --print-architecture
df -h /usr /boot
```

## ダウンロードとインストール

[配布用ReleaseのAssets](https://github.com/FuminoriSugawara/ubuntu24-preempt-rt/releases/tag/rt-6.17.5-rt7) から、次の3ファイルを同じディレクトリに保存する。

- `linux-image-6.17.5-rt7_6.17.5-rt7-1_amd64.deb`
- `linux-headers-6.17.5-rt7_6.17.5-rt7-1_amd64.deb`
- `SHA256SUMS`

保存先で次のコマンドを実行し、2パッケージがともに `OK` になってからインストールする。
`--ignore-missing` は未取得のデバッグパッケージを検証対象から外すために指定する。

```bash
sha256sum --check --ignore-missing SHA256SUMS
```

```bash
sudo apt install ./linux-image-6.17.5-rt7_6.17.5-rt7-1_amd64.deb \
  ./linux-headers-6.17.5-rt7_6.17.5-rt7-1_amd64.deb
```

インストールと必要なDKMSドライバーのビルドにエラーがなく、次の2ファイルが存在することを確認する。

```bash
ls -lh /boot/vmlinuz-6.17.5-rt7 /boot/initrd.img-6.17.5-rt7
```

### デバッグシンボル（任意）

同じReleaseから `linux-image-6.17.5-rt7-dbg_6.17.5-rt7-1_amd64.deb` を取得し、`SHA256SUMS` と同じディレクトリに保存する。
このパッケージが `OK` になることを確認してからインストールする。

```bash
sha256sum --check --ignore-missing SHA256SUMS
sudo apt install ./linux-image-6.17.5-rt7-dbg_6.17.5-rt7-1_amd64.deb
```

## 既定カーネルの設定と再起動

`6.17.5-rt7` を既定の起動対象にし、検証中はGRUBメニューを10秒間表示する。
設定を別ファイルに分け、後から待ち時間だけを元に戻せるようにする。

```bash
printf '%s\n' 'GRUB_DEFAULT="Advanced options for Ubuntu>Ubuntu, with Linux 6.17.5-rt7"' | \
  sudo tee /etc/default/grub.d/zz-rt-default.cfg
```

```bash
printf 'GRUB_TIMEOUT_STYLE=menu\nGRUB_TIMEOUT=10\n' | \
  sudo tee /etc/default/grub.d/zz-rt-menu.cfg
sudo env LC_ALL=C update-grub
```

`LC_ALL=C` は、起動対象の指定に使った英語のメニュー名で設定を生成するために指定する。
`update-grub` が成功し、`vmlinuz-6.17.5-rt7` が検出されたことを確認する。
稼働中の作業を終了し、コンソールを操作できる状態で再起動する。
何も操作しなければ10秒後にこのカーネルで起動する。
別のカーネルを選ぶ場合は「Advanced options for Ubuntu」から選択する。

```bash
sudo reboot
```

起動後、次の出力がそれぞれ `6.17.5-rt7` と `1` になることを確認する。

```bash
uname -r
cat /sys/kernel/realtime
```

続けて、使用するデバイスとアプリケーションの動作を確認する。

## 検証後に待ち時間を元に戻す

メニュー表示用の設定だけを削除する。
表示方法と待ち時間は元の設定に戻り、RTカーネルを既定にする設定は残る。

```bash
sudo rm /etc/default/grub.d/zz-rt-menu.cfg
sudo env LC_ALL=C update-grub
```

## 新しい版への更新

新しい版は [Releases](https://github.com/FuminoriSugawara/ubuntu24-preempt-rt/releases) から取得して手動でインストールする。
新版の動作確認が済むまで、現在のカーネルは残しておく。

1. 新版の本体、headers、`SHA256SUMS` を別のディレクトリに保存する。デバッグシンボルが必要な場合は、同じ版のパッケージも取得する。
2. [ダウンロードとインストール](#ダウンロードとインストール)のファイル名を新版に置き換え、チェックサムとインストール結果を確認する。
3. [既定カーネルの設定と再起動](#既定カーネルの設定と再起動)に従い、GRUB設定の `6.17.5-rt7` を新版のカーネル名に置き換える。10秒のメニュー表示を解除していた場合は再設定する。
4. 再起動後、`uname -r` が新版のカーネル名、`/sys/kernel/realtime` が `1` であることを確認し、デバイスとアプリケーションの動作を確認する。
5. 確認が済んだら、[待ち時間を元に戻す](#検証後に待ち時間を元に戻す)。

カーネル名は、本体のファイル名の `linux-image-` から最初のアンダースコアまでの部分である。
その後に続くパッケージ版とは区別する。
新版に問題がある場合はGRUBから旧カーネルで起動し、同じ設定手順で旧カーネル名を既定に戻す。

## 旧カーネルへの切り戻し

GRUBから旧カーネルで起動し、`uname -r` で確認する。
既定の起動対象の指定を解除し、不要になったRTパッケージを削除する。

```bash
sudo rm /etc/default/grub.d/zz-rt-default.cfg
sudo update-grub
```

```bash
sudo apt remove linux-image-6.17.5-rt7 linux-headers-6.17.5-rt7
sudo update-grub
```

デバッグシンボルも導入した場合は、`linux-image-6.17.5-rt7-dbg` を削除対象に追加する。

<details>
<summary>自分でビルドする場合</summary>

Dockerを操作できるx86_64環境と約100 GiBの空き容量を用意する。
スクリプトはソースとパッチを取得・検証し、バックグラウンドでビルドする。

```bash
git clone --branch rt-6.17.5-rt7 https://github.com/FuminoriSugawara/ubuntu24-preempt-rt.git
cd ubuntu24-preempt-rt
JOBS=16 MEMORY=24g ./build-rt-kernel.sh
source scripts/kernel-settings.sh
docker logs --tail 30 -f "$DEFAULT_CONTAINER_NAME"
```

ログの追跡はCtrl+Cで終了できる。
コンテナが `exited`、終了コードが `0` になった後で成果物を検査する。

```bash
docker inspect --format '{{.State.Status}} exit={{.State.ExitCode}}' "$DEFAULT_CONTAINER_NAME"
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD:/workspace" -w /workspace rt-kernel-builder:noble \
  bash scripts/check-artifacts.sh
```

パッケージは `artifacts/6.17.5-rt7/` に保存される。
ビルド機へのインストールは行わない。

</details>

## ソースと利用条件

Linuxの元ソースとRTパッチは [ソース用Release](https://github.com/FuminoriSugawara/ubuntu24-preempt-rt/releases/tag/sources-6.17.5-rt7)、ビルド時のスクリプトと設定は [配布版のタグ](https://github.com/FuminoriSugawara/ubuntu24-preempt-rt/tree/rt-6.17.5-rt7) から取得できる。

自作スクリプトにはライセンスを付与していない。
Linux本体、RTパッチ、および派生するファイルは、それぞれのライセンス条件に従う。
