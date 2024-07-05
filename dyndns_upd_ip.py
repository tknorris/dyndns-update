#!/usr/bin/env python3
import os
import sys
import logging
import subprocess
import random
import requests
from time import sleep

logging.basicConfig(
    stream=sys.stdout, format="%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s - (%(threadName)s)")
logging.getLogger().setLevel(os.environ.get("LOG_LEVEL", logging.INFO))


def dig_method():
    res = subprocess.run(["dig", "+short", "myip.opendns.com", "@resolver1.opendns.com"], capture_output=True)
    res.check_returncode()
    return res.stdout.decode().strip()


def http_method(service):
    url = service["url"]
    if not url.startswith("http"):
        url = f"https://{url}"

    res = requests.get(url=url)
    res.raise_for_status()
    return res.text


def get_last_ip(file_path):
    try:
        with open(file_path, "r") as f:
            last_ip = f.read()
    except:
        last_ip = ""
    return last_ip


def update_last_ip(file_path, ip):
    with open(file_path, "w") as f:
        f.write(ip)


def main(argv=None):
    """
    main
    """
    if sys.argv: argv = sys.argv  # noqa: E701, F841
    sleep_secs = int(os.environ.get("SLEEP_SECS", 3600))
    max_retries = int(os.environ.get("MAX_RETRIES", 3))
    duck_domains = os.environ.get("DUCK_DOMAINS", "")
    duck_token = os.environ.get("DUCK_TOKEN", "")
    dom_username = os.environ.get("DOM_USERNAME", "")
    dom_password = os.environ.get("DOM_PASSWORD", "")
    LAST_FILE = "/tmp/last_ip"

    http_services = [
        {"url": "ifconfig.co"},
        {"url": "ipecho.net/plain"},
        {"url": "ipv4.icanhazip.com"},
        {"url": "whatismyip.akamai.com"},
        {"url": "v4.ident.me"},
        {"url": "ipinfo.io/ip"},
        {"url": "www.trackip.net/ip"},
        {"url": "ip.tyk.nu" },
        {"url": "api.ipify.org"},
        {"url": "myexternalip.com/raw"},
        {"url": "wgetip.com"}]

    methods = [dig_method] + [http_method] * len(http_services)

    duck_enable = bool(duck_domains and duck_token)
    dom_enable = bool(dom_username and dom_password)
    logging.info(f"Sleep pause: {sleep_secs}s HTTP Services: {len(http_services)} DuckDNS: {duck_enable}")

    while True:
        last_ip = get_last_ip(LAST_FILE)
        ip = ""
        retries = 0
        while not ip and retries <= max_retries:
            choice = random.choice(methods)
            if choice == http_method:
                http_choice = random.choice(http_services)
                ip = http_method(http_choice)
                log_method = f"http_method: {http_choice}"
            else:
                ip = dig_method()
                log_method = "dig_method"
            logging.info(f"Got {ip} from {log_method}")
            retries += 1

        logging.info(f"Updating IP to: {ip}")
        if ip != last_ip:
            # Try the duckdns update even if we got no IP because it's inferred
            if duck_enable:
                url = f"https://www.duckdns.org/update?domains={duck_domains}&token={duck_token}&ip="
                res = requests.get(url)
                res.raise_for_status()
                logging.info(f"DuckDNS Response: {res.text}")

            # Only try the dns-o-matic update if we got an ip because it's not inferred
            if ip and dom_enable:
                url = f"https://updates.dnsomatic.com/nic/update?hostname=all.dnsomatic.com&myip={ip}"
                res = requests.get(url, auth=(dom_username, dom_password))
                res.raise_for_status()
                logging.info(f"DNS-O-Matic Response: {res.text}")

        logging.info(f"Waiting for {sleep_secs} seconds...")
        sleep(sleep_secs)


if __name__ == "__main__":
    sys.exit(main())
