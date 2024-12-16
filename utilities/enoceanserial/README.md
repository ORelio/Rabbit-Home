# EnoceanSerial

A simple Linux wrapper program around Serial-Over-USB dongles used for Enocean protocol, allowing unprivileged access to the dongle using the `enoceanserial` command. Based on [CppLinuxSerial](https://github.com/gbmhunter/CppLinuxSerial) as of commit [d1a5d4f](https://github.com/gbmhunter/CppLinuxSerial/tree/d1a5d4f78bffb98e094ca86f1ab7cba426314f78).

# Setup

1. Plug dongle on Linux computer
2. `ls /dev/serial/by-id`
3. Edit `main.cpp` and set device path by ID and baud rate
4. Run `./build.sh` to build `enoceanserial`
5. `sudo mv enoceanserial /usr/local/bin/enoceanserial`
6. `sudo chown root:root /usr/local/bin/enoceanserial`
7. `sudo chmod 755 /usr/local/bin/enoceanserial`
8. `sudo chmod u+s /usr/local/bin/enoceanserial`
9. The `enoceanserial` command is now available
