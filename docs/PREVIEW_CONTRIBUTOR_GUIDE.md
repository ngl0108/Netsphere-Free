# Free Intake Contributor Guide

## Purpose

This guide explains how to use NetSphere Free Intake Edition to experience discovery, topology, and connected NMS first, then contribute masked raw output safely.

## Recommended free edition journey

1. Run auto discovery.
2. Review topology and path trace.
3. Inspect device detail, diagnosis, and observability.
4. Open `Data Contribution` only when you want to help improve parser quality.

## Contribution workflow

1. Log in to NetSphere Free.
2. Accept product terms on first run.
3. Optionally enable parser-contribution upload. You can skip this and still use discovery, topology, and connected NMS.
4. Open `Data Contribution`.
5. Choose one of:
   - `Device capture`
   - `Manual paste`
6. Select only the allowlisted commands.
7. Generate the sanitized preview.
8. Review the masked output carefully.
9. Confirm consent.
10. Upload the sanitized contribution.

## Recommended commands

- `show version`
- `show inventory`
- `show interfaces brief`
- `show vlan`
- `show mac address-table`
- `show lldp neighbors detail`
- `show cdp neighbors detail`
- `show ip route summary`
- `show ospf neighbor`
- `show bgp summary`
- `show evpn summary`
- `show vxlan vni`

## Do not submit

- full configuration outputs
- account or AAA outputs
- certificates or private keys
- cloud credential outputs
- firewall policy dumps
- anything you do not want masked and reviewed

## Review checklist

- hostnames are masked
- IP addresses are tokenized
- serial numbers are masked
- obvious secret strings are redacted
- command structure is still readable

## Operator note

If the sanitized preview still exposes identifying data, do not upload it. Remove the block manually and regenerate the preview.
