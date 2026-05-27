-- types.ads - Shared type definitions for the example Ada project

package Types is

   -- Status enumeration for return codes
   type Status is (OK, Error, Timeout, Busy);

   -- 2D point with coordinates
   type Point is record
      X : Integer;
      Y : Integer;
   end record;

   -- Configuration for UART peripheral
   type UartConfig is record
      Baudrate : Integer;
      DataBits : Integer;
      Parity   : Integer;
   end record;

   -- Sensor data variant
   type SensorData is record
      Value     : Integer;
      Threshold : Integer;
   end record;

   -- Hardware register width aliases
   subtype BYTE is Integer range 0 .. 255;
   subtype WORD is Integer range 0 .. 65535;

   -- SPI communication mode
   type SpiMode is (Master, Slave);

   -- Incomplete forward declaration for access type
   type SpiHandle;

   -- Pointer to SPI handle
   type SpiHandlePtr is access SpiHandle;

   -- SPI peripheral handle
   type SpiHandle is record
      Mode     : SpiMode;
      BusyFlag : BYTE;
   end record;

end Types;
