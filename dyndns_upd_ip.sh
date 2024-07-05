#!/bin/bash
log () {
    NOW=$(date +"%x %X")
    echo "[$NOW] $1"
}

set_http_fetch () {
    local com_str
    com_str=$(command -v curl)
    if [ $? -eq 0 ]; then
        com_str="$com_str -s -L"
        [ "$NO_CERT" -eq 1 ] && com_str="$com_str -k"
    else
        com_str=$(command -v wget)
        if [ $? -eq 0 ]; then
            com_str="$com_str -q -O -"
            [ "$NO_CERT" -eq 1 ] && com_str="$com_str --no-check-certificate"
        else
            log "No HTTP Fetch program found. Install curl or wget"
            exit 1
        fi
    fi

    echo "$com_str"
}

# Each IP detection method should echo the current IP Address as output
http_method () {
    local pick=$(( $RANDOM % ${#HTTP_SERVICES[@]} ))
    local url="${HTTP_SERVICES[$pick]}"
    if [[ $url != http* ]];then
        url="https://$url"
    fi
    $HTTP_FETCH $url
    return $pick
}

dig_method () {
    dig +short myip.opendns.com @resolver1.opendns.com
}

dyndns_method () {
    $HTTP_FETCH "http://checkip.dyndns.org" | sed -nE 's/.*IP Address: ([[:digit:].]+).*/\1/p'
}

ipapi_method () {
    $HTTP_FETCH "http://ip-api.com/line" | tail -1
}

tnx_method () {
    $HTTP_FETCH "https://tnx.nl/ip" | sed -nE 's/.*<([[:digit:].]+)>[[:space:]]*$/\1/p'
}

BASEPATH="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
. "$BASEPATH/dyndns.cfg"

[ -z $NO_CERT ] && NO_CERT=0
[ -z $MAXRETRIES ] && MAXRETRIES=0
DUCK_TOKEN=${DUCK_TOKEN//[[:space:]]/}
DUCK_DOMAINS=${DUCK_DOMAINS//[[:space:]]/}
LASTFILE="$BASEPATH/lastip"

# Additional methods names added to this array will get randomly chosen
METHODS=("http_method" "http_method" "http_method" "dig_method" "dyndns_method" "ipapi_method" "tnx_method")

# Additional hostnames added to this array will get randomly chosen in the http_method
HTTP_SERVICES=( \
    "ifconfig.co" "ipecho.net/plain" "ipv4.icanhazip.com" "whatismyip.akamai.com" \
    "v4.ident.me" "ipinfo.io/ip" "www.trackip.net/ip" \
    "ip.tyk.nu" "api.ipify.org" "myexternalip.com/raw" "wgetip.com")

HTTP_FETCH=$(set_http_fetch)

LASTIP=""
[ -f "$LASTFILE" ] && LASTIP=$(cat "$LASTFILE")

IP=""
try=1
while [[ "$IP" == "" || "$IP" == "GARBAGE" ]]; do
    PICK=$(( $RANDOM % ${#METHODS[@]} ))
    IP=$(${METHODS[$PICK]})
    curl_pick=$?

    if ! [[ "$IP" =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
        if [[ ${#IP} -lt 50 ]]; then
            log "Actual Response: |$IP|"
        fi
        IP="GARBAGE"
    fi

    message="Try #$try: Got $IP from ${METHODS[$PICK]}"
    if [ "${METHODS[$PICK]}" == "http_method" ]; then
        message="$message (${HTTP_SERVICES[$curl_pick]})"
    fi

    log "$message"

    if [ "$try" -gt "$MAXRETRIES" ]; then
        # Unable to get a good response, try to update dns anyway
        break
    fi
    (( ++try ))
done

if [ "$IP" == "GARBAGE" ]; then
    log "Skipping update got only garbage"
elif [ "$LASTIP" != "$IP" ]; then
    log "Updating IP to $IP"
    if [[ "$HTTP_FETCH" == *curl* ]]; then
        header='--header '
    else
        header='--header='
    fi

    if [ -z "$DUCK_TOKEN" ] || [ -z "$DUCK_DOMAINS" ]; then
        DUCK_TOKEN=$(echo "$DUCK_TOKEN" | shasum | awk '{print $1}')
        log "Incomplete duckdns.org config. Skipping duckdns.org update: |$DUCK_DOMAINS|$DUCK_TOKEN|"
    else
        url="https://www.duckdns.org/update?domains=$DUCK_DOMAINS&token=$DUCK_TOKEN&ip="
        response=$($HTTP_FETCH "$url")
        log "DuckDNS: $response"
    fi

    if [ -z "$DOM_USERNAME" ] || [ -z "$DOM_PASSWORD" ]; then
        DOM_PASSWORD=$(echo "$DOM_PASSWORD" | shasum | awk '{print $1}')
        log "Incomplete dns-o-matic config. Skipping dns-o-matic update: |$DOM_USERNAME|$DOM_PASSWORD|"
    else
        auth=$(echo -n "$DOM_USERNAME:$DOM_PASSWORD" | base64)
        echo $HTTP_FETCH

        url="https://updates.dnsomatic.com/nic/update?hostname=all.dnsomatic.com&myip=$IP" 
        response=$($HTTP_FETCH "$url" $header"Authorization: Basic $auth")
        log "DNS-O-Matic: $response"
    fi

    echo "$IP" > "$LASTFILE"
else
    log "IP Unchanged. Skipping Update."
fi
