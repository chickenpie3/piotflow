# Raspberry Pi Setup Notes

## WPA Supplicant
Use wpa supplicant to connect to wifi by updating wpa_supplicant.conf:

`wpa_passphrase [SSID] [password] > /etc/wpa_supplicant/wpa_supplicant.conf`

Must be run in a root shell

## Systemd for piotflow service
Copy `piotflow.service` to /etc/systemd/system
Copy piotflow.sh, python, key and crt files to /usr/sbin/piotflow/

To start, stop, or restart the service:

```
sudo systemctl stop piotflow  
sudo systemctl stop piotflow
sudo systemctl restart piotflow
```

To start the service automatically at boot:

`sudo systemctl enable piotflow`
