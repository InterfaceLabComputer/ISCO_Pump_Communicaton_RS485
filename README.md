# ISCO_Pump_Communicaton_RS485

A command line program used to communicate with a Teledyne ISCO D-Series Pump Controller. Uses an external USB to RS485 converter that attaches to the DB25 on the back of the controller. The program was developed for a research lab to use for outputting pressure and flow rate data from the ISCO pumps to a csv file. The program will also read the units being used and maximum allowable pressure and flowrate settings and output this information to the file header. The program can also be used to turn the pumps on or off. Currently only setup for two pumps but could be easily expanded to control more (or less).

Requires the modbus_tk module be manually installed and a custom DB25 to DB9 cable be soldered as per the ISCO manual pinout and the RS485-USB converter pinout. 

Only tested on Windows. The serial USB connection may need to be adjusted for UNIX(-like) systems.
