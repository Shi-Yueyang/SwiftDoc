-- sensor.adb - Sensor management package body

with System_Pkg;

package body Sensor is

   Last_Reading : SensorData := (Value => 0, Threshold => 100);

   procedure Init_Sensor(Config : in UartConfig; Status_Out : out Status) is
   begin
      if Config.Baudrate = 0 then
         Status_Out := Error;
         return;
      end if;
      Sensor_Active := True;
      Status_Out := OK;
   end Init_Sensor;

   function Read_Sensor return SensorData is
      Result : SensorData;
   begin
      if not Sensor_Active then
         return Last_Reading;
      end if;

      Result.Value := System_Pkg.Get_Raw_Value;
      Result.Threshold := Last_Reading.Threshold;

      if Result.Value > Result.Threshold then
         Result.Threshold := Result.Value;
      end if;

      Last_Reading := Result;
      return Result;
   end Read_Sensor;

   procedure Calibrate(Offset : in out Integer) is
   begin
      Offset := Offset + Last_Reading.Value;
      Last_Reading.Threshold := Last_Reading.Threshold + Offset;
   end Calibrate;

end Sensor;
