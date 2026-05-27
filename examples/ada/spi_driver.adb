-- spi_driver.adb - SPI driver implementation

package body Spi_Driver is

   procedure Init_Spi(Mode : in SpiMode; Handle : out SpiHandlePtr) is
   begin
      Handle := new SpiHandle;
      Handle.Mode := Mode;
      Handle.BusyFlag := 0;
      Spi_Ready := True;
   end Init_Spi;

   procedure Transfer(Handle : in out SpiHandlePtr; Data : out BYTE) is
   begin
      if not Spi_Ready then
         Data := 0;
         return;
      end if;
      Handle.BusyFlag := 1;
      Data := 42;
      Handle.BusyFlag := 0;
   end Transfer;

end Spi_Driver;
