#!/bin/sh
# wpa-select-test.sh: stop NetworkManager, run wpa_supplicant by hand with full debug (/tmp/wpa-test.log), connect to the 2.4 GHz network, then switch to the 5 GHz
# network with select_network and see whether it associates. PSKs are taken from the NetworkManager profiles on the phone (never printed). Restores NetworkManager at the end.
# Run detached: setsid sh /tmp/wpa-select-test.sh >/dev/null 2>&1 &     Result: /tmp/wpa-select-test.out
D=/etc/NetworkManager/system-connections; O=/tmp/wpa-select-test.out; : > $O
f24=$(ls $D/bitra-Kapil2.4G* | head -1); f5=$(ls $D/bitra-Kapil-5G* | head -1)
p24=$(grep '^psk=' "$f24" | cut -d= -f2-); p5=$(grep '^psk=' "$f5" | cut -d= -f2-)
# NetworkManager stores either a passphrase or a 64-hex raw key: the raw key must not be quoted in wpa_supplicant.conf
q24=\"$p24\"; [ ${#p24} -eq 64 ] && q24=$p24
q5=\"$p5\"; [ ${#p5} -eq 64 ] && q5=$p5
cat > /tmp/wpa-test.conf <<EOC
ctrl_interface=/run/wpa-test
update_config=0
network={
 ssid="Kapil2.4G"
 psk=$q24
 key_mgmt=WPA-PSK
 scan_ssid=1
 id_str="a"
}
network={
 ssid="Kapil-5G"
 psk=$q5
 key_mgmt=WPA-PSK
 scan_ssid=1
 disabled=1
 id_str="b"
}
EOC
chmod 600 /tmp/wpa-test.conf
rc-service networkmanager stop >/dev/null 2>&1; killall wpa_supplicant 2>/dev/null; sleep 2
ip link set wlan0 up
wpa_supplicant -i wlan0 -c /tmp/wpa-test.conf -dd -t > /tmp/wpa-test.log 2>&1 &
sleep 3
W="wpa_cli -p /run/wpa-test -i wlan0"
for i in 1 2 3 4 5 6 7 8 9 10; do $W status | grep -q "wpa_state=COMPLETED" && break; sleep 2; done
echo "after start: $($W status | grep -E 'wpa_state|ssid=' | tr '\n' ' ')" >> $O
$W enable_network 1 >/dev/null; $W select_network 1 >> $O
for i in $(seq 1 15); do sleep 2; s=$($W status | grep wpa_state | cut -d= -f2); echo "t+$((i*2))s $s" >> $O; [ "$s" = COMPLETED ] && break; done
echo "final: $($W status | grep -E 'wpa_state|ssid=|freq' | tr '\n' ' ')" >> $O
echo "--- scan results:" >> $O; $W scan_results | grep -i kapil >> $O
killall wpa_supplicant 2>/dev/null; sleep 1
rm -f /tmp/wpa-test.conf    # holds the PSKs
rc-service networkmanager start >/dev/null 2>&1
echo restored >> $O
