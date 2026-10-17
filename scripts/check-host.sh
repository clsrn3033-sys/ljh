#!/bin/bash
set -u
failed=0
for tool in git python3 gcc g++ make which sed ld diff bash patch gzip bzip2 perl tar cpio unzip rsync file bc find awk wget; do
    if command -v "$tool" >/dev/null 2>&1; then
        printf 'OK      %s\n' "$tool"
    else
        printf 'MISSING %s\n' "$tool"
        failed=1
    fi
done
printf 'QEMU: '
command -v qemu-system-x86_64 || true
printf 'KVM visible: '
if [[ -r /dev/kvm && -w /dev/kvm ]]; then echo yes; else echo no; fi
printf 'Available disk:\n'
df -h -- "$(dirname -- "$0")"
exit "$failed"
