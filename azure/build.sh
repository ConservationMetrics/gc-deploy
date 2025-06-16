#!/bin/bash

# Destination directory for the built ARM template
DST="../build/azure"
mkdir -p "$DST"

# Minimize cloud-config.yml:
# Add comma separator between lines (prefix all lines except the first),
# then wrap each line in single quotes (\047) and add literal \n for newlines.
# Write output to a temp file ( replacement.txt )
awk 'NR > 1 {printf(", ")} {gsub(/"/, "\\\""); printf "\047%s\\n\047", $0}' < cloud-config.yml > replacement.txt

# Wrap the entire content of replacement.txt with a JSON property definition
# that wraps the cloud-init content in ARM template base64(concat()) function
gawk -i inplace '$0="          \"customData\": \"[base64(concat("$0"))]\","' replacement.txt

# Find the __CLOUD_INIT__ placeholder in new-vm.arm.json.
# Replace its entire line with the contents of replacement.txt (r command),
# then delete the placeholder line (d command).
# Output the built ARM template to $DST directory.
sed '/__CLOUD_INIT__/{
r replacement.txt
d
}' < new-vm.arm.json > $DST/new-vm.arm.json

# Clean up temporary file
rm replacement.txt