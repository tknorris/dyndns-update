#!/usr/bin/env python3
import os
import sys
import re
import json
import logging
import subprocess
import random
import requests
from datetime import datetime, timezone
from time import sleep

logging.basicConfig(
    stream=sys.stdout, format="%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s - (%(threadName)s)")
logging.getLogger().setLevel(os.environ.get("LOG_LEVEL", logging.INFO))

USER_AGENT = os.environ.get("USER_AGENT")


def http_get(url, headers=None, auth=None):
    if headers is None: headers = {}  # noqa: E701

    if USER_AGENT is not None:
        headers.update({"User-Agent": USER_AGENT})

    res = requests.get(url=url, headers=headers, auth=auth)
    # Tolerate 418 (some IP services return it as a "teapot" easter egg); raise on any other error status
    if res.status_code != 418:
        res.raise_for_status()

    return res


def dig_method():
    res = subprocess.run(["dig", "+short", "myip.opendns.com", "@resolver1.opendns.com"], capture_output=True)
    res.check_returncode()
    return res.stdout.decode().strip()


def ifconfig_method():
    res = http_get("https://ifconfig.co/json")
    return res.json().get("ip", "")


def http_method(service):
    url = service.get("url", "")
    try:
        if not url.startswith("http"):
            url = f"https://{url}"
        res = http_get(url)
        reg_exp = service.get("re")
        if reg_exp is not None:
            m = re.search(reg_exp, res.text, flags=re.DOTALL)
            if m is None:
                logging.warning(f"RE: {reg_exp} failed to match {url} result")
                ip = ""
            else:
                try:
                    ip = m.group("ip")
                except IndexError:
                    logging.warning(f"Missing 'ip' group from match: {reg_exp}")
                    ip = ""
        else:
            m = re.match(r"(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", res.text)
            if m is not None:
                ip = m.group("ip")
            else:
                res_text = "GARBAGE" if len(res.text) > 50 else res.text
                logging.warning(f"Got suspicious response from {url}: {res_text}")
                ip = ""

    except requests.RequestException as e:
        logging.warning(f"Exception during http_method: {url}: {e}")
        ip = ""

    return ip


def get_last_ip(file_path):
    try:
        with open(file_path, "r") as f:
            last_ip = f.read()
    except:  # noqa: E722
        last_ip = ""
    return last_ip


def update_last_ip(file_path, ip):
    with open(file_path, "w") as f:
        f.write(ip)


def get_http_services(file_path):
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception as e:  # noqa: E722
        logging.warning(f"Failed to load http services: {e}")
        return {}


CF_API_BASE = "https://api.cloudflare.com/client/v4"


def cf_get_zone_id(token, record_name):
    """Find the zone that owns record_name.

    Rather than guess where the registrable domain boundary is (which breaks
    for multi-label public suffixes like example.co.uk), list the account's
    zones and pick the longest zone name that record_name ends with."""
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(f"{CF_API_BASE}/zones", headers=headers, params={"per_page": 50})
    res.raise_for_status()
    zones = res.json().get("result", [])
    candidates = [
        z for z in zones
        if record_name == z["name"] or record_name.endswith("." + z["name"])
    ]
    if not candidates:
        raise RuntimeError(f"No Cloudflare zone found that owns '{record_name}'")
    best = max(candidates, key=lambda z: len(z["name"]))
    return best["id"]


def cf_get_record_id(token, zone_id, record_name):
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(
        f"{CF_API_BASE}/zones/{zone_id}/dns_records",
        headers=headers, params={"type": "A", "name": record_name})
    res.raise_for_status()
    result = res.json().get("result", [])
    if not result:
        raise RuntimeError(f"Cloudflare A record not found for '{record_name}'")
    return result[0]["id"]


def cf_update(token, record_name, ip, ttl=1, proxied=False):
    """Update the Cloudflare A record for record_name to point at ip.

    The Cloudflare update endpoint identifies the record by zone_id and
    dns_record_id in the URL path (not by hostname), so we look both up
    from the record name first. ttl=1 means 'automatic'."""
    zone_id = cf_get_zone_id(token, record_name)
    record_id = cf_get_record_id(token, zone_id, record_name)

    # Cloudflare caps the comment field at 100 chars
    comment = f"dyndns-update: set to {ip} at {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC"[:100]
    headers = {"Authorization": f"Bearer {token}"}
    body = {"type": "A", "name": record_name, "content": ip, "ttl": ttl, "proxied": proxied, "comment": comment}
    res = requests.put(
        f"{CF_API_BASE}/zones/{zone_id}/dns_records/{record_id}",
        headers=headers, json=body)
    res.raise_for_status()
    return res


def main(argv=None):
    """
    main
    """
    if sys.argv: argv = sys.argv  # noqa: E701, F841
    sleep_secs = int(os.environ.get("SLEEP_SECS", 3600))
    max_retries = int(os.environ.get("MAX_RETRIES", 3))
    duck_domains = os.environ.get("DUCK_DOMAINS", "")
    duck_token = os.environ.get("DUCK_TOKEN", "")
    cf_token = os.environ.get("CF_API_TOKEN", "")
    cf_record = os.environ.get("CF_RECORD_NAME", "")
    cf_proxied = os.environ.get("CF_PROXIED", "false").strip().lower() in ("1", "true", "yes")
    last_file = "/tmp/last_ip"

    http_services = get_http_services(os.environ["HTTP_SERVICES"])
    methods = [dig_method, ifconfig_method] + [http_method] * len(http_services)

    duck_enable = bool(duck_domains and duck_token)
    cf_enable = bool(cf_token and cf_record)
    logging.info(f"Sleep pause: {sleep_secs}s HTTP Services: {len(http_services)} DuckDNS: {duck_enable} Cloudflare: {cf_enable}")

    while True:
        last_ip = get_last_ip(last_file)
        ip = ""
        retries = 0
        while not ip and retries <= max_retries:
            choice = random.choice(methods)
            log_method = choice.__name__
            if choice == http_method:
                http_choice = random.choice(http_services)
                ip = http_method(http_choice)
                log_method += f" ({http_choice})"
            else:
                ip = choice()
            logging.info(f"Got {ip} from {log_method}")
            retries += 1

        if ip != last_ip:
            logging.info(f"Updating IP to: {ip}")
            # Try the duckdns update even if we got no IP because it's inferred
            if duck_enable:
                try:
                    url = f"https://www.duckdns.org/update?domains={duck_domains}&token={duck_token}&ip="
                    res = http_get(url)
                    logging.info(f"DuckDNS Response: {res.text}")
                except requests.RequestException as e:
                    logging.warning(f"DuckDNS update failed: {e}")

            # Only try the Cloudflare update if we got an ip because it's not inferred
            if ip and cf_enable:
                try:
                    res = cf_update(cf_token, cf_record, ip, proxied=cf_proxied)
                    logging.info(f"Cloudflare update {cf_record} -> {ip}: {res.json().get('success')}")
                except (requests.RequestException, RuntimeError, ValueError) as e:
                    # RuntimeError: zone/record not found. ValueError: non-JSON success body.
                    logging.warning(f"Cloudflare update failed, skipping: {e}")

            update_last_ip(last_file, ip)

        logging.info(f"Waiting for {sleep_secs} seconds...")
        sleep(sleep_secs)


if __name__ == "__main__":
    sys.exit(main())
