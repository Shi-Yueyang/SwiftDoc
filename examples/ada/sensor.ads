-- sensor.ads - Sensor management package spec

with Types; use Types;

package Sensor is

   Sensor_Active : Boolean := False;

   procedure Init_Sensor(Config : in UartConfig; Status_Out : out Status);

   function Read_Sensor return SensorData;

   procedure Calibrate(Offset : in out Integer);

end Sensor;
