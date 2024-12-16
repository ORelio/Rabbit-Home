# ShutterCMD

A simple Linux wrapper program around Serial-Over-USB ESP8266 interface offered by the [Yokis-Hack](https://github.com/nmaupu/yokis-hack) project, allowing unprivileged users to pass commands to the microcontroller's command prompt using the `shuttercmd` command. Based on [CppLinuxSerial](https://github.com/gbmhunter/CppLinuxSerial) as of commit [cf8ca48](https://github.com/gbmhunter/CppLinuxSerial/tree/cf8ca480c4d09dc07ee86a8787a7ab6b31aaf40b).

# Setup

1. Plug dongle on Linux computer
2. `ls /dev/serial/by-id`
3. Edit `main.cpp` and set device path by ID and baud rate
4. Run `./build.sh` to build `shuttercmd`
5. `sudo mv shuttercmd /usr/local/bin/shuttercmd`
6. `sudo chown root:root /usr/local/bin/shuttercmd`
7. `sudo chmod 755 /usr/local/bin/shuttercmd`
8. `sudo chmod u+s /usr/local/bin/shuttercmd`
9. The `shuttercmd` command is now available
