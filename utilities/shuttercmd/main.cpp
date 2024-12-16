#include <iostream>
#include "SerialPort.hpp"

using namespace mn::CppLinuxSerial;

int main(int argc, char *argv[])
{
	if (argc > 1)
	{
		SerialPort serialPort("/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0", BaudRate::B_115200);
		serialPort.Open();
		serialPort.Write(argv[1]);
		serialPort.Write("\r\n");
		serialPort.Close();
	}
	else
	{
		std::cout << argv[0];
		std::cout << " <command>";
		std::cout << std::endl;
	}
}
