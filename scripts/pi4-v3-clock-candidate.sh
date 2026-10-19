#!/bin/bash
# Create a *separate, unqualified* Pi4 clock test image; never change the base.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[[ $# == 3 && ( "$1" == 1800 || "$1" == 2000 ) ]] || {
  echo "Usage: $0 1800|2000 BASE.img NEW-TEST.img" >&2; exit 2;
}
mhz=$1
source_image=$(realpath -- "$2")
output_image=$(realpath -m -- "$3")
[[ -f "$source_image" && ! -b "$source_image" && ! -e "$output_image" ]] || {
  echo 'Source must be a regular image; output must be new' >&2; exit 2;
}
[[ "$source_image" == "$repo"/output/* && "$output_image" == "$repo"/output/* ]] || {
  echo 'Only repository output/ image paths are accepted' >&2; exit 2;
}
offset=$(sfdisk --json "$source_image" | python3 -c 'import json,sys; p=json.load(sys.stdin)["partitiontable"]["partitions"][0]; assert p["type"]=="c"; print(p["start"]*512)')
temporary=$(mktemp)
trap 'rm -f -- "$temporary"' EXIT
mtype -i "${source_image}@@${offset}" ::config.txt > "$temporary"
if ! rg -qx 'arm_freq=1500' "$temporary" || ! rg -qx 'arm_boost=0' "$temporary" ||
   rg -q '^(over_voltage|force_turbo)=' "$temporary"; then
  echo 'Base must have only the conservative 1.5GHz boot clock' >&2; exit 2
fi
sed -i "s/^arm_freq=1500$/arm_freq=${mhz}/" "$temporary"
printf '\n# UNVALIDATED TEST ONLY: restore 1.5GHz after testing\n' >> "$temporary"
cp --reflink=always --no-clobber -- "$source_image" "$output_image"
mcopy -o -i "${output_image}@@${offset}" "$temporary" ::config.txt
mtype -i "${output_image}@@${offset}" ::config.txt | rg -q "^arm_freq=${mhz}$"
echo "UNVALIDATED TEST IMAGE: $output_image"
sha256sum "$output_image"
