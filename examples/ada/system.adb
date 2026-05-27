-- system.adb - System implementation

with Sensor;

package body System_Pkg is

   Raw_Sensor_Data : Integer := 100;

   procedure Tick is
   begin
      System_Tick := System_Tick + 1;
      if System_Tick mod 10 = 0 then
         Raw_Sensor_Data := Raw_Sensor_Data + 1;
      end if;
   end Tick;

   function Get_Raw_Value return Integer is
   begin
      return Raw_Sensor_Data;
   end Get_Raw_Value;

   procedure Reset_System is
   begin
      System_Status := OK;
      System_Tick := 0;
      Raw_Sensor_Data := 0;
      Tick;
   end Reset_System;

end System_Pkg;
