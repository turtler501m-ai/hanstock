# OCI A1 Flex Success Strategy

Current Oracle Always Free A1 guidance is narrower than the original 4c/24g examples.
Use these safer defaults:

- `OCI_RETRY_PROFILES=1:6,2:12`
- `OCI_RETRY_CAPACITY_REPORT_MODE=gate`
- `OCI_RETRY_STOP_ON_CONFIG_ERROR=true`

Run diagnosis before repeated launch attempts:

```bash
python3 oci_retry.py diagnose --root /home/turtler800/oci-vm-retry
```

The retry command launches only when the compute capacity report says `AVAILABLE`.
`NotAuthorizedOrNotFound` is treated as a configuration error, not a capacity problem, and
the retry loop is paused until region, compartment, subnet, image, availability domain, and
IAM policy settings are fixed.

Multi-region mode:

- Put region-specific targets in `targets.json`.
- Set `OCI_RETRY_TARGETS_FILE=/home/turtler800/oci-vm-retry/targets.json`.
- Each target needs its own `region`, `availability_domain`, `subnet_id`, and `image_id`.
- The script checks every target's capacity and rotates launch attempts across target/profile pairs.

Region expansion check:

```bash
python3 oci_retry.py expand-regions --root /home/turtler800/oci-vm-retry \
  --region-keys IAD,PHX,FRA,LHR,NRT,KIX,SIN
```

This writes `region-subscription-status.json`. If Oracle returns
`TenantCapacityExceeded`, the tenancy is blocked from additional subscribed
regions until PAYG upgrade or subscribed-region limit increase. The retry
script can still run with the existing targets, but true multi-region launch
requires more READY region subscriptions plus region-specific subnet/image
targets.

Recommended path from public success cases:

1. Verify OCI ids and home region with `diagnose`.
2. Prefer 1c/6g first, then 2c/12g.
3. If staying on Free Tier keeps failing, consider PAYG with budget alerts and compartment quotas.
4. Keep total A1 usage within the Always Free allowance unless intentional paid usage is acceptable.
