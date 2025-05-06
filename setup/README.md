# Setting up Rabbit Home

Rabbit Home can handle several rabbits at once. Installing can be done directly on a rabbit with limited functionality (no plugs433/enocean/shutters), or another Raspberry Pi on the same network (full functionality).

## Setup

1. Install utilities if you plan to use plugs433/enocean/shutters:
    * See `utilities` folder for instructions.
2. Install packages if you plan to use cameras:
    * See debian-packages.txt for instructions
3. Upload the `rabbit-home` folder to your home directory:
    * `/home/USERNAME/rabbit-home` should contain `rabbit-home.py`
4. Upload and install `requirements.txt`:
    * `pip3 install -r requirements.txt`
5. Enable lingering services for your account:
    * `sudo loginctl enable-linger USERNAME`
6. Create the `rabbithome` service:
    * `mkdir -p ~/.config/systemd/user`
    * `editor ~/.config/systemd/user/rabbithome.service`
    * Paste the following, adjusting your `USERNAME`:
```ini
[Unit]
Description=Rabbit Home
After=local-fs.target network.target systemd-tmpfiles-setup.service

[Service]
ExecStart=/usr/bin/env python3 /home/USERNAME/rabbit-home/rabbit-home.py
Restart=always
Type=simple

[Install]
WantedBy=default.target
```

6. Start service:
```
systemctl --user unmask rabbithome
systemctl --user enable rabbithome
systemctl --user restart rabbithome
systemctl --user status rabbithome
```

## Enroll rabbits

1. Edit `config/rabbits.ini` and add your rabbits
2. If the rabbit is not local (`127.0.0.1`), add direct SSH access from rabbit-home to the rabbit:

```bash
NABAZTAGIP=192.168.1.XXX # Set your rabbit IP here. The rabbit must have a static IP, see your router settings.
if [ ! -f ~/.ssh/id_rsa.pub ]; then ssh-keygen -b 4096; fi
PUBKEY=$(cat ~/.ssh/id_rsa.pub)
ssh pi@${NABAZTAGIP} "if [ ! -d ~/.ssh ]; then mkdir ~/.ssh; fi; echo '${PUBKEY}' >> ~/.ssh/authorized_keys; echo added ssh key."
ssh pi@${NABAZTAGIP} # Should get a shell on your rabbit without typing a password
```

## Configure

See `config` folder and edit files of interest.

Each configuration file has its own instructions inside.

After changing configuration files, restart the service to apply your changes:
```
systemctl --user restart rabbithome
```
