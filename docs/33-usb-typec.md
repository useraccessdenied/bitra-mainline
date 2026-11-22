# 33 — USB, Type-C roles and OTG power (2026-11-22)

Status: **device role verified with the Type-C port manager in charge; host (OTG) mode untested** (no OTG adapter available yet).

## Verified (RAM-boot images `a-28`, `a-29`, flashed image unchanged)
- The OnePlus 8T tree already carries the full dual-role setup (PM8150B `qcom,pm8150b-typec` with the PD PHY, DWC3 `usb-role-switch`, the connector with DRP/DFP/UFP PDOs, FSA4480 SBU mux). The bitra DT used to override it with `dr_mode = "peripheral"`, `/delete-property/ usb-role-switch` "for the debug link". Removing that override works: with the Mac connected the NCM gadget shell comes back after ~30 s, `usb_role` = `device`, UDC `configured`, Type-C `port0` + `port0-partner` (the Mac), data role `device`, power role `sink`, PD revision 3.0, `tcpm-source-psy` online (5 V, 3 A advertised).
- `usb_otg_vbus` (see below) stays **disabled** while the phone is a device, as required.

## OTG power: where the 5 V comes from (stock DT analysis)
- The Type-C driver (`qcom_pmic_typec_port.c`) takes VBUS from the (deprecated) `vdd-vbus` supply of the Type-C node. The OnePlus tree leaves it unset (log: `supply vdd-vbus not found, using dummy regulator`), so host mode could never power a device.
- On this phone the OTG boost is **not** the PM8150B `smb5_vbus`: the stock realme DT has `mp2650-charger@5c` on i2c5 with **`qcom,mps_otg_en-gpio = <&pm8150_gpios 3>`** (active high, pinctrl "mps_otg_en_active/sleep"), i.e. the external MPS **MP2650** charger/boost switched by pm8150 GPIO 3. (Stock also has `usb2_vbus_boost`/`dischg` pins on pm8150 gpio9/10 for the charge path.)
- DT now: `usb_otg_vbus` = `regulator-fixed`, 5.0 V, `gpio = <&pm8150_gpios 3 GPIO_ACTIVE_HIGH>`, wired as `&pm8150b_typec { vdd-vbus-supply = <&usb_otg_vbus>; }`. The port manager enables it only while the phone is a source (Attached.SRC).

## Untested / open
- **Host mode itself**: needs a USB-C OTG adapter with a low-power device. An autonomous logger (`/usr/local/bin/otg-log.sh`, detached, writes `/root/otg-test.log`: Type-C roles, `usb_role`, regulator state, `lsusb`, USB/Type-C dmesg lines, power supplies) was prepared so the test can be run with the Mac cable unplugged and read afterwards. Unknowns: whether the MP2650 produces 5 V from the enable pin alone (the Oplus driver also writes registers over i2c5 @0x5c), the current limit it applies, and VBUS-over-current behaviour.
- The committed DT is **not flashed** (`mainline-boot-7` still forces peripheral); verify host mode in a RAM-boot image first. Risk to watch: the phone entering the source role while a charger/host is attached (TCPM has `try-power-role = "sink"`, PD role swap rules apply).
- USB3 / orientation: `/delete-property/ mode-switch` on the QMP PHY is still in the bitra DT (USB 2.0 only for the combo PHY SS lanes, no DisplayPort alt mode), left as is.
- Wi-Fi is not reachable from the build workstation (different segment), so USB is the only control path: any USB test must be done in RAM-boot images.
