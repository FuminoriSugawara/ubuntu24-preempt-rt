FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc-13 g++-13 bc flex bison libssl-dev libelf-dev libdw-dev \
    libncurses-dev dwarves debhelper fakeroot rsync cpio kmod python3 \
    curl ca-certificates xz-utils zstd git file && rm -rf /var/lib/apt/lists/*
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
