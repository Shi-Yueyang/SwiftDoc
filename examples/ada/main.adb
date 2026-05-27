-- main.adb - Entry point demonstrating cross-package coordination

with Types;       use Types;
with Sensor;      use Sensor;
with Spi_Driver;  use Spi_Driver;
with System_Pkg;  use System_Pkg;

procedure Main is
   My_Config  : UartConfig := (Baudrate => 115200, DataBits => 8, Parity => 0);
   My_Status  : Status;
   My_Spi     : SpiHandlePtr;
   My_Data    : BYTE;
   Reading    : SensorData;
   Cal_Offset : Integer := 5;
begin
   -- Initialize sensor subsystem
   Init_Sensor(My_Config, My_Status);

   if My_Status /= OK then
      return;
   end if;

   -- Initialize SPI
   Init_Spi(Master, My_Spi);

   -- Start system ticking
   Tick;

   -- Perform SPI transfer
   Transfer(My_Spi, My_Data);

   -- Read sensor data
   Reading := Read_Sensor;

   -- Calibrate with reading
   Calibrate(Cal_Offset);

   -- Clean shutdown
   Reset_System;
end Main;
