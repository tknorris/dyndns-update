#!/usr/bin/env python3
import os
import sys
import re
import json
import logging
import subprocess
import random
import requests
from time import sleep

logging.basicConfig(
    stream=sys.stdout, format="%(asctime)s %(levelname)s %(filename)s:%(lineno)d %(message)s - (%(threadName)s)")
logging.getLogger().setLevel(os.environ.get("LOG_LEVEL", logging.INFO))

USER_AGENT = os.environ.get("USER_AGENT")


def http_get(url, headers=None, auth=None):
    if headers is None: headers = {}  # noqa: E701

    if USER_AGENT is not None:
        headers.update({"User-Agent": USER_AGENT})

    try:
        res = requests.get(url=url, headers=headers, auth=auth)
        res.raise_for_status()
    except requests.HTTPError:
        if res.status_code != 418:
            raise

    return res


def dig_method():
    res = subprocess.run(["dig", "+short", "myip.opendns.com", "@resolver1.opendns.com"], capture_output=True)
    res.check_returncode()
    return res.stdout.decode().strip()


def ifconfig_method():
    res = http_get("https://ifconfig.co/json")
    return res.json().get("ip", "")


def http_method(service):
    try:
        url = service["url"]
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
            m = re.match("(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", res.text)  # noqa: W605
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
    last_file = "/tmp/last_ip"

    http_services = get_http_services(os.environ["HTTP_SERVICES"])
    methods = [dig_method, ifconfig_method] + [http_method] * len(http_services)

    duck_enable = bool(duck_domains and duck_token)
    dom_enable = bool(dom_username and dom_password)
    logging.info(f"Sleep pause: {sleep_secs}s HTTP Services: {len(http_services)} DuckDNS: {duck_enable} DOM: {dom_enable}")

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
                url = f"https://www.duckdns.org/update?domains={duck_domains}&token={duck_token}&ip="
                res = http_get(url)
                logging.info(f"DuckDNS Response: {res.text}")

            # Only try the dns-o-matic update if we got an ip because it's not inferred
            if ip and dom_enable:
                url = f"https://updates.dnsomatic.com/nic/update?hostname=all.dnsomatic.com&myip={ip}"
                res = requests.get(url, auth=(dom_username, dom_password))
                res.raise_for_status()
                logging.info(f"DNS-O-Matic Response: {res.text}")

            update_last_ip(last_file, ip)

        logging.info(f"Waiting for {sleep_secs} seconds...")
        sleep(sleep_secs)


if __name__ == "__main__":
    sys.exit(main())
