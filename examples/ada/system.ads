-- system.ads - System-level functions and global state

package System_Pkg is

   System_Status : Status := OK;
   System_Tick   : Integer := 0;

   procedure Tick;

   function Get_Raw_Value return Integer;

   procedure Reset_System;

end System_Pkg;
