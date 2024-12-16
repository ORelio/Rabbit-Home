# Codesend

This folder contains a compiled version of [codesend](https://github.com/ninjablocks/433Utils/blob/master/RPi_utils/codesend.cpp) from the [433Utils](https://github.com/ninjablocks/433Utils) library for ARM32, tested on Raspberry Pi 1 and 3. This utility allows sending 433MHz command codes using a dedicated module such as FS1000A.

# Setup

1. Copy `codesend` on your Pi
1. `sudo mv codesend /usr/local/bin/codesend`
2. `sudo chown root:root /usr/local/bin/codesend`
3. `sudo chmod 755 /usr/local/bin/codesend`
4. `sudo chmod u+s /usr/local/bin/codesend`
5. The `codesend` command is now available

# Wiring

Wiring FS1000A module on Raspberry Pi:

```
           3.3V [01] [02] 5V
          GPIO2 [03] [04] 5V     <= VCC
          GPIO3 [05] [06] GND    <= GND
          GPIO4 [07] [08] GPIO14
            GND [09] [10] GPIO15
DATA  => GPIO17 [11] [12] GPIO18
         GPIO27 [13] [14] GND
```

# Build instructions

To compile from source, the following (dated) build instructions might still work:

```
sudo -s
apt install git
git clone https://git.pofilo.fr/mirrors/wiringPi
cd wiringPi
./build
cd ..
git clone --recursive git://github.com/ninjablocks/433Utils.git
cd 433Utils/RPi_utils
make
cp codesend /usr/local/bin/
chown root:root /usr/local/bin/codesend
chmod 755 /usr/local/bin/codesend
chmod u+s /usr/local/bin/codesend
cd ../../
rm -rf wiringPi 433Utils
exit
```
