# 19 — bitra hardware map for the mainline port (from the stock merged FDT, 2026-11-21)

Source: `/sys/firmware/fdt` of the stock-vendor 4.19 kernel (kept local: roms/mainline/stock/stock.dts, contains the serial).
Reproduce: `python3` walker over `dtc -I dtb -O dts`. GPIO numbers are TLMM unless noted. Not yet verified on mainline.

| Block | Stock description | Mainline status / plan |
|---|---|---|
| Panel | Samsung AMS662ZS01 "dvt dsc cmd mode", 1080x2400, 120/90/60 Hz, DSI0 4 lanes, DCS cmd mode + DSC, TE pin 66, reset GPIO 75, panel-vout GPIO 125, ESD flag GPIO (pm) , backlight via DCS 0..2047, supplies in `dsi_panel_pwr_supply` | no driver; write `panel-samsung-ams662zs01` from the on/off DCS blobs; DPU+DSI+DSC are upstream (kebab uses an AMB655X) |
| Display co-processor | Pixelworks Iris5 @ i2c 0x988000/0x26 (`dsi_iris_pwr_supply`) | must be bypassed/kept off; check whether the DSI path really goes through it on this variant |
| Touch | Synaptics **S3908** (oplus TouchComm) @ i2c 0xa94000/0x4b, IRQ GPIO 39, reset GPIO 38, vdd 2.8 V + vcc 1.8 V, 16x35 channels | not RMI4; needs a TouchComm (TCM) input driver — port |
| Buttons | gpio-keys (vol on pm8150 gpios 6/7 as in OnePlus common), power on pon | likely ok from the OnePlus common dtsi |
| Haptics | AWINIC AW8697 @ i2c 0xa8c000/0x5a | upstream has aw8695/aw86927 only — port or skip |
| Charger/gauge | MP2650 @ 0x994000/0x5c, charge-pump divider 0x68, BQ27541 gauge @ 0x888000/0x55, RK826 fast-charge MCU @0x0a, SMB1390 slave | oplus VOOC — mostly out of tree; gauge bq27xxx exists upstream |
| Audio | 2x TFA98xx @ i2c 0x884000/0x34,0x35, WCD938x, WSA/RX/TX macros, FSA4480 usb-c mux @0x42 | Q6 stack upstream; TFA98xx out of tree |
| NFC | NQ-NCI @ i2c 0x984000/0x28 | nxp-nci/st? mainline `nxp-nci` covers NQ-style with DT tweaks |
| FM radio | rtc6226 @ 0x884000/0x64 | skip |
| PMICs | pm8150 / pm8150b / pm8150l / pm8009 (pm8008 @ i2c 0x988000/0x8,0x9) | in OnePlus common dtsi |
| Modem | Qualcomm X55 (mpss), IPA | no upstream nodes (docs/12) |
| Memory map | identical to OnePlus 8T kebab (framebuffer 0x9c000000, ramoops 0xb0000000) | reused |
| Project IDs | oplus dtsi_no 0x5473, prjname 2169A, board-id 0x10008 | |
