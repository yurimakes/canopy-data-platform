#!/usr/bin/env python3

import json

SPEED_KMH = 23.33237837
SEQUENCE_LENGTH = 200

print(json.dumps({"speed_sequence": [SPEED_KMH] * SEQUENCE_LENGTH}, indent=2))
