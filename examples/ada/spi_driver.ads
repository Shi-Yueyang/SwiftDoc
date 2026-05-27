-- spi_driver.ads - SPI driver interface

with Types; use Types;

package Spi_Driver is

   Spi_Ready : Boolean := True;

   procedure Init_Spi(Mode : in SpiMode; Handle : out SpiHandlePtr);

   procedure Transfer(Handle : in out SpiHandlePtr; Data : out BYTE);

end Spi_Driver;
