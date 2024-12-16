#include <iostream>
#include <vector>
#include "SerialPort.hpp"

using namespace mn::CppLinuxSerial;

int main(int argc, char *argv[])
{
	std::vector<uint8_t> readVector;
	SerialPort serialPort("/dev/serial/by-id/usb-FTDI_FT231X_USB_UART_D30DPN8O-if00-port0", BaudRate::B_57600, NumDataBits::EIGHT, Parity::NONE, NumStopBits::ONE);
	serialPort.Open();
	while (1)
	{
		serialPort.ReadBinary(readVector);
		for (const uint8_t& b : readVector)
		{
			std::cout << b;
		}
		std::cout << std::flush;
		readVector.clear();
	}
}
